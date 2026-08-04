"""
User-Agent → device category.

Categorizes SES open/click event user-agent strings into one of four buckets
so CRM can group engagement stats without parsing raw UAs. Uses the ua-parser
project via the `user-agents` wrapper — same library used by Django,
Wikipedia, and countless other production systems.

Caveats (industry-wide, not our bug):
- Apple Mail Privacy Protection pre-fetches the tracking pixel from Apple's
  servers, hiding the real device. UAs from Apple's proxy will show up as
  Apple Mail on Safari (`desktop`) regardless of the recipient's actual device.
- Corporate security scanners (Mimecast, Proofpoint, etc.) auto-fetch open
  pixels — they show as browsers even though no human clicked.
- Older webmail clients (Outlook web, iCloud web) look like the browser they
  run in, so the "client" isn't reliably identifiable — only the device.
"""

import logging
from typing import Optional

from user_agents import parse

logger = logging.getLogger(__name__)


def detect_device_type(user_agent: Optional[str]) -> str:
    """
    Return one of: 'phone', 'tablet', 'desktop', 'unknown'.

    Never raises — falls back to 'unknown' on any parse error.
    """
    if not user_agent:
        return "unknown"

    try:
        ua = parse(user_agent)
    except Exception as e:  # ua-parser is defensive but never trust third-party libs
        logger.warning("device_parse_failed error=%r ua=%r", e, user_agent[:200])
        return "unknown"

    if ua.is_mobile:
        return "phone"
    if ua.is_tablet:
        return "tablet"
    if ua.is_pc:
        return "desktop"
    return "unknown"
