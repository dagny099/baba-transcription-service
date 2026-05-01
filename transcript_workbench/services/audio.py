"""Audio inspection / preprocessing service.

The MVP passes uploaded files directly to the provider. This service exists
so future milestones can plug in normalization, format conversion, and audio
extraction from video files without touching the rest of the app.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcript_workbench.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AudioMetadata:
    duration_seconds: float | None = None
    codec: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    format_name: str | None = None
    raw: dict[str, Any] | None = None


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def has_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


def ffprobe_metadata(path: Path) -> AudioMetadata:
    """Inspect a media file with ffprobe. Returns empty metadata if unavailable."""
    if not has_ffprobe():
        logger.info("ffprobe not installed; skipping metadata inspection.")
        return AudioMetadata()

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=30
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.warning("ffprobe failed for %s: %s", path, e)
        return AudioMetadata()

    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return AudioMetadata()

    fmt = raw.get("format", {}) or {}
    streams = raw.get("streams", []) or []
    audio_stream = next(
        (s for s in streams if s.get("codec_type") == "audio"),
        None,
    )

    duration: float | None = None
    if "duration" in fmt:
        try:
            duration = float(fmt["duration"])
        except (TypeError, ValueError):
            duration = None

    codec = audio_stream.get("codec_name") if audio_stream else None
    sample_rate = None
    channels = None
    if audio_stream:
        try:
            sample_rate = int(audio_stream.get("sample_rate")) if audio_stream.get("sample_rate") else None
        except (TypeError, ValueError):
            sample_rate = None
        channels = audio_stream.get("channels")

    return AudioMetadata(
        duration_seconds=duration,
        codec=codec,
        sample_rate=sample_rate,
        channels=channels,
        format_name=fmt.get("format_name"),
        raw=raw,
    )


def normalize_to_wav(input_path: Path, output_path: Path) -> Path:  # pragma: no cover - optional
    """Normalize an audio file to mono 16kHz wav using ffmpeg.

    Not used by the MVP transcription path, but available for future use.
    """
    if not has_ffmpeg():
        raise RuntimeError("ffmpeg is not installed; cannot normalize audio.")
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-ac", "1",
        "-ar", "16000",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path
