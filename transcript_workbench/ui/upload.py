"""Upload / record section of the Streamlit UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import streamlit as st

from transcript_workbench.constants import SUPPORTED_AUDIO_EXTENSIONS


@dataclass
class MicSource:
    """Adapter wrapping a mic recording in the `UploadedFile` shape the rest
    of the pipeline expects, with a timestamped filename so History entries
    are distinguishable from uploads."""

    name: str
    size: int
    type: str
    _data: bytes

    def getbuffer(self) -> memoryview:
        return memoryview(self._data)

    def read(self) -> bytes:
        return self._data


def _wrap_mic_recording(recording: Any) -> MicSource:
    """Wrap the `st.audio_input` result, keeping the timestamped name stable
    across reruns (downstream caches key on name::size)."""
    identity = f"{getattr(recording, 'file_id', '')}::{recording.size}"
    state = st.session_state.get("_mic_source")
    if state is None or state.get("identity") != identity:
        state = {
            "identity": identity,
            "name": datetime.now().strftime("mic-%Y%m%d-%H%M%S.wav"),
        }
        st.session_state["_mic_source"] = state
    return MicSource(
        name=state["name"],
        size=recording.size or 0,
        type=recording.type or "audio/wav",
        _data=bytes(recording.getbuffer()),
    )


def _render_file_uploader(max_upload_mb: int | None) -> Any:
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
        st.caption(
            f"**{uploaded.name}** · {size_mb:.2f} MB · {uploaded.type or 'unknown type'}"
        )
        st.audio(uploaded.getvalue(), format=uploaded.type or None)
        if max_upload_mb and size_mb > max_upload_mb:
            st.error(
                f"This file is {size_mb:.1f} MB, which exceeds the configured "
                f"MAX_UPLOAD_MB={max_upload_mb}. Compress it (e.g. extract audio with "
                "ffmpeg) or raise the limit in `.env` and the Nginx config."
            )
            return None
    return uploaded


def _default_source_choice(uploaded: Any, recording: Any) -> None:
    """When both sources exist, default the picker to whichever source
    appeared (or changed) most recently, while still letting the user
    override it via the radio."""
    upload_id = f"{uploaded.name}::{uploaded.size}" if uploaded is not None else None
    mic_id = (
        f"{getattr(recording, 'file_id', '')}::{recording.size}"
        if recording is not None
        else None
    )
    prev = st.session_state.get("_source_ids", {})
    if mic_id is not None and mic_id != prev.get("mic"):
        st.session_state["_source_choice"] = "Mic recording"
    if upload_id is not None and upload_id != prev.get("upload"):
        st.session_state["_source_choice"] = "Uploaded file"
    st.session_state["_source_ids"] = {"mic": mic_id, "upload": upload_id}


def render_upload_section(max_upload_mb: int | None = None) -> Any:
    """Render the audio source section and return the source to transcribe.

    Returns a Streamlit `UploadedFile`, a `MicSource` (mic recording), or
    None when no source is ready. If both a file and a recording are
    present, a picker chooses between them (defaulting to the newest).
    """
    st.subheader("1 · Add audio :material/graphic_eq:")
    upload_tab, mic_tab = st.tabs(
        [":material/upload_file: Upload a file", ":material/mic: Record from mic"]
    )

    with upload_tab:
        uploaded = _render_file_uploader(max_upload_mb)

    with mic_tab:
        recording = st.audio_input(
            "Record from your microphone",
            help=(
                "Your browser will ask for mic permission. Recording stays "
                "in the browser until you stop it; playback appears below "
                "the recorder. Requires HTTPS (or localhost). Hover over a "
                "finished recording to reveal the ✕ that deletes it."
            ),
        )
        if recording is None:
            st.session_state.pop("_mic_source", None)

    _default_source_choice(uploaded, recording)

    if recording is not None and uploaded is not None:
        choice = st.radio(
            "Two audio sources are ready — which one should be transcribed?",
            ["Mic recording", "Uploaded file"],
            horizontal=True,
            key="_source_choice",
        )
        if choice == "Uploaded file":
            return uploaded
        return _wrap_mic_recording(recording)

    if recording is not None:
        return _wrap_mic_recording(recording)
    return uploaded
