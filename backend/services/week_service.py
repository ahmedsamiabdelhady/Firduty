"""
week_service.py — Week plan creation, cloning, assignment, and publishing.

Fixes vs v2.4:
  - _notify_assigned_teachers() accepts an optional `teacher_ids` set so
    the router can scope notifications to *newly* assigned teachers only.
  - publish_week() no longer uses hasattr() for is_published — field is NOT NULL
    in DB/model, so a silent skip would mask a real schema issue.
  - clone_week() returns explicit sentinel strings instead of bare None so
    the router can distinguish "target exists" from "source not found".
  - publish_day() same hasattr removal.
"""

import hashlib
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import pytz
from sqlalchemy.orm import Session, selectinload

from models.models import (
    WeekPlan,
    DayPlan,
    ShiftLocation,
    Assignment,
    ChangeLog,
    Teacher,
    DeviceToken,
    Shift,
    Location,
    GradeClass,
)
from models.notification_log import NotificationLog

logger = logging.getLogger(__name__)

MUSCAT_TZ = pytz.timezone("Asia/Muscat")
WEEK_DAYS = 5  # Sun–Thu (Oman working week)

SHIFT_NAME_ALIASES = {
    "morning": {
        "en": {"morning duty", "morning"},
        "ar": {"المناوبة الصباحية", "الصباحية"},
    },
    "break_1": {
        "en": {"first break", "break 1"},
        "ar": {"البريك الأول", "الاستراحة الأولى", "الفسحة الأولى"},
    },
    "break_2": {
        "en": {"second break", "break 2"},
        "ar": {"البريك الثاني", "الاستراحة الثانية", "الفسحة الثانية"},
    },
    "end_of_day": {
        "en": {"end of day duty", "end of day", "evening duty"},
        "ar": {"المناوبة المسائية", "نهاية الدوام", "المسائية"},
    },
}

MORNING_LOCATION_SPECS = [
    {"name_en": "First floor - Interior corridor", "slots_count": 1},
    {"name_en": "First floor - Main corridor", "slots_count": 2},
    {"name_en": "First floor - Beside teachers room", "slots_count": 1},
    {"name_en": "Area A", "slots_count": 1},
    {"name_en": "Area B", "slots_count": 1},
    {"name_en": "Area C", "slots_count": 1},
    {"name_en": "Area D", "slots_count": 1},
    {"name_en": "Second floor - Interior corridor", "slots_count": 2},
    {"name_en": "Second floor - Main corridor", "slots_count": 2},
    {"name_en": "Second floor - Beside teachers room", "slots_count": 1},
    {"name_en": "Playground", "slots_count": 5},
    {"name_en": "Ground floor", "slots_count": 1},
    {"name_en": "Ground floor - KG2A", "slots_count": 2},
    {"name_en": "General supervision", "slots_count": 1}    
]

END_OF_DAY_LOCATION_SPECS = [
    {"name_en": "Waiting room", "slots_count": 2},
    {"name_en": "Glass door", "slots_count": 2},
    {"name_en": "Stairs - KG", "slots_count": 2},
    {"name_en": "Area A", "slots_count": 1},
    {"name_en": "Area B", "slots_count": 1},
    {"name_en": "Area C", "slots_count": 1},
    {"name_en": "Area D", "slots_count": 1},
    {"name_en": "Second floor", "slots_count": 1},
    {"name_en": "Basement floor", "slots_count": 7},
    {"name_en": "First floor", "slots_count": 1},
    {"name_en": "Playground", "slots_count": 6},
    {"name_en": "Ground floor", "slots_count": 1},
    {"name_en": "General Supervision", "slots_count": 1},
]

# ─── Utilities ────────────────────────────────────────────────────────────────

def get_today_muscat() -> date:
    return datetime.now(MUSCAT_TZ).date()


def is_day_editable(day_date: date) -> bool:
    return day_date >= get_today_muscat()


def _ensure_day_not_past(day_date: date) -> None:
    if day_date < get_today_muscat():
        raise ValueError("Cannot modify past days")


def get_current_week_start() -> date:
    now = datetime.now(MUSCAT_TZ).date()
    days_since_sunday = now.isoweekday() % 7
    return now - timedelta(days=days_since_sunday)


def get_previous_week_start() -> date:
    return get_current_week_start() - timedelta(days=7)


def _log_change(
    db: Session,
    week: WeekPlan,
    actor: str,
    action: str,
    payload: Optional[dict] = None,
) -> None:
    db.add(ChangeLog(
        week_plan_id=week.id,
        actor=str(actor),
        action=action,
        payload_json=json.dumps(payload) if payload else None,
    ))


def _normalize(value: Optional[str]) -> str:
    return " ".join(
        (value or "")
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .replace("/", " / ")
        .split()
    )


# ─── Alias / location maps ────────────────────────────────────────────────────

def _build_shift_alias_map(db: Session) -> dict[str, Shift]:
    shifts = db.query(Shift).order_by(Shift.order.asc(), Shift.id.asc()).all()
    result: dict[str, Shift] = {}

    for alias_key, alias in SHIFT_NAME_ALIASES.items():
        alias_en = {_normalize(v) for v in alias["en"]}
        alias_ar = {_normalize(v) for v in alias["ar"]}

        for shift in shifts:
            shift_en = _normalize(getattr(shift, "name_en", None))
            shift_ar = _normalize(getattr(shift, "name_ar", None))
            if shift_en in alias_en or shift_ar in alias_ar:
                result[alias_key] = shift
                break

    missing = [k for k in SHIFT_NAME_ALIASES if k not in result]
    if missing:
        raise ValueError(
            f"Required shifts not found in DB: {', '.join(missing)}. "
            "Please seed shifts with Morning / First Break / Second Break / End of Day names."
        )

    return result


def _build_location_map(db: Session) -> dict[str, Location]:
    locations = db.query(Location).order_by(Location.order.asc(), Location.id.asc()).all()
    return {_normalize(loc.name_en): loc for loc in locations}


def _ensure_required_locations_exist(
    db: Session,
    location_specs: list[dict],
) -> dict[str, Location]:
    location_map = _build_location_map(db)

    for spec in location_specs:
        target = _normalize(spec["name_en"])
        if target not in location_map:
            raise ValueError(
                f"Required location '{spec['name_en']}' was not found in DB. "
                "Please seed the Location table with all planner locations."
            )

    return location_map


def _get_break_grade_classes(db: Session) -> list[str]:
    rows = (
        db.query(GradeClass)
        .filter(GradeClass.active.is_(True))
        .order_by(GradeClass.order.asc(), GradeClass.id.asc())
        .all()
    )
    return [r.name_en for r in rows] if rows else ["1/A", "1/B", "2/A", "2/B", "3/A"]


# ─── Week helpers ─────────────────────────────────────────────────────────────

def _get_week_with_day_plans(db: Session, week_id: int) -> WeekPlan:
    week = (
        db.query(WeekPlan)
        .options(
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.assignments)
        )
        .filter(WeekPlan.id == week_id)
        .first()
    )
    if not week:
        raise ValueError(f"WeekPlan id={week_id} not found")
    return week


def _build_day_template_rows(
    day_id: int,
    morning_shift: Shift,
    break_1_shift: Shift,
    break_2_shift: Shift,
    end_of_day_shift: Shift,
    location_map: dict[str, Location],
    break_grade_classes: list[str],
) -> list[ShiftLocation]:
    rows: list[ShiftLocation] = []
    order = 0

    # Morning duty — one slot per location
    for spec in MORNING_LOCATION_SPECS:
        loc = location_map.get(_normalize(spec["name_en"]))
        if not loc:
            continue
        rows.append(ShiftLocation(
            day_plan_id=day_id,
            shift_id=morning_shift.id,
            location_id=loc.id,
            slots_count=spec["slots_count"],
            order=order,
        ))
        order += 1

    # Break 1 (no location — grade/class driven)
    rows.append(ShiftLocation(
        day_plan_id=day_id,
        shift_id=break_1_shift.id,
        location_id=None,
        slots_count=len(break_grade_classes),
        order=order,
    ))
    order += 1

    # Break 2 (no location — grade/class driven)
    rows.append(ShiftLocation(
        day_plan_id=day_id,
        shift_id=break_2_shift.id,
        location_id=None,
        slots_count=len(break_grade_classes),
        order=order,
    ))
    order += 1

    # End of day — one slot per location
    for spec in END_OF_DAY_LOCATION_SPECS:
        loc = location_map.get(_normalize(spec["name_en"]))
        if not loc:
            continue
        rows.append(ShiftLocation(
            day_plan_id=day_id,
            shift_id=end_of_day_shift.id,
            location_id=loc.id,
            slots_count=spec["slots_count"],
            order=order,
        ))
        order += 1

    return rows


def _is_week_fully_populated(db: Session, week: WeekPlan) -> bool:
    week = _get_week_with_day_plans(db, week.id)
    by_date = {day.date: day for day in week.day_plans}
    for i in range(WEEK_DAYS):
        day_date = week.week_start_date + timedelta(days=i)
        day = by_date.get(day_date)
        if not day or not day.shift_locations:
            return False
    return True


def ensure_week_fully_populated(db: Session, week: WeekPlan) -> WeekPlan:
    week = _get_week_with_day_plans(db, week.id)

    shift_map = _build_shift_alias_map(db)
    location_map = _ensure_required_locations_exist(
        db,
        MORNING_LOCATION_SPECS + END_OF_DAY_LOCATION_SPECS,
    )
    break_grade_classes = _get_break_grade_classes(db)

    existing_days = {day.date: day for day in week.day_plans}
    changed = False

    for i in range(WEEK_DAYS):
        day_date = week.week_start_date + timedelta(days=i)
        day = existing_days.get(day_date)

        # Create missing day
        if not day:
            day = DayPlan(week_plan_id=week.id, date=day_date, is_published=False)
            db.add(day)
            db.flush()
            existing_days[day_date] = day
            changed = True

        # Refresh current rows for this day
        day_shift_locations = list(day.shift_locations or [])

        existing_sls: dict[tuple[int, Optional[int]], ShiftLocation] = {
            (sl.shift_id, sl.location_id): sl
            for sl in day_shift_locations
        }

        def ensure_shift_location(
            *,
            shift_id: int,
            location_id: Optional[int],
            slots_count: int,
            order: int,
        ) -> ShiftLocation:
            nonlocal changed

            key = (shift_id, location_id)
            sl = existing_sls.get(key)

            if sl is None:
                sl = ShiftLocation(
                    day_plan_id=day.id,
                    shift_id=shift_id,
                    location_id=location_id,
                    slots_count=slots_count,
                    order=order,
                )
                db.add(sl)
                db.flush()
                existing_sls[key] = sl
                day.shift_locations.append(sl)
                changed = True
            else:
                # Keep template slots_count in sync if corrupted
                if int(sl.slots_count or 0) != int(slots_count):
                    sl.slots_count = slots_count
                    changed = True
                if sl.order != order:
                    sl.order = order
                    changed = True

            return sl

        order = 0

        # Morning duty rows
        for spec in MORNING_LOCATION_SPECS:
            loc = location_map[_normalize(spec["name_en"])]
            ensure_shift_location(
                shift_id=shift_map["morning"].id,
                location_id=loc.id,
                slots_count=int(spec["slots_count"]),
                order=order,
            )
            order += 1

        # Break 1 row
        ensure_shift_location(
            shift_id=shift_map["break_1"].id,
            location_id=None,
            slots_count=len(break_grade_classes),
            order=order,
        )
        order += 1

        # Break 2 row
        ensure_shift_location(
            shift_id=shift_map["break_2"].id,
            location_id=None,
            slots_count=len(break_grade_classes),
            order=order,
        )
        order += 1

        # End-of-day rows
        for spec in END_OF_DAY_LOCATION_SPECS:
            loc = location_map[_normalize(spec["name_en"])]
            ensure_shift_location(
                shift_id=shift_map["end_of_day"].id,
                location_id=loc.id,
                slots_count=int(spec["slots_count"]),
                order=order,
            )
            order += 1

        # Ensure assignments exist for every slot
        break_shift_ids = {shift_map["break_1"].id, shift_map["break_2"].id}

        for sl in list(day.shift_locations or []):
            existing_assignments = {
                int(a.slot_index): a
                for a in (sl.assignments or [])
                if a.slot_index is not None
            }

            if sl.location_id is None and sl.shift_id in break_shift_ids:
                # Break rows: one assignment per grade class
                for idx, gc in enumerate(break_grade_classes):
                    a = existing_assignments.get(idx)
                    if a is None:
                        db.add(Assignment(
                            shift_location_id=sl.id,
                            slot_index=idx,
                            teacher_id=None,
                            grade_class=gc,
                        ))
                        changed = True
                    else:
                        if a.grade_class != gc:
                            a.grade_class = gc
                            changed = True

                # Remove overflow corrupted assignments beyond grade class count
                for idx, a in existing_assignments.items():
                    if idx >= len(break_grade_classes):
                        db.delete(a)
                        changed = True

            else:
                target_slots = int(sl.slots_count or 0)

                for idx in range(target_slots):
                    if idx not in existing_assignments:
                        db.add(Assignment(
                            shift_location_id=sl.id,
                            slot_index=idx,
                            teacher_id=None,
                            grade_class=None,
                        ))
                        changed = True

                # Remove overflow corrupted assignments beyond slots_count
                for idx, a in existing_assignments.items():
                    if idx >= target_slots:
                        db.delete(a)
                        changed = True

    if changed:
        db.commit()

    return _get_week_with_day_plans(db, week.id)

# ─── Week CRUD ────────────────────────────────────────────────────────────────

def create_week_plan(db: Session, week_start: date, actor: str = "admin") -> WeekPlan:
    existing = db.query(WeekPlan).filter(WeekPlan.week_start_date == week_start).first()

    if existing:
        week = ensure_week_fully_populated(db, existing)
        if _is_week_fully_populated(db, week):
            raise ValueError(f"Week {week_start} already exists. Cannot create it again.")
        return week

    shift_map       = _build_shift_alias_map(db)
    location_map    = _ensure_required_locations_exist(db, MORNING_LOCATION_SPECS + END_OF_DAY_LOCATION_SPECS)
    break_grade_classes = _get_break_grade_classes(db)

    week = WeekPlan(week_start_date=week_start, status="draft", version=1)
    db.add(week)
    db.flush()

    days: list[DayPlan] = [
        DayPlan(week_plan_id=week.id, date=week_start + timedelta(days=i), is_published=False)
        for i in range(WEEK_DAYS)
    ]
    db.add_all(days)
    db.flush()

    all_shift_locations: list[ShiftLocation] = []
    for day in days:
        all_shift_locations.extend(_build_day_template_rows(
            day_id=day.id,
            morning_shift=shift_map["morning"],
            break_1_shift=shift_map["break_1"],
            break_2_shift=shift_map["break_2"],
            end_of_day_shift=shift_map["end_of_day"],
            location_map=location_map,
            break_grade_classes=break_grade_classes,
        ))

    db.add_all(all_shift_locations)
    db.flush()

    all_assignments: list[Assignment] = []
    break_shift_ids = {shift_map["break_1"].id, shift_map["break_2"].id}

    for sl in all_shift_locations:
        if sl.location_id is None and sl.shift_id in break_shift_ids:
            for idx, gc in enumerate(break_grade_classes):
                all_assignments.append(Assignment(
                    shift_location_id=sl.id, slot_index=idx,
                    teacher_id=None, grade_class=gc,
                ))
        else:
            for idx in range(int(sl.slots_count)):
                all_assignments.append(Assignment(
                    shift_location_id=sl.id, slot_index=idx,
                    teacher_id=None, grade_class=None,
                ))

    if all_assignments:
        db.add_all(all_assignments)

    _log_change(db, week, actor, "create_week", {"week_start": str(week_start)})
    db.commit()
    db.refresh(week)
    logger.info("Created week plan for %s (id=%s)", week_start, week.id)
    return week


def clone_week(
    db: Session,
    source_week_start: date,
    target_week_start: date,
    actor: str = "admin",
) -> Optional[WeekPlan]:
    """
    Clone source_week_start into target_week_start as a new draft.

    Returns None in two cases (the router now pre-checks these, so None
    here is genuinely unexpected):
      - target already exists  (router pre-checks → 409)
      - source not found       (router pre-checks → 404)
    """
    if db.query(WeekPlan).filter(WeekPlan.week_start_date == target_week_start).first():
        logger.warning("clone_week: target %s already exists.", target_week_start)
        return None

    source = (
        db.query(WeekPlan)
        .options(
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.assignments)
        )
        .filter(WeekPlan.week_start_date == source_week_start)
        .first()
    )
    if not source:
        logger.error("clone_week: source %s not found.", source_week_start)
        return None

    source     = ensure_week_fully_populated(db, source)
    day_offset = target_week_start - source_week_start

    new_week = WeekPlan(
        week_start_date=target_week_start,
        status="draft",
        version=1,
        cloned_from_week_start=source_week_start,
    )
    db.add(new_week)
    db.flush()

    sorted_days = sorted(source.day_plans, key=lambda d: d.date)

    new_days: list[DayPlan] = [
        DayPlan(week_plan_id=new_week.id, date=src_day.date + day_offset, is_published=False)
        for src_day in sorted_days
    ]
    db.add_all(new_days)
    db.flush()

    all_new_sls: list[ShiftLocation] = []
    sl_mapping: list[tuple[ShiftLocation, ShiftLocation]] = []

    for src_day, new_day in zip(sorted_days, new_days):
        for src_sl in sorted(src_day.shift_locations, key=lambda sl: ((sl.order or 9999), sl.id)):
            new_sl = ShiftLocation(
                day_plan_id=new_day.id,
                shift_id=src_sl.shift_id,
                location_id=src_sl.location_id,
                slots_count=src_sl.slots_count,
                order=src_sl.order,
            )
            all_new_sls.append(new_sl)
            sl_mapping.append((src_sl, new_sl))

    db.add_all(all_new_sls)
    db.flush()

    all_new_assignments: list[Assignment] = []
    for src_sl, new_sl in sl_mapping:
        for src_a in sorted(src_sl.assignments, key=lambda a: ((a.slot_index or 9999), a.id)):
            all_new_assignments.append(Assignment(
                shift_location_id=new_sl.id,
                slot_index=src_a.slot_index,
                teacher_id=src_a.teacher_id,
                grade_class=src_a.grade_class,
            ))

    if all_new_assignments:
        db.add_all(all_new_assignments)

    _log_change(db, new_week, actor, "clone_week",
                {"source": str(source_week_start), "target": str(target_week_start)})
    db.commit()
    db.refresh(new_week)
    logger.info("Cloned %s → %s (id=%s)", source_week_start, target_week_start, new_week.id)
    return new_week


# ─── Slot / assignment updates ────────────────────────────────────────────────

def _find_shift_location(
    db: Session,
    day: DayPlan,
    shift_id: int,
    location_id: Optional[int],
) -> Optional[ShiftLocation]:
    query = db.query(ShiftLocation).filter(
        ShiftLocation.day_plan_id == day.id,
        ShiftLocation.shift_id == shift_id,
    )
    if location_id is None:
        query = query.filter(ShiftLocation.location_id.is_(None))
    else:
        query = query.filter(ShiftLocation.location_id == location_id)
    return query.options(selectinload(ShiftLocation.assignments)).first()


def update_shift_location_slots(
    db: Session,
    week: WeekPlan,
    day_date: date,
    shift_id: int,
    location_id: Optional[int],
    slots_count: int,
    actor: str = "admin",
) -> ShiftLocation:
    _ensure_day_not_past(day_date)

    day = (
        db.query(DayPlan)
        .options(selectinload(DayPlan.shift_locations).selectinload(ShiftLocation.assignments))
        .filter(DayPlan.week_plan_id == week.id, DayPlan.date == day_date)
        .first()
    )
    if not day:
        day = DayPlan(week_plan_id=week.id, date=day_date, is_published=False)
        db.add(day)
        db.flush()

    sl = _find_shift_location(db, day, shift_id, location_id)

    if not sl:
        max_order = db.query(ShiftLocation).filter(ShiftLocation.day_plan_id == day.id).count()
        sl = ShiftLocation(
            day_plan_id=day.id,
            shift_id=shift_id,
            location_id=location_id,
            slots_count=slots_count,
            order=max_order,
        )
        db.add(sl)
        db.flush()
    else:
        current_count = int(sl.slots_count)

        if slots_count > current_count:
            for idx in range(current_count, slots_count):
                db.add(Assignment(
                    shift_location_id=sl.id, slot_index=idx,
                    teacher_id=None, grade_class=None,
                ))
        elif slots_count < current_count:
            for idx in range(slots_count, current_count):
                excess = (
                    db.query(Assignment)
                    .filter(Assignment.shift_location_id == sl.id, Assignment.slot_index == idx)
                    .first()
                )
                if excess:
                    db.delete(excess)

        sl.slots_count = slots_count

    _log_change(db, week, actor, "update_slots", {
        "day": str(day_date), "shift_id": shift_id,
        "location_id": location_id, "slots_count": slots_count,
    })
    db.commit()
    db.refresh(sl)
    return sl


def update_assignment(
    db: Session,
    week: WeekPlan,
    shift_location_id: int,
    slot_index: int,
    teacher_id: Optional[int],
    grade_class: Optional[str],
    actor: str = "admin",
) -> Assignment:
    sl = db.query(ShiftLocation).filter(
        ShiftLocation.id == shift_location_id,
        ShiftLocation.day_plan.has(DayPlan.week_plan_id == week.id),
    ).first()

    if not sl:
        raise ValueError(f"ShiftLocation {shift_location_id} not found in week {week.week_start_date}")

    day = sl.day_plan
    _ensure_day_not_past(day.date)

    assignment = (
        db.query(Assignment)
        .filter(Assignment.shift_location_id == shift_location_id, Assignment.slot_index == slot_index)
        .first()
    )

    if assignment is None:
        assignment = Assignment(
            shift_location_id=shift_location_id,
            slot_index=slot_index,
            teacher_id=teacher_id,
            grade_class=grade_class,
        )
        db.add(assignment)
    else:
        assignment.teacher_id  = teacher_id
        assignment.grade_class = grade_class

    _log_change(db, week, actor, "update_assignment", {
        "shift_location_id": shift_location_id,
        "slot_index":        slot_index,
        "teacher_id":        teacher_id,
        "grade_class":       grade_class,
    })
    db.commit()
    db.refresh(assignment)
    return assignment


# ─── Publishing ───────────────────────────────────────────────────────────────


def publish_week(
    db: Session,
    week: WeekPlan,
    actor: str = "admin",
    notify_scope: str = "all",
    notify_teacher_ids: Optional[set[int]] = None,
) -> WeekPlan:
    """
    Publish the full week.

    A repeated publish on an already-published week keeps the same version/hash,
    so teachers are notified once for that exact published state.
    """
    week = (
        db.query(WeekPlan)
        .options(
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.assignments)
        )
        .filter(WeekPlan.id == week.id)
        .first()
    )
    if not week:
        raise ValueError("Week not found")

    was_already_published = (
        str(week.status) == "published"
        and all(bool(day.is_published) for day in week.day_plans)
    )

    if not was_already_published:
        week.version = (week.version or 0) + 1

    week.status = "published"

    for day in week.day_plans:
        day.is_published = True

    _log_change(db, week, actor, "publish", {
        "version": week.version,
        "notify_scope": notify_scope,
        "already_published": was_already_published,
    })
    db.commit()
    db.refresh(week)

    update_hash = _build_week_update_hash(week)

    logger.info(
        "Week %s published (v%s) notify_scope=%s already_published=%s hash=%s",
        week.week_start_date,
        week.version,
        notify_scope,
        was_already_published,
        update_hash,
    )

    if notify_scope == "all":
        _notify_assigned_teachers(db, week, update_hash=update_hash)
    elif notify_scope == "affected" and notify_teacher_ids:
        _notify_assigned_teachers(
            db,
            week,
            teacher_ids=notify_teacher_ids,
            update_hash=update_hash,
        )

    return week



def publish_day(
    db: Session,
    week: WeekPlan,
    day_date: date,
    actor: str = "admin",
    notify_scope: str = "all",
    notify_teacher_ids: Optional[set[int]] = None,
) -> DayPlan:
    """
    Publish a single day.

    The week version is incremented only when publishing changes visibility
    state (first publish of the week or first publish of that day). Repeating
    the same publish keeps the same version/hash, so update notifications are
    deduplicated cleanly.
    """
    day = (
        db.query(DayPlan)
        .options(
            selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.assignments)
        )
        .filter(DayPlan.week_plan_id == week.id, DayPlan.date == day_date)
        .first()
    )

    if not day:
        raise ValueError(f"Day {day_date} not found in week {week.week_start_date}")

    week_obj = db.query(WeekPlan).filter(WeekPlan.id == week.id).first()
    if not week_obj:
        raise ValueError("Week not found")

    week_was_published = str(week_obj.status) == "published"
    day_was_published = bool(day.is_published)

    state_changed = False

    if not week_was_published:
        week_obj.status = "published"
        state_changed = True
        logger.info(
            "publish_day: week %s promoted to published (first day publish)",
            week.week_start_date,
        )

    if not day_was_published:
        day.is_published = True
        state_changed = True
    else:
        day.is_published = True

    if state_changed:
        week_obj.version = (week_obj.version or 0) + 1

    _log_change(db, week_obj, actor, "publish_day", {
        "day": str(day_date),
        "notify_scope": notify_scope,
        "state_changed": state_changed,
        "version": week_obj.version,
    })
    db.commit()
    db.refresh(day)
    db.refresh(week_obj)

    update_hash = _build_week_update_hash(week_obj, day_date=day_date)

    logger.info(
        "Published day %s in week %s notify_scope=%s state_changed=%s version=%s hash=%s",
        day_date,
        week_obj.week_start_date,
        notify_scope,
        state_changed,
        week_obj.version,
        update_hash,
    )

    day_teacher_ids: set[int] = set()
    for sl in day.shift_locations:
        for a in sl.assignments:
            if a.teacher_id is not None:
                day_teacher_ids.add(int(a.teacher_id))

    if notify_scope == "all" and day_teacher_ids:
        _notify_assigned_teachers(
            db,
            week_obj,
            teacher_ids=day_teacher_ids,
            update_hash=update_hash,
        )
    elif notify_scope == "affected" and notify_teacher_ids:
        targets = notify_teacher_ids & day_teacher_ids
        if targets:
            _notify_assigned_teachers(
                db,
                week_obj,
                teacher_ids=targets,
                update_hash=update_hash,
            )

    return day


# ─── Notifications ────────────────────────────────────────────────────────────

def _get_latest_teacher_tokens_by_installation(
    db: Session,
    teacher_ids: set[int],
) -> dict[int, list[str]]:
    """
    Return one freshest token per installation for each teacher.

    This mirrors the reminder job logic so publish / republish notifications
    cannot fan out to stale rotated tokens for the same device.
    """
    if not teacher_ids:
        return {}

    rows = (
        db.query(DeviceToken)
        .filter(DeviceToken.teacher_id.in_(teacher_ids))
        .order_by(
            DeviceToken.teacher_id.asc(),
            DeviceToken.updated_at.desc(),
            DeviceToken.id.desc(),
        )
        .all()
    )

    tokens_by_teacher: dict[int, list[str]] = {}
    seen_installations: dict[int, set[str]] = {}
    seen_tokens: dict[int, set[str]] = {}

    for row in rows:
        teacher_id = int(row.teacher_id)
        token = str(getattr(row, "token", "") or "").strip()
        if not token:
            continue

        teacher_seen_tokens = seen_tokens.setdefault(teacher_id, set())
        if token in teacher_seen_tokens:
            continue

        installation_id = str(getattr(row, "installation_id", "") or "").strip()
        dedupe_key = installation_id or f"token:{token}"

        teacher_seen_installations = seen_installations.setdefault(teacher_id, set())
        if dedupe_key in teacher_seen_installations:
            continue

        teacher_seen_installations.add(dedupe_key)
        teacher_seen_tokens.add(token)
        tokens_by_teacher.setdefault(teacher_id, []).append(token)


    return tokens_by_teacher


def _build_week_update_hash(week: WeekPlan, *, day_date: Optional[date] = None) -> str:
    """
    Build a stable hash for the current published update version.

    The hash is tied to the effective week version. Re-publishing the same
    already-published state keeps the same hash, so update notifications are
    sent once per teacher for that version only.
    """
    day_part = day_date.isoformat() if day_date else "full-week"
    raw = f"{week.id}|{week.week_start_date.isoformat()}|v{int(week.version or 0)}|{day_part}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _build_duty_update_notification_type(update_hash: str) -> str:
    return f"duty_update:{update_hash}"



def _notify_assigned_teachers(
    db: Session,
    week: WeekPlan,
    teacher_ids: Optional[set[int]] = None,
    *,
    update_hash: Optional[str] = None,
) -> None:
    """
    Send push notifications to assigned teachers.

    Parameters
    ----------
    teacher_ids
        Optional subset of teacher IDs to notify. When None (default),
        every teacher assigned anywhere in the week is notified.
    update_hash
        Stable hash for the published week version. Each teacher receives
        at most one update notification for the same hash.
    """
    try:
        from services.notification_service import notify_teacher_updated
    except Exception:
        return

    week = (
        db.query(WeekPlan)
        .options(
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.assignments)
        )
        .filter(WeekPlan.id == week.id)
        .first()
    )
    if not week:
        return

    all_assigned: set[int] = set()
    for day in week.day_plans:
        for sl in day.shift_locations:
            for a in sl.assignments:
                if a.teacher_id is not None:
                    all_assigned.add(int(a.teacher_id))

    targets = (all_assigned & teacher_ids) if teacher_ids is not None else all_assigned
    if not targets:
        return

    teachers = db.query(Teacher).filter(Teacher.id.in_(targets)).all()
    teachers_by_id = {int(t.id): t for t in teachers}
    tokens_by_teacher = _get_latest_teacher_tokens_by_installation(db, targets)

    notification_type = (
        _build_duty_update_notification_type(update_hash)
        if update_hash
        else "duty_update"
    )

    pending_logs: list[NotificationLog] = []

    for tid in sorted(targets):
        teacher = teachers_by_id.get(tid)
        if not teacher:
            continue

        tokens = tokens_by_teacher.get(tid, [])
        if not tokens:
            continue

        existing_log = (
            db.query(NotificationLog)
            .filter(
                NotificationLog.teacher_id == tid,
                NotificationLog.assignment_id.is_(None),
                NotificationLog.notification_type == notification_type,
            )
            .first()
        )
        if existing_log:
            logger.info(
                "[notify] Skipping duplicate duty update for teacher=%s hash=%s",
                tid,
                update_hash or "legacy",
            )
            continue

        lang = str(teacher.preferred_language) if teacher.preferred_language else "ar"

        try:
            success_count, _bad_tokens = notify_teacher_updated(tokens, lang)
        except Exception as exc:
            logger.warning("Failed to notify teacher %s: %s", tid, exc)
            continue

        if int(success_count or 0) > 0:
            pending_logs.append(NotificationLog(
                teacher_id=tid,
                assignment_id=None,
                notification_type=notification_type,
                status="sent",
            ))

    if pending_logs:
        db.add_all(pending_logs)
        db.commit()


# ─── Old week cleanup ─────────────────────────────────────────────────────────

def purge_old_weeks(db: Session, actor: str = "system") -> int:
    cutoff = get_previous_week_start()
    old_weeks = (
        db.query(WeekPlan)
        .filter(WeekPlan.week_start_date < cutoff)
        .order_by(WeekPlan.week_start_date.asc())
        .all()
    )
    if not old_weeks:
        return 0

    week_ids = [w.id for w in old_weeks]
    day_ids = [
        row[0]
        for row in db.query(DayPlan.id).filter(DayPlan.week_plan_id.in_(week_ids)).all()
    ]
    shift_location_ids: list[int] = []
    if day_ids:
        shift_location_ids = [
            row[0]
            for row in db.query(ShiftLocation.id).filter(ShiftLocation.day_plan_id.in_(day_ids)).all()
        ]

    if shift_location_ids:
        db.query(Assignment).filter(Assignment.shift_location_id.in_(shift_location_ids)).delete(
            synchronize_session=False
        )
    if day_ids:
        db.query(ShiftLocation).filter(ShiftLocation.day_plan_id.in_(day_ids)).delete(
            synchronize_session=False
        )
    db.query(ChangeLog).filter(ChangeLog.week_plan_id.in_(week_ids)).delete(synchronize_session=False)
    if day_ids:
        db.query(DayPlan).filter(DayPlan.id.in_(day_ids)).delete(synchronize_session=False)
    db.query(WeekPlan).filter(WeekPlan.id.in_(week_ids)).delete(synchronize_session=False)
    db.commit()

    logger.info(
        "Purged %s old week(s) older than %s (actor=%s)",
        len(week_ids), cutoff, actor,
    )
    return len(week_ids)
