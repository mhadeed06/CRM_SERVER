from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class SMSRecipient(BaseModel):
    phone: str
    client_message_id: str = Field(
        ..., description="REQUIRED. Client-provided tracking ID."
    )

class SendSMSRequest(BaseModel):
    text: str
    link_url: Optional[str] = None
    recipients: List[SMSRecipient] = Field(
        ..., description="List of recipients (use list of 1 for single SMS)."
    )

class SMSSendResult(BaseModel):
    phone: str
    tracking_id: str

class SendSMSResponse(BaseModel):
    results: List[SMSSendResult]
