from fastapi import APIRouter, HTTPException

from app.domain.sms_models import SendSMSRequest, SendSMSResponse, SMSSendResult
from app.services.sms_telnyx import send_sms
import re

router = APIRouter(prefix="/sms", tags=["SMS"])
URL_RE = re.compile(r"(https?://[^\s]+)", re.IGNORECASE)

@router.post("/send", response_model=SendSMSResponse)
async def send_sms_route(req: SendSMSRequest):
    # API-level validation only
    if URL_RE.search(req.text):
        raise HTTPException(
            status_code=400,
            detail="Do not include URLs inside `text`. Use `link_url` instead."
        )

    try:
        sent = send_sms(req)
    except RuntimeError as e:
        # optional: map service errors to clean HTTP errors
        raise HTTPException(status_code=500, detail=str(e))

    return SendSMSResponse(
        results=[SMSSendResult(phone=p, tracking_id=t) for p, t in sent]
    )