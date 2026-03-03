import logging
import httpx
from app.core.config import CONFIG

logger = logging.getLogger("crm_client")

# Common headers using your env token
COMMON_HEADERS = {
    "Authorization": f"Bearer {CONFIG.CRM_TOKEN}",
    "Content-Type": "application/json",
}


async def send_email_event_to_crm(event_payload: dict) -> tuple[int | None, str]:
    """
    Sends outbound SendGrid event (delivered/open/click/etc.) to CRM.
    Body format required by CRM:
    {
        "emailEvent": { ... }
    }
    """
    if not CONFIG.CRM_BASE_URL or not CONFIG.CRM_EVENT_ENDPOINT:
        logger.error("❌ CRM endpoints not configured")
        return None, "CRM URL not configured"

    url = CONFIG.CRM_BASE_URL + CONFIG.CRM_EVENT_ENDPOINT
    body = {"emailEvent": event_payload}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=body, headers=COMMON_HEADERS)

        logger.info("CRM EVENT -> %s | %s", resp.status_code, resp.text)
        return resp.status_code, resp.text

    except Exception as e:
        logger.error(
            "❌ CRM EVENT ERROR: url=%s body=%s error=%r",
            url,
            body,
            e,
        )
        return None, str(e)


async def send_inbound_email_to_crm(email_payload: dict) -> tuple[int | None, str]:
    """
    Sends inbound email (reply) to CRM.
    Body format required by CRM:
    {
        "email": { ... }
    }
    """
    if not CONFIG.CRM_BASE_URL or not CONFIG.CRM_INBOUND_ENDPOINT:
        logger.error("❌ CRM inbound endpoint not configured")
        return None, "CRM inbound URL not configured"

    url = CONFIG.CRM_BASE_URL + CONFIG.CRM_INBOUND_ENDPOINT
    body = {"email": email_payload}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=body, headers=COMMON_HEADERS)

        logger.info("CRM INBOUND -> %s | %s", resp.status_code, resp.text)
        return resp.status_code, resp.text

    except Exception as e:
        logger.error(
            "❌ CRM INBOUND ERROR: url=%s body=%s error=%r",
            url,
            body,
            e,
        )
        return None, str(e)