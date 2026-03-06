"""
main.py — FastAPI application entry point for Firduty backend.

Start command (Koyeb / Procfile):
    uvicorn main:app --host 0.0.0.0 --port $PORT

Scheduler:
    APScheduler starts automatically inside the lifespan context.
    Set RUN_SCHEDULER=false to disable on any specific instance.
"""

import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import Base, engine
from routers import auth, teachers, locations, shifts, weeks, points, reports
from scheduler import start_scheduler, stop_scheduler
from scheduler import router as scheduler_router

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ── Database tables ────────────────────────────────────────────────────────────
# Creates any missing tables on startup. Safe to run on every restart.
Base.metadata.create_all(bind=engine)


# ── Lifespan ───────────────────────────────────────────────────────────────────
# FastAPI lifespan replaces deprecated @app.on_event("startup"/"shutdown").
# The scheduler starts once when uvicorn loads the app and stops cleanly
# when the process receives a shutdown signal (SIGTERM on Koyeb).
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────────────
    logger.info("Firduty API starting up...")
    start_scheduler()          # No-op if RUN_SCHEDULER != "true"
    yield
    # ── Shutdown ───────────────────────────────────────────────────────────────
    logger.info("Firduty API shutting down...")
    stop_scheduler()


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Firduty API",
    description="School Duty Roster Management System",
    version="2.0.0",
    lifespan=lifespan,         # Attach lifespan handler
)

# ── CORS ───────────────────────────────────────────────────────────────────────
# Origins are read from ALLOWED_ORIGINS env var (comma-separated).
# Defaults to ["*"] for local dev. Always restrict in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(teachers.router)
app.include_router(locations.router)
app.include_router(shifts.router)
app.include_router(weeks.router)
app.include_router(points.router)
app.include_router(reports.router)
app.include_router(scheduler_router)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "Firduty API", "version": "2.0.0", "status": "running"}


@app.get("/health")
def health():
    """Health check endpoint — Koyeb polls this to verify the service is alive."""
    return {"status": "ok"}


@app.get("/scheduler/status")
def scheduler_status():
    """
    Returns the current status of the background scheduler and each job's
    next scheduled run time. Useful for verifying jobs are registered after deploy.
    """
    from scheduler import _scheduler
    if _scheduler is None or not _scheduler.running:
        return {"running": False, "jobs": []}
    jobs = [
        {
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time),
        }
        for job in _scheduler.get_jobs()
    ]
    return {"running": True, "jobs": jobs}


# ── Local dev entry point ──────────────────────────────────────────────────────
# In production (Koyeb) the Procfile runs uvicorn directly.
# This block is only used when running `python main.py` locally.
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,
    )