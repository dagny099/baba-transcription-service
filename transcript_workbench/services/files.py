"""Job directory and file-saving helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import IO


@dataclass
class JobDirs:
    job_id: str
    root: Path
    input_dir: Path
    raw_dir: Path
    exports_dir: Path

    @property
    def raw_response_path(self) -> Path:
        return self.raw_dir / "provider_response.json"


def create_job_dirs(jobs_root: Path, job_id: str) -> JobDirs:
    root = jobs_root / job_id
    input_dir = root / "input"
    raw_dir = root / "raw"
    exports_dir = root / "exports"
    for d in (root, input_dir, raw_dir, exports_dir):
        d.mkdir(parents=True, exist_ok=True)
    return JobDirs(
        job_id=job_id,
        root=root,
        input_dir=input_dir,
        raw_dir=raw_dir,
        exports_dir=exports_dir,
    )


def save_uploaded_file(
    src: IO[bytes] | bytes,
    original_filename: str,
    input_dir: Path,
) -> Path:
    """Save an uploaded file to disk and return its path.

    Accepts either a file-like object (Streamlit `UploadedFile`) or raw bytes.
    """
    suffix = Path(original_filename).suffix.lower()
    target = input_dir / f"original{suffix}"
    if isinstance(src, (bytes, bytearray)):
        data = bytes(src)
    elif hasattr(src, "getbuffer"):
        data = bytes(src.getbuffer())  # type: ignore[union-attr]
    else:
        data = src.read()  # type: ignore[union-attr]
    target.write_bytes(data)
    return target
