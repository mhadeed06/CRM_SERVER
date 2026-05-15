import logging
import time
from datetime import datetime

from fastapi import APIRouter, Depends

from app.auth.jwt_auth import verify_token
from app.domain.email_models import (
    RecipientSendResult,
    SendEmailRequest,
    SendEmailResponse,
)
from app.services.email_sendgrid import send_email_bulk

router = APIRouter(prefix="/email", tags=["Email"])
logger = logging.getLogger(__name__)


@router.post(
    "/send",
    response_model=SendEmailResponse,
    # JWT auth temporarily disabled until .NET CRM caller is ready to send tokens.
    # To re-enable: uncomment the line below.
    # dependencies=[Depends(verify_token)],
)
async def send(req: SendEmailRequest):
    start = time.perf_counter()
    recipient_count = len(req.recipients)

    logger.info(
        "email_send requested recipients=%d from=%s subject_len=%d",
        recipient_count, req.from_email, len(req.subject),
    )

    try:
        success, sendgrid_message_id = send_email_bulk(
            subject=req.subject,
            html=req.html,
            text=req.text,
            from_email=req.from_email,
            recipients=[r.model_dump() for r in req.recipients],
        )
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error(
            "email_send failed recipients=%d from=%s error=%r duration_ms=%d",
            recipient_count, req.from_email, e, duration_ms,
        )
        return SendEmailResponse(
            status=False,
            timestamp=datetime.utcnow(),
            results=[
                RecipientSendResult(
                    to_email=r.to_email,
                    thread_id=r.thread_id,
                    message_id=r.message_id,
                    status=f"error: {str(e)}",
                )
                for r in req.recipients
            ],
        )

    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "email_send succeeded recipients=%d sendgrid_message_id=%s duration_ms=%d",
        recipient_count, sendgrid_message_id, duration_ms,
    )

    results = [
        RecipientSendResult(
            to_email=r.to_email,
            thread_id=r.thread_id,
            message_id=r.message_id,
            status="accepted" if success else "rejected",
        )
        for r in req.recipients
    ]

    return SendEmailResponse(
        status=True,
        timestamp=datetime.utcnow(),
        results=results,
    )