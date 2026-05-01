"""Pydantic models for requested and effective features."""

from __future__ import annotations

from pydantic import BaseModel

from transcript_workbench.constants import (
    FEATURE_NOT_REQUESTED,
    FEATURE_SUPPORTED,
)


class RequestedFeatures(BaseModel):
    """What the user asked for."""

    timestamps: bool = True
    confidence: bool = False
    diarization: bool = False
    save_raw: bool = True
    export_txt: bool = True
    export_md: bool = True
    export_json: bool = True
    export_srt: bool = False
    export_vtt: bool = False


class EffectiveFeatures(BaseModel):
    """What the selected provider/model can actually deliver.

    Each value is one of:
    - supported, partial, proxy, diagnostic, unsupported, not_requested.
    """

    timestamps: str = FEATURE_NOT_REQUESTED
    confidence: str = FEATURE_NOT_REQUESTED
    diarization: str = FEATURE_NOT_REQUESTED
    save_raw: str = FEATURE_SUPPORTED
