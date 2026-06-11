"""UI for compressing oversize uploads before transcription."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st

from transcript_workbench.constants import PROVIDER_MAX_UPLOAD_MB
from transcript_workbench.services.audio import has_ffmpeg
from transcript_workbench.services.compress import (
    CompressionResult,
    compress_for_transcription,
)

# Fallback cap used when the chosen provider doesn't declare one.
_DEFAULT_PROVIDER_CAP_MB = 25


@dataclass
class CompressedSource:
    """Adapter that mimics Streamlit's `UploadedFile` shape just enough to
    flow through `save_uploaded_file` and the rest of the pipeline."""

    name: str
    size: int
    type: str
    _data: bytes

    def getbuffer(self) -> memoryview:
        return memoryview(self._data)

    def read(self) -> bytes:
        return self._data


def _provider_cap_mb(provider: str | None) -> int:
    if provider and provider in PROVIDER_MAX_UPLOAD_MB:
        return PROVIDER_MAX_UPLOAD_MB[provider]
    return _DEFAULT_PROVIDER_CAP_MB


def _estimate_compress_seconds(input_size_mb: float) -> str:
    """Rough human-readable range. Tuned for t2.micro-ish: ~1s per 2 MB of
    input for typical audio/video, with a generous spread to set expectations."""
    low = max(5, int(input_size_mb * 0.4))
    high = max(low + 5, int(input_size_mb * 1.5))
    return f"{low}–{high}s"


def render_compression_panel(
    uploaded_file: Any,
    provider: str | None = None,
) -> Any:
    """Possibly offer to compress an oversize file.

    Returns the source to transcribe:
    - the original `uploaded_file` when no compression is needed (or the user
      opts out of using the compressed version),
    - a `CompressedSource` when the user has compressed and chosen to use it,
    - `None` when the file is over the cap and not yet compressed (so the
      caller can disable the Run button).
    """
    if uploaded_file is None:
        return None

    cap_mb = _provider_cap_mb(provider)
    file_size_mb = (uploaded_file.size or 0) / (1024 * 1024)

    if file_size_mb <= cap_mb:
        # Original fits; clear any stale compression state from a prior upload.
        st.session_state.pop("_compression", None)
        return uploaded_file

    st.subheader("Compress to fit the provider's size limit")
    st.info(
        f"This file is **{file_size_mb:.1f} MB**, over the **{cap_mb} MB** cap "
        f"for the selected provider. Compress to mono 16 kHz MP3 (~64 kbps) to "
        "bring it under the limit. Video (if any) is dropped — only the audio "
        "is transcribed."
    )

    if not has_ffmpeg():
        suffix = Path(uploaded_file.name).suffix or ".mp4"
        st.warning(
            "ffmpeg is not installed on this server, so in-browser compression "
            "isn't available. Compress locally and re-upload:\n\n"
            "```bash\n"
            f"ffmpeg -i input{suffix} -vn -ac 1 -ar 16000 "
            "-c:a libmp3lame -b:a 64k output.mp3\n"
            "```"
        )
        return None  # block the run button — original will fail at the provider

    # ---- state cache (avoid re-running ffmpeg on every rerun) -----------
    source_key = f"{uploaded_file.name}::{uploaded_file.size}"
    state = st.session_state.get("_compression")
    if state and state.get("source_key") != source_key:
        st.session_state.pop("_compression", None)
        state = None

    if state is None:
        st.caption(
            "What this changes: drops video, downmixes stereo → mono, "
            "downsamples to 16 kHz, re-encodes at 64 kbps MP3. Speech models "
            "don't benefit from higher fidelity, so transcription accuracy "
            "stays the same."
        )
        st.caption(
            f"Estimated wait: ~{_estimate_compress_seconds(file_size_mb)} "
            "(depends on instance size and recording length)."
        )
        if st.button("Compress audio", type="secondary"):
            with st.spinner("Compressing with ffmpeg..."):
                try:
                    result = compress_for_transcription(
                        src_bytes=bytes(uploaded_file.getbuffer()),
                        source_filename=uploaded_file.name,
                    )
                except RuntimeError as e:
                    st.error(f"Compression failed: {e}")
                    return None
            st.session_state["_compression"] = {
                "source_key": source_key,
                "result": result,
            }
            st.rerun()
        # Awaiting click — caller should disable Run.
        return None

    # ---- post-compression preview ----------------------------------------
    result: CompressionResult = state["result"]
    compressed_mb = result.size_bytes / (1024 * 1024)
    pct = (compressed_mb / file_size_mb * 100) if file_size_mb else 0

    cols = st.columns(3)
    cols[0].metric("Original", f"{file_size_mb:.1f} MB")
    # `delta_color="inverse"` flips the default: a negative delta (smaller
    # is better here) shows green instead of red.
    cols[1].metric(
        "Compressed",
        f"{compressed_mb:.1f} MB",
        f"-{100 - pct:.0f}%",
        delta_color="inverse",
    )
    cols[2].metric("Format", "MP3 mono 16 kHz")

    st.audio(result.data, format=result.mime_type)
    st.download_button(
        "Download compressed audio",
        data=result.data,
        file_name=result.suggested_filename,
        mime=result.mime_type,
    )

    if compressed_mb > cap_mb:
        st.error(
            f"The compressed file is still {compressed_mb:.1f} MB, over the "
            f"{cap_mb} MB cap. This recording is likely too long to transcribe "
            "in one piece — chunked uploads aren't supported yet."
        )
        return None

    use_compressed = st.checkbox(
        "Use the compressed audio for transcription",
        value=True,
        help="Uncheck to send the original file instead (will fail if over the cap).",
    )

    if use_compressed:
        return CompressedSource(
            name=result.suggested_filename,
            size=result.size_bytes,
            type=result.mime_type,
            _data=result.data,
        )
    # User opted to keep the original; let the caller decide whether to block.
    return uploaded_file
