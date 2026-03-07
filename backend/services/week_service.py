"""Business logic for week planning, cloning, and slot management."""

import json
import logging
from datetime import date, timedelta, datetime, timezone
from typing import Optional

import pytz
from sqlalchemy.orm import Session

from models.models import (
    WeekPlan, DayPlan, ShiftLocation, Assignment,
    ChangeLog, Teacher, DeviceToken
)
from services.notification_service import notify_teacher_updated

logger = logging.getLogger(__name__)
MUSCAT_TZ = pytz.timezone("Asia/Muscat")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─── Week Utilities ───────────────────────────────────────────────────────────

def get_week_start(for_date: date) -> date:
    """Return the Sunday of the week containing for_date."""
    days_since_sunday = (for_date.weekday() + 1) % 7
    return for_date - timedelta(days=days_since_sunday)


def get_current_week_start() -> date:
    """Return the Sunday of the current week in Asia/Muscat timezone."""
    now_muscat = datetime.now(MUSCAT_TZ).date()
    return get_week_start(now_muscat)


def get_working_days(week_start: date) -> list[date]:
    """Return Sunday–Thursday for the given week_start."""
    return [week_start + timedelta(days=i) for i in range(5)]


# ─── Week CRUD ────────────────────────────────────────────────────────────────

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


def clone_week(
    db: Session,
    source_week_start: date,
    target_week_start: date,
    actor: str = "system",
) -> Optional[WeekPlan]:
    """
    Clone a week plan to a new week as draft.
    Preserves duty_type, location_id (None for break duties), grade_class,
    and teacher assignments.
    """
    existing = db.query(WeekPlan).filter(WeekPlan.week_start_date == target_week_start).first()
    if existing:
        logger.info(f"Clone skipped: week {target_week_start} already exists.")
        return None

    source = db.query(WeekPlan).filter(WeekPlan.week_start_date == source_week_start).first()
    if not source:
        logger.error(f"Clone failed: source week {source_week_start} not found.")
        return None

    day_offset = target_week_start - source_week_start

    new_plan = WeekPlan(
        week_start_date=target_week_start,
        status="draft",
        version=1,
        cloned_from_week_start=source_week_start,
    )
    db.add(new_plan)
    db.flush()

    for src_day in source.day_plans:
        new_day = DayPlan(week_plan_id=new_plan.id, date=src_day.date + day_offset)
        db.add(new_day)
        db.flush()

        for src_sl in src_day.shift_locations:
            new_sl = ShiftLocation(
                day_plan_id=new_day.id,
                shift_id=src_sl.shift_id,
                location_id=src_sl.location_id,   # None preserved for break duties
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
                    grade_class=src_a.grade_class,  # preserved for break duties
                ))

    _log_change(db, new_plan.id, actor, "clone_week", {
        "source": str(source_week_start),
        "target": str(target_week_start),
    })
    db.commit()
    db.refresh(new_plan)
    logger.info(f"Week {target_week_start} cloned from {source_week_start}.")
    return new_plan


def update_shift_location_slots(
    db: Session,
    week_plan: WeekPlan,
    day_date: date,
    shift_id: int,
    location_id: Optional[int],
    new_slots_count: int,
    actor: str = "admin",
) -> ShiftLocation:
    """
    Update slots_count for a shift+(location|None) within a day.
    location_id is None for break duties.
    Creates ShiftLocation + assignments if it doesn't exist yet.
    """
    day_plan = db.query(DayPlan).filter(
        DayPlan.week_plan_id == week_plan.id,
        DayPlan.date == day_date,
    ).first()
    if not day_plan:
        raise ValueError(f"No day plan for {day_date} in week {week_plan.week_start_date}")

    # Build filter — handle NULL location_id correctly
    sl_query = db.query(ShiftLocation).filter(
        ShiftLocation.day_plan_id == day_plan.id,
        ShiftLocation.shift_id == shift_id,
    )
    if location_id is None:
        sl_query = sl_query.filter(ShiftLocation.location_id.is_(None))
    else:
        sl_query = sl_query.filter(ShiftLocation.location_id == location_id)

    sl = sl_query.first()

    if not sl:
        sl = ShiftLocation(
            day_plan_id=day_plan.id,
            shift_id=shift_id,
            location_id=location_id,
            slots_count=new_slots_count,
            order=0,
        )
        db.add(sl)
        db.flush()
        for i in range(new_slots_count):
            db.add(Assignment(shift_location_id=sl.id, slot_index=i, teacher_id=None))
    else:
        old_count = sl.slots_count
        sl.slots_count = new_slots_count
        if new_slots_count < old_count:
            db.query(Assignment).filter(
                Assignment.shift_location_id == sl.id,
                Assignment.slot_index >= new_slots_count,
            ).delete()
        elif new_slots_count > old_count:
            for i in range(old_count, new_slots_count):
                db.add(Assignment(shift_location_id=sl.id, slot_index=i, teacher_id=None))

    db.commit()
    db.refresh(sl)
    _log_change(db, week_plan.id, actor, "update_slots", {
        "day": str(day_date), "shift_id": shift_id,
        "location_id": location_id, "slots": new_slots_count,
    })
    return sl


def update_assignment(
    db: Session,
    week_plan: WeekPlan,
    shift_location_id: int,
    slot_index: int,
    teacher_id: Optional[int],
    grade_class: Optional[str] = None,
    actor: str = "admin",
) -> Assignment:
    """
    Assign or unassign a teacher to a slot.
    For break duties, grade_class is stored on the Assignment.
    Enforces: a teacher cannot be in multiple slots in the same shift on the same day.
    """
    sl = db.query(ShiftLocation).filter(ShiftLocation.id == shift_location_id).first()
    if not sl:
        raise ValueError(f"ShiftLocation {shift_location_id} not found")

    if teacher_id:
        day_plan = sl.day_plan
        conflict = db.query(Assignment).join(ShiftLocation).filter(
            ShiftLocation.day_plan_id == day_plan.id,
            ShiftLocation.shift_id == sl.shift_id,
            Assignment.teacher_id == teacher_id,
            Assignment.shift_location_id != shift_location_id,
        ).first()
        if conflict:
            raise ValueError(
                f"Teacher {teacher_id} is already assigned in shift {sl.shift_id} on {day_plan.date}"
            )

    assignment = db.query(Assignment).filter(
        Assignment.shift_location_id == shift_location_id,
        Assignment.slot_index == slot_index,
    ).first()

    if not assignment:
        assignment = Assignment(
            shift_location_id=shift_location_id,
            slot_index=slot_index,
            teacher_id=teacher_id,
            grade_class=grade_class,
        )
        db.add(assignment)
    else:
        assignment.teacher_id = teacher_id
        # Always update grade_class — clearing it when teacher is removed
        assignment.grade_class = grade_class if teacher_id else None

    db.commit()
    db.refresh(assignment)
    _log_change(db, week_plan.id, actor, "update_assignment", {
        "shift_location_id": shift_location_id,
        "slot_index": slot_index,
        "teacher_id": teacher_id,
        "grade_class": grade_class,
    })
    return assignment


def publish_week(db: Session, week_plan: WeekPlan, actor: str = "admin") -> WeekPlan:
    """Publish a week plan and notify all assigned teachers."""
    week_plan.status = "published"
    week_plan.version += 1
    _log_change(db, week_plan.id, actor, "publish", {"week_start": str(week_plan.week_start_date)})
    db.commit()
    db.refresh(week_plan)
    _notify_assigned_teachers(db, week_plan)
    return week_plan


def _notify_assigned_teachers(db: Session, week_plan: WeekPlan) -> None:
    """Notify all assigned teachers about a schedule update (batched queries)."""
    teacher_ids: set[int] = set()
    for day in week_plan.day_plans:
        for sl in day.shift_locations:
            for a in sl.assignments:
                if a.teacher_id:
                    teacher_ids.add(a.teacher_id)

    if not teacher_ids:
        return

    teachers = {
        t.id: t
        for t in db.query(Teacher).filter(Teacher.id.in_(teacher_ids)).all()
    }
    tokens_by_teacher: dict[int, list[str]] = {}
    for dt in db.query(DeviceToken).filter(DeviceToken.teacher_id.in_(teacher_ids)).all():
        tokens_by_teacher.setdefault(dt.teacher_id, []).append(dt.token)

    for tid in teacher_ids:
        teacher = teachers.get(tid)
        tokens = tokens_by_teacher.get(tid, [])
        if teacher and tokens:
            notify_teacher_updated(tokens, teacher.preferred_language)


def _log_change(db: Session, week_plan_id: int, actor: str, action: str, payload: dict) -> None:
    db.add(ChangeLog(
        week_plan_id=week_plan_id,
        actor=actor,
        action=action,
        payload_json=json.dumps(payload, ensure_ascii=False),
    ))