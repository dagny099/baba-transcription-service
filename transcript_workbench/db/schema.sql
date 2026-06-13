-- TranscriptWorkbench SQLite schema (MVP).

CREATE TABLE IF NOT EXISTS transcription_jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_hash TEXT,
    duration_seconds REAL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    requested_features_json TEXT NOT NULL,
    effective_features_json TEXT NOT NULL,
    warnings_json TEXT,
    errors_json TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_transcription_jobs_created_at
    ON transcription_jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS provider_runs (
    run_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    runtime_seconds REAL,
    cost_estimate_usd REAL,
    cost_rate_usd REAL,
    cost_unit TEXT,
    raw_response_path TEXT,
    error_json TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(job_id) REFERENCES transcription_jobs(job_id)
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    segment_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    segment_index INTEGER NOT NULL,
    start_seconds REAL,
    end_seconds REAL,
    speaker TEXT,
    text TEXT NOT NULL,
    confidence REAL,
    confidence_type TEXT NOT NULL,
    provider_metadata_json TEXT,
    FOREIGN KEY(job_id) REFERENCES transcription_jobs(job_id)
);

CREATE INDEX IF NOT EXISTS idx_transcript_segments_job
    ON transcript_segments(job_id, segment_index);

CREATE TABLE IF NOT EXISTS transcript_words (
    word_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    segment_id TEXT,
    word_index INTEGER NOT NULL,
    start_seconds REAL,
    end_seconds REAL,
    speaker TEXT,
    word TEXT NOT NULL,
    confidence REAL,
    confidence_type TEXT NOT NULL,
    provider_metadata_json TEXT,
    FOREIGN KEY(job_id) REFERENCES transcription_jobs(job_id),
    FOREIGN KEY(segment_id) REFERENCES transcript_segments(segment_id)
);

CREATE INDEX IF NOT EXISTS idx_transcript_words_job
    ON transcript_words(job_id, word_index);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES transcription_jobs(job_id)
);

CREATE INDEX IF NOT EXISTS idx_artifacts_job
    ON artifacts(job_id);

-- Audit log of transcript emails. Doubles as the data source for the
-- per-day send limit (EMAIL_DAILY_LIMIT) enforced before each send.
CREATE TABLE IF NOT EXISTS email_log (
    email_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    recipients TEXT NOT NULL,        -- comma-separated addresses
    attachments TEXT,                -- comma-separated attachment filenames
    ses_message_id TEXT,             -- NULL when the send failed
    status TEXT NOT NULL,            -- 'sent' | 'failed'
    error TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES transcription_jobs(job_id)
);

CREATE INDEX IF NOT EXISTS idx_email_log_created_at
    ON email_log(created_at DESC);
