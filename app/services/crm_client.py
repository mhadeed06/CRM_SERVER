import logging
import time

import httpx

from app.core.config import CONFIG

logger = logging.getLogger(__name__)


def _build_headers(token: str | None) -> dict:
    """Build CRM request headers with dynamic bearer token."""
    headers = {
        "Content-Type": "application/json",
        "ngrok-skip-browser-warning": "true",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def send_email_event_to_crm(
    event_payload: dict,
    token: str | None = None,
) -> tuple[int | None, str]:
    """Forward a SendGrid outbound event (delivered/open/click) to CRM."""
    if not CONFIG.CRM_BASE_URL or not CONFIG.CRM_EVENT_ENDPOINT:
        logger.error("crm_event not_configured")
        return None, "CRM URL not configured"

    if not token:
        logger.error("crm_event skipped — missing auth token")
        return None, "Missing auth token"

    url = CONFIG.CRM_BASE_URL + CONFIG.CRM_EVENT_ENDPOINT
    body = {"emailEvent": event_payload}
    event_type = event_payload.get("eventType")
    thread_seq = event_payload.get("threadId")
    msg_seq = event_payload.get("messageId")

    headers = _build_headers(token)

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=body, headers=headers)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error(
            "crm_event request_exception event=%s thread=%s message=%s duration_ms=%d error=%r",
            event_type, thread_seq, msg_seq, duration_ms, e,
        )
        return None, str(e)

    duration_ms = int((time.perf_counter() - start) * 1000)

    if 200 <= resp.status_code < 300:
        logger.debug(
            "crm_event ok event=%s thread=%s message=%s status=%s duration_ms=%d",
            event_type, thread_seq, msg_seq, resp.status_code, duration_ms,
        )
    else:
        logger.error(
            "crm_event bad_status event=%s thread=%s message=%s status=%s duration_ms=%d body=%s",
            event_type, thread_seq, msg_seq, resp.status_code, duration_ms,
            resp.text[:500],
        )

    return resp.status_code, resp.text


async def send_inbound_email_to_crm(
    email_payload: dict,
    token: str | None = None,
) -> tuple[int | None, str]:
    """Forward an inbound reply email to CRM."""
    if not CONFIG.CRM_BASE_URL or not CONFIG.CRM_INBOUND_ENDPOINT:
        logger.error("crm_inbound not_configured")
        return None, "CRM inbound URL not configured"

    if not token:
        logger.error("crm_inbound skipped — missing auth token")
        return None, "Missing auth token"

    url = CONFIG.CRM_BASE_URL + CONFIG.CRM_INBOUND_ENDPOINT
    body = {"email": email_payload}
    message_id = email_payload.get("sendgridMessageId")

    headers = _build_headers(token)

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=body, headers=headers)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error(
            "crm_inbound request_exception message_id=%s duration_ms=%d error=%r",
            message_id, duration_ms, e,
        )
        return None, str(e)

    duration_ms = int((time.perf_counter() - start) * 1000)

    if 200 <= resp.status_code < 300:
        logger.debug(
            "crm_inbound ok message_id=%s status=%s duration_ms=%d",
            message_id, resp.status_code, duration_ms,
        )
    else:
        logger.error(
            "crm_inbound bad_status message_id=%s status=%s duration_ms=%d body=%s",
            message_id, resp.status_code, duration_ms, resp.text[:500],
        )

    return resp.status_code, resp.text
