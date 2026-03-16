"""Teacher CRUD, self-registration, approval, device token, and schedule endpoints."""

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

VALID_TEACHER_STATUSES = {"pending", "approved"}
VALID_TEACHER_LANGUAGES = {"ar", "en"}


def _duty_dict(a: Assignment, sl: ShiftLocation, query_date: date_type) -> dict:
    """Serialize a duty assignment — duty-type aware."""
    duty_type = sl.shift.duty_type
    base = {
        "assignment_id": a.id,
        "date": str(query_date),
        "shift_name_en": sl.shift.name_en,
        "shift_name_ar": sl.shift.name_ar,
        "shift_start": str(sl.shift.start_time),
        "shift_end": str(sl.shift.end_time),
        "duty_type": duty_type,
    }
    if duty_type == "morning_endofday" and sl.location:
        base["location_name_en"] = sl.location.name_en
        base["location_name_ar"] = sl.location.name_ar
    else:
        base["location_name_en"] = None
        base["location_name_ar"] = None
    base["grade_class"] = a.grade_class
    return base


def _normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    value = email.strip().lower()
    return value or None


def _validate_language(value: str | None) -> str:
    language = (value or "ar").strip().lower()
    if language not in VALID_TEACHER_LANGUAGES:
        raise HTTPException(400, "Preferred language must be 'ar' or 'en'")
    return language


def _validate_status(value: str | None) -> str:
    status = (value or "approved").strip().lower()
    if status not in VALID_TEACHER_STATUSES:
        raise HTTPException(400, "Status must be 'pending' or 'approved'")
    return status


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
    """List active teachers only for admin management page."""
    rows = (
        db.query(Teacher)
        .filter(Teacher.active.is_(True))
        .order_by(Teacher.name)
        .all()
    )
    logger.debug("list_all_teachers → %d rows", len(rows))
    return rows


@router.get("/pending", response_model=List[TeacherOut])
def list_pending_teachers(
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> List[TeacherOut]:
    """List active teachers awaiting approval (admin only)."""
    rows = (
        db.query(Teacher)
        .filter(Teacher.active.is_(True), Teacher.status == "pending")
        .order_by(Teacher.created_at)
        .all()
    )
    logger.debug("list_pending_teachers → %d rows", len(rows))
    return rows


@router.post("/", response_model=TeacherOut)
def create_teacher(
    data: TeacherCreate,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> TeacherOut:
    """Admin-only: create a teacher directly (bypasses approval flow)."""
    name = data.name.strip()
    if not name:
        raise HTTPException(400, "Teacher name is required")

    email = _normalize_email(data.email)
    if email:
        existing = db.query(Teacher).filter(Teacher.email == email).first()
        if existing and bool(existing.active):
            raise HTTPException(409, "Email already registered")
        if existing and not bool(existing.active):
            raise HTTPException(409, "This email belongs to a removed teacher record")

    teacher = Teacher(
        name=name,
        email=email,
        status=_validate_status(data.status),
        active=bool(data.active),
        preferred_language=_validate_language(data.preferred_language),
    )

    db.add(teacher)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("create_teacher DB error — name=%r email=%r", name, email)
        raise HTTPException(500, f"Database error: {exc}") from exc
    db.refresh(teacher)
    logger.info("Created teacher id=%d name=%r", teacher.id, teacher.name)
    return teacher


@router.post("/register", response_model=TeacherStatusOut)
def register_teacher(
    data: TeacherRegister,
    db: Session = Depends(get_db),
) -> TeacherStatusOut:
    """
    Public self-registration.
    Creates a teacher with status='pending'. Admin must approve.
    Returns 409 if the email is already registered.
    """
    name = data.name.strip()
    if not name:
        raise HTTPException(400, "Teacher name is required")

    email_lower = _normalize_email(data.email)
    if not email_lower:
        raise HTTPException(400, "Email is required")

    existing = db.query(Teacher).filter(Teacher.email == email_lower).first()
    if existing:
        raise HTTPException(409, "Email already registered")

    teacher = Teacher(
        name=name,
        email=email_lower,
        status="pending",
        active=True,
        preferred_language="ar",
    )
    db.add(teacher)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("register_teacher DB error — email=%s", email_lower)
        raise HTTPException(500, f"Database error: {exc}") from exc
    db.refresh(teacher)
    logger.info("Teacher registered (pending) id=%d email=%s", teacher.id, email_lower)
    return teacher


@router.post("/approve-all")
def approve_all_pending(
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict:
    """Approve every active pending teacher in one operation (admin only)."""
    pending = (
        db.query(Teacher)
        .filter(Teacher.active.is_(True), Teacher.status == "pending")
        .all()
    )
    count = len(pending)
    for teacher in pending:
        setattr(teacher, "status", "approved")
    db.commit()
    logger.info("approve_all_pending → approved %d teachers", count)
    return {"approved_count": count}


# ─── Parameterised routes /{teacher_id}/… ─────────────────────────────────────

@router.put("/{teacher_id}", response_model=TeacherOut)
def update_teacher(
    teacher_id: int,
    data: TeacherUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> TeacherOut:
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")

    payload = (
        data.model_dump(exclude_none=True)
        if hasattr(data, "model_dump")
        else data.dict(exclude_none=True)
    )

    if "name" in payload:
        payload["name"] = str(payload["name"]).strip()
        if not payload["name"]:
            raise HTTPException(400, "Teacher name is required")

    if "email" in payload:
        new_email = _normalize_email(payload.get("email"))
        if new_email:
            existing = db.query(Teacher).filter(Teacher.email == new_email).first()
            if existing and int(existing.id) != int(teacher_id):
                raise HTTPException(409, "Email already registered")
        payload["email"] = new_email

    if "preferred_language" in payload:
        payload["preferred_language"] = _validate_language(payload.get("preferred_language"))

    if "status" in payload:
        payload["status"] = _validate_status(payload.get("status"))

    for field, value in payload.items():
        setattr(teacher, field, value)

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("update_teacher DB error — teacher_id=%d payload=%s", teacher_id, payload)
        raise HTTPException(500, f"Database error: {exc}") from exc

    db.refresh(teacher)
    logger.info("Updated teacher id=%d", teacher.id)
    return teacher


@router.delete("/{teacher_id}")
def delete_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict:
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    if not bool(teacher.active):
        return {"status": "already_deactivated", "id": teacher_id}
    setattr(teacher, "active", False)
    db.commit()
    logger.info("Deactivated teacher id=%d name=%r", teacher.id, teacher.name)
    return {"status": "deactivated", "id": teacher_id}


@router.get("/{teacher_id}/status", response_model=TeacherStatusOut)
def get_teacher_status(
    teacher_id: int,
    db: Session = Depends(get_db),
) -> TeacherStatusOut:
    """
    Public endpoint — Flutter app checks this on every launch.
    Returns 404 if the teacher record no longer exists.
    """
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    return teacher


@router.post("/{teacher_id}/approve", response_model=TeacherOut)
def approve_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> TeacherOut:
    """Approve a single pending teacher (admin only)."""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    setattr(teacher, "status", "approved")
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
    Get a teacher's duties for a specific date.
    Returns duty_type, location (for morning/end-of-day), grade_class (for break),
    plus assignment_id and already_confirmed status.
    """
    query_date = date_type.fromisoformat(date)
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    if str(teacher.status) != "approved":
        raise HTTPException(403, "Teacher account not yet approved")

    duties = []
    for day in db.query(DayPlan).filter(DayPlan.date == query_date).all():
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
                    entry["points_earned"] = confirmation.points_earned if confirmation else None
                    duties.append(entry)

    return {"teacher_id": teacher_id, "teacher_name": teacher.name, "duties": duties}


@router.get("/{teacher_id}/week")
def get_teacher_week(
    teacher_id: int,
    week_start: str,
    db: Session = Depends(get_db),
) -> dict:
    """Get a teacher's duties for an entire week."""
    ws = date_type.fromisoformat(week_start)
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    if str(teacher.status) != "approved":
        raise HTTPException(403, "Teacher account not yet approved")

    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == ws).first()
    if not week:
        return {"teacher_id": teacher_id, "teacher_name": teacher.name, "duties": []}

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
                    entry["points_earned"] = confirmation.points_earned if confirmation else None
                    duties.append(entry)

    return {
        "teacher_id": teacher_id,
        "teacher_name": teacher.name,
        "week_status": week.status,
        "duties": duties,
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
        setattr(existing, "teacher_id", teacher_id)
        setattr(existing, "platform", data.platform)
    else:
        db.add(DeviceToken(teacher_id=teacher_id, token=data.token, platform=data.platform))
    db.commit()
    return {"status": "registered"}
