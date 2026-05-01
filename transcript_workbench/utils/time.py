"""Timing helpers."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return a timezone-aware UTC `datetime`."""
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime | None = None) -> str:
    """Return an ISO 8601 UTC string for `dt` (or now)."""
    if dt is None:
        dt = utcnow()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def format_hms(seconds: float | None) -> str:
    """Format a number of seconds as HH:MM:SS, or '--:--:--' if missing."""
    if seconds is None:
        return "--:--:--"
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
