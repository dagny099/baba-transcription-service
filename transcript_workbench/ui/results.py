"""Results tabs: Transcript / Segments / Confidence / Metadata / Raw / Downloads / History."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from transcript_workbench.config import AppConfig
from transcript_workbench.constants import CONFIDENCE_NONE
from transcript_workbench.db.connection import initialize_database
from transcript_workbench.db.repository import Repository
from transcript_workbench.providers.pricing import format_cost_usd
from transcript_workbench.services.confidence import summarize_confidence
from transcript_workbench.services.email import (
    EmailAttachment,
    EmailNotAllowedError,
    build_transcript_email,
    send_email,
)
from transcript_workbench.services.transcription import TranscriptionRunReport
from transcript_workbench.ui.history import render_history_tab
from transcript_workbench.utils.time import format_hms, utcnow

# Display labels for artifact types, shared by the download buttons and the
# email attachment checkboxes: artifact type -> (label, filename, mime).
_ARTIFACT_LABELS = {
    "txt": ("Plain text (.txt)", "transcript.txt", "text/plain"),
    "md": ("Markdown (.md)", "transcript.md", "text/markdown"),
    "json": ("JSON (.json)", "transcript.json", "application/json"),
    "raw": ("Raw provider response (.json)", "raw_response.json", "application/json"),
}


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

    st.success(
        f"Transcription completed in {report.elapsed_seconds:.1f}s.",
        icon=":material/check_circle:",
    )

    tabs = st.tabs(
        [
            ":material/article: Transcript",
            ":material/format_list_numbered: Segments",
            ":material/insights: Confidence",
            ":material/info: Metadata",
            ":material/data_object: Raw / Debug",
            ":material/download: Downloads & Share",
            ":material/history: History",
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
        _render_downloads_tab(result, config)
    with tabs[6]:
        render_history_tab(config)


def _render_transcript_tab(result: Any) -> None:
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
    raw_path = result.raw_response_path
    if not raw_path or not Path(raw_path).exists():
        st.info("No raw provider response was saved for this run.")
        return
    try:
        raw_text = Path(raw_path).read_text(encoding="utf-8")
        st.code(raw_text, language="json")
    except Exception as e:  # pragma: no cover - defensive
        st.error(f"Could not read raw response file: {e}")


def _render_downloads_tab(result: Any, config: AppConfig) -> None:
    artifacts = result.artifacts or {}

    for atype, path in artifacts.items():
        label, filename, mime = _ARTIFACT_LABELS.get(
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
            icon=":material/download:",
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
            icon=":material/download:",
            key=f"download-compressed-{result.job.job_id}",
            help="Only available for this session. Save it now if you want to keep it.",
        )

    if not artifacts and not compressed:
        st.info("No exports were generated.")

    _render_share_section(result, config)


# ---- share via email ---------------------------------------------------------


def _render_share_section(result: Any, config: AppConfig) -> None:
    """Email the transcript (and optionally the audio) to an allowlisted address.

    All sending rules (allowlist, size cap) are enforced in
    `services.email`; this section only collects choices and shows results.
    """
    st.markdown("---")
    st.subheader(":material/mail: Share via email")

    if not config.email_enabled:
        st.caption(
            "Email sharing isn't configured. Set `EMAIL_SENDER` and "
            "`EMAIL_RECIPIENTS` in `.env` (plus `SMTP_USERNAME` / "
            "`SMTP_PASSWORD` when `EMAIL_PROVIDER=smtp`) — see "
            "`docs/EMAIL_SETUP.md`."
        )
        return

    artifacts = result.artifacts or {}
    audio = _audio_candidate(result, config)
    audio_limit_bytes = config.email_max_attachment_mb * 1024 * 1024

    with st.form(key=f"email-form-{result.job.job_id}"):
        recipients = st.multiselect(
            "Send to",
            options=config.email_recipients,
            default=config.email_recipients[:1],
            help="Recipients come from the EMAIL_RECIPIENTS allowlist in .env.",
        )

        st.markdown("**Attach**")
        # Transcript artifacts: markdown on by default, the rest opt-in.
        selected_types: list[str] = []
        for atype, default in (("md", True), ("txt", False), ("json", False)):
            path = artifacts.get(atype)
            if not path or not Path(path).exists():
                continue
            label, _, _ = _ARTIFACT_LABELS[atype]
            size_kb = Path(path).stat().st_size / 1024
            if st.checkbox(
                f"{label} — {size_kb:.0f} KB",
                value=default,
                key=f"email-attach-{atype}-{result.job.job_id}",
            ):
                selected_types.append(atype)

        include_audio = False
        if audio is not None:
            size_mb = audio["size"] / (1024 * 1024)
            too_big = audio["size"] > audio_limit_bytes
            include_audio = st.checkbox(
                f"Audio ({audio['filename']}, {size_mb:.1f} MB)",
                value=False,
                disabled=too_big,
                key=f"email-attach-audio-{result.job.job_id}",
                help=(
                    f"Too large to email — the limit is "
                    f"{config.email_max_attachment_mb} MB. Use the download "
                    "button above instead."
                    if too_big
                    else "Attaches the compressed audio when available, "
                    "otherwise the original upload."
                ),
            )

        note = st.text_input(
            "Optional note",
            placeholder="A short message shown at the top of the email",
            key=f"email-note-{result.job.job_id}",
        )

        submitted = st.form_submit_button("Send email", icon=":material/send:")

    if submitted:
        _handle_email_send(
            result, config, recipients, selected_types, include_audio, audio, note
        )


def _audio_candidate(result: Any, config: AppConfig) -> dict[str, Any] | None:
    """Pick the audio file to offer as an attachment.

    Prefer the in-session compressed version (smaller); fall back to the
    original upload on disk so emailing audio also works for past jobs.
    Returns None when neither exists.
    """
    compressed = st.session_state.get("latest_compressed")
    if compressed:
        return {
            "filename": compressed["name"],
            "size": compressed["size"],
            "mime": compressed["mime"] or "audio/mpeg",
            "path": None,  # bytes live in session_state, not on disk
        }
    input_dir = config.jobs_dir / result.job.job_id / "input"
    matches = sorted(input_dir.glob("original.*")) if input_dir.exists() else []
    if not matches:
        return None
    path = matches[0]
    mime, _ = mimetypes.guess_type(result.job.original_filename)
    return {
        "filename": result.job.original_filename,
        "size": path.stat().st_size,
        "mime": mime or "application/octet-stream",
        "path": path,
    }


def _handle_email_send(
    result: Any,
    config: AppConfig,
    recipients: list[str],
    selected_types: list[str],
    include_audio: bool,
    audio: dict[str, Any] | None,
    note: str,
) -> None:
    if not recipients:
        st.error("Select at least one recipient.")
        return

    initialize_database(config.db_path)
    repo = Repository(config.db_path)

    # Daily send cap: a cheap abuse backstop for a publicly reachable app.
    today_start = utcnow().strftime("%Y-%m-%dT00:00:00")
    if repo.count_emails_sent_since(today_start) >= config.email_daily_limit:
        st.error(
            f"Daily email limit reached ({config.email_daily_limit}). "
            "Try again tomorrow or raise EMAIL_DAILY_LIMIT."
        )
        return

    # Load the selected files into memory.
    attachments: list[EmailAttachment] = []
    artifacts = result.artifacts or {}
    for atype in selected_types:
        _, filename, mime = _ARTIFACT_LABELS[atype]
        attachments.append(
            EmailAttachment(filename, Path(artifacts[atype]).read_bytes(), mime)
        )
    if include_audio and audio is not None:
        if audio["path"] is not None:
            data = Path(audio["path"]).read_bytes()
        else:
            data = st.session_state["latest_compressed"]["data"]
        attachments.append(EmailAttachment(audio["filename"], data, audio["mime"]))

    attachment_names = [a.filename for a in attachments]
    try:
        msg = build_transcript_email(
            result,
            sender=config.email_sender,
            recipients=recipients,
            allowed_recipients=config.email_recipients,
            attachments=attachments,
            note=note.strip() or None,
            max_attachment_mb=config.email_max_attachment_mb,
        )
    except EmailNotAllowedError as e:
        st.error(str(e))
        return

    try:
        with st.spinner("Sending..."):
            message_id = send_email(msg, config)
    except Exception as e:
        repo.insert_email_log(
            job_id=result.job.job_id,
            recipients=recipients,
            attachments=attachment_names,
            status="failed",
            error=str(e),
        )
        st.error(f"Sending failed: {e}")
        return

    repo.insert_email_log(
        job_id=result.job.job_id,
        recipients=recipients,
        attachments=attachment_names,
        status="sent",
        ses_message_id=message_id,
    )
    st.success(
        f"Sent to {', '.join(recipients)}.", icon=":material/mark_email_read:"
    )
