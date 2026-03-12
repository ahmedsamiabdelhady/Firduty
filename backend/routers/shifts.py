"""Shift CRUD endpoints."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.models import Shift
from schemas.schemas import ShiftCreate, ShiftUpdate, ShiftOut
from routers.auth import get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/shifts", tags=["shifts"])

_VALID_DUTY_TYPES = {"morning_endofday", "break"}


@router.get("/", response_model=List[ShiftOut])
def list_shifts(db: Session = Depends(get_db)) -> List[ShiftOut]:
    """Return all shifts ordered by display order then id (public)."""
    rows = db.query(Shift).order_by(Shift.order, Shift.id).all()
    logger.debug("list_shifts → %d rows", len(rows))
    return rows


@router.post("/", response_model=ShiftOut)
def create_shift(
    data: ShiftCreate,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> ShiftOut:
    if data.duty_type not in _VALID_DUTY_TYPES:
        raise HTTPException(
            422,
            f"duty_type must be one of: {sorted(_VALID_DUTY_TYPES)}"
        )
    payload = data.model_dump() if hasattr(data, "model_dump") else data.dict()
    shift = Shift(**payload)
    db.add(shift)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("create_shift DB error")
        raise HTTPException(500, f"Database error: {exc}") from exc
    db.refresh(shift)
    return shift


@router.put("/{shift_id}", response_model=ShiftOut)
def update_shift(
    shift_id: int,
    data: ShiftUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> ShiftOut:
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(404, "Shift not found")
    payload = (
        data.model_dump(exclude_none=True)
        if hasattr(data, "model_dump")
        else data.dict(exclude_none=True)
    )
    if "duty_type" in payload and payload["duty_type"] not in _VALID_DUTY_TYPES:
        raise HTTPException(
            422,
            f"duty_type must be one of: {sorted(_VALID_DUTY_TYPES)}"
        )
    for field, value in payload.items():
        setattr(shift, field, value)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("update_shift DB error for id=%d", shift_id)
        raise HTTPException(500, f"Database error: {exc}") from exc
    db.refresh(shift)
    return shift


@router.delete("/{shift_id}")
def delete_shift(
    shift_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict:
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(404, "Shift not found")
    db.delete(shift)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("delete_shift DB error for id=%d", shift_id)
        raise HTTPException(500, f"Database error: {exc}") from exc
    return {"status": "deleted", "id": shift_id}