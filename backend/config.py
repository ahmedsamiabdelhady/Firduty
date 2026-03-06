"""
config.py — Application configuration.

All values are read from environment variables.
For local development, values can be set in a .env file (loaded by python-dotenv).
In production (Koyeb), set these as platform environment variables.
"""

import os
from dotenv import load_dotenv

# Load .env file for local development only.
# In production (Koyeb) env vars are injected directly — load_dotenv() is a no-op.
load_dotenv()


class Settings:
    # ── Database ───────────────────────────────────────────────────────────────
    # Full PostgreSQL connection string.
    # Supabase example:
    #   postgresql://postgres:PASSWORD@db.xxxx.supabase.co:5432/postgres
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./firduty.db"   # Safe local fallback — never used in production
    )

    # ── JWT ────────────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

    # ── Admin Credentials ──────────────────────────────────────────────────────
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")

    # ── Firebase ───────────────────────────────────────────────────────────────
    FIREBASE_CREDENTIALS_PATH: str = os.getenv(
        "FIREBASE_CREDENTIALS_PATH", "./firebase-credentials.json"
    )

    # ── Server ─────────────────────────────────────────────────────────────────
    # PORT is injected automatically by Koyeb. Default to 8000 for local dev.
    PORT: int = int(os.getenv("PORT", "8000"))

    # ── CORS ───────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins.
    # Example: https://admin.yourschool.com,https://yourschool.com
    # Defaults to "*" for local dev. Always set this explicitly in production.
    ALLOWED_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")
        if o.strip()
    ]

    # ── Scheduler ─────────────────────────────────────────────────────────────
    # Set RUN_SCHEDULER=false to disable the background scheduler on a specific
    # instance (e.g. worker-only replicas). Default: "true" → starts on boot.
    RUN_SCHEDULER: str = os.getenv("RUN_SCHEDULER", "true")

    # ── App ────────────────────────────────────────────────────────────────────
    TIMEZONE: str = "Asia/Muscat"
    REMINDER_MINUTES: int = 15


settings = Settings()