"""
routers/reports.py — Admin-only reporting endpoints.

Provides monthly points leaderboard and per-teacher breakdowns.
Protected by JWT (admin only).
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from database import get_db
from routers.auth import get_current_admin
from services.points_service import (
    get_monthly_report,
    get_teacher_confirmation_detail,
    rebuild_monthly_summary_for_all,
)

router = APIRouter(prefix="/admin/reports", tags=["admin-reports"])


@router.get("/monthly-points")
def monthly_points_report(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """
    Full monthly points leaderboard for all active teachers.
    Returns ranked list with total points, confirmation counts, and breakdowns.
    """
    report = get_monthly_report(db, year, month)
    return {
        "year": year,
        "month": month,
        "teachers": report,
        "total_teachers": len(report),
        "total_confirmations": sum(r["confirmations"] for r in report),
    }


@router.get("/monthly-points/{teacher_id}")
def teacher_monthly_detail(
    teacher_id: int,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """
    Detailed per-duty confirmation breakdown for a single teacher in a month.
    """
    details = get_teacher_confirmation_detail(db, teacher_id, year, month)
    total = sum(d["points_earned"] for d in details)
    return {
        "teacher_id": teacher_id,
        "year": year,
        "month": month,
        "total_points": total,
        "duties": details,
    }


@router.post("/monthly-points/rebuild")
def rebuild_monthly_cache(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """
    Manually trigger a rebuild of the monthly points cache for all teachers.
    Normally called automatically by the monthly cron job.
    """
    rebuild_monthly_summary_for_all(db, year, month)
    return {"status": "rebuilt", "year": year, "month": month}


@router.get("/monthly-points/export/csv")
def export_monthly_csv(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """
    Export monthly points report as a CSV file for download.
    """
    import csv
    import io

    report = get_monthly_report(db, year, month)

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Rank", "Teacher Name", "Total Points",
        "Confirmations", "On Time (2pts)", "Late 1-5min (1pt)", "No Points (0pt)"
    ])

    for rank, row in enumerate(report, start=1):
        writer.writerow([
            rank,
            row["teacher_name"],
            row["total_points"],
            row["confirmations"],
            row["on_time"],
            row["late"],
            row["no_points"],
        ])

    csv_content = output.getvalue()
    filename = f"firduty_points_{year}_{month:02d}.csv"

    return Response(
        content=csv_content.encode("utf-8-sig"),  # utf-8-sig for Excel Arabic compatibility
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )