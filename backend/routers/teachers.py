"""Teacher CRUD, self-registration, approval, device token, and schedule endpoints.

Fixes vs v2.4:
  - GET /{id}/week  now only returns duties from *published* weeks.
    Draft weeks were previously visible to teachers — they should not be.
"""

import logging
from datetime import date as date_type
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.models import Teacher, DeviceToken, DayPlan, ShiftLocation, Assignment, WeekPlan
from models.points_models import DutyConfirmation
from schemas.schemas import (
    TeacherCreate, TeacherRegister, TeacherUpdate,
    TeacherOut, TeacherStatusOut, DeviceTokenCreate,
)
from routers.auth import get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/teachers", tags=["teachers"])


# ─── Duty serialisation helper ────────────────────────────────────────────────

def _duty_dict(a: Assignment, sl: ShiftLocation, query_date: date_type) -> dict:
    """Serialise a duty assignment — duty-type aware."""
    duty_type = sl.shift.duty_type
    base = {
        "assignment_id": a.id,
        "date":          str(query_date),
        "shift_name_en": sl.shift.name_en,
        "shift_name_ar": sl.shift.name_ar,
        "shift_start":   str(sl.shift.start_time),
        "shift_end":     str(sl.shift.end_time),
        "duty_type":     duty_type,
    }
    if duty_type == "morning_endofday" and sl.location:
        base["location_name_en"] = sl.location.name_en
        base["location_name_ar"] = sl.location.name_ar
    else:
        base["location_name_en"] = None
        base["location_name_ar"] = None
    base["grade_class"] = a.grade_class
    return base


# ─── Static-path routes (must come before /{teacher_id}/…) ───────────────────

@router.get("/", response_model=List[TeacherOut])
def list_teachers(db: Session = Depends(get_db)) -> List[TeacherOut]:
    """List all approved + active teachers (public — used by admin planner)."""
    rows = (
        db.query(Teacher)
        .filter(Teacher.active.is_(True), Teacher.status == "approved")
        .order_by(Teacher.name)
        .all()
    )
    logger.debug("list_teachers → %d rows", len(rows))
    return rows


@router.get("/all", response_model=List[TeacherOut])
def list_all_teachers(
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> List[TeacherOut]:
    """List ALL teachers regardless of status or active flag (admin only)."""
    rows = db.query(Teacher).order_by(Teacher.name).all()
    logger.debug("list_all_teachers → %d rows", len(rows))
    return rows


@router.get("/pending", response_model=List[TeacherOut])
def list_pending_teachers(
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> List[TeacherOut]:
    """List teachers awaiting approval (admin only)."""
    rows = (
        db.query(Teacher)
        .filter(Teacher.status == "pending")
        .order_by(Teacher.created_at.desc())
        .all()
    )
    return rows


@router.post("/register")
def register_teacher(
    data: TeacherRegister,
    db: Session = Depends(get_db),
):
    """Self-register a new teacher (status = pending until approved)."""
    # Duplicate e-mail check
    if data.email:
        existing = db.query(Teacher).filter(Teacher.email == data.email.lower()).first()
        if existing:
            raise HTTPException(409, "This email is already registered.")

    teacher = Teacher(
        name=data.name,
        email=data.email.lower() if data.email else None,
        status="pending",
        active=True,
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    logger.info("New teacher registered: %s (id=%s)", teacher.name, teacher.id)
    return {"id": teacher.id, "name": teacher.name, "status": teacher.status}


@router.post("/approve-all")
def approve_all_pending(
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    """Approve all pending teachers in one call."""
    rows = db.query(Teacher).filter(Teacher.status == "pending").all()
    for t in rows:
        t.status = "approved"
    db.commit()
    return {"approved": len(rows)}


# ─── Dynamic-path routes (/teachers/{teacher_id}/…) ──────────────────────────

@router.get("/{teacher_id}/status")
def get_teacher_status(teacher_id: int, db: Session = Depends(get_db)):
    """Lightweight status check — used by Flutter app splash screen."""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    return {
        "id":     teacher.id,
        "name":   teacher.name,
        "email":  teacher.email,
        "status": teacher.status,
    }


@router.post("/{teacher_id}/approve")
def approve_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    teacher.status = "approved"
    db.commit()
    db.refresh(teacher)
    return teacher


@router.get("/{teacher_id}/schedule")
def get_teacher_schedule(
    teacher_id: int,
    date: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Teacher's duties for a specific date.
    Only returns duties from *published* week plans.
    """
    query_date = date_type.fromisoformat(date)
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    if str(teacher.status) != "approved":
        raise HTTPException(403, "Teacher account not yet approved")

    duties = []
    for day in db.query(DayPlan).filter(DayPlan.date == query_date).all():
        # Only include duties from published week plans
        if str(day.week_plan.status) != "published":
            continue
        for sl in day.shift_locations:
            for a in sl.assignments:
                if int(a.teacher_id or 0) == teacher_id:
                    confirmation = db.query(DutyConfirmation).filter(
                        DutyConfirmation.teacher_id == teacher_id,
                        DutyConfirmation.assignment_id == a.id,
                    ).first()
                    entry = _duty_dict(a, sl, query_date)
                    entry["already_confirmed"] = confirmation is not None
                    entry["points_earned"]     = confirmation.points_earned if confirmation else None
                    duties.append(entry)

    return {"teacher_id": teacher_id, "teacher_name": teacher.name, "duties": duties}


@router.get("/{teacher_id}/week")
def get_teacher_week(
    teacher_id: int,
    week_start: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Teacher's duties for an entire week.

    Fix (v2.5): only returns duties from a *published* week plan.
    Previously returned draft assignments, leaking unconfirmed rosters.
    """
    ws = date_type.fromisoformat(week_start)

    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    if str(teacher.status) != "approved":
        raise HTTPException(403, "Teacher account not yet approved")

    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == ws).first()

    # No week at all, or week is a draft → return empty list (not an error)
    if not week or str(week.status) != "published":
        return {
            "teacher_id":   teacher_id,
            "teacher_name": teacher.name,
            "week_status":  str(week.status) if week else None,
            "duties":       [],
        }

    duties = []
    for day in week.day_plans:
        for sl in day.shift_locations:
            for a in sl.assignments:
                if int(a.teacher_id or 0) == teacher_id:
                    confirmation = db.query(DutyConfirmation).filter(
                        DutyConfirmation.teacher_id == teacher_id,
                        DutyConfirmation.assignment_id == a.id,
                    ).first()
                    entry = _duty_dict(a, sl, day.date)
                    entry["already_confirmed"] = confirmation is not None
                    entry["points_earned"]     = confirmation.points_earned if confirmation else None
                    duties.append(entry)

    return {
        "teacher_id":   teacher_id,
        "teacher_name": teacher.name,
        "week_status":  str(week.status),
        "duties":       duties,
    }


@router.post("/{teacher_id}/device-token")
def register_device_token(
    teacher_id: int,
    data: DeviceTokenCreate,
    db: Session = Depends(get_db),
) -> dict:
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")

    existing = db.query(DeviceToken).filter(DeviceToken.token == data.token).first()
    if existing:
        existing.teacher_id = teacher_id
        existing.platform   = data.platform
    else:
        db.add(DeviceToken(teacher_id=teacher_id, token=data.token, platform=data.platform))
    db.commit()
    return {"status": "registered"}


@router.get("/{teacher_id}", response_model=TeacherOut)
def get_teacher(teacher_id: int, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    return teacher


@router.post("/", response_model=TeacherOut, status_code=201)
def create_teacher(
    data: TeacherCreate,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    """Admin-created teacher (immediately approved)."""
    teacher = Teacher(
        name=data.name,
        email=data.email.lower() if data.email else None,
        status="approved",
        active=True,
        preferred_language=getattr(data, "preferred_language", "ar"),
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.put("/{teacher_id}", response_model=TeacherOut)
def update_teacher(
    teacher_id: int,
    data: TeacherUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(teacher, field, value)

    db.commit()
    db.refresh(teacher)
    return teacher


@router.delete("/{teacher_id}", status_code=204)
def deactivate_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    """Soft-delete: set active = False."""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    teacher.active = False
    db.commit()
