"""Application configuration loaded from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    data_dir: Path
    db_path: Path
    jobs_dir: Path
    openai_api_key: str | None
    aws_region: str
    aws_bucket: str | None
    assemblyai_api_key: str | None
    deepgram_api_key: str | None
    max_upload_mb: int
    low_confidence_threshold: float
    default_provider: str
    default_model: str
    # Email sharing (see docs/EMAIL_SETUP.md). The transport is selected by
    # EMAIL_PROVIDER: "ses" (default) or "smtp" (e.g. Gmail app password).
    email_provider: str
    email_sender: str | None
    email_recipients: list[str]
    email_max_attachment_mb: int
    email_daily_limit: int
    smtp_host: str
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    # Optional ephemeral OpenAI key entered in the Streamlit sidebar.
    # Not loaded from env. Set at runtime by the UI; not persisted.
    session_openai_api_key: str | None = None

    @property
    def effective_openai_api_key(self) -> str | None:
        """Prefer session-supplied key over env, so users can BYO at runtime."""
        return self.session_openai_api_key or self.openai_api_key

    @property
    def email_enabled(self) -> bool:
        """Email sharing is on iff a sender, at least one recipient, and the
        chosen transport's credentials are all configured."""
        if not (self.email_sender and self.email_recipients):
            return False
        if self.email_provider == "smtp":
            return bool(self.smtp_username and self.smtp_password)
        return True  # SES authenticates via the ambient AWS credentials


def get_config() -> AppConfig:
    data_dir = Path(os.getenv("TRANSCRIPT_WORKBENCH_DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    jobs_dir = data_dir / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "transcript_workbench.sqlite"

    return AppConfig(
        data_dir=data_dir,
        db_path=db_path,
        jobs_dir=jobs_dir,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        aws_region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        aws_bucket=os.getenv("AWS_TRANSCRIBE_BUCKET") or None,
        assemblyai_api_key=os.getenv("ASSEMBLYAI_API_KEY") or None,
        deepgram_api_key=os.getenv("DEEPGRAM_API_KEY") or None,
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "200")),
        low_confidence_threshold=float(os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.80")),
        default_provider=os.getenv("DEFAULT_PROVIDER", "openai"),
        default_model=os.getenv("DEFAULT_MODEL", "gpt-4o-mini-transcribe"),
        email_provider=os.getenv("EMAIL_PROVIDER", "ses").strip().lower(),
        email_sender=os.getenv("EMAIL_SENDER") or None,
        email_recipients=_parse_csv(os.getenv("EMAIL_RECIPIENTS", "")),
        email_max_attachment_mb=int(os.getenv("EMAIL_MAX_ATTACHMENT_MB", "25")),
        email_daily_limit=int(os.getenv("EMAIL_DAILY_LIMIT", "20")),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "465")),
        smtp_username=os.getenv("SMTP_USERNAME") or None,
        smtp_password=os.getenv("SMTP_PASSWORD") or None,
    )


def _parse_csv(raw: str) -> list[str]:
    """Split a comma-separated env value into a clean list."""
    return [item.strip() for item in raw.split(",") if item.strip()]
