"""
routers/points.py — Endpoints for duty confirmation and point retrieval.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.models import Assignment
from services.points_service import (
    confirm_duty,
    get_teacher_monthly_points,
    get_teacher_confirmation_detail,
)

router = APIRouter(prefix="/points", tags=["points"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ConfirmDutyRequest(BaseModel):
    assignment_id: int
    # Optional: allow passing a custom timestamp (for testing).
    # In production the server time is always used.
    confirmed_at_utc: Optional[datetime] = None


class ConfirmDutyResponse(BaseModel):
    confirmation_id: int
    assignment_id: int
    confirmed_at: datetime
    points_earned: int
    message_en: str
    message_ar: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/teachers/{teacher_id}/confirm", response_model=ConfirmDutyResponse)
def confirm_teacher_duty(
    teacher_id: int,
    body: ConfirmDutyRequest,
    db: Session = Depends(get_db),
):
    """
    Teacher confirms they are present at their duty location.
    Uses server UTC time unless confirmed_at_utc is provided (testing only).
    """
    try:
        confirmation = confirm_duty(
            db=db,
            teacher_id=teacher_id,
            assignment_id=body.assignment_id,
            confirmed_at_utc=body.confirmed_at_utc,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Human-readable result messages per points earned
    messages = {
        2: ("✅ On time! You earned 2 points.", "✅ في الوقت المحدد! حصلت على نقطتين."),
        1: ("⏱ Slightly late. You earned 1 point.", "⏱ تأخرت قليلاً. حصلت على نقطة واحدة."),
        0: ("❌ Too late. No points awarded.", "❌ تأخرت كثيراً. لم تحصل على نقاط."),
    }
    msg_en, msg_ar = messages.get(confirmation.points_earned, ("Confirmed.", "تم التأكيد."))

    return ConfirmDutyResponse(
        confirmation_id=confirmation.id,
        assignment_id=confirmation.assignment_id,
        confirmed_at=confirmation.confirmed_at,
        points_earned=confirmation.points_earned,
        message_en=msg_en,
        message_ar=msg_ar,
    )


@router.get("/teachers/{teacher_id}/monthly")
def get_teacher_points(
    teacher_id: int,
    year: int,
    month: int,
    db: Session = Depends(get_db),
):
    """Get a teacher's total points and per-duty breakdown for a given month."""
    total = get_teacher_monthly_points(db, teacher_id, year, month)
    details = get_teacher_confirmation_detail(db, teacher_id, year, month)
    return {
        "teacher_id": teacher_id,
        "year": year,
        "month": month,
        "total_points": total,
        "details": details,
    }