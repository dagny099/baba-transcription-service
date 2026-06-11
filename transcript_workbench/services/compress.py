"""Audio compression for transcription.

Re-encodes audio (or audio from a video file) to a small, speech-optimized
MP3 so oversize files fit under provider size caps (notably OpenAI's 25 MB).
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from transcript_workbench.services.audio import has_ffmpeg
from transcript_workbench.utils.logging import get_logger

logger = get_logger(__name__)

# Speech-optimized recipe: drop video, mono, 16 kHz, 64 kbps MP3.
# About 28 MB per hour of speech — most inputs end up well under the 25 MB cap.
_CODEC = "libmp3lame"
_BITRATE = "64k"
_SAMPLE_RATE = 16000
_CHANNELS = 1
COMPRESSED_EXTENSION = ".mp3"
COMPRESSED_MIME = "audio/mpeg"


@dataclass
class CompressionResult:
    data: bytes
    size_bytes: int
    suggested_filename: str
    mime_type: str


def compress_for_transcription(
    src_bytes: bytes,
    source_filename: str,
    timeout_seconds: int = 600,
) -> CompressionResult:
    """Compress an audio/video blob to speech-optimized MP3.

    Raises RuntimeError if ffmpeg is missing or the encode fails.
    """
    if not has_ffmpeg():
        raise RuntimeError(
            "ffmpeg is not installed on the server. Compress the file locally "
            "and re-upload, or install ffmpeg on the host."
        )

    src_suffix = Path(source_filename).suffix or ".bin"
    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = Path(tmpdir) / f"input{src_suffix}"
        out_path = Path(tmpdir) / f"compressed{COMPRESSED_EXTENSION}"
        in_path.write_bytes(src_bytes)

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(in_path),
            "-vn",
            "-ac", str(_CHANNELS),
            "-ar", str(_SAMPLE_RATE),
            "-c:a", _CODEC,
            "-b:a", _BITRATE,
            str(out_path),
        ]
        logger.info("Running ffmpeg compression: %s", " ".join(cmd))
        try:
            completed = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_seconds
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"ffmpeg timed out after {timeout_seconds}s while compressing "
                f"{source_filename}."
            ) from e

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            tail = "\n".join(stderr.splitlines()[-5:]) if stderr else "(no stderr)"
            raise RuntimeError(
                f"ffmpeg failed (exit {completed.returncode}). Last lines of stderr:\n{tail}"
            )

        data = out_path.read_bytes()

    suggested_name = f"{Path(source_filename).stem}_compressed{COMPRESSED_EXTENSION}"
    return CompressionResult(
        data=data,
        size_bytes=len(data),
        suggested_filename=suggested_name,
        mime_type=COMPRESSED_MIME,
    )
