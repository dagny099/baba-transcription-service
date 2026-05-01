"""Tests for the OpenAI provider response parser.

These tests do NOT call the OpenAI API. They feed fixture JSON through the
internal parsing helpers.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from transcript_workbench.constants import (
    CONFIDENCE_NONE,
    CONFIDENCE_TOKEN_LOGPROB,
)
from transcript_workbench.providers.openai_provider import (
    _coerce_response_to_dict,
    _parse_duration,
    _parse_segments,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_verbose_json_segments():
    raw = _load("sample_openai_verbose_response.json")
    segments = _parse_segments(raw, job_id="job-1", model="whisper-1")
    assert len(segments) == 2
    s0 = segments[0]
    assert s0.text == "Hello world."
    assert s0.start_seconds == 0.0
    assert s0.end_seconds == 4.0
    assert s0.confidence is not None
    assert s0.confidence_type == CONFIDENCE_TOKEN_LOGPROB
    # exp(-0.2) ~= 0.8187
    assert math.isclose(s0.confidence, math.exp(-0.2), rel_tol=1e-6)
    # Ensure segment 1's confidence < segment 0's confidence (lower logprob).
    assert segments[1].confidence < s0.confidence
    # Provider metadata is preserved for debugging.
    assert segments[0].provider_metadata["avg_logprob"] == -0.2


def test_parse_simple_json_returns_single_segment():
    raw = _load("sample_openai_simple_response.json")
    segments = _parse_segments(raw, job_id="job-1", model="gpt-4o-mini-transcribe")
    assert len(segments) == 1
    assert segments[0].text.startswith("Hello world")
    assert segments[0].confidence is None
    assert segments[0].confidence_type == CONFIDENCE_NONE


def test_parse_empty_returns_no_segments():
    segments = _parse_segments({"text": "   "}, job_id="job-1", model="x")
    assert segments == []


def test_parse_duration():
    assert _parse_duration({"duration": 12.5}) == 12.5
    assert _parse_duration({}) is None
    assert _parse_duration({"duration": "not-a-number"}) is None


def test_coerce_response_to_dict_handles_str():
    assert _coerce_response_to_dict("hello") == {"text": "hello"}


def test_coerce_response_to_dict_passes_dict_through():
    assert _coerce_response_to_dict({"text": "x"}) == {"text": "x"}


class _FakeResponse:
    def model_dump(self) -> dict:
        return {"text": "from-model-dump", "duration": 2.0}


def test_coerce_response_to_dict_uses_model_dump():
    out = _coerce_response_to_dict(_FakeResponse())
    assert out == {"text": "from-model-dump", "duration": 2.0}
