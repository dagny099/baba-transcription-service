"""Upload section of the Streamlit UI."""

from __future__ import annotations

from typing import Any

import streamlit as st

from transcript_workbench.constants import SUPPORTED_AUDIO_EXTENSIONS


def render_upload_section() -> Any:
    """Render the file uploader and return the Streamlit `UploadedFile` (or None)."""
    st.subheader("1 · Upload an audio or video file")
    uploaded = st.file_uploader(
        "Drop or browse for an audio/video file",
        type=SUPPORTED_AUDIO_EXTENSIONS,
        accept_multiple_files=False,
    )
    if uploaded is not None:
        size_mb = (uploaded.size or 0) / (1024 * 1024)
        col1, col2, col3 = st.columns(3)
        col1.metric("Filename", uploaded.name)
        col2.metric("Size", f"{size_mb:.2f} MB")
        col3.metric("MIME", uploaded.type or "—")
    return uploaded
