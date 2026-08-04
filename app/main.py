import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import CONFIG
from app.core.logging_config import setup_logging

setup_logging()
from app.api.v1.routes.email import router as email_router
from app.api.v1.routes.webhooks_ses import router as ses_webhook_router
from app.api.v1.routes.sms import router as sms_router
from app.api.v1.routes.webhooks_telnyx import router as telnyx_webhook_router
from app.api.v1.routes.redirect import router as redirect_router
from app.api.v1.routes.unsubscribe import router as unsubscribe_router

app = FastAPI(title="Comms Service ")

# CORS — browsers blocking calls from the CRM frontend
# are unblocked by listing their origin in CORS_ALLOWED_ORIGINS env var.
_allowed_origins = [
    o.strip() for o in CONFIG.CORS_ALLOWED_ORIGINS.split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Email APIs + Webhooks
app.include_router(email_router, prefix="/api/v1")
app.include_router(ses_webhook_router, prefix="/api/v1")
app.include_router(unsubscribe_router, prefix="/api/v1")

# SMS APIs + Webhooks + Click tracking redirect
app.include_router(sms_router, prefix="/api/v1")
app.include_router(telnyx_webhook_router, prefix="/api/v1")
app.include_router(redirect_router, prefix="/api/v1")


APP_VERSION = os.getenv("APP_VERSION", "unknown")


@app.get("/")
def health():
    return {"status": "ok", "version": APP_VERSION}
