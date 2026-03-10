"""Teacher CRUD, self-registration, approval, device token, and schedule endpoints."""

from datetime import date as date_type
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

router = APIRouter(prefix="/teachers", tags=["teachers"])


def _duty_dict(a: Assignment, sl: ShiftLocation, query_date: date_type) -> dict:
    """Serialize a duty assignment — duty-type aware."""
    duty_type = sl.shift.duty_type
    base = {
        "assignment_id":  a.id,
        "date":           str(query_date),
        "shift_name_en":  sl.shift.name_en,
        "shift_name_ar":  sl.shift.name_ar,
        "shift_start":    str(sl.shift.start_time),
        "shift_end":      str(sl.shift.end_time),
        "duty_type":      duty_type,
    }
    if duty_type == "morning_endofday" and sl.location:
        base["location_name_en"] = sl.location.name_en
        base["location_name_ar"] = sl.location.name_ar
    else:
        base["location_name_en"] = None
        base["location_name_ar"] = None
    base["grade_class"] = a.grade_class
    return base


# ─── Static-path routes first (must come before /{teacher_id}/...) ────────────

@router.get("/", response_model=list[TeacherOut])
def list_teachers(db: Session = Depends(get_db)):
    """List all approved + active teachers (public — used by admin planner to assign teachers)."""
    return (
        db.query(Teacher)
        .filter(Teacher.active.is_(True), Teacher.status == "approved")
        .order_by(Teacher.name)
        .all()
    )


@router.get("/all", response_model=list[TeacherOut])
def list_all_teachers(db: Session = Depends(get_db), _=Depends(get_current_admin)):
    """List all teachers regardless of status or active flag (admin only)."""
    return db.query(Teacher).order_by(Teacher.name).all()


@router.get("/pending", response_model=list[TeacherOut])
def list_pending_teachers(db: Session = Depends(get_db), _=Depends(get_current_admin)):
    """List teachers awaiting approval (admin only)."""
    return (
        db.query(Teacher)
        .filter(Teacher.status == "pending")
        .order_by(Teacher.created_at)
        .all()
    )


@router.post("/", response_model=TeacherOut)
def create_teacher(
    data: TeacherCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """Admin-only: create a teacher record directly (bypasses approval flow)."""
    if data.email:
        existing = db.query(Teacher).filter(Teacher.email == data.email).first()
        if existing:
            raise HTTPException(409, "Email already registered")
    teacher = Teacher(**data.model_dump())
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.post("/register", response_model=TeacherStatusOut)
def register_teacher(data: TeacherRegister, db: Session = Depends(get_db)):
    """
    Public self-registration endpoint.
    Creates a teacher with status='pending'. Admin must approve before
    the teacher can access the duty system.
    Returns HTTP 409 if the email is already registered.
    """
    # Normalise email to lowercase for consistent uniqueness check
    email_lower = data.email.lower().strip()
    existing = db.query(Teacher).filter(Teacher.email == email_lower).first()
    if existing:
        raise HTTPException(409, "Email already registered")
    teacher = Teacher(
        name=data.name.strip(),
        email=email_lower,
        status="pending",
        active=True,
        preferred_language="ar",
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.post("/approve-all")
def approve_all_pending(
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """Approve every pending teacher in one operation (admin only)."""
    pending = db.query(Teacher).filter(Teacher.status == "pending").all()
    count = len(pending)
    for t in pending:
        setattr(t, "status", "approved")
    db.commit()
    return {"approved_count": count}


# ─── Parameterised routes /{teacher_id}/... ───────────────────────────────────

@router.put("/{teacher_id}", response_model=TeacherOut)
def update_teacher(
    teacher_id: int,
    data: TeacherUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(teacher, field, value)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.delete("/{teacher_id}")
def delete_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    setattr(teacher, "active", False)
    db.commit()
    return {"status": "deactivated"}


@router.get("/{teacher_id}/status", response_model=TeacherStatusOut)
def get_teacher_status(teacher_id: int, db: Session = Depends(get_db)):
    """
    Public endpoint used by the Flutter app on every launch to check
    whether the teacher has been approved.
    Returns 404 if the teacher record no longer exists (cleared local storage on client).
    """
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    return teacher


@router.post("/{teacher_id}/approve", response_model=TeacherOut)
def approve_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
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
):
    """
    Get a teacher's duties for a specific date.
    Returns duty_type, location (for morning/end-of-day), grade_class (for break),
    plus assignment_id and already_confirmed status.
    Only approved teachers can have duties.
    """
    query_date = date_type.fromisoformat(date)
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    if teacher.status != "approved":
        raise HTTPException(403, "Teacher account not yet approved")

    duties = []
    for day in db.query(DayPlan).filter(DayPlan.date == query_date).all():
        if day.week_plan.status != "published":
            continue
        for sl in day.shift_locations:
            for a in sl.assignments:
                if a.teacher_id == teacher_id:
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
):
    """Get a teacher's duties for an entire week."""
    ws = date_type.fromisoformat(week_start)
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    if teacher.status != "approved":
        raise HTTPException(403, "Teacher account not yet approved")

    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == ws).first()
    if not week:
        return {"teacher_id": teacher_id, "teacher_name": teacher.name, "duties": []}

    duties = []
    for day in week.day_plans:
        for sl in day.shift_locations:
            for a in sl.assignments:
                if a.teacher_id == teacher_id:
                    confirmation = db.query(DutyConfirmation).filter(
                        DutyConfirmation.teacher_id == teacher_id,
                        DutyConfirmation.assignment_id == a.id,
                    ).first()
                    entry = _duty_dict(a, sl, day.date)
                    entry["already_confirmed"] = confirmation is not None
                    entry["points_earned"] = confirmation.points_earned if confirmation else None
                    duties.append(entry)

    return {
        "teacher_id":   teacher_id,
        "teacher_name": teacher.name,
        "week_status":  week.status,
        "duties":       duties,
    }


@router.post("/{teacher_id}/device-token")
def register_device_token(
    teacher_id: int,
    data: DeviceTokenCreate,
    db: Session = Depends(get_db),
):
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