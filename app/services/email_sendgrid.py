import logging
import time
from typing import Dict, List, Optional, Tuple

from sendgrid import SendGridAPIClient

from app.core.config import CONFIG

logger = logging.getLogger(__name__)

reply_to_email = CONFIG.SENDGRID_REPLY_TO_EMAIL


def _wrap_msg_id(mid: str) -> str:
    """Ensure Message-ID is wrapped in <...> per RFC 5322."""
    mid = mid.strip()
    if not mid:
        return mid
    if not mid.startswith("<"):
        mid = "<" + mid
    if not mid.endswith(">"):
        mid = mid + ">"
    return mid


def _build_references(references: Optional[str], reply_to_message_id: Optional[str]) -> Optional[str]:
    """
    Build the References header value.
    - references: comma-separated string of previous message IDs (can be None)
    - reply_to_message_id: the immediate parent message ID (can be None)

    Returns space-separated string of <id@domain> tokens per RFC 5322, or None.
    """
    ids = []

    if references:
        # caller sends comma-separated, we convert to space-separated for RFC 5322
        ids = [mid.strip() for mid in references.split(",") if mid.strip()]

    if reply_to_message_id and reply_to_message_id not in ids:
        ids.append(reply_to_message_id)

    return " ".join(_wrap_msg_id(mid) for mid in ids) if ids else None


def send_email_bulk(
    subject: str,
    html: Optional[str],
    text: Optional[str],
    from_email: str,
    recipients: List[Dict[str, Optional[str]]],
) -> Tuple[bool, Optional[str]]:
    """
    Sends bulk email in ONE SendGrid call.

    recipients format:
    [
        {
            "to_email": "...",
            "thread_id": "...",
            "message_id": "...",
            "reply_to_message_id": Optional[str],
            "references": Optional[str]  # comma-separated previous message IDs
        }
    ]
    """

    if not CONFIG.SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY is missing")

    if not recipients:
        raise RuntimeError("Recipients list cannot be empty")

    if len(recipients) > 1000:
        raise RuntimeError("SendGrid allows max 1000 recipients per API call")

    content = []

    if text:
        content.append({"type": "text/plain", "value": text})

    if html:
        content.append({"type": "text/html", "value": html})

    if not content:
        raise RuntimeError("Either html or text must be provided")

    personalizations = []

    for r in recipients:

        personalization = {
            "to": [{"email": r["to_email"]}],
            "subject": subject,
            "custom_args": {
                "thread_id": r["thread_id"],
                "message_id": r["message_id"],
            }
        }

        reply_to_message_id = r.get("reply_to_message_id")
        references = r.get("references")

        references_header = _build_references(references, reply_to_message_id)

        if reply_to_message_id or references_header:
            personalization["headers"] = {}

            if reply_to_message_id:
                personalization["headers"]["In-Reply-To"] = _wrap_msg_id(reply_to_message_id)

            if references_header:
                personalization["headers"]["References"] = references_header

        logger.info(
            "email_threading to=%s subject=%r in_reply_to_raw=%r references_raw=%r headers=%s",
            r["to_email"], subject, reply_to_message_id, references,
            personalization.get("headers"),
        )

        personalizations.append(personalization)

    payload = {
        "from": {"email": from_email},
        "reply_to": {"email": reply_to_email},
        "personalizations": personalizations,
        "content": content,
    }

    sg = SendGridAPIClient(CONFIG.SENDGRID_API_KEY)

    start = time.perf_counter()
    try:
        resp = sg.client.mail.send.post(request_body=payload)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error(
            "sendgrid_api request_failed recipients=%d duration_ms=%d error=%r",
            len(recipients), duration_ms, e,
        )
        raise RuntimeError(f"SendGrid request failed: {str(e)}")

    duration_ms = int((time.perf_counter() - start) * 1000)
    sendgrid_message_id = resp.headers.get("X-Message-Id")

    if resp.status_code not in (200, 202):
        logger.error(
            "sendgrid_api bad_status recipients=%d status=%s duration_ms=%d body=%s",
            len(recipients), resp.status_code, duration_ms,
            str(resp.body)[:500] if resp.body else "",
        )
        raise RuntimeError(f"SendGrid error: {resp.status_code} {resp.body}")

    logger.info(
        "sendgrid_api ok recipients=%d status=%s message_id=%s duration_ms=%d",
        len(recipients), resp.status_code, sendgrid_message_id, duration_ms,
    )

    # Log custom_args per recipient for traceability
    for r in recipients:
        logger.info(
            "sendgrid_api custom_args to=%s thread_id=%s message_id=%s",
            r.get("to_email"), r.get("thread_id"), r.get("message_id"),
        )

    return True, sendgrid_message_id
