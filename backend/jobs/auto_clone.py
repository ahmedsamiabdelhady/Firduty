#!/usr/bin/env python3
"""
jobs/auto_clone.py — Weekly duty schedule auto-clone job.

Scheduled: every Thursday at 16:00 Asia/Muscat
Callable:  run_auto_clone()  ← used by backend/scheduler.py
CLI:       python jobs/auto_clone.py  ← still works directly

Logic:
  - Find the latest published WeekPlan
  - Clone it to next week as Draft
  - Skip if next week already exists
  - Log all outcomes
"""

import sys
import os
import logging
from datetime import datetime, timedelta

import pytz

# ── Path bootstrap ─────────────────────────────────────────────────────────────
# Needed when this file is executed directly as a script (python jobs/auto_clone.py).
# When imported by backend/scheduler.py the backend/ directory is already on sys.path,
# so this insert is harmless (Python deduplicates sys.path entries at import time).
_backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../backend")
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

from database import SessionLocal
from models.models import WeekPlan
from services.week_service import get_current_week_start, clone_week

# ── Logger ─────────────────────────────────────────────────────────────────────
# Use a named logger so output goes through whatever handler is active
# (basicConfig when run as CLI, the app's root logger when run via APScheduler).
logger = logging.getLogger("firduty.jobs.auto_clone")

MUSCAT_TZ = pytz.timezone("Asia/Muscat")


# ── Callable ───────────────────────────────────────────────────────────────────

def run_auto_clone() -> None:
    """
    Core auto-clone logic. Called by APScheduler and by main() for CLI use.

    - Detects current week (Asia/Muscat)
    - Finds latest published week
    - Clones → next week as Draft
    - Skips silently if next week already exists
    """
    now_muscat = datetime.now(MUSCAT_TZ)
    logger.info(f"[auto_clone] Starting at {now_muscat.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    db = SessionLocal()
    try:
        current_week_start = get_current_week_start()
        next_week_start = current_week_start + timedelta(weeks=1)

        logger.info(
            f"[auto_clone] Current week: {current_week_start} | "
            f"Target week: {next_week_start}"
        )

        # Skip if target week already exists
        existing = db.query(WeekPlan).filter(
            WeekPlan.week_start_date == next_week_start
        ).first()
        if existing:
            logger.info(
                f"[auto_clone] Week {next_week_start} already exists "
                f"(status={existing.status}). Skipping."
            )
            return

        # Find the most recent published week to clone from
        source = db.query(WeekPlan).filter(
            WeekPlan.status == "published",
            WeekPlan.week_start_date <= current_week_start,
        ).order_by(WeekPlan.week_start_date.desc()).first()

        if not source:
            logger.warning(
                "[auto_clone] No published week found to clone from. Aborting."
            )
            return

        logger.info(
            f"[auto_clone] Cloning {source.week_start_date} → {next_week_start}"
        )
        result = clone_week(db, source.week_start_date, next_week_start, actor="scheduler")

        if result:
            logger.info(
                f"[auto_clone] ✓ Week {next_week_start} created as DRAFT (id={result.id})"
            )
        else:
            logger.error("[auto_clone] clone_week() returned None — unexpected.")

    except Exception:
        logger.exception("[auto_clone] Unexpected error")
        raise  # Re-raise so APScheduler can log the failure properly
    finally:
        db.close()

    logger.info("[auto_clone] Finished.")


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    """Configure logging for CLI use and run the job once."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [auto_clone] %(levelname)s: %(message)s",
    )
    run_auto_clone()


if __name__ == "__main__":
    main()