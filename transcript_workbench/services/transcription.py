"""Transcription orchestration.

Wires up: job creation -> file save -> audio inspection -> feature
negotiation -> provider transcription -> persistence -> exports.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcript_workbench.config import AppConfig
from transcript_workbench.constants import (
    ARTIFACT_INPUT,
    ARTIFACT_RAW,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_CREATED,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
)
from transcript_workbench.db.connection import initialize_database
from transcript_workbench.db.repository import Repository
from transcript_workbench.models.canonical import (
    TranscriptionJob,
    TranscriptionResult,
)
from transcript_workbench.models.features import RequestedFeatures
from transcript_workbench.providers.factory import get_provider
from transcript_workbench.providers.pricing import CostEstimate, estimate_cost
from transcript_workbench.services.audio import ffprobe_metadata, has_ffmpeg
from transcript_workbench.services.exports import export_result
from transcript_workbench.services.feature_negotiation import resolve_effective_features
from transcript_workbench.services.files import create_job_dirs, save_uploaded_file
from transcript_workbench.utils.hashing import sha256_file
from transcript_workbench.utils.ids import new_id
from transcript_workbench.utils.logging import get_logger
from transcript_workbench.utils.time import iso_utc, utcnow

logger = get_logger(__name__)


@dataclass
class TranscriptionRunReport:
    """Result returned to the UI."""

    result: TranscriptionResult | None
    error: str | None
    warnings: list[str]
    job_id: str
    elapsed_seconds: float
    artifacts: dict[str, str]
    audio_metadata: dict[str, Any]
    cost_estimate: CostEstimate | None = None


def run_transcription(
    *,
    uploaded_file: Any,
    original_filename: str,
    provider_name: str,
    model: str,
    requested_features: RequestedFeatures,
    config: AppConfig,
) -> TranscriptionRunReport:
    """End-to-end orchestration of one transcription job."""
    initialize_database(config.db_path)
    repo = Repository(config.db_path)

    job_id = new_id()
    job_dirs = create_job_dirs(config.jobs_dir, job_id)

    started_at = utcnow()
    started_iso = iso_utc(started_at)

    # ---- save upload --------------------------------------------------------
    try:
        original_path = save_uploaded_file(
            uploaded_file, original_filename, job_dirs.input_dir
        )
    except Exception as e:
        logger.exception("Failed to save uploaded file")
        return _failure(job_id, f"Failed to save uploaded file: {e}", started_at)

    # ---- inspect audio ------------------------------------------------------
    audio_meta = ffprobe_metadata(original_path)
    audio_meta_dict: dict[str, Any] = {
        "duration_seconds": audio_meta.duration_seconds,
        "codec": audio_meta.codec,
        "sample_rate": audio_meta.sample_rate,
        "channels": audio_meta.channels,
        "format_name": audio_meta.format_name,
        "ffmpeg_available": has_ffmpeg(),
    }

    file_hash: str | None
    try:
        file_hash = sha256_file(original_path)
    except Exception:  # pragma: no cover - defensive
        file_hash = None

    # ---- feature negotiation ------------------------------------------------
    try:
        effective_features, neg_warnings = resolve_effective_features(
            provider_name, model, requested_features
        )
    except KeyError as e:
        return _failure(job_id, f"Unknown provider/model: {e}", started_at)

    # ---- create job row -----------------------------------------------------
    job_record = TranscriptionJob(
        job_id=job_id,
        created_at=started_at,
        completed_at=None,
        status=JOB_STATUS_CREATED,
        original_filename=original_filename,
        file_hash=file_hash,
        duration_seconds=audio_meta.duration_seconds,
        provider=provider_name,
        model=model,
        requested_features=requested_features,
        effective_features=effective_features,
        warnings=list(neg_warnings),
        errors=[],
    )
    repo.create_job(job_record)
    repo.insert_artifact(job_id, ARTIFACT_INPUT, str(original_path))

    # ---- get provider, validate config -------------------------------------
    try:
        provider = get_provider(provider_name, config)
    except ValueError as e:
        repo.update_job_status(
            job_id, JOB_STATUS_FAILED, completed=True, errors=[str(e)]
        )
        return _failure(job_id, str(e), started_at, warnings=neg_warnings)

    config_errors = provider.validate_config()
    if config_errors:
        msg = "; ".join(config_errors)
        repo.update_job_status(
            job_id, JOB_STATUS_FAILED, completed=True, errors=config_errors
        )
        return _failure(job_id, msg, started_at, warnings=neg_warnings)

    repo.update_job_status(job_id, JOB_STATUS_RUNNING)

    # ---- run transcription --------------------------------------------------
    perf_start = time.perf_counter()
    raw_path = job_dirs.raw_response_path
    try:
        result = provider.transcribe(
            audio_path=original_path,
            job_id=job_id,
            original_filename=original_filename,
            model=model,
            requested_features=requested_features,
            effective_features=effective_features,
            raw_output_path=raw_path,
        )
    except Exception as e:  # noqa: BLE001 - we want to surface anything
        logger.exception("Provider transcription failed")
        elapsed = time.perf_counter() - perf_start
        # No cost recorded on failure — we don't know how much (if any) the
        # provider billed for a request that errored mid-flight.
        repo.insert_provider_run(
            job_id=job_id,
            provider=provider_name,
            model=model,
            status="failed",
            runtime_seconds=elapsed,
            raw_response_path=str(raw_path) if raw_path.exists() else None,
            error=str(e),
            started_at=started_iso,
            completed_at=iso_utc(utcnow()),
        )
        repo.update_job_status(
            job_id,
            JOB_STATUS_FAILED,
            completed=True,
            errors=[str(e)],
            warnings=neg_warnings,
        )
        return _failure(job_id, f"Transcription failed: {e}", started_at, warnings=neg_warnings)

    elapsed = time.perf_counter() - perf_start

    # The provider may set its own duration; prefer ffprobe if it was missing.
    if result.job.duration_seconds is None and audio_meta.duration_seconds is not None:
        result.job.duration_seconds = audio_meta.duration_seconds
    # Carry negotiation warnings into the result.
    result.job.warnings = list(neg_warnings) + list(result.job.warnings or [])
    result.job.file_hash = file_hash
    result.job.original_filename = original_filename
    result.job.requested_features = requested_features
    result.job.effective_features = effective_features

    # ---- estimate cost ------------------------------------------------------
    # Compute after the run so we use the most accurate duration available
    # (provider-reported preferred, ffprobe fallback already merged above).
    cost = estimate_cost(provider_name, model, result.job.duration_seconds)

    # ---- record provider run ------------------------------------------------
    repo.insert_provider_run(
        job_id=job_id,
        provider=provider_name,
        model=model,
        status="completed",
        runtime_seconds=elapsed,
        cost_estimate_usd=cost.usd if cost else None,
        cost_rate_usd=cost.rate_usd if cost else None,
        cost_unit=cost.unit if cost else None,
        raw_response_path=str(raw_path) if raw_path.exists() else None,
        started_at=started_iso,
        completed_at=iso_utc(utcnow()),
    )
    if raw_path.exists():
        repo.insert_artifact(job_id, ARTIFACT_RAW, str(raw_path))

    # ---- persist segments / words ------------------------------------------
    repo.save_result(result)

    # ---- exports ------------------------------------------------------------
    artifacts = export_result(
        result,
        job_dirs.exports_dir,
        txt=requested_features.export_txt,
        md=requested_features.export_md,
        json_export=requested_features.export_json,
    )
    artifact_paths = artifacts.as_dict()
    for atype, p in artifact_paths.items():
        repo.insert_artifact(job_id, atype, p)

    result.artifacts = dict(artifact_paths)
    if raw_path.exists():
        result.artifacts["raw"] = str(raw_path)

    # ---- finalize -----------------------------------------------------------
    repo.update_job_status(
        job_id,
        JOB_STATUS_COMPLETED,
        completed=True,
        warnings=result.job.warnings,
        duration_seconds=result.job.duration_seconds,
    )

    return TranscriptionRunReport(
        result=result,
        error=None,
        warnings=list(result.job.warnings),
        job_id=job_id,
        elapsed_seconds=elapsed,
        artifacts=result.artifacts,
        audio_metadata=audio_meta_dict,
        cost_estimate=cost,
    )


def _failure(
    job_id: str,
    message: str,
    started_at,
    warnings: list[str] | None = None,
) -> TranscriptionRunReport:
    elapsed = (utcnow() - started_at).total_seconds()
    return TranscriptionRunReport(
        result=None,
        error=message,
        warnings=list(warnings or []),
        job_id=job_id,
        elapsed_seconds=elapsed,
        artifacts={},
        audio_metadata={},
    )
