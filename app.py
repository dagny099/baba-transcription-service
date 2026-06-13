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
from transcript_workbench.ui.compression import CompressedSource, render_compression_panel
from transcript_workbench.ui.configuration import (
    preflight_caption,
    render_configuration_section,
)
from transcript_workbench.ui.history import render_history_tab
from transcript_workbench.ui.results import render_results
from transcript_workbench.ui.upload import render_upload_section


def _render_sidebar(config) -> None:
    st.sidebar.title("TranscriptWorkbench")
    st.sidebar.caption("Local-first, provider-agnostic transcription utility.")

    with st.sidebar.expander(":material/menu_book: How to use", expanded=False):
        st.markdown(
            "**Transcribe in three steps**\n"
            "1. **Add audio** — drop in a file or record from your mic. "
            "Most audio and video formats work.\n"
            "2. **Choose provider & features** — the defaults are good for "
            "most jobs. The capabilities line shows what the selected model "
            "can deliver, plus a cost estimate.\n"
            "3. **Run** — duration and estimated cost appear next to the "
            "button before you commit.\n"
            "\n"
            "**After a run** — read the transcript, check segments and "
            "confidence, or grab TXT / Markdown / JSON from the Downloads "
            "tab. Past runs live in History.\n"
            "\n"
            "**Big files** — anything over the provider's size cap gets a "
            "one-click compression step; speech accuracy is unchanged.\n"
            "\n"
            "**Privacy** — files and transcripts stay on this machine. "
            "Audio is sent only to the provider you choose, using your own "
            "API key."
        )

    st.sidebar.markdown("---")

    st.sidebar.subheader(":material/key: OpenAI API key")
    env_present = bool(config.openai_api_key)
    if env_present:
        st.sidebar.caption("✓ OPENAI_API_KEY loaded from environment.")
    else:
        st.sidebar.caption(
            "No OPENAI_API_KEY in environment — paste a key below to transcribe."
        )
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
    st.sidebar.subheader(":material/terminal: Environment")
    if has_ffmpeg() and has_ffprobe():
        st.sidebar.caption("✓ ffmpeg + ffprobe detected.")
    elif has_ffprobe():
        st.sidebar.caption(
            "⚠ ffprobe detected; ffmpeg missing (audio normalization unavailable)."
        )
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

    # Title on the left, logo filling the blank space to its right.
    # Placeholder graphic — swap assets/logo.svg for a real one anytime.
    title_col, logo_col = st.columns([2, 1], vertical_alignment="center")
    with title_col:
        st.title("TranscriptWorkbench")
        st.caption(
            "Upload an audio/video file or record from your mic, "
            "choose a provider, and transcribe."
        )
    with logo_col:
        st.image("assets/logo.svg", width="stretch")

    uploaded_file = render_upload_section(max_upload_mb=config.max_upload_mb)
    provider, model, requested = render_configuration_section(config, uploaded_file)
    transcription_source = render_compression_panel(uploaded_file, provider=provider)

    st.subheader("3 · Run :material/play_circle:")
    run_clicked = st.button(
        "Run transcription",
        type="primary",
        icon=":material/play_arrow:",
        disabled=transcription_source is None,
    )
    if transcription_source is None:
        if uploaded_file is None:
            st.caption("Add an audio file in step 1 to enable.")
        else:
            st.caption("Finish the compression step above to enable.")
    else:
        st.caption(preflight_caption(provider, model, transcription_source))

    if run_clicked and transcription_source is not None:
        with st.status("Running transcription...", expanded=True) as status:
            status.write(f"Provider: **{provider}**, model: **{model}**")
            status.write("Saving upload, inspecting audio, and calling provider...")
            report = run_transcription(
                uploaded_file=transcription_source,
                original_filename=transcription_source.name,
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
        if isinstance(transcription_source, CompressedSource):
            st.session_state["latest_compressed"] = {
                "data": bytes(transcription_source.getbuffer()),
                "name": transcription_source.name,
                "size": transcription_source.size,
                "mime": transcription_source.type,
            }
        else:
            st.session_state.pop("latest_compressed", None)

    st.markdown("---")
    st.subheader("Results")

    if "latest_report" in st.session_state:
        render_results(st.session_state["latest_report"], config)
    else:
        # No active result — still let users see history.
        history_tab, = st.tabs([":material/history: History"])
        with history_tab:
            render_history_tab(config)


if __name__ == "__main__":
    main()
