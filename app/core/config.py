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
    CRM_TOKEN: str = os.getenv("CRM_TOKEN", "")
    SENDGRID_REPLY_TO_EMAIL: str = os.getenv("SENDGRID_REPLY_TO_EMAIL", "")


CONFIG = Settings()

