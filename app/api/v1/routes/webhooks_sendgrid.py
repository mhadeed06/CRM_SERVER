from fastapi import APIRouter, Request, Response
from datetime import datetime
from app.store.memory_store import update_email_event
import logging

router = APIRouter(prefix="/webhooks/sendgrid", tags=["Webhooks"])

logger = logging.getLogger("uvicorn")  # ✅ correct logger

@router.post("/events")
async def events(request: Request):
    payload = await request.json()
    logger.info("FIRST EVENT SAMPLE: %s", payload[0] if isinstance(payload, list) and payload else payload)


    logger.info("✅ WEBHOOK HIT - events received: %s",
                len(payload) if isinstance(payload, list) else type(payload))

    if not isinstance(payload, list):
        return Response(status_code=200)

    for ev in payload:
        custom_args = ev.get("custom_args") or {}
        tracking_id = custom_args.get("tracking_id")


        
        if not tracking_id:
            continue

        event_type = ev.get("event", "unknown")
        logger.info("📩 SendGrid Event: %s | Message ID: %s", event_type, tracking_id)
        ts = ev.get("timestamp")
        event_time = datetime.utcfromtimestamp(ts) if ts else datetime.utcnow()

        update_email_event(
            tracking_id=tracking_id,
            event_type=event_type,
            event_payload=ev,
            event_time=event_time,
        )

    return Response(status_code=200)
