import logging
import re
import time

from fastapi import APIRouter, HTTPException

from app.domain.sms_models import SendSMSRequest, SendSMSResponse, SMSSendResult
from app.services.sms_telnyx import send_sms

router = APIRouter(prefix="/sms", tags=["SMS"])
logger = logging.getLogger(__name__)

URL_RE = re.compile(r"(https?://[^\s]+)", re.IGNORECASE)


@router.post("/send", response_model=SendSMSResponse)
async def send_sms_route(req: SendSMSRequest):
    start = time.perf_counter()
    recipient_count = len(req.recipients)

    if URL_RE.search(req.text):
        logger.warning(
            "sms_send rejected reason=url_in_text recipients=%d",
            recipient_count,
        )
        raise HTTPException(
            status_code=400,
            detail="Do not include URLs inside `text`. Use `link_url` instead.",
        )

    logger.info(
        "sms_send requested recipients=%d text_len=%d has_link=%s",
        recipient_count, len(req.text), bool(req.link_url),
    )

    try:
        sent = send_sms(req)
    except RuntimeError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error(
            "sms_send failed recipients=%d error=%r duration_ms=%d",
            recipient_count, e, duration_ms,
        )
        raise HTTPException(status_code=500, detail=str(e))

    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "sms_send succeeded recipients=%d duration_ms=%d",
        len(sent), duration_ms,
    )

    return SendSMSResponse(
        results=[SMSSendResult(phone=p, tracking_id=t) for p, t in sent]
    )
