"""
main.py — FastAPI application entry point for Firduty.

Firebase credentials bootstrap
──────────────────────────────
Option A — File on disk  (local dev / Koyeb Secrets volume):
  Set  FIREBASE_CREDENTIALS_PATH=./firebase-credentials.json

Option B — Inline env var  (easiest on Koyeb free tier):
  Set  FIREBASE_CREDENTIALS_JSON=<entire contents of firebase-credentials.json>
  This block detects that env var, validates it, writes it to a temp file,
  and sets FIREBASE_CREDENTIALS_PATH automatically before firebase-admin loads.
"""

import json
import logging
import os
import tempfile
import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Firebase credentials bootstrap (runs before any service import) ───────────
_fcm_json_str = os.getenv("FIREBASE_CREDENTIALS_JSON")
if _fcm_json_str:
    try:
        json.loads(_fcm_json_str)
        _tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="firebase-creds-"
        )
        _tmp.write(_fcm_json_str)
        _tmp.close()
        os.environ["FIREBASE_CREDENTIALS_PATH"] = _tmp.name
        logging.getLogger(__name__).info(
            "Firebase credentials loaded from FIREBASE_CREDENTIALS_JSON env var."
        )
    except (json.JSONDecodeError, OSError) as _e:
        logging.getLogger(__name__).warning(
            f"FIREBASE_CREDENTIALS_JSON is set but could not be written: {_e}"
        )
# ─────────────────────────────────────────────────────────────────────────────

from config import settings
from database import Base, engine, SessionLocal
from routers.auth import router as auth_router, oauth2_scheme  # noqa: F401
from routers.teachers import router as teachers_router
from routers.locations import router as locations_router
from routers.shifts import router as shifts_router
from routers.weeks import router as weeks_router
from routers.points import router as points_router
from routers.reports import router as reports_router
from routers.dashboard import router as dashboard_router
from scheduler import start_scheduler, stop_scheduler
from scheduler import router as scheduler_router
from seed_data import seed_shifts, seed_locations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def bootstrap_database() -> None:
    """
    Create tables if missing, then seed required master data.
    Safe to run on every startup.
    """
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_shifts(db)
        seed_locations(db)
        db.commit()
        logger.info("Database bootstrap completed successfully.")
    except Exception:
        db.rollback()
        logger.exception("Database bootstrap failed.")
        raise
    finally:
        db.close()


bootstrap_database()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Firduty API starting up...")
    start_scheduler()
    yield
    logger.info("Firduty API shutting down...")
    stop_scheduler()


app = FastAPI(
    title="Firduty API",
    description=(
        "School Duty Roster Management System.\n\n"
        "**Authentication:** Click the 🔓 Authorize button and enter your admin "
        "username and password. All protected endpoints will then work from Swagger."
    ),
    version="2.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(teachers_router)
app.include_router(locations_router)
app.include_router(shifts_router)
app.include_router(weeks_router)
app.include_router(points_router)
app.include_router(reports_router)
app.include_router(dashboard_router)
app.include_router(scheduler_router)


@app.get("/")
def root():
    return {"service": "Firduty API", "version": "2.3.0", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)