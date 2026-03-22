#!/usr/bin/env python3
"""
jobs/duty_reminders.py — Duty reminder notification job.

Scheduled: every 60 seconds via APScheduler interval trigger (scheduler.py)
Callable:  run_duty_reminders()

── What it does ────────────────────────────────────────────────────────────────
Every minute it queries today's published assignments and sends:

  reminder_15m  →  shift starts in 13–16 minutes from now  (3-min safe window)
  duty_started  →  shift started 0–2 minutes ago            (2-min safe window)

A 3-minute window (vs the old 1-minute window) ensures a late scheduler tick
or a Koyeb CPU spike doesn't silently drop a notification.

── Deduplication ────────────────────────────────────────────────────────────────
Before every send we INSERT a row into notification_logs.
The UNIQUE constraint on (teacher_id, assignment_id, notification_type) prevents
double-sending even if the job runs twice within the same window.
A notification is only logged as "sent" if FCM returns success_count > 0.
If FCM fails, status = "failed" and the row is NOT written — so the next
tick will retry.

── Invalid token cleanup ────────────────────────────────────────────────────────
When FCM reports a token as invalid/expired, it is removed from device_tokens
so future sends don't waste FCM quota.

── CLI / test ───────────────────────────────────────────────────────────────────
  python backend/jobs/duty_reminders.py
  → runs one tick immediately, logs results, exits.
"""

import sys
import os
import logging
from datetime import datetime, timedelta

import pytz

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from database import SessionLocal
from models.models import (
    Assignment, ShiftLocation, DayPlan, WeekPlan,
    Teacher, DeviceToken, Shift,
)

logger = logging.getLogger("firduty.jobs.duty_reminders")

MUSCAT_TZ = pytz.timezone("Asia/Muscat")

# ── Time windows ──────────────────────────────────────────────────────────────
# Wide enough that a late scheduler tick (CPU spike, Koyeb cold start) still
# catches the window. Deduplication prevents double-sending.
REMINDER_WINDOW_MIN = 13    # reminder fires when shift is 13–16 min away
REMINDER_WINDOW_MAX = 16
START_WINDOW_BEFORE = 0     # duty_started fires when shift started 0–2 min ago
START_WINDOW_AFTER  = 2


# ── Time helpers ──────────────────────────────────────────────────────────────

def _muscat_now() -> datetime:
    return datetime.now(MUSCAT_TZ).replace(tzinfo=None)


def _utcnow() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Deduplication ─────────────────────────────────────────────────────────────

def _already_sent(db: Session, teacher_id: int, assignment_id: int, notif_type: str) -> bool:
    try:
        from models.notification_log import NotificationLog
        return (
            db.query(NotificationLog)
            .filter(
                NotificationLog.teacher_id        == teacher_id,
                NotificationLog.assignment_id     == assignment_id,
                NotificationLog.notification_type == notif_type,
            )
            .first()
        ) is not None
    except Exception as exc:
        logger.error("[reminders] _already_sent error: %s", exc)
        return False   # fail open — attempt the send rather than silently skip


def _mark_sent(
    db: Session,
    teacher_id: int,
    assignment_id: int,
    notif_type: str,
    status: str,
) -> None:
    """
    Record that a notification was attempted.
    status = "sent"    → FCM confirmed at least one delivery
    status = "failed"  → FCM returned success_count=0 (will be retried next tick)
    status = "skipped" → teacher has no device tokens

    IMPORTANT: for "failed" we do NOT write the row — the unique constraint would
    block the next retry.  Only "sent" and "skipped" are persisted.
    """
    if status == "failed":
        # Don't record failures — let the next tick retry.
        logger.warning(
            "[reminders] Delivery FAILED for teacher=%d assignment=%d type=%s — "
            "will retry next tick.",
            teacher_id, assignment_id, notif_type,
        )
        return

    try:
        from models.notification_log import NotificationLog
        log = NotificationLog(
            teacher_id=teacher_id,
            assignment_id=assignment_id,
            notification_type=notif_type,
            sent_at=_utcnow(),
            status=status,
        )
        db.add(log)
        db.flush()
    except IntegrityError:
        db.rollback()   # already in DB from a concurrent write — safe to ignore
    except Exception as exc:
        logger.error("[reminders] _mark_sent error: %s", exc)
        db.rollback()


# ── Assignment context builder ────────────────────────────────────────────────

def _build_ctx(a: Assignment) -> dict:
    sl: ShiftLocation = a.shift_location
    shift: Shift      = sl.shift
    duty_type         = str(shift.duty_type)

    loc_en = loc_ar = None
    if duty_type == "morning_endofday" and sl.location:
        loc_en = sl.location.name_en
        loc_ar = sl.location.name_ar

    return {
        "assignment_id": a.id,
        "teacher_id":    int(a.teacher_id),
        "duty_type":     duty_type,
        "shift_name_en": shift.name_en,
        "shift_name_ar": shift.name_ar,
        "grade_class":   a.grade_class,
        "location_en":   loc_en,
        "location_ar":   loc_ar,
        "start_time":    shift.start_time,
    }


# ── Send one notification ─────────────────────────────────────────────────────

def _send_one(db: Session, ctx: dict, notif_type: str) -> None:
    """
    Send one notification if not already sent.

    Only marks as 'sent' if FCM returns success_count > 0.
    Cleans up invalid tokens from the DB.
    """
    teacher_id    = ctx["teacher_id"]
    assignment_id = ctx["assignment_id"]

    # ── Dedup check ───────────────────────────────────────────────────────────
    if _already_sent(db, teacher_id, assignment_id, notif_type):
        logger.debug(
            "[reminders] skip %s for teacher=%d assignment=%d (already sent)",
            notif_type, teacher_id, assignment_id,
        )
        return

    # ── Token fetch ───────────────────────────────────────────────────────────
    token_rows = (
        db.query(DeviceToken)
        .filter(DeviceToken.teacher_id == teacher_id)
        .all()
    )
    tokens = [r.token for r in token_rows]

    if not tokens:
        logger.info(
            "[reminders] teacher=%d has no device tokens — skipping %s",
            teacher_id, notif_type,
        )
        _mark_sent(db, teacher_id, assignment_id, notif_type, "skipped")
        db.commit()
        return

    # ── Language ──────────────────────────────────────────────────────────────
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    lang    = str(teacher.preferred_language) if teacher and teacher.preferred_language else "ar"

    # ── FCM send ──────────────────────────────────────────────────────────────
    try:
        from services.notification_service import (
            notify_duty_reminder,
            notify_duty_start,
            remove_invalid_tokens,
        )

        if notif_type == "reminder_15m":
            success, bad_tokens = notify_duty_reminder(
                teacher_tokens=tokens,
                lang=lang,
                shift=ctx["shift_name_ar"] if lang == "ar" else ctx["shift_name_en"],
                duty_type=ctx["duty_type"],
                location=ctx["location_ar"] if lang == "ar" else ctx["location_en"],
                grade_class=ctx.get("grade_class"),
            )
        elif notif_type == "duty_started":
            success, bad_tokens = notify_duty_start(
                teacher_tokens=tokens,
                lang=lang,
                duty_type=ctx["duty_type"],
                location=ctx["location_ar"] if lang == "ar" else ctx["location_en"],
                grade_class=ctx.get("grade_class"),
            )
        else:
            logger.error("[reminders] Unknown notif_type: %s", notif_type)
            return

        # ── Clean up invalid tokens ───────────────────────────────────────────
        if bad_tokens:
            remove_invalid_tokens(db, bad_tokens)

        # ── Record delivery only on confirmed success ─────────────────────────
        # If success == 0, status = "failed" which does NOT write to notification_logs,
        # allowing the next tick to retry.
        status = "sent" if success > 0 else "failed"
        _mark_sent(db, teacher_id, assignment_id, notif_type, status)
        db.commit()

        if success > 0:
            logger.info(
                "[reminders] ✓ %s → teacher=%d assignment=%d (%d/%d tokens OK)",
                notif_type, teacher_id, assignment_id, success, len(tokens),
            )

    except Exception as exc:
        logger.exception(
            "[reminders] Unexpected error sending %s for teacher=%d: %s",
            notif_type, teacher_id, exc,
        )
        try:
            db.rollback()
        except Exception:
            pass


# ── Main job ──────────────────────────────────────────────────────────────────

def run_duty_reminders() -> None:
    """
    Core job function. Called by APScheduler every 60 seconds.

    Scans today's published assignments against two time windows:
      reminder_15m  →  13–16 minutes before shift start
      duty_started  →  0–2 minutes after shift start
    """
    now   = _muscat_now()
    today = now.date()

    logger.debug("[reminders] tick at %s", now.strftime("%Y-%m-%d %H:%M:%S"))

    db: Session = SessionLocal()
    try:
        assignments = (
            db.query(Assignment)
            .join(ShiftLocation, Assignment.shift_location_id == ShiftLocation.id)
            .join(DayPlan,       ShiftLocation.day_plan_id == DayPlan.id)
            .join(WeekPlan,      DayPlan.week_plan_id == WeekPlan.id)
            .options(
                joinedload(Assignment.shift_location).joinedload(ShiftLocation.shift),
                joinedload(Assignment.shift_location).joinedload(ShiftLocation.location),
                joinedload(Assignment.shift_location).joinedload(ShiftLocation.day_plan),
            )
            .filter(
                DayPlan.date         == today,
                DayPlan.is_published.is_(True),
                Assignment.teacher_id.isnot(None),
            )
            .all()
        )

        if not assignments:
            logger.debug("[reminders] No published assignments for %s", today)
            return

        reminder_count = 0
        start_count    = 0

        for a in assignments:
            try:
                start_time  = a.shift_location.shift.start_time
                shift_dt    = datetime.combine(today, start_time)      # naive Muscat
                mins_away   = (shift_dt - now).total_seconds() / 60    # positive = future

                ctx = _build_ctx(a)

                # ── 15-min reminder window ────────────────────────────────────
                # Fire when 13 <= mins_away < 16  (3-minute safe window)
                if REMINDER_WINDOW_MIN <= mins_away < REMINDER_WINDOW_MAX:
                    _send_one(db, ctx, "reminder_15m")
                    reminder_count += 1

                # ── Duty started window ───────────────────────────────────────
                # Fire when -2 < mins_away <= 0  (2-minute window past start)
                elif -START_WINDOW_AFTER < mins_away <= START_WINDOW_BEFORE:
                    _send_one(db, ctx, "duty_started")
                    start_count += 1

            except Exception as exc:
                logger.error(
                    "[reminders] Error processing assignment id=%d: %s",
                    a.id, exc,
                )

        if reminder_count or start_count:
            logger.info(
                "[reminders] %s — reminder_15m=%d duty_started=%d",
                today, reminder_count, start_count,
            )

    except Exception as exc:
        logger.exception("[reminders] Unexpected top-level error: %s", exc)
    finally:
        db.close()


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [duty_reminders] %(levelname)s: %(message)s",
    )
    logger.info("Running duty_reminders manually (one tick)...")
    run_duty_reminders()
    logger.info("Done.")


if __name__ == "__main__":
    main()
