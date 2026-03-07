"""
points_service.py — Duty confirmation and point scoring.

Scoring (Asia/Muscat):
  confirmed_at <= shift start         → 2 points
  start < confirmed_at <= start + 5m  → 1 point
  confirmed_at > start + 5 minutes    → 0 points
"""

import calendar
import logging
from collections import defaultdict
from datetime import datetime, timezone, date
from typing import Optional

import pytz
from sqlalchemy.orm import Session

from models.models import Assignment, Teacher, ShiftLocation, DayPlan, WeekPlan
from models.points_models import DutyConfirmation, MonthlyPointsSummary

logger = logging.getLogger(__name__)

MUSCAT_TZ = pytz.timezone("Asia/Muscat")
LATE_WINDOW_MINUTES = 5
ON_TIME_POINTS = 2
LATE_POINTS = 1
MISS_POINTS = 0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _month_utc_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start_muscat = MUSCAT_TZ.localize(datetime(year, month, 1, 0, 0, 0))
    last_day = calendar.monthrange(year, month)[1]
    end_muscat = MUSCAT_TZ.localize(datetime(year, month, last_day, 23, 59, 59))
    return (
        start_muscat.astimezone(pytz.utc).replace(tzinfo=None),
        end_muscat.astimezone(pytz.utc).replace(tzinfo=None),
    )


# ─── Scoring ──────────────────────────────────────────────────────────────────

def calculate_points(shift_start_time, duty_date: date, confirmed_at_utc: datetime) -> int:
    start_naive = datetime.combine(duty_date, shift_start_time)
    start_muscat = MUSCAT_TZ.localize(start_naive)
    if confirmed_at_utc.tzinfo is None:
        confirmed_muscat = pytz.utc.localize(confirmed_at_utc).astimezone(MUSCAT_TZ)
    else:
        confirmed_muscat = confirmed_at_utc.astimezone(MUSCAT_TZ)
    late_seconds = (confirmed_muscat - start_muscat).total_seconds()
    if late_seconds <= 0:
        return ON_TIME_POINTS
    elif late_seconds <= LATE_WINDOW_MINUTES * 60:
        return LATE_POINTS
    else:
        return MISS_POINTS


# ─── Confirmation ─────────────────────────────────────────────────────────────

def confirm_duty(
    db: Session,
    teacher_id: int,
    assignment_id: int,
    confirmed_at_utc: Optional[datetime] = None,
) -> DutyConfirmation:
    if confirmed_at_utc is None:
        confirmed_at_utc = _utcnow()

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise ValueError(f"Assignment {assignment_id} not found.")
    if assignment.teacher_id != teacher_id:
        raise ValueError("This assignment does not belong to this teacher.")

    sl: ShiftLocation = assignment.shift_location
    day: DayPlan = sl.day_plan
    week: WeekPlan = day.week_plan
    if week.status != "published":
        raise ValueError("Cannot confirm a duty in a draft week.")

    existing = db.query(DutyConfirmation).filter(
        DutyConfirmation.teacher_id == teacher_id,
        DutyConfirmation.assignment_id == assignment_id,
    ).first()
    if existing:
        raise ValueError("Duty already confirmed.")

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
    _upsert_monthly_summary(db, teacher_id, confirmed_at_utc)
    return confirmation


# ─── Monthly Summary ──────────────────────────────────────────────────────────

def _upsert_monthly_summary(db: Session, teacher_id: int, reference_dt: datetime) -> None:
    if reference_dt.tzinfo is None:
        ref_muscat = pytz.utc.localize(reference_dt).astimezone(MUSCAT_TZ)
    else:
        ref_muscat = reference_dt.astimezone(MUSCAT_TZ)
    year, month = ref_muscat.year, ref_muscat.month
    total = _compute_monthly_total(db, teacher_id, year, month)
    summary = db.query(MonthlyPointsSummary).filter(
        MonthlyPointsSummary.teacher_id == teacher_id,
        MonthlyPointsSummary.year == year,
        MonthlyPointsSummary.month == month,
    ).first()
    if summary:
        summary.total_points = total
        summary.updated_at = _utcnow()
    else:
        db.add(MonthlyPointsSummary(teacher_id=teacher_id, year=year, month=month, total_points=total))
    db.commit()


def _compute_monthly_total(db: Session, teacher_id: int, year: int, month: int) -> int:
    start_utc, end_utc = _month_utc_bounds(year, month)
    rows = db.query(DutyConfirmation).filter(
        DutyConfirmation.teacher_id == teacher_id,
        DutyConfirmation.confirmed_at >= start_utc,
        DutyConfirmation.confirmed_at <= end_utc,
    ).all()
    total = 0
    for row in rows:
        cm = pytz.utc.localize(row.confirmed_at).astimezone(MUSCAT_TZ)
        if cm.year == year and cm.month == month:
            total += row.points_earned
    return total


def rebuild_monthly_summary_for_all(db: Session, year: int, month: int) -> None:
    teachers = db.query(Teacher).filter(Teacher.active.is_(True)).all()
    start_utc, end_utc = _month_utc_bounds(year, month)
    all_confs = db.query(DutyConfirmation).filter(
        DutyConfirmation.confirmed_at >= start_utc,
        DutyConfirmation.confirmed_at <= end_utc,
    ).all()
    totals: dict[int, int] = defaultdict(int)
    for c in all_confs:
        cm = pytz.utc.localize(c.confirmed_at).astimezone(MUSCAT_TZ)
        if cm.year == year and cm.month == month:
            totals[c.teacher_id] += c.points_earned
    for teacher in teachers:
        total = totals.get(teacher.id, 0)
        summary = db.query(MonthlyPointsSummary).filter(
            MonthlyPointsSummary.teacher_id == teacher.id,
            MonthlyPointsSummary.year == year,
            MonthlyPointsSummary.month == month,
        ).first()
        if summary:
            summary.total_points = total
            summary.updated_at = _utcnow()
        else:
            db.add(MonthlyPointsSummary(teacher_id=teacher.id, year=year, month=month, total_points=total))
    db.commit()
    logger.info(f"Monthly summary rebuilt for {len(teachers)} teachers ({year}/{month:02d})")


# ─── Queries ──────────────────────────────────────────────────────────────────

def get_teacher_monthly_points(db: Session, teacher_id: int, year: int, month: int) -> int:
    summary = db.query(MonthlyPointsSummary).filter(
        MonthlyPointsSummary.teacher_id == teacher_id,
        MonthlyPointsSummary.year == year,
        MonthlyPointsSummary.month == month,
    ).first()
    if summary:
        return summary.total_points
    return _compute_monthly_total(db, teacher_id, year, month)


def get_monthly_report(db: Session, year: int, month: int) -> list[dict]:
    start_utc, end_utc = _month_utc_bounds(year, month)
    teachers = db.query(Teacher).filter(Teacher.active.is_(True)).order_by(Teacher.name).all()
    all_confs = db.query(DutyConfirmation).filter(
        DutyConfirmation.confirmed_at >= start_utc,
        DutyConfirmation.confirmed_at <= end_utc,
    ).all()
    confs_by_teacher: dict[int, list] = defaultdict(list)
    for c in all_confs:
        cm = pytz.utc.localize(c.confirmed_at).astimezone(MUSCAT_TZ)
        if cm.year == year and cm.month == month:
            confs_by_teacher[c.teacher_id].append(c)
    report = []
    for teacher in teachers:
        confs = confs_by_teacher.get(teacher.id, [])
        report.append({
            "teacher_id":    teacher.id,
            "teacher_name":  teacher.name,
            "total_points":  sum(c.points_earned for c in confs),
            "confirmations": len(confs),
            "on_time":       sum(1 for c in confs if c.points_earned == 2),
            "late":          sum(1 for c in confs if c.points_earned == 1),
            "no_points":     sum(1 for c in confs if c.points_earned == 0),
        })
    report.sort(key=lambda x: x["total_points"], reverse=True)
    return report


def get_teacher_confirmation_detail(
    db: Session, teacher_id: int, year: int, month: int
) -> list[dict]:
    """Per-duty confirmation details for a teacher. Duty-type aware."""
    start_utc, end_utc = _month_utc_bounds(year, month)
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
        duty_type = sl.shift.duty_type
        entry: dict = {
            "confirmation_id":     c.id,
            "date":                str(day.date),
            "shift_name_en":       sl.shift.name_en,
            "shift_name_ar":       sl.shift.name_ar,
            "shift_start":         str(sl.shift.start_time),
            "duty_type":           duty_type,
            "confirmed_at_muscat": cm.strftime("%Y-%m-%d %H:%M:%S"),
            "points_earned":       c.points_earned,
        }
        if duty_type == "morning_endofday" and sl.location:
            entry["location_name_en"] = sl.location.name_en
            entry["location_name_ar"] = sl.location.name_ar
        else:
            entry["location_name_en"] = None
            entry["location_name_ar"] = None
        entry["grade_class"] = c.assignment.grade_class
        result.append(entry)
    return result