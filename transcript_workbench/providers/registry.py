"""Provider registry.

Adding a new provider/model only requires adding a registry entry plus a
provider adapter — no UI rewrites.

Each model entry declares per-feature support, optional notes, and an
implemented flag. The UI uses `implemented=False` to mark a provider as
"coming soon" without removing it from the dropdown.
"""

from __future__ import annotations

from typing import Any

from transcript_workbench.constants import (
    FEATURE_DIAGNOSTIC,
    FEATURE_PARTIAL,
    FEATURE_PROXY,
    FEATURE_SUPPORTED,
    FEATURE_UNSUPPORTED,
)


PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "openai": {
        "display_name": "OpenAI",
        "implemented": True,
        "env_keys": ["OPENAI_API_KEY"],
        "models": {
            "gpt-4o-mini-transcribe": {
                "display_name": "gpt-4o-mini-transcribe",
                "timestamps": FEATURE_PARTIAL,
                "confidence": FEATURE_PROXY,
                "diarization": FEATURE_UNSUPPORTED,
                "notes": [
                    "Good default for fast transcription.",
                    "Confidence is a proxy when available, not calibrated word-level confidence.",
                ],
            },
            "gpt-4o-transcribe": {
                "display_name": "gpt-4o-transcribe",
                "timestamps": FEATURE_PARTIAL,
                "confidence": FEATURE_PROXY,
                "diarization": FEATURE_UNSUPPORTED,
                "notes": [
                    "Higher-quality OpenAI transcription model.",
                    "Confidence is a proxy when available, not calibrated word-level confidence.",
                ],
            },
            "whisper-1": {
                "display_name": "whisper-1 (verbose_json supports segments)",
                "timestamps": FEATURE_SUPPORTED,
                "confidence": FEATURE_PROXY,
                "diarization": FEATURE_UNSUPPORTED,
                "notes": [
                    "Older OpenAI Whisper model, supports verbose_json with segment timestamps.",
                    "Confidence (avg_logprob) is a diagnostic proxy, not calibrated.",
                ],
            },
        },
    },
    "aws": {
        "display_name": "AWS Transcribe",
        "implemented": False,
        "env_keys": [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_DEFAULT_REGION",
            "AWS_TRANSCRIBE_BUCKET",
        ],
        "models": {
            "standard": {
                "display_name": "AWS Transcribe (standard)",
                "timestamps": FEATURE_SUPPORTED,
                "confidence": FEATURE_SUPPORTED,
                "diarization": FEATURE_SUPPORTED,
                "notes": [
                    "Coming soon. Will be the first backend with true word-level confidence and diarization.",
                ],
            },
        },
    },
    "faster_whisper": {
        "display_name": "Local faster-whisper",
        "implemented": False,
        "env_keys": [],
        "models": {
            "small": {
                "display_name": "faster-whisper small",
                "timestamps": FEATURE_PARTIAL,
                "confidence": FEATURE_DIAGNOSTIC,
                "diarization": FEATURE_UNSUPPORTED,
                "notes": [
                    "Coming soon. Local open-source transcription.",
                    "Confidence is diagnostic, not calibrated.",
                ],
            },
            "medium": {
                "display_name": "faster-whisper medium",
                "timestamps": FEATURE_PARTIAL,
                "confidence": FEATURE_DIAGNOSTIC,
                "diarization": FEATURE_UNSUPPORTED,
                "notes": [
                    "Coming soon. Higher-quality local model, slower than small.",
                ],
            },
        },
    },
}


def list_providers() -> list[str]:
    """Return registry provider keys (implemented first, then unimplemented)."""
    items = sorted(
        PROVIDER_REGISTRY.items(),
        key=lambda kv: (not kv[1].get("implemented", False), kv[0]),
    )
    return [k for k, _ in items]


def get_provider_meta(provider: str) -> dict[str, Any]:
    if provider not in PROVIDER_REGISTRY:
        raise KeyError(f"Unknown provider: {provider}")
    return PROVIDER_REGISTRY[provider]


def list_models(provider: str) -> list[str]:
    return list(get_provider_meta(provider)["models"].keys())


def get_model_meta(provider: str, model: str) -> dict[str, Any]:
    models = get_provider_meta(provider)["models"]
    if model not in models:
        raise KeyError(f"Unknown model {model!r} for provider {provider!r}")
    return models[model]


def is_implemented(provider: str) -> bool:
    return bool(get_provider_meta(provider).get("implemented", False))
