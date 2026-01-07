import requests
from typing import List, Dict, Tuple
from ..core.config import settings

TELNYX_URL = "https://api.telnyx.com/v2/messages"

def send_sms_bulk(
    recipients: List[Dict[str, str]],
) -> List[Tuple[str, str]]:
    """
    recipients: [{ "phone": "...", "tracking_id": "...", "text": "..." }, ...]
    returns: [(phone, tracking_id), ...]
    """

    if not settings.TELNYX_API_KEY:
        raise RuntimeError("TELNYX_API_KEY missing")
    if not settings.TELNYX_FROM_NUMBER:
        raise RuntimeError("TELNYX_FROM_NUMBER missing")

    headers = {
        "Authorization": f"Bearer {settings.TELNYX_API_KEY}",
        "Content-Type": "application/json",
    }

    results = []

    for r in recipients:
        phone = r["phone"]
        tracking_id = r["tracking_id"]  # ✅ NOW DEFINED

        payload = {
            "from": settings.TELNYX_FROM_NUMBER,
            "to": r["phone"],
            "text": r["text"],
            "tags": [tracking_id],# ✅ your tracking id
        }

        resp = requests.post(TELNYX_URL, json=payload, headers=headers)

        if resp.status_code not in (200, 202):
            raise RuntimeError(f"Telnyx error: {resp.status_code} {resp.text}")

        results.append((r["phone"], r["tracking_id"]))

    return results
