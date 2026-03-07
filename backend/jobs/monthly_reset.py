#!/usr/bin/env python3
"""
jobs/monthly_reset.py — Monthly points summary rebuild job.

Scheduled: every month on day 1 at 20:05 Asia/Muscat
Callable:  run_monthly_reset()  ← used by backend/scheduler.py
CLI:       python jobs/monthly_reset.py  ← still works directly

Logic:
  - Rebuild MonthlyPointsSummary for the month that just ended
  - Seed empty summary rows for the new current month
    so all teachers appear in reports from day 1
"""

import sys
import os
import logging
from datetime import datetime

import pytz

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../backend")
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

from database import SessionLocal
from services.points_service import rebuild_monthly_summary_for_all

# ── Logger ─────────────────────────────────────────────────────────────────────
logger = logging.getLogger("firduty.jobs.monthly_reset")

MUSCAT_TZ = pytz.timezone("Asia/Muscat")


# ── Callable ───────────────────────────────────────────────────────────────────

def run_monthly_reset() -> None:
    """
    Core monthly reset logic. Called by APScheduler and by main() for CLI use.

    Runs on the 1st of the month at 20:05 Muscat, so:
      - Previous month = now.month - 1 (handles January → December rollover)
      - Current month  = now.month     (seed empty rows for new month)
    """
    now_muscat = datetime.now(MUSCAT_TZ)
    logger.info(
        f"[monthly_reset] Starting at {now_muscat.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    )

    db = SessionLocal()
    try:
        if now_muscat.month == 1:
            prev_year, prev_month = now_muscat.year - 1, 12
        else:
            prev_year, prev_month = now_muscat.year, now_muscat.month - 1

        logger.info(f"[monthly_reset] Rebuilding {prev_year}/{prev_month:02d}...")
        rebuild_monthly_summary_for_all(db, prev_year, prev_month)
        logger.info(f"[monthly_reset] ✓ Finalized {prev_year}/{prev_month:02d}")

        logger.info(
            f"[monthly_reset] Seeding {now_muscat.year}/{now_muscat.month:02d}..."
        )
        rebuild_monthly_summary_for_all(db, now_muscat.year, now_muscat.month)
        logger.info(
            f"[monthly_reset] ✓ Seeded {now_muscat.year}/{now_muscat.month:02d}"
        )

    except Exception:
        logger.exception("[monthly_reset] Unexpected error")
        raise
    finally:
        db.close()

    logger.info("[monthly_reset] Finished.")


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    """Configure logging for CLI use and run the job once."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [monthly_reset] %(levelname)s: %(message)s",
    )
    run_monthly_reset()


if __name__ == "__main__":
    main()