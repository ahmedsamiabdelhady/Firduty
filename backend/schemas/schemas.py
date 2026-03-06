"""Pydantic schemas for request/response validation."""

from datetime import date, time, datetime
from typing import Optional, List
from pydantic import BaseModel


# ─── Auth ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ─── App Settings ─────────────────────────────────────────────────────────────

class AppSettingOut(BaseModel):
    key: str
    value: str
    class Config:
        from_attributes = True

class AppSettingUpdate(BaseModel):
    value: str


# ─── Teacher ──────────────────────────────────────────────────────────────────

class TeacherCreate(BaseModel):
    name: str
    active: bool = True
    preferred_language: str = "ar"

class TeacherUpdate(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None
    preferred_language: Optional[str] = None

class TeacherOut(BaseModel):
    id: int
    name: str
    active: bool
    preferred_language: str
    created_at: datetime
    class Config:
        from_attributes = True


# ─── Device Token ─────────────────────────────────────────────────────────────

class DeviceTokenCreate(BaseModel):
    token: str
    platform: str  # 'android' | 'ios'


# ─── Location ─────────────────────────────────────────────────────────────────

class LocationCreate(BaseModel):
    name_en: str
    name_ar: str
    order: int = 0

class LocationUpdate(BaseModel):
    name_en: Optional[str] = None
    name_ar: Optional[str] = None
    order: Optional[int] = None

class LocationOut(BaseModel):
    id: int
    name_en: str
    name_ar: str
    order: int
    class Config:
        from_attributes = True


# ─── Shift ────────────────────────────────────────────────────────────────────

class ShiftCreate(BaseModel):
    name_en: str
    name_ar: str
    start_time: time
    end_time: time
    order: int = 0

class ShiftUpdate(BaseModel):
    name_en: Optional[str] = None
    name_ar: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    order: Optional[int] = None

class ShiftOut(BaseModel):
    id: int
    name_en: str
    name_ar: str
    start_time: time
    end_time: time
    order: int
    class Config:
        from_attributes = True


# ─── Nested Week Plan ─────────────────────────────────────────────────────────

class AssignmentOut(BaseModel):
    id: int
    slot_index: int
    teacher_id: Optional[int]
    teacher_name: Optional[str] = None
    class Config:
        from_attributes = True

class ShiftLocationOut(BaseModel):
    id: int
    shift_id: int
    location_id: int
    slots_count: int
    order: int
    shift: ShiftOut
    location: LocationOut
    assignments: List[AssignmentOut] = []
    class Config:
        from_attributes = True

class DayPlanOut(BaseModel):
    id: int
    date: date
    shift_locations: List[ShiftLocationOut] = []
    class Config:
        from_attributes = True

class WeekPlanOut(BaseModel):
    id: int
    week_start_date: date
    status: str
    version: int
    cloned_from_week_start: Optional[date]
    created_at: datetime
    updated_at: datetime
    day_plans: List[DayPlanOut] = []
    class Config:
        from_attributes = True


# ─── Week Plan Mutations ──────────────────────────────────────────────────────

class ShiftLocationUpdate(BaseModel):
    """Update slots_count for a shift+location within a day."""
    day_date: date
    shift_id: int
    location_id: int
    slots_count: int

class AssignmentUpdate(BaseModel):
    """Assign/unassign a teacher to a specific slot."""
    shift_location_id: int
    slot_index: int
    teacher_id: Optional[int]  # None = clear slot

class WeekStatusUpdate(BaseModel):
    status: str  # 'draft' | 'published'


# ─── Teacher Schedule ─────────────────────────────────────────────────────────

class TeacherDutySlot(BaseModel):
    date: date
    shift_name_en: str
    shift_name_ar: str
    shift_start: time
    shift_end: time
    location_name_en: str
    location_name_ar: str

class TeacherScheduleResponse(BaseModel):
    teacher_id: int
    teacher_name: str
    duties: List[TeacherDutySlot]