"""Canonical transcript data model.

Every provider adapter must produce a `TranscriptionResult` that conforms to
this schema, regardless of the underlying provider response shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from transcript_workbench.constants import CONFIDENCE_NONE
from transcript_workbench.models.features import EffectiveFeatures, RequestedFeatures


class TranscriptSegment(BaseModel):
    segment_id: str
    job_id: str
    segment_index: int
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None
    speaker: Optional[str] = None
    text: str
    confidence: Optional[float] = None
    confidence_type: str = CONFIDENCE_NONE
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class TranscriptWord(BaseModel):
    word_id: str
    job_id: str
    segment_id: Optional[str] = None
    word_index: int
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None
    speaker: Optional[str] = None
    word: str
    confidence: Optional[float] = None
    confidence_type: str = CONFIDENCE_NONE
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class TranscriptionJob(BaseModel):
    job_id: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    original_filename: str
    file_hash: Optional[str] = None
    duration_seconds: Optional[float] = None
    provider: str
    model: str
    requested_features: RequestedFeatures
    effective_features: EffectiveFeatures
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class TranscriptionResult(BaseModel):
    """The canonical transcript shape exposed to the rest of the app."""

    job: TranscriptionJob
    text: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    words: list[TranscriptWord] = Field(default_factory=list)
    raw_response_path: Optional[str] = None
    artifacts: dict[str, str] = Field(default_factory=dict)
