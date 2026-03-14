"""Week planning endpoints."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models.models import WeekPlan, DayPlan, ShiftLocation, Assignment
from schemas.schemas import WeekStatusUpdate, ShiftLocationUpdate, AssignmentUpdate, ShiftTimeUpdate
from routers.auth import get_current_admin
from services.week_service import (
    get_current_week_start,
    create_week_plan,
    clone_week,
    update_shift_location_slots,
    update_assignment,
    update_shift_time,
    publish_week,
    publish_day,
    is_day_editable,
    purge_old_weeks,
)

router = APIRouter(prefix="/weeks", tags=["weeks"])


CONFLICT_HINTS = (
    "already exists",
    "already assigned",
    "conflict",
    "duplicate",
)


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



def _get_week_or_404(db: Session, week_start: date) -> WeekPlan:
    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == week_start).first()
    if not week:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Week starting {week_start} was not found",
        )
    return week



def _raise_service_error(exc: ValueError) -> None:
    message = str(exc)
    lowered = message.lower()
    if any(hint in lowered for hint in CONFLICT_HINTS):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _cleanup_old_weeks(db: Session, actor: str) -> None:
    try:
        purge_old_weeks(db, actor=actor)
    except Exception:
        db.rollback()


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
    _cleanup_old_weeks(db, actor="system:get_current_week")
    ws = get_current_week_start()
    week = _get_week_with_relations(db, ws)
    if not week:
        return {
            "week_start_date": str(ws),
            "status": None,
            "message": "No plan found for the current week",
        }

    payload = _serialize_week(week)
    payload["message"] = "Current week loaded successfully"
    return payload


@router.get("/{week_start}")
def get_week(week_start: date, db: Session = Depends(get_db)):
    _cleanup_old_weeks(db, actor="system:get_week")
    week = _get_week_with_relations(db, week_start)
    if not week:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No plan found for week starting {week_start}",
        )

    payload = _serialize_week(week)
    payload["message"] = "Week loaded successfully"
    return payload


@router.post("/{week_start}/create", status_code=status.HTTP_201_CREATED)
def create_week(
    week_start: date,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    _cleanup_old_weeks(db, actor=str(admin))
    try:
        create_week_plan(db, week_start, actor=admin)
        week = _get_week_with_relations(db, week_start)
        if not week:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Week was created but could not be reloaded",
            )
        payload = _serialize_week(week)
        payload["message"] = f"Week {week_start} created successfully"
        return payload
    except ValueError as exc:
        _raise_service_error(exc)


@router.post("/{week_start}/clone", status_code=status.HTTP_201_CREATED)
def clone_week_endpoint(
    week_start: date,
    source_week: Optional[date] = None,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    _cleanup_old_weeks(db, actor=str(admin))
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No published week was found to clone from",
            )

        source_week = latest.week_start_date

    result = clone_week(db, source_week, week_start, actor=admin)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Could not clone into week {week_start}. "
                f"Either the target week already exists or the source week {source_week} was not found"
            ),
        )

    week = _get_week_with_relations(db, week_start)
    if not week:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cloned week could not be reloaded",
        )

    payload = _serialize_week(week)
    payload["message"] = f"Week {week_start} cloned successfully from {source_week}"
    return payload


@router.put("/{week_start}/status")
def update_week_status(
    week_start: date,
    data: WeekStatusUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    _cleanup_old_weeks(db, actor=str(admin))
    week = _get_week_or_404(db, week_start)

    try:
        if data.status == "published":
            publish_week(db, week, actor=admin)
            success_message = f"Week {week_start} published successfully"
        else:
            week.status = data.status
            db.commit()
            db.refresh(week)
            success_message = f"Week {week_start} status updated to {data.status}"
    except ValueError as exc:
        _raise_service_error(exc)

    week_loaded = _get_week_with_relations(db, week_start)
    if not week_loaded:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Updated week could not be reloaded",
        )

    payload = _serialize_week(week_loaded)
    payload["message"] = success_message
    return payload


@router.put("/{week_start}/publish-day")
def publish_single_day(
    week_start: date,
    day_date: date = Query(..., description="The exact day to publish"),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    _cleanup_old_weeks(db, actor=str(admin))
    week = _get_week_or_404(db, week_start)

    try:
        publish_day(db, week, day_date, actor=admin)
    except ValueError as exc:
        _raise_service_error(exc)

    week_loaded = _get_week_with_relations(db, week_start)
    if not week_loaded:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The day was published but the week could not be reloaded",
        )

    payload = _serialize_week(week_loaded)
    payload["message"] = f"Day {day_date} published successfully"
    return payload


@router.put("/{week_start}/shift-locations")
def update_shift_locations(
    week_start: date,
    updates: list[ShiftLocationUpdate],
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    _cleanup_old_weeks(db, actor=str(admin))
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No shift-location updates were provided",
        )

    week = _get_week_or_404(db, week_start)

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
        except ValueError as exc:
            _raise_service_error(exc)

    week_loaded = _get_week_with_relations(db, week_start)
    if not week_loaded:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shift locations were updated but the week could not be reloaded",
        )

    payload = _serialize_week(week_loaded)
    payload["message"] = "Shift locations updated successfully"
    return payload


@router.put("/{week_start}/assignments")
def update_assignments(
    week_start: date,
    updates: list[AssignmentUpdate],
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    _cleanup_old_weeks(db, actor=str(admin))
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No assignment updates were provided",
        )

    week = _get_week_or_404(db, week_start)

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
        except ValueError as exc:
            _raise_service_error(exc)

    week_loaded = _get_week_with_relations(db, week_start)
    if not week_loaded:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Assignments were updated but the week could not be reloaded",
        )

    if str(week_loaded.status) == "published":
        from services.week_service import _notify_assigned_teachers

        _notify_assigned_teachers(db, week_loaded)

    payload = _serialize_week(week_loaded)
    payload["message"] = "Assignments updated successfully"
    return payload


@router.put("/{week_start}/shift-times")
def update_shift_times(
    week_start: date,
    updates: list[ShiftTimeUpdate],
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    _cleanup_old_weeks(db, actor=str(admin))
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No shift-time updates were provided",
        )

    week = _get_week_or_404(db, week_start)

    for upd in updates:
        try:
            update_shift_time(
                db=db,
                week=week,
                shift_id=upd.shift_id,
                start_time=upd.start_time,
                end_time=upd.end_time,
                actor=admin,
            )
        except ValueError as exc:
            _raise_service_error(exc)

    week_loaded = _get_week_with_relations(db, week_start)
    if not week_loaded:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shift times were updated but the week could not be reloaded",
        )

    payload = _serialize_week(week_loaded)
    payload["message"] = "Shift times updated successfully"
    return payload
