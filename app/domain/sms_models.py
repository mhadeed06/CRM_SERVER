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
    # single
    to_phone: Optional[str] = None
    client_message_id: Optional[str] = None

    # bulk
    recipients: List[SMSRecipient] = Field(default_factory=list)


class SMSSendResult(BaseModel):
    phone: str
    tracking_id: str

class SendSMSResponse(BaseModel):
    results: List[SMSSendResult]
