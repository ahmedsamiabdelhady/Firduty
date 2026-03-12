"""Location CRUD endpoints."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.models import Location
from schemas.schemas import LocationCreate, LocationUpdate, LocationOut
from routers.auth import get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/", response_model=List[LocationOut])
def list_locations(db: Session = Depends(get_db)) -> List[LocationOut]:
    """Return all locations ordered by display order then id (public)."""
    rows = db.query(Location).order_by(Location.order, Location.id).all()
    logger.debug("list_locations → %d rows", len(rows))
    return rows


@router.post("/", response_model=LocationOut)
def create_location(
    data: LocationCreate,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> LocationOut:
    payload = data.model_dump() if hasattr(data, "model_dump") else data.dict()
    location = Location(**payload)
    db.add(location)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("create_location DB error")
        raise HTTPException(500, f"Database error: {exc}") from exc
    db.refresh(location)
    return location


@router.put("/{location_id}", response_model=LocationOut)
def update_location(
    location_id: int,
    data: LocationUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> LocationOut:
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(404, "Location not found")
    payload = (
        data.model_dump(exclude_none=True)
        if hasattr(data, "model_dump")
        else data.dict(exclude_none=True)
    )
    for field, value in payload.items():
        setattr(location, field, value)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("update_location DB error for id=%d", location_id)
        raise HTTPException(500, f"Database error: {exc}") from exc
    db.refresh(location)
    return location


@router.delete("/{location_id}")
def delete_location(
    location_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict:
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(404, "Location not found")
    db.delete(location)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("delete_location DB error for id=%d", location_id)
        raise HTTPException(500, f"Database error: {exc}") from exc
    return {"status": "deleted", "id": location_id}