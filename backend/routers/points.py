"""
routers/points.py — Duty confirmation and points query endpoints.

POST /points/teachers/{id}/confirm
    Teacher confirms they attended a duty assignment.
    Points are calculated based on how early/late the confirmation is
    relative to the shift start time (Asia/Muscat timezone).

    Scoring:
      confirmed_at <= shift_start           → 2 points (on time)
      shift_start < confirmed_at <= +5 min  → 1 point  (late but within window)
      confirmed_at > shift_start + 5 min    → 0 points (missed)

GET /points/teachers/{id}/monthly?year=&month=
    Monthly total and per-duty confirmation history for a teacher.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services.points_service import (
    confirm_duty,
    get_teacher_monthly_points,
    get_teacher_confirmation_detail,
    rebuild_monthly_summary_for_all,
)
from schemas.schemas import ConfirmDutyRequest
from routers.auth import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/points", tags=["points"])


@router.post("/teachers/{teacher_id}/confirm")
def confirm_teacher_duty(
    teacher_id: int,
    data: ConfirmDutyRequest,
    db: Session = Depends(get_db),
):
    """
    Confirm a teacher attended their duty assignment.
    Returns points earned and a bilingual confirmation message.
    """
    try:
        confirmation = confirm_duty(
            db=db,
            teacher_id=teacher_id,
            assignment_id=data.assignment_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception(f"Unexpected error confirming duty for teacher {teacher_id}")
        raise HTTPException(500, "Internal error confirming duty")

    points = confirmation.points_earned
    messages = {
        2: {"en": "On time! 2 points earned.", "ar": "في الوقت! حصلت على نقطتين."},
        1: {"en": "Slightly late. 1 point earned.", "ar": "تأخر طفيف. حصلت على نقطة واحدة."},
        0: {"en": "Too late. 0 points.", "ar": "فات الأوان. 0 نقاط."},
    }
    msg = messages.get(points, messages[0])

    return {
        "assignment_id": data.assignment_id,
        "teacher_id":    teacher_id,
        "points_earned": points,
        "message_en":    msg["en"],
        "message_ar":    msg["ar"],
    }


@router.get("/teachers/{teacher_id}/monthly")
def get_monthly_points(
    teacher_id: int,
    year: int,
    month: int,
    db: Session = Depends(get_db),
):
    """Monthly total and per-duty confirmation breakdown for a teacher."""
    total = get_teacher_monthly_points(db, teacher_id, year, month)
    details = get_teacher_confirmation_detail(db, teacher_id, year, month)
    return {
        "teacher_id":    teacher_id,
        "year":          year,
        "month":         month,
        "total_points":  total,
        "confirmations": details,
    }


@router.post("/rebuild")
def rebuild_points_cache(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """Admin: rebuild the monthly points summary cache for all active teachers."""
    rebuild_monthly_summary_for_all(db, year, month)
    return {"status": "rebuilt", "year": year, "month": month}