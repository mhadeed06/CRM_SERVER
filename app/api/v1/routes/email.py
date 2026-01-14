from fastapi import APIRouter, HTTPException
from app.domain.email_models import SendEmailRequest, SendEmailResponse, RecipientSendResult
from app.store.memory_store import create_email_record
from app.services.email_sendgrid import send_email_bulk

router = APIRouter(prefix="/email", tags=["Email"])

@router.post("/send", response_model=SendEmailResponse)
async def send(req: SendEmailRequest):
    recipients = [
        {"email": r.email, "tracking_id": r.client_message_id}
        for r in req.recipients
    ]
    sent = send_email_bulk(
        recipients=recipients,
        subject=req.subject,
        html=req.html,
    )
    results = []
    for email, tracking_id in sent:
        create_email_record(
            tracking_id=tracking_id,
            to_email=email,
            subject=req.subject,
        )
        results.append(
            RecipientSendResult(email=email, tracking_id=tracking_id)
        )
    return SendEmailResponse(results=results)