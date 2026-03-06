#!/usr/bin/env python3
"""
auto_clone.py — Automatic weekly duty schedule clone job.

Runs every Thursday at 16:00 Asia/Muscat time.
Cron: 0 12 * * 4 /usr/bin/python3 /app/jobs/auto_clone.py >> /var/log/auto_clone.log 2>&1
(16:00 Muscat = 12:00 UTC, UTC+4)
"""

import sys
import os
import logging
from datetime import datetime, timedelta

import pytz

# Add backend to path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from database import SessionLocal
from models.models import WeekPlan
from services.week_service import get_current_week_start, clone_week, get_week_start

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [auto_clone] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

MUSCAT_TZ = pytz.timezone("Asia/Muscat")


def main():
    now_muscat = datetime.now(MUSCAT_TZ)
    logger.info(f"Auto-clone job started at {now_muscat.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    db = SessionLocal()
    try:
        # Current week start (Sunday)
        current_week_start = get_current_week_start()
        # Next week start
        next_week_start = current_week_start + timedelta(weeks=1)

        logger.info(f"Current week: {current_week_start}  |  Target week: {next_week_start}")

        # Check if next week already exists — skip if so
        existing = db.query(WeekPlan).filter(WeekPlan.week_start_date == next_week_start).first()
        if existing:
            logger.info(f"Week {next_week_start} already exists (status={existing.status}). Skipping clone.")
            return

        # Find the latest published week to clone from
        source = db.query(WeekPlan).filter(
            WeekPlan.status == "published",
            WeekPlan.week_start_date <= current_week_start
        ).order_by(WeekPlan.week_start_date.desc()).first()

        if not source:
            logger.warning("No published week found to clone from. Auto-clone aborted.")
            return

        logger.info(f"Cloning from week {source.week_start_date} → {next_week_start}")
        result = clone_week(db, source.week_start_date, next_week_start, actor="auto_clone")

        if result:
            logger.info(f"✓ Successfully cloned week {next_week_start} as DRAFT (id={result.id})")
        else:
            logger.error("Clone returned None — something went wrong.")

    except Exception as e:
        logger.exception(f"Unexpected error in auto_clone: {e}")
        sys.exit(1)
    finally:
        db.close()

    logger.info("Auto-clone job completed.")


if __name__ == "__main__":
    main()