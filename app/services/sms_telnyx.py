import requests
from typing import List, Dict, Tuple
from urllib.parse import quote_plus

from app.core.config import CONFIG
from app.domain.sms_models import SendSMSRequest

TELNYX_URL = "https://api.telnyx.com/v2/messages"
base=CONFIG.PUBLIC_BASE_URL


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

        print("FINAL SMS TEXT:", r["text"])

        resp = requests.post(TELNYX_URL, json=payload, headers=headers)

        if resp.status_code not in (200, 202):
            raise RuntimeError(f"Telnyx error: {resp.status_code} {resp.text}")

        results.append((r["phone"], r["tracking_id"]))

    return results
