#!/usr/bin/env python3
"""
jobs/monthly_reset.py — Monthly points summary rebuild job.

Runs on the 1st of every month at 00:05 Asia/Muscat time.
Rebuilds the MonthlyPointsSummary cache for the just-ended month
and initializes an empty record for all teachers for the new month.

Cron entry (UTC, Muscat=UTC+4, so 00:05 Muscat = 20:05 UTC previous day):
  5 20 28-31 * * [ "$(date +\%d -d tomorrow)" = "01" ] && /usr/bin/python3 /app/jobs/monthly_reset.py >> /var/log/monthly_reset.log 2>&1

Simpler alternative (runs every month on the 1st at 00:05 Muscat = 20:05 UTC):
  5 20 * * * [ $(date +\%d) = "01" ] && /usr/bin/python3 /app/jobs/monthly_reset.py

Or simply:
  5 20 1 * * /usr/bin/python3 /app/jobs/monthly_reset.py >> /var/log/monthly_reset.log 2>&1
"""

import sys
import os
import logging
from datetime import datetime

import pytz

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from database import SessionLocal
from services.points_service import rebuild_monthly_summary_for_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [monthly_reset] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

MUSCAT_TZ = pytz.timezone("Asia/Muscat")


def main():
    now_muscat = datetime.now(MUSCAT_TZ)
    logger.info(f"Monthly reset job started at {now_muscat.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    db = SessionLocal()
    try:
        # Rebuild summary for the month that just ended
        # (this job runs on the 1st of the new month, so previous month = now - 1 month)
        if now_muscat.month == 1:
            prev_year = now_muscat.year - 1
            prev_month = 12
        else:
            prev_year = now_muscat.year
            prev_month = now_muscat.month - 1

        logger.info(f"Rebuilding summary for {prev_year}/{prev_month:02d}...")
        rebuild_monthly_summary_for_all(db, prev_year, prev_month)
        logger.info(f"✓ Monthly summary rebuilt for {prev_year}/{prev_month:02d}")

        # Also seed empty records for current month (so teachers appear in current-month report)
        logger.info(f"Seeding current month {now_muscat.year}/{now_muscat.month:02d}...")
        rebuild_monthly_summary_for_all(db, now_muscat.year, now_muscat.month)
        logger.info(f"✓ Current month seeded: {now_muscat.year}/{now_muscat.month:02d}")

    except Exception as e:
        logger.exception(f"Unexpected error in monthly_reset: {e}")
        sys.exit(1)
    finally:
        db.close()

    logger.info("Monthly reset job completed.")


if __name__ == "__main__":
    main()