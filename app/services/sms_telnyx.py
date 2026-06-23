import logging
import time
from typing import Dict, List, Tuple
from urllib.parse import quote_plus

import requests

from app.core.config import CONFIG
from app.domain.sms_models import SendSMSRequest

logger = logging.getLogger(__name__)

TELNYX_URL = "https://api.telnyx.com/v2/messages"
base = CONFIG.PUBLIC_BASE_URL


def _build_tracked_link(tracking_id: str, link_url: str) -> str:
    link_url = link_url.strip()
    return f"{base}/api/v1/r/{tracking_id}?u={quote_plus(link_url)}"


def _build_recipients_with_text(req: SendSMSRequest) -> List[Dict[str, str]]:
    recipients_with_text = []

    for r in req.recipients:
        tracking_id = r.client_message_id
        final_text = req.text

        if req.link_url:
            final_text = f"{final_text} {_build_tracked_link(tracking_id, req.link_url)}"

        recipients_with_text.append({
            "phone": r.phone,
            "tracking_id": tracking_id,
            "text": final_text,
        })

    return recipients_with_text


def send_sms(req: SendSMSRequest) -> List[Tuple[str, str]]:
    """
    Orchestrates SMS sending for all recipients:
    - builds final per-recipient text (tracked link)
    - sends to Telnyx
    - returns [(phone, tracking_id), ...]
    """
    recipients = _build_recipients_with_text(req)
    return send_sms_bulk(recipients)


def send_sms_bulk(recipients: List[Dict[str, str]]) -> List[Tuple[str, str]]:
    if not CONFIG.TELNYX_API_KEY:
        raise RuntimeError("TELNYX_API_KEY missing")
    if not CONFIG.TELNYX_FROM_NUMBER:
        raise RuntimeError("TELNYX_FROM_NUMBER missing")

    headers = {
        "Authorization": f"Bearer {CONFIG.TELNYX_API_KEY}",
        "Content-Type": "application/json",
    }

    results = []

    for r in recipients:
        payload = {
            "from": CONFIG.TELNYX_FROM_NUMBER,
            "to": r["phone"],
            "text": r["text"],
            "tags": [r["tracking_id"]],
        }

        start = time.perf_counter()
        try:
            resp = requests.post(TELNYX_URL, json=payload, headers=headers, timeout=10)
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.error(
                "telnyx_api request_exception phone=%s tracking_id=%s duration_ms=%d error=%r",
                r["phone"], r["tracking_id"], duration_ms, e,
            )
            raise RuntimeError(f"Telnyx request failed: {str(e)}")

        duration_ms = int((time.perf_counter() - start) * 1000)

        if resp.status_code not in (200, 202):
            logger.error(
                "telnyx_api bad_status phone=%s tracking_id=%s status=%s duration_ms=%d body=%s",
                r["phone"], r["tracking_id"], resp.status_code, duration_ms,
                resp.text[:500],
            )
            raise RuntimeError(f"Telnyx error: {resp.status_code} {resp.text}")

        logger.info(
            "telnyx_api ok phone=%s tracking_id=%s status=%s text_len=%d duration_ms=%d",
            r["phone"], r["tracking_id"], resp.status_code, len(r["text"]), duration_ms,
        )

        results.append((r["phone"], r["tracking_id"]))

    return results
