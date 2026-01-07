from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import logging

router = APIRouter(prefix="/r", tags=["Redirect"])
logger = logging.getLogger("uvicorn")

@router.get("/{tracking_id}")
async def redirect(tracking_id: str, u: str, request: Request):
    logger.info(
        "SMS CLICK | tracking_id=%s | ip=%s | ua=%s | url=%s",
        tracking_id,
        request.client.host,
        request.headers.get("user-agent"),
        u,
    )
    return RedirectResponse(url=u)
