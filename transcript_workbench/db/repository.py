"""SQLite repository.

All SQL lives here. UI and providers do not import sqlite3 directly.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from transcript_workbench.db.connection import get_connection
from transcript_workbench.models.canonical import (
    TranscriptionJob,
    TranscriptionResult,
    TranscriptSegment,
    TranscriptWord,
)
from transcript_workbench.utils.ids import new_id
from transcript_workbench.utils.time import iso_utc, utcnow


class Repository:
    """Thin SQLite repository — open a fresh connection per call."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    # ---- connection helper -------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    # ---- jobs --------------------------------------------------------------

    def create_job(self, job: TranscriptionJob) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO transcription_jobs (
                    job_id, status, original_filename, file_hash,
                    duration_seconds, provider, model,
                    requested_features_json, effective_features_json,
                    warnings_json, errors_json, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.status,
                    job.original_filename,
                    job.file_hash,
                    job.duration_seconds,
                    job.provider,
                    job.model,
                    job.requested_features.model_dump_json(),
                    job.effective_features.model_dump_json(),
                    json.dumps(job.warnings),
                    json.dumps(job.errors),
                    iso_utc(job.created_at),
                    iso_utc(job.completed_at) if job.completed_at else None,
                ),
            )

    def update_job_status(
        self,
        job_id: str,
        status: str,
        *,
        completed: bool = False,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        sets = ["status = ?"]
        args: list[Any] = [status]
        if completed:
            sets.append("completed_at = ?")
            args.append(iso_utc(utcnow()))
        if warnings is not None:
            sets.append("warnings_json = ?")
            args.append(json.dumps(warnings))
        if errors is not None:
            sets.append("errors_json = ?")
            args.append(json.dumps(errors))
        if duration_seconds is not None:
            sets.append("duration_seconds = ?")
            args.append(duration_seconds)
        args.append(job_id)
        sql = f"UPDATE transcription_jobs SET {', '.join(sets)} WHERE job_id = ?"
        with self._conn() as conn:
            conn.execute(sql, args)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM transcription_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return _row_to_dict(row)

    def list_recent_jobs(self, limit: int = 25) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM transcription_jobs "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows if r is not None]

    # ---- provider runs -----------------------------------------------------

    def insert_provider_run(
        self,
        *,
        job_id: str,
        provider: str,
        model: str,
        status: str,
        runtime_seconds: float | None = None,
        cost_estimate_usd: float | None = None,
        cost_rate_usd: float | None = None,
        cost_unit: str | None = None,
        raw_response_path: str | None = None,
        error: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> str:
        run_id = new_id()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO provider_runs (
                    run_id, job_id, provider, model, status,
                    runtime_seconds, cost_estimate_usd, cost_rate_usd,
                    cost_unit, raw_response_path, error_json,
                    started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    job_id,
                    provider,
                    model,
                    status,
                    runtime_seconds,
                    cost_estimate_usd,
                    cost_rate_usd,
                    cost_unit,
                    raw_response_path,
                    json.dumps({"error": error}) if error else None,
                    started_at or iso_utc(utcnow()),
                    completed_at,
                ),
            )
        return run_id

    def get_latest_provider_run(self, job_id: str) -> dict[str, Any] | None:
        """Return the most recent provider_run for a job, used by history view."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM provider_runs WHERE job_id = ? "
                "ORDER BY started_at DESC LIMIT 1",
                (job_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None

    # ---- segments / words --------------------------------------------------

    def insert_segments(self, segments: Iterable[TranscriptSegment]) -> None:
        rows = [
            (
                s.segment_id,
                s.job_id,
                s.segment_index,
                s.start_seconds,
                s.end_seconds,
                s.speaker,
                s.text,
                s.confidence,
                s.confidence_type,
                json.dumps(s.provider_metadata),
            )
            for s in segments
        ]
        if not rows:
            return
        with self._conn() as conn:
            conn.executemany(
                """
                INSERT INTO transcript_segments (
                    segment_id, job_id, segment_index, start_seconds,
                    end_seconds, speaker, text, confidence,
                    confidence_type, provider_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def insert_words(self, words: Iterable[TranscriptWord]) -> None:
        rows = [
            (
                w.word_id,
                w.job_id,
                w.segment_id,
                w.word_index,
                w.start_seconds,
                w.end_seconds,
                w.speaker,
                w.word,
                w.confidence,
                w.confidence_type,
                json.dumps(w.provider_metadata),
            )
            for w in words
        ]
        if not rows:
            return
        with self._conn() as conn:
            conn.executemany(
                """
                INSERT INTO transcript_words (
                    word_id, job_id, segment_id, word_index, start_seconds,
                    end_seconds, speaker, word, confidence,
                    confidence_type, provider_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_job_segments(self, job_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM transcript_segments WHERE job_id = ? "
                "ORDER BY segment_index ASC",
                (job_id,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows if r is not None]

    def get_job_words(self, job_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM transcript_words WHERE job_id = ? "
                "ORDER BY word_index ASC",
                (job_id,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows if r is not None]

    # ---- artifacts ---------------------------------------------------------

    def insert_artifact(
        self, job_id: str, artifact_type: str, path: str
    ) -> str:
        artifact_id = new_id()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (artifact_id, job_id, artifact_type, path, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (artifact_id, job_id, artifact_type, path, iso_utc(utcnow())),
            )
        return artifact_id

    def get_job_artifacts(self, job_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE job_id = ? ORDER BY created_at ASC",
                (job_id,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows if r is not None]

    # ---- composite ---------------------------------------------------------

    def save_result(self, result: TranscriptionResult) -> None:
        """Persist segments and words from a completed result."""
        self.insert_segments(result.segments)
        self.insert_words(result.words)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {k: row[k] for k in row.keys()}
