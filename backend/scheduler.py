"""
scheduler.py — APScheduler background job integration for Firduty.

Three jobs are registered:
  1. auto_clone      → every Thursday at 16:00 Asia/Muscat
  2. monthly_reset   → day 1 of every month at 20:05 Asia/Muscat
  3. duty_reminders  → every minute (15-min reminder + duty-start notifications)

Usage (called from main.py lifespan):
    from scheduler import start_scheduler, stop_scheduler, router

Environment variables:
  RUN_SCHEDULER=true      (default) — start scheduler on app startup
  RUN_SCHEDULER=false               — disable (useful for worker-only instances)
  SCHEDULER_JITTER=30               — random jitter seconds for cron jobs only
                                      (NOT applied to duty_reminders interval)

Koyeb multi-instance note:
  If Koyeb scales beyond one instance every instance runs this scheduler.
  Set RUN_SCHEDULER=true on ONE instance and RUN_SCHEDULER=false on all others.
"""

import logging
import os
import sys
from typing import Any

import pytz
from fastapi import APIRouter
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from jobs.auto_clone     import run_auto_clone       # noqa: E402
from jobs.monthly_reset  import run_monthly_reset    # noqa: E402
from jobs.duty_reminders import run_duty_reminders   # noqa: E402

router    = APIRouter(tags=["Scheduler"])
logger    = logging.getLogger("firduty.scheduler")
MUSCAT_TZ = pytz.timezone("Asia/Muscat")
_JITTER   = int(os.getenv("SCHEDULER_JITTER", "30"))

_scheduler: BackgroundScheduler | None = None


# ── Wrapped job functions ──────────────────────────────────────────────────────

def _run_auto_clone_job() -> None:
    logger.info("[scheduler] ▶ Starting job: auto_clone")
    run_auto_clone()


def _run_monthly_reset_job() -> None:
    logger.info("[scheduler] ▶ Starting job: monthly_reset")
    run_monthly_reset()


def _run_duty_reminders_job() -> None:
    # duty_reminders logs internally — no wrapper noise needed.
    # Exceptions propagate to the APScheduler event listener.
    run_duty_reminders()


# ── Event listener ─────────────────────────────────────────────────────────────

def _job_listener(event) -> None:
    if event.exception:
        logger.error(
            "[scheduler] ✗ Job '%s' FAILED — %s: %s",
            event.job_id,
            type(event.exception).__name__,
            event.exception,
        )
    else:
        # duty_reminders fires every minute — suppress noisy success logs.
        if event.job_id != "duty_reminders":
            logger.info("[scheduler] ✓ Job '%s' finished successfully.", event.job_id)


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
    return {
        "enabled_by_env": os.getenv("RUN_SCHEDULER", "true").strip().lower() == "true",
        "running":        bool(_scheduler and _scheduler.running),
        "timezone":       "Asia/Muscat",
        "jitter_seconds": _JITTER,
        "jobs":           _serialize_jobs(),
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """Build and start the APScheduler BackgroundScheduler. Idempotent."""
    global _scheduler

    if os.getenv("RUN_SCHEDULER", "true").strip().lower() != "true":
        logger.info("[scheduler] RUN_SCHEDULER != 'true' — scheduler disabled.")
        return

    if _scheduler is not None and _scheduler.running:
        logger.warning("[scheduler] Already running — ignoring duplicate start() call.")
        return

    _scheduler = BackgroundScheduler(timezone=MUSCAT_TZ)

    # ── 1. Weekly auto-clone ─────────────────────────────────────────────────
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

    # ── 2. Monthly points rebuild ────────────────────────────────────────────
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

    # ── 3. Duty reminders (every 60 seconds) ─────────────────────────────────
    # Checks for duties starting in ~15 min or right now and sends FCM push.
    # NO jitter — we need reliable 60-second cadence for accurate time windows.
    # max_instances=1 prevents overlap if a run takes longer than 60 seconds.
    _scheduler.add_job(
        func=_run_duty_reminders_job,
        trigger="interval",
        seconds=60,
        id="duty_reminders",
        name="Duty reminder notifications",
        replace_existing=True,
        misfire_grace_time=90,
        max_instances=1,
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
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] APScheduler stopped.")
    _scheduler = None
