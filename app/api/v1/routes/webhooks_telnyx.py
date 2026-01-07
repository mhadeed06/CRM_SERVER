from fastapi import APIRouter, Request, Response
import logging

router = APIRouter(prefix="/webhooks/telnyx", tags=["Webhooks"])
logger = logging.getLogger("uvicorn")

@router.post("/events")
async def telnyx_events(request: Request):
    payload = await request.json()

    data = payload.get("data", {}) or {}
    event_type = data.get("event_type")

    message = data.get("payload", {}) or {}

    tags = message.get("tags", []) or []
    tracking_id = tags[0] if isinstance(tags, list) and len(tags) > 0 else None

    telnyx_message_id = message.get("id")

    # 🔎 extra debug
    logger.info("TELNYX event_type=%s message_id=%s tags=%s", event_type, telnyx_message_id, tags)

    logger.info(
        "SMS Event | type=%s | tracking_id=%s | telnyx_message_id=%s",
        event_type, tracking_id, telnyx_message_id
    )

    return Response(status_code=200)
