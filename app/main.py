from fastapi import FastAPI

from app.api.v1.routes.email import router as email_router
from app.api.v1.routes.webhooks_sendgrid import router as sendgrid_webhook_router
from app.api.v1.routes.sms import router as sms_router
from app.api.v1.routes.webhooks_telnyx import router as telnyx_webhook_router
from app.api.v1.routes.redirect import router as redirect_router

app = FastAPI(title="Comms Service ")

# Email APIs + Webhooks
app.include_router(email_router, prefix="/api/v1")
app.include_router(sendgrid_webhook_router, prefix="/api/v1")

# SMS APIs + Webhooks + Click tracking redirect
app.include_router(sms_router, prefix="/api/v1")
app.include_router(telnyx_webhook_router, prefix="/api/v1")
app.include_router(redirect_router, prefix="/api/v1")


@app.get("/")
def health():
    return {"status": "ok"}
