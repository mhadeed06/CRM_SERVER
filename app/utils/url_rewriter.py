import re
from urllib.parse import quote_plus
from ..core.config import settings

URL_RE = re.compile(r"(https?://[^\s]+)")

def rewrite_first_url(text: str, tracking_id: str) -> str:
    """
    Rewrites the first URL found in 'text' into a tracked URL:
    {PUBLIC_BASE_URL}/api/v1/r/{tracking_id}?u=<encoded_original_url>
    """
    m = URL_RE.search(text)
    if not m:
        return text

    if not settings.PUBLIC_BASE_URL:
        raise RuntimeError("PUBLIC_BASE_URL is missing (needed for click tracking)")

    original_url = m.group(1)
    encoded = quote_plus(original_url)

    tracked_url = f"{settings.PUBLIC_BASE_URL}/api/v1/r/{tracking_id}?u={encoded}"

    return text.replace(original_url, tracked_url, 1)
