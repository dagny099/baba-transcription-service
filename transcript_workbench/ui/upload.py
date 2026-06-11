"""Upload section of the Streamlit UI."""

from __future__ import annotations

from typing import Any

import streamlit as st

from transcript_workbench.constants import SUPPORTED_AUDIO_EXTENSIONS


def render_upload_section(max_upload_mb: int | None = None) -> Any:
    """Render the file uploader and return the Streamlit `UploadedFile` (or None).

    If `max_upload_mb` is provided and the uploaded file exceeds it, an error is shown
    and `None` is returned so the rest of the flow stays disabled.
    """
    st.subheader("1 · Upload an audio or video file")
    caption = "Drop or browse for an audio/video file"
    if max_upload_mb:
        caption += f" (max {max_upload_mb} MB)"
    uploaded = st.file_uploader(
        caption,
        type=SUPPORTED_AUDIO_EXTENSIONS,
        accept_multiple_files=False,
    )
    if uploaded is not None:
        size_mb = (uploaded.size or 0) / (1024 * 1024)
        col1, col2, col3 = st.columns(3)
        col1.metric("Filename", uploaded.name)
        col2.metric("Size", f"{size_mb:.2f} MB")
        col3.metric("MIME", uploaded.type or "—")
        if max_upload_mb and size_mb > max_upload_mb:
            st.error(
                f"This file is {size_mb:.1f} MB, which exceeds the configured "
                f"MAX_UPLOAD_MB={max_upload_mb}. Compress it (e.g. extract audio with "
                "ffmpeg) or raise the limit in `.env` and the Nginx config."
            )
            return None
    return uploaded
