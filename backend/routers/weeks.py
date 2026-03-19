"""Week planning endpoints — Firduty v2.5

Fixes vs v2.4:
  - POST /create  now returns the full serialised week (not just a stub dict)
  - POST /clone   distinguishes 404 (source not found) from 409 (target exists)
  - PUT  /assignments  only notifies *newly-assigned* teachers, not all of them
  - PUT  /shift-locations  rejects slots_count < 1 (server-side guard)
"""

from datetime import date
from typing import Optional, list

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    _notify_assigned_teachers,   # re-export used here for scoped notifications
)

router = APIRouter(prefix="/weeks", tags=["weeks"])


CONFLICT_HINTS = (
    "already exists",
    "already assigned",
    "conflict",
    "duplicate",
)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _get_week_with_relations(db: Session, week_start: date) -> Optional[WeekPlan]:
    """Eager-load full week with all nested relations (no N+1 during serialisation)."""
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
    if any(h in message.lower() for h in CONFLICT_HINTS):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _serialize_week(week: WeekPlan) -> dict:
    """Full nested week serialisation — duty-type aware."""
    result: dict = {
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

    for day in sorted(week.day_plans, key=lambda d: d.date):
        day_data: dict = {
            "id": day.id,
            "date": str(day.date),
            "is_published": bool(day.is_published),   # no hasattr — field is NOT NULL in DB
            "is_editable": bool(is_day_editable(day.date)),
            "shift_locations": [],
        }

        for sl in sorted(
            day.shift_locations,
            key=lambda sl: ((sl.order if sl.order is not None else 9999), sl.id),
        ):
            duty_type = sl.shift.duty_type if sl.shift else None

            sl_data: dict = {
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
                } if sl.shift else None,
                "location": {
                    "id": sl.location.id,
                    "name_en": sl.location.name_en,
                    "name_ar": sl.location.name_ar,
                    "order": sl.location.order,
                } if sl.location else None,
                "assignments": [
                    {
                        "id": a.id,
                        "slot_index": a.slot_index,
                        "teacher_id": a.teacher_id,
                        "teacher_name": a.teacher.name if a.teacher else None,
                        "grade_class": a.grade_class,
                    }
                    for a in sorted(
                        sl.assignments,
                        key=lambda a: (a.slot_index if a.slot_index is not None else 9999, a.id),
                    )
                ],
            }
            day_data["shift_locations"].append(sl_data)

        result["day_plans"].append(day_data)

    return result


def _collect_teacher_ids(week: WeekPlan) -> set[int]:
    """Collect all teacher IDs currently assigned in the week."""
    ids: set[int] = set()
    for day in week.day_plans:
        for sl in day.shift_locations:
            for a in sl.assignments:
                if a.teacher_id is not None:
                    ids.add(int(a.teacher_id))
    return ids


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/current")
def get_current_week(db: Session = Depends(get_db)):
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
    """
    Create a new draft week.  Returns the full serialised week so the planner
    can render immediately without a second round-trip.
    Raises 409 if the week already exists (idempotent guard in service).
    """
    try:
        create_week_plan(db, week_start, actor=admin)
    except ValueError as exc:
        _raise_service_error(exc)

    week_loaded = _get_week_with_relations(db, week_start)
    if not week_loaded:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Week was created but could not be reloaded",
        )

    payload = _serialize_week(week_loaded)
    payload["message"] = f"Week {week_start} created successfully"
    return payload


@router.post("/{week_start}/clone", status_code=status.HTTP_201_CREATED)
def clone_week_endpoint(
    week_start: date,
    source_week: Optional[date] = None,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    Clone the latest published week (or a specific source) into week_start.
    Returns the full serialised week.

    Error differentiation (fixed vs v2.4):
      - 404  source published week not found
      - 409  target week already exists
    """
    # If no source given, find the latest published week before the target
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

    # Check target doesn't already exist BEFORE calling service
    # (so we can return 409 vs 404 clearly)
    if db.query(WeekPlan).filter(WeekPlan.week_start_date == week_start).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Week {week_start} already exists",
        )

    # Check source exists
    if not db.query(WeekPlan).filter(WeekPlan.week_start_date == source_week).first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source week {source_week} was not found",
        )

    result = clone_week(db, source_week, week_start, actor=admin)
    if result is None:
        # Defensive: service returned None unexpectedly
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Could not clone into week {week_start}",
        )

    week_loaded = _get_week_with_relations(db, week_start)
    if not week_loaded:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Week was cloned but could not be reloaded",
        )

    payload = _serialize_week(week_loaded)
    payload["message"] = f"Week {week_start} cloned successfully from {source_week}"
    return payload


@router.put("/{week_start}/status")
def update_week_status(
    week_start: date,
    data: WeekStatusUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    week = _get_week_or_404(db, week_start)

    notify_ids: Optional[set[int]] = (
        set(data.notify_teacher_ids) if data.notify_teacher_ids else None
    )

    try:
        if data.status == "published":
            publish_week(
                db, week, actor=admin,
                notify_scope=data.notify_scope or "all",
                notify_teacher_ids=notify_ids,
            )
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
    day_date: date = Query(..., description="The exact day to publish (YYYY-MM-DD)"),
    notify_scope: str = Query("all", description="'all' | 'affected' | 'none'"),
    notify_teacher_ids: Optional[List[int]] = Query(
        None,
        description="Teacher IDs to notify when notify_scope='affected'"
    ),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    from typing import List as _List
    week = _get_week_or_404(db, week_start)
    ids_set: Optional[set[int]] = set(notify_teacher_ids) if notify_teacher_ids else None

    try:
        publish_day(
            db, week, day_date, actor=admin,
            notify_scope=notify_scope,
            notify_teacher_ids=ids_set,
        )
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
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No shift-location updates were provided",
        )

    # Server-side guard: slots_count must be at least 1
    # (frontend already enforces Math.max(0,…) but defence-in-depth matters)
    for upd in updates:
        if upd.slots_count is not None and upd.slots_count < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"slots_count must be at least 1 (got {upd.slots_count} for shift_id={upd.shift_id})",
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
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No assignment updates were provided",
        )

    week = _get_week_or_404(db, week_start)

    # Snapshot teacher IDs *before* changes so we can diff after
    week_before = _get_week_with_relations(db, week_start)
    teachers_before: set[int] = _collect_teacher_ids(week_before) if week_before else set()

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

    # Only notify teachers who are *newly* assigned (not those already in the week)
    # This prevents re-notifying all teachers on every incremental save to a
    # published week.
    if str(week_loaded.status) == "published":
        teachers_after  = _collect_teacher_ids(week_loaded)
        newly_assigned  = teachers_after - teachers_before
        if newly_assigned:
            _notify_assigned_teachers(db, week_loaded, teacher_ids=newly_assigned)

    payload = _serialize_week(week_loaded)
    payload["message"] = "Assignments updated successfully"
    return payload
