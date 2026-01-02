from fastapi import FastAPI
from .api.v1.routes.email import router as email_router
from .api.v1.routes.webhooks_sendgrid import router as sendgrid_webhook_router

app = FastAPI(title="Comms Service (Demo)")

app.include_router(email_router, prefix="/api/v1")
app.include_router(sendgrid_webhook_router, prefix="/api/v1")

@app.get("/")
def health():
    return {"status": "ok"}
