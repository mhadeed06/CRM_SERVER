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


config = Settings()

