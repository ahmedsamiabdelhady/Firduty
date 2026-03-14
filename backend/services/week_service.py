"""
week_service.py — Week plan creation, cloning, assignment, and publishing.

Optimized version:
- Greatly reduces flush() calls during create/clone
- Creates day rows in one batch, then flushes once
- Creates shift-location rows in one batch, then flushes once
- Creates assignment rows in one batch
- Keeps public API compatible with existing routers
"""

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
    {"name_en": "First floor - Main corridor", "slots_count": 1},
    {"name_en": "First floor - Beside teachers room", "slots_count": 1},
    {"name_en": "Area A", "slots_count": 1},
    {"name_en": "Area B", "slots_count": 1},
    {"name_en": "Area C", "slots_count": 1},
    {"name_en": "Area D", "slots_count": 1},
    {"name_en": "Second floor - Interior corridor", "slots_count": 1},
    {"name_en": "Second floor - Main corridor", "slots_count": 2},
    {"name_en": "Second floor - Beside teachers room", "slots_count": 1},
    {"name_en": "Play ground", "slots_count": 6},
    {"name_en": "Ground floor", "slots_count": 1},
    {"name_en": "Ground floor / KG2A", "slots_count": 2},
    {"name_en": "General supervision", "slots_count": 1},
]

END_OF_DAY_LOCATION_SPECS = [
    {"name_en": "Waiting room", "slots_count": 1},
    {"name_en": "Glass door", "slots_count": 1},
    {"name_en": "Stairs - KG", "slots_count": 1},
    {"name_en": "Basement floor", "slots_count": 7},
    {"name_en": "Area A", "slots_count": 1},
    {"name_en": "Area B", "slots_count": 1},
    {"name_en": "Area C", "slots_count": 1},
    {"name_en": "Area D", "slots_count": 1},
    {"name_en": "First floor", "slots_count": 1},
    {"name_en": "Second floor", "slots_count": 1},
    {"name_en": "Ground floor", "slots_count": 1},
    {"name_en": "Play ground", "slots_count": 6},
    {"name_en": "General supervision", "slots_count": 1},
]

BREAK_GRADE_CLASSES_FALLBACK = [
    "1/A", "1/B", "1/C", "1/D",
    "2/A", "2/B", "2/C", "2/D",
    "3/A", "3/B", "3/C",
    "4/A", "4/B", "4/C",
    "5/A", "5/B",
    "6/A", "6/B",
    "7/A", "7/B",
    "8/AB",
    "9",
]


def _get_break_grade_classes(db: Session) -> list[str]:
    rows = (
        db.query(GradeClass)
        .filter(GradeClass.active.is_(True))
        .order_by(GradeClass.order.asc(), GradeClass.id.asc())
        .all()
    )
    if rows:
        return [row.name_en for row in rows]
    return BREAK_GRADE_CLASSES_FALLBACK.copy()


def _find_shift_location(
    db: Session,
    day_plan_id: int,
    shift_id: int,
    location_id: Optional[int],
) -> Optional[ShiftLocation]:
    query = db.query(ShiftLocation).filter(
        ShiftLocation.day_plan_id == day_plan_id,
        ShiftLocation.shift_id == shift_id,
    )
    if location_id is None:
        query = query.filter(ShiftLocation.location_id.is_(None))
    else:
        query = query.filter(ShiftLocation.location_id == location_id)
    return query.options(selectinload(ShiftLocation.assignments)).first()


def get_current_week_start() -> date:
    now = datetime.now(MUSCAT_TZ).date()
    days_since_sunday = now.isoweekday() % 7
    return now - timedelta(days=days_since_sunday)


def get_previous_week_start() -> date:
    return get_current_week_start() - timedelta(days=7)


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
    day_ids = [row[0] for row in db.query(DayPlan.id).filter(DayPlan.week_plan_id.in_(week_ids)).all()]
    shift_location_ids = []
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
        "Purged %s old week(s) older than previous week cutoff %s by %s",
        len(week_ids),
        cutoff,
        actor,
    )
    return len(week_ids)


def get_today_muscat() -> date:
    return datetime.now(MUSCAT_TZ).date()


def is_day_editable(day_date: date) -> bool:
    return day_date >= get_today_muscat()


def _ensure_day_not_past(day_date: date) -> None:
    if day_date < get_today_muscat():
        raise ValueError("Cannot modify past days")


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


def _build_shift_alias_map(db: Session) -> dict[str, Shift]:
    shifts = db.query(Shift).order_by(Shift.order.asc(), Shift.id.asc()).all()
    result: dict[str, Shift] = {}

    for alias_key in SHIFT_NAME_ALIASES.keys():
        alias = SHIFT_NAME_ALIASES[alias_key]
        alias_en = {_normalize(v) for v in alias["en"]}
        alias_ar = {_normalize(v) for v in alias["ar"]}

        for shift in shifts:
            shift_en = _normalize(getattr(shift, "name_en", None))
            shift_ar = _normalize(getattr(shift, "name_ar", None))
            if shift_en in alias_en or shift_ar in alias_ar:
                result[alias_key] = shift
                break

    missing = [key for key in SHIFT_NAME_ALIASES.keys() if key not in result]
    if missing:
        raise ValueError(
            f"Required shifts not found in DB: {', '.join(missing)}. "
            "Please seed shifts with names for Morning Duty / First Break / "
            "Second Break / End of Day Duty."
        )

    return result


def _build_location_map(db: Session) -> dict[str, Location]:
    locations = db.query(Location).order_by(Location.order.asc(), Location.id.asc()).all()
    result: dict[str, Location] = {}

    for loc in locations:
        loc_en = _normalize(getattr(loc, "name_en", None))
        result[loc_en] = loc

    return result


def _ensure_required_locations_exist(db: Session, location_specs: list[dict]) -> dict[str, Location]:
    location_map = _build_location_map(db)

    for spec in location_specs:
        target = _normalize(spec["name_en"])
        if target not in location_map:
            raise ValueError(
                f"Required location '{spec['name_en']}' was not found in DB. "
                "Please seed the Location table with all planner locations."
            )

    return location_map


def _ensure_assignments_for_shift_location(
    db: Session,
    shift_location: ShiftLocation,
    slots_count: int,
) -> None:
    existing = {int(a.slot_index): a for a in shift_location.assignments}
    shift_location.slots_count = slots_count

    for idx in range(slots_count):
        if idx not in existing:
            db.add(
                Assignment(
                    shift_location_id=shift_location.id,
                    slot_index=idx,
                    teacher_id=None,
                    grade_class=None,
                )
            )

    for idx, assignment in existing.items():
        if idx >= slots_count:
            db.delete(assignment)


def _build_day_template_rows(
    day_id: int,
    morning_shift: Shift,
    break_1_shift: Shift,
    break_2_shift: Shift,
    end_of_day_shift: Shift,
    location_map: dict[str, Location],
    break_grade_classes: list[str],
) -> list[ShiftLocation]:
    shift_locations: list[ShiftLocation] = []
    order_counter = 0

    for spec in MORNING_LOCATION_SPECS:
        loc = location_map[_normalize(spec["name_en"])]
        shift_locations.append(
            ShiftLocation(
                day_plan_id=day_id,
                shift_id=morning_shift.id,
                location_id=loc.id,
                slots_count=int(spec["slots_count"]),
                order=order_counter,
            )
        )
        order_counter += 1

    for break_shift in (break_1_shift, break_2_shift):
        shift_locations.append(
            ShiftLocation(
                day_plan_id=day_id,
                shift_id=break_shift.id,
                location_id=None,
                slots_count=len(break_grade_classes),
                order=order_counter,
            )
        )
        order_counter += 1

    for spec in END_OF_DAY_LOCATION_SPECS:
        loc = location_map[_normalize(spec["name_en"])]
        shift_locations.append(
            ShiftLocation(
                day_plan_id=day_id,
                shift_id=end_of_day_shift.id,
                location_id=loc.id,
                slots_count=int(spec["slots_count"]),
                order=order_counter,
            )
        )
        order_counter += 1

    return shift_locations


def _populate_day_if_empty(
    db: Session,
    day: DayPlan,
    morning_shift: Shift,
    break_1_shift: Shift,
    break_2_shift: Shift,
    end_of_day_shift: Shift,
    location_map: dict[str, Location],
) -> None:
    if day.shift_locations:
        return

    break_grade_classes = _get_break_grade_classes(db)
    shift_locations = _build_day_template_rows(
        day_id=day.id,
        morning_shift=morning_shift,
        break_1_shift=break_1_shift,
        break_2_shift=break_2_shift,
        end_of_day_shift=end_of_day_shift,
        location_map=location_map,
        break_grade_classes=break_grade_classes,
    )

    db.add_all(shift_locations)
    db.flush()

    assignments: list[Assignment] = []
    break_shift_ids = {break_1_shift.id, break_2_shift.id}

    for sl in shift_locations:
        if sl.location_id is None and sl.shift_id in break_shift_ids:
            for idx, grade_class in enumerate(break_grade_classes):
                assignments.append(
                    Assignment(
                        shift_location_id=sl.id,
                        slot_index=idx,
                        teacher_id=None,
                        grade_class=grade_class,
                    )
                )
        else:
            for idx in range(int(sl.slots_count)):
                assignments.append(
                    Assignment(
                        shift_location_id=sl.id,
                        slot_index=idx,
                        teacher_id=None,
                        grade_class=None,
                    )
                )

    if assignments:
        db.add_all(assignments)


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


def ensure_week_fully_populated(db: Session, week: WeekPlan) -> WeekPlan:
    week = _get_week_with_day_plans(db, week.id)

    shift_map = _build_shift_alias_map(db)
    location_map = _ensure_required_locations_exist(
        db,
        MORNING_LOCATION_SPECS + END_OF_DAY_LOCATION_SPECS,
    )
    break_grade_classes = _get_break_grade_classes(db)

    existing_days_by_date = {day.date: day for day in week.day_plans}
    changed = False

    for i in range(WEEK_DAYS):
        day_date = week.week_start_date + timedelta(days=i)
        day = existing_days_by_date.get(day_date)

        if not day:
            day = DayPlan(
                week_plan_id=week.id,
                date=day_date,
                is_published=False,
            )
            db.add(day)
            db.flush()
            existing_days_by_date[day_date] = day
            changed = True

        if not day.shift_locations:
            shift_locations = _build_day_template_rows(
                day_id=day.id,
                morning_shift=shift_map["morning"],
                break_1_shift=shift_map["break_1"],
                break_2_shift=shift_map["break_2"],
                end_of_day_shift=shift_map["end_of_day"],
                location_map=location_map,
                break_grade_classes=break_grade_classes,
            )
            db.add_all(shift_locations)
            db.flush()

            assignments: list[Assignment] = []
            break_shift_ids = {shift_map["break_1"].id, shift_map["break_2"].id}
            for sl in shift_locations:
                if sl.location_id is None and sl.shift_id in break_shift_ids:
                    for idx, grade_class in enumerate(break_grade_classes):
                        assignments.append(
                            Assignment(
                                shift_location_id=sl.id,
                                slot_index=idx,
                                teacher_id=None,
                                grade_class=grade_class,
                            )
                        )
                else:
                    for idx in range(int(sl.slots_count)):
                        assignments.append(
                            Assignment(
                                shift_location_id=sl.id,
                                slot_index=idx,
                                teacher_id=None,
                                grade_class=None,
                            )
                        )

            if assignments:
                db.add_all(assignments)
            changed = True

    if changed:
        db.commit()

    return _get_week_with_day_plans(db, week.id)


def _is_week_fully_populated(db: Session, week: WeekPlan) -> bool:
    week = _get_week_with_day_plans(db, week.id)
    existing_days_by_date = {day.date: day for day in week.day_plans}

    for i in range(WEEK_DAYS):
        day_date = week.week_start_date + timedelta(days=i)
        day = existing_days_by_date.get(day_date)
        if not day or not day.shift_locations:
            return False

    return True


def create_week_plan(db: Session, week_start: date, actor: str = "admin") -> WeekPlan:
    existing = db.query(WeekPlan).filter(WeekPlan.week_start_date == week_start).first()

    if existing:
        week = ensure_week_fully_populated(db, existing)
        if _is_week_fully_populated(db, week):
            raise ValueError(f"Week {week_start} already exists. Cannot create it again.")
        return week

    shift_map = _build_shift_alias_map(db)
    location_map = _ensure_required_locations_exist(
        db,
        MORNING_LOCATION_SPECS + END_OF_DAY_LOCATION_SPECS,
    )
    break_grade_classes = _get_break_grade_classes(db)

    week = WeekPlan(week_start_date=week_start, status="draft", version=1)
    db.add(week)
    db.flush()

    days: list[DayPlan] = [
        DayPlan(
            week_plan_id=week.id,
            date=week_start + timedelta(days=i),
            is_published=False,
        )
        for i in range(WEEK_DAYS)
    ]
    db.add_all(days)
    db.flush()

    all_shift_locations: list[ShiftLocation] = []
    for day in days:
        all_shift_locations.extend(
            _build_day_template_rows(
                day_id=day.id,
                morning_shift=shift_map["morning"],
                break_1_shift=shift_map["break_1"],
                break_2_shift=shift_map["break_2"],
                end_of_day_shift=shift_map["end_of_day"],
                location_map=location_map,
                break_grade_classes=break_grade_classes,
            )
        )

    db.add_all(all_shift_locations)
    db.flush()

    all_assignments: list[Assignment] = []
    break_shift_ids = {shift_map["break_1"].id, shift_map["break_2"].id}

    for sl in all_shift_locations:
        if sl.location_id is None and sl.shift_id in break_shift_ids:
            for idx, grade_class in enumerate(break_grade_classes):
                all_assignments.append(
                    Assignment(
                        shift_location_id=sl.id,
                        slot_index=idx,
                        teacher_id=None,
                        grade_class=grade_class,
                    )
                )
        else:
            for idx in range(int(sl.slots_count)):
                all_assignments.append(
                    Assignment(
                        shift_location_id=sl.id,
                        slot_index=idx,
                        teacher_id=None,
                        grade_class=None,
                    )
                )

    if all_assignments:
        db.add_all(all_assignments)

    _log_change(db, week, actor, "create_week", {"week_start": str(week_start)})
    db.commit()
    db.refresh(week)
    logger.info("Created optimized week plan for %s (id=%s)", week_start, week.id)
    return week


def clone_week(
    db: Session,
    source_week_start: date,
    target_week_start: date,
    actor: str = "admin",
) -> Optional[WeekPlan]:
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

    source = ensure_week_fully_populated(db, source)
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
        DayPlan(
            week_plan_id=new_week.id,
            date=src_day.date + day_offset,
            is_published=False,
        )
        for src_day in sorted_days
    ]
    db.add_all(new_days)
    db.flush()

    all_new_shift_locations: list[ShiftLocation] = []
    sl_mapping: list[tuple[ShiftLocation, ShiftLocation]] = []

    for src_day, new_day in zip(sorted_days, new_days):
        sorted_shift_locations = sorted(
            src_day.shift_locations,
            key=lambda sl: ((sl.order if sl.order is not None else 9999), sl.id),
        )
        for src_sl in sorted_shift_locations:
            new_sl = ShiftLocation(
                day_plan_id=new_day.id,
                shift_id=src_sl.shift_id,
                location_id=src_sl.location_id,
                slots_count=src_sl.slots_count,
                order=src_sl.order,
            )
            all_new_shift_locations.append(new_sl)
            sl_mapping.append((src_sl, new_sl))

    db.add_all(all_new_shift_locations)
    db.flush()

    all_new_assignments: list[Assignment] = []
    for src_sl, new_sl in sl_mapping:
        sorted_assignments = sorted(
            src_sl.assignments,
            key=lambda a: (a.slot_index if a.slot_index is not None else 9999, a.id),
        )
        for src_a in sorted_assignments:
            all_new_assignments.append(
                Assignment(
                    shift_location_id=new_sl.id,
                    slot_index=src_a.slot_index,
                    teacher_id=src_a.teacher_id,
                    grade_class=src_a.grade_class,
                )
            )

    if all_new_assignments:
        db.add_all(all_new_assignments)

    _log_change(
        db,
        new_week,
        actor,
        "clone_week",
        {"source": str(source_week_start), "target": str(target_week_start)},
    )
    db.commit()
    db.refresh(new_week)
    logger.info("Cloned optimized %s → %s (id=%s)", source_week_start, target_week_start, new_week.id)
    return new_week


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
        .filter(
            DayPlan.week_plan_id == week.id,
            DayPlan.date == day_date,
        )
        .first()
    )
    if not day:
        day = DayPlan(
            week_plan_id=week.id,
            date=day_date,
            is_published=False,
        )
        db.add(day)
        db.flush()

    sl_query = db.query(ShiftLocation).filter(
        ShiftLocation.day_plan_id == day.id,
        ShiftLocation.shift_id == shift_id,
    )

    if location_id is None:
        sl_query = sl_query.filter(ShiftLocation.location_id.is_(None))
    else:
        sl_query = sl_query.filter(ShiftLocation.location_id == location_id)

    sl = sl_query.options(selectinload(ShiftLocation.assignments)).first()

    if not sl:
        max_order = (
            db.query(ShiftLocation)
            .filter(ShiftLocation.day_plan_id == day.id)
            .count()
        )

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
        sl.location_id = location_id
        sl.slots_count = slots_count

    existing = sorted(sl.assignments, key=lambda a: a.slot_index)
    current = len(existing)

    if slots_count > current:
        for idx in range(current, slots_count):
            db.add(
                Assignment(
                    shift_location_id=sl.id,
                    slot_index=idx,
                    teacher_id=None,
                    grade_class=None,
                )
            )
    elif slots_count < current:
        for a in existing[slots_count:]:
            db.delete(a)

    _log_change(
        db,
        week,
        actor,
        "update_slots",
        {
            "day": str(day_date),
            "shift_id": shift_id,
            "location_id": location_id,
            "slots_count": slots_count,
        },
    )
    db.commit()
    db.refresh(sl)
    return sl


def update_shift_time(
    db: Session,
    week: WeekPlan,
    shift_id: int,
    start_time,
    end_time,
    actor: str = "admin",
) -> Shift:
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise ValueError(f"Shift {shift_id} not found")

    shift.start_time = start_time
    shift.end_time = end_time

    _log_change(
        db,
        week,
        actor,
        "update_shift_time",
        {
            "shift_id": shift_id,
            "start_time": str(start_time),
            "end_time": str(end_time),
        },
    )
    db.commit()
    db.refresh(shift)
    return shift


def update_assignment(
    db: Session,
    week: WeekPlan,
    shift_location_id: int,
    slot_index: int,
    teacher_id: Optional[int],
    grade_class: Optional[str],
    actor: str = "admin",
) -> Assignment:
    sl = db.query(ShiftLocation).filter(ShiftLocation.id == shift_location_id).first()
    if not sl:
        raise ValueError(f"ShiftLocation {shift_location_id} not found")

    day = db.query(DayPlan).filter(DayPlan.id == sl.day_plan_id).first()
    if not day or day.week_plan_id != week.id:
        raise ValueError(
            f"ShiftLocation {shift_location_id} does not belong to week {week.week_start_date}"
        )

    _ensure_day_not_past(day.date)

    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.shift_location_id == shift_location_id,
            Assignment.slot_index == slot_index,
        )
        .first()
    )
    if not assignment:
        assignment = Assignment(
            shift_location_id=shift_location_id,
            slot_index=slot_index,
        )
        db.add(assignment)
        db.flush()

    if teacher_id is not None:
        same_shift_location_ids = (
            db.query(ShiftLocation.id)
            .filter(
                ShiftLocation.day_plan_id == day.id,
                ShiftLocation.shift_id == sl.shift_id,
            )
            .subquery()
        )

        conflict = (
            db.query(Assignment)
            .filter(
                Assignment.teacher_id == teacher_id,
                Assignment.shift_location_id.in_(same_shift_location_ids),
                ~(
                    (Assignment.shift_location_id == shift_location_id)
                    & (Assignment.slot_index == slot_index)
                ),
            )
            .first()
        )

        if conflict:
            raise ValueError(
                "This teacher is already assigned in the same duty for this day"
            )

    assignment.teacher_id = teacher_id
    if grade_class is not None:
        assignment.grade_class = grade_class

    _log_change(
        db,
        week,
        actor,
        "update_assignment",
        {
            "shift_location_id": shift_location_id,
            "slot_index": slot_index,
            "teacher_id": teacher_id,
            "grade_class": grade_class,
        },
    )
    db.commit()
    db.refresh(assignment)
    return assignment


def publish_week(db: Session, week: WeekPlan, actor: str = "admin") -> WeekPlan:
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

    week.status = "published"
    week.version = (week.version or 0) + 1

    for day in week.day_plans:
        if hasattr(day, "is_published"):
            day.is_published = True

    _log_change(db, week, actor, "publish", {"version": week.version})
    db.commit()
    db.refresh(week)
    logger.info("Week %s published (v%s)", week.week_start_date, week.version)
    _notify_assigned_teachers(db, week)
    return week


def publish_day(
    db: Session,
    week: WeekPlan,
    day_date: date,
    actor: str = "admin",
) -> DayPlan:
    day = (
        db.query(DayPlan)
        .options(
            selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.assignments)
        )
        .filter(
            DayPlan.week_plan_id == week.id,
            DayPlan.date == day_date,
        )
        .first()
    )

    if not day:
        raise ValueError(f"Day {day_date} not found in week {week.week_start_date}")

    if not hasattr(day, "is_published"):
        raise ValueError(
            "DayPlan.is_published field is missing. Add it to the model/database first."
        )

    day.is_published = True

    _log_change(db, week, actor, "publish_day", {"day": str(day_date)})
    db.commit()
    db.refresh(day)

    logger.info("Published day %s in week %s", day_date, week.week_start_date)

    try:
        from services.notification_service import notify_teacher_updated
    except Exception:
        return day

    teacher_ids: set[int] = set()
    for sl in day.shift_locations:
        for a in sl.assignments:
            if a.teacher_id is not None:
                teacher_ids.add(int(a.teacher_id))

    if not teacher_ids:
        return day

    teachers = db.query(Teacher).filter(Teacher.id.in_(teacher_ids)).all()
    teachers_by_id = {int(t.id): t for t in teachers}

    device_tokens = db.query(DeviceToken).filter(DeviceToken.teacher_id.in_(teacher_ids)).all()
    tokens_by_teacher: dict[int, list[str]] = {}
    for dt in device_tokens:
        tokens_by_teacher.setdefault(int(dt.teacher_id), []).append(str(dt.token))

    for tid in teacher_ids:
        teacher = teachers_by_id.get(tid)
        if not teacher:
            continue

        tokens = tokens_by_teacher.get(tid, [])
        if tokens:
            lang = str(teacher.preferred_language) if teacher.preferred_language else "ar"
            notify_teacher_updated(tokens, lang)

    return day


def _notify_assigned_teachers(db: Session, week: WeekPlan) -> None:
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

    teacher_ids: set[int] = set()
    for day in week.day_plans:
        for sl in day.shift_locations:
            for a in sl.assignments:
                if a.teacher_id is not None:
                    teacher_ids.add(int(a.teacher_id))

    if not teacher_ids:
        return

    teachers = db.query(Teacher).filter(Teacher.id.in_(teacher_ids)).all()
    teachers_by_id = {int(t.id): t for t in teachers}

    device_tokens = db.query(DeviceToken).filter(DeviceToken.teacher_id.in_(teacher_ids)).all()
    tokens_by_teacher: dict[int, list[str]] = {}
    for dt in device_tokens:
        tokens_by_teacher.setdefault(int(dt.teacher_id), []).append(str(dt.token))

    for tid in teacher_ids:
        teacher = teachers_by_id.get(tid)
        if not teacher:
            continue

        tokens = tokens_by_teacher.get(tid, [])
        if tokens:
            lang = str(teacher.preferred_language) if teacher.preferred_language else "ar"
            notify_teacher_updated(tokens, lang)
