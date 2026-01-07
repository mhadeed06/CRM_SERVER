from fastapi import APIRouter, HTTPException
from ....domain.sms_models import SendSMSRequest, SendSMSResponse, SMSSendResult
from ....services.sms_telnyx import send_sms_bulk
from ....core.config import settings
from urllib.parse import quote_plus
import re

router = APIRouter(prefix="/sms", tags=["SMS"])

URL_RE = re.compile(r"(https?://[^\s]+)", re.IGNORECASE)

@router.post("/send", response_model=SendSMSResponse)
async def send_sms(req: SendSMSRequest):
    # ✅ enforce clean contract (no inline URLs)
    if URL_RE.search(req.text):
        raise HTTPException(
            status_code=400,
            detail="Do not include URLs inside `text`. Use `link_url` instead."
        )

    # normalize recipients
    recipients = []
    if req.recipients and len(req.recipients) > 0:
        recipients = [{"phone": r.phone, "tracking_id": r.client_message_id} for r in req.recipients]
    elif req.to_phone:
        if not req.client_message_id:
            raise HTTPException(400, "client_message_id is required for single SMS")
        recipients = [{"phone": req.to_phone, "tracking_id": req.client_message_id}]
    else:
        raise HTTPException(400, "Provide to_phone or recipients")

    # per-recipient message (unique tracked link)
    recipients_with_text = []
    for r in recipients:
        tracking_id = r["tracking_id"]
        final_text = req.text

        if req.link_url:
            tracked_link = f"{settings.PUBLIC_BASE_URL}/api/v1/r/{tracking_id}?u={quote_plus(req.link_url)}"
            final_text = f"{final_text} {tracked_link}"

        recipients_with_text.append({
            "phone": r["phone"],
            "tracking_id": tracking_id,
            "text": final_text,
        })

    sent = send_sms_bulk(recipients_with_text)

    return SendSMSResponse(
        results=[SMSSendResult(phone=p, tracking_id=t) for p, t in sent]
    )
