"""
points_service.py — Core business logic for duty confirmation and point scoring.

Scoring rules (all times compared in Asia/Muscat timezone):
  - confirmed_at <= shift start_time          → 2 points
  - shift start <= confirmed_at <= start + 5m → 1 point
  - confirmed_at > start_time + 5 minutes     → 0 points

Monthly summaries are rebuilt on demand or by cron on the 1st of each month.
"""

import logging
from datetime import datetime, timedelta, date
from typing import Optional

import pytz
from sqlalchemy import func, extract
from sqlalchemy.orm import Session

from models.models import Assignment, Teacher, ShiftLocation, Shift, DayPlan, WeekPlan
from models.points_models import DutyConfirmation, MonthlyPointsSummary

logger = logging.getLogger(__name__)

MUSCAT_TZ = pytz.timezone("Asia/Muscat")
LATE_WINDOW_MINUTES = 5   # 1 point window
ON_TIME_POINTS = 2
LATE_POINTS = 1
MISS_POINTS = 0


# ─── Scoring ──────────────────────────────────────────────────────────────────

def calculate_points(shift_start_time, duty_date: date, confirmed_at_utc: datetime) -> int:
    """
    Calculate points earned based on confirmation time vs shift start.

    Args:
        shift_start_time: datetime.time object (the shift's start_time, naive, school local time)
        duty_date:         the date of the duty
        confirmed_at_utc:  when the teacher confirmed, in UTC (naive or aware)

    Returns:
        int: 2, 1, or 0
    """
    # Build shift start as a timezone-aware datetime in Asia/Muscat
    start_naive = datetime.combine(duty_date, shift_start_time)
    start_muscat = MUSCAT_TZ.localize(start_naive)

    # Normalize confirmed_at to Muscat timezone
    if confirmed_at_utc.tzinfo is None:
        confirmed_muscat = pytz.utc.localize(confirmed_at_utc).astimezone(MUSCAT_TZ)
    else:
        confirmed_muscat = confirmed_at_utc.astimezone(MUSCAT_TZ)

    late_seconds = (confirmed_muscat - start_muscat).total_seconds()

    if late_seconds <= 0:
        # Confirmed on time or early
        return ON_TIME_POINTS
    elif late_seconds <= LATE_WINDOW_MINUTES * 60:
        # Within the grace window (1–5 minutes late)
        return LATE_POINTS
    else:
        # More than 5 minutes late
        return MISS_POINTS


# ─── Confirmation ─────────────────────────────────────────────────────────────

def confirm_duty(
    db: Session,
    teacher_id: int,
    assignment_id: int,
    confirmed_at_utc: Optional[datetime] = None,
) -> DutyConfirmation:
    """
    Record a teacher's duty confirmation and calculate their points.

    Raises:
        ValueError: if assignment not found, teacher mismatch, week not published,
                    or confirmation already exists.
    """
    if confirmed_at_utc is None:
        confirmed_at_utc = datetime.utcnow()

    # Validate assignment
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise ValueError(f"Assignment {assignment_id} not found.")

    if assignment.teacher_id != teacher_id:
        raise ValueError("This assignment does not belong to this teacher.")

    # Validate the week is published (no points for draft weeks)
    sl: ShiftLocation = assignment.shift_location
    day: DayPlan = sl.day_plan
    week: WeekPlan = day.week_plan
    if week.status != "published":
        raise ValueError("Cannot confirm a duty in a draft week.")

    # Check not already confirmed
    existing = db.query(DutyConfirmation).filter(
        DutyConfirmation.teacher_id == teacher_id,
        DutyConfirmation.assignment_id == assignment_id,
    ).first()
    if existing:
        raise ValueError("Duty already confirmed.")

    # Calculate points
    points = calculate_points(sl.shift.start_time, day.date, confirmed_at_utc)

    confirmation = DutyConfirmation(
        teacher_id=teacher_id,
        assignment_id=assignment_id,
        confirmed_at=confirmed_at_utc,
        points_earned=points,
    )
    db.add(confirmation)
    db.commit()
    db.refresh(confirmation)

    logger.info(
        f"Teacher {teacher_id} confirmed assignment {assignment_id} "
        f"at {confirmed_at_utc.isoformat()} UTC → {points} point(s)"
    )

    # Update the monthly summary cache
    _upsert_monthly_summary(db, teacher_id, confirmed_at_utc)

    return confirmation


# ─── Monthly Summary ──────────────────────────────────────────────────────────

def _upsert_monthly_summary(db: Session, teacher_id: int, reference_dt: datetime):
    """
    Recalculate and store the monthly summary for teacher_id for the month of reference_dt.
    """
    # Convert to Muscat time for month bucketing
    if reference_dt.tzinfo is None:
        ref_muscat = pytz.utc.localize(reference_dt).astimezone(MUSCAT_TZ)
    else:
        ref_muscat = reference_dt.astimezone(MUSCAT_TZ)

    year = ref_muscat.year
    month = ref_muscat.month

    total = _compute_monthly_total(db, teacher_id, year, month)

    summary = db.query(MonthlyPointsSummary).filter(
        MonthlyPointsSummary.teacher_id == teacher_id,
        MonthlyPointsSummary.year == year,
        MonthlyPointsSummary.month == month,
    ).first()

    if summary:
        summary.total_points = total
        summary.updated_at = datetime.utcnow()
    else:
        summary = MonthlyPointsSummary(
            teacher_id=teacher_id,
            year=year,
            month=month,
            total_points=total,
        )
        db.add(summary)

    db.commit()


def _compute_monthly_total(db: Session, teacher_id: int, year: int, month: int) -> int:
    """
    Sum confirmed points for a teacher in the given month (Asia/Muscat calendar month).
    We use the UTC confirmed_at but note: UTC+4 means Muscat month starts 4h before UTC.
    For simplicity and correctness we convert in Python after fetching the month's records.
    """
    # Fetch the full month's confirmations for this teacher
    # Use ±1 day buffer, then filter precisely in Python to handle the UTC/Muscat offset
    from datetime import date as date_type
    import calendar

    month_start_muscat = MUSCAT_TZ.localize(datetime(year, month, 1, 0, 0, 0))
    last_day = calendar.monthrange(year, month)[1]
    month_end_muscat = MUSCAT_TZ.localize(datetime(year, month, last_day, 23, 59, 59))

    # Convert to UTC for DB query
    start_utc = month_start_muscat.astimezone(pytz.utc).replace(tzinfo=None)
    end_utc = month_end_muscat.astimezone(pytz.utc).replace(tzinfo=None)

    rows = db.query(DutyConfirmation).filter(
        DutyConfirmation.teacher_id == teacher_id,
        DutyConfirmation.confirmed_at >= start_utc,
        DutyConfirmation.confirmed_at <= end_utc,
    ).all()

    # Re-verify month in Muscat TZ to be precise
    total = 0
    for row in rows:
        confirmed_muscat = pytz.utc.localize(row.confirmed_at).astimezone(MUSCAT_TZ)
        if confirmed_muscat.year == year and confirmed_muscat.month == month:
            total += row.points_earned

    return total


def rebuild_monthly_summary_for_all(db: Session, year: int, month: int):
    """
    Rebuild the monthly summary for ALL teachers for a given month.
    Called by the monthly reset cron job.
    """
    teachers = db.query(Teacher).filter(Teacher.active == True).all()
    for teacher in teachers:
        total = _compute_monthly_total(db, teacher.id, year, month)
        summary = db.query(MonthlyPointsSummary).filter(
            MonthlyPointsSummary.teacher_id == teacher.id,
            MonthlyPointsSummary.year == year,
            MonthlyPointsSummary.month == month,
        ).first()
        if summary:
            summary.total_points = total
            summary.updated_at = datetime.utcnow()
        else:
            db.add(MonthlyPointsSummary(
                teacher_id=teacher.id,
                year=year,
                month=month,
                total_points=total,
            ))
    db.commit()
    logger.info(f"Monthly summary rebuilt for {len(teachers)} teachers ({year}/{month:02d})")


# ─── Queries ──────────────────────────────────────────────────────────────────

def get_teacher_monthly_points(db: Session, teacher_id: int, year: int, month: int) -> int:
    """Return a teacher's total points for a specific month."""
    summary = db.query(MonthlyPointsSummary).filter(
        MonthlyPointsSummary.teacher_id == teacher_id,
        MonthlyPointsSummary.year == year,
        MonthlyPointsSummary.month == month,
    ).first()
    if summary:
        return summary.total_points
    # Fallback: compute live if not cached
    total = _compute_monthly_total(db, teacher_id, year, month)
    return total


def get_monthly_report(db: Session, year: int, month: int) -> list[dict]:
    """
    Return a full monthly report: all active teachers with their point totals,
    confirmation count, and breakdown of 2/1/0 point confirmations.
    """
    import calendar
    from datetime import date as date_type

    month_start_muscat = MUSCAT_TZ.localize(datetime(year, month, 1))
    last_day = calendar.monthrange(year, month)[1]
    month_end_muscat = MUSCAT_TZ.localize(datetime(year, month, last_day, 23, 59, 59))
    start_utc = month_start_muscat.astimezone(pytz.utc).replace(tzinfo=None)
    end_utc = month_end_muscat.astimezone(pytz.utc).replace(tzinfo=None)

    teachers = db.query(Teacher).filter(Teacher.active == True).order_by(Teacher.name).all()
    report = []

    for teacher in teachers:
        confirmations = db.query(DutyConfirmation).filter(
            DutyConfirmation.teacher_id == teacher.id,
            DutyConfirmation.confirmed_at >= start_utc,
            DutyConfirmation.confirmed_at <= end_utc,
        ).all()

        # Filter to exact Muscat month
        confs = []
        for c in confirmations:
            cm = pytz.utc.localize(c.confirmed_at).astimezone(MUSCAT_TZ)
            if cm.year == year and cm.month == month:
                confs.append(c)

        total   = sum(c.points_earned for c in confs)
        on_time = sum(1 for c in confs if c.points_earned == 2)
        late    = sum(1 for c in confs if c.points_earned == 1)
        missed  = sum(1 for c in confs if c.points_earned == 0)

        report.append({
            "teacher_id":   teacher.id,
            "teacher_name": teacher.name,
            "total_points": total,
            "confirmations": len(confs),
            "on_time":  on_time,
            "late":     late,
            "no_points": missed,
        })

    # Sort by total_points descending (leaderboard style)
    report.sort(key=lambda x: x["total_points"], reverse=True)
    return report


def get_teacher_confirmation_detail(
    db: Session, teacher_id: int, year: int, month: int
) -> list[dict]:
    """
    Return per-duty confirmation details for a teacher in a month.
    Useful for the detailed breakdown view.
    """
    import calendar

    month_start_muscat = MUSCAT_TZ.localize(datetime(year, month, 1))
    last_day = calendar.monthrange(year, month)[1]
    month_end_muscat = MUSCAT_TZ.localize(datetime(year, month, last_day, 23, 59, 59))
    start_utc = month_start_muscat.astimezone(pytz.utc).replace(tzinfo=None)
    end_utc = month_end_muscat.astimezone(pytz.utc).replace(tzinfo=None)

    confirmations = (
        db.query(DutyConfirmation)
        .filter(
            DutyConfirmation.teacher_id == teacher_id,
            DutyConfirmation.confirmed_at >= start_utc,
            DutyConfirmation.confirmed_at <= end_utc,
        )
        .order_by(DutyConfirmation.confirmed_at)
        .all()
    )

    result = []
    for c in confirmations:
        cm = pytz.utc.localize(c.confirmed_at).astimezone(MUSCAT_TZ)
        if cm.year != year or cm.month != month:
            continue

        sl: ShiftLocation = c.assignment.shift_location
        day: DayPlan = sl.day_plan

        result.append({
            "confirmation_id": c.id,
            "date":            str(day.date),
            "shift_name_en":   sl.shift.name_en,
            "shift_name_ar":   sl.shift.name_ar,
            "shift_start":     str(sl.shift.start_time),
            "location_name_en": sl.location.name_en,
            "location_name_ar": sl.location.name_ar,
            "confirmed_at_muscat": cm.strftime("%Y-%m-%d %H:%M:%S"),
            "points_earned":   c.points_earned,
        })

    return result