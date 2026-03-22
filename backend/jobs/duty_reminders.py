#!/usr/bin/env python3
"""
jobs/duty_reminders.py — Duty reminder notification job.
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
    Assignment, ShiftLocation, DayPlan, WeekPlan,
    Teacher, DeviceToken, Shift,
)

logger = logging.getLogger("firduty.jobs.duty_reminders")

MUSCAT_TZ = pytz.timezone("Asia/Muscat")

REMINDER_WIN_MIN = 10
REMINDER_WIN_MAX = 20
START_WIN_EARLY  = 3
START_WIN_LATE   = 2


def _muscat_now() -> datetime:
    return datetime.now(MUSCAT_TZ)


def _utcnow() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _already_sent(db: Session, teacher_id: int, assignment_id: int, notif_type: str) -> bool:
    """
    Fallback dedup check.

    Production safety uses _claim_notification() first, but this helper remains
    useful as a defensive fallback and for readable logs.
    """
    try:
        from models.notification_log import NotificationLog
        row = (
            db.query(NotificationLog)
            .filter(
                NotificationLog.teacher_id == teacher_id,
                NotificationLog.assignment_id == assignment_id,
                NotificationLog.notification_type == notif_type,
            )
            .first()
        )
        return row is not None and str(getattr(row, "status", "")) in {"processing", "sent", "skipped"}
    except Exception as exc:
        logger.error(
            "[reminders] _already_sent DB error teacher=%d assignment=%d type=%s: %s — treating as already-sent",
            teacher_id, assignment_id, notif_type, exc,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return True


def _claim_notification(db: Session, teacher_id: int, assignment_id: int, notif_type: str) -> bool:
    """
    Atomically claim a notification slot BEFORE sending.

    This is the production-safe dedup mechanism:
      - first scheduler tick INSERTs a row with status='processing'
      - later ticks hit UNIQUE conflict and skip
      - after successful FCM send, the row is updated to status='sent'

    This removes the race in the old flow:
      already_sent? -> send -> insert log
    where 2 workers could both send before either inserts.
    """
    try:
        from models.notification_log import NotificationLog
        log = NotificationLog(
            teacher_id=teacher_id,
            assignment_id=assignment_id,
            notification_type=notif_type,
            sent_at=_utcnow(),
            status="processing",
        )
        db.add(log)
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        logger.info(
            "[reminders] skip %s teacher=%d assignment=%d (already claimed/sent)",
            notif_type, teacher_id, assignment_id,
        )
        return False
    except Exception as exc:
        logger.error(
            "[reminders] _claim_notification error teacher=%d assignment=%d type=%s: %s",
            teacher_id, assignment_id, notif_type, exc,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return False


def _finalize_claim(
    db: Session,
    teacher_id: int,
    assignment_id: int,
    notif_type: str,
    status: str,
) -> None:
    """
    Finalize a previously claimed notification row.

    status:
      sent      -> keep dedup locked forever for this assignment/type
      skipped   -> keep dedup locked (no tokens)
      failed    -> release claim so next tick can retry
    """
    try:
        from models.notification_log import NotificationLog
        row = (
            db.query(NotificationLog)
            .filter(
                NotificationLog.teacher_id == teacher_id,
                NotificationLog.assignment_id == assignment_id,
                NotificationLog.notification_type == notif_type,
            )
            .first()
        )
        if not row:
            return

        if status == "failed":
            db.delete(row)
        else:
            row.status = status
            row.sent_at = _utcnow()
        db.commit()
    except Exception as exc:
        logger.error(
            "[reminders] _finalize_claim error teacher=%d assignment=%d type=%s status=%s: %s",
            teacher_id, assignment_id, notif_type, status, exc,
        )
        try:
            db.rollback()
        except Exception:
            pass


def _build_ctx(a: Assignment) -> dict:
    sl: ShiftLocation = a.shift_location
    shift: Shift = sl.shift
    duty_type = str(shift.duty_type)

    loc_en = loc_ar = None
    if duty_type == "morning_endofday" and sl.location:
        loc_en = sl.location.name_en
        loc_ar = sl.location.name_ar

    return {
        "assignment_id": a.id,
        "teacher_id": int(a.teacher_id),
        "duty_type": duty_type,
        "shift_name_en": shift.name_en,
        "shift_name_ar": shift.name_ar,
        "grade_class": a.grade_class,
        "location_en": loc_en,
        "location_ar": loc_ar,
        "start_time": shift.start_time,
    }


def _get_teacher_tokens(db: Session, teacher_id: int) -> list[str]:
    rows = (
        db.query(DeviceToken)
        .filter(DeviceToken.teacher_id == teacher_id)
        .order_by(DeviceToken.updated_at.desc(), DeviceToken.id.desc())
        .all()
    )

    tokens: list[str] = []
    seen_keys: set[str] = set()
    seen_tokens: set[str] = set()

    for row in rows:
        token = str(getattr(row, "token", "") or "").strip()
        if not token or token in seen_tokens:
            continue

        installation_id = str(getattr(row, "installation_id", "") or "").strip()
        dedupe_key = installation_id or f"token:{token}"
        if dedupe_key in seen_keys:
            continue

        seen_keys.add(dedupe_key)
        seen_tokens.add(token)
        tokens.append(token)

    return tokens


def _send_one(db: Session, ctx: dict, notif_type: str) -> None:
    teacher_id = ctx["teacher_id"]
    assignment_id = ctx["assignment_id"]

    # Defensive fast-path check for readability in logs.
    if _already_sent(db, teacher_id, assignment_id, notif_type):
        logger.info(
            "[reminders] skip %s teacher=%d assignment=%d (already sent / already processing)",
            notif_type, teacher_id, assignment_id,
        )
        return

    # Production-safe claim before external side effect.
    if not _claim_notification(db, teacher_id, assignment_id, notif_type):
        return

    tokens = _get_teacher_tokens(db, teacher_id)
    if not tokens:
        logger.info(
            "[reminders] teacher=%d has no device tokens — skipping %s",
            teacher_id, notif_type,
        )
        _finalize_claim(db, teacher_id, assignment_id, notif_type, "skipped")
        return

    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    lang = str(teacher.preferred_language) if teacher and teacher.preferred_language else "ar"

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
            _finalize_claim(db, teacher_id, assignment_id, notif_type, "failed")
            return

        if bad_tokens:
            remove_invalid_tokens(db, bad_tokens)

        if success > 0:
            _finalize_claim(db, teacher_id, assignment_id, notif_type, "sent")
            logger.info(
                "[reminders] ✓ %s → teacher=%d assignment=%d lang=%s (%d/%d tokens OK)",
                notif_type, teacher_id, assignment_id, lang, success, len(tokens),
            )
        else:
            logger.warning(
                "[reminders] FCM delivery FAILED for teacher=%d assignment=%d type=%s — will retry on next tick.",
                teacher_id, assignment_id, notif_type,
            )
            _finalize_claim(db, teacher_id, assignment_id, notif_type, "failed")

    except Exception as exc:
        logger.exception(
            "[reminders] Unexpected error sending %s for teacher=%d assignment=%d: %s",
            notif_type, teacher_id, assignment_id, exc,
        )
        _finalize_claim(db, teacher_id, assignment_id, notif_type, "failed")
        try:
            db.rollback()
        except Exception:
            pass


def run_duty_reminders() -> None:
    now = _muscat_now()
    today = now.date()

    logger.info("[reminders] tick: now=%s muscat_date=%s", now.strftime("%H:%M:%S"), today)

    db: Session = SessionLocal()
    try:
        assignments = (
            db.query(Assignment)
            .join(ShiftLocation, Assignment.shift_location_id == ShiftLocation.id)
            .join(DayPlan, ShiftLocation.day_plan_id == DayPlan.id)
            .join(WeekPlan, DayPlan.week_plan_id == WeekPlan.id)
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
            logger.info("[reminders] No published assignments for %s — nothing to send.", today)
            return

        logger.info(
            "[reminders] Found %d published assignment(s) for %s — checking windows...",
            len(assignments), today,
        )

        reminder_count = 0
        start_count = 0

        for a in assignments:
            try:
                start_time = a.shift_location.shift.start_time
                shift_dt = MUSCAT_TZ.localize(datetime.combine(today, start_time))
                mins_away = (shift_dt - now).total_seconds() / 60

                logger.info(
                    "[REMINDER DEBUG] assignment=%d teacher=%d shift=%s now=%s mins_away=%.2f | reminder_win=[%d,%d] start_win=[-%d,+%d]",
                    a.id,
                    int(a.teacher_id),
                    shift_dt.strftime("%H:%M"),
                    now.strftime("%H:%M:%S"),
                    mins_away,
                    REMINDER_WIN_MIN, REMINDER_WIN_MAX,
                    START_WIN_LATE, START_WIN_EARLY,
                )

                ctx = _build_ctx(a)

                if REMINDER_WIN_MIN <= mins_away <= REMINDER_WIN_MAX:
                    logger.info("[reminders] → REMINDER WINDOW HIT: assignment=%d mins_away=%.2f", a.id, mins_away)
                    _send_one(db, ctx, "reminder_15m")
                    reminder_count += 1
                elif -START_WIN_LATE <= mins_away <= START_WIN_EARLY:
                    logger.info("[reminders] → START WINDOW HIT: assignment=%d mins_away=%.2f", a.id, mins_away)
                    _send_one(db, ctx, "duty_started")
                    start_count += 1
            except Exception as exc:
                logger.error("[reminders] Error processing assignment id=%d: %s", a.id, exc)
                try:
                    db.rollback()
                except Exception:
                    pass

        logger.info(
            "[reminders] tick complete: date=%s reminder_15m=%d duty_started=%d",
            today, reminder_count, start_count,
        )

    except Exception as exc:
        logger.exception("[reminders] Unexpected top-level error: %s", exc)
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [duty_reminders] %(levelname)s: %(message)s")
    logger.info("Running duty_reminders manually (one tick)...")
    run_duty_reminders()
    logger.info("Done.")


if __name__ == "__main__":
    main()
