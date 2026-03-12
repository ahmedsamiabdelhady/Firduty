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

    # ── Firebase / FCM (Android + Web Push via Firebase) ──────────────────────
    # Path to your downloaded Firebase service account JSON file.
    FIREBASE_CREDENTIALS_PATH: str = os.getenv(
        "FIREBASE_CREDENTIALS_PATH", "./firebase-credentials.json"
    )

    # ── VAPID Keys (Web Push — iOS PWA + desktop browsers) ───────────────────
    # Used by pywebpush to sign web push requests.
    # Generation (run once, store the output in your env):
    #
    #   pip install py-vapid
    #   vapid --gen
    #   # Outputs vapid_private.pem and vapid_public.pem
    #
    # Or generate programmatically:
    #   from py_vapid import Vapid
    #   v = Vapid(); v.generate_keys()
    #   print("Private:", v.private_key)   # base64url
    #   print("Public:", v.public_key)     # base64url — also set in firebase_options.dart
    #
    # VAPID_PUBLIC_KEY must also be set in flutter_app/lib/firebase_options.dart
    # as kVapidPublicKey for the Flutter app to request the correct web push token.
    VAPID_PRIVATE_KEY: str = os.getenv("VAPID_PRIVATE_KEY", "")
    VAPID_PUBLIC_KEY: str  = os.getenv("VAPID_PUBLIC_KEY", "")
    # Contact email shown in VAPID claims (required by push services)
    VAPID_CONTACT_EMAIL: str = os.getenv("VAPID_CONTACT_EMAIL", "admin@yourschool.com")

    # ── Server ─────────────────────────────────────────────────────────────────
    PORT: int = int(os.getenv("PORT", "8000"))

    # ── CORS ───────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")
        if o.strip()
    ]

    # ── Scheduler ─────────────────────────────────────────────────────────────
    RUN_SCHEDULER: str = os.getenv("RUN_SCHEDULER", "true")

    # ── App ────────────────────────────────────────────────────────────────────
    TIMEZONE: str = "Asia/Muscat"
    REMINDER_MINUTES: int = 15


settings = Settings()