"""Tests for feature negotiation logic."""

from __future__ import annotations

import pytest

from transcript_workbench.constants import (
    FEATURE_DIAGNOSTIC,
    FEATURE_NOT_REQUESTED,
    FEATURE_PARTIAL,
    FEATURE_PROXY,
    FEATURE_SUPPORTED,
    FEATURE_UNSUPPORTED,
)
from transcript_workbench.models.features import RequestedFeatures
from transcript_workbench.services.feature_negotiation import resolve_effective_features


def test_openai_mini_with_confidence_marked_proxy_with_warning():
    requested = RequestedFeatures(
        timestamps=True, confidence=True, diarization=False, save_raw=True
    )
    effective, warnings = resolve_effective_features(
        "openai", "gpt-4o-mini-transcribe", requested
    )
    assert effective.confidence == FEATURE_PROXY
    assert effective.timestamps == FEATURE_PARTIAL
    assert effective.diarization == FEATURE_NOT_REQUESTED
    assert effective.save_raw == FEATURE_SUPPORTED
    assert any("proxy" in w.lower() for w in warnings)


def test_openai_mini_with_diarization_warns_unsupported():
    requested = RequestedFeatures(diarization=True)
    effective, warnings = resolve_effective_features(
        "openai", "gpt-4o-mini-transcribe", requested
    )
    assert effective.diarization == FEATURE_UNSUPPORTED
    assert any("diarization" in w.lower() for w in warnings)


def test_aws_with_confidence_and_diarization_supported():
    requested = RequestedFeatures(
        timestamps=True, confidence=True, diarization=True, save_raw=True
    )
    effective, warnings = resolve_effective_features("aws", "standard", requested)
    assert effective.timestamps == FEATURE_SUPPORTED
    assert effective.confidence == FEATURE_SUPPORTED
    assert effective.diarization == FEATURE_SUPPORTED
    # No proxy/unsupported warnings expected for AWS standard.
    assert not any("proxy" in w.lower() for w in warnings)
    assert not any("not supported" in w.lower() for w in warnings)


def test_faster_whisper_diarization_warns():
    requested = RequestedFeatures(confidence=True, diarization=True)
    effective, warnings = resolve_effective_features(
        "faster_whisper", "small", requested
    )
    assert effective.confidence == FEATURE_DIAGNOSTIC
    assert effective.diarization == FEATURE_UNSUPPORTED
    assert any("diarization" in w.lower() for w in warnings)


def test_unchecked_features_return_not_requested():
    requested = RequestedFeatures(
        timestamps=False,
        confidence=False,
        diarization=False,
        save_raw=False,
    )
    effective, _ = resolve_effective_features(
        "openai", "gpt-4o-mini-transcribe", requested
    )
    assert effective.timestamps == FEATURE_NOT_REQUESTED
    assert effective.confidence == FEATURE_NOT_REQUESTED
    assert effective.diarization == FEATURE_NOT_REQUESTED
    assert effective.save_raw == FEATURE_NOT_REQUESTED


def test_unknown_provider_raises():
    requested = RequestedFeatures()
    with pytest.raises(KeyError):
        resolve_effective_features("doesnotexist", "anything", requested)
