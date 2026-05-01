"""TranscriptWorkbench — Streamlit entry point.

This module is intentionally thin. It composes UI sections and calls
service layers. SQL, provider API calls, parsing, and export formatting
all live in dedicated modules.
"""

from __future__ import annotations

import streamlit as st

from transcript_workbench.config import get_config
from transcript_workbench.db.connection import initialize_database
from transcript_workbench.services.audio import has_ffmpeg, has_ffprobe
from transcript_workbench.services.transcription import run_transcription
from transcript_workbench.ui.configuration import render_configuration_section
from transcript_workbench.ui.history import render_history_tab
from transcript_workbench.ui.results import render_results
from transcript_workbench.ui.upload import render_upload_section


def _render_sidebar(config) -> None:
    st.sidebar.title("TranscriptWorkbench")
    st.sidebar.caption("Local-first, provider-agnostic transcription utility.")
    st.sidebar.markdown("---")

    st.sidebar.subheader("OpenAI API key")
    env_present = bool(config.openai_api_key)
    if env_present:
        st.sidebar.success("OPENAI_API_KEY loaded from environment.")
    else:
        st.sidebar.info("No OPENAI_API_KEY in environment.")
    sidebar_key = st.sidebar.text_input(
        "Override key (this session only — never persisted)",
        type="password",
        help=(
            "Optional: paste a key here to use instead of the env value. "
            "Cleared when the app reloads."
        ),
    )
    if sidebar_key:
        config.session_openai_api_key = sidebar_key.strip()
    else:
        config.session_openai_api_key = None

    st.sidebar.markdown("---")
    st.sidebar.subheader("Environment")
    if has_ffmpeg() and has_ffprobe():
        st.sidebar.success("ffmpeg + ffprobe detected.")
    elif has_ffprobe():
        st.sidebar.info("ffprobe detected; ffmpeg missing (audio normalization unavailable).")
    else:
        st.sidebar.warning(
            "ffmpeg/ffprobe not detected. The MVP can still work for files OpenAI accepts directly, "
            "but audio metadata inspection and future normalization need ffmpeg."
        )
    st.sidebar.caption(f"Data dir: `{config.data_dir}`")
    st.sidebar.caption(f"DB: `{config.db_path.name}`")


def main() -> None:
    st.set_page_config(
        page_title="TranscriptWorkbench",
        page_icon="🎧",
        layout="wide",
    )

    config = get_config()
    initialize_database(config.db_path)

    _render_sidebar(config)

    st.title("TranscriptWorkbench")
    st.caption("Upload an audio/video file, choose a provider, and transcribe.")

    uploaded_file = render_upload_section()
    provider, model, requested = render_configuration_section(config, uploaded_file)

    st.subheader("3 · Run")
    run_clicked = st.button(
        "Run transcription",
        type="primary",
        disabled=uploaded_file is None,
    )

    if run_clicked and uploaded_file is not None:
        with st.status("Running transcription...", expanded=True) as status:
            status.write(f"Provider: **{provider}**, model: **{model}**")
            status.write("Saving upload, inspecting audio, and calling provider...")
            report = run_transcription(
                uploaded_file=uploaded_file,
                original_filename=uploaded_file.name,
                provider_name=provider,
                model=model,
                requested_features=requested,
                config=config,
            )
            if report.error:
                status.update(label="Transcription failed", state="error")
            else:
                status.update(label="Transcription complete", state="complete")
        st.session_state["latest_report"] = report

    st.markdown("---")
    st.subheader("Results")

    if "latest_report" in st.session_state:
        render_results(st.session_state["latest_report"], config)
    else:
        # No active result — still let users see history.
        history_tab, = st.tabs(["History"])
        with history_tab:
            render_history_tab(config)


if __name__ == "__main__":
    main()
