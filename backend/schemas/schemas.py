"""
Pydantic schemas for request/response validation.

Compatibility notes
───────────────────
All ORM-backed response models inherit from _OrmBase.
_OrmBase sets both:
  from_attributes = True   ← Pydantic v2
  orm_mode        = True   ← Pydantic v1 (alias; harmless in v2)

This ensures the codebase works regardless of which Pydantic major
version Koyeb resolves at deploy time.

List response types use typing.List[X] (not list[X]) so the code
runs on Python 3.8 as well as 3.9+.
"""

from datetime import date, time, datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr


# ─── Shared ORM base ──────────────────────────────────────────────────────────

class _OrmBase(BaseModel):
    """Base class for all schemas that are populated from SQLAlchemy ORM objects."""
    class Config:
        from_attributes = True   # Pydantic v2
        from_attributes = True   # Pydantic v2


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminIdentity(BaseModel):
    username: str
    role: str = "admin"
    expires_at: Optional[int] = None   # Unix timestamp from JWT 'exp' claim


# ─── App Settings ─────────────────────────────────────────────────────────────

class AppSettingOut(_OrmBase):
    key: str
    value: str


class AppSettingUpdate(BaseModel):
    value: str


# ─── Teacher ──────────────────────────────────────────────────────────────────

class TeacherRegister(BaseModel):
    """Public self-registration payload. Creates a 'pending' teacher record."""
    name: str
    email: EmailStr


class TeacherCreate(BaseModel):
    """Admin-only: create a teacher directly (defaults to approved + active)."""
    name: str
    active: bool = True
    preferred_language: str = "ar"
    email: Optional[str] = None
    status: str = "approved"


class TeacherUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    active: Optional[bool] = None
    preferred_language: Optional[str] = None


class TeacherStatusOut(_OrmBase):
    """Lightweight status check — used by the Flutter app on every launch."""
    id: int
    name: str
    status: str   # 'pending' | 'approved'


class TeacherOut(_OrmBase):
    id: int
    name: str
    email: Optional[str] = None
    status: str
    active: bool
    preferred_language: str
    created_at: datetime


# ─── Device Token ─────────────────────────────────────────────────────────────

class DeviceTokenCreate(BaseModel):
    """
    Register a push notification token for a teacher.

    platform = 'android'
        FCM registration token from FirebaseMessaging.getToken() on Android.

    platform = 'web'
        FCM web registration token from FirebaseMessaging.getToken(vapidKey=…)
        in the Flutter Web app. Firebase delivers this via Web Push (VAPID)
        to the browser's service worker. Works on iOS Safari 16.4+ PWA.
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


class LocationOut(_OrmBase):
    id: int
    name_en: str
    name_ar: str
    order: int = 0   # default=0: guards against legacy NULL rows in DB


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


class ShiftOut(_OrmBase):
    id: int
    name_en: str
    name_ar: str
    start_time: time
    end_time: time
    order: int = 0   # default=0: guards against legacy NULL rows in DB
    duty_type: str


# ─── Nested Week Plan ─────────────────────────────────────────────────────────

class AssignmentOut(_OrmBase):
    id: int
    slot_index: int
    teacher_id: Optional[int] = None
    teacher_name: Optional[str] = None
    grade_class: Optional[str] = None


class ShiftLocationOut(_OrmBase):
    id: int
    shift_id: int
    location_id: Optional[int] = None
    slots_count: int = 1
    order: int = 0   # default=0: guards against legacy NULL rows
    shift: ShiftOut
    location: Optional[LocationOut] = None
    assignments: List[AssignmentOut] = []


class DayPlanOut(_OrmBase):
    id: int
    date: date
    shift_locations: List[ShiftLocationOut] = []


class WeekPlanOut(_OrmBase):
    id: int
    week_start_date: date
    status: str
    version: int
    cloned_from_week_start: Optional[date] = None
    created_at: datetime
    updated_at: datetime
    day_plans: List[DayPlanOut] = []


# ─── Week Plan Mutations ──────────────────────────────────────────────────────

class ShiftLocationUpdate(BaseModel):
    day_date: date
    shift_id: int
    location_id: Optional[int] = None
    slots_count: int


class AssignmentUpdate(BaseModel):
    shift_location_id: int
    slot_index: int
    teacher_id: Optional[int] = None
    grade_class: Optional[str] = None


class WeekStatusUpdate(BaseModel):
    status: str   # 'draft' | 'published'


class ShiftTimeUpdate(BaseModel):
    shift_id: int
    start_time: time
    end_time: time


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


# ─── Points ───────────────────────────────────────────────────────────────────

class ConfirmDutyRequest(BaseModel):
    assignment_id: int