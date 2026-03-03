from typing import Dict, Optional, Tuple, List
from sendgrid import SendGridAPIClient
from app.core.config import CONFIG

reply_to_email = CONFIG.SENDGRID_REPLY_TO_EMAIL


def _build_references(references: Optional[str], reply_to_message_id: Optional[str]) -> Optional[str]:
    """
    Build the References header value.
    - references: comma-separated string of previous message IDs (can be None)
    - reply_to_message_id: the immediate parent message ID (can be None)

    Returns space-separated string as required by RFC 5322, or None if nothing to reference.
    """
    ids = []

    if references:
        # caller sends comma-separated, we convert to space-separated for RFC 5322
        ids = [mid.strip() for mid in references.split(",") if mid.strip()]

    if reply_to_message_id and reply_to_message_id not in ids:
        ids.append(reply_to_message_id)

    return " ".join(ids) if ids else None


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
                personalization["headers"]["In-Reply-To"] = reply_to_message_id

            if references_header:
                personalization["headers"]["References"] = references_header

        personalizations.append(personalization)

    payload = {
        "from": {"email": from_email},
        "reply_to": {"email": reply_to_email},
        "personalizations": personalizations,
        "content": content,
    }

    sg = SendGridAPIClient(CONFIG.SENDGRID_API_KEY)

    try:
        resp = sg.client.mail.send.post(request_body=payload)
    except Exception as e:
        raise RuntimeError(f"SendGrid request failed: {str(e)}")

    sendgrid_message_id = resp.headers.get("X-Message-Id")

    if resp.status_code not in (200, 202):
        raise RuntimeError(f"SendGrid error: {resp.status_code} {resp.body}")

    return True, sendgrid_message_id    