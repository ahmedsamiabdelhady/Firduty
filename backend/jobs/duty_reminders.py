from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import joinedload

from database import SessionLocal
from models.models import Assignment, DayPlan, ShiftLocation, Teacher
from models.notification_log import NotificationLog
from services.notification_service import send_notification

logger = logging.getLogger("firduty.jobs.duty_reminders")
MUSCAT_TZ = ZoneInfo("Asia/Muscat")


def _truncate_to_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def _claim_notification(
    db,
    teacher_id: int,
    assignment_id: int,
    notif_type: str,
) -> bool:
    existing = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.teacher_id == teacher_id,
            NotificationLog.assignment_id == assignment_id,
            NotificationLog.notification_type == notif_type,
        )
        .first()
    )

    if existing:
        status = str(existing.status or "").lower().strip()

        # Already handled or in-progress
        if status in {"sent", "claimed", "processing"}:
            return False

        # Retry failed/skipped rows
        existing.status = "claimed"
        existing.sent_at = None
        db.commit()
        return True

    db.add(
        NotificationLog(
            teacher_id=teacher_id,
            assignment_id=assignment_id,
            notification_type=notif_type,
            status="claimed",
        )
    )
    db.commit()
    return True


def _mark_status(
    db,
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
    if row:
        row.status = status
        if status == "sent":
            row.sent_at = datetime.now(MUSCAT_TZ)
        db.commit()


def _localized_shift_name(shift, lang: str) -> str:
    is_ar = (lang or "en").lower() == "ar"
    if is_ar:
        return getattr(shift, "name_ar", None) or getattr(shift, "name_en", None) or "المناوبة"
    return getattr(shift, "name_en", None) or getattr(shift, "name_ar", None) or "Duty"


def _localized_location_name(location, lang: str) -> str:
    is_ar = (lang or "en").lower() == "ar"
    if not location:
        return "الموقع غير معروف" if is_ar else "Unknown location"

    if is_ar:
        return (
            getattr(location, "name_ar", None)
            or getattr(location, "name_en", None)
            or "الموقع غير معروف"
        )
    return (
        getattr(location, "name_en", None)
        or getattr(location, "name_ar", None)
        or "Unknown location"
    )


def _build_title_body(
    notif_type: str,
    shift_name: str,
    location_name: str,
    lang: str,
) -> tuple[str, str]:
    is_ar = (lang or "en").lower() == "ar"

    if notif_type == "reminder_15m":
        if is_ar:
            return (
                "تذكير بالمناوبة",
                f"مناوبتك {shift_name} ستبدأ بعد 15 دقيقة في {location_name}.",
            )
        return (
            "Duty reminder",
            f"Your {shift_name} duty starts in 15 minutes at {location_name}.",
        )

    if notif_type == "duty_started":
        if is_ar:
            return (
                "بدأت المناوبة الآن",
                f"بدأت الآن مناوبة {shift_name} في {location_name}.",
            )
        return (
            "Duty started",
            f"Your {shift_name} duty has started now at {location_name}.",
        )

    if is_ar:
        return ("إشعار مناوبة", "لديك إشعار جديد بخصوص المناوبة.")
    return ("Duty notification", "You have a new duty notification.")


def run_duty_reminders() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(MUSCAT_TZ)
        now_minute = _truncate_to_minute(now)
        muscat_date = now.date()

        logger.info(
            "[reminders] tick: now=%s muscat_date=%s",
            now.strftime("%H:%M:%S"),
            muscat_date,
        )

        assignments = (
            db.query(Assignment)
            .join(ShiftLocation, Assignment.shift_location_id == ShiftLocation.id)
            .join(DayPlan, ShiftLocation.day_plan_id == DayPlan.id)
            .join(Teacher, Assignment.teacher_id == Teacher.id)
            .options(
                joinedload(Assignment.teacher),
                joinedload(Assignment.shift_location).joinedload(ShiftLocation.shift),
                joinedload(Assignment.shift_location).joinedload(ShiftLocation.location),
                joinedload(Assignment.shift_location).joinedload(ShiftLocation.day_plan),
            )
            .filter(
                DayPlan.date == muscat_date,
                DayPlan.is_published.is_(True),
                Assignment.teacher_id.isnot(None),
            )
            .all()
        )

        # Extra safety against accidental duplicates from joins
        assignments = list({a.id: a for a in assignments}.values())

        if not assignments:
            logger.info("[reminders] No published assignments for %s — nothing to send.", muscat_date)
            return

        logger.info(
            "[reminders] Found %d unique published assignment(s) for %s — checking exact minute...",
            len(assignments),
            muscat_date,
        )

        sent_reminder = 0
        sent_started = 0

        for assignment in assignments:
            teacher = assignment.teacher
            shift_location = assignment.shift_location
            shift = shift_location.shift if shift_location else None
            location = shift_location.location if shift_location else None
            day_plan = shift_location.day_plan if shift_location else None

            if not teacher or not shift or not day_plan or not shift.start_time:
                continue

            start_dt = datetime.combine(day_plan.date, shift.start_time, tzinfo=MUSCAT_TZ)
            start_dt = _truncate_to_minute(start_dt)
            reminder_dt = _truncate_to_minute(start_dt - timedelta(minutes=15))

            logger.info(
                "[REMINDER DEBUG] assignment=%s teacher=%s now=%s reminder_at=%s start_at=%s",
                assignment.id,
                teacher.id,
                now_minute.strftime("%H:%M:%S"),
                reminder_dt.strftime("%H:%M:%S"),
                start_dt.strftime("%H:%M:%S"),
            )

            notif_type = None
            if now_minute == reminder_dt:
                notif_type = "reminder_15m"
                logger.info("[reminders] → EXACT REMINDER HIT: assignment=%s", assignment.id)
            elif now_minute == start_dt:
                notif_type = "duty_started"
                logger.info("[reminders] → EXACT START HIT: assignment=%s", assignment.id)
            else:
                continue

            claimed = _claim_notification(db, teacher.id, assignment.id, notif_type)
            if not claimed:
                logger.info(
                    "[reminders] skip %s teacher=%s assignment=%s (already claimed/sent)",
                    notif_type,
                    teacher.id,
                    assignment.id,
                )
                continue

            lang = (teacher.preferred_language or "en").lower()
            shift_name = _localized_shift_name(shift, lang)
            location_name = _localized_location_name(location, lang)
            title, body = _build_title_body(notif_type, shift_name, location_name, lang)

            payload = {
                "event_id": f"{notif_type}:{assignment.id}",
                "type": notif_type,
                "notification_type": notif_type,
                "teacher_id": str(teacher.id),
                "assignment_id": str(assignment.id),
                "day_date": str(day_plan.date),
                "shift_name": shift_name,
                "location_name": location_name,
                "title": title,
                "body": body,
            }

            try:
                success_count, invalid_tokens = send_notification(
                    teacher_id=teacher.id,
                    data=payload,
                )

                if success_count > 0:
                    _mark_status(db, teacher.id, assignment.id, notif_type, "sent")
                    logger.info(
                        "[reminders] ✓ %s → teacher=%s assignment=%s lang=%s success=%s invalid=%s",
                        notif_type,
                        teacher.id,
                        assignment.id,
                        lang,
                        success_count,
                        len(invalid_tokens),
                    )
                    if notif_type == "reminder_15m":
                        sent_reminder += 1
                    else:
                        sent_started += 1
                else:
                    _mark_status(db, teacher.id, assignment.id, notif_type, "failed")
                    logger.warning(
                        "[reminders] ✗ %s → teacher=%s assignment=%s (0 tokens succeeded)",
                        notif_type,
                        teacher.id,
                        assignment.id,
                    )

            except Exception:
                _mark_status(db, teacher.id, assignment.id, notif_type, "failed")
                logger.exception(
                    "[reminders] Failed sending %s for teacher=%s assignment=%s",
                    notif_type,
                    teacher.id,
                    assignment.id,
                )

        logger.info(
            "[reminders] tick complete: date=%s reminder_15m=%s duty_started=%s",
            muscat_date,
            sent_reminder,
            sent_started,
        )

    except Exception:
        logger.exception("[reminders] Job crashed unexpectedly.")
    finally:
        db.close()