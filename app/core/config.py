import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "local")
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    SENDGRID_FROM_EMAIL: str = os.getenv("SENDGRID_FROM_EMAIL", "")
    TELNYX_API_KEY: str = os.getenv("TELNYX_API_KEY", "")
    TELNYX_FROM_NUMBER: str = os.getenv("TELNYX_FROM_NUMBER", "")
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "")
    CRM_BASE_URL: str = os.getenv("CRM_BASE_URL", "")
    CRM_EVENT_ENDPOINT: str = os.getenv("CRM_EVENT_ENDPOINT", "")
    CRM_INBOUND_ENDPOINT: str = os.getenv("CRM_INBOUND_ENDPOINT", "")
    SENDGRID_REPLY_TO_EMAIL: str = os.getenv("SENDGRID_REPLY_TO_EMAIL", "")

    # Auth service — for fetching dynamic bearer token
    AUTH_URL: str = os.getenv("AUTH_URL", "")
    AUTH_EMAIL: str = os.getenv("AUTH_EMAIL", "")
    AUTH_PASSWORD: str = os.getenv("AUTH_PASSWORD", "")

    # Shared HS256 secret with PracticeEHR .NET CRM backend for JWT verification
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")

    # Comma-separated list of origins allowed to call the API from a browser.
    # Default covers common local dev ports; add prod origins via App Service env.
    CORS_ALLOWED_ORIGINS: str = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    )


CONFIG = Settings()

