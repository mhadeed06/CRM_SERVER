"""
Strip quoted reply blocks from inbound email HTML.

Major mail clients wrap the quoted parent message in predictable container
elements. We remove those containers to forward only the new reply text
to the CRM.

SendGrid's `stripped-html` field is unreliable; doing this ourselves with
BeautifulSoup is more deterministic for the clients our patients actually use.
"""

import logging
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Selectors that wrap the entire quoted block — safe to just remove.
_CONTAINER_SELECTORS = [
    "div.gmail_quote_container",
    "div.gmail_quote",
    "div.gmail_extra",
    'blockquote[type="cite"]',
    "div.yahoo_quoted",
    "div.yahoo_quoted_legacy",
    "blockquote.protonmail_quote",
    "div.protonmail_quote",
    "blockquote.moz-cite-prefix",
    "div.moz-cite-prefix",
    "blockquote.zmail_extra_hr",
    "div.zmail_extra",
    "blockquote.gmail_quote",
]

# Selectors that mark the START of the quoted block; the element itself AND
# everything after it (siblings) must be removed. Common in Outlook variants.
_BOUNDARY_SELECTORS = [
    "div#appendonsend",
    "div#divRplyFwdMsg",
    "div.OutlookMessageHeader",
]


def strip_quoted_html(html: Optional[str]) -> Optional[str]:
    """
    Remove the quoted parent-email block from a reply's HTML body.

    Returns the cleaned HTML. On any parse error, returns the original input
    so we never break the inbound flow.
    """
    if not html:
        return html

    try:
        soup = BeautifulSoup(html, "html.parser")

        # 1. Remove "boundary" elements: the element itself AND every sibling after it.
        for selector in _BOUNDARY_SELECTORS:
            for el in soup.select(selector):
                for sib in list(el.find_next_siblings()):
                    sib.decompose()
                el.decompose()

        # 2. Outlook (new): same idea with <hr id="stopSpelling"> as boundary
        hr = soup.find("hr", id="stopSpelling")
        if hr:
            for sib in list(hr.find_next_siblings()):
                sib.decompose()
            hr.decompose()

        # 3. Remove known quote container elements (self-contained quote blocks)
        for selector in _CONTAINER_SELECTORS:
            for el in soup.select(selector):
                el.decompose()

        # 4. Outlook classic header pattern: <b>From:</b> ... — when this appears
        #    in a div/p without a containing wrapper class, trim from there.
        for b in soup.find_all(["b", "strong"]):
            txt = (b.get_text() or "").strip().lower()
            if txt.startswith("from:"):
                ancestor = b.find_parent(["div", "p", "table"])
                if ancestor:
                    for sib in list(ancestor.find_next_siblings()):
                        sib.decompose()
                    ancestor.decompose()
                    break

        # 5. Generic top-level <blockquote> with quote-like styling as last resort
        for bq in soup.find_all("blockquote"):
            classes = bq.get("class") or []
            style = (bq.get("style") or "").lower()
            if (
                "gmail_quote" in classes
                or "border-left" in style
                or bq.get("type") == "cite"
            ):
                bq.decompose()

        return str(soup)

    except Exception as e:
        # Never break the pipeline on a parse error — fall back to the raw html.
        logger.warning("html_quote_strip failed error=%r len=%d", e, len(html))
        return html
