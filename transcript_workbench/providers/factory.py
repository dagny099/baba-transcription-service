"""Provider adapter factory."""

from __future__ import annotations

from transcript_workbench.config import AppConfig
from transcript_workbench.providers.aws_provider import AWSTranscribeProvider
from transcript_workbench.providers.base import ProviderAdapter
from transcript_workbench.providers.faster_whisper_provider import FasterWhisperProvider
from transcript_workbench.providers.openai_provider import OpenAIProvider


def get_provider(provider_name: str, config: AppConfig) -> ProviderAdapter:
    """Return an adapter instance for `provider_name`.

    Adding a new provider here is the second step (registry first, factory
    second). The Streamlit UI does not branch on provider names.
    """
    if provider_name == "openai":
        return OpenAIProvider(config)
    if provider_name == "aws":
        return AWSTranscribeProvider(config)
    if provider_name == "faster_whisper":
        return FasterWhisperProvider(config)
    raise ValueError(f"Unsupported provider: {provider_name}")
