"""Tests for the SQLite repository."""

from __future__ import annotations

from datetime import datetime, timezone

from transcript_workbench.constants import (
    ARTIFACT_TXT,
    CONFIDENCE_NONE,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_CREATED,
)
from transcript_workbench.db.connection import initialize_database
from transcript_workbench.db.repository import Repository
from transcript_workbench.models.canonical import (
    TranscriptionJob,
    TranscriptSegment,
    TranscriptWord,
)
from transcript_workbench.models.features import EffectiveFeatures, RequestedFeatures


def _new_repo(tmp_path):
    db_path = tmp_path / "test.sqlite"
    initialize_database(db_path)
    return Repository(db_path)


def _make_job(job_id="job-1", status=JOB_STATUS_CREATED) -> TranscriptionJob:
    return TranscriptionJob(
        job_id=job_id,
        created_at=datetime.now(timezone.utc),
        completed_at=None,
        status=status,
        original_filename="sample.mp3",
        provider="openai",
        model="gpt-4o-mini-transcribe",
        requested_features=RequestedFeatures(),
        effective_features=EffectiveFeatures(),
        warnings=["w1"],
        errors=[],
    )


def test_create_and_get_job(tmp_path):
    repo = _new_repo(tmp_path)
    job = _make_job()
    repo.create_job(job)
    fetched = repo.get_job("job-1")
    assert fetched["job_id"] == "job-1"
    assert fetched["status"] == JOB_STATUS_CREATED
    assert fetched["original_filename"] == "sample.mp3"


def test_update_job_status_marks_completed(tmp_path):
    repo = _new_repo(tmp_path)
    repo.create_job(_make_job())
    repo.update_job_status(
        "job-1", JOB_STATUS_COMPLETED, completed=True, duration_seconds=42.0
    )
    fetched = repo.get_job("job-1")
    assert fetched["status"] == JOB_STATUS_COMPLETED
    assert fetched["completed_at"] is not None
    assert abs(float(fetched["duration_seconds"]) - 42.0) < 1e-6


def test_list_recent_jobs(tmp_path):
    repo = _new_repo(tmp_path)
    repo.create_job(_make_job(job_id="job-1"))
    repo.create_job(_make_job(job_id="job-2"))
    rows = repo.list_recent_jobs(limit=10)
    ids = [r["job_id"] for r in rows]
    assert set(ids) == {"job-1", "job-2"}


def test_insert_segments_and_words(tmp_path):
    repo = _new_repo(tmp_path)
    repo.create_job(_make_job())
    seg = TranscriptSegment(
        segment_id="seg-1",
        job_id="job-1",
        segment_index=0,
        start_seconds=0.0,
        end_seconds=4.0,
        text="hello",
        confidence=None,
        confidence_type=CONFIDENCE_NONE,
    )
    word = TranscriptWord(
        word_id="w-1",
        job_id="job-1",
        segment_id="seg-1",
        word_index=0,
        start_seconds=0.0,
        end_seconds=0.5,
        word="hello",
        confidence=None,
        confidence_type=CONFIDENCE_NONE,
    )
    repo.insert_segments([seg])
    repo.insert_words([word])
    assert len(repo.get_job_segments("job-1")) == 1
    assert len(repo.get_job_words("job-1")) == 1


def test_insert_artifact_and_provider_run(tmp_path):
    repo = _new_repo(tmp_path)
    repo.create_job(_make_job())
    aid = repo.insert_artifact("job-1", ARTIFACT_TXT, "/tmp/transcript.txt")
    assert isinstance(aid, str) and aid
    artifacts = repo.get_job_artifacts("job-1")
    assert len(artifacts) == 1
    assert artifacts[0]["path"] == "/tmp/transcript.txt"

    run_id = repo.insert_provider_run(
        job_id="job-1",
        provider="openai",
        model="gpt-4o-mini-transcribe",
        status="completed",
        runtime_seconds=1.23,
        cost_estimate_usd=0.018,
        cost_rate_usd=0.003,
        cost_unit="per_minute",
        raw_response_path="/tmp/raw.json",
    )
    assert isinstance(run_id, str) and run_id

    latest = repo.get_latest_provider_run("job-1")
    assert latest is not None
    assert latest["cost_estimate_usd"] == 0.018
    assert latest["cost_rate_usd"] == 0.003
    assert latest["cost_unit"] == "per_minute"


def test_get_latest_provider_run_returns_none_when_no_runs(tmp_path):
    repo = _new_repo(tmp_path)
    repo.create_job(_make_job())
    assert repo.get_latest_provider_run("job-1") is None


def test_idempotent_migration_adds_cost_columns_to_old_db(tmp_path):
    """A pre-cost-tracking DB should gain the new columns on init."""
    import sqlite3

    db_path = tmp_path / "old.sqlite"
    # Build a minimal pre-migration schema lacking the cost_rate_usd / cost_unit columns.
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE provider_runs (
            run_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL,
            runtime_seconds REAL,
            cost_estimate_usd REAL,
            raw_response_path TEXT,
            error_json TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    initialize_database(db_path)

    conn = sqlite3.connect(db_path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(provider_runs)").fetchall()]
    conn.close()
    assert "cost_rate_usd" in cols
    assert "cost_unit" in cols


def test_insert_segments_empty_is_noop(tmp_path):
    repo = _new_repo(tmp_path)
    repo.create_job(_make_job())
    repo.insert_segments([])  # should not raise
    repo.insert_words([])
    assert repo.get_job_segments("job-1") == []
    assert repo.get_job_words("job-1") == []
