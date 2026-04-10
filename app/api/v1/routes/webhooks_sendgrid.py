import asyncio
import re
import logging
from datetime import datetime
from email.parser import Parser
from email.policy import default

from fastapi import APIRouter, Request, Response

from app.utils.geoip import get_region_from_ip
from app.services.crm_client import (
    send_email_event_to_crm,
    send_inbound_email_to_crm,
)

router = APIRouter(prefix="/webhooks/sendgrid", tags=["Webhooks"])
logger = logging.getLogger("uvicorn")


# ==========================================================
# Utility
# ==========================================================

def normalize_msg_id(mid: str | None) -> str | None:
    if not mid:
        return None
    return mid.strip().lstrip("<").rstrip(">")


@router.post("/events")
async def events(request: Request):

    payload = await request.json()

    if not isinstance(payload, list):
        logger.warning("❌ Invalid SendGrid events payload format")
        return Response(status_code=200)

    logger.info("📩 ===== SENDGRID EVENTS RECEIVED =====")
    buckets = {"delivered": [], "open": [], "click": []}


    ALLOWED_EVENT_TYPES = {"delivered", "open", "click"}

    crm_tasks = []

    for ev in payload:
        et = ev.get("event")
        if et in ALLOWED_EVENT_TYPES:
            buckets[et].append(ev)
        else:
            logger.debug("Ignoring event type=%s", et)

        custom_args = ev.get("custom_args") or {}

        # try custom_args first, then top-level
        thread_id = custom_args.get("thread_id") or ev.get("thread_id")
        message_id = custom_args.get("message_id") or ev.get("message_id")
        event_type = ev.get("event")
        timestamp = ev.get("timestamp")

        if thread_id is None or message_id is None:
            logger.info("⚠ Skipping event without thread/message id: %s", ev)
            continue

        if event_type not in ALLOWED_EVENT_TYPES:
            logger.info(f"[IGNORED] {event_type} for {thread_id}/{message_id}")
            continue

        occurred_at = (
            datetime.utcfromtimestamp(timestamp).isoformat()
            if timestamp else None
        )

        email = ev.get("email")
        ip = ev.get("ip")

        # our geo function returns a dict — convert to a single string
        region_info = get_region_from_ip(ip) if ip else None
        if isinstance(region_info, dict):
            region_str = ", ".join(
                part
                for part in [
                    region_info.get("city"),
                    region_info.get("region"),
                    region_info.get("country"),
                ]
                if part
            ) or None
        else:
            region_str = region_info

        sg_message_id = ev.get("sg_message_id")
        smtp_id = normalize_msg_id(ev.get("smtp-id"))

        try:
            thread_seq = int(thread_id)
        except Exception:
            thread_seq = 0

        try:
            msg_seq = int(message_id)
        except Exception:
            msg_seq = 0

        # build exactly what CRM expects
        crm_event_payload = {
            "toEmail": email,
            "threadSeqNum": thread_seq,
            "messageSeqNum": msg_seq,
            "sendGridMessageId": smtp_id or "",
            "eventType": event_type,
            "ipAddress": ip or "",
            "region": region_str or "",
            "rawEvent": str(ev),
        }

        if event_type == "delivered":
            logger.info(f"[DELIVERED] {crm_event_payload}")
        elif event_type == "open":
            logger.info(f"[OPEN] {crm_event_payload}")
        elif event_type == "click":
            logger.info(f"[CLICK] {crm_event_payload}")

        crm_tasks.append(send_email_event_to_crm(crm_event_payload))

    # fire all CRM calls concurrently instead of one-by-one
    if crm_tasks:
        results = await asyncio.gather(*crm_tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("➡ CRM EVENT ERROR: %r", result)
            else:
                status, body = result
                logger.info("➡ CRM EVENT RESULT: status=%s body=%s", status, body)

    logger.info("📩 ===== END SENDGRID EVENTS =====")
    return Response(status_code=200)
# ==========================================================
# SENDGRID INBOUND PARSE WEBHOOK
# ==========================================================

@router.post("/inbound")
async def inbound_email(request: Request):

    form_data = await request.form()

    headers_raw = form_data.get("headers", "")
    parsed_headers = Parser(policy=default).parsestr(headers_raw)

    # SMTP message-id we will send as sendgridMessageId (threading id)
    smtp_message_id = normalize_msg_id(parsed_headers.get("Message-ID"))
    in_reply_to = normalize_msg_id(parsed_headers.get("In-Reply-To"))

    from_raw = form_data.get("from")
    subject = form_data.get("subject")
    text_body = form_data.get("text")
    html_body = form_data.get("html")
    to_email = form_data.get("to")

    # Extract clean email from "Name <email@x.com>"
    email_match = re.search(r"<(.+?)>", from_raw or "")
    from_email = email_match.group(1) if email_match else from_raw

    logger.info("📥 ===== INBOUND EMAIL RECEIVED =====")
    logger.info("From            : %s", from_email)
    logger.info("To              : %s", to_email)
    logger.info("Subject         : %s", subject)
    logger.info("SMTP Message ID : %s", smtp_message_id)
    logger.info("In-Reply-To     : %s", in_reply_to)
    logger.info("Text Length     : %d", len(text_body) if text_body else 0)
    logger.info("HTML Length     : %d", len(html_body) if html_body else 0)

    # Build payload for CRM inbound API
    crm_inbound_payload = {
        "sendgridMessageId": smtp_message_id,   # threading id
        "inReplyTo": in_reply_to,
        "fromEmail": from_email,
        "toEmail": to_email,
        "subject": subject,
        "textBody": text_body,
        "htmlBody": html_body,
    }

    # Send to CRM
    await send_inbound_email_to_crm(crm_inbound_payload)

    logger.info("📥 Sent inbound email to CRM: %s", crm_inbound_payload)
    logger.info("📥 ===== END INBOUND EMAIL =====")

    return Response(status_code=200)