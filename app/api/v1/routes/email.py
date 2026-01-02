# from fastapi import APIRouter, HTTPException
# from ....domain.email_models import SendEmailRequest, SendEmailResponse
# from ....services.email_sendgrid import send_email
# from ....store.memory_store import create_email_record, get_email_record, list_email_records

# router = APIRouter(prefix="/email", tags=["Email"])

# @router.post("/send", response_model=SendEmailResponse)
# def send(req: SendEmailRequest):
#     try:
#         msg_id = send_email(req.to_email, req.subject, req.html)
#         create_email_record(msg_id, req.to_email, req.subject)
#         return SendEmailResponse(message_id=msg_id, status="sent")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# @router.get("/status/{message_id}")
# def status(message_id: str):
#     record = get_email_record(message_id)
#     if not record:
#         raise HTTPException(status_code=404, detail="Message not found")
#     return record

# @router.get("/status")
# def list_status():
#     return list_email_records()



from fastapi import APIRouter, HTTPException
from ....domain.email_models import SendEmailRequest, SendEmailResponse, RecipientSendResult
from ....services.email_sendgrid import send_email_bulk
from ....store.memory_store import create_email_record

router = APIRouter(prefix="/email", tags=["Email"])

@router.post("/send", response_model=SendEmailResponse)
async def send(req: SendEmailRequest):
    # Normalize recipients list
    recipients = []

    if req.recipients:
        for r in req.recipients:
            recipients.append({"email": r.email, "tracking_id": r.client_message_id})

    elif req.to_email:
        recipients.append({"email": req.to_email, "tracking_id": req.client_message_id})

    else:
        raise HTTPException(status_code=400, detail="Provide either 'to_email' or 'recipients'.")

    sent = send_email_bulk(
        recipients=recipients,
        subject=req.subject,
        html=req.html,
    )

    results = []
    for email, tracking_id in sent:
        create_email_record(tracking_id=tracking_id, to_email=email, subject=req.subject)
        results.append(RecipientSendResult(email=email, tracking_id=tracking_id))

    return SendEmailResponse(results=results)
