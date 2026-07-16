"""
Amazon SES outbound send.

Same function signature as the legacy SendGrid sender so /email/send stays
unchanged. Uses SES v2 `send_email` with raw MIME so we can attach RFC 5322
threading headers (In-Reply-To / References).
"""

import logging
import time
from email.message import EmailMessage
from typing import Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from app.core.config import CONFIG

logger = logging.getLogger(__name__)

_ses_client = None


def _get_client():
    global _ses_client
    if _ses_client is None:
        _ses_client = boto3.client(
            "sesv2",
            region_name=CONFIG.AWS_REGION,
            aws_access_key_id=CONFIG.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=CONFIG.AWS_SECRET_ACCESS_KEY,
        )
    return _ses_client


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


# SES publishes bare message IDs via SendEmail API + event notifications, but
# stamps the actual outbound `Message-ID` header as `<{id}@email.amazonses.com>`.
# Recipients' `In-Reply-To` on replies carries the header value — so anything
# CRM stores for correlation must include the suffix, or lookups will miss.
_SES_MESSAGE_ID_DOMAIN = "email.amazonses.com"


def normalize_ses_message_id(mid: Optional[str]) -> Optional[str]:
    """
    Convert a bare SES message id (`abc-def-...-000000`) into the fully
    qualified form (`abc-def-...-000000@email.amazonses.com`) so it matches
    the `Message-ID` header SES actually stamps on the outbound email.

    Leaves already-qualified ids untouched. Returns None on empty/None input.
    """
    if not mid:
        return None
    mid = mid.strip()
    if not mid:
        return None
    if "@" in mid:
        return mid
    return f"{mid}@{_SES_MESSAGE_ID_DOMAIN}"


def _build_references(references: Optional[str], reply_to_message_id: Optional[str]) -> Optional[str]:
    """
    Build the References header value.
    - references: comma-separated string of previous message IDs (can be None)
    - reply_to_message_id: the immediate parent message ID (can be None)

    Returns space-separated string of <id@domain> tokens per RFC 5322, or None.
    """
    ids = []

    if references:
        ids = [mid.strip() for mid in references.split(",") if mid.strip()]

    if reply_to_message_id and reply_to_message_id not in ids:
        ids.append(reply_to_message_id)

    return " ".join(_wrap_msg_id(mid) for mid in ids) if ids else None


def _build_mime(
    subject: str,
    html: Optional[str],
    text: Optional[str],
    from_header: str,
    reply_to: Optional[str],
    to_email: str,
    cc_list: Optional[List[str]],
    in_reply_to: Optional[str],
    references_header: Optional[str],
) -> bytes:
    """Build a raw RFC 5322 MIME message for SES SendRawEmail."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_header
    msg["To"] = to_email
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to:
        msg["Reply-To"] = reply_to
    if in_reply_to:
        msg["In-Reply-To"] = _wrap_msg_id(in_reply_to)
    if references_header:
        msg["References"] = references_header

    # Prefer HTML with a text fallback when both are provided.
    if text and html:
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
    elif html:
        msg.set_content(html, subtype="html")
    elif text:
        msg.set_content(text)

    return msg.as_bytes()


def _sanitize_tag_value(value: str) -> str:
    """
    SES message tag values must be alphanumeric plus - and _; max 256 chars.
    thread_id/message_id are numeric so this is a safety net for future fields.
    """
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(value))[:256]


def send_email_bulk(
    subject: str,
    html: Optional[str],
    text: Optional[str],
    from_email: str,
    recipients: List[Dict[str, Optional[str]]],
) -> Tuple[bool, Optional[str]]:
    """
    Send email(s) via Amazon SES. One SES API call per recipient (SES has no
    built-in personalization equivalent to SendGrid's bulk send).

    recipients format:
    [
        {
            "to_email": "...",
            "thread_id": int,
            "message_id": int,
            "reply_to_message_id": Optional[str],
            "references": Optional[str],
            "is_test": Optional[bool],
        }
    ]

    Returns (True, last_ses_message_id) on success; raises RuntimeError on any
    failure (fail-fast, matches legacy SendGrid behavior).
    """
    if not (CONFIG.AWS_ACCESS_KEY_ID and CONFIG.AWS_SECRET_ACCESS_KEY):
        raise RuntimeError("AWS SES credentials are missing")

    if not recipients:
        raise RuntimeError("Recipients list cannot be empty")

    if not html and not text:
        raise RuntimeError("Either html or text must be provided")

    # Caller-supplied from_email takes precedence; fall back to configured default.
    effective_from = from_email or CONFIG.AWS_SES_FROM_EMAIL
    if not effective_from:
        raise RuntimeError("No sender email configured (from_email or AWS_SES_FROM_EMAIL)")

    from_name = CONFIG.AWS_SES_FROM_NAME
    from_header = f"{from_name} <{effective_from}>" if from_name else effective_from
    reply_to = CONFIG.AWS_SES_REPLY_TO_EMAIL or None
    config_set = CONFIG.AWS_SES_CONFIGURATION_SET or None

    client = _get_client()
    last_message_id = None
    ok_count = 0
    start = time.perf_counter()

    for r in recipients:
        to_email = r["to_email"]
        cc_list = r.get("cc") or None  # normalize [] to None so we skip empty CC
        reply_to_message_id = r.get("reply_to_message_id")
        references_raw = r.get("references")
        references_header = _build_references(references_raw, reply_to_message_id)

        raw_mime = _build_mime(
            subject=subject,
            html=html,
            text=text,
            from_header=from_header,
            reply_to=reply_to,
            to_email=to_email,
            cc_list=cc_list,
            in_reply_to=reply_to_message_id,
            references_header=references_header,
        )

        # Message tags — SES echoes these on every event via SNS. Used by
        # webhooks_ses.py to correlate events back to CRM thread/message IDs
        # and to skip test-marked events.
        tags = [
            {"Name": "thread_id", "Value": _sanitize_tag_value(r["thread_id"])},
            {"Name": "message_id", "Value": _sanitize_tag_value(r["message_id"])},
        ]
        if r.get("is_test"):
            tags.append({"Name": "is_test", "Value": "1"})

        logger.info(
            "email_threading to=%s subject=%r in_reply_to_raw=%r references_raw=%r has_headers=%s",
            to_email, subject, reply_to_message_id, references_raw,
            bool(reply_to_message_id or references_header),
        )

        destination = {"ToAddresses": [to_email]}
        if cc_list:
            destination["CcAddresses"] = cc_list

        params = {
            "FromEmailAddress": from_header,
            "Destination": destination,
            "Content": {"Raw": {"Data": raw_mime}},
            "EmailTags": tags,
        }
        if reply_to:
            params["ReplyToAddresses"] = [reply_to]
        if config_set:
            params["ConfigurationSetName"] = config_set

        logger.info(
            "ses_api sending to=%s cc=%s config_set=%r tags=%s",
            to_email, cc_list or [], config_set,
            [(t["Name"], t["Value"]) for t in tags],
        )

        try:
            resp = client.send_email(**params)
        except ClientError as e:
            logger.error(
                "ses_api request_failed to=%s error=%r",
                to_email, e,
            )
            raise RuntimeError(f"SES request failed: {e}")

        # SES returns a bare id — normalize to the RFC 5322 Message-ID form
        # so downstream storage matches what replies' In-Reply-To will carry.
        msg_id = normalize_ses_message_id(resp.get("MessageId"))
        last_message_id = msg_id
        ok_count += 1
        logger.info(
            "ses_api ok to=%s message_id=%s thread_id=%s message_id_tag=%s",
            to_email, msg_id, r.get("thread_id"), r.get("message_id"),
        )

    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "ses_api bulk_done recipients=%d ok=%d duration_ms=%d",
        len(recipients), ok_count, duration_ms,
    )

    return True, last_message_id
