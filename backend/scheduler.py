"""
scheduler.py — APScheduler background job integration for Firduty.

Jobs registered:
  1. auto_clone      → every Thursday at 16:00 Asia/Muscat
  2. monthly_reset   → day 1 of every month at 20:05 Asia/Muscat
  3. duty_reminders  → every minute (sends 15m-before and duty-start notifications)

Usage (called from main.py lifespan):
    from scheduler import start_scheduler, stop_scheduler, router

Environment variables:
  RUN_SCHEDULER=true      (default) — start scheduler on app startup
  RUN_SCHEDULER=false               — disable
  SCHEDULER_JITTER=30               — random jitter seconds (default: 30)

Deduplication for duty_reminders:
  Each notification is recorded in notification_logs. Running the job
  multiple times for the same duty has no effect — duplicates are suppressed
  by the unique constraint on (teacher_id, assignment_id, notification_type).
"""

import logging
import os
import sys
from typing import Any

import pytz
from fastapi import APIRouter
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from jobs.auto_clone      import run_auto_clone       # noqa: E402
from jobs.monthly_reset   import run_monthly_reset    # noqa: E402
from jobs.duty_reminders  import run_duty_reminders   # noqa: E402

router     = APIRouter(tags=["Scheduler"])
logger     = logging.getLogger("firduty.scheduler")
MUSCAT_TZ  = pytz.timezone("Asia/Muscat")
_JITTER    = int(os.getenv("SCHEDULER_JITTER", "30"))

_scheduler: BackgroundScheduler | None = None


# ── Wrapped job functions ──────────────────────────────────────────────────────

def _run_auto_clone_job() -> None:
    logger.info("[scheduler] ▶ Starting job: auto_clone")
    run_auto_clone()


def _run_monthly_reset_job() -> None:
    logger.info("[scheduler] ▶ Starting job: monthly_reset")
    run_monthly_reset()


def _run_duty_reminders_job() -> None:
    run_duty_reminders()   # job logs internally; no extra wrap needed


# ── Event listener ─────────────────────────────────────────────────────────────

def _job_listener(event) -> None:
    if event.exception:
        logger.error(
            f"[scheduler] ✗ Job '{event.job_id}' FAILED — "
            f"{type(event.exception).__name__}: {event.exception}"
        )
    else:
        # duty_reminders fires every minute — skip "success" log to avoid noise
        if event.job_id != "duty_reminders":
            logger.info(f"[scheduler] ✓ Job '{event.job_id}' finished successfully.")


# ── API helpers ────────────────────────────────────────────────────────────────

def _serialize_jobs() -> list[dict[str, Any]]:
    if not _scheduler:
        return []
    return [
        {
            "id":            job.id,
            "name":          job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger":       str(job.trigger),
        }
        for job in _scheduler.get_jobs()
    ]


@router.get("/scheduler/status")
def scheduler_status() -> dict[str, Any]:
    run_scheduler_env = os.getenv("RUN_SCHEDULER", "true").strip().lower()
    return {
        "enabled_by_env": run_scheduler_env == "true",
        "running":        bool(_scheduler and _scheduler.running),
        "timezone":       "Asia/Muscat",
        "jitter_seconds": _JITTER,
        "jobs":           _serialize_jobs(),
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """Build and start the APScheduler BackgroundScheduler. Idempotent."""
    global _scheduler

    run = os.getenv("RUN_SCHEDULER", "true").strip().lower()
    if run != "true":
        logger.info("[scheduler] RUN_SCHEDULER != 'true' — scheduler disabled.")
        return

    if _scheduler is not None and _scheduler.running:
        logger.warning("[scheduler] Already running — ignoring duplicate start() call.")
        return

    _scheduler = BackgroundScheduler(timezone=MUSCAT_TZ)

    # ── Weekly auto-clone ────────────────────────────────────────────────────
    _scheduler.add_job(
        func=_run_auto_clone_job,
        trigger="cron",
        day_of_week="thu", hour=16, minute=0, second=0,
        timezone=MUSCAT_TZ,
        jitter=_JITTER,
        id="auto_clone",
        name="Weekly duty schedule auto-clone",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # ── Monthly points rebuild ────────────────────────────────────────────────
    _scheduler.add_job(
        func=_run_monthly_reset_job,
        trigger="cron",
        day=1, hour=20, minute=5, second=0,
        timezone=MUSCAT_TZ,
        jitter=_JITTER,
        id="monthly_reset",
        name="Monthly points summary rebuild",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # ── Duty reminders (every minute) ─────────────────────────────────────────
    # Runs every minute to catch the 15-min-before and duty-started windows.
    # Fully idempotent — deduplication is handled by notification_logs table.
    _scheduler.add_job(
        func=_run_duty_reminders_job,
        trigger="interval",
        seconds=60,
        id="duty_reminders",
        name="Duty reminder notifications (every minute)",
        replace_existing=True,
        misfire_grace_time=90,
        max_instances=1,         # never overlap — one run at a time
    )

    _scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    _scheduler.start()

    logger.info("[scheduler] APScheduler started (timezone: Asia/Muscat).")
    for job in _scheduler.get_jobs():
        logger.info(
            "[scheduler]   • '%s' (%s) — next run: %s",
            job.id, job.name, job.next_run_time,
        )


def stop_scheduler() -> None:
    """Gracefully stop the scheduler. Called from FastAPI lifespan shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] APScheduler stopped.")
    _scheduler = None
