"""
config.py — Application configuration.

All values are read from environment variables.
For local development, copy .env.example to .env and fill in the values.

IMPORTANT: No validation runs at import time.
All required-field checking happens inside Settings.__init__() so that
the process can start, configure logging, and print a clear error message
before exiting — rather than crashing silently before any log output.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Settings:
    def __init__(self) -> None:
        # ── Database ──────────────────────────────────────────────────────────
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "")
        if not self.DATABASE_URL:
            # Log the error THEN raise — so the message appears in Koyeb logs
            # before the process exits.
            logger.critical(
                "FATAL: DATABASE_URL environment variable is not set. "
                "Add it in Koyeb → Service → Environment variables."
            )
            raise SystemExit(
                "DATABASE_URL is required. "
                "Set it in Koyeb environment variables and redeploy."
            )

        # ── Auth ──────────────────────────────────────────────────────────────
        self.SECRET_KEY: str = os.getenv(
            "SECRET_KEY", "dev-secret-key-change-in-production"
        )
        self.ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
        )

        # ── Admin credentials ─────────────────────────────────────────────────
        self.ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
        self.ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")

        # ── Firebase / FCM ────────────────────────────────────────────────────
        self.FIREBASE_CREDENTIALS_PATH: str = os.getenv(
            "FIREBASE_CREDENTIALS_PATH", "./firebase-credentials.json"
        )

        # ── VAPID (Web Push) ──────────────────────────────────────────────────
        self.VAPID_PRIVATE_KEY: str = os.getenv("VAPID_PRIVATE_KEY", "")
        self.VAPID_PUBLIC_KEY: str  = os.getenv("VAPID_PUBLIC_KEY", "")
        self.VAPID_CONTACT_EMAIL: str = os.getenv(
            "VAPID_CONTACT_EMAIL", "admin@yourschool.com"
        )

        # ── Server ────────────────────────────────────────────────────────────
        self.PORT: int = int(os.getenv("PORT", "8000"))

        # ── CORS ──────────────────────────────────────────────────────────────
        self.ALLOWED_ORIGINS: list[str] = [
            o.strip()
            for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")
            if o.strip()
        ]

        # ── Scheduler ─────────────────────────────────────────────────────────
        self.RUN_SCHEDULER: str = os.getenv("RUN_SCHEDULER", "true")

        # ── App constants ─────────────────────────────────────────────────────
        self.TIMEZONE: str = "Asia/Muscat"
        self.REMINDER_MINUTES: int = 15


settings = Settings()
