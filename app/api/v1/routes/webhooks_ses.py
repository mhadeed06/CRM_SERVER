"""
Amazon SES event webhook (via SNS HTTPS subscription).

SES publishes send/delivery/open/click/bounce/complaint/reject events to a
configuration set → SNS topic → HTTPS subscription (this endpoint).

Payload envelope shape (SNS):
    {
      "Type": "SubscriptionConfirmation" | "Notification" | "UnsubscribeConfirmation",
      "MessageId": "...",
      "TopicArn": "...",
      "Message": "<JSON string containing the SES event>",
      "SubscribeURL": "..."       // only on SubscriptionConfirmation
    }

We forward events to CRM in the same JSON shape we used with SendGrid so no
CRM-side changes are required. `sendGridMessageId` field name is retained
for CRM backwards-compatibility (it now carries the SES message id).
"""

import asyncio
import json
import logging
import re
import time
import urllib.request
from email.parser import BytesParser
from email.policy import default as email_default_policy

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Request, Response

from app.core.config import CONFIG
from app.services.auth_client import get_auth_token
from app.services.crm_client import (
    send_email_event_to_crm,
    send_inbound_email_to_crm,
)
from app.services.email_ses import normalize_ses_message_id
from app.utils.device_detector import detect_device_type
from app.utils.geoip import get_region_from_ip
from app.utils.html_quote_stripper import strip_quoted_html
from app.utils.mail_provider import get_email_provider
from app.utils.text_quote_stripper import strip_quoted_text

router = APIRouter(prefix="/webhooks/ses", tags=["Webhooks"])
logger = logging.getLogger(__name__)


# Map SES event names → lowercase strings CRM already knows (from the
# SendGrid era). Keep this mapping stable to avoid CRM-side changes.
_SES_TO_CRM_EVENT = {
    "Delivery": "delivered",
    "Open": "open",
    "Click": "click",
    "Bounce": "bounce",
    "Complaint": "spamreport",
    "Reject": "dropped",
    # Send / DeliveryDelay / Rendering Failure / Subscription — intentionally
    # not forwarded (either duplicative of Delivery, or not needed by CRM).
}


def _tags_dict(mail_tags):
    """SES v2 tags come back as {name: [value, ...]}; flatten to {name: value}."""
    if not mail_tags:
        return {}
    result = {}
    for k, v in mail_tags.items():
        if isinstance(v, list):
            result[k] = v[0] if v else ""
        else:
            result[k] = v
    return result


def _extract_recipient(ses_event, event_type):
    """Recipient email location varies by event type."""
    if event_type == "Bounce":
        recips = ses_event.get("bounce", {}).get("bouncedRecipients") or []
        if recips:
            return recips[0].get("emailAddress")
    elif event_type == "Complaint":
        recips = ses_event.get("complaint", {}).get("complainedRecipients") or []
        if recips:
            return recips[0].get("emailAddress")
    elif event_type == "Delivery":
        recips = ses_event.get("delivery", {}).get("recipients") or []
        if recips:
            return recips[0]
    # Open / Click / Reject — use mail.destination
    dests = ses_event.get("mail", {}).get("destination") or []
    return dests[0] if dests else None


def _extract_ip_ua(ses_event, event_type):
    if event_type == "Open":
        o = ses_event.get("open", {})
        return o.get("ipAddress"), o.get("userAgent")
    if event_type == "Click":
        c = ses_event.get("click", {})
        return c.get("ipAddress"), c.get("userAgent")
    return None, None


def _map_bounce_classification(bounce_type):
    """Map SES bounceType to the SendGrid-style hard/soft strings CRM expects."""
    return {
        "Permanent": "hard",
        "Transient": "soft",
        "Undetermined": "other",
    }.get(bounce_type or "", "")


def _extract_reason(ses_event, event_type):
    if event_type == "Bounce":
        b = ses_event.get("bounce", {})
        parts = [b.get("bounceType", ""), b.get("bounceSubType", "")]
        return "/".join(p for p in parts if p)
    if event_type == "Complaint":
        return ses_event.get("complaint", {}).get("complaintFeedbackType", "") or ""
    if event_type == "Reject":
        return ses_event.get("reject", {}).get("reason", "") or ""
    return ""


def _confirm_sns_subscription(subscribe_url: str, topic_arn: str) -> bool:
    """
    Respond to an SNS subscription confirmation by GETing the SubscribeURL.
    """
    if not subscribe_url:
        return False
    try:
        with urllib.request.urlopen(subscribe_url, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            logger.info(
                "sns subscription_confirmed topic=%s status=%s body_preview=%s",
                topic_arn, resp.status, body[:200],
            )
            return True
    except Exception as e:
        logger.error("sns subscription_confirm_failed topic=%s error=%r", topic_arn, e)
        return False


@router.post("/events")
async def events(request: Request):
    start = time.perf_counter()

    try:
        raw_body = await request.body()
        envelope = json.loads(raw_body)
    except Exception as e:
        logger.error("ses_events parse_error error=%r", e)
        return Response(status_code=200)

    msg_type = envelope.get("Type") or ""
    topic_arn = envelope.get("TopicArn", "")

    # --- SNS handshake: confirm subscription on first POST ---
    if msg_type == "SubscriptionConfirmation":
        subscribe_url = envelope.get("SubscribeURL")
        logger.info(
            "sns subscription_confirmation topic=%s subscribe_url=%s",
            topic_arn, subscribe_url,
        )
        await asyncio.get_event_loop().run_in_executor(
            None, _confirm_sns_subscription, subscribe_url, topic_arn
        )
        return Response(status_code=200)

    if msg_type == "UnsubscribeConfirmation":
        logger.info("sns unsubscribe_confirmation topic=%s", topic_arn)
        return Response(status_code=200)

    if msg_type != "Notification":
        logger.warning("sns unknown_envelope_type type=%s", msg_type)
        return Response(status_code=200)

    # --- Notification: parse the nested SES event JSON string ---
    try:
        ses_event = json.loads(envelope.get("Message") or "{}")
    except Exception as e:
        logger.error("ses_events inner_parse_error error=%r", e)
        return Response(status_code=200)

    ses_event_type = ses_event.get("eventType") or ses_event.get("notificationType") or ""
    crm_event_type = _SES_TO_CRM_EVENT.get(ses_event_type)

    if not crm_event_type:
        logger.info("ses_event skipped reason=other_type event=%s", ses_event_type)
        return Response(status_code=200)

    mail_block = ses_event.get("mail", {}) or {}
    tags = _tags_dict(mail_block.get("tags"))
    # SES event carries the bare id; normalize so the value CRM stores matches
    # what replies' `In-Reply-To` header will contain (@email.amazonses.com).
    smtp_id = normalize_ses_message_id(mail_block.get("messageId", "")) or ""

    thread_id_raw = tags.get("thread_id")
    message_id_raw = tags.get("message_id")
    is_test = tags.get("is_test")

    try:
        thread_id_int = int(thread_id_raw) if thread_id_raw is not None else None
        message_id_int = int(message_id_raw) if message_id_raw is not None else None
    except (TypeError, ValueError):
        thread_id_int = None
        message_id_int = None

    recipient_email = _extract_recipient(ses_event, ses_event_type)

    if not thread_id_int or not message_id_int:
        logger.info(
            "ses_event skipped reason=missing_or_zero_ids event=%s email=%s thread_id=%s message_id=%s",
            crm_event_type, recipient_email, thread_id_raw, message_id_raw,
        )
        return Response(status_code=200)

    if is_test:
        logger.info(
            "ses_event skipped reason=is_test event=%s email=%s thread_id=%s message_id=%s",
            crm_event_type, recipient_email, thread_id_raw, message_id_raw,
        )
        return Response(status_code=200)

    ip, useragent = _extract_ip_ua(ses_event, ses_event_type)
    url = ses_event.get("click", {}).get("link", "") if ses_event_type == "Click" else ""
    reason = _extract_reason(ses_event, ses_event_type)
    bounce_classification = (
        _map_bounce_classification(ses_event.get("bounce", {}).get("bounceType", ""))
        if ses_event_type == "Bounce"
        else ""
    )

    region_str = None
    if ip:
        region_info = get_region_from_ip(ip)
        if isinstance(region_info, dict):
            region_str = ", ".join(
                part for part in [
                    region_info.get("city"),
                    region_info.get("region"),
                    region_info.get("country"),
                ] if part
            ) or None
        else:
            region_str = region_info

    logger.info(
        "ses_event forwarding event=%s to=%s threadId=%d messageId=%d",
        crm_event_type, recipient_email, thread_id_int, message_id_int,
    )

    crm_event_payload = {
        "toEmail": recipient_email or "",
        "threadId": thread_id_int,
        "messageId": message_id_int,
        "sendGridMessageId": smtp_id,  # field name kept for CRM back-compat
        "eventType": crm_event_type,
        "ipAddress": ip or "",
        "region": region_str or "",
        "emailProvider": get_email_provider(recipient_email),
        "userAgent": useragent or "",
        "deviceType": detect_device_type(useragent),
        "url": url,
        "reason": reason,
        "bounceClassification": bounce_classification,
        "rawEvent": str(ses_event),
    }

    token = await get_auth_token()
    status, body = await send_email_event_to_crm(crm_event_payload, token=token)

    duration_ms = int((time.perf_counter() - start) * 1000)
    if status and 200 <= status < 300:
        logger.info(
            "ses_event forwarded event=%s status=%s duration_ms=%d",
            crm_event_type, status, duration_ms,
        )
    else:
        logger.error(
            "ses_event forward_failed event=%s status=%s body=%s duration_ms=%d",
            crm_event_type, status, (body or "")[:500], duration_ms,
        )

    return Response(status_code=200)


# ---------------------------------------------------------------------------
# Inbound email webhook (SES receive rule → SNS → this endpoint)
# ---------------------------------------------------------------------------
#
# SES publishes each received email to an SNS topic. The SNS envelope wraps
# an "Inbound" notification whose Message field (JSON string) contains:
#
#   {
#     "notificationType": "Received",
#     "receipt": { ... },
#     "mail": {
#       "timestamp": "...",
#       "source": "sender@gmail.com",
#       "messageId": "<ses-message-id>",
#       "destination": ["reply@crm.practiceehr.com"],
#       "headers": [{"name":"From","value":"..."}, ...],
#       "commonHeaders": {"from":[...],"to":[...],"subject":"..."}
#     },
#     "content": "<full raw MIME as UTF-8 or Base64 string>"
#   }
#
# We parse the raw MIME with Python's email library, strip the quoted parent
# from the HTML body, and forward to CRM in the EXACT same shape the SendGrid
# inbound handler used — so no CRM changes are needed.
# ---------------------------------------------------------------------------


_s3_client = None


def _get_s3_client():
    """
    Lazy S3 client — created once on first inbound event.

    Prefers dedicated S3 credentials (least-privilege IAM user) if set;
    otherwise falls back to the shared AWS credentials.
    """
    global _s3_client
    if _s3_client is None:
        access_key = CONFIG.AWS_S3_ACCESS_KEY_ID or CONFIG.AWS_ACCESS_KEY_ID
        secret_key = CONFIG.AWS_S3_SECRET_ACCESS_KEY or CONFIG.AWS_SECRET_ACCESS_KEY
        _s3_client = boto3.client(
            "s3",
            region_name=CONFIG.AWS_REGION,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
    return _s3_client


def _fetch_raw_mime_from_s3(message_id):
    """
    Fetch the raw MIME email SES stored in S3. Returns bytes on success,
    None on any error (never raises — inbound path must always return 200).
    """
    bucket = CONFIG.AWS_SES_INBOUND_BUCKET
    prefix = CONFIG.AWS_SES_INBOUND_PREFIX or ""

    if not bucket or not message_id:
        logger.error(
            "ses_inbound s3_config_missing bucket=%r message_id=%r",
            bucket, message_id,
        )
        return None

    key = prefix + message_id if prefix else message_id
    try:
        resp = _get_s3_client().get_object(Bucket=bucket, Key=key)
        return resp["Body"].read()
    except ClientError as e:
        logger.error(
            "ses_inbound s3_fetch_failed bucket=%s key=%s error=%r",
            bucket, key, e,
        )
        return None


def _normalize_msg_id(mid):
    """Strip angle brackets and surrounding whitespace from a Message-ID header."""
    if not mid:
        return None
    return mid.strip().lstrip("<").rstrip(">")


def _extract_body_parts(msg):
    """Return (text_body, html_body) from a parsed EmailMessage."""
    text_body = None
    html_body = None

    # `iter_parts()` is safe on both single-part and multipart messages via the
    # default policy in Python 3.10+.
    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            try:
                content = part.get_content()
            except Exception:
                content = part.get_payload(decode=True) or b""
                if isinstance(content, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        content = content.decode(charset, errors="replace")
                    except LookupError:
                        content = content.decode("utf-8", errors="replace")
            if ctype == "text/plain" and text_body is None:
                text_body = content
            elif ctype == "text/html" and html_body is None:
                html_body = content
    else:
        ctype = msg.get_content_type()
        try:
            content = msg.get_content()
        except Exception:
            payload = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            content = payload.decode(charset, errors="replace") if isinstance(payload, bytes) else str(payload)
        if ctype == "text/html":
            html_body = content
        else:
            text_body = content

    return text_body, html_body


def _extract_from_email(from_header):
    """Extract the bare email address from a From: header value."""
    if not from_header:
        return None
    m = re.search(r"<([^>]+)>", from_header)
    if m:
        return m.group(1).strip()
    return from_header.strip()


@router.post("/inbound")
async def inbound(request: Request):
    """
    Receive inbound emails via SNS (SES receive rule → SNS topic → this URL).
    Parses the raw MIME and forwards to CRM using the same payload shape the
    SendGrid inbound handler used.
    """
    start = time.perf_counter()

    try:
        raw_body = await request.body()
        envelope = json.loads(raw_body)
    except Exception as e:
        logger.error("ses_inbound parse_error error=%r", e)
        return Response(status_code=200)

    msg_type = envelope.get("Type") or ""
    topic_arn = envelope.get("TopicArn", "")

    if msg_type == "SubscriptionConfirmation":
        subscribe_url = envelope.get("SubscribeURL")
        logger.info(
            "sns_inbound subscription_confirmation topic=%s subscribe_url=%s",
            topic_arn, subscribe_url,
        )
        await asyncio.get_event_loop().run_in_executor(
            None, _confirm_sns_subscription, subscribe_url, topic_arn
        )
        return Response(status_code=200)

    if msg_type == "UnsubscribeConfirmation":
        logger.info("sns_inbound unsubscribe_confirmation topic=%s", topic_arn)
        return Response(status_code=200)

    if msg_type != "Notification":
        logger.warning("sns_inbound unknown_envelope_type type=%s", msg_type)
        return Response(status_code=200)

    try:
        ses_message = json.loads(envelope.get("Message") or "{}")
    except Exception as e:
        logger.error("ses_inbound inner_parse_error error=%r", e)
        return Response(status_code=200)

    # SES uses "Received" notification type for inbound emails.
    notif_type = ses_message.get("notificationType") or ses_message.get("eventType") or ""
    if notif_type != "Received":
        logger.info("ses_inbound skipped reason=other_type type=%s", notif_type)
        return Response(status_code=200)

    mail_block = ses_message.get("mail") or {}
    ses_internal_id = mail_block.get("messageId", "") or ""
    destination_list = mail_block.get("destination") or []
    to_email = destination_list[0] if destination_list else ""

    # The SNS notification carries only metadata (no raw email content) —
    # SES stores the raw MIME in S3. Fetch it using the SES message ID.
    raw_bytes = await asyncio.get_event_loop().run_in_executor(
        None, _fetch_raw_mime_from_s3, ses_internal_id
    )
    if not raw_bytes:
        logger.error(
            "ses_inbound s3_fetch_returned_empty ses_id=%s to=%s",
            ses_internal_id, to_email,
        )
        return Response(status_code=200)

    try:
        msg = BytesParser(policy=email_default_policy).parsebytes(raw_bytes)
    except Exception as e:
        logger.error("ses_inbound mime_parse_error ses_id=%s error=%r", ses_internal_id, e)
        return Response(status_code=200)

    smtp_message_id = _normalize_msg_id(msg.get("Message-ID"))
    in_reply_to = _normalize_msg_id(msg.get("In-Reply-To"))
    from_header = str(msg.get("From") or "")
    subject = str(msg.get("Subject") or "")
    from_email = _extract_from_email(from_header)

    raw_text, raw_html = _extract_body_parts(msg)
    text_body = strip_quoted_text(raw_text) if raw_text else None
    html_body = strip_quoted_html(raw_html) if raw_html else None

    # Sanity log if the stripper barely changed the HTML — either it was a
    # clean reply already, or we hit an unknown client wrapper worth adding.
    if raw_html and html_body and len(html_body) > 0.9 * len(raw_html):
        logger.info(
            "ses_inbound html_quote_strip no_change from=%s raw_len=%d stripped_len=%d",
            from_email, len(raw_html), len(html_body),
        )

    logger.info(
        "ses_inbound received from=%s to=%s message_id=%s in_reply_to=%s text_len=%d html_len=%d",
        from_email, to_email, smtp_message_id, in_reply_to,
        len(text_body) if text_body else 0,
        len(html_body) if html_body else 0,
    )

    # Dev-only preview so we can eyeball parsed content in local logs.
    # Remove or gate behind APP_ENV == "local" before shipping to prod (PHI risk).
    if CONFIG.APP_ENV == "local":
        logger.info(
            "ses_inbound preview subject=%r text_preview=%r html_preview=%r",
            subject,
            (text_body or "")[:300],
            (html_body or "")[:300],
        )

    crm_inbound_payload = {
        "sendgridMessageId": smtp_message_id,   # field name kept for CRM back-compat
        "inReplyTo": in_reply_to,
        "fromEmail": from_email,
        "toEmail": to_email,
        "subject": subject,
        "textBody": text_body,
        "htmlBody": html_body,
    }

    token = await get_auth_token()
    status, body = await send_inbound_email_to_crm(crm_inbound_payload, token=token)

    duration_ms = int((time.perf_counter() - start) * 1000)
    if status and 200 <= status < 300:
        logger.info(
            "ses_inbound forwarded message_id=%s status=%s duration_ms=%d",
            smtp_message_id, status, duration_ms,
        )
    else:
        logger.error(
            "ses_inbound forward_failed message_id=%s status=%s body=%s duration_ms=%d",
            smtp_message_id, status, (body or "")[:500], duration_ms,
        )

    return Response(status_code=200)
