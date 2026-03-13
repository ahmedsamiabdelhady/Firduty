"""Week planning endpoints."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models.models import WeekPlan, DayPlan, ShiftLocation, Assignment
from schemas.schemas import WeekStatusUpdate, ShiftLocationUpdate, AssignmentUpdate
from routers.auth import get_current_admin
from services.week_service import (
    get_current_week_start,
    create_week_plan,
    clone_week,
    update_shift_location_slots,
    update_assignment,
    publish_week,
    publish_day,
    is_day_editable,
    ensure_week_fully_populated,
)

router = APIRouter(prefix="/weeks", tags=["weeks"])


def _get_week_with_relations(db: Session, week_start: date) -> Optional[WeekPlan]:
    """
    Load a week with all nested relations eagerly to avoid N+1 queries during serialization.
    """
    return (
        db.query(WeekPlan)
        .options(
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.shift),
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.location),
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.assignments)
            .selectinload(Assignment.teacher),
        )
        .filter(WeekPlan.week_start_date == week_start)
        .first()
    )


def _serialize_week(week: WeekPlan) -> dict:
    """Full nested week serialization — duty-type aware."""
    result = {
        "id": week.id,
        "week_start_date": str(week.week_start_date),
        "status": str(week.status),
        "version": week.version,
        "cloned_from_week_start": (
            str(week.cloned_from_week_start)
            if week.cloned_from_week_start is not None
            else None
        ),
        "created_at": week.created_at.isoformat(),
        "updated_at": week.updated_at.isoformat(),
        "day_plans": [],
    }

    sorted_days = sorted(week.day_plans, key=lambda d: d.date)

    for day in sorted_days:
        day_data = {
            "id": day.id,
            "date": str(day.date),
            "is_published": bool(getattr(day, "is_published", False)),
            "is_editable": bool(is_day_editable(day.date)),
            "shift_locations": [],
        }

        sorted_shift_locations = sorted(
            day.shift_locations,
            key=lambda sl: ((sl.order if sl.order is not None else 9999), sl.id),
        )

        for sl in sorted_shift_locations:
            duty_type = sl.shift.duty_type if sl.shift else None

            sorted_assignments = sorted(
                sl.assignments,
                key=lambda a: (a.slot_index if a.slot_index is not None else 9999, a.id),
            )

            sl_data = {
                "id": sl.id,
                "shift_id": sl.shift_id,
                "location_id": sl.location_id,
                "slots_count": sl.slots_count,
                "order": sl.order,
                "duty_type": duty_type,
                "shift": {
                    "id": sl.shift.id,
                    "name_en": sl.shift.name_en,
                    "name_ar": sl.shift.name_ar,
                    "start_time": str(sl.shift.start_time),
                    "end_time": str(sl.shift.end_time),
                    "order": sl.shift.order,
                    "duty_type": duty_type,
                }
                if sl.shift
                else None,
                "location": {
                    "id": sl.location.id,
                    "name_en": sl.location.name_en,
                    "name_ar": sl.location.name_ar,
                    "order": sl.location.order,
                }
                if sl.location
                else None,
                "assignments": [
                    {
                        "id": a.id,
                        "slot_index": a.slot_index,
                        "teacher_id": a.teacher_id,
                        "teacher_name": a.teacher.name if a.teacher else None,
                        "grade_class": a.grade_class,
                    }
                    for a in sorted_assignments
                ],
            }
            day_data["shift_locations"].append(sl_data)

        result["day_plans"].append(day_data)

    return result


@router.get("/current")
def get_current_week(db: Session = Depends(get_db)):
    ws = get_current_week_start()
    week = _get_week_with_relations(db, ws)
    if not week:
        return {
            "week_start_date": str(ws),
            "status": None,
            "message": "No plan for current week",
        }

    # IMPORTANT:
    # Do NOT call ensure_week_fully_populated() on GET.
    return _serialize_week(week)


@router.get("/{week_start}")
def get_week(week_start: date, db: Session = Depends(get_db)):
    week = _get_week_with_relations(db, week_start)
    if not week:
        raise HTTPException(404, f"No plan found for week starting {week_start}")

    # IMPORTANT:
    # Do NOT call ensure_week_fully_populated() on GET.
    return _serialize_week(week)


@router.post("/{week_start}/create")
def create_week(
    week_start: date,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        create_week_plan(db, week_start, actor=admin)
        week = _get_week_with_relations(db, week_start)
        if not week:
            raise HTTPException(500, "Week was created but could not be reloaded")
        return _serialize_week(week)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/{week_start}/clone")
def clone_week_endpoint(
    week_start: date,
    source_week: Optional[date] = None,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    if not source_week:
        latest = (
            db.query(WeekPlan)
            .filter(
                WeekPlan.status == "published",
                WeekPlan.week_start_date < week_start,
            )
            .order_by(WeekPlan.week_start_date.desc())
            .first()
        )

        if not latest:
            raise HTTPException(404, "No published week found to clone from")

        source_week = latest.week_start_date

    result = clone_week(db, source_week, week_start, actor=admin)
    if result is None:
        raise HTTPException(
            400,
            f"Week {week_start} already exists or source {source_week} not found",
        )

    week = _get_week_with_relations(db, week_start)
    if not week:
        raise HTTPException(500, "Cloned week could not be reloaded")

    return _serialize_week(week)


@router.put("/{week_start}/status")
def update_week_status(
    week_start: date,
    data: WeekStatusUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == week_start).first()
    if not week:
        raise HTTPException(404, "Week not found")

    # Optional safety for old/incomplete historical data only:
    # week = ensure_week_fully_populated(db, week)

    if data.status == "published":
        publish_week(db, week, actor=admin)
    else:
        week.status = data.status
        db.commit()
        db.refresh(week)

    week_loaded = _get_week_with_relations(db, week_start)
    if not week_loaded:
        raise HTTPException(500, "Updated week could not be reloaded")

    return _serialize_week(week_loaded)


@router.put("/{week_start}/publish-day")
def publish_single_day(
    week_start: date,
    day_date: date = Query(..., description="The exact day to publish"),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == week_start).first()
    if not week:
        raise HTTPException(404, "Week not found")

    try:
        publish_day(db, week, day_date, actor=admin)
    except ValueError as e:
        raise HTTPException(400, str(e))

    week_loaded = _get_week_with_relations(db, week_start)
    if not week_loaded:
        raise HTTPException(500, "Published day but failed to reload week")

    return _serialize_week(week_loaded)


@router.put("/{week_start}/shift-locations")
def update_shift_locations(
    week_start: date,
    updates: list[ShiftLocationUpdate],
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == week_start).first()
    if not week:
        raise HTTPException(404, "Week not found")

    for upd in updates:
        try:
            update_shift_location_slots(
                db=db,
                week=week,
                day_date=upd.day_date,
                shift_id=upd.shift_id,
                location_id=upd.location_id,
                slots_count=upd.slots_count,
                actor=admin,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))

    week_loaded = _get_week_with_relations(db, week_start)
    if not week_loaded:
        raise HTTPException(500, "Shift locations updated but failed to reload week")

    return _serialize_week(week_loaded)


@router.put("/{week_start}/assignments")
def update_assignments(
    week_start: date,
    updates: list[AssignmentUpdate],
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == week_start).first()
    if not week:
        raise HTTPException(404, "Week not found")

    for upd in updates:
        try:
            update_assignment(
                db=db,
                week=week,
                shift_location_id=upd.shift_location_id,
                slot_index=upd.slot_index,
                teacher_id=upd.teacher_id,
                grade_class=upd.grade_class,
                actor=admin,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))

    week_loaded = _get_week_with_relations(db, week_start)
    if not week_loaded:
        raise HTTPException(500, "Assignments updated but failed to reload week")

    if str(week_loaded.status) == "published":
        from services.week_service import _notify_assigned_teachers

        _notify_assigned_teachers(db, week_loaded)

    return _serialize_week(week_loaded)