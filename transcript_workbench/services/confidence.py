"""Confidence summary helpers."""

from __future__ import annotations

from typing import Any

from transcript_workbench.constants import CONFIDENCE_NONE
from transcript_workbench.models.canonical import TranscriptSegment, TranscriptWord


def summarize_confidence(
    words: list[TranscriptWord],
    segments: list[TranscriptSegment],
    threshold: float = 0.80,
) -> dict[str, Any]:
    """Summarize confidence at whichever level is available.

    Prefer word-level over segment-level. Returns a dict with keys:
    confidence_type, average_confidence, low_confidence_count,
    low_confidence_percent, threshold.
    """
    word_vals = [w for w in words if w.confidence is not None]
    if word_vals:
        values = [float(w.confidence) for w in word_vals]  # type: ignore[arg-type]
        low = [v for v in values if v < threshold]
        return {
            "confidence_type": word_vals[0].confidence_type,
            "average_confidence": sum(values) / len(values),
            "low_confidence_count": len(low),
            "low_confidence_percent": len(low) / len(values),
            "threshold": threshold,
        }

    seg_vals = [s for s in segments if s.confidence is not None]
    if seg_vals:
        values = [float(s.confidence) for s in seg_vals]  # type: ignore[arg-type]
        low = [v for v in values if v < threshold]
        return {
            "confidence_type": seg_vals[0].confidence_type,
            "average_confidence": sum(values) / len(values),
            "low_confidence_count": len(low),
            "low_confidence_percent": len(low) / len(values),
            "threshold": threshold,
        }

    return {
        "confidence_type": CONFIDENCE_NONE,
        "average_confidence": None,
        "low_confidence_count": None,
        "low_confidence_percent": None,
        "threshold": threshold,
    }
