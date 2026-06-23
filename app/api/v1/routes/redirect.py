import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/r", tags=["Redirect"])
logger = logging.getLogger(__name__)


@router.get("/{tracking_id}")
async def redirect(tracking_id: str, u: str, request: Request):
    logger.info(
        "sms_click tracking_id=%s ip=%s user_agent=%s",
        tracking_id,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )
    return RedirectResponse(url=u)
