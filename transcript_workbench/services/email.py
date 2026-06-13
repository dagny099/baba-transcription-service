"""Email a transcript via AWS SES or SMTP (e.g. Gmail).

The transport is chosen by EMAIL_PROVIDER ("ses" or "smtp"); everything else —
message building, allowlist, size caps — is identical for both. Follows the
same split as the exports service: everything in this module is a pure
function that can be unit-tested without a network, except `send_email`,
which is the single function that talks to the outside world.

The email is designed to be useful without opening any attachment: the body
carries the rendered transcript, and the selected artifact files (markdown,
plain text, JSON, optionally audio) ride along as attachments.

Safety model — the app is publicly reachable, so sending is restricted here,
not just in the UI:
- Recipients must appear in the configured allowlist (`EMAIL_RECIPIENTS`).
- Total attachment size is capped (`EMAIL_MAX_ATTACHMENT_MB`).
- The UI additionally logs every send to the `email_log` table and enforces
  `EMAIL_DAILY_LIMIT` sends per UTC day.
"""

from __future__ import annotations

import html
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Sequence

import boto3

from transcript_workbench.config import AppConfig
from transcript_workbench.models.canonical import TranscriptionResult
from transcript_workbench.services.exports import build_txt
from transcript_workbench.utils.time import format_hms

# SES rejects messages larger than 40 MB *after* base64 encoding, which
# inflates binary attachments by roughly 4/3. The default attachment cap of
# 25 MB (EMAIL_MAX_ATTACHMENT_MB) keeps the encoded message comfortably under
# that ceiling with room for the body and headers.
SES_MAX_MESSAGE_MB = 40

# Email clients clip very long HTML bodies (Gmail clips at ~102 KB), so the
# inline transcript stops past this budget. Attachments always carry the
# full text, and the body says so when truncated.
MAX_HTML_BODY_CHARS = 100_000


class EmailNotAllowedError(ValueError):
    """A send request violated the recipient allowlist or the size cap."""


@dataclass
class EmailAttachment:
    """One file to attach, already loaded into memory."""

    filename: str
    data: bytes
    mime: str  # e.g. "text/markdown" or "audio/mpeg"

    @property
    def size_bytes(self) -> int:
        return len(self.data)


# ---- message assembly --------------------------------------------------------


def build_transcript_email(
    result: TranscriptionResult,
    *,
    sender: str,
    recipients: Sequence[str],
    allowed_recipients: Sequence[str],
    attachments: Sequence[EmailAttachment] = (),
    note: str | None = None,
    max_attachment_mb: int = 25,
) -> EmailMessage:
    """Build the complete MIME message for a transcript email.

    Raises `EmailNotAllowedError` if any recipient is not in the allowlist or
    the combined attachments exceed `max_attachment_mb`. These checks live
    here (not only in the UI) so a manipulated session can't bypass them.
    """
    _validate_recipients(recipients, allowed_recipients)
    _validate_attachment_size(attachments, max_attachment_mb)

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"Transcript: {result.job.original_filename}"
    # Our own Message-ID so sends are traceable in email_log regardless of
    # transport (SMTP, unlike SES, doesn't hand back an ID).
    msg["Message-ID"] = make_msgid()

    # Plain-text part first, then HTML as the preferred alternative.
    msg.set_content(build_plain_body(result, note=note))
    msg.add_alternative(build_html_body(result, note=note), subtype="html")

    for att in attachments:
        maintype, _, subtype = (att.mime or "application/octet-stream").partition("/")
        msg.add_attachment(
            att.data,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=att.filename,
        )
    return msg


def _validate_recipients(
    recipients: Sequence[str], allowed: Sequence[str]
) -> None:
    if not recipients:
        raise EmailNotAllowedError("No recipients selected.")
    allowed_normalized = {a.strip().casefold() for a in allowed}
    for r in recipients:
        if r.strip().casefold() not in allowed_normalized:
            raise EmailNotAllowedError(
                f"Recipient {r!r} is not in the configured allowlist "
                "(EMAIL_RECIPIENTS)."
            )


def _validate_attachment_size(
    attachments: Sequence[EmailAttachment], max_attachment_mb: int
) -> None:
    total = sum(a.size_bytes for a in attachments)
    limit = max_attachment_mb * 1024 * 1024
    if total > limit:
        raise EmailNotAllowedError(
            f"Attachments total {total / (1024 * 1024):.1f} MB, which exceeds "
            f"the {max_attachment_mb} MB limit (EMAIL_MAX_ATTACHMENT_MB)."
        )


# ---- body rendering ----------------------------------------------------------


def build_plain_body(result: TranscriptionResult, note: str | None = None) -> str:
    """Plain-text alternative for clients that don't render HTML."""
    job = result.job
    lines = [f"Transcript: {job.original_filename}"]
    if job.duration_seconds is not None:
        lines.append(f"Duration: {format_hms(job.duration_seconds)}")
    lines.append(f"Transcribed with {job.provider} / {job.model}")
    if note:
        lines.extend(["", note])
    lines.extend(["", build_txt(result)])
    return "\n".join(lines)


def build_html_body(result: TranscriptionResult, note: str | None = None) -> str:
    """HTML body: a short metadata header, the optional personal note, then
    the transcript itself (speakers bold, timestamps small and gray)."""
    job = result.job
    parts: list[str] = []
    parts.append(
        '<div style="font-family: -apple-system, \'Segoe UI\', Roboto, '
        "Helvetica, Arial, sans-serif; max-width: 680px; margin: 0 auto; "
        'color: #1a1a1a; line-height: 1.5;">'
    )
    parts.append(
        f'<h2 style="margin: 0 0 4px 0;">Transcript: '
        f"{html.escape(job.original_filename)}</h2>"
    )

    meta_bits: list[str] = []
    if job.duration_seconds is not None:
        meta_bits.append(format_hms(job.duration_seconds))
    meta_bits.append(f"{job.provider} / {job.model}")
    if job.created_at:
        meta_bits.append(job.created_at.strftime("%b %d, %Y"))
    parts.append(
        f'<p style="color: #666; margin: 0 0 12px 0;">'
        f'{html.escape(" · ".join(meta_bits))}</p>'
    )

    if note:
        parts.append(
            '<p style="border-left: 3px solid #ccc; padding-left: 12px; '
            f'font-style: italic;">{html.escape(note)}</p>'
        )

    parts.append('<hr style="border: none; border-top: 1px solid #ddd;">')

    blocks = _transcript_html_blocks(result)
    rendered, truncated = _join_within_budget(blocks, MAX_HTML_BODY_CHARS)
    parts.append(rendered)
    if truncated:
        parts.append(
            '<p style="color: #666;"><em>Transcript truncated for email — '
            "the attached file contains the full text.</em></p>"
        )

    parts.append("</div>")
    return "\n".join(parts)


def _transcript_html_blocks(result: TranscriptionResult) -> list[str]:
    """One HTML block per segment (or per paragraph for unsegmented text)."""
    if not result.segments:
        text = (result.text or "").strip()
        return [
            f'<p style="margin: 0 0 12px 0;">{html.escape(p)}</p>'
            for p in text.split("\n\n")
            if p.strip()
        ]

    has_times = any(s.start_seconds is not None for s in result.segments)
    blocks: list[str] = []
    for seg in result.segments:
        header_bits: list[str] = []
        if seg.speaker:
            header_bits.append(f"<strong>{html.escape(seg.speaker)}</strong>")
        if has_times:
            ts = f"{format_hms(seg.start_seconds)}–{format_hms(seg.end_seconds)}"
            header_bits.append(
                f'<span style="color: #999; font-size: 0.85em;">{ts}</span>'
            )
        header = (
            f'<div style="margin-bottom: 2px;">{" &middot; ".join(header_bits)}</div>'
            if header_bits
            else ""
        )
        blocks.append(
            f'<div style="margin: 0 0 14px 0;">{header}'
            f"{html.escape(seg.text.strip())}</div>"
        )
    return blocks


def _join_within_budget(blocks: list[str], budget_chars: int) -> tuple[str, bool]:
    """Join blocks until the character budget is spent.

    Returns (joined_html, truncated). Always includes at least one block so
    the email is never empty.
    """
    out: list[str] = []
    used = 0
    for block in blocks:
        if out and used + len(block) > budget_chars:
            return "\n".join(out), True
        out.append(block)
        used += len(block)
    return "\n".join(out), False


# ---- sending -----------------------------------------------------------------


def send_email(msg: EmailMessage, config: AppConfig) -> str:
    """Send a fully built message and return a message ID for the audit log.

    Dispatches on EMAIL_PROVIDER. The From/To addresses are taken from the
    message headers, so both transports send the exact same message.
    """
    if config.email_provider == "smtp":
        if not (config.smtp_username and config.smtp_password):
            raise RuntimeError(
                "EMAIL_PROVIDER=smtp but SMTP_USERNAME/SMTP_PASSWORD are not set."
            )
        return _send_via_smtp(
            msg,
            host=config.smtp_host,
            port=config.smtp_port,
            username=config.smtp_username,
            password=config.smtp_password,
        )
    return _send_via_ses(msg, region=config.aws_region)


def _send_via_ses(msg: EmailMessage, *, region: str) -> str:
    """AWS SES. Credentials come from the environment (local dev:
    AWS_PROFILE / keys; EC2: instance role), same as the rest of the app's
    boto3 usage. Returns the SES message ID."""
    client = boto3.client("sesv2", region_name=region)
    response = client.send_email(Content={"Raw": {"Data": msg.as_bytes()}})
    return response["MessageId"]


def _send_via_smtp(
    msg: EmailMessage, *, host: str, port: int, username: str, password: str
) -> str:
    """Authenticated SMTP over implicit TLS (e.g. Gmail with an app password).

    Returns our own Message-ID header, since SMTP has no server-issued ID.
    """
    with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
        smtp.login(username, password)
        refused = smtp.send_message(msg)
    if refused:
        # Partial failure: the server accepted the message for some
        # recipients but rejected others.
        raise RuntimeError(f"Server refused recipients: {', '.join(refused)}")
    return msg["Message-ID"]
