"""
main.py — FastAPI application entry point for Firduty.

── Startup order (critical for Koyeb) ──────────────────────────────────────────
1. logging.basicConfig()          ← FIRST — so every crash is visible in logs
2. Firebase credential bootstrap  ← must run before firebase-admin is imported
3. All other imports              ← config / database / routers
4. lifespan():
     a. threading.Thread(_run_bootstrap).start()  ← background, non-blocking
     b. start_scheduler()
     c. yield  ← /health responds 200 immediately; Koyeb marks deployment healthy

The old pattern ran bootstrap_database() synchronously before yield, which blocked
the ASGI server from accepting connections. Koyeb's health check timed out and the
deployment stayed "Starting" for up to an hour with empty logs.

── Firebase credentials ────────────────────────────────────────────────────────
Option A  FIREBASE_CREDENTIALS_PATH=./firebase-credentials.json
Option B  FIREBASE_CREDENTIALS_JSON=<entire JSON as a single string>
"""

# ── Step 1: configure logging FIRST ──────────────────────────────────────────
# This must be the very first executable line so that any subsequent import
# crash is captured and visible in Koyeb logs instead of producing empty logs.
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
logger.info("Firduty main.py loading — logging configured.")

# ── Step 2: Firebase credential bootstrap ────────────────────────────────────
# Must happen before any import that touches firebase-admin.
import json
import tempfile

_fcm_json_str = os.getenv("FIREBASE_CREDENTIALS_JSON")
if _fcm_json_str:
    try:
        json.loads(_fcm_json_str)   # validate JSON before writing
        _tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="firebase-creds-"
        )
        _tmp.write(_fcm_json_str)
        _tmp.close()
        os.environ["FIREBASE_CREDENTIALS_PATH"] = _tmp.name
        logger.info("Firebase credentials written from FIREBASE_CREDENTIALS_JSON.")
    except (json.JSONDecodeError, OSError) as _e:
        logger.warning("FIREBASE_CREDENTIALS_JSON could not be written: %s", _e)

# ── Step 3: all remaining imports ────────────────────────────────────────────
import threading
import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger.info("Importing config and database...")
from config import settings
from database import Base, engine, SessionLocal

logger.info("Importing routers...")
from routers.auth      import router as auth_router, oauth2_scheme  # noqa: F401
from routers.teachers  import router as teachers_router
from routers.locations import router as locations_router
from routers.shifts    import router as shifts_router
from routers.weeks     import router as weeks_router
from routers.points    import router as points_router
from routers.reports   import router as reports_router
from routers.dashboard import router as dashboard_router
from scheduler         import start_scheduler, stop_scheduler, router as scheduler_router
from seed_data         import seed_shifts, seed_locations, seed_grade_classes

# ── Model imports — required so Base.metadata.create_all() registers all tables
import models.models           # noqa: F401
import models.notification_log # noqa: F401 — NotificationLog (duty reminders)

logger.info("All imports complete — building FastAPI app.")

# ── Bootstrap state (exposed by /health) ─────────────────────────────────────
_bootstrap_done  = False
_bootstrap_error = False


def _run_bootstrap() -> None:
    """
    Background thread: create tables + seed reference data.
    Never blocks the health check — fires after the app is already accepting connections.

    RUN_SEED env var:
      true  (default) — run seed on every startup (idempotent, safe)
      false           — skip seeding (faster restarts after first deploy)
    """
    global _bootstrap_done, _bootstrap_error
    try:
        logger.info("[bootstrap] Creating tables if missing...")
        Base.metadata.create_all(bind=engine)
        logger.info("[bootstrap] create_all done.")

        if os.getenv("RUN_SEED", "true").strip().lower() == "true":
            db = SessionLocal()
            try:
                logger.info("[bootstrap] Seeding reference data...")
                seed_shifts(db);        db.commit()
                seed_locations(db);     db.commit()
                seed_grade_classes(db); db.commit()
                logger.info("[bootstrap] Seeding complete.")
            except Exception:
                db.rollback()
                logger.exception("[bootstrap] Seed failed.")
                raise
            finally:
                db.close()
        else:
            logger.info("[bootstrap] RUN_SEED=false — skipping seed.")

        _bootstrap_done = True
        logger.info("[bootstrap] Bootstrap finished successfully.")
    except Exception:
        _bootstrap_error = True
        logger.exception("[bootstrap] Bootstrap failed — app still running.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Firduty lifespan start.")

    # Launch bootstrap in background — returns immediately.
    # /health can respond 200 before any DB connection is opened.
    thread = threading.Thread(target=_run_bootstrap, daemon=True, name="bootstrap")
    thread.start()
    logger.info("Bootstrap thread started.")

    start_scheduler()
    logger.info("Scheduler started. API ready.")
    yield

    logger.info("Firduty shutting down...")
    stop_scheduler()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Firduty API",
    description=(
        "School Duty Roster Management System.\n\n"
        "**Authentication:** Click 🔓 Authorize and enter admin credentials."
    ),
    version="3.2.0",
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
    return {"service": "Firduty API", "version": "3.2.0", "status": "running"}


@app.get("/health")
def health():
    """
    Always returns 200 OK immediately — even while bootstrap is still running.
    Koyeb calls this to decide when the deployment is healthy.
    bootstrap_ready turns true once create_all + seed finish (~5–10 s after start).
    """
    return {
        "status":           "ok",
        "bootstrap_ready":  _bootstrap_done,
        "bootstrap_error":  _bootstrap_error,
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT)
