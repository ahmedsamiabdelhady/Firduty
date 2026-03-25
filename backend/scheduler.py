"""
scheduler.py — APScheduler background job integration for Firduty.

Production-safe behavior:
- Prevents duplicate scheduler startup across multiple app processes
- Uses a dedicated PostgreSQL advisory-lock connection
- Keeps the lock alive for the whole scheduler lifetime
"""

import logging
import os
import sys
from typing import Any

import pytz
from fastapi import APIRouter
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from sqlalchemy import text

# Ensure backend path is available
_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from database import engine  # noqa: E402
from jobs.auto_clone import run_auto_clone  # noqa: E402
from jobs.monthly_reset import run_monthly_reset  # noqa: E402
from jobs.duty_reminders import run_duty_reminders  # noqa: E402

router = APIRouter(tags=["Scheduler"])
logger = logging.getLogger("firduty.scheduler")
MUSCAT_TZ = pytz.timezone("Asia/Muscat")
_JITTER = int(os.getenv("SCHEDULER_JITTER", "30"))

# Must be constant across all app processes
_SCHEDULER_LOCK_KEY = 918274661239

_scheduler: BackgroundScheduler | None = None
_scheduler_lock_acquired = False
_scheduler_lock_conn = None


def _run_auto_clone_job() -> None:
    logger.info("[scheduler] ▶ Starting job: auto_clone")
    run_auto_clone()


def _run_monthly_reset_job() -> None:
    logger.info("[scheduler] ▶ Starting job: monthly_reset")
    run_monthly_reset()


def _run_duty_reminders_job() -> None:
    run_duty_reminders()


def _try_acquire_scheduler_lock() -> bool:
    """
    Acquire a PostgreSQL advisory lock using a dedicated connection.
    The same connection must remain open for the entire scheduler lifetime.
    """
    global _scheduler_lock_acquired, _scheduler_lock_conn

    if _scheduler_lock_acquired and _scheduler_lock_conn is not None:
        return True

    try:
        conn = engine.connect()
        acquired = conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": _SCHEDULER_LOCK_KEY},
        ).scalar()
        acquired = bool(acquired)

        if acquired:
            _scheduler_lock_conn = conn
            _scheduler_lock_acquired = True
            logger.info(
                "[scheduler] Advisory lock acquired. This process is the scheduler leader."
            )
            return True

        conn.close()
        logger.info(
            "[scheduler] Advisory lock NOT acquired. Another process is already running the scheduler."
        )
        return False
    except Exception:
        logger.exception("[scheduler] Failed to acquire advisory lock.")
        try:
            if _scheduler_lock_conn is not None:
                _scheduler_lock_conn.close()
        except Exception:
            pass
        _scheduler_lock_conn = None
        _scheduler_lock_acquired = False
        return False


def _release_scheduler_lock() -> None:
    """
    Release the advisory lock and close the dedicated connection.
    """
    global _scheduler_lock_acquired, _scheduler_lock_conn

    if not _scheduler_lock_acquired or _scheduler_lock_conn is None:
        return

    try:
        _scheduler_lock_conn.execute(
            text("SELECT pg_advisory_unlock(:key)"),
            {"key": _SCHEDULER_LOCK_KEY},
        )
        logger.info("[scheduler] Advisory lock released.")
    except Exception:
        logger.exception("[scheduler] Failed to release advisory lock.")
    finally:
        try:
            _scheduler_lock_conn.close()
        except Exception:
            pass
        _scheduler_lock_conn = None
        _scheduler_lock_acquired = False


def _job_listener(event) -> None:
    if event.exception:
        logger.error(
            "[scheduler] ✗ Job '%s' FAILED — %s: %s",
            event.job_id,
            type(event.exception).__name__,
            event.exception,
        )
    else:
        if event.job_id != "duty_reminders":
            logger.info("[scheduler] ✓ Job '%s' finished successfully.", event.job_id)


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
    return {
        "enabled_by_env": os.getenv("RUN_SCHEDULER", "true").strip().lower() == "true",
        "leader": _scheduler_lock_acquired,
        "running": bool(_scheduler and _scheduler.running),
        "timezone": "Asia/Muscat",
        "jitter_seconds": _JITTER,
        "jobs": _serialize_jobs(),
    }


def start_scheduler() -> None:
    """
    Start APScheduler safely.

    Guarantees:
    - Respects RUN_SCHEDULER env variable
    - Runs once per process
    - Only one process becomes scheduler leader via PostgreSQL advisory lock
    """
    global _scheduler

    if os.getenv("RUN_SCHEDULER", "true").strip().lower() != "true":
        logger.info("[scheduler] RUN_SCHEDULER != 'true' — scheduler disabled.")
        return

    if _scheduler is not None and _scheduler.running:
        logger.warning("[scheduler] Already running in this process — skipping duplicate start.")
        return

    if not _try_acquire_scheduler_lock():
        logger.info("[scheduler] This process is not the scheduler leader — skipping startup.")
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

    _scheduler.add_job(
        func=_run_duty_reminders_job,
        trigger="cron",
        second=0,
        timezone=MUSCAT_TZ,
        id="duty_reminders",
        name="Duty reminder notifications",
        replace_existing=True,
        misfire_grace_time=5,
        max_instances=1,
        coalesce=True,
    )

    _scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    _scheduler.start()

    logger.info("[scheduler] APScheduler started (timezone: Asia/Muscat).")
    for job in _scheduler.get_jobs():
        logger.info(
            "[scheduler]   • '%s' (%s) — next run: %s",
            job.id,
            job.name,
            job.next_run_time,
        )


def stop_scheduler() -> None:
    """
    Stop scheduler and release advisory lock.
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("[scheduler] APScheduler stopped.")
        except Exception:
            logger.exception("[scheduler] Error while stopping APScheduler.")

    _scheduler = None
    _release_scheduler_lock()