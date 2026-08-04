"""
Recipient email → mail provider name.

Two-tier lookup:
  1. Fast-path: public mailbox providers by domain (gmail.com, outlook.com…)
  2. Fallback: MX DNS lookup for custom domains (e.g. mhadeed@practiceehr.com
     whose MX record points to Microsoft 365). We match the MX hostname
     against known provider suffixes to say "outlook", "gmail", etc.

Falls back to "other" when the domain has MX records we don't recognize
(usually a niche provider or a self-hosted server), and "unknown" when the
email is malformed or DNS resolution fails.

MX results are memoized in-process (LRU) so we don't hit DNS on every event.
Cache is unbounded in time — a domain's mail provider rarely changes.
"""

import logging
from functools import lru_cache
from typing import Optional

from dns import resolver
from dns.exception import DNSException

logger = logging.getLogger(__name__)


# ── Fast-path: recipient email domain → provider label ────────────────────
_PUBLIC_DOMAIN_MAP = {
    "gmail.com": "gmail",
    "googlemail.com": "gmail",
    "outlook.com": "outlook",
    "hotmail.com": "outlook",
    "live.com": "outlook",
    "msn.com": "outlook",
    "yahoo.com": "yahoo",
    "ymail.com": "yahoo",
    "rocketmail.com": "yahoo",
    "icloud.com": "apple",
    "me.com": "apple",
    "mac.com": "apple",
    "aol.com": "aol",
    "protonmail.com": "protonmail",
    "proton.me": "protonmail",
    "zoho.com": "zoho",
    "gmx.com": "gmx",
    "gmx.net": "gmx",
}


# ── Fallback: MX hostname substring → provider label ──────────────────────
# Order matters — first match wins. Substring match is deliberately lenient
# because MX hosts vary across regions/plans.
_MX_HOST_RULES: list[tuple[list[str], str]] = [
    (["protection.outlook.com", "olc.protection.outlook.com"], "outlook"),
    (["mail.eo.outlook.com"], "outlook"),
    (["googlemail.com", "aspmx.l.google.com", "aspmx"], "gmail"),
    (["google.com"], "gmail"),
    (["yahoodns.net", "yahoo.com"], "yahoo"),
    (["icloud.com", "apple.com"], "apple"),
    (["zoho.com", "zohomail.com"], "zoho"),
    (["protonmail.ch", "proton.me"], "protonmail"),
    (["pphosted.com", "proofpoint.com"], "proofpoint"),
    (["mimecast.com"], "mimecast"),
    (["barracuda"], "barracuda"),
    (["messagelabs.com"], "symantec"),
    (["fastmail.com"], "fastmail"),
]


_MX_TIMEOUT_SEC = 3.0


def get_email_provider(email: Optional[str]) -> str:
    """
    Best-effort mapping of an email address to its mail provider.

    Returns lowercase strings like "gmail", "outlook", "yahoo", "apple",
    "other" (has mail service but unknown provider), or "unknown"
    (malformed email or DNS failure).
    """
    if not email or "@" not in email:
        return "unknown"

    domain = email.rsplit("@", 1)[1].lower().strip()
    if not domain:
        return "unknown"

    # Fast path: public consumer providers
    if domain in _PUBLIC_DOMAIN_MAP:
        return _PUBLIC_DOMAIN_MAP[domain]

    # Custom domain — inspect MX records
    return _provider_from_mx(domain)


@lru_cache(maxsize=10_000)
def _provider_from_mx(domain: str) -> str:
    """
    Resolve MX for `domain` and return a provider label. Cached — subsequent
    calls for the same domain are instant.
    """
    try:
        answers = resolver.resolve(domain, "MX", lifetime=_MX_TIMEOUT_SEC)
    except DNSException as e:
        logger.info("mx_lookup_failed domain=%s error=%r", domain, type(e).__name__)
        return "unknown"
    except Exception as e:
        logger.warning("mx_lookup_error domain=%s error=%r", domain, e)
        return "unknown"

    # Sort by MX priority (lowest = primary)
    sorted_mx = sorted(answers, key=lambda r: r.preference)
    for record in sorted_mx:
        host = str(record.exchange).lower().rstrip(".")
        for host_patterns, provider in _MX_HOST_RULES:
            if any(pattern in host for pattern in host_patterns):
                return provider

    # MX records exist but none matched our known patterns → real mail service
    # but we don't recognize the provider.
    return "other"
