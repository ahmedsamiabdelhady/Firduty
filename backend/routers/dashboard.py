"""
routers/dashboard.py — Admin dashboard statistics endpoint.

GET /admin/dashboard
  Returns aggregated insights about the current and next week.

Performance notes (v2.4):
  • WeekPlan loads use selectinload chains — zero lazy-load N+1 on assignments.
  • Teacher name is taken from the eagerly-loaded assignment.teacher relation.
  • Counts (teachers, locations, shifts) use db.query(...).count() — single
    SQL COUNT(*) each, no Python-side len() on full result sets.
  • all_active is fetched once, ID-only set built for O(1) membership checks.
"""

from datetime import timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models.models import (
    Teacher, WeekPlan, DayPlan, ShiftLocation, Assignment, Location, Shift
)
from routers.auth import get_current_admin
from services.week_service import get_current_week_start

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])


# ─── Eager-load helper ────────────────────────────────────────────────────────

def _load_week(db: Session, week_start) -> WeekPlan | None:
    """
    Load a WeekPlan with all nested relations in a single round-trip.
    Using selectinload on assignment→teacher avoids N+1 when we access
    a.teacher.name inside _week_stats.
    """
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
        )
        .filter(WeekPlan.week_start_date == week_start)
        .first()
    )


# ─── Stats builder ────────────────────────────────────────────────────────────

def _week_stats(week: WeekPlan) -> dict:
    """
    Build stats dict for one week plan.
    All data comes from the already-loaded ORM graph — no additional queries.
    """
    total_slots = 0
    assigned_slots = 0
    duties_per_day: dict[str, int] = {}
    duties_per_type: dict[str, int] = {"morning_endofday": 0, "break": 0}
    teacher_counts: dict[int, dict] = {}

    for day in week.day_plans:
        day_assigned = 0
        for sl in day.shift_locations:
            dtype = sl.shift.duty_type if sl.shift else "morning_endofday"
            for a in sl.assignments:
                total_slots += 1
                if a.teacher_id:
                    assigned_slots += 1
                    day_assigned += 1
                    duties_per_type[dtype] = duties_per_type.get(dtype, 0) + 1
                    if a.teacher_id not in teacher_counts:
                        teacher_counts[a.teacher_id] = {
                            "teacher_id": a.teacher_id,
                            # teacher is already loaded — no extra query
                            "teacher_name": a.teacher.name if a.teacher else str(a.teacher_id),
                            "count": 0,
                        }
                    teacher_counts[a.teacher_id]["count"] += 1
        duties_per_day[str(day.date)] = day_assigned

    teacher_list = sorted(teacher_counts.values(), key=lambda x: x["count"], reverse=True)

    return {
        "week_start": str(week.week_start_date),
        "status": str(week.status),
        "version": week.version,
        "total_slots": total_slots,
        "assigned_slots": assigned_slots,
        "unassigned_slots": total_slots - assigned_slots,
        "duties_per_day": duties_per_day,
        "duties_per_type": duties_per_type,
        "teacher_counts": teacher_list,
        "teachers_assigned_count": len(teacher_counts),
    }


# ─── Warnings ─────────────────────────────────────────────────────────────────

def _fairness_warnings(week_stats: dict, total_active: int, week_label: str) -> list[str]:
    warnings = []
    assigned_count = len(week_stats["teacher_counts"])
    without = total_active - assigned_count

    if week_stats["unassigned_slots"] > 0:
        warnings.append(
            f"{week_stats['unassigned_slots']} empty slot(s) in {week_label} — assign teachers before publishing."
        )
    if without > 0:
        warnings.append(
            f"{without} active teacher(s) have no duties in {week_label}."
        )
    counts = [t["count"] for t in week_stats["teacher_counts"]]
    if counts and max(counts) - min(counts) >= 3:
        warnings.append(
            f"Uneven distribution in {week_label}: highest {max(counts)} vs lowest {min(counts)} duties."
        )
    return warnings


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def get_dashboard(
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """
    Admin dashboard: current-week and next-week insights.

    Single DB round-trip per week plan (selectinload), plus three
    COUNT(*) queries. Total: ~5 SQL statements regardless of data size.
    """
    current_ws = get_current_week_start()
    next_ws    = current_ws + timedelta(weeks=1)

    # ── Parallel-ish queries (SQLAlchemy synchronous, but all fast) ──────────
    current_week  = _load_week(db, current_ws)
    next_week     = _load_week(db, next_ws)
    total_active  = db.query(Teacher).filter(Teacher.active.is_(True)).count()
    total_locations = db.query(Location).count()
    total_shifts    = db.query(Shift).count()

    # Fetch active teacher IDs + names in one query (id + name only, no *)
    active_teachers = (
        db.query(Teacher.id, Teacher.name)
        .filter(Teacher.active.is_(True))
        .order_by(Teacher.name)
        .all()
    )

    warnings: list[str] = []
    current_stats: dict | None = None
    next_stats:    dict | None = None

    if current_week:
        current_stats = _week_stats(current_week)
        warnings.extend(_fairness_warnings(current_stats, total_active, "current week"))
    else:
        warnings.append("No week plan exists for the current week.")

    if next_week:
        next_stats = _week_stats(next_week)
        warnings.extend(_fairness_warnings(next_stats, total_active, "next week (draft)"))

    # Teachers with no duties this week — O(n) set lookup
    assigned_ids: set[int] = (
        {t["teacher_id"] for t in current_stats["teacher_counts"]}
        if current_stats else set()
    )
    teachers_without_duties = [
        {"teacher_id": t.id, "teacher_name": t.name}
        for t in active_teachers
        if t.id not in assigned_ids
    ]

    top_teachers = current_stats["teacher_counts"][:5] if current_stats else []

    return {
        "current_week":  current_stats,
        "next_week":     next_stats,
        "total_active_teachers": total_active,
        "total_locations": total_locations,
        "total_shifts":    total_shifts,
        "teachers_without_duties_this_week": teachers_without_duties,
        "top_teachers_this_week": top_teachers,
        "warnings": warnings,
        "pending_teachers_count": db.query(Teacher).filter(Teacher.status == "pending").count(),
    }