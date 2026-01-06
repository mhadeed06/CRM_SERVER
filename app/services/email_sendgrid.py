# import uuid
# from sendgrid import SendGridAPIClient
# from ..core.config import settings

# def send_email(to_email: str, subject: str, html: str) -> str:
#     if not settings.SENDGRID_API_KEY:
#         raise RuntimeError("SENDGRID_API_KEY is missing")
#     if not settings.SENDGRID_FROM_EMAIL:
#         raise RuntimeError("SENDGRID_FROM_EMAIL is missing")

#     internal_message_id = str(uuid.uuid4())

#     # ✅ Raw JSON payload (SendGrid v3 Mail Send format)
#     payload = {
#         "from": {"email": settings.SENDGRID_FROM_EMAIL},
#         "personalizations": [
#             {
#                 "to": [{"email": to_email}],
#                 "subject": subject,
#                 "custom_args": {  # ✅ this will return in webhook events
#                     "message_id": internal_message_id
#                 },
#             }
#         ],
#         "content": [{"type": "text/html", "value": html}],
#     }

#     sg = SendGridAPIClient(settings.SENDGRID_API_KEY)

#     # ✅ Use low-level client so no helper-library weirdness
#     response = sg.client.mail.send.post(request_body=payload)

#     # 202 = accepted (normal for SendGrid)
#     if response.status_code not in (200, 202):
#         raise RuntimeError(f"SendGrid error: {response.status_code} {response.body}")

#     return internal_message_id




import uuid
from typing import List, Dict, Tuple, Optional
from sendgrid import SendGridAPIClient
from ..core.config import settings

def send_email_bulk(
    recipients: List[Dict[str, Optional[str]]],
    subject: str,
    html: str,
) -> List[Tuple[str, str]]:
    """
    recipients: [{ "email": "...", "tracking_id": "..." }, ...]
    returns: [(email, tracking_id), ...]
    """

    if not settings.SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY is missing")
    if not settings.SENDGRID_FROM_EMAIL:
        raise RuntimeError("SENDGRID_FROM_EMAIL is missing")

    personalizations = []
    results = []

    for r in recipients:
        email = r["email"]
        tracking_id = r.get("tracking_id")
        if not tracking_id:
            raise ValueError("tracking_id is required for every recipient")



        personalizations.append({
            "to": [{"email": email}],
            "subject": subject,
            "custom_args": {  # ✅ key part for webhook correlation
                "tracking_id": tracking_id
            }
        })

        results.append((email, tracking_id))

    payload = {
        "from": {"email": settings.SENDGRID_FROM_EMAIL},
        "personalizations": personalizations,
        "content": [{"type": "text/html", "value": html}],
    }

    sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
    resp = sg.client.mail.send.post(request_body=payload)

    if resp.status_code not in (200, 202):
        raise RuntimeError(f"SendGrid error: {resp.status_code} {resp.body}")

    return results
