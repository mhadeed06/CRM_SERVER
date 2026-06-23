import asyncio
import logging
import re
import time
from datetime import datetime, timezone

import httpx

from app.core.config import CONFIG

logger = logging.getLogger(__name__)

# ── Token cache ──────────────────────────────────────────
_cached_token: str | None = None
_token_expiry: datetime | None = None
_token_lock = asyncio.Lock()

REFRESH_BUFFER_SECONDS = 300  # refresh 5 minutes before actual expiry


def _parse_iso_datetime(s: str) -> datetime:
    """
    Parse ISO datetime, tolerating >6-digit fractional seconds (which
    Python's datetime.fromisoformat doesn't accept until 3.11).
    e.g. '2026-04-22T15:30:04.9415052+00:00' -> truncated to 6 digits.
    """
    # Truncate fractional seconds to 6 digits if longer
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


async def get_auth_token() -> str | None:
    """
    Returns a valid bearer token, re-authenticating only when needed.

    - First call: authenticates and caches the token.
    - Subsequent calls: returns cached token if not expired.
    - If expired: re-authenticates (one call at a time via lock).
    """
    global _cached_token, _token_expiry

    # fast path — token is cached and still valid
    if _cached_token and _token_expiry:
        now = datetime.now(timezone.utc)
        if now.timestamp() < _token_expiry.timestamp() - REFRESH_BUFFER_SECONDS:
            return _cached_token

    # slow path — need to authenticate (only one coroutine does this at a time)
    async with _token_lock:
        # double-check after acquiring lock (another coroutine may have refreshed)
        if _cached_token and _token_expiry:
            now = datetime.now(timezone.utc)
            if now.timestamp() < _token_expiry.timestamp() - REFRESH_BUFFER_SECONDS:
                return _cached_token

        return await _authenticate()


async def _authenticate() -> str | None:
    """Call the auth API and cache the token."""
    global _cached_token, _token_expiry

    if not CONFIG.AUTH_URL or not CONFIG.AUTH_EMAIL or not CONFIG.AUTH_PASSWORD:
        logger.error("auth not_configured — AUTH_URL, AUTH_EMAIL, or AUTH_PASSWORD missing")
        return None

    body = {
        "EMAIL": CONFIG.AUTH_EMAIL,
        "PASSWORD": CONFIG.AUTH_PASSWORD,
    }

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                CONFIG.AUTH_URL,
                json=body,
                headers={"Content-Type": "application/json"},
            )
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error("auth request_exception duration_ms=%d error=%r", duration_ms, e)
        return None

    duration_ms = int((time.perf_counter() - start) * 1000)

    if resp.status_code != 200:
        logger.error(
            "auth failed status=%s duration_ms=%d body=%s",
            resp.status_code, duration_ms, resp.text[:500],
        )
        return None

    try:
        data = resp.json()
        token = data["data"]["token"]
        expiry_str = data["data"]["expiryDate"]
        _token_expiry = _parse_iso_datetime(expiry_str)
        _cached_token = token
    except Exception as e:
        logger.error("auth parse_error duration_ms=%d error=%r body=%s", duration_ms, e, resp.text[:500])
        return None

    logger.info(
        "auth ok duration_ms=%d expires=%s",
        duration_ms, _token_expiry.isoformat(),
    )
    return _cached_token
