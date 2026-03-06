"""Week planning endpoints."""

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.models import WeekPlan, DayPlan, ShiftLocation, Assignment
from schemas.schemas import WeekPlanOut, WeekStatusUpdate, ShiftLocationUpdate, AssignmentUpdate
from routers.auth import get_current_admin
from services.week_service import (
    get_current_week_start, create_week_plan, clone_week,
    update_shift_location_slots, update_assignment, publish_week
)

router = APIRouter(prefix="/weeks", tags=["weeks"])


def _serialize_week(week: WeekPlan) -> dict:
    """Serialize a week plan with all nested data including teacher names."""
    result = {
        "id": week.id,
        "week_start_date": str(week.week_start_date),
        "status": week.status,
        "version": week.version,
        "cloned_from_week_start": str(week.cloned_from_week_start) if week.cloned_from_week_start else None,
        "created_at": week.created_at.isoformat(),
        "updated_at": week.updated_at.isoformat(),
        "day_plans": []
    }
    for day in week.day_plans:
        day_data = {"id": day.id, "date": str(day.date), "shift_locations": []}
        for sl in day.shift_locations:
            sl_data = {
                "id": sl.id,
                "shift_id": sl.shift_id,
                "location_id": sl.location_id,
                "slots_count": sl.slots_count,
                "order": sl.order,
                "shift": {
                    "id": sl.shift.id,
                    "name_en": sl.shift.name_en,
                    "name_ar": sl.shift.name_ar,
                    "start_time": str(sl.shift.start_time),
                    "end_time": str(sl.shift.end_time),
                    "order": sl.shift.order
                },
                "location": {
                    "id": sl.location.id,
                    "name_en": sl.location.name_en,
                    "name_ar": sl.location.name_ar,
                    "order": sl.location.order
                },
                "assignments": [
                    {
                        "id": a.id,
                        "slot_index": a.slot_index,
                        "teacher_id": a.teacher_id,
                        "teacher_name": a.teacher.name if a.teacher else None
                    }
                    for a in sl.assignments
                ]
            }
            day_data["shift_locations"].append(sl_data)
        result["day_plans"].append(day_data)
    return result


@router.get("/current")
def get_current_week(db: Session = Depends(get_db)):
    """Get the current week's plan."""
    ws = get_current_week_start()
    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == ws).first()
    if not week:
        return {"week_start_date": str(ws), "status": None, "message": "No plan for current week"}
    return _serialize_week(week)


@router.get("/{week_start}")
def get_week(week_start: date, db: Session = Depends(get_db)):
    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == week_start).first()
    if not week:
        raise HTTPException(404, f"No plan found for week starting {week_start}")
    return _serialize_week(week)


@router.post("/{week_start}/create")
def create_week(week_start: date, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    existing = db.query(WeekPlan).filter(WeekPlan.week_start_date == week_start).first()
    if existing:
        raise HTTPException(400, "Week plan already exists")
    week = create_week_plan(db, week_start, actor=admin)
    return _serialize_week(week)


@router.post("/{week_start}/clone")
def clone_week_endpoint(week_start: date, source_week: Optional[date] = None,
                         db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    """Clone from source_week (or latest published week) to week_start."""
    if not source_week:
        # Find the latest published week before this one
        latest = db.query(WeekPlan).filter(
            WeekPlan.status == "published",
            WeekPlan.week_start_date < week_start
        ).order_by(WeekPlan.week_start_date.desc()).first()
        if not latest:
            raise HTTPException(404, "No published week found to clone from")
        source_week = latest.week_start_date

    result = clone_week(db, source_week, week_start, actor=admin)
    if result is None:
        raise HTTPException(400, f"Week {week_start} already exists or source {source_week} not found")
    return _serialize_week(result)


@router.put("/{week_start}/status")
def update_week_status(week_start: date, data: WeekStatusUpdate,
                        db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == week_start).first()
    if not week:
        raise HTTPException(404, "Week not found")
    if data.status == "published":
        publish_week(db, week, actor=admin)
    else:
        week.status = data.status
        db.commit()
        db.refresh(week)
    return _serialize_week(week)


@router.put("/{week_start}/shift-locations")
def update_shift_locations(week_start: date, updates: List[ShiftLocationUpdate],
                             db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    """Update slots_count for one or more shift+location combinations."""
    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == week_start).first()
    if not week:
        raise HTTPException(404, "Week not found")
    for upd in updates:
        update_shift_location_slots(db, week, upd.day_date, upd.shift_id,
                                     upd.location_id, upd.slots_count, actor=admin)
    db.refresh(week)
    return _serialize_week(week)


@router.put("/{week_start}/assignments")
def update_assignments(week_start: date, updates: List[AssignmentUpdate],
                        db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    """Bulk update teacher assignments."""
    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == week_start).first()
    if not week:
        raise HTTPException(404, "Week not found")
    for upd in updates:
        try:
            update_assignment(db, week, upd.shift_location_id, upd.slot_index,
                               upd.teacher_id, actor=admin)
        except ValueError as e:
            raise HTTPException(400, str(e))
    db.refresh(week)
    # Notify affected teachers if week is published
    if week.status == "published":
        from services.week_service import _notify_assigned_teachers
        _notify_assigned_teachers(db, week, action="updated")
    return _serialize_week(week)