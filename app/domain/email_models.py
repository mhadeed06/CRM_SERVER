from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional,Dict, Any
from datetime import datetime


class EmailRecipient(BaseModel):
    email: EmailStr
    client_message_id: str = Field(..., description="REQUIRED. Unique ID provided by client for webhook/DB correlation.")


class SendEmailRequest(BaseModel):
    subject: str
    html: str
    recipients: List[EmailRecipient] = Field(
        ..., description="List of recipients (use list of 1 for single send)"
    )

class RecipientSendResult(BaseModel):
    email: EmailStr
    tracking_id: str          # the ID you will use later to update DB

class SendEmailResponse(BaseModel):
    results: List[RecipientSendResult]

class EmailStatus(BaseModel):
    tracking_id: str
    to_email: EmailStr
    subject: str
    status: str
    opened_count: int = 0
    clicked_count: int = 0
    last_event_at: Optional[datetime] = None
    last_event_type: Optional[str] = None
    raw_last_event: Optional[Dict[str, Any]] = None

class EmailRecord(BaseModel):
    tracking_id: str
    to_email: EmailStr
    subject: str
    last_event_type: str = "sent"
    last_event_time: datetime = datetime.utcnow()
    last_event_payload: Optional[Dict[str, Any]] = None
