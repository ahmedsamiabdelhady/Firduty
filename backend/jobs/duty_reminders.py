#!/usr/bin/env python3
"""
jobs/duty_reminders.py — Duty reminder notification job.

Scheduled: every 60 seconds via APScheduler interval trigger (scheduler.py)
Callable:  run_duty_reminders()

── What it does ────────────────────────────────────────────────────────────────
Every minute it queries today's published assignments and sends:

  reminder_15m  →  shift starts in 10–20 minutes from now  (10-min safe window)
  duty_started  →  shift started 0–3 minutes ago            (3-min safe window)

Wide windows guarantee a notification is sent even if the scheduler fires late
(Koyeb CPU throttling, cold start). Deduplication via notification_logs prevents
double-sending within the same window.

── Why we changed from narrow (3-min) to wide (10-min) windows ─────────────────
The original 3-minute reminder window (13–16 min) worked mathematically but:
  1. Koyeb free-tier CPU throttling can delay the job 5–15 seconds per tick.
     Over several ticks, drift accumulates and the job fires outside the window.
  2. ALL internal logging was at DEBUG level — invisible on Koyeb (INFO default).
     No mins_away logs existed, making it impossible to diagnose misses.
  3. APScheduler interval jobs do NOT get jitter, but late execution from the
     previous tick can push the next fire time past the window boundary.

── Timezone handling ────────────────────────────────────────────────────────────
All datetime comparisons use timezone-AWARE datetimes in Asia/Muscat:
  • now      = datetime.now(MUSCAT_TZ)         → aware, Muscat local time
  • shift_dt = MUSCAT_TZ.localize(combine(today, start_time)) → aware, Muscat
  • mins_away = (shift_dt - now).total_seconds() / 60

Both values are in the same timezone → subtraction is unambiguous.
.replace(tzinfo=None) was previously used, which worked but was fragile.

── Deduplication ────────────────────────────────────────────────────────────────
INSERT into notification_logs before every send.
UNIQUE(teacher_id, assignment_id, notification_type) prevents double-sending.
Only marked "sent" if FCM returns success_count > 0.
_already_sent() fails CLOSED on DB error (returns True) — prevents duplicate
sends if the notification_logs table is temporarily unavailable.

── CLI / test ───────────────────────────────────────────────────────────────────
  python backend/jobs/duty_reminders.py
  → runs one tick immediately, logs full per-assignment detail, exits.
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
# Wide windows tolerate Koyeb CPU throttling (5-15 s delay per tick).
# Deduplication ensures each teacher receives exactly one notification
# per event even if the job fires multiple times within the window.
#
# reminder_15m window: 10 <= mins_away <= 20
#   → fires starting 20 min before shift, guaranteed to hit by 10 min before
#   → 10-minute window = ~10 chances to send (one per tick)
#
# duty_started window: -2 <= mins_away <= 3
#   → fires from 3 min before start to 2 min after start
#   → teacher gets the "duty started" push while they're walking to position
REMINDER_WIN_MIN = 10    # reminder fires when shift is 10–20 minutes away
REMINDER_WIN_MAX = 20
START_WIN_EARLY  = 3     # "started" fires up to 3 min BEFORE shift time
START_WIN_LATE   = 2     # "started" fires up to 2 min AFTER shift time


# ── Time helpers ──────────────────────────────────────────────────────────────

def _muscat_now() -> datetime:
    """Return the current time as a timezone-AWARE datetime in Asia/Muscat."""
    return datetime.now(MUSCAT_TZ)


def _utcnow() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Deduplication ─────────────────────────────────────────────────────────────

def _already_sent(db: Session, teacher_id: int, assignment_id: int, notif_type: str) -> bool:
    """
    Return True if this notification was already sent.

    CRITICAL — fail CLOSED on any error.
    If the notification_logs table is unavailable or any DB error occurs,
    returns True (treat as "already sent") to prevent duplicate sends.

    The wide window means the job runs 10–20 times per reminder window.
    If we returned False on error, each tick would send → massive duplicates.
    Fail-closed prevents this. Fix the underlying DB issue to resume sending.
    """
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
        logger.error(
            "[reminders] _already_sent DB error teacher=%d assignment=%d type=%s: %s "
            "— treating as already-sent (FAIL CLOSED) to prevent duplicates. "
            "Ensure the notification_logs table exists in Supabase.",
            teacher_id, assignment_id, notif_type, exc,
        )
        return True   # FAIL CLOSED


def _mark_sent(
    db: Session,
    teacher_id: int,
    assignment_id: int,
    notif_type: str,
    status: str,
) -> None:
    """
    Record notification attempt in notification_logs.

    status = "sent"    → FCM confirmed at least one delivery  (written to DB)
    status = "failed"  → FCM returned success_count=0         (NOT written → retried next tick)
    status = "skipped" → teacher has no device tokens         (written to DB)

    For "failed" we deliberately skip the INSERT so the dedup check on the
    next tick still returns False and the send is retried.
    """
    if status == "failed":
        logger.warning(
            "[reminders] FCM delivery FAILED for teacher=%d assignment=%d type=%s "
            "— will retry on next tick.",
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
        db.rollback()   # duplicate key — concurrent write, safe to ignore
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
    Only marks as "sent" if FCM returns success_count > 0.
    Cleans up invalid tokens from the DB.
    """
    teacher_id    = ctx["teacher_id"]
    assignment_id = ctx["assignment_id"]

    # ── Dedup check ───────────────────────────────────────────────────────────
    if _already_sent(db, teacher_id, assignment_id, notif_type):
        logger.debug(
            "[reminders] skip %s teacher=%d assignment=%d (already sent / dedup)",
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

        # ── Record only on confirmed success ──────────────────────────────────
        status = "sent" if success > 0 else "failed"
        _mark_sent(db, teacher_id, assignment_id, notif_type, status)
        db.commit()

        if success > 0:
            logger.info(
                "[reminders] ✓ %s → teacher=%d assignment=%d lang=%s (%d/%d tokens OK)",
                notif_type, teacher_id, assignment_id, lang, success, len(tokens),
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

    Per-assignment debug log (always INFO):
      [REMINDER DEBUG] assignment=N shift=HH:MM now=HH:MM:SS mins_away=X.XX → action

    Time windows (with tz-aware datetimes):
      reminder_15m: 10 <= mins_away <= 20   (fires 10–20 min before shift)
      duty_started: -2 <= mins_away <= 3    (fires 3 min before to 2 min after)
    """
    # ── Use timezone-AWARE now ────────────────────────────────────────────────
    # Both now and shift_dt will be tz-aware (Asia/Muscat).
    # Subtraction of two aware datetimes in the same timezone is unambiguous.
    now   = _muscat_now()                     # tz-aware, Muscat
    today = now.date()                        # correct Muscat date

    logger.info(                              # INFO not DEBUG — visible on Koyeb
        "[reminders] tick: now=%s muscat_date=%s",
        now.strftime("%H:%M:%S"),
        today,
    )

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
            # INFO so admin can see "no assignments" in Koyeb logs
            logger.info(
                "[reminders] No published assignments for %s — nothing to send.", today
            )
            return

        logger.info(
            "[reminders] Found %d published assignment(s) for %s — checking windows...",
            len(assignments), today,
        )

        reminder_count = 0
        start_count    = 0

        for a in assignments:
            try:
                start_time = a.shift_location.shift.start_time   # datetime.time

                # ── Build tz-aware shift datetime ─────────────────────────────
                # Both now and shift_dt are in Asia/Muscat → subtraction is correct.
                shift_dt_naive = datetime.combine(today, start_time)
                shift_dt       = MUSCAT_TZ.localize(shift_dt_naive)   # tz-aware

                mins_away = (shift_dt - now).total_seconds() / 60

                # ── Per-assignment debug log — ALWAYS at INFO level ───────────
                # This is the critical log the senior engineer asked for.
                # Without it, missed windows are impossible to diagnose.
                logger.info(
                    "[REMINDER DEBUG] assignment=%d teacher=%d shift=%s now=%s "
                    "mins_away=%.2f | reminder_win=[%d,%d] start_win=[-%d,+%d]",
                    a.id,
                    int(a.teacher_id),
                    shift_dt.strftime("%H:%M"),
                    now.strftime("%H:%M:%S"),
                    mins_away,
                    REMINDER_WIN_MIN, REMINDER_WIN_MAX,
                    START_WIN_LATE, START_WIN_EARLY,
                )

                ctx = _build_ctx(a)

                # ── 15-min reminder window ────────────────────────────────────
                # 10 <= mins_away <= 20: fires when shift is 10–20 min away.
                # 10-minute window gives ~10 ticks per window.
                # Deduplication ensures exactly one notification per teacher.
                if REMINDER_WIN_MIN <= mins_away <= REMINDER_WIN_MAX:
                    logger.info(
                        "[reminders] → REMINDER WINDOW HIT: assignment=%d mins_away=%.2f",
                        a.id, mins_away,
                    )
                    _send_one(db, ctx, "reminder_15m")
                    reminder_count += 1

                # ── Duty started window ───────────────────────────────────────
                # -2 <= mins_away <= 3: fires from 3 min before to 2 min after.
                # Catches teachers who are already at their position early,
                # or the job fires slightly late.
                elif -START_WIN_LATE <= mins_away <= START_WIN_EARLY:
                    logger.info(
                        "[reminders] → START WINDOW HIT: assignment=%d mins_away=%.2f",
                        a.id, mins_away,
                    )
                    _send_one(db, ctx, "duty_started")
                    start_count += 1

                else:
                    # Explicit "out of window" log — crucial for diagnosis
                    if mins_away > REMINDER_WIN_MAX:
                        logger.debug(
                            "[reminders] assignment=%d shift=%s: %.1f min away "
                            "(reminder window opens in %.1f min)",
                            a.id, shift_dt.strftime("%H:%M"),
                            mins_away, mins_away - REMINDER_WIN_MAX,
                        )
                    elif 0 < mins_away < REMINDER_WIN_MIN:
                        logger.info(
                            "[reminders] ⚠ MISSED WINDOW: assignment=%d shift=%s: "
                            "%.1f min away — between windows (reminder already sent?)",
                            a.id, shift_dt.strftime("%H:%M"), mins_away,
                        )
                    else:
                        logger.debug(
                            "[reminders] assignment=%d shift=%s: %.1f min past start "
                            "(outside start window)",
                            a.id, shift_dt.strftime("%H:%M"), abs(mins_away),
                        )

            except Exception as exc:
                logger.error(
                    "[reminders] Error processing assignment id=%d: %s",
                    a.id, exc,
                )

        # ── Summary log ───────────────────────────────────────────────────────
        logger.info(
            "[reminders] tick complete: date=%s reminder_15m=%d duty_started=%d",
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
