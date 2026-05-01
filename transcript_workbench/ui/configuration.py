"""Provider/model/feature selection and capability feedback panel."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import streamlit as st

from transcript_workbench.config import AppConfig
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

    st.subheader("2 · Choose provider, model, and features")

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

    with st.expander("Capability panel", expanded=True):
        st.markdown(
            f"**Selected provider:** {get_provider_meta(provider)['display_name']}  \n"
            f"**Selected model:** {model}"
        )
        cap_col1, cap_col2, cap_col3, cap_col4 = st.columns(4)
        cap_col1.metric("Timestamps", effective.timestamps)
        cap_col2.metric("Confidence", effective.confidence)
        cap_col3.metric("Diarization", effective.diarization)
        cap_col4.metric("Raw output", effective.save_raw)
        if warnings:
            for w in warnings:
                st.info(w)

        _render_preflight_estimate(provider, model, uploaded_file)

    return provider, model, requested


def _render_preflight_estimate(
    provider: str, model: str, uploaded_file: Any | None
) -> None:
    """Show duration + estimated cost before transcription runs."""
    st.markdown("---")
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
    cols = st.columns(3)
    cols[0].metric("Duration", format_hms(duration))
    if estimate is None:
        cols[1].metric("Estimated cost", "—")
        cols[2].metric("Rate", "—")
        return
    cols[1].metric("Estimated cost", format_cost_usd(estimate.usd))
    if estimate.unit == "free":
        cols[2].metric("Rate", "free")
    else:
        cols[2].metric(
            "Rate",
            f"${estimate.rate_usd:.4f} / {estimate.unit.replace('_', ' ')}",
        )
    st.caption(
        "Estimates are derived from duration × published rate. The provider "
        "does not return a billed amount; actual charges may differ slightly."
    )
