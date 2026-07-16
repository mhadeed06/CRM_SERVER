import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "local")

    # === AWS SES (outbound email + events via SNS) ===
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    AWS_SES_FROM_EMAIL: str = os.getenv("AWS_SES_FROM_EMAIL", "")
    AWS_SES_FROM_NAME: str = os.getenv("AWS_SES_FROM_NAME", "")
    AWS_SES_REPLY_TO_EMAIL: str = os.getenv("AWS_SES_REPLY_TO_EMAIL", "")
    # Optional — name of the SES configuration set that publishes events to SNS.
    # If empty, events won't be published (fine for send-only testing).
    AWS_SES_CONFIGURATION_SET: str = os.getenv("AWS_SES_CONFIGURATION_SET", "")

    # S3 location where SES stores raw inbound emails (SES receipt rule action).
    # The inbound webhook fetches the raw MIME from here using mail.messageId
    # from the SNS notification.
    AWS_SES_INBOUND_BUCKET: str = os.getenv("AWS_SES_INBOUND_BUCKET", "")
    AWS_SES_INBOUND_PREFIX: str = os.getenv("AWS_SES_INBOUND_PREFIX", "")

    # Dedicated IAM user for reading raw inbound emails from the S3 bucket.
    # Separate from the SES-send credentials for least-privilege security.
    # If unset, the S3 client falls back to AWS_ACCESS_KEY_ID / SECRET_ACCESS_KEY.
    AWS_S3_ACCESS_KEY_ID: str = os.getenv("AWS_S3_ACCESS_KEY_ID", "")
    AWS_S3_SECRET_ACCESS_KEY: str = os.getenv("AWS_S3_SECRET_ACCESS_KEY", "")

    # === Telnyx (SMS — legacy, still present) ===
    TELNYX_API_KEY: str = os.getenv("TELNYX_API_KEY", "")
    TELNYX_FROM_NUMBER: str = os.getenv("TELNYX_FROM_NUMBER", "")

    # Public base URL for click-tracking redirect
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "")

    # === CRM downstream ===
    CRM_BASE_URL: str = os.getenv("CRM_BASE_URL", "")
    CRM_EVENT_ENDPOINT: str = os.getenv("CRM_EVENT_ENDPOINT", "")
    CRM_INBOUND_ENDPOINT: str = os.getenv("CRM_INBOUND_ENDPOINT", "")

    # Auth service — for fetching dynamic bearer token
    AUTH_URL: str = os.getenv("AUTH_URL", "")
    AUTH_EMAIL: str = os.getenv("AUTH_EMAIL", "")
    AUTH_PASSWORD: str = os.getenv("AUTH_PASSWORD", "")

    # Shared HS256 secret with PracticeEHR .NET CRM backend for JWT verification
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")

    # Comma-separated list of origins allowed to call the API from a browser.
    CORS_ALLOWED_ORIGINS: str = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    )


CONFIG = Settings()
