"""Shift CRUD endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.models import Shift
from schemas.schemas import ShiftCreate, ShiftUpdate, ShiftOut
from routers.auth import get_current_admin

router = APIRouter(prefix="/shifts", tags=["shifts"])


@router.get("/", response_model=List[ShiftOut])
def list_shifts(db: Session = Depends(get_db)):
    return db.query(Shift).order_by(Shift.order, Shift.id).all()


@router.post("/", response_model=ShiftOut)
def create_shift(data: ShiftCreate, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    shift = Shift(**data.model_dump())
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


@router.put("/{shift_id}", response_model=ShiftOut)
def update_shift(shift_id: int, data: ShiftUpdate, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(404, "Shift not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(shift, field, value)
    db.commit()
    db.refresh(shift)
    return shift


@router.delete("/{shift_id}")
def delete_shift(shift_id: int, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(404, "Shift not found")
    db.delete(shift)
    db.commit()
    return {"status": "deleted"}