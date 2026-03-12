"""Pydantic schemas for request/response validation."""

from datetime import date, time, datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr


# ─── Auth ─────────────────────────────────────────────────────────────────────

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

class TeacherRegister(BaseModel):
    """Public self-registration payload. Creates a 'pending' teacher record."""
    name: str
    email: EmailStr

class TeacherCreate(BaseModel):
    """Admin-only: create a teacher directly (defaults to approved)."""
    name: str
    active: bool = True
    preferred_language: str = "ar"
    email: Optional[str] = None
    status: str = "approved"

class TeacherUpdate(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None
    preferred_language: Optional[str] = None

class TeacherStatusOut(BaseModel):
    """Lightweight response for the Flutter status-check endpoint."""
    id: int
    name: str
    status: str   # 'pending' | 'approved'
    class Config:
        from_attributes = True

class TeacherOut(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    status: str
    active: bool
    preferred_language: str
    created_at: datetime
    class Config:
        from_attributes = True


# ─── Device Token ─────────────────────────────────────────────────────────────

class DeviceTokenCreate(BaseModel):
    """
    Register a push notification token for a teacher.

    platform = 'android'
        token = FCM registration token from FirebaseMessaging.getToken() on Android

    platform = 'web'
        token = FCM web registration token from FirebaseMessaging.getToken(vapidKey=...)
                in the Flutter Web app. Firebase delivers this via Web Push to the
                browser's service worker (supports iOS Safari 16.4+).
    """
    token: str
    platform: str   # 'android' | 'web'


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
    duty_type: str = "morning_endofday"

class ShiftUpdate(BaseModel):
    name_en: Optional[str] = None
    name_ar: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    order: Optional[int] = None
    duty_type: Optional[str] = None

class ShiftOut(BaseModel):
    id: int
    name_en: str
    name_ar: str
    start_time: time
    end_time: time
    order: int
    duty_type: str
    class Config:
        from_attributes = True


# ─── Nested Week Plan ─────────────────────────────────────────────────────────

class AssignmentOut(BaseModel):
    id: int
    slot_index: int
    teacher_id: Optional[int]
    teacher_name: Optional[str] = None
    grade_class: Optional[str] = None
    class Config:
        from_attributes = True

class ShiftLocationOut(BaseModel):
    id: int
    shift_id: int
    location_id: Optional[int]
    slots_count: int
    order: int
    shift: ShiftOut
    location: Optional[LocationOut]
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
    day_date: date
    shift_id: int
    location_id: Optional[int] = None
    slots_count: int

class AssignmentUpdate(BaseModel):
    shift_location_id: int
    slot_index: int
    teacher_id: Optional[int]
    grade_class: Optional[str] = None

class WeekStatusUpdate(BaseModel):
    status: str   # 'draft' | 'published'


# ─── Teacher Schedule ─────────────────────────────────────────────────────────

class TeacherDutySlot(BaseModel):
    date: date
    shift_name_en: str
    shift_name_ar: str
    shift_start: time
    shift_end: time
    duty_type: str
    location_name_en: Optional[str] = None
    location_name_ar: Optional[str] = None
    grade_class: Optional[str] = None

class TeacherScheduleResponse(BaseModel):
    teacher_id: int
    teacher_name: str
    duties: List[TeacherDutySlot]