"""
week_service.py — Week plan creation, cloning, assignment, and publishing.

Public API consumed by routers/weeks.py and jobs/auto_clone.py:
  get_current_week_start()          → date (Sunday, Asia/Muscat)
  create_week_plan(...)             → WeekPlan
  clone_week(...)                   → WeekPlan | None
  update_shift_location_slots(...)
  update_assignment(...)
  publish_week(...)
  _notify_assigned_teachers(...)    (internal, called from weeks.py inline)
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import pytz
from sqlalchemy.orm import Session

from models.models import (
    WeekPlan, DayPlan, ShiftLocation,
    Assignment, ChangeLog, Teacher, DeviceToken,
)

logger = logging.getLogger(__name__)

MUSCAT_TZ = pytz.timezone("Asia/Muscat")
WEEK_DAYS = 5  # Sun–Thu (Oman working week)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_current_week_start() -> date:
    """
    Return the Sunday that starts the current school week (Asia/Muscat timezone).
    isoweekday(): Mon=1 … Sun=7. (isoweekday % 7) gives days-since-Sunday.
    """
    now = datetime.now(MUSCAT_TZ).date()
    days_since_sunday = now.isoweekday() % 7   # Sun=0, Mon=1, …, Sat=6
    return now - timedelta(days=days_since_sunday)


def _log_change(
    db: Session,
    week: WeekPlan,
    actor: str,
    action: str,
    payload: Optional[dict] = None,
) -> None:
    entry = ChangeLog(
        week_plan_id=week.id,
        actor=str(actor),
        action=action,
        payload_json=json.dumps(payload) if payload else None,
    )
    db.add(entry)


# ── Week creation ─────────────────────────────────────────────────────────────

def create_week_plan(db: Session, week_start: date, actor: str = "admin") -> WeekPlan:
    """Create a new empty draft WeekPlan for the given Sunday start date."""
    week = WeekPlan(week_start_date=week_start, status="draft", version=1)
    db.add(week)
    db.flush()

    for i in range(WEEK_DAYS):
        db.add(DayPlan(week_plan_id=week.id, date=week_start + timedelta(days=i)))

    _log_change(db, week, actor, "create_week", {"week_start": str(week_start)})
    db.commit()
    db.refresh(week)
    logger.info(f"Created empty week plan for {week_start} (id={week.id})")
    return week


# ── Week cloning ──────────────────────────────────────────────────────────────

def clone_week(
    db: Session,
    source_week_start: date,
    target_week_start: date,
    actor: str = "admin",
) -> Optional[WeekPlan]:
    """
    Clone source week → new draft week at target_week_start.
    Copies DayPlans, ShiftLocations, and Assignments (including grade_class).
    Returns None if target already exists or source not found.
    """
    if db.query(WeekPlan).filter(WeekPlan.week_start_date == target_week_start).first():
        logger.warning(f"clone_week: target {target_week_start} already exists.")
        return None

    source = db.query(WeekPlan).filter(WeekPlan.week_start_date == source_week_start).first()
    if not source:
        logger.error(f"clone_week: source {source_week_start} not found.")
        return None

    day_offset = target_week_start - source_week_start

    new_week = WeekPlan(
        week_start_date=target_week_start,
        status="draft",
        version=1,
        cloned_from_week_start=source_week_start,
    )
    db.add(new_week)
    db.flush()

    for src_day in source.day_plans:
        new_day = DayPlan(week_plan_id=new_week.id, date=src_day.date + day_offset)
        db.add(new_day)
        db.flush()

        for src_sl in src_day.shift_locations:
            new_sl = ShiftLocation(
                day_plan_id=new_day.id,
                shift_id=src_sl.shift_id,
                location_id=src_sl.location_id,
                slots_count=src_sl.slots_count,
                order=src_sl.order,
            )
            db.add(new_sl)
            db.flush()

            for src_a in src_sl.assignments:
                db.add(Assignment(
                    shift_location_id=new_sl.id,
                    slot_index=src_a.slot_index,
                    teacher_id=src_a.teacher_id,
                    grade_class=src_a.grade_class,
                ))

    _log_change(db, new_week, actor, "clone_week", {
        "source": str(source_week_start),
        "target": str(target_week_start),
    })
    db.commit()
    db.refresh(new_week)
    logger.info(f"Cloned {source_week_start} → {target_week_start} (id={new_week.id})")
    return new_week


# ── Slot management ───────────────────────────────────────────────────────────

def update_shift_location_slots(
    db: Session,
    week: WeekPlan,
    day_date: date,
    shift_id: int,
    location_id: Optional[int],
    slots_count: int,
    actor: str = "admin",
) -> ShiftLocation:
    """
    Set the number of assignment slots for a shift+location on a given day.
    Finds or creates DayPlan / ShiftLocation rows as needed.
    Pads or trims Assignment rows to match slots_count.
    """
    day = db.query(DayPlan).filter(
        DayPlan.week_plan_id == week.id,
        DayPlan.date == day_date,
    ).first()
    if not day:
        day = DayPlan(week_plan_id=week.id, date=day_date)
        db.add(day)
        db.flush()

    sl = db.query(ShiftLocation).filter(
        ShiftLocation.day_plan_id == day.id,
        ShiftLocation.shift_id == shift_id,
    ).first()
    if not sl:
        sl = ShiftLocation(
            day_plan_id=day.id,
            shift_id=shift_id,
            location_id=location_id,
            slots_count=slots_count,
            order=0,
        )
        db.add(sl)
        db.flush()
    else:
        sl.location_id = location_id
        sl.slots_count = slots_count

    existing = sorted(sl.assignments, key=lambda a: a.slot_index)
    current = len(existing)
    if slots_count > current:
        for idx in range(current, slots_count):
            db.add(Assignment(shift_location_id=sl.id, slot_index=idx, teacher_id=None))
    elif slots_count < current:
        for a in existing[slots_count:]:
            db.delete(a)

    _log_change(db, week, actor, "update_slots", {
        "day": str(day_date), "shift_id": shift_id,
        "location_id": location_id, "slots_count": slots_count,
    })
    db.commit()
    db.refresh(sl)
    return sl


# ── Assignment management ─────────────────────────────────────────────────────

def update_assignment(
    db: Session,
    week: WeekPlan,
    shift_location_id: int,
    slot_index: int,
    teacher_id: Optional[int],
    grade_class: Optional[str],
    actor: str = "admin",
) -> Assignment:
    """
    Assign or clear a teacher for a slot. Stores grade_class for break duties.
    Raises ValueError if the ShiftLocation does not belong to this week.
    """
    sl = db.query(ShiftLocation).filter(ShiftLocation.id == shift_location_id).first()
    if not sl:
        raise ValueError(f"ShiftLocation {shift_location_id} not found")

    day = db.query(DayPlan).filter(DayPlan.id == sl.day_plan_id).first()
    if not day or day.week_plan_id != week.id:
        raise ValueError(
            f"ShiftLocation {shift_location_id} does not belong to week {week.week_start_date}"
        )

    assignment = db.query(Assignment).filter(
        Assignment.shift_location_id == shift_location_id,
        Assignment.slot_index == slot_index,
    ).first()
    if not assignment:
        assignment = Assignment(shift_location_id=shift_location_id, slot_index=slot_index)
        db.add(assignment)

    # Guard: a teacher may not occupy more than one slot within the same
    # ShiftLocation (same shift + same day + same time).
    # They are still free to appear in multiple ShiftLocations across the day/week.
    if teacher_id is not None:
        conflict = db.query(Assignment).filter(
            Assignment.shift_location_id == shift_location_id,
            Assignment.teacher_id == teacher_id,
            Assignment.slot_index != slot_index,   # a different slot in the same block
        ).first()
        if conflict:
            raise ValueError(
                f"Teacher {teacher_id} is already assigned to another slot "
                f"in the same shift block (shift_location_id={shift_location_id}). "
                f"A teacher can only cover one slot per shift per day."
            )

    assignment.teacher_id = teacher_id
    assignment.grade_class = grade_class

    _log_change(db, week, actor, "update_assignment", {
        "shift_location_id": shift_location_id,
        "slot_index": slot_index,
        "teacher_id": teacher_id,
        "grade_class": grade_class,
    })
    db.commit()
    db.refresh(assignment)
    return assignment


# ── Publishing ────────────────────────────────────────────────────────────────

def publish_week(db: Session, week: WeekPlan, actor: str = "admin") -> WeekPlan:
    """Publish a draft week and notify all assigned teachers."""
    week.status = "published"
    week.version = (week.version or 0) + 1
    _log_change(db, week, actor, "publish", {"version": week.version})
    db.commit()
    db.refresh(week)
    logger.info(f"Week {week.week_start_date} published (v{week.version})")
    _notify_assigned_teachers(db, week)
    return week


# ── Notifications ─────────────────────────────────────────────────────────────

def _notify_assigned_teachers(db: Session, week: WeekPlan) -> None:
    """
    Send a schedule-updated FCM notification to every teacher assigned this week.
    Silent no-op if Firebase is not initialised.
    """
    try:
        from services.notification_service import notify_teacher_updated
    except Exception:
        return

    teacher_ids: set[int] = set()
    for day in week.day_plans:
        for sl in day.shift_locations:
            for a in sl.assignments:
                if a.teacher_id is not None:
                    teacher_ids.add(int(a.teacher_id))

    for tid in teacher_ids:
        teacher = db.query(Teacher).filter(Teacher.id == tid).first()
        if not teacher:
            continue
        tokens = [
            str(dt.token)
            for dt in db.query(DeviceToken).filter(DeviceToken.teacher_id == tid).all()
        ]
        if tokens:
            lang = str(teacher.preferred_language) if teacher.preferred_language else "ar"
            notify_teacher_updated(tokens, lang)