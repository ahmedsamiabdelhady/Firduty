"""
routers/dashboard.py — Admin dashboard statistics endpoint.

GET /admin/dashboard
  Returns aggregated insights about the current and next week:
  - slot/assignment counts
  - per-teacher, per-day, per-duty-type breakdowns
  - teachers with no duties (fairness warning)
  - distribution evenness score
"""

from collections import defaultdict
from datetime import timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models.models import (
    Teacher, WeekPlan, DayPlan, ShiftLocation, Assignment, Location, Shift
)
from routers.auth import get_current_admin
from services.week_service import get_current_week_start

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])


def _week_stats(week: WeekPlan, db: Session) -> dict:
    """Build stats dict for one week plan."""
    total_slots = 0
    assigned_slots = 0
    duties_per_day: dict[str, int] = {}
    duties_per_type: dict[str, int] = {"morning_endofday": 0, "break": 0}
    teacher_counts: dict[int, dict] = {}  # teacher_id → {name, count}

    for day in week.day_plans:
        day_assigned = 0
        for sl in day.shift_locations:
            dtype = sl.shift.duty_type
            for a in sl.assignments:
                total_slots += 1
                if a.teacher_id:
                    assigned_slots += 1
                    day_assigned += 1
                    duties_per_type[dtype] = duties_per_type.get(dtype, 0) + 1
                    if a.teacher_id not in teacher_counts:
                        teacher_counts[a.teacher_id] = {
                            "teacher_id": a.teacher_id,
                            "teacher_name": a.teacher.name if a.teacher else str(a.teacher_id),
                            "count": 0,
                        }
                    teacher_counts[a.teacher_id]["count"] += 1
        duties_per_day[str(day.date)] = day_assigned

    teacher_list = sorted(teacher_counts.values(), key=lambda x: x["count"], reverse=True)

    return {
        "week_start": str(week.week_start_date),
        "status": week.status,
        "version": week.version,
        "total_slots": total_slots,
        "assigned_slots": assigned_slots,
        "unassigned_slots": total_slots - assigned_slots,
        "duties_per_day": duties_per_day,
        "duties_per_type": duties_per_type,
        "teacher_counts": teacher_list,
        "teachers_assigned_count": len(teacher_counts),
    }


def _fairness_warnings(
    week_stats: dict,
    all_active_teachers: list,
    week_label: str,
) -> list[str]:
    """Generate warnings about assignment distribution."""
    warnings = []
    assigned_ids = {t["teacher_id"] for t in week_stats["teacher_counts"]}
    total_active = len(all_active_teachers)
    without = total_active - len(assigned_ids)

    if week_stats["unassigned_slots"] > 0:
        warnings.append(
            f"{week_stats['unassigned_slots']} empty slot(s) in {week_label} — assign teachers before publishing."
        )
    if without > 0:
        warnings.append(
            f"{without} active teacher(s) have no duties in {week_label}."
        )

    counts = [t["count"] for t in week_stats["teacher_counts"]]
    if counts:
        if max(counts) - min(counts) >= 3:
            warnings.append(
                f"Uneven distribution in {week_label}: highest {max(counts)} duties vs lowest {min(counts)}."
            )

    return warnings


@router.get("/dashboard")
def get_dashboard(
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """
    Admin dashboard: current-week and next-week insights.
    Returns assignment stats, per-teacher counts, distribution warnings.
    """
    current_ws = get_current_week_start()
    next_ws = current_ws + timedelta(weeks=1)

    current_week = db.query(WeekPlan).filter(WeekPlan.week_start_date == current_ws).first()
    next_week = db.query(WeekPlan).filter(WeekPlan.week_start_date == next_ws).first()

    all_active = db.query(Teacher).filter(Teacher.active.is_(True)).order_by(Teacher.name).all()
    total_active = len(all_active)
    total_locations = db.query(Location).count()
    total_shifts = db.query(Shift).count()

    warnings: list[str] = []
    current_stats = None
    next_stats = None

    if current_week:
        current_stats = _week_stats(current_week, db)
        warnings.extend(_fairness_warnings(current_stats, all_active, "current week"))
    else:
        warnings.append("No week plan exists for the current week.")

    if next_week:
        next_stats = _week_stats(next_week, db)
        warnings.extend(_fairness_warnings(next_stats, all_active, "next week (draft)"))

    # Teachers with no duties in current week
    assigned_this_week: set[int] = set()
    if current_stats:
        assigned_this_week = {t["teacher_id"] for t in current_stats["teacher_counts"]}
    teachers_without_duties = [
        {"teacher_id": t.id, "teacher_name": t.name}
        for t in all_active
        if t.id not in assigned_this_week
    ]

    # Top teachers this week (top 5)
    top_teachers = (current_stats["teacher_counts"][:5] if current_stats else [])

    return {
        "current_week": current_stats,
        "next_week": next_stats,
        "total_active_teachers": total_active,
        "total_locations": total_locations,
        "total_shifts": total_shifts,
        "teachers_without_duties_this_week": teachers_without_duties,
        "top_teachers_this_week": top_teachers,
        "warnings": warnings,
    }