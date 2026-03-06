"""Business logic for week planning, cloning, and slot management."""

import json
import logging
from datetime import date, timedelta, datetime
from typing import Optional

import pytz
from sqlalchemy.orm import Session

from models.models import (
    WeekPlan, DayPlan, ShiftLocation, Assignment,
    Location, Shift, ChangeLog, Teacher, DeviceToken
)
from services.notification_service import notify_teacher_updated

logger = logging.getLogger(__name__)
MUSCAT_TZ = pytz.timezone("Asia/Muscat")


def get_week_start(for_date: date) -> date:
    """Return the Sunday of the week containing for_date."""
    days_since_sunday = (for_date.weekday() + 1) % 7  # Monday=0, so Sunday = -1 mod 7 = 6 → 0
    return for_date - timedelta(days=days_since_sunday)


def get_current_week_start() -> date:
    """Return the Sunday of the current week in Asia/Muscat timezone."""
    now_muscat = datetime.now(MUSCAT_TZ).date()
    return get_week_start(now_muscat)


def get_working_days(week_start: date) -> list[date]:
    """Return Sunday–Thursday for the given week_start (Sunday)."""
    return [week_start + timedelta(days=i) for i in range(5)]


def create_week_plan(db: Session, week_start: date, actor: str = "system") -> WeekPlan:
    """Create an empty draft week plan with day plans for Sun–Thu."""
    week_plan = WeekPlan(week_start_date=week_start, status="draft", version=1)
    db.add(week_plan)
    db.flush()

    for day in get_working_days(week_start):
        db.add(DayPlan(week_plan_id=week_plan.id, date=day))

    _log_change(db, week_plan.id, actor, "create_week", {"week_start": str(week_start)})
    db.commit()
    db.refresh(week_plan)
    return week_plan


def clone_week(db: Session, source_week_start: date, target_week_start: date, actor: str = "system") -> Optional[WeekPlan]:
    """
    Clone a published week plan to a new week as draft.
    Returns None if target week already exists.
    """
    # Check target doesn't already exist
    existing = db.query(WeekPlan).filter(WeekPlan.week_start_date == target_week_start).first()
    if existing:
        logger.info(f"Clone skipped: week {target_week_start} already exists.")
        return None

    source = db.query(WeekPlan).filter(WeekPlan.week_start_date == source_week_start).first()
    if not source:
        logger.error(f"Clone failed: source week {source_week_start} not found.")
        return None

    # Compute day offset between source and target
    day_offset = target_week_start - source_week_start

    # Create new week plan
    new_plan = WeekPlan(
        week_start_date=target_week_start,
        status="draft",
        version=1,
        cloned_from_week_start=source_week_start
    )
    db.add(new_plan)
    db.flush()

    # Clone each day
    for src_day in source.day_plans:
        new_date = src_day.date + day_offset
        new_day = DayPlan(week_plan_id=new_plan.id, date=new_date)
        db.add(new_day)
        db.flush()

        # Clone shift_locations
        for src_sl in src_day.shift_locations:
            new_sl = ShiftLocation(
                day_plan_id=new_day.id,
                shift_id=src_sl.shift_id,
                location_id=src_sl.location_id,
                slots_count=src_sl.slots_count,
                order=src_sl.order
            )
            db.add(new_sl)
            db.flush()

            # Clone assignments
            for src_a in src_sl.assignments:
                new_a = Assignment(
                    shift_location_id=new_sl.id,
                    slot_index=src_a.slot_index,
                    teacher_id=src_a.teacher_id
                )
                db.add(new_a)

    _log_change(db, new_plan.id, actor, "clone_week", {
        "source": str(source_week_start),
        "target": str(target_week_start)
    })
    db.commit()
    db.refresh(new_plan)
    logger.info(f"Week {target_week_start} cloned from {source_week_start}.")
    return new_plan


def update_shift_location_slots(db: Session, week_plan: WeekPlan,
                                  day_date: date, shift_id: int, location_id: int,
                                  new_slots_count: int, actor: str = "admin") -> ShiftLocation:
    """
    Update slots_count for a shift+location. Remove overflowing assignments.
    Creates ShiftLocation if not found, along with its assignments.
    """
    day_plan = db.query(DayPlan).filter(
        DayPlan.week_plan_id == week_plan.id,
        DayPlan.date == day_date
    ).first()
    if not day_plan:
        raise ValueError(f"No day plan for {day_date} in week {week_plan.week_start_date}")

    sl = db.query(ShiftLocation).filter(
        ShiftLocation.day_plan_id == day_plan.id,
        ShiftLocation.shift_id == shift_id,
        ShiftLocation.location_id == location_id
    ).first()

    if not sl:
        # Create new shift_location
        sl = ShiftLocation(
            day_plan_id=day_plan.id,
            shift_id=shift_id,
            location_id=location_id,
            slots_count=new_slots_count,
            order=0
        )
        db.add(sl)
        db.flush()
        # Create empty assignments
        for i in range(new_slots_count):
            db.add(Assignment(shift_location_id=sl.id, slot_index=i, teacher_id=None))
    else:
        old_count = sl.slots_count
        sl.slots_count = new_slots_count

        if new_slots_count < old_count:
            # Remove overflowing assignments
            db.query(Assignment).filter(
                Assignment.shift_location_id == sl.id,
                Assignment.slot_index >= new_slots_count
            ).delete()
        elif new_slots_count > old_count:
            # Add new empty slots
            for i in range(old_count, new_slots_count):
                db.add(Assignment(shift_location_id=sl.id, slot_index=i, teacher_id=None))

    db.commit()
    db.refresh(sl)
    return sl


def update_assignment(db: Session, week_plan: WeekPlan,
                       shift_location_id: int, slot_index: int,
                       teacher_id: Optional[int], actor: str = "admin") -> Assignment:
    """
    Assign or unassign a teacher to a slot.
    Enforces: a teacher cannot be in multiple locations in the same shift on the same day.
    """
    sl = db.query(ShiftLocation).filter(ShiftLocation.id == shift_location_id).first()
    if not sl:
        raise ValueError(f"ShiftLocation {shift_location_id} not found")

    # Check conflict: teacher assigned elsewhere in same shift+day?
    if teacher_id:
        day_plan = sl.day_plan
        conflict = db.query(Assignment).join(ShiftLocation).filter(
            ShiftLocation.day_plan_id == day_plan.id,
            ShiftLocation.shift_id == sl.shift_id,
            Assignment.teacher_id == teacher_id,
            Assignment.shift_location_id != shift_location_id
        ).first()
        if conflict:
            raise ValueError(
                f"Teacher {teacher_id} is already assigned in shift {sl.shift_id} on {day_plan.date}"
            )

    assignment = db.query(Assignment).filter(
        Assignment.shift_location_id == shift_location_id,
        Assignment.slot_index == slot_index
    ).first()

    if not assignment:
        assignment = Assignment(
            shift_location_id=shift_location_id,
            slot_index=slot_index,
            teacher_id=teacher_id
        )
        db.add(assignment)
    else:
        assignment.teacher_id = teacher_id

    db.commit()
    db.refresh(assignment)
    return assignment


def publish_week(db: Session, week_plan: WeekPlan, actor: str = "admin"):
    """
    Publish a week plan. Logs the action and notifies affected teachers.
    """
    week_plan.status = "published"
    week_plan.version += 1
    _log_change(db, week_plan.id, actor, "publish", {"week_start": str(week_plan.week_start_date)})
    db.commit()
    db.refresh(week_plan)

    # Notify all assigned teachers about publication
    _notify_assigned_teachers(db, week_plan, action="updated")
    return week_plan


def _notify_assigned_teachers(db: Session, week_plan: WeekPlan, action: str = "updated"):
    """Find all teachers assigned in this week and send update notifications."""
    teacher_ids = set()
    for day in week_plan.day_plans:
        for sl in day.shift_locations:
            for a in sl.assignments:
                if a.teacher_id:
                    teacher_ids.add(a.teacher_id)

    for teacher_id in teacher_ids:
        teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if not teacher:
            continue
        tokens = [dt.token for dt in db.query(DeviceToken).filter(
            DeviceToken.teacher_id == teacher_id).all()]
        if tokens:
            notify_teacher_updated(tokens, teacher.preferred_language)


def _log_change(db: Session, week_plan_id: int, actor: str, action: str, payload: dict):
    log = ChangeLog(
        week_plan_id=week_plan_id,
        actor=actor,
        action=action,
        payload_json=json.dumps(payload, ensure_ascii=False)
    )
    db.add(log)