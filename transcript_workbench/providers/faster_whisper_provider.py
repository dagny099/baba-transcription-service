"""Local faster-whisper provider stub.

Registered in `PROVIDER_REGISTRY`, but adapter is not yet implemented.
"""

from __future__ import annotations

from pathlib import Path

from transcript_workbench.config import AppConfig
from transcript_workbench.models.canonical import TranscriptionResult
from transcript_workbench.models.features import EffectiveFeatures, RequestedFeatures
from transcript_workbench.providers.base import (
    ProviderAdapter,
    ProviderNotImplementedError,
)


class FasterWhisperProvider(ProviderAdapter):
    provider_name = "faster_whisper"

    def __init__(self, config: AppConfig):
        self.config = config

    def validate_config(self) -> list[str]:
        return [
            "Local faster-whisper is not yet implemented. It is reserved for "
            "the local/open-source milestone after AWS Transcribe."
        ]

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
        raise ProviderNotImplementedError(
            "Local faster-whisper provider is not yet implemented."
        )
