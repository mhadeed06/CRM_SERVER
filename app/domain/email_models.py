from pydantic import BaseModel, BeforeValidator, EmailStr
from typing import Annotated, List, Optional
from datetime import datetime


def _coerce_to_str(v):
    """
    CRM sends entity_id as either a bare number (long) or a string. Normalize
    to string at parse-time so downstream code always deals with str.
    """
    if v is None:
        return None
    if isinstance(v, bool):
        # bool is technically an int subclass — treat as-is so Pydantic can
        # reject it if the field is str-only.
        return v
    if isinstance(v, (int, float)):
        return str(v)
    return v


class RecipientItem(BaseModel):
    to_email: EmailStr
    thread_id: int
    message_id: int
    reply_to_message_id: Optional[str] = None
    references: Optional[str] = None  # comma-separated list of previous message IDs
    is_test: Optional[bool] = None  # mark as test so resulting events are NOT forwarded to CRM
    cc: Optional[List[EmailStr]] = None  # additional CC recipients; treated identically to `to` by CRM
    # CRM tenant/practice id — echoed back on unsubscribe events. Accepts int
    # or string on the wire; coerced to string internally.
    entity_id: Annotated[Optional[str], BeforeValidator(_coerce_to_str)] = None


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
    status: str


class SendEmailResponse(BaseModel):
    status: bool
    timestamp: datetime
    results: List[RecipientSendResult]
