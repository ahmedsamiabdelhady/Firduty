"""Teacher CRUD, self-registration, approval, device token, and schedule endpoints.

v3.1 — timezone-safe mobile endpoints:
  - GET /{teacher_id}/today
      Server resolves "today" using Asia/Muscat timezone. The client does NOT
      send a date; the server computes it. This eliminates device-timezone
      mismatch as a source of wrong/empty results.

  - GET /{teacher_id}/current-week
      Server resolves the current Oman work-week start (Sunday) using
      Asia/Muscat timezone. Client no longer needs to compute the week start.

  Both new endpoints delegate to the same internal helper used by the
  existing /{id}/schedule?date=... and /{id}/week?week_start=... endpoints,
  so logic is not duplicated.

v3.0 — root-cause fixes preserved:
  - Eager loading (selectinload/joinedload) everywhere to prevent
    DetachedInstanceError silently producing empty duty lists.
  - Returns week_status so Flutter shows contextual empty-state messages.
  - Batch-loads confirmations in a single query.
  - Comprehensive logging on all schedule/week endpoints.
"""

import logging
from datetime import date as date_type, datetime
from typing import List, Optional

import pytz
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload, joinedload

from database import get_db
from models.models import (
    Teacher, DeviceToken, DayPlan, ShiftLocation, Assignment, WeekPlan,
)
from models.points_models import DutyConfirmation
from schemas.schemas import (
    TeacherCreate, TeacherLogin, TeacherRegister, TeacherUpdate,
    TeacherOut, TeacherStatusOut, DeviceTokenCreate,
)
from routers.auth import get_current_admin
from services.week_service import get_current_week_start

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/teachers", tags=["teachers"])

MUSCAT_TZ = pytz.timezone("Asia/Muscat")


# ─── Shared date helpers ──────────────────────────────────────────────────────

def _today_muscat() -> date_type:
    """Return today's date in Asia/Muscat timezone (Oman)."""
    return datetime.now(MUSCAT_TZ).date()


# ─── Duty serialisation helper ────────────────────────────────────────────────

def _duty_dict(a: Assignment, sl: ShiftLocation, query_date: date_type) -> dict:
    """
    Serialise a duty assignment — duty-type aware.
    ALL relationship attributes on sl (shift, location) must be eagerly loaded
    before calling this to avoid lazy-load DetachedInstanceError.
    """
    shift     = sl.shift
    duty_type = str(shift.duty_type) if shift.duty_type else "morning_endofday"

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


# ─── Shared schedule logic (used by both /schedule and /today) ────────────────

def _build_schedule_response(
    teacher_id: int,
    teacher: Teacher,
    query_date: date_type,
    db: Session,
) -> dict:
    """
    Core logic for returning a teacher's duties on a specific date.

    Eagerly loads all relationships to prevent DetachedInstanceError.
    Returns week_status so the Flutter client can show contextual messages.
    """
    # Load DayPlan(s) for this date with all nested relationships in ONE query.
    days = (
        db.query(DayPlan)
        .options(
            joinedload(DayPlan.week_plan),
            selectinload(DayPlan.shift_locations).joinedload(ShiftLocation.shift),
            selectinload(DayPlan.shift_locations).joinedload(ShiftLocation.location),
            selectinload(DayPlan.shift_locations).selectinload(ShiftLocation.assignments),
        )
        .filter(DayPlan.date == query_date)
        .all()
    )

    logger.info(
        "[schedule] teacher_id=%d  query_date=%s  day_plans_found=%d",
        teacher_id, query_date, len(days),
    )

    if not days:
        logger.info(
            "[schedule] teacher_id=%d  query_date=%s  → no DayPlan; "
            "possible weekend or no week plan created yet",
            teacher_id, query_date,
        )
        return {
            "teacher_id":   teacher_id,
            "teacher_name": teacher.name,
            "week_status":  None,  # no week covers this date
            "duties":       [],
        }

    # Phase 1 fix: gate visibility on day.is_published, not week_plan.status.
    # This makes Publish Day / Re-publish Day instantly visible to teachers
    # without requiring the entire week to be published first.
    # week_status is still read from week_plan.status for contextual messages
    # (so the Flutter "schedule being prepared" message still works).

    week_status: Optional[str] = None
    for day in days:
        ws = str(day.week_plan.status)
        logger.info(
            "[schedule] DayPlan id=%d  week_start=%s  week_status=%s  "
            "is_published=%s",
            day.id, day.week_plan.week_start_date, ws,
            getattr(day, "is_published", False),
        )
        if ws == "published":
            week_status = "published"
            break
        if week_status is None:
            week_status = ws

    # If the week is a pure draft and no day is published, return draft status
    # so Flutter shows "schedule being prepared".
    any_day_published = any(getattr(d, "is_published", False) for d in days)
    if not any_day_published and week_status != "published":
        logger.info(
            "[schedule] teacher_id=%d  week_status=%s  no days published → "
            "returning draft empty state",
            teacher_id, week_status,
        )
        return {
            "teacher_id":   teacher_id,
            "teacher_name": teacher.name,
            "week_status":  week_status,
            "duties":       [],
        }

    # If the week is published OR at least one day is published,
    # return duties for days that are individually published.
    effective_status = "published" if (week_status == "published" or any_day_published) else week_status

    # Collect assignments only for days that are marked is_published.
    assignment_ids: List[int] = []
    triples: List[tuple] = []  # (assignment, shift_location, day)

    for day in days:
        # Only show duties for days that have been explicitly published
        if not getattr(day, "is_published", False):
            logger.info(
                "[schedule] Skipping DayPlan id=%d  date=%s  "
                "(is_published=False)",
                day.id, day.date,
            )
            continue
        for sl in day.shift_locations:
            for a in sl.assignments:
                if int(a.teacher_id or 0) == teacher_id:
                    assignment_ids.append(a.id)
                    triples.append((a, sl, day))

    logger.info(
        "[schedule] teacher_id=%d  query_date=%s  assignments_found=%d",
        teacher_id, query_date, len(assignment_ids),
    )

    # Batch-load confirmations (1 query instead of N).
    conf_map: dict = {}
    if assignment_ids:
        conf_map = {
            c.assignment_id: c
            for c in db.query(DutyConfirmation).filter(
                DutyConfirmation.teacher_id == teacher_id,
                DutyConfirmation.assignment_id.in_(assignment_ids),
            ).all()
        }

    duties = []
    for a, sl, day in triples:
        conf  = conf_map.get(a.id)
        entry = _duty_dict(a, sl, query_date)
        entry["already_confirmed"] = conf is not None
        entry["points_earned"]     = conf.points_earned if conf else None
        duties.append(entry)

    logger.info(
        "[schedule] teacher_id=%d  query_date=%s  returning %d duties  "
        "week_status=published",
        teacher_id, query_date, len(duties),
    )

    return {
        "teacher_id":   teacher_id,
        "teacher_name": teacher.name,
        "week_status":  effective_status,
        "duties":       duties,
    }


def _build_week_response(
    teacher_id: int,
    teacher: Teacher,
    ws: date_type,
    db: Session,
) -> dict:
    """
    Core logic for returning a teacher's duties for an entire week.
    Eagerly loads all relationships; returns week_status.
    """
    week = db.query(WeekPlan).filter(WeekPlan.week_start_date == ws).first()

    if not week:
        logger.info("[week] teacher_id=%d  week_start=%s  → no WeekPlan", teacher_id, ws)
        return {
            "teacher_id":   teacher_id,
            "teacher_name": teacher.name,
            "week_status":  None,
            "duties":       [],
        }

    week_status = str(week.status)
    logger.info("[week] teacher_id=%d  week_start=%s  status=%s", teacher_id, ws, week_status)

    if week_status != "published":
        return {
            "teacher_id":   teacher_id,
            "teacher_name": teacher.name,
            "week_status":  week_status,
            "duties":       [],
        }

    # Eagerly reload with all relations.
    week = (
        db.query(WeekPlan)
        .options(
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations).joinedload(ShiftLocation.shift),
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations).joinedload(ShiftLocation.location),
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations).selectinload(ShiftLocation.assignments),
        )
        .filter(WeekPlan.week_start_date == ws)
        .first()
    )
    if not week:
        return {"teacher_id": teacher_id, "teacher_name": teacher.name,
                "week_status": None, "duties": []}

    assignment_ids: List[int] = []
    triples: List[tuple] = []

    for day in week.day_plans:
        # Phase 1 fix: only include days that have been explicitly published.
        # This ensures Publish Day / Re-publish Day shows only the intended days.
        if not getattr(day, "is_published", False):
            logger.info(
                "[week] Skipping DayPlan id=%d  date=%s  (is_published=False)",
                day.id, day.date,
            )
            continue
        for sl in day.shift_locations:
            for a in sl.assignments:
                if int(a.teacher_id or 0) == teacher_id:
                    assignment_ids.append(a.id)
                    triples.append((a, sl, day))

    conf_map: dict = {}
    if assignment_ids:
        conf_map = {
            c.assignment_id: c
            for c in db.query(DutyConfirmation).filter(
                DutyConfirmation.teacher_id == teacher_id,
                DutyConfirmation.assignment_id.in_(assignment_ids),
            ).all()
        }

    duties = []
    for a, sl, day in triples:
        conf  = conf_map.get(a.id)
        entry = _duty_dict(a, sl, day.date)
        entry["already_confirmed"] = conf is not None
        entry["points_earned"]     = conf.points_earned if conf else None
        duties.append(entry)

    logger.info("[week] teacher_id=%d  week=%s  %d duties (published days only)",
                teacher_id, ws, len(duties))

    # Use "published" even if only some days are published — Flutter shows
    # duties for the specific days that are available.
    return {
        "teacher_id":   teacher_id,
        "teacher_name": teacher.name,
        "week_status":  "published",
        "duties":       duties,
    }


def _validate_teacher(teacher_id: int, db: Session) -> Teacher:
    """Fetch and validate teacher; raises HTTP 404 / 403 as appropriate."""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    if str(teacher.status) != "approved":
        raise HTTPException(403, "Teacher account not yet approved")
    return teacher


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
    return (
        db.query(Teacher)
        .filter(Teacher.status == "pending")
        .order_by(Teacher.created_at.desc())
        .all()
    )


@router.post("/register", response_model=TeacherOut, status_code=201)
def register_teacher(data: TeacherRegister, db: Session = Depends(get_db)):
    """Self-registration — creates a pending teacher record."""
    if data.email:
        existing = (
            db.query(Teacher).filter(Teacher.email == data.email.lower()).first()
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


@router.post("/login", response_model=TeacherOut, status_code=200)
def login_teacher(data: TeacherLogin, db: Session = Depends(get_db)):
    """
    Teacher login — name + email only (no password, no OTP).

    Matches the teacher record by email (case-insensitive).
    Also verifies the supplied name loosely (case-insensitive, stripped)
    to prevent one teacher from accidentally accessing another's account.

    Returns the teacher record so the Flutter app can store teacher_id.
    Returns 404 if no record matches.
    Returns 403 if the account is still pending approval.
    Returns 409 if the name doesn't match the registered name for that email.
    """
    email_lower = data.email.lower().strip()
    name_stripped = data.name.strip().lower()

    teacher = db.query(Teacher).filter(Teacher.email == email_lower).first()
    if not teacher:
        raise HTTPException(
            404,
            "No account found with this email. "
            "Please register first or check your email address.",
        )
    # Soft name check — prevents using another teacher's email accidentally
    if teacher.name.strip().lower() != name_stripped:
        raise HTTPException(
            409,
            "The name you entered does not match the registered name for this email. "
            "Please check and try again.",
        )
    if str(teacher.status) == "pending":
        raise HTTPException(
            403,
            "Your account is pending admin approval. "
            "Please check back later.",
        )
    if not bool(teacher.active):
        raise HTTPException(
            403,
            "Your account has been deactivated. Contact the admin.",
        )
    logger.info("Teacher login: id=%d  email=%s", teacher.id, email_lower)
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


# ── TIMEZONE-SAFE MOBILE ENDPOINTS (preferred for Flutter app) ──────────────

@router.get("/{teacher_id}/today")
def get_teacher_today(
    teacher_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """
    Teacher's duties for TODAY in Oman (Asia/Muscat) timezone.

    ── Why this endpoint exists ───────────────────────────────────────────────
    The existing  GET /{id}/schedule?date=...  requires the client to send
    today's date as a query parameter. This works only if the device timezone
    matches Oman (Asia/Muscat, UTC+4). If the device is in a different
    timezone, or set to UTC (common on development machines and some Android
    builds), the wrong date is sent, and the backend finds no DayPlan for that
    date — producing an empty result even when published duties exist.

    This endpoint solves the problem at the source: the server computes
    today's date in Asia/Muscat, so the result is always correct regardless of
    what timezone the client device is set to.

    Response shape (same as /schedule):
        {
          "teacher_id":   int,
          "teacher_name": str,
          "week_status":  "published" | "draft" | null,
          "duties":       [...]
        }
    """
    today = _today_muscat()

    logger.info(
        "[today] teacher_id=%d  server_muscat_date=%s  tz=Asia/Muscat",
        teacher_id, today,
    )

    teacher = _validate_teacher(teacher_id, db)
    return _build_schedule_response(teacher_id, teacher, today, db)


@router.get("/{teacher_id}/current-week")
def get_teacher_current_week(
    teacher_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """
    Teacher's duties for the current Oman school week (Sunday–Thursday).

    ── Why this endpoint exists ───────────────────────────────────────────────
    The existing  GET /{id}/week?week_start=...  requires the client to compute
    the current week's Sunday start date. If the device timezone is wrong, this
    calculation can be off by one week (e.g., sending the previous week's
    Sunday when Oman is already in the next week).

    This endpoint lets the server compute the correct Sunday start in
    Asia/Muscat timezone, guaranteeing accuracy.

    Response shape (same as /week):
        {
          "teacher_id":   int,
          "teacher_name": str,
          "week_status":  "published" | "draft" | null,
          "duties":       [...]
        }
    """
    ws = get_current_week_start()  # uses Asia/Muscat internally

    logger.info(
        "[current-week] teacher_id=%d  server_week_start=%s  tz=Asia/Muscat",
        teacher_id, ws,
    )

    teacher = _validate_teacher(teacher_id, db)
    return _build_week_response(teacher_id, teacher, ws, db)


# ── LEGACY ENDPOINTS (kept for backward compatibility) ───────────────────────

@router.get("/{teacher_id}/schedule")
def get_teacher_schedule(
    teacher_id: int,
    date: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Teacher's duties for a specific date (client supplies date).

    Prefer GET /{id}/today when calling from the Flutter mobile app to avoid
    timezone mismatch. Use this endpoint only when the client has a reliable
    local date (e.g., the admin web UI or manual testing).

    Returns week_status: "published" | "draft" | null
    """
    try:
        query_date = date_type.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, f"Invalid date format: '{date}'. Use YYYY-MM-DD.")

    logger.info(
        "[schedule] teacher_id=%d  client_date=%s  "
        "[NOTE: use /today for timezone-safe resolution]",
        teacher_id, query_date,
    )

    teacher = _validate_teacher(teacher_id, db)
    return _build_schedule_response(teacher_id, teacher, query_date, db)


@router.get("/{teacher_id}/week")
def get_teacher_week(
    teacher_id: int,
    week_start: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Teacher's duties for a specific week (client supplies week start date).

    Prefer GET /{id}/current-week when calling from the Flutter mobile app.
    """
    try:
        ws = date_type.fromisoformat(week_start)
    except ValueError:
        raise HTTPException(400, f"Invalid week_start: '{week_start}'. Use YYYY-MM-DD.")

    logger.info(
        "[week] teacher_id=%d  client_week_start=%s  "
        "[NOTE: use /current-week for timezone-safe resolution]",
        teacher_id, ws,
    )

    teacher = _validate_teacher(teacher_id, db)
    return _build_week_response(teacher_id, teacher, ws, db)


# ─── Device token ─────────────────────────────────────────────────────────────

@router.post("/{teacher_id}/device-token")
def register_device_token(
    teacher_id: int,
    data: DeviceTokenCreate,
    db: Session = Depends(get_db),
) -> dict:
    """
    Register or update a push notification token.

    Upsert strategy that prevents duplicate-notification accumulation:

    Path 1 — installation_id provided (new clients v3.3+):
      UPSERT on (teacher_id, installation_id).
      When FCM rotates the token for the same device, the existing row is
      UPDATED in place — no new row, no future duplicate notification.

    Path 2 — no installation_id (legacy clients, backward compat):
      UPSERT on token value only — same as previous behavior.
    """
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(404, "Teacher not found")

    now = datetime.utcnow()

    # ── Path 1: installation_id present — deterministic per-device upsert ─────
    #
    # Identity key is (teacher_id, installation_id) — NOT the token value.
    # FCM token may rotate; installation_id is stable for the life of the install.
    #
    # Sub-cases:
    #   a) Row with (teacher_id, installation_id) EXISTS
    #      → token rotated for the same device → UPDATE token in place
    #   b) Row with (teacher_id, installation_id) does NOT exist — new device
    #      b1) This teacher already owns a row with this exact token (impossible
    #          normally, but guards against extremely rare FCM duplicate-token edge)
    #          → remove the stale row, INSERT fresh row with new installation_id
    #      b2) A DIFFERENT teacher owns this token (shared physical device,
    #          one teacher logged out, another logged in)
    #          → DO NOT overwrite another teacher's row. The old teacher's row
    #          will become stale and be cleaned up by FCM error handling on the
    #          next send (remove_invalid_tokens). INSERT a new row for this teacher.
    #      b3) Token is completely new → INSERT new row
    if data.installation_id:
        row = (
            db.query(DeviceToken)
            .filter(
                DeviceToken.teacher_id      == teacher_id,
                DeviceToken.installation_id == data.installation_id,
            )
            .first()
        )
        if row:
            # Case a: Same teacher, same device, token rotated — UPDATE in place.
            # This is the hot path for every FCM token rotation.
            # Zero new rows created — one device stays one row.
            row.token      = data.token
            row.platform   = data.platform
            row.updated_at = now
            logger.info(
                "[token] Updated (token rotation): teacher=%d install=%s",
                teacher_id, data.installation_id[:8],
            )
        else:
            # Case b: New device for this teacher.
            # Check if THIS teacher already has a different row with the same token.
            # (Happens if the same teacher re-installs the app: old installation_id
            # is gone, but the FCM token may still be the same for a brief window.)
            same_teacher_old_row = (
                db.query(DeviceToken)
                .filter(
                    DeviceToken.teacher_id == teacher_id,
                    DeviceToken.token      == data.token,
                )
                .first()
            )
            if same_teacher_old_row:
                # Stale row from a previous install of the same teacher on this
                # device. Remove it and let the INSERT below create a clean row.
                db.delete(same_teacher_old_row)
                db.flush()
                logger.info(
                    "[token] Removed stale row (re-install): teacher=%d old_install=%s",
                    teacher_id,
                    (same_teacher_old_row.installation_id or "null")[:8],
                )

            # Case b2 is handled by NOT touching any other teacher's row.
            # If a different teacher owns this token, their row is left intact.
            # It will be cleaned by FCM's "token not registered" response on the
            # next notification send (remove_invalid_tokens). This is the safe
            # approach — we never corrupt another teacher's notification delivery.

            db.add(DeviceToken(
                teacher_id=teacher_id,
                token=data.token,
                platform=data.platform,
                installation_id=data.installation_id,
                updated_at=now,
            ))
            logger.info(
                "[token] Registered new device: teacher=%d install=%s platform=%s",
                teacher_id, data.installation_id[:8], data.platform,
            )

    # ── Path 2: no installation_id — legacy upsert by token ──────────────────
    else:
        row = db.query(DeviceToken).filter(DeviceToken.token == data.token).first()
        if row:
            row.teacher_id = teacher_id
            row.platform   = data.platform
            row.updated_at = now
        else:
            db.add(DeviceToken(
                teacher_id=teacher_id,
                token=data.token,
                platform=data.platform,
                updated_at=now,
            ))

    db.commit()
    return {"status": "registered"}


# ─── CRUD ─────────────────────────────────────────────────────────────────────

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
