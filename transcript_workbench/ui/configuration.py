"""Provider/model/feature selection and capability feedback panel."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import streamlit as st

from transcript_workbench.config import AppConfig
from transcript_workbench.constants import (
    FEATURE_DIAGNOSTIC,
    FEATURE_NOT_REQUESTED,
    FEATURE_PARTIAL,
    FEATURE_PROXY,
    FEATURE_SUPPORTED,
    FEATURE_UNSUPPORTED,
)
from transcript_workbench.models.features import RequestedFeatures
from transcript_workbench.providers.pricing import (
    estimate_cost,
    format_cost_usd,
    get_pricing_rule,
)
from transcript_workbench.providers.registry import (
    PROVIDER_REGISTRY,
    get_model_meta,
    get_provider_meta,
    is_implemented,
    list_models,
    list_providers,
)
from transcript_workbench.services.audio import ffprobe_metadata, has_ffprobe
from transcript_workbench.services.feature_negotiation import resolve_effective_features
from transcript_workbench.utils.time import format_hms


# Human-readable labels for the internal feature-status enum, so values like
# "not_requested" never reach the UI verbatim.
_FEATURE_STATUS_LABELS = {
    FEATURE_SUPPORTED: "✓ supported",
    FEATURE_PARTIAL: "partial",
    FEATURE_PROXY: "proxy",
    FEATURE_DIAGNOSTIC: "diagnostic",
    FEATURE_UNSUPPORTED: "✗ not available",
    FEATURE_NOT_REQUESTED: "not requested",
}


def _feature_label(status: str) -> str:
    return _FEATURE_STATUS_LABELS.get(status, status.replace("_", " "))


def _probe_uploaded_duration(uploaded_file: Any) -> float | None:
    """Run ffprobe on an uploaded file once per (name, size). Cached in session.

    Returns duration in seconds, or None if ffprobe is unavailable / fails.
    """
    if uploaded_file is None or not has_ffprobe():
        return None
    cache: dict[str, float | None] = st.session_state.setdefault(
        "_duration_cache", {}
    )
    cache_key = f"{uploaded_file.name}::{uploaded_file.size}"
    if cache_key in cache:
        return cache[cache_key]

    suffix = Path(uploaded_file.name).suffix
    duration: float | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            # `getbuffer` works for Streamlit UploadedFile without consuming it.
            tmp.write(bytes(uploaded_file.getbuffer()))
            tmp_path = Path(tmp.name)
        try:
            meta = ffprobe_metadata(tmp_path)
            duration = meta.duration_seconds
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception:
        duration = None

    cache[cache_key] = duration
    return duration


def render_configuration_section(
    config: AppConfig,
    uploaded_file: Any | None = None,
) -> tuple[str, str, RequestedFeatures]:
    """Render configuration UI and return (provider, model, requested features)."""

    st.subheader("2 · Choose provider, model, and features :material/tune:")
    st.caption(
        "Not sure what to pick? The defaults work well for most recordings — "
        "just add a file and run."
    )

    providers = list_providers()
    default_provider = (
        config.default_provider if config.default_provider in providers else providers[0]
    )

    def _provider_label(p: str) -> str:
        meta = PROVIDER_REGISTRY[p]
        suffix = "" if meta.get("implemented") else "  (coming soon)"
        return f"{meta['display_name']}{suffix}"

    col1, col2 = st.columns(2)
    with col1:
        provider = st.selectbox(
            "Provider",
            providers,
            index=providers.index(default_provider),
            format_func=_provider_label,
            key="provider_select",
        )
    models = list_models(provider)
    default_model = (
        config.default_model if config.default_model in models else models[0]
    )
    with col2:
        model = st.selectbox(
            "Model",
            models,
            index=models.index(default_model),
            format_func=lambda m: get_model_meta(provider, m).get("display_name", m),
            key="model_select",
        )

    if not is_implemented(provider):
        st.warning(
            f"**{get_provider_meta(provider)['display_name']}** is registered "
            "but not implemented yet. Pick **OpenAI** to run a real transcription."
        )

    st.markdown("**Optional features**")
    fcol1, fcol2, fcol3 = st.columns(3)
    timestamps = fcol1.checkbox("Include timestamps", value=True)
    confidence = fcol2.checkbox("Include confidence info", value=False)
    diarization = fcol3.checkbox("Identify speakers", value=False)

    fcol4, fcol5, fcol6 = st.columns(3)
    save_raw = fcol4.checkbox("Save raw provider response", value=True)
    export_txt = fcol5.checkbox("Export TXT", value=True)
    export_md = fcol6.checkbox("Export Markdown", value=True)
    fcol7, _, _ = st.columns(3)
    export_json = fcol7.checkbox("Export JSON", value=True)

    requested = RequestedFeatures(
        timestamps=timestamps,
        confidence=confidence,
        diarization=diarization,
        save_raw=save_raw,
        export_txt=export_txt,
        export_md=export_md,
        export_json=export_json,
    )

    # ---- capability panel ---------------------------------------------------
    try:
        effective, warnings = resolve_effective_features(provider, model, requested)
    except KeyError as e:
        st.error(f"Unknown provider/model combination: {e}")
        return provider, model, requested

    summary = " · ".join(
        [
            f"Timestamps: {_feature_label(effective.timestamps)}",
            f"Confidence: {_feature_label(effective.confidence)}",
            f"Speakers: {_feature_label(effective.diarization)}",
        ]
    )
    with st.expander(
        f"Capabilities — {summary}", expanded=False, icon=":material/fact_check:"
    ):
        st.caption(
            f"{get_provider_meta(provider)['display_name']} · {model} · "
            f"raw output: {_feature_label(effective.save_raw)}"
        )
        for w in warnings:
            st.caption(f"💡 {w}")

        _render_preflight_estimate(provider, model, uploaded_file)

    return provider, model, requested


def preflight_caption(provider: str, model: str, source: Any) -> str:
    """One-line run summary (duration · est. cost · model) for the Run button."""
    parts: list[str] = []
    duration = _probe_uploaded_duration(source)
    if duration is not None:
        parts.append(format_hms(duration))
        estimate = estimate_cost(provider, model, duration)
        if estimate is not None:
            parts.append(
                "free" if estimate.unit == "free" else f"est. {format_cost_usd(estimate.usd)}"
            )
    parts.append(model)
    return " · ".join(parts)


def _render_preflight_estimate(
    provider: str, model: str, uploaded_file: Any | None
) -> None:
    """Show duration + estimated cost before transcription runs."""
    st.markdown("**Pre-flight estimate**")

    rule = get_pricing_rule(provider, model)
    if rule is None:
        st.caption(
            f"No pricing rule registered for `{provider}/{model}`. "
            "Cost will not be estimated for this run."
        )
        return

    if uploaded_file is None:
        rate_label = (
            "free" if rule.unit == "free"
            else f"${rule.usd_per_unit:.4f} {rule.unit.replace('_', ' ')}"
        )
        st.caption(
            f"Rate: {rate_label}. Upload a file to see an estimate."
        )
        return

    duration = _probe_uploaded_duration(uploaded_file)
    if duration is None:
        if not has_ffprobe():
            st.caption(
                "Install ffmpeg/ffprobe to see a pre-flight cost estimate. "
                "Cost will still be recorded after the run if the provider "
                "reports a duration."
            )
        else:
            st.caption(
                "Could not read duration from this file. Cost will be "
                "estimated after transcription based on the provider response."
            )
        return

    estimate = estimate_cost(provider, model, duration)
    if estimate is None:
        st.caption(
            f"Duration {format_hms(duration)} · no cost estimate available "
            "for this provider/model."
        )
        return
    st.metric("Estimated cost", format_cost_usd(estimate.usd))
    rate = (
        "free"
        if estimate.unit == "free"
        else f"${estimate.rate_usd:.4f} {estimate.unit.replace('_', ' ')}"
    )
    st.caption(
        f"Duration {format_hms(duration)} · rate {rate} · estimated from "
        "duration × published rate; the provider does not return a billed "
        "amount, so actual charges may differ slightly."
    )
