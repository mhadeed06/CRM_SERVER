import asyncio
import logging
import re
import time
from datetime import datetime
from email.parser import Parser
from email.policy import default

from fastapi import APIRouter, Request, Response

from app.services.crm_client import (
    send_email_event_to_crm,
    send_inbound_email_to_crm,
)
from app.utils.geoip import get_region_from_ip

router = APIRouter(prefix="/webhooks/sendgrid", tags=["Webhooks"])
logger = logging.getLogger(__name__)

ALLOWED_EVENT_TYPES = {"delivered", "open", "click"}


def normalize_msg_id(mid: str | None) -> str | None:
    if not mid:
        return None
    return mid.strip().lstrip("<").rstrip(">")


@router.post("/events")
async def events(request: Request):
    start = time.perf_counter()

    try:
        payload = await request.json()
    except Exception as e:
        logger.error("sendgrid_events parse_error error=%r", e)
        return Response(status_code=200)

    if not isinstance(payload, list):
        logger.warning("sendgrid_events invalid_payload type=%s", type(payload).__name__)
        return Response(status_code=200)

    total = len(payload)
    counts = {"delivered": 0, "open": 0, "click": 0}
    skipped_no_ids = 0
    skipped_other_type = 0
    crm_tasks = []

    for ev in payload:
        event_type = ev.get("event")
        custom_args = ev.get("custom_args") or {}
        thread_id = custom_args.get("thread_id") or ev.get("thread_id")
        message_id = custom_args.get("message_id") or ev.get("message_id")

        if thread_id is None or message_id is None:
            skipped_no_ids += 1
            logger.debug(
                "sendgrid_event skipped reason=missing_ids event=%s email=%s",
                event_type, ev.get("email"),
            )
            continue

        if event_type not in ALLOWED_EVENT_TYPES:
            skipped_other_type += 1
            continue

        counts[event_type] += 1

        email = ev.get("email")
        ip = ev.get("ip")

        region_info = get_region_from_ip(ip) if ip else None
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

        smtp_id = normalize_msg_id(ev.get("smtp-id"))

        try:
            thread_seq = int(thread_id)
        except Exception:
            thread_seq = 0

        try:
            msg_seq = int(message_id)
        except Exception:
            msg_seq = 0

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

        crm_tasks.append(send_email_event_to_crm(crm_event_payload))

    logger.info(
        "sendgrid_events received total=%d delivered=%d open=%d click=%d skipped_no_ids=%d skipped_other_type=%d",
        total, counts["delivered"], counts["open"], counts["click"],
        skipped_no_ids, skipped_other_type,
    )

    crm_success = 0
    crm_failed = 0
    if crm_tasks:
        results = await asyncio.gather(*crm_tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                crm_failed += 1
                logger.error("crm_forward_event exception=%r", result)
            else:
                status, body = result
                if status and 200 <= status < 300:
                    crm_success += 1
                else:
                    crm_failed += 1
                    logger.error(
                        "crm_forward_event failed status=%s body=%s",
                        status, (body or "")[:500],
                    )

    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "sendgrid_events processed total=%d crm_success=%d crm_failed=%d duration_ms=%d",
        total, crm_success, crm_failed, duration_ms,
    )

    return Response(status_code=200)


@router.post("/inbound")
async def inbound_email(request: Request):
    start = time.perf_counter()

    form_data = await request.form()

    headers_raw = form_data.get("headers", "")
    parsed_headers = Parser(policy=default).parsestr(headers_raw)

    smtp_message_id = normalize_msg_id(parsed_headers.get("Message-ID"))
    in_reply_to = normalize_msg_id(parsed_headers.get("In-Reply-To"))

    from_raw = form_data.get("from")
    subject = form_data.get("subject")
    text_body = form_data.get("text")
    html_body = form_data.get("html")
    to_email = form_data.get("to")

    email_match = re.search(r"<(.+?)>", from_raw or "")
    from_email = email_match.group(1) if email_match else from_raw

    logger.info(
        "inbound_email received from=%s to=%s message_id=%s in_reply_to=%s text_len=%d html_len=%d",
        from_email, to_email, smtp_message_id, in_reply_to,
        len(text_body) if text_body else 0,
        len(html_body) if html_body else 0,
    )

    crm_inbound_payload = {
        "sendgridMessageId": smtp_message_id,
        "inReplyTo": in_reply_to,
        "fromEmail": from_email,
        "toEmail": to_email,
        "subject": subject,
        "textBody": text_body,
        "htmlBody": html_body,
    }

    status, body = await send_inbound_email_to_crm(crm_inbound_payload)

    duration_ms = int((time.perf_counter() - start) * 1000)
    if status and 200 <= status < 300:
        logger.info(
            "inbound_email forwarded message_id=%s status=%s duration_ms=%d",
            smtp_message_id, status, duration_ms,
        )
    else:
        logger.error(
            "inbound_email forward_failed message_id=%s status=%s body=%s duration_ms=%d",
            smtp_message_id, status, (body or "")[:500], duration_ms,
        )

    return Response(status_code=200)
