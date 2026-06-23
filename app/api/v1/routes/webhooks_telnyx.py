import logging

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/webhooks/telnyx", tags=["Webhooks"])
logger = logging.getLogger(__name__)


@router.post("/events")
async def telnyx_events(request: Request):
    try:
        payload = await request.json()
    except Exception as e:
        logger.error("telnyx_events parse_error error=%r", e)
        return Response(status_code=200)

    data = payload.get("data", {}) or {}
    event_type = data.get("event_type")
    message = data.get("payload", {}) or {}

    tags = message.get("tags", []) or []
    tracking_id = tags[0] if isinstance(tags, list) and len(tags) > 0 else None
    telnyx_message_id = message.get("id")

    if event_type == "message.received":
        logger.info(
            "sms_inbound received from=%s to=%s text_len=%d telnyx_message_id=%s",
            message.get("from"),
            message.get("to"),
            len(message.get("text") or ""),
            telnyx_message_id,
        )
    else:
        logger.info(
            "sms_event type=%s tracking_id=%s telnyx_message_id=%s",
            event_type, tracking_id, telnyx_message_id,
        )

    return Response(status_code=200)
