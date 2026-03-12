"""
routers/reports.py — Admin monthly points reports and CSV export.

GET  /admin/reports/monthly-points?year=&month=
    Full leaderboard — all active teachers sorted by points descending.

GET  /admin/reports/monthly-points/{teacher_id}?year=&month=
    Per-duty detail for a single teacher.

GET  /admin/reports/monthly-points/export/csv?year=&month=
    Download leaderboard as CSV.

POST /admin/reports/monthly-points/rebuild?year=&month=
    Rebuild cached MonthlyPointsSummary rows.
"""

import csv
import io
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from services.points_service import (
    get_monthly_report,
    get_teacher_confirmation_detail,
    rebuild_monthly_summary_for_all,
)
from routers.auth import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/reports", tags=["admin-reports"])


@router.get("/monthly-points")
def monthly_leaderboard(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """Monthly points leaderboard for all active teachers."""
    rows = get_monthly_report(db, year, month)
    total_points = sum(r["total_points"] for r in rows)
    total_confs = sum(r["confirmations"] for r in rows)
    teachers_with_data = sum(1 for r in rows if r["confirmations"] > 0)
    avg = round(total_points / teachers_with_data, 1) if teachers_with_data else 0

    return {
        "year":             year,
        "month":            month,
        "summary": {
            "active_teachers":       len(rows),
            "total_confirmations":   total_confs,
            "total_points":          total_points,
            "avg_points_per_teacher": avg,
        },
        "leaderboard": rows,
    }


@router.get("/monthly-points/export/csv")
def export_csv(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """Download monthly leaderboard as a UTF-8 CSV file."""
    rows = get_monthly_report(db, year, month)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Rank", "Teacher ID", "Teacher Name",
        "Total Points", "Confirmations",
        "On Time (2pts)", "Late 1-5min (1pt)", "No Points (0pts)",
    ])
    for rank, row in enumerate(rows, start=1):
        writer.writerow([
            rank,
            row["teacher_id"],
            row["teacher_name"],
            row["total_points"],
            row["confirmations"],
            row["on_time"],
            row["late"],
            row["no_points"],
        ])

    buf.seek(0)
    filename = f"firduty_points_{year}_{month:02d}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/monthly-points/{teacher_id}")
def teacher_detail(
    teacher_id: int,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """Duty-by-duty confirmation breakdown for one teacher (admin view)."""
    details = get_teacher_confirmation_detail(db, teacher_id, year, month)
    total = sum(d["points_earned"] for d in details)
    return {
        "teacher_id":    teacher_id,
        "year":          year,
        "month":         month,
        "total_points":  total,
        "confirmations": details,
    }


@router.post("/monthly-points/rebuild")
def rebuild_cache(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """Rebuild the monthly points cache for all active teachers."""
    rebuild_monthly_summary_for_all(db, year, month)
    return {"status": "rebuilt", "year": year, "month": month}