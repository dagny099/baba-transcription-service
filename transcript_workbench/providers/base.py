"""Provider adapter interface.

Every transcription backend must implement this interface so the rest of the
app stays provider-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from transcript_workbench.models.canonical import TranscriptionResult
from transcript_workbench.models.features import EffectiveFeatures, RequestedFeatures


class ProviderAdapter(ABC):
    """Abstract base class for transcription providers."""

    provider_name: str = ""

    @abstractmethod
    def validate_config(self) -> list[str]:
        """Return a list of human-readable config errors. Empty means OK."""
        raise NotImplementedError

    @abstractmethod
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
        """Run transcription and return a canonical result.

        Implementations MUST:
        - write the raw provider response to `raw_output_path` when available;
        - populate `TranscriptionResult.text`;
        - populate segments and words when supported by the provider/model;
        - swallow nothing silently — raise informative exceptions on failure.
        """
        raise NotImplementedError


class ProviderNotImplementedError(NotImplementedError):
    """Raised when a registered provider has no working adapter yet."""
