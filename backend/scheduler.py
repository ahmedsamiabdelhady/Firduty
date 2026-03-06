"""
scheduler.py — APScheduler background job integration for Firduty.

Two jobs are registered:
  1. auto_clone    → every Thursday at 16:00 Asia/Muscat
  2. monthly_reset → day 1 of every month at 20:05 Asia/Muscat

Usage (called from main.py lifespan):
    from scheduler import start_scheduler, stop_scheduler, router

Environment variables:
  RUN_SCHEDULER=true    (default) — start scheduler on app startup
  RUN_SCHEDULER=false             — disable (useful for worker-only instances)
  SCHEDULER_JITTER=30             — random seconds added to each trigger
                                    to reduce collision on multi-instance deploys
                                    (default: 30)

Koyeb multi-instance note
──────────────────────────
If Koyeb scales beyond one instance every instance runs this scheduler,
meaning both jobs fire N times per trigger. To avoid this:
  - Deploy with a single instance (recommended — see README).
  - Or set RUN_SCHEDULER=true on exactly ONE instance and
    RUN_SCHEDULER=false on all others.

Both job functions (run_auto_clone, run_monthly_reset) are idempotent:
  - auto_clone skips if next week already exists.
  - monthly_reset is a pure recalculation — running it twice is safe.
"""

import logging
import os
import sys
from typing import Any

import pytz
from fastapi import APIRouter
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

# ── Import job callables ───────────────────────────────────────────────────────
# jobs/ sits one level above backend/ in the project tree.
# Insert it so imports resolve regardless of the working directory.
_jobs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../jobs")
if _jobs_dir not in sys.path:
    sys.path.insert(0, _jobs_dir)

from auto_clone import run_auto_clone          # noqa: E402
from monthly_reset import run_monthly_reset    # noqa: E402

# ── API Router ─────────────────────────────────────────────────────────────────
router = APIRouter(tags=["Scheduler"])

# ── Logger ─────────────────────────────────────────────────────────────────────
logger = logging.getLogger("firduty.scheduler")

MUSCAT_TZ = pytz.timezone("Asia/Muscat")

# Random jitter (seconds) added to each trigger — softens multi-instance collision
_JITTER = int(os.getenv("SCHEDULER_JITTER", "30"))

# ── Singleton scheduler instance ───────────────────────────────────────────────
_scheduler: BackgroundScheduler | None = None


# ── Wrapped job functions ──────────────────────────────────────────────────────
def _run_auto_clone_job() -> None:
    logger.info("[scheduler] ▶ Starting job: auto_clone")
    run_auto_clone()


def _run_monthly_reset_job() -> None:
    logger.info("[scheduler] ▶ Starting job: monthly_reset")
    run_monthly_reset()


# ── Event listener ─────────────────────────────────────────────────────────────
def _job_listener(event) -> None:
    """Structured success/failure logging after each job execution."""
    if event.exception:
        logger.error(
            f"[scheduler] ✗ Job '{event.job_id}' FAILED — "
            f"{type(event.exception).__name__}: {event.exception}"
        )
    else:
        logger.info(f"[scheduler] ✓ Job '{event.job_id}' finished successfully.")


# ── Helper for API status ──────────────────────────────────────────────────────
def _serialize_jobs() -> list[dict[str, Any]]:
    if not _scheduler:
        return []

    jobs: list[dict[str, Any]] = []
    for job in _scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
        )
    return jobs


# ── Public API route ───────────────────────────────────────────────────────────
@router.get("/scheduler/status")
def scheduler_status() -> dict[str, Any]:
    run_scheduler_env = os.getenv("RUN_SCHEDULER", "true").strip().lower()

    return {
        "enabled_by_env": run_scheduler_env == "true",
        "running": bool(_scheduler and _scheduler.running),
        "timezone": "Asia/Muscat",
        "jitter_seconds": _JITTER,
        "jobs": _serialize_jobs(),
    }


# ── Public API ─────────────────────────────────────────────────────────────────
def start_scheduler() -> None:
    """
    Build and start the APScheduler BackgroundScheduler.

    Guards:
      - RUN_SCHEDULER env var must equal "true" (default).
        Set RUN_SCHEDULER=false to disable without changing code.
      - If already running, this is a no-op.
    """
    global _scheduler

    run = os.getenv("RUN_SCHEDULER", "true").strip().lower()
    if run != "true":
        logger.info(
            "[scheduler] RUN_SCHEDULER != 'true' — scheduler disabled on this instance."
        )
        return

    if _scheduler is not None and _scheduler.running:
        logger.warning("[scheduler] Already running — ignoring duplicate start() call.")
        return

    _scheduler = BackgroundScheduler(timezone=MUSCAT_TZ)

    _scheduler.add_job(
        func=_run_auto_clone_job,
        trigger="cron",
        day_of_week="thu",
        hour=16,
        minute=0,
        second=0,
        timezone=MUSCAT_TZ,
        jitter=_JITTER,
        id="auto_clone",
        name="Weekly duty schedule auto-clone",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.add_job(
        func=_run_monthly_reset_job,
        trigger="cron",
        day=1,
        hour=20,
        minute=5,
        second=0,
        timezone=MUSCAT_TZ,
        jitter=_JITTER,
        id="monthly_reset",
        name="Monthly points summary rebuild",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    _scheduler.start()

    logger.info("[scheduler] APScheduler started (timezone: Asia/Muscat).")
    for job in _scheduler.get_jobs():
        logger.info(
            f"[scheduler]   • '{job.id}' ({job.name}) — "
            f"next run: {job.next_run_time}"
        )


def stop_scheduler() -> None:
    """
    Gracefully shut down the scheduler.
    Called from the FastAPI lifespan shutdown hook.
    Safe to call even if the scheduler was never started.
    """
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] APScheduler stopped.")
    _scheduler = None