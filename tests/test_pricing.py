"""Tests for the pricing module."""

from __future__ import annotations

import math

import pytest

from transcript_workbench.providers.pricing import (
    PRICING,
    estimate_cost,
    format_cost_usd,
    get_pricing_rule,
)


def test_pricing_table_has_openai_entries():
    assert "openai" in PRICING
    for model in ("gpt-4o-mini-transcribe", "gpt-4o-transcribe", "whisper-1"):
        assert model in PRICING["openai"]


def test_per_minute_estimate_basic_math():
    # 60 seconds at $0.003/min = $0.003
    estimate = estimate_cost("openai", "gpt-4o-mini-transcribe", 60.0)
    assert estimate is not None
    assert math.isclose(estimate.usd, 0.003, rel_tol=1e-9)
    assert estimate.unit == "per_minute"
    assert estimate.rate_usd == 0.003


def test_per_minute_estimate_for_real_world_duration():
    # 38-minute file at $0.003/min = $0.114
    estimate = estimate_cost("openai", "gpt-4o-mini-transcribe", 38 * 60)
    assert estimate is not None
    assert math.isclose(estimate.usd, 0.114, rel_tol=1e-9)


def test_per_second_estimate_aws():
    estimate = estimate_cost("aws", "standard", 600.0)
    assert estimate is not None
    assert estimate.unit == "per_second"
    # Rate is approx $0.024 / 60 per second; 600s -> ~$0.24
    assert math.isclose(estimate.usd, 600 * (0.024 / 60.0), rel_tol=1e-9)


def test_free_local_model_returns_zero_with_free_unit():
    estimate = estimate_cost("faster_whisper", "small", 1234.0)
    assert estimate is not None
    assert estimate.unit == "free"
    assert estimate.usd == 0.0
    assert estimate.rate_usd == 0.0


def test_unknown_provider_returns_none():
    assert estimate_cost("doesnotexist", "any", 60.0) is None


def test_unknown_model_returns_none():
    assert estimate_cost("openai", "not-a-real-model", 60.0) is None


def test_missing_duration_returns_none():
    assert estimate_cost("openai", "gpt-4o-mini-transcribe", None) is None


def test_negative_duration_returns_none():
    assert estimate_cost("openai", "gpt-4o-mini-transcribe", -1.0) is None


def test_get_pricing_rule_returns_rule_or_none():
    assert get_pricing_rule("openai", "gpt-4o-mini-transcribe") is not None
    assert get_pricing_rule("openai", "nope") is None
    assert get_pricing_rule("nope", "nope") is None


@pytest.mark.parametrize(
    "usd,expected",
    [
        (None, "—"),
        (0.0, "free"),
        (-0.1, "free"),
        (0.001, "<$0.01"),
        (0.0099, "<$0.01"),
        (0.018, "$0.018"),
        (0.114, "$0.114"),
        (1.5, "$1.50"),
        (12.345, "$12.35"),  # rounded to 2dp
    ],
)
def test_format_cost_usd(usd, expected):
    assert format_cost_usd(usd) == expected
