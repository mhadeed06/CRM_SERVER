from fastapi import APIRouter, HTTPException
from datetime import datetime
from app.domain.email_models import (
    SendEmailRequest,
    SendEmailResponse,
    RecipientSendResult,
)
from app.services.email_sendgrid import send_email_bulk

router = APIRouter(prefix="/email", tags=["Email"])


@router.post("/send", response_model=SendEmailResponse)
async def send(req: SendEmailRequest):

    try:
        success, sendgrid_message_id = send_email_bulk(
            subject=req.subject,
            html=req.html,
            text=req.text,
            from_email=req.from_email,
            recipients=[r.dict() for r in req.recipients],
        )
    except Exception as e:
        return {
        "status": False,
        "error": str(e),
        "timestamp": datetime.utcnow()
    }

    results = []

    for r in req.recipients:
        results.append(
            RecipientSendResult(
                to_email=r.to_email,
                thread_id=r.thread_id,
                message_id=r.message_id,
                status="accepted" if success else "rejected",
            )
        )

    return SendEmailResponse(
        status=True,
        timestamp=datetime.utcnow(),
        results=results
    )