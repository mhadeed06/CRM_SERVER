from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime


class RecipientItem(BaseModel):
    to_email: EmailStr
    thread_id: int
    message_id: int
    reply_to_message_id: Optional[str] = None
    references: Optional[str] = None  # comma-separated list of previous message IDs
    is_test: Optional[bool] = None  # mark as test so resulting events are NOT forwarded to CRM


class SendEmailRequest(BaseModel):
    subject: str
    html: Optional[str] = None
    text: Optional[str] = None
    from_email: EmailStr
    recipients: List[RecipientItem]


class RecipientSendResult(BaseModel):
    to_email: EmailStr
    thread_id: int
    message_id: int
    sendgrid_message_id: Optional[str] = Field(default=None, exclude=True)
    status: str

class SendEmailResponse(BaseModel):
    status: bool
    timestamp: datetime
    results: List[RecipientSendResult]
