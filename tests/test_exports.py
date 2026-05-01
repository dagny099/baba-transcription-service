"""Tests for transcript export formatting."""

from __future__ import annotations

import json
from datetime import datetime, timezone

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
from transcript_workbench.services.exports import (
    build_json,
    build_markdown,
    build_txt,
    export_result,
)


def _make_result(*, segments=None, text="hello world") -> TranscriptionResult:
    job = TranscriptionJob(
        job_id="job-123",
        created_at=datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 30, 12, 1, 0, tzinfo=timezone.utc),
        status=JOB_STATUS_COMPLETED,
        original_filename="sample.mp3",
        duration_seconds=12.5,
        provider="openai",
        model="gpt-4o-mini-transcribe",
        requested_features=RequestedFeatures(),
        effective_features=EffectiveFeatures(),
        warnings=["test warning"],
    )
    return TranscriptionResult(
        job=job, text=text, segments=segments or [], words=[]
    )


def test_txt_export_no_segments_returns_text():
    result = _make_result(text="just plain text")
    out = build_txt(result)
    assert "just plain text" in out
    assert out.endswith("\n")


def test_txt_export_with_timestamps_and_speakers():
    segments = [
        TranscriptSegment(
            segment_id="s1",
            job_id="job-123",
            segment_index=0,
            start_seconds=0.0,
            end_seconds=4.0,
            speaker="Speaker 1",
            text="Hello world.",
            confidence=0.9,
            confidence_type=CONFIDENCE_TOKEN_LOGPROB,
        ),
        TranscriptSegment(
            segment_id="s2",
            job_id="job-123",
            segment_index=1,
            start_seconds=4.0,
            end_seconds=8.0,
            speaker="Speaker 2",
            text="Goodbye world.",
            confidence=0.5,
            confidence_type=CONFIDENCE_TOKEN_LOGPROB,
        ),
    ]
    out = build_txt(_make_result(segments=segments))
    assert "Speaker 1" in out
    assert "00:00:00" in out
    assert "Hello world." in out
    assert "Goodbye world." in out


def test_markdown_export_includes_metadata_and_segments():
    segments = [
        TranscriptSegment(
            segment_id="s1",
            job_id="job-123",
            segment_index=0,
            start_seconds=0.0,
            end_seconds=4.0,
            text="Hello world.",
            confidence_type=CONFIDENCE_NONE,
        )
    ]
    md = build_markdown(_make_result(segments=segments))
    assert "# Transcript" in md
    assert "**Provider:** openai" in md
    assert "**Model:** gpt-4o-mini-transcribe" in md
    assert "Hello world." in md
    assert "test warning" in md


def test_json_export_is_valid_canonical_json():
    segments = [
        TranscriptSegment(
            segment_id="s1",
            job_id="job-123",
            segment_index=0,
            text="Hello world.",
        )
    ]
    payload = build_json(_make_result(segments=segments))
    data = json.loads(payload)
    assert data["text"] == "hello world"
    assert data["job"]["job_id"] == "job-123"
    assert len(data["segments"]) == 1
    assert data["segments"][0]["text"] == "Hello world."


def test_export_result_writes_three_files(tmp_path):
    artifacts = export_result(_make_result(), tmp_path)
    assert artifacts.txt_path is not None and artifacts.txt_path.exists()
    assert artifacts.md_path is not None and artifacts.md_path.exists()
    assert artifacts.json_path is not None and artifacts.json_path.exists()
    d = artifacts.as_dict()
    assert set(d.keys()) == {"txt", "md", "json"}


def test_export_result_respects_disable_flags(tmp_path):
    artifacts = export_result(_make_result(), tmp_path, txt=False, md=True, json_export=False)
    assert artifacts.txt_path is None
    assert artifacts.json_path is None
    assert artifacts.md_path is not None and artifacts.md_path.exists()
