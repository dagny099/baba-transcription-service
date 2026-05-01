"""OpenAI transcription provider.

This is the only fully-implemented provider in the MVP. It uses the OpenAI
Audio Transcriptions API and maps the response into the canonical schema.

Notes on response shapes:
- For `whisper-1`, `response_format="verbose_json"` returns segments with
  `start`, `end`, `text`, and an `avg_logprob` proxy for confidence.
- For `gpt-4o-mini-transcribe` and `gpt-4o-transcribe`, `verbose_json` is
  not always supported. We fall back to `response_format="json"` (plain
  text + minimal metadata) and emit a single segment.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transcript_workbench.config import AppConfig
from transcript_workbench.constants import (
    CONFIDENCE_NONE,
    CONFIDENCE_TOKEN_LOGPROB,
    JOB_STATUS_COMPLETED,
)
from transcript_workbench.models.canonical import (
    TranscriptionJob,
    TranscriptionResult,
    TranscriptSegment,
)
from transcript_workbench.models.features import EffectiveFeatures, RequestedFeatures
from transcript_workbench.providers.base import ProviderAdapter
from transcript_workbench.utils.ids import new_id
from transcript_workbench.utils.logging import get_logger

logger = get_logger(__name__)


# Models that support verbose_json (and therefore segment timestamps).
_VERBOSE_JSON_MODELS = {"whisper-1"}


class OpenAIProvider(ProviderAdapter):
    provider_name = "openai"

    def __init__(self, config: AppConfig):
        self.config = config

    def validate_config(self) -> list[str]:
        if not self.config.effective_openai_api_key:
            return [
                "OPENAI_API_KEY is missing. Set it in your .env file or "
                "enter a temporary key in the sidebar."
            ]
        return []

    def transcribe(
        self,
        audio_path: Path,
        job_id: str,
        original_filename: str,
        model: str,
        requested_features: RequestedFeatures,
        effective_features: EffectiveFeatures,
        raw_output_path: Path,
    ) -> TranscriptionResult:
        # Late import: keeps `openai` an optional import error
        # surfaced only at transcription time, not module-load time.
        from openai import OpenAI  # type: ignore

        api_key = self.config.effective_openai_api_key
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is missing. Set it in .env or in the sidebar."
            )

        client = OpenAI(api_key=api_key)

        use_verbose = model in _VERBOSE_JSON_MODELS
        response_format = "verbose_json" if use_verbose else "json"

        logger.info(
            "Calling OpenAI transcription: model=%s response_format=%s file=%s",
            model,
            response_format,
            audio_path.name,
        )

        with audio_path.open("rb") as audio_file:
            response = client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                response_format=response_format,
            )

        raw = _coerce_response_to_dict(response)
        raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_output_path.write_text(
            json.dumps(raw, indent=2, default=str), encoding="utf-8"
        )

        text = raw.get("text", "") or ""
        segments = _parse_segments(raw, job_id, model)
        duration = _parse_duration(raw)

        job = TranscriptionJob(
            job_id=job_id,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            status=JOB_STATUS_COMPLETED,
            original_filename=original_filename,
            file_hash=None,
            duration_seconds=duration,
            provider=self.provider_name,
            model=model,
            requested_features=requested_features,
            effective_features=effective_features,
            warnings=[],
        )

        return TranscriptionResult(
            job=job,
            text=text,
            segments=segments,
            words=[],
            raw_response_path=str(raw_output_path),
            artifacts={},
        )


# ----- helpers (also covered by tests) ---------------------------------------


def _coerce_response_to_dict(response: Any) -> dict[str, Any]:
    """Best-effort conversion of an OpenAI SDK response to a plain dict."""
    if hasattr(response, "model_dump"):
        try:
            return response.model_dump()
        except Exception:  # pragma: no cover - defensive
            pass
    if isinstance(response, dict):
        return response
    if hasattr(response, "to_dict"):
        try:
            return response.to_dict()  # type: ignore[no-any-return]
        except Exception:  # pragma: no cover
            pass
    if isinstance(response, str):
        return {"text": response}
    return {"text": str(response)}


def _parse_segments(
    raw: dict[str, Any], job_id: str, model: str
) -> list[TranscriptSegment]:
    """Map an OpenAI response (verbose_json or plain) to canonical segments."""
    raw_segments = raw.get("segments")
    if isinstance(raw_segments, list) and raw_segments:
        out: list[TranscriptSegment] = []
        for idx, s in enumerate(raw_segments):
            if not isinstance(s, dict):
                continue
            avg_logprob = s.get("avg_logprob")
            confidence: float | None = None
            confidence_type = CONFIDENCE_NONE
            if isinstance(avg_logprob, (int, float)):
                # avg_logprob is in (-inf, 0]; map roughly to (0, 1].
                # exp(avg_logprob) is bounded in (0, 1].
                import math

                confidence = math.exp(float(avg_logprob))
                confidence_type = CONFIDENCE_TOKEN_LOGPROB
            out.append(
                TranscriptSegment(
                    segment_id=new_id(),
                    job_id=job_id,
                    segment_index=idx,
                    start_seconds=_safe_float(s.get("start")),
                    end_seconds=_safe_float(s.get("end")),
                    speaker=None,
                    text=str(s.get("text", "")).strip(),
                    confidence=confidence,
                    confidence_type=confidence_type,
                    provider_metadata={
                        "provider": "openai",
                        "model": model,
                        "avg_logprob": avg_logprob,
                        "no_speech_prob": s.get("no_speech_prob"),
                        "compression_ratio": s.get("compression_ratio"),
                    },
                )
            )
        if out:
            return out

    # Fallback: single segment with the full text.
    text = raw.get("text", "") or ""
    if not text.strip():
        return []
    return [
        TranscriptSegment(
            segment_id=new_id(),
            job_id=job_id,
            segment_index=0,
            start_seconds=None,
            end_seconds=None,
            speaker=None,
            text=text.strip(),
            confidence=None,
            confidence_type=CONFIDENCE_NONE,
            provider_metadata={"provider": "openai", "model": model},
        )
    ]


def _parse_duration(raw: dict[str, Any]) -> float | None:
    duration = raw.get("duration")
    return _safe_float(duration)


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None
