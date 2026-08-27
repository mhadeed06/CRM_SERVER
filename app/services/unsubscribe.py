"""
Unsubscribe support.

Generates signed HMAC tokens embedded in outbound-email unsubscribe URLs,
verifies them on click, and replaces the `{{UNSUBSCRIBE_URL}}` placeholder
in HTML sent by CRM with the recipient-specific signed URL.

Design notes:
- Kept isolated in its own module so the outbound send flow stays untouched
  when no placeholder is present.
- Uses a dedicated secret (UNSUBSCRIBE_SECRET_KEY) — never mixed with the
  general JWT auth secret.
- Tokens carry the recipient email plus an issued-at timestamp; no explicit
  expiry (unsubscribe should still work if a recipient rediscovers an old
  email months later).
"""

import logging
from typing import Optional

import jwt

from app.core.config import CONFIG

logger = logging.getLogger(__name__)


PLACEHOLDER = "{{UNSUBSCRIBE_URL}}"
_ROUTE_PATH = "/api/v1/unsubscribe"
_TOKEN_TYPE = "unsub"
_TOKEN_ALGO = "HS256"


def _secret() -> str:
    return CONFIG.UNSUBSCRIBE_SECRET_KEY


def _base_url() -> str:
    """Base URL for building outbound unsubscribe links. Trailing slash tolerated."""
    return (CONFIG.PUBLIC_BASE_URL or "").rstrip("/")


def is_configured() -> bool:
    """True when both the signing secret and a base URL are available."""
    return bool(_secret()) and bool(_base_url())


def make_token(
    email: str,
    entity_id: Optional[str] = None,
    thread_id: Optional[int] = None,
) -> Optional[str]:
    """
    Create a signed token that identifies the unsubscribing recipient.
    `entity_id` (CRM tenant/practice id) and `thread_id` (CRM thread id) are
    optional — included in the JWT payload when provided so they can be
    echoed back to CRM on click.
    """
    if not is_configured() or not email:
        return None
    payload = {"email": email, "typ": _TOKEN_TYPE}
    if entity_id:
        payload["entity_id"] = str(entity_id)
    if thread_id is not None:
        payload["thread_id"] = int(thread_id)
    return jwt.encode(payload, _secret(), algorithm=_TOKEN_ALGO)


def verify_token(token: str) -> Optional[dict]:
    """
    Verify an unsubscribe token. Returns
    {'email': ..., 'entity_id': ..., 'thread_id': ...} (entity_id/thread_id
    may be None if the token was minted without them) or None on any failure.
    Never raises.
    """
    if not token or not _secret():
        return None
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_TOKEN_ALGO])
    except jwt.PyJWTError as e:
        logger.info("unsub_token_invalid error=%r", e)
        return None
    if payload.get("typ") != _TOKEN_TYPE:
        return None
    email = payload.get("email")
    if not isinstance(email, str) or not email:
        return None
    entity_id = payload.get("entity_id")
    thread_id_raw = payload.get("thread_id")
    try:
        thread_id = int(thread_id_raw) if thread_id_raw is not None else None
    except (TypeError, ValueError):
        thread_id = None
    return {
        "email": email,
        "entity_id": str(entity_id) if entity_id else None,
        "thread_id": thread_id,
    }


def build_url(
    email: str,
    entity_id: Optional[str] = None,
    thread_id: Optional[int] = None,
) -> Optional[str]:
    """Full unsubscribe URL for an email address, or None if not configured."""
    token = make_token(email, entity_id=entity_id, thread_id=thread_id)
    if not token:
        return None
    return f"{_base_url()}{_ROUTE_PATH}?token={token}"


def inject_into_html(
    html: Optional[str],
    recipient_email: str,
    entity_id: Optional[str] = None,
    thread_id: Optional[int] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    Look for `{{UNSUBSCRIBE_URL}}` in the HTML and replace it with a signed
    URL for this recipient. Returns (possibly-modified html, unsubscribe url).

    - Returns (html, None) unchanged if the placeholder is absent OR the
      service isn't configured for unsubscribe.
    - The returned URL is also what should be set as the `List-Unsubscribe`
      header so both the in-body link and Gmail's native one-click button
      resolve to the same endpoint.
    """
    if not html or PLACEHOLDER not in html:
        return html, None

    url = build_url(recipient_email, entity_id=entity_id, thread_id=thread_id)
    if not url:
        logger.warning(
            "unsubscribe_placeholder_present_but_not_configured to=%s",
            recipient_email,
        )
        return html, None

    return html.replace(PLACEHOLDER, url), url
