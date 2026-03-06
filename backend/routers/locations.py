"""Location CRUD endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.models import Location
from schemas.schemas import LocationCreate, LocationUpdate, LocationOut
from routers.auth import get_current_admin

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/", response_model=List[LocationOut])
def list_locations(db: Session = Depends(get_db)):
    return db.query(Location).order_by(Location.order, Location.id).all()


@router.post("/", response_model=LocationOut)
def create_location(data: LocationCreate, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    loc = Location(**data.model_dump())
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


@router.put("/{location_id}", response_model=LocationOut)
def update_location(location_id: int, data: LocationUpdate, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(404, "Location not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(loc, field, value)
    db.commit()
    db.refresh(loc)
    return loc


@router.delete("/{location_id}")
def delete_location(location_id: int, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(404, "Location not found")
    db.delete(loc)
    db.commit()
    return {"status": "deleted"}