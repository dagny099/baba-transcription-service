"""Feature negotiation: what the user asked for vs. what the provider supports."""

from __future__ import annotations

from transcript_workbench.constants import (
    FEATURE_DIAGNOSTIC,
    FEATURE_NOT_REQUESTED,
    FEATURE_PROXY,
    FEATURE_SUPPORTED,
    FEATURE_UNSUPPORTED,
)
from transcript_workbench.models.features import EffectiveFeatures, RequestedFeatures
from transcript_workbench.providers.registry import get_model_meta


def resolve_effective_features(
    provider: str,
    model: str,
    requested: RequestedFeatures,
) -> tuple[EffectiveFeatures, list[str]]:
    """Compare requested features against provider/model capabilities.

    Returns:
        (effective, warnings) where:
        - effective is the resolved EffectiveFeatures object;
        - warnings is a list of human-readable strings to surface in the UI.
    """
    model_meta = get_model_meta(provider, model)
    warnings: list[str] = list(model_meta.get("notes", []))

    def _resolve(feature: str, asked: bool) -> str:
        if not asked:
            return FEATURE_NOT_REQUESTED
        return model_meta.get(feature, FEATURE_UNSUPPORTED)

    effective = EffectiveFeatures(
        timestamps=_resolve("timestamps", requested.timestamps),
        confidence=_resolve("confidence", requested.confidence),
        diarization=_resolve("diarization", requested.diarization),
        save_raw=FEATURE_SUPPORTED if requested.save_raw else FEATURE_NOT_REQUESTED,
    )

    if requested.confidence and effective.confidence in {FEATURE_PROXY, FEATURE_DIAGNOSTIC}:
        warnings.append(
            "Confidence requested, but the selected model only provides a "
            f"{effective.confidence} confidence signal — not calibrated word-level confidence."
        )
    if requested.confidence and effective.confidence == FEATURE_UNSUPPORTED:
        warnings.append(
            "Confidence requested but unsupported by this provider/model. "
            "It will be omitted from the result."
        )
    if requested.diarization and effective.diarization == FEATURE_UNSUPPORTED:
        warnings.append(
            "Speaker diarization was requested but is not supported by this "
            "provider/model. The transcript will not include speaker labels."
        )
    if requested.timestamps and effective.timestamps == FEATURE_UNSUPPORTED:
        warnings.append(
            "Timestamps were requested but are not supported in this configuration."
        )

    return effective, warnings
