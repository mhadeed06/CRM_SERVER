from typing import Dict, Any
from datetime import datetime
from ..domain.email_models import EmailStatus
from ..domain.email_models import EmailRecord

# In-memory store for demo (replace with DB later)
EMAILS: Dict[str, EmailRecord] = {}

def create_email_record(tracking_id: str, to_email: str, subject: str) -> None:
    EMAILS[tracking_id] = EmailRecord(
        tracking_id=tracking_id,
        to_email=to_email,
        subject=subject,
        last_event_type="sent",
        last_event_time=datetime.utcnow(),
        last_event_payload=None,
    )

def update_email_event(tracking_id: str, event_type: str, event_payload: Dict[str, Any], event_time: datetime) -> None:
    rec = EMAILS.get(tracking_id)
    if not rec:
        # create it if webhook arrives first (happens sometimes)
        EMAILS[tracking_id] = EmailRecord(
            tracking_id=tracking_id,
            to_email=event_payload.get("email", "unknown@example.com"),
            subject="(unknown)",
            last_event_type=event_type,
            last_event_time=event_time,
            last_event_payload=event_payload,
        )
        return

    rec.last_event_type = event_type
    rec.last_event_time = event_time
    rec.last_event_payload = event_payload

def list_email_status():
    return list(EMAILS.values())
