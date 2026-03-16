"""
routers/dashboard.py — Admin dashboard statistics endpoint v2.5

GET /admin/dashboard

All 8 insight groups:
  1. Per-day slot stats for current week   (assigned/empty per day — NOT week totals)
  2. Today's live duty status              (assigned + confirmed today)
  3. Unpublished days this week            (publish status per day)
  4. Monthly confirmation rate             (% of assigned duties confirmed)
  5. Punctuality breakdown                 (on-time / late / missed this month)
  6. Teacher reliability                   (most unconfirmed duties this week)
  7. Workload balance score                (max vs min assignment gap)
  8. Teachers with zero duties this month  (not just this week)

Performance:
  - Week data: selectinload chain (1 round-trip per week plan)
  - Monthly stats: direct SQL aggregation — no ORM object hydration
  - ~10 SQL statements total regardless of data size
"""

import calendar
from datetime import date, datetime, timedelta
from typing import Optional

import pytz
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models.models import (
    Teacher, WeekPlan, DayPlan, ShiftLocation, Assignment, Location, Shift
)
from models.points_models import DutyConfirmation
from routers.auth import get_current_admin
from services.week_service import get_current_week_start

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])

MUSCAT_TZ = pytz.timezone("Asia/Muscat")
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
DAY_KEYS  = ["day_sun", "day_mon", "day_tue", "day_wed", "day_thu", "day_fri", "day_sat"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now_muscat() -> datetime:
    return datetime.now(pytz.utc).astimezone(MUSCAT_TZ)


def _month_utc_bounds(year: int, month: int):
    start = MUSCAT_TZ.localize(datetime(year, month, 1, 0, 0, 0))
    last_day = calendar.monthrange(year, month)[1]
    end = MUSCAT_TZ.localize(datetime(year, month, last_day, 23, 59, 59))
    return (
        start.astimezone(pytz.utc).replace(tzinfo=None),
        end.astimezone(pytz.utc).replace(tzinfo=None),
    )


def _load_week(db: Session, week_start: date) -> Optional[WeekPlan]:
    """Load week with full ORM graph — zero lazy-load N+1."""
    return (
        db.query(WeekPlan)
        .options(
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.shift),
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.assignments)
            .selectinload(Assignment.teacher),
            selectinload(WeekPlan.day_plans)
            .selectinload(DayPlan.shift_locations)
            .selectinload(ShiftLocation.assignments)
            .selectinload(Assignment.confirmation),
        )
        .filter(WeekPlan.week_start_date == week_start)
        .first()
    )


# ─── Per-day slot stats ───────────────────────────────────────────────────────

def _per_day_stats(week: WeekPlan) -> list[dict]:
    """
    Per-day breakdown: total/assigned/empty/confirmed slots.
    Slots are per day — never aggregated into a week total.
    """
    result = []
    for day in sorted(week.day_plans, key=lambda d: d.date):
        total = assigned = confirmed = 0
        for sl in day.shift_locations:
            for a in sl.assignments:
                total += 1
                if a.teacher_id:
                    assigned += 1
                    if a.confirmation:
                        confirmed += 1
        # Python's isoweekday: Mon=1…Sun=7 → Sun-based index: Sun=0
        sun_idx = day.date.isoweekday() % 7
        result.append({
            "date":      str(day.date),
            "day_key":   DAY_KEYS[sun_idx],
            "day_name":  DAY_NAMES[sun_idx],
            "total":     total,
            "assigned":  assigned,
            "empty":     total - assigned,
            "confirmed": confirmed,
            "published": bool(getattr(day, "is_published", False)),
        })
    return result


# ─── Today live status ────────────────────────────────────────────────────────

def _today_status(per_day: list[dict]) -> Optional[dict]:
    today_str = str(_now_muscat().date())
    for d in per_day:
        if d["date"] == today_str:
            confirm_rate = (
                round(d["confirmed"] / d["assigned"] * 100)
                if d["assigned"] > 0 else 0
            )
            return {**d, "confirm_rate": confirm_rate}
    return None


# ─── Workload balance ─────────────────────────────────────────────────────────

def _workload_balance(teacher_counts: list[dict]) -> Optional[dict]:
    if len(teacher_counts) < 2:
        return None
    top = teacher_counts[0]
    bot = teacher_counts[-1]
    gap = top["count"] - bot["count"]
    return {
        "max_teacher": top["teacher_name"],
        "max_count":   top["count"],
        "min_teacher": bot["teacher_name"],
        "min_count":   bot["count"],
        "gap":         gap,
        "fair":        gap <= 2,
    }


# ─── Monthly confirmation stats ───────────────────────────────────────────────

def _monthly_confirmation_stats(db: Session, year: int, month: int) -> dict:
    """
    SQL GROUP BY points_earned for the month — single query.
    'total_assigned' = published assignments with a teacher this month.
    """
    start_utc, end_utc = _month_utc_bounds(year, month)

    rows = (
        db.query(
            DutyConfirmation.points_earned,
            func.count(DutyConfirmation.id).label("cnt"),
        )
        .filter(
            DutyConfirmation.confirmed_at >= start_utc,
            DutyConfirmation.confirmed_at <= end_utc,
        )
        .group_by(DutyConfirmation.points_earned)
        .all()
    )

    breakdown = {r.points_earned: r.cnt for r in rows}
    on_time   = breakdown.get(2, 0)
    late      = breakdown.get(1, 0)
    missed    = breakdown.get(0, 0)
    confirmed = on_time + late + missed

    # Total published assignments with a teacher in this calendar month
    total_assigned = (
        db.query(func.count(Assignment.id))
        .join(ShiftLocation, Assignment.shift_location_id == ShiftLocation.id)
        .join(DayPlan, ShiftLocation.day_plan_id == DayPlan.id)
        .filter(
            Assignment.teacher_id.isnot(None),
            DayPlan.date >= date(year, month, 1),
            DayPlan.date <= date(year, month, calendar.monthrange(year, month)[1]),
            DayPlan.is_published.is_(True),
        )
        .scalar() or 0
    )

    confirmation_rate = round(confirmed / total_assigned * 100) if total_assigned > 0 else 0

    return {
        "total_assigned":    total_assigned,
        "confirmed":         confirmed,
        "on_time":           on_time,
        "late":              late,
        "missed":            missed,
        "confirmation_rate": confirmation_rate,
    }


# ─── Teacher reliability ─────────────────────────────────────────────────────

def _teacher_reliability(week: WeekPlan, top_n: int = 5) -> list[dict]:
    """
    From published days only: teachers sorted by unconfirmed duty count.
    All data from already-loaded ORM graph — no extra queries.
    """
    data: dict[int, dict] = {}
    for day in week.day_plans:
        if not getattr(day, "is_published", False):
            continue
        for sl in day.shift_locations:
            for a in sl.assignments:
                if not a.teacher_id:
                    continue
                tid = a.teacher_id
                if tid not in data:
                    data[tid] = {
                        "teacher_id":   tid,
                        "teacher_name": a.teacher.name if a.teacher else str(tid),
                        "assigned":     0,
                        "confirmed":    0,
                    }
                data[tid]["assigned"] += 1
                if a.confirmation:
                    data[tid]["confirmed"] += 1

    result = []
    for t in data.values():
        t["unconfirmed"]   = t["assigned"] - t["confirmed"]
        t["confirm_rate"]  = (
            round(t["confirmed"] / t["assigned"] * 100) if t["assigned"] > 0 else 0
        )
        result.append(t)

    result.sort(key=lambda x: (-x["unconfirmed"], x["teacher_name"]))
    return result[:top_n]


# ─── Zero-duty teachers this month ───────────────────────────────────────────

def _zero_duty_teachers_month(
    db: Session, year: int, month: int, active_teachers
) -> list[dict]:
    """Active teachers with no confirmation at all this month."""
    start_utc, end_utc = _month_utc_bounds(year, month)

    active_with_conf = {
        row[0] for row in (
            db.query(DutyConfirmation.teacher_id)
            .filter(
                DutyConfirmation.confirmed_at >= start_utc,
                DutyConfirmation.confirmed_at <= end_utc,
            )
            .distinct()
            .all()
        )
    }

    return [
        {"teacher_id": t.id, "teacher_name": t.name}
        for t in active_teachers
        if t.id not in active_with_conf
    ]


# ─── Week teacher counts ─────────────────────────────────────────────────────

def _week_teacher_counts(week: WeekPlan) -> list[dict]:
    counts: dict[int, dict] = {}
    for day in week.day_plans:
        for sl in day.shift_locations:
            for a in sl.assignments:
                if not a.teacher_id:
                    continue
                tid = a.teacher_id
                if tid not in counts:
                    counts[tid] = {
                        "teacher_id":   tid,
                        "teacher_name": a.teacher.name if a.teacher else str(tid),
                        "count":        0,
                    }
                counts[tid]["count"] += 1
    return sorted(counts.values(), key=lambda x: x["count"], reverse=True)


# ─── Fairness warnings ────────────────────────────────────────────────────────

def _fairness_warnings(
    per_day: list[dict], total_active: int,
    teacher_counts: list[dict], week_label: str,
) -> list[str]:
    warnings = []

    # Days with empty slots — per day, not a week total
    for d in per_day:
        if d["empty"] > 0:
            warnings.append(
                f"{d['empty']} empty slot(s) on {d['day_name']} "
                f"({d['date']}) in {week_label}."
            )

    assigned_ids = {t["teacher_id"] for t in teacher_counts}
    without = total_active - len(assigned_ids)
    if without > 0:
        warnings.append(
            f"{without} active teacher(s) have no duties in {week_label}."
        )

    if len(teacher_counts) >= 2:
        gap = teacher_counts[0]["count"] - teacher_counts[-1]["count"]
        if gap >= 3:
            warnings.append(
                f"Uneven distribution in {week_label}: "
                f"{teacher_counts[0]['teacher_name']} has {teacher_counts[0]['count']} "
                f"duties vs {teacher_counts[-1]['teacher_name']} "
                f"with {teacher_counts[-1]['count']}."
            )
    return warnings


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def get_dashboard(
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    now_muscat  = _now_muscat()
    current_ws  = get_current_week_start()
    next_ws     = current_ws + timedelta(weeks=1)
    year, month = now_muscat.year, now_muscat.month

    # ── Week plans ────────────────────────────────────────────────────────────
    current_week = _load_week(db, current_ws)
    next_week    = _load_week(db, next_ws)

    # ── Scalar counts ─────────────────────────────────────────────────────────
    total_active    = db.query(Teacher).filter(Teacher.active.is_(True)).count()
    total_locations = db.query(Location).count()
    total_shifts    = db.query(Shift).count()
    pending_count   = db.query(Teacher).filter(Teacher.status == "pending").count()

    active_teachers = (
        db.query(Teacher)
        .filter(Teacher.active.is_(True))
        .order_by(Teacher.name)
        .all()
    )

    # ── Per-day stats ─────────────────────────────────────────────────────────
    current_per_day = _per_day_stats(current_week) if current_week else []
    next_per_day    = _per_day_stats(next_week)    if next_week    else []

    current_teacher_counts = _week_teacher_counts(current_week) if current_week else []
    next_teacher_counts    = _week_teacher_counts(next_week)    if next_week    else []

    warnings: list[str] = []
    if current_week:
        warnings.extend(_fairness_warnings(
            current_per_day, total_active, current_teacher_counts, "current week"
        ))
    else:
        warnings.append("No week plan for the current week.")

    if next_week:
        warnings.extend(_fairness_warnings(
            next_per_day, total_active, next_teacher_counts, "next week (draft)"
        ))

    # ── Other insights ────────────────────────────────────────────────────────
    today_status     = _today_status(current_per_day)
    unpublished_days = [d for d in current_per_day if not d["published"]]
    monthly_stats    = _monthly_confirmation_stats(db, year, month)
    reliability      = _teacher_reliability(current_week) if current_week else []
    balance          = _workload_balance(current_teacher_counts)
    zero_month       = _zero_duty_teachers_month(db, year, month, active_teachers)

    assigned_week_ids = {t["teacher_id"] for t in current_teacher_counts}
    no_duty_week = [
        {"teacher_id": t.id, "teacher_name": t.name}
        for t in active_teachers
        if t.id not in assigned_week_ids
    ]

    return {
        # Summary
        "total_active_teachers":  total_active,
        "total_locations":        total_locations,
        "total_shifts":           total_shifts,
        "pending_teachers_count": pending_count,

        # Per-day slot data (both weeks) — no week-level totals
        "current_week_days":    current_per_day,
        "next_week_days":       next_per_day,
        "current_week_status":  str(current_week.status) if current_week else None,
        "next_week_status":     str(next_week.status)    if next_week    else None,
        "current_week_version": current_week.version if current_week else None,

        # Today
        "today": today_status,

        # Unpublished
        "unpublished_days": unpublished_days,

        # Monthly engagement
        "monthly_stats": monthly_stats,
        "month":         month,
        "year":          year,

        # Teacher insights
        "top_teachers":                 current_teacher_counts[:5],
        "teacher_reliability":          reliability,
        "teachers_without_duties_week": no_duty_week,
        "zero_duty_teachers_month":     zero_month,

        # Balance
        "workload_balance": balance,

        # Warnings
        "warnings": warnings,
    }