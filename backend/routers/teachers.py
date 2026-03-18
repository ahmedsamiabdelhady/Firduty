"""Teacher CRUD, self-registration, approval, device token, and schedule endpoints.

v2.5 → v3.0  root-cause fixes:
  - get_teacher_schedule: replaced all lazy-loading with selectinload/joinedload
    so no DetachedInstanceError can silently drop records.
  - get_teacher_schedule: added comprehensive logging (teacher, date, week found,
    week status, days found, assignment count) so "empty today" is diagnosable
    from server logs.
  - get_teacher_schedule: now returns `week_status` ("published"|"draft"|null)
    so Flutter can show a different message when the week is draft vs truly empty.
  - get_teacher_week: also uses eager loading and returns `week_status`.
  - Both endpoints only return duties from *published* weeks (correct behaviour
    — teachers must not see unconfirmed draft rosters).
"""

import logging
from datetime import date as date_type
from typing import List, Optional

import pytz
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload, joinedload

from database import get_db
from models.models import (
    Teacher, DeviceToken, DayPlan, ShiftLocation, Assignment, WeekPlan, Location, Shift,
)
from models.points_models import DutyConfirmation
from schemas.schemas import (
    TeacherCreate, TeacherRegister, TeacherUpdate,
    TeacherOut, TeacherStatusOut, DeviceTokenCreate,
)
from routers.auth import get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/teachers", tags=["teachers"])

MUSCAT_TZ = pytz.timezone("Asia/Muscat")


# ─── Duty serialisation helper ────────────────────────────────────────────────

def _duty_dict(a: Assignment, sl: ShiftLocation, query_date: date_type) -> dict:
    """
    Serialise a duty assignment — duty-type aware.
    All relationship attributes (sl.shift, sl.location) must be eagerly loaded
    BEFORE calling this function to avoid lazy-load DetachedInstanceError.
    """
    shift = sl.shift
    duty_type: str = str(shift.duty_type) if shift.duty_type else "morning_endofday"

    base: dict = {
        "assignment_id": a.id,
        "date":          str(query_date),
        "shift_name_en": shift.name_en or "",
        "shift_name_ar": shift.name_ar or "",
        "shift_start":   str(shift.start_time),
        "shift_end":     str(shift.end_time),
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
    rows = db.query(Teacher).order_by(Teacher.name).all()
    logger.debug("list_all_teachers → %d rows", len(rows))
    return rows


@router.get("/pending", response_model=List[TeacherOut])
def list_pending_teachers(
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> List[TeacherOut]:
    rows = (
        db.query(Teacher)
        .filter(Teacher.status == "pending")
        .order_by(Teacher.created_at.desc())
        .all()
    )
    return rows


@router.post("/register", response_model=TeacherOut, status_code=201)
def register_teacher(
    data: TeacherRegister,
    db: Session = Depends(get_db),
):
    """Self-registration — creates a pending teacher record."""
    if data.email:
        existing = (
            db.query(Teacher)
            .filter(Teacher.email == data.email.lower())
            .first()
        )
        if existing:
            raise HTTPException(409, "A teacher with this email is already registered.")

    teacher = Teacher(
        name=data.name,
        email=data.email.lower() if data.email else None,
        status="pending",
        active=True,
        preferred_language="ar",
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    logger.info("Teacher registered: id=%d, name=%s", teacher.id, teacher.name)
    return teacher


@router.post("/approve-all")
def approve_all_pending(
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    pending = db.query(Teacher).filter(Teacher.status == "pending").all()
    count = len(pending)
    for t in pending:
        t.status = "approved"
    db.commit()
    logger.info("approve_all_pending → approved %d teachers", count)
    return {"approved_count": count}


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

    Returns:
        week_status: "published" | "draft" | null
            - null: no week plan covering this date was found
            - "draft": a week exists but has not been published yet
            - "published": week is published (duties list may still be empty
              if this teacher has no assignments for this day)

    Flutter uses `week_status` to show contextual empty-state messages:
        draft   → "Your schedule is being prepared. Please check back later."
        null    → "No weekly plan has been set up for this date."
        published + empty duties → "You have no duties scheduled for today."
    """
    # ── Parse + validate date ────────────────────────────────────────────────
    try:
        query_date = date_type.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, f"Invalid date format: '{date}'. Use YYYY-MM-DD.")

    # ── Log the incoming request ─────────────────────────────────────────────
    logger.info(
        "[schedule] teacher_id=%s  requested_date=%s",
        teacher_id, query_date,
    )

    # ── Validate teacher ─────────────────────────────────────────────────────
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    if str(teacher.status) != "approved":
        raise HTTPException(403, "Teacher account not yet approved")

    # ── Load DayPlan(s) for this date with ALL needed relationships eagerly ──
    #
    # ROOT CAUSE FIX:
    # The original code accessed day.week_plan, day.shift_locations,
    # sl.assignments, sl.shift, sl.location all via lazy-loading after the
    # initial query. With certain SQLAlchemy + PostgreSQL configurations
    # (especially on Koyeb), this caused DetachedInstanceError or stale data
    # silently producing an empty duties list even for a published week.
    #
    # Solution: load EVERYTHING in one query using selectinload/joinedload.
    days = (
        db.query(DayPlan)
        .options(
            # Eagerly load the parent WeekPlan to read .status without lazy-load
            joinedload(DayPlan.week_plan),
            # Eagerly load shift_locations + shift + location in one go
            selectinload(DayPlan.shift_locations)
            .joinedload(ShiftLocation.shift),
            selectinload(DayPlan.shift_locations)
            .joinedload(ShiftLocation.location),
            # Eagerly load assignments (no teacher join needed — we filter by id)
            selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.assignments),
        )
        .filter(DayPlan.date == query_date)
        .all()
    )

    logger.info(
        "[schedule] date=%s  found %d day_plan(s) in DB",
        query_date, len(days),
    )

    if not days:
        logger.info("[schedule] No DayPlan for date=%s → no week plan covers this date", query_date)
        return {
            "teacher_id":   teacher_id,
            "teacher_name": teacher.name,
            "week_status":  None,   # no week plan at all for this date
            "duties":       [],
        }

    # ── Determine week status (there should be at most one DayPlan per date) ──
    # If for some reason there are multiple (data inconsistency), prefer published.
    week_status: Optional[str] = None
    for day in days:
        ws = str(day.week_plan.status)
        logger.info(
            "[schedule] DayPlan id=%d  week_start=%s  week_status=%s",
            day.id, day.week_plan.week_start_date, ws,
        )
        if ws == "published":
            week_status = "published"
            break
        if week_status is None:
            week_status = ws  # capture first status if none is published

    if week_status != "published":
        logger.info(
            "[schedule] week_status=%s (not published) → returning empty duties list "
            "with week_status=%s so Flutter can show 'schedule being prepared' message",
            week_status, week_status,
        )
        return {
            "teacher_id":   teacher_id,
            "teacher_name": teacher.name,
            "week_status":  week_status,  # Flutter will show "coming soon" message
            "duties":       [],
        }

    # ── Collect duties for this teacher from the published day ───────────────
    # Load confirmations in a single batch query (avoids N+1)
    assignment_ids_for_teacher: List[int] = []
    teacher_assignments: List[tuple] = []  # (assignment, shift_location, day)

    for day in days:
        if str(day.week_plan.status) != "published":
            continue
        for sl in day.shift_locations:
            for a in sl.assignments:
                if int(a.teacher_id or 0) == teacher_id:
                    assignment_ids_for_teacher.append(a.id)
                    teacher_assignments.append((a, sl, day))

    logger.info(
        "[schedule] teacher_id=%d  date=%s  found %d assignment(s) in published week",
        teacher_id, query_date, len(assignment_ids_for_teacher),
    )

    # Batch-load all confirmations for these assignments (1 query instead of N)
    if assignment_ids_for_teacher:
        confirmations_map = {
            c.assignment_id: c
            for c in db.query(DutyConfirmation).filter(
                DutyConfirmation.teacher_id == teacher_id,
                DutyConfirmation.assignment_id.in_(assignment_ids_for_teacher),
            ).all()
        }
    else:
        confirmations_map = {}

    # ── Build duty dicts ─────────────────────────────────────────────────────
    duties = []
    for a, sl, day in teacher_assignments:
        conf = confirmations_map.get(a.id)
        entry = _duty_dict(a, sl, query_date)
        entry["already_confirmed"] = conf is not None
        entry["points_earned"]     = conf.points_earned if conf else None
        duties.append(entry)

    logger.info(
        "[schedule] teacher_id=%d  date=%s  returning %d duty/duties  week_status=published",
        teacher_id, query_date, len(duties),
    )

    return {
        "teacher_id":   teacher_id,
        "teacher_name": teacher.name,
        "week_status":  "published",
        "duties":       duties,
    }


@router.get("/{teacher_id}/week")
def get_teacher_week(
    teacher_id: int,
    week_start: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Teacher's duties for an entire week.
    Only returns duties from a *published* week plan.
    Returns `week_status` so Flutter can show contextual messages.
    """
    try:
        ws = date_type.fromisoformat(week_start)
    except ValueError:
        raise HTTPException(400, f"Invalid week_start format: '{week_start}'. Use YYYY-MM-DD.")

    logger.info("[week] teacher_id=%s  week_start=%s", teacher_id, ws)

    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    if str(teacher.status) != "approved":
        raise HTTPException(403, "Teacher account not yet approved")

    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == ws).first()

    if not week:
        logger.info("[week] No WeekPlan for week_start=%s", ws)
        return {
            "teacher_id":   teacher_id,
            "teacher_name": teacher.name,
            "week_status":  None,
            "duties":       [],
        }

    week_status = str(week.status)
    logger.info("[week] week_start=%s  status=%s", ws, week_status)

    if week_status != "published":
        return {
            "teacher_id":   teacher_id,
            "teacher_name": teacher.name,
            "week_status":  week_status,
            "duties":       [],
        }

    # Eagerly load everything needed for serialisation
    week = (
        db.query(WeekPlan)
        .options(
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations)
            .joinedload(ShiftLocation.shift),
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations)
            .joinedload(ShiftLocation.location),
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.assignments),
        )
        .filter(WeekPlan.week_start_date == ws)
        .first()
    )
    if not week:
        return {"teacher_id": teacher_id, "teacher_name": teacher.name,
                "week_status": None, "duties": []}

    # Collect all assignment IDs for this teacher
    all_assignment_ids: List[int] = []
    teacher_triples: List[tuple] = []  # (assignment, sl, day)

    for day in week.day_plans:
        for sl in day.shift_locations:
            for a in sl.assignments:
                if int(a.teacher_id or 0) == teacher_id:
                    all_assignment_ids.append(a.id)
                    teacher_triples.append((a, sl, day))

    # Batch-load confirmations
    conf_map = {}
    if all_assignment_ids:
        conf_map = {
            c.assignment_id: c
            for c in db.query(DutyConfirmation).filter(
                DutyConfirmation.teacher_id == teacher_id,
                DutyConfirmation.assignment_id.in_(all_assignment_ids),
            ).all()
        }

    duties = []
    for a, sl, day in teacher_triples:
        conf = conf_map.get(a.id)
        entry = _duty_dict(a, sl, day.date)
        entry["already_confirmed"] = conf is not None
        entry["points_earned"]     = conf.points_earned if conf else None
        duties.append(entry)

    logger.info("[week] teacher_id=%d  week=%s  %d duties", teacher_id, ws, len(duties))

    return {
        "teacher_id":   teacher_id,
        "teacher_name": teacher.name,
        "week_status":  "published",
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

    payload = (
        data.model_dump(exclude_unset=True)
        if hasattr(data, "model_dump")
        else data.dict(exclude_unset=True)
    )
    for field, value in payload.items():
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
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    teacher.active = False
    db.commit()
