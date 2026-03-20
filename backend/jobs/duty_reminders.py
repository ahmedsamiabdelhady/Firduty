#!/usr/bin/env python3
"""
jobs/duty_reminders.py — Duty reminder notification job.

Scheduled: every minute (interval trigger, registered in scheduler.py)
Callable:  run_duty_reminders()

Logic per run:
  1. Resolve current Oman time (Asia/Muscat).
  2. Find all published assignments whose shift starts in the next 15–16 minutes
     → send "reminder_15m" notifications (deduplicated by notification_logs).
  3. Find all published assignments whose shift started 0–1 minutes ago
     → send "duty_started" notifications (deduplicated).

Deduplication:
  Before every send we try to INSERT a row into notification_logs.
  If the row already exists (UNIQUE constraint) we skip — no double-fire.

Timezone:
  Shift times are stored as bare TIME values in the database with no timezone.
  We interpret them as Asia/Muscat local time (correct for this school system).

Safety:
  - All DB errors are caught per-assignment so one bad row doesn't block others.
  - Firebase errors are caught and logged.
  - Running this job more than once per minute is safe (idempotent).
"""

import sys
import os
import logging
from datetime import datetime

import pytz

_backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from database import SessionLocal
from models.models import (
    Assignment, ShiftLocation, DayPlan, WeekPlan, Teacher, DeviceToken, Shift,
)
from models.notification_log import NotificationLog

logger = logging.getLogger("firduty.jobs.duty_reminders")

MUSCAT_TZ   = pytz.timezone("Asia/Muscat")
WINDOW_SECS = 60   # window width (seconds) for matching — matches once per minute


def _utcnow() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _muscat_now() -> datetime:
    return datetime.now(MUSCAT_TZ).replace(tzinfo=None)


def _assignment_context(a: Assignment) -> dict:
    """Extract the context needed for a notification from an assignment."""
    sl: ShiftLocation = a.shift_location
    shift: Shift       = sl.shift
    day: DayPlan       = sl.day_plan
    duty_type          = str(shift.duty_type)

    location_en = location_ar = None
    if duty_type == "morning_endofday" and sl.location:
        location_en = sl.location.name_en
        location_ar = sl.location.name_ar

    return {
        "assignment_id": a.id,
        "teacher_id":    int(a.teacher_id),
        "duty_type":     duty_type,
        "shift_name_en": shift.name_en,
        "shift_name_ar": shift.name_ar,
        "grade_class":   a.grade_class,
        "location_en":   location_en,
        "location_ar":   location_ar,
        "date":          str(day.date),
        "start_time":    shift.start_time,
    }


def _claim_notification(
    db: Session,
    teacher_id: int,
    assignment_id: int,
    notif_type: str,
) -> bool:
    """
    Atomically claim a notification slot using the UNIQUE constraint.

    Returns True only for the first caller that inserts the row. Any later
    duplicate attempt rolls back and returns False, so no second send happens.
    """
    log = NotificationLog(
        teacher_id=teacher_id,
        assignment_id=assignment_id,
        notification_type=notif_type,
        sent_at=_utcnow(),
        status="pending",
    )
    try:
        db.add(log)
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _update_claim_status(
    db: Session,
    teacher_id: int,
    assignment_id: int,
    notif_type: str,
    status: str,
) -> None:
    row = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.teacher_id == teacher_id,
            NotificationLog.assignment_id == assignment_id,
            NotificationLog.notification_type == notif_type,
        )
        .first()
    )
    if row is None:
        return

    row.status = status
    row.sent_at = _utcnow()
    db.commit()


def _get_teacher_tokens(db: Session, teacher_id: int) -> list[str]:
    """
    Return one freshest token per installation for a teacher.

    This protects against duplicated sends when stale rows exist for the same
    installation after token rotation. If installation_id has not been migrated
    yet, this still de-dupes exact repeated tokens as a fallback.
    """
    rows = (
        db.query(DeviceToken)
        .filter(DeviceToken.teacher_id == teacher_id)
        .order_by(DeviceToken.last_seen_at.desc(), DeviceToken.created_at.desc())
        .all()
    )

    by_installation: dict[str, str] = {}
    seen_tokens: set[str] = set()

    for row in rows:
        token = (row.token or "").strip()
        if not token or token in seen_tokens:
            continue

        installation_id = str(getattr(row, "installation_id", "") or "").strip()
        key = installation_id or f"token:{token}"
        if key in by_installation:
            continue

        by_installation[key] = token
        seen_tokens.add(token)

    return list(by_installation.values())


def _get_teacher_lang(db: Session, teacher_id: int) -> str:
    t = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if t and t.preferred_language:
        return str(t.preferred_language)
    return "ar"


# ── Notification dispatch ─────────────────────────────────────────────────────

def _send_one(db: Session, ctx: dict, notif_type: str) -> None:
    """Send exactly one notification per teacher/assignment/type."""
    teacher_id = ctx["teacher_id"]
    assignment_id = ctx["assignment_id"]

    if not _claim_notification(db, teacher_id, assignment_id, notif_type):
        logger.debug(
            "[reminders] skip %s for teacher=%d assignment=%d (already claimed)",
            notif_type, teacher_id, assignment_id,
        )
        return

    tokens = _get_teacher_tokens(db, teacher_id)
    if not tokens:
        logger.debug(
            "[reminders] teacher=%d has no device tokens — skipping %s",
            teacher_id, notif_type,
        )
        try:
            _update_claim_status(db, teacher_id, assignment_id, notif_type, "skipped")
        except Exception:
            db.rollback()
        return

    lang = _get_teacher_lang(db, teacher_id)

    try:
        from services.notification_service import notify_duty_reminder, notify_duty_start

        if notif_type == "reminder_15m":
            notify_duty_reminder(
                teacher_tokens=tokens,
                lang=lang,
                shift=ctx["shift_name_ar"] if lang == "ar" else ctx["shift_name_en"],
                duty_type=ctx["duty_type"],
                location=ctx["location_ar"] if lang == "ar" else ctx["location_en"],
                grade_class=ctx.get("grade_class"),
            )
        elif notif_type == "duty_started":
            notify_duty_start(
                teacher_tokens=tokens,
                lang=lang,
                duty_type=ctx["duty_type"],
                location=ctx["location_ar"] if lang == "ar" else ctx["location_en"],
                grade_class=ctx.get("grade_class"),
            )
        else:
            logger.warning(
                "[reminders] unknown notification type '%s' for teacher=%d assignment=%d",
                notif_type, teacher_id, assignment_id,
            )
            _update_claim_status(db, teacher_id, assignment_id, notif_type, "failed")
            return

        _update_claim_status(db, teacher_id, assignment_id, notif_type, "sent")
        logger.info(
            "[reminders] sent %s → teacher=%d assignment=%d tokens=%d",
            notif_type, teacher_id, assignment_id, len(tokens),
        )
    except Exception as exc:
        logger.error(
            "[reminders] failed to send %s for teacher=%d assignment=%d: %s",
            notif_type, teacher_id, assignment_id, exc,
        )
        try:
            _update_claim_status(db, teacher_id, assignment_id, notif_type, "failed")
        except Exception:
            db.rollback()


# ── Main job ──────────────────────────────────────────────────────────────────

def run_duty_reminders() -> None:
    """
    Core duty-reminder logic. Called by APScheduler every minute.

    Finds published assignments in two time windows:
      - 15-minute window: start_time is 14m00s – 15m00s from now → reminder_15m
      - 0-minute window:  start_time is 0m00s  –  1m00s from now → duty_started
    """
    now = _muscat_now()
    logger.debug("[reminders] tick at %s", now.strftime("%Y-%m-%d %H:%M:%S"))

    db: Session = SessionLocal()
    try:
        today = now.date()

        # Load all published assignments for today with eager joins
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
                DayPlan.date == today,
                DayPlan.is_published.is_(True),
                Assignment.teacher_id.isnot(None),
            )
            .all()
        )

        if not assignments:
            logger.debug("[reminders] no published assignments for %s", today)
            return

        reminder_count = 0
        start_count    = 0

        for a in assignments:
            try:
                shift        = a.shift_location.shift
                start_time   = shift.start_time          # datetime.time
                shift_dt     = datetime.combine(today, start_time)   # naive Muscat
                minutes_away = (shift_dt - now).total_seconds() / 60

                ctx = _assignment_context(a)

                # Reminder window is one scheduler tick wide. Duplicate runs are
                # still safe because _claim_notification() is atomic.
                if 14 <= minutes_away < 15:
                    _send_one(db, ctx, "reminder_15m")
                    reminder_count += 1

                if -1 < minutes_away <= 0:
                    _send_one(db, ctx, "duty_started")
                    start_count += 1

            except Exception as exc:
                logger.error(
                    "[reminders] error processing assignment id=%d: %s",
                    a.id, exc,
                )

        if reminder_count or start_count:
            logger.info(
                "[reminders] %s — sent reminder_15m=%d duty_started=%d",
                today, reminder_count, start_count,
            )

    except Exception as exc:
        logger.exception("[reminders] unexpected error: %s", exc)
    finally:
        db.close()


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [duty_reminders] %(levelname)s: %(message)s",
    )
    run_duty_reminders()


if __name__ == "__main__":
    main()
