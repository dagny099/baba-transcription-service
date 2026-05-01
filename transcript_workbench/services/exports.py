"""Transcript export service: TXT, Markdown, JSON.

All formatting logic lives here. The Streamlit UI only reads back the
generated files; it never builds the export strings itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from transcript_workbench.constants import (
    ARTIFACT_JSON,
    ARTIFACT_MD,
    ARTIFACT_TXT,
)
from transcript_workbench.models.canonical import TranscriptionResult
from transcript_workbench.utils.time import format_hms


@dataclass
class ExportArtifacts:
    txt_path: Path | None = None
    md_path: Path | None = None
    json_path: Path | None = None

    def as_dict(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.txt_path:
            out[ARTIFACT_TXT] = str(self.txt_path)
        if self.md_path:
            out[ARTIFACT_MD] = str(self.md_path)
        if self.json_path:
            out[ARTIFACT_JSON] = str(self.json_path)
        return out


def export_result(
    result: TranscriptionResult,
    exports_dir: Path,
    *,
    txt: bool = True,
    md: bool = True,
    json_export: bool = True,
) -> ExportArtifacts:
    exports_dir.mkdir(parents=True, exist_ok=True)
    artifacts = ExportArtifacts()
    if txt:
        artifacts.txt_path = _write(exports_dir / "transcript.txt", build_txt(result))
    if md:
        artifacts.md_path = _write(exports_dir / "transcript.md", build_markdown(result))
    if json_export:
        artifacts.json_path = _write(
            exports_dir / "transcript.json", build_json(result)
        )
    return artifacts


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ---- formatting -------------------------------------------------------------


def build_txt(result: TranscriptionResult) -> str:
    """Plain-text transcript.

    If segments contain timestamps or speakers, render line-per-segment with
    inline metadata. Otherwise return the full text body.
    """
    if not result.segments:
        return (result.text or "").strip() + "\n"

    has_times = any(s.start_seconds is not None for s in result.segments)
    has_speakers = any(s.speaker for s in result.segments)

    if not has_times and not has_speakers:
        return (result.text or "\n".join(s.text for s in result.segments)).strip() + "\n"

    lines: list[str] = []
    for seg in result.segments:
        prefix_parts: list[str] = []
        if seg.speaker:
            prefix_parts.append(seg.speaker)
        if has_times:
            ts = f"[{format_hms(seg.start_seconds)} - {format_hms(seg.end_seconds)}]"
            prefix_parts.append(ts)
        prefix = " ".join(prefix_parts)
        if prefix:
            lines.append(f"{prefix}\n{seg.text.strip()}")
        else:
            lines.append(seg.text.strip())
    return "\n\n".join(lines).strip() + "\n"


def build_markdown(result: TranscriptionResult) -> str:
    job = result.job
    out: list[str] = []
    out.append("# Transcript\n")
    out.append(f"- **Job ID:** `{job.job_id}`")
    out.append(f"- **Provider:** {job.provider}")
    out.append(f"- **Model:** {job.model}")
    out.append(f"- **Original file:** {job.original_filename}")
    if job.duration_seconds is not None:
        out.append(f"- **Duration:** {format_hms(job.duration_seconds)}")
    out.append(f"- **Status:** {job.status}")
    out.append("")
    out.append("## Effective features")
    out.append("")
    ef = job.effective_features.model_dump()
    for k, v in ef.items():
        out.append(f"- **{k}:** {v}")
    if job.warnings:
        out.append("")
        out.append("## Warnings")
        out.append("")
        for w in job.warnings:
            out.append(f"- {w}")
    out.append("")
    out.append("## Transcript")
    out.append("")

    if result.segments:
        has_times = any(s.start_seconds is not None for s in result.segments)
        for seg in result.segments:
            header_bits: list[str] = []
            if seg.speaker:
                header_bits.append(f"**{seg.speaker}**")
            if has_times:
                ts = f"_{format_hms(seg.start_seconds)}–{format_hms(seg.end_seconds)}_"
                header_bits.append(ts)
            if header_bits:
                out.append("### " + " · ".join(header_bits))
                out.append("")
            out.append(seg.text.strip())
            out.append("")
    else:
        out.append((result.text or "").strip())
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def build_json(result: TranscriptionResult) -> str:
    """JSON export of the canonical TranscriptionResult."""
    return json.dumps(result.model_dump(mode="json"), indent=2, default=str)
