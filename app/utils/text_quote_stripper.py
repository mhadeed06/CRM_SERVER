"""
Strip the quoted parent block from a plain-text email reply.

Unlike HTML, plain text has no structural markers we can decompose. We rely on
common client-generated boundary strings and truncate everything from the first
strong match onwards.

Covers the common patterns:
- Outlook — a line of underscores (usually 32) followed by a From:/Sent:/To: block
- Outlook (older) — "-----Original Message-----"
- Gmail / Apple Mail — "On [date], [name] wrote:"
- Same idea in non-English clients (Spanish "escribió", French "a écrit", German "schrieb")

On any parse error we return the original text so the inbound flow never breaks.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# Patterns whose FIRST occurrence marks the start of the quoted parent.
# The line matching the pattern AND everything after it are stripped.
_QUOTE_MARKERS = [
    # Outlook (all versions): line of 20+ underscores as separator
    re.compile(r"^_{20,}\s*$", re.MULTILINE),
    # Outlook older: -----Original Message-----
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}\s*$", re.MULTILINE | re.IGNORECASE),
    # Outlook forwarded header — From:  followed by Sent: on the next line
    re.compile(r"^From:\s+.+\r?\n\s*Sent:\s+", re.MULTILINE),
    # Gmail / Apple Mail — "On <date>, <name> wrote:"
    re.compile(r"^On\s+.{0,200}wrote:\s*$", re.MULTILINE),
    # Non-English variants
    re.compile(r"^El\s+.{0,200}escribió:\s*$", re.MULTILINE),        # Spanish
    re.compile(r"^Le\s+.{0,200}a écrit\s*:\s*$", re.MULTILINE),       # French
    re.compile(r"^Am\s+.{0,200}schrieb\s+.{0,200}:\s*$", re.MULTILINE),  # German
]


def strip_quoted_text(text: Optional[str]) -> Optional[str]:
    """
    Remove the quoted parent from a plain-text reply body.

    Returns the cleaned text. On any error (or None input), returns the input
    unchanged so the inbound flow is never broken.
    """
    if not text:
        return text

    try:
        earliest = len(text)
        for pattern in _QUOTE_MARKERS:
            m = pattern.search(text)
            if m and m.start() < earliest:
                earliest = m.start()

        if earliest < len(text):
            return text[:earliest].rstrip()
        return text

    except Exception as e:
        logger.warning("text_quote_strip failed error=%r len=%d", e, len(text))
        return text
