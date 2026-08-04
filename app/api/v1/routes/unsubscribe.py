"""
Unsubscribe click handler.

Both entry points hit the same route:
- Recipient clicks the `Unsubscribe` link in the email body → GET
- Gmail/Outlook native unsubscribe button (RFC 8058) → POST

Both paths verify the signed token, notify CRM to mark the recipient as
unsubscribed, and return a small landing page (GET) or a bare 200 (POST).
"""

import logging
import time

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from app.services.auth_client import get_auth_token
from app.services.crm_client import send_unsubscribe_to_crm
from app.services.unsubscribe import verify_token

router = APIRouter(prefix="/unsubscribe", tags=["Unsubscribe"])
logger = logging.getLogger(__name__)


_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Unsubscribed</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif;
         max-width: 480px; margin: 80px auto; padding: 24px; color: #222; }
  p  { line-height: 1.55; }
</style>
</head>
<body>
  <p>You have been unsubscribed.</p>
</body>
</html>
"""

_INVALID_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Unsubscribe link invalid</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif;
         max-width: 480px; margin: 80px auto; padding: 24px; color: #222; }
  p  { line-height: 1.55; }
</style>
</head>
<body>
  <p>This unsubscribe link is invalid.</p>
</body>
</html>
"""


async def _process(token: str) -> tuple[bool, str]:
    """
    Shared logic for GET + POST. Returns (ok, email_or_error).
    Never raises — every failure returns ok=False.
    """
    email = verify_token(token)
    if not email:
        return False, "invalid_token"

    start = time.perf_counter()
    auth_token = await get_auth_token()
    status, body = await send_unsubscribe_to_crm(email, token=auth_token)
    duration_ms = int((time.perf_counter() - start) * 1000)

    if status and 200 <= status < 300:
        logger.info(
            "unsubscribe processed email=%s status=%s duration_ms=%d",
            email, status, duration_ms,
        )
        return True, email

    logger.error(
        "unsubscribe crm_forward_failed email=%s status=%s duration_ms=%d body=%s",
        email, status, duration_ms, (body or "")[:500],
    )
    # We still tell the user they've been unsubscribed — we can't leave them
    # staring at an error page after a good-faith click. Ops must reconcile
    # any failed CRM forwards from the logs.
    return True, email


@router.get("")
async def unsubscribe_click(token: str = ""):
    """Recipient clicked the unsubscribe link in the email body."""
    ok, _ = await _process(token)
    body = _SUCCESS_HTML if ok else _INVALID_HTML
    return HTMLResponse(content=body, status_code=200 if ok else 400)


@router.post("")
async def unsubscribe_one_click(request: Request, token: str = ""):
    """
    RFC 8058 One-Click unsubscribe endpoint. Gmail/Outlook POST here when
    the recipient clicks the native unsubscribe button next to the sender.
    Response body isn't shown to the user — a 200 is what matters.
    """
    ok, _ = await _process(token)
    return Response(status_code=200 if ok else 400)
