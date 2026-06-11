"""Results tabs: Transcript / Segments / Confidence / Metadata / Raw / Downloads / History."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from transcript_workbench.config import AppConfig
from transcript_workbench.constants import CONFIDENCE_NONE
from transcript_workbench.providers.pricing import format_cost_usd
from transcript_workbench.services.confidence import summarize_confidence
from transcript_workbench.services.transcription import TranscriptionRunReport
from transcript_workbench.ui.history import render_history_tab
from transcript_workbench.utils.time import format_hms


def render_results(report: TranscriptionRunReport, config: AppConfig) -> None:
    if report.error:
        st.error(f"Transcription failed: {report.error}")
        if report.warnings:
            with st.expander("Warnings"):
                for w in report.warnings:
                    st.write(f"- {w}")
        return

    result = report.result
    if result is None:
        st.warning("No result to display.")
        return

    st.success(f"Transcription completed in {report.elapsed_seconds:.1f}s.")

    tabs = st.tabs(
        [
            "Transcript",
            "Segments",
            "Confidence",
            "Metadata",
            "Raw / Debug",
            "Downloads",
            "History",
        ]
    )

    with tabs[0]:
        _render_transcript_tab(result)
    with tabs[1]:
        _render_segments_tab(result)
    with tabs[2]:
        _render_confidence_tab(result, config)
    with tabs[3]:
        _render_metadata_tab(result, report)
    with tabs[4]:
        _render_raw_tab(result)
    with tabs[5]:
        _render_downloads_tab(result)
    with tabs[6]:
        render_history_tab(config)


def _render_transcript_tab(result: Any) -> None:
    st.subheader("Transcript")
    if not result.segments:
        st.text_area("Transcript text", value=result.text or "", height=400)
        return
    has_times = any(s.start_seconds is not None for s in result.segments)
    has_speakers = any(s.speaker for s in result.segments)
    if not has_times and not has_speakers:
        st.text_area("Transcript text", value=result.text or "", height=400)
        return
    for seg in result.segments:
        prefix = []
        if seg.speaker:
            prefix.append(f"**{seg.speaker}**")
        if has_times:
            prefix.append(
                f"`{format_hms(seg.start_seconds)} - {format_hms(seg.end_seconds)}`"
            )
        if prefix:
            st.markdown(" · ".join(prefix))
        st.write(seg.text)


def _render_segments_tab(result: Any) -> None:
    st.subheader("Segments")
    if not result.segments:
        st.info("This transcription returned a single text body without segments.")
        return
    df = pd.DataFrame(
        [
            {
                "#": s.segment_index,
                "start": format_hms(s.start_seconds) if s.start_seconds is not None else "—",
                "end": format_hms(s.end_seconds) if s.end_seconds is not None else "—",
                "speaker": s.speaker or "—",
                "confidence": s.confidence,
                "type": s.confidence_type,
                "text": s.text,
            }
            for s in result.segments
        ]
    )
    st.dataframe(df, width="stretch", hide_index=True)


def _render_confidence_tab(result: Any, config: AppConfig) -> None:
    st.subheader("Confidence")
    summary = summarize_confidence(
        result.words, result.segments, threshold=config.low_confidence_threshold
    )
    if summary["confidence_type"] == CONFIDENCE_NONE:
        st.info(
            "No confidence information was returned for this provider/model. "
            "Use AWS Transcribe (coming soon) for true word-level confidence."
        )
        return
    col1, col2, col3 = st.columns(3)
    col1.metric("Type", summary["confidence_type"])
    avg = summary["average_confidence"]
    col2.metric("Average", f"{avg:.2f}" if avg is not None else "—")
    pct = summary["low_confidence_percent"]
    col3.metric(
        f"% below {summary['threshold']:.2f}",
        f"{pct * 100:.1f}%" if pct is not None else "—",
    )
    st.caption(
        "Note: confidence semantics vary by provider. A logprob proxy from "
        "OpenAI is not the same signal as calibrated confidence from AWS."
    )


def _render_metadata_tab(result: Any, report: TranscriptionRunReport) -> None:
    st.subheader("Metadata")
    job = result.job

    # Cost summary up top, where users will look for it.
    cost = report.cost_estimate
    cost_cols = st.columns(3)
    cost_cols[0].metric(
        "Duration",
        format_hms(job.duration_seconds) if job.duration_seconds is not None else "—",
    )
    cost_cols[1].metric(
        "Estimated cost",
        format_cost_usd(cost.usd) if cost else "—",
    )
    if cost is None:
        cost_cols[2].metric("Rate", "—")
    elif cost.unit == "free":
        cost_cols[2].metric("Rate", "free")
    else:
        cost_cols[2].metric(
            "Rate", f"${cost.rate_usd:.4f} / {cost.unit.replace('_', ' ')}"
        )
    st.caption(
        "Cost is an estimate from duration × published rate. The provider "
        "does not return a billed amount."
    )

    st.write(
        {
            "job_id": job.job_id,
            "status": job.status,
            "provider": job.provider,
            "model": job.model,
            "original_filename": job.original_filename,
            "file_hash": job.file_hash,
            "duration_seconds": job.duration_seconds,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "elapsed_seconds": report.elapsed_seconds,
        }
    )
    st.markdown("**Requested features**")
    st.write(job.requested_features.model_dump())
    st.markdown("**Effective features**")
    st.write(job.effective_features.model_dump())
    if job.warnings:
        st.markdown("**Warnings**")
        for w in job.warnings:
            st.warning(w)
    if report.audio_metadata:
        st.markdown("**Audio metadata (ffprobe)**")
        st.write(report.audio_metadata)


def _render_raw_tab(result: Any) -> None:
    st.subheader("Raw / Debug")
    raw_path = result.raw_response_path
    if not raw_path or not Path(raw_path).exists():
        st.info("No raw provider response was saved for this run.")
        return
    try:
        raw_text = Path(raw_path).read_text(encoding="utf-8")
        st.code(raw_text, language="json")
    except Exception as e:  # pragma: no cover - defensive
        st.error(f"Could not read raw response file: {e}")


def _render_downloads_tab(result: Any) -> None:
    st.subheader("Downloads")
    artifacts = result.artifacts or {}

    label_map = {
        "txt": ("Plain text (.txt)", "transcript.txt", "text/plain"),
        "md": ("Markdown (.md)", "transcript.md", "text/markdown"),
        "json": ("JSON (.json)", "transcript.json", "application/json"),
        "raw": ("Raw provider response (.json)", "raw_response.json", "application/json"),
    }
    for atype, path in artifacts.items():
        label, filename, mime = label_map.get(
            atype, (atype, Path(path).name, "application/octet-stream")
        )
        try:
            data = Path(path).read_bytes()
        except FileNotFoundError:
            st.warning(f"Artifact missing on disk: {path}")
            continue
        st.download_button(
            label=f"Download {label}",
            data=data,
            file_name=filename,
            mime=mime,
            key=f"download-{atype}-{result.job.job_id}",
        )

    # Compressed-audio download, if this run used in-app compression.
    # Bytes live in session_state and disappear when the tab is closed —
    # disk is precious on small instances so we don't persist them.
    compressed = st.session_state.get("latest_compressed")
    if compressed:
        size_mb = compressed["size"] / (1024 * 1024)
        st.download_button(
            label=f"Download compressed audio (.mp3, {size_mb:.1f} MB)",
            data=compressed["data"],
            file_name=compressed["name"],
            mime=compressed["mime"],
            key=f"download-compressed-{result.job.job_id}",
            help="Only available for this session. Save it now if you want to keep it.",
        )

    if not artifacts and not compressed:
        st.info("No exports were generated.")
