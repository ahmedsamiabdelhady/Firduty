"""Teacher CRUD, device token, and schedule endpoints."""

from typing import List
from datetime import date as date_type
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.models import Teacher, DeviceToken, DayPlan, ShiftLocation, Assignment, WeekPlan
from models.points_models import DutyConfirmation
from schemas.schemas import TeacherCreate, TeacherUpdate, TeacherOut, DeviceTokenCreate
from routers.auth import get_current_admin

router = APIRouter(prefix="/teachers", tags=["teachers"])


@router.get("/", response_model=List[TeacherOut])
def list_teachers(db: Session = Depends(get_db)):
    """List all active teachers (public — used by Flutter for teacher selection)."""
    return db.query(Teacher).filter(Teacher.active == True).order_by(Teacher.name).all()


@router.get("/all", response_model=List[TeacherOut])
def list_all_teachers(db: Session = Depends(get_db), _=Depends(get_current_admin)):
    """List all teachers including inactive (admin only)."""
    return db.query(Teacher).order_by(Teacher.name).all()


@router.post("/", response_model=TeacherOut)
def create_teacher(data: TeacherCreate, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    teacher = Teacher(**data.model_dump())
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.put("/{teacher_id}", response_model=TeacherOut)
def update_teacher(teacher_id: int, data: TeacherUpdate,
                    db: Session = Depends(get_db), _=Depends(get_current_admin)):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(teacher, field, value)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.delete("/{teacher_id}")
def delete_teacher(teacher_id: int, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    teacher.active = False
    db.commit()
    return {"status": "deactivated"}


@router.get("/{teacher_id}/schedule")
def get_teacher_schedule(teacher_id: int, date: str, db: Session = Depends(get_db)):
    """
    Get a teacher's duties for a specific date.
    Includes assignment_id (for confirmation) and already_confirmed status.
    """
    query_date = date_type.fromisoformat(date)
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")

    duties = []
    day_plans = db.query(DayPlan).filter(DayPlan.date == query_date).all()

    for day in day_plans:
        week = day.week_plan
        if week.status != "published":
            continue
        for sl in day.shift_locations:
            for a in sl.assignments:
                if a.teacher_id == teacher_id:
                    # Check if already confirmed
                    confirmation = db.query(DutyConfirmation).filter(
                        DutyConfirmation.teacher_id == teacher_id,
                        DutyConfirmation.assignment_id == a.id,
                    ).first()

                    duties.append({
                        "assignment_id":     a.id,
                        "date":              str(query_date),
                        "shift_name_en":     sl.shift.name_en,
                        "shift_name_ar":     sl.shift.name_ar,
                        "shift_start":       str(sl.shift.start_time),
                        "shift_end":         str(sl.shift.end_time),
                        "location_name_en":  sl.location.name_en,
                        "location_name_ar":  sl.location.name_ar,
                        "already_confirmed": confirmation is not None,
                        "points_earned":     confirmation.points_earned if confirmation else None,
                    })

    return {"teacher_id": teacher_id, "teacher_name": teacher.name, "duties": duties}


@router.get("/{teacher_id}/week")
def get_teacher_week(teacher_id: int, week_start: str, db: Session = Depends(get_db)):
    """Get a teacher's duties for an entire week."""
    ws = date_type.fromisoformat(week_start)
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")

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

                    duties.append({
                        "assignment_id":     a.id,
                        "date":              str(day.date),
                        "shift_name_en":     sl.shift.name_en,
                        "shift_name_ar":     sl.shift.name_ar,
                        "shift_start":       str(sl.shift.start_time),
                        "shift_end":         str(sl.shift.end_time),
                        "location_name_en":  sl.location.name_en,
                        "location_name_ar":  sl.location.name_ar,
                        "already_confirmed": confirmation is not None,
                        "points_earned":     confirmation.points_earned if confirmation else None,
                    })

    return {
        "teacher_id":   teacher_id,
        "teacher_name": teacher.name,
        "week_status":  week.status,
        "duties":       duties,
    }


@router.post("/{teacher_id}/device-token")
def register_device_token(teacher_id: int, data: DeviceTokenCreate, db: Session = Depends(get_db)):
    """Register or update a teacher's FCM device token."""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    existing = db.query(DeviceToken).filter(DeviceToken.token == data.token).first()
    if existing:
        existing.teacher_id = teacher_id
        existing.platform = data.platform
    else:
        db.add(DeviceToken(teacher_id=teacher_id, token=data.token, platform=data.platform))
    db.commit()
    return {"status": "registered"}