"""
scheduler.py — APScheduler background job integration for Firduty.

Production-safe changes:
- Idempotent startup / shutdown
- Non-blocking shutdown for Koyeb and similar platforms
- Avoid duplicate event listeners on restart
- Reduced chance of stuck deployments during container stop
- Defensive exception handling during stop
"""

import atexit
import logging
import os
import sys
from typing import Any

import pytz
from fastapi import APIRouter
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.base import STATE_RUNNING, STATE_STOPPED, STATE_PAUSED

_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from jobs.auto_clone import run_auto_clone  # noqa: E402
from jobs.monthly_reset import run_monthly_reset  # noqa: E402
from jobs.duty_reminders import run_duty_reminders  # noqa: E402

router = APIRouter(tags=["Scheduler"])
logger = logging.getLogger("firduty.scheduler")
MUSCAT_TZ = pytz.timezone("Asia/Muscat")
_JITTER = int(os.getenv("SCHEDULER_JITTER", "30"))

_scheduler: BackgroundScheduler | None = None
_atexit_registered = False


# ── Wrapped job functions ─────────────────────────────────────────────────────

def _run_auto_clone_job() -> None:
    logger.info("[scheduler] ▶ Starting job: auto_clone")
    run_auto_clone()


def _run_monthly_reset_job() -> None:
    logger.info("[scheduler] ▶ Starting job: monthly_reset")
    run_monthly_reset()


def _run_duty_reminders_job() -> None:
    run_duty_reminders()


# ── Event listener ────────────────────────────────────────────────────────────

def _job_listener(event) -> None:
    if event.exception:
        logger.error(
            "[scheduler] ✗ Job '%s' FAILED — %s: %s",
            event.job_id,
            type(event.exception).__name__,
            event.exception,
        )
    elif event.job_id != "duty_reminders":
        logger.info("[scheduler] ✓ Job '%s' finished successfully.", event.job_id)


# ── API helpers ───────────────────────────────────────────────────────────────

def _serialize_jobs() -> list[dict[str, Any]]:
    if not _scheduler:
        return []
    return [
        {
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        }
        for job in _scheduler.get_jobs()
    ]


@router.get("/scheduler/status")
def scheduler_status() -> dict[str, Any]:
    run_scheduler_env = os.getenv("RUN_SCHEDULER", "true").strip().lower()
    state = None
    if _scheduler is not None:
        if _scheduler.state == STATE_RUNNING:
            state = "running"
        elif _scheduler.state == STATE_PAUSED:
            state = "paused"
        elif _scheduler.state == STATE_STOPPED:
            state = "stopped"
        else:
            state = str(_scheduler.state)

    return {
        "enabled_by_env": run_scheduler_env == "true",
        "running": bool(_scheduler and _scheduler.running),
        "state": state,
        "timezone": "Asia/Muscat",
        "jitter_seconds": _JITTER,
        "jobs": _serialize_jobs(),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _register_atexit_once() -> None:
    global _atexit_registered
    if not _atexit_registered:
        atexit.register(stop_scheduler)
        _atexit_registered = True


def _build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=MUSCAT_TZ, daemon=True)

    scheduler.add_job(
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
        coalesce=True,
        max_instances=1,
    )

    scheduler.add_job(
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
        coalesce=True,
        max_instances=1,
    )

    scheduler.add_job(
        func=_run_duty_reminders_job,
        trigger="interval",
        seconds=60,
        id="duty_reminders",
        name="Duty reminder notifications (every minute)",
        replace_existing=True,
        misfire_grace_time=90,
        coalesce=True,
        max_instances=1,
    )

    scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    return scheduler


# ── Public API ────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """Build and start APScheduler. Safe to call multiple times."""
    global _scheduler

    run = os.getenv("RUN_SCHEDULER", "true").strip().lower()
    if run != "true":
        logger.info("[scheduler] RUN_SCHEDULER != 'true' — scheduler disabled.")
        return

    if _scheduler is not None:
        if _scheduler.state == STATE_RUNNING:
            logger.info("[scheduler] Already running — skipping duplicate start().")
            return
        if _scheduler.state in {STATE_PAUSED, STATE_STOPPED}:
            try:
                _scheduler.shutdown(wait=False)
            except Exception:
                logger.debug("[scheduler] Ignored shutdown error while rebuilding scheduler.", exc_info=True)
            _scheduler = None

    _scheduler = _build_scheduler()
    _register_atexit_once()

    try:
        _scheduler.start()
    except Exception:
        logger.exception("[scheduler] Failed to start APScheduler.")
        _scheduler = None
        raise

    logger.info("[scheduler] APScheduler started (timezone: Asia/Muscat).")
    for job in _scheduler.get_jobs():
        logger.info(
            "[scheduler]   • '%s' (%s) — next run: %s",
            job.id,
            job.name,
            job.next_run_time,
        )


def stop_scheduler() -> None:
    """Stop APScheduler without blocking container shutdown."""
    global _scheduler

    if _scheduler is None:
        return

    try:
        if _scheduler.state != STATE_STOPPED:
            _scheduler.shutdown(wait=False)
            logger.info("[scheduler] APScheduler stopped.")
    except Exception:
        logger.warning("[scheduler] Ignored error during shutdown.", exc_info=True)
    finally:
        _scheduler = None
