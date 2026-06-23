import logging
import os
from logging.config import dictConfig

from app.core.config import CONFIG

COLORS = {
    "DEBUG": "\033[37m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[41m",
    "RESET": "\033[0m",
}


class ColorFormatter(logging.Formatter):
    def format(self, record):
        color = COLORS.get(record.levelname, COLORS["RESET"])
        record.levelname = f"{color}{record.levelname}{COLORS['RESET']}"
        return super().format(record)


LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> None:
    """Initialize global logging. Call once at app startup."""

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    is_production = CONFIG.APP_ENV.lower() in ("production", "prod")

    formatter_name = "plain" if is_production else "colored"

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "colored": {
                "()": ColorFormatter,
                "format": LOG_FORMAT,
                "datefmt": DATE_FORMAT,
            },
            "plain": {
                "format": LOG_FORMAT,
                "datefmt": DATE_FORMAT,
            },
        },
        "handlers": {
            "console": {
                "level": log_level,
                "formatter": formatter_name,
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["console"],
        },
        "loggers": {
            # keep uvicorn access logs at WARNING to avoid noise
            "uvicorn.access": {"level": "WARNING", "handlers": ["console"], "propagate": False},
            "uvicorn.error": {"level": log_level, "handlers": ["console"], "propagate": False},
            "httpx": {"level": "WARNING", "handlers": ["console"], "propagate": False},
            "httpcore": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        },
    }

    dictConfig(config)
