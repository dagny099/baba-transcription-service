"""AWS Transcribe provider stub.

This provider is registered in `PROVIDER_REGISTRY` so the UI can show its
future capabilities, but the adapter is not yet implemented. Selecting it
raises a clear `ProviderNotImplementedError`.
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


class AWSTranscribeProvider(ProviderAdapter):
    provider_name = "aws"

    def __init__(self, config: AppConfig):
        self.config = config

    def validate_config(self) -> list[str]:
        return [
            "AWS Transcribe is not yet implemented. It is reserved for the next "
            "milestone, where it will become the first backend with true "
            "word-level confidence and diarization."
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
            "AWS Transcribe provider is not yet implemented."
        )
