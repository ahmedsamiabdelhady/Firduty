"""
SQLAlchemy ORM models for Firduty.

Column nullable rules
─────────────────────
  nullable=False + server_default  → column is NOT NULL in DB; any INSERT that
                                     omits the field still gets the default value.
                                     This is important for ALTER TABLE migrations:
                                     adding a NOT NULL column to a table with
                                     existing rows requires a DEFAULT.

  nullable=True  (or omitted)      → column is NULL-able in DB; schema fields for
                                     these columns should use Optional[...].

Duty types (Shift.duty_type):
  'morning_endofday' → teacher needs a location
  'break'            → teacher needs a grade/class

Teacher registration status (Teacher.status):
  'pending'  → self-registered, awaiting admin approval
  'approved' → admin-approved, can access the duty system

DeviceToken.platform values:
  'android' → FCM registration token (native Android)
  'web'     → FCM web registration token (Flutter Web / iOS PWA via Firebase JS SDK)
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Time, Text,
    ForeignKey, Enum as SAEnum, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from database import Base


def _utcnow() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─── App Settings ─────────────────────────────────────────────────────────────

class AppSetting(Base):
    __tablename__ = "app_settings"
    id         = Column(Integer, primary_key=True, index=True)
    key        = Column(String(100), unique=True, nullable=False)
    value      = Column(String(255), nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# ─── Teacher ──────────────────────────────────────────────────────────────────

class Teacher(Base):
    __tablename__ = "teachers"
    id                 = Column(Integer, primary_key=True, index=True)
    name               = Column(String(200), nullable=False)
    #
    # email: nullable — legacy records created by admin may not have an email.
    # Added in migration 002. Production ALT: see migrations/002_teacher_registration.sql
    #
    email              = Column(String(255), unique=True, nullable=True, index=True)
    #
    # status: NOT NULL with server_default ensures any INSERT that omits status
    # (e.g. admin-created teachers from before migration 002) still gets 'approved'.
    # Production ALT: see migrations/002_teacher_registration.sql
    #
    status             = Column(
        SAEnum("pending", "approved", name="teacher_status_enum"),
        nullable=False,
        default="approved",
        server_default="approved",
    )
    active             = Column(Boolean, default=True, nullable=False, server_default="true")
    preferred_language = Column(String(2), default="ar", nullable=False, server_default="ar")
    created_at         = Column(DateTime, default=_utcnow)

    device_tokens     = relationship("DeviceToken",          back_populates="teacher", cascade="all, delete-orphan")
    assignments       = relationship("Assignment",           back_populates="teacher")
    confirmations     = relationship("DutyConfirmation",     back_populates="teacher", cascade="all, delete-orphan")
    monthly_summaries = relationship("MonthlyPointsSummary", back_populates="teacher", cascade="all, delete-orphan")


# ─── Device Token ─────────────────────────────────────────────────────────────

class DeviceToken(Base):
    """
    Push notification tokens for a teacher.

    platform = 'android'
        token = FCM registration token (standard string)

    platform = 'web'
        token = FCM web registration token obtained via
                firebase_messaging.getToken(vapidKey=…) in the Flutter Web app.
                Firebase delivers this via Web Push (VAPID) to the browser's
                service worker (iOS Safari 16.4+ supported).
    """
    __tablename__ = "device_tokens"
    id         = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    token      = Column(String(500), nullable=False, unique=True)
    platform   = Column(String(10), nullable=False)   # 'android' | 'web'
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    teacher    = relationship("Teacher", back_populates="device_tokens")


# ─── Location ─────────────────────────────────────────────────────────────────

class Location(Base):
    __tablename__ = "locations"
    id      = Column(Integer, primary_key=True, index=True)
    name_en = Column(String(200), nullable=False)
    name_ar = Column(String(200), nullable=False)
    #
    # order: NOT NULL with server_default so schema response (order: int)
    # never receives NULL from the DB — prevents Pydantic validation errors
    # on existing rows that pre-date this constraint.
    #
    order   = Column(Integer, default=0, nullable=False, server_default="0")
    shift_locations = relationship("ShiftLocation", back_populates="location")


# ─── Shift ────────────────────────────────────────────────────────────────────

class Shift(Base):
    """
    A duty time period.
    duty_type controls display logic in the Flutter app:
      'morning_endofday' → show location to teacher
      'break'            → show grade/class to teacher
    """
    __tablename__ = "shifts"
    id         = Column(Integer, primary_key=True, index=True)
    name_en    = Column(String(200), nullable=False)
    name_ar    = Column(String(200), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time   = Column(Time, nullable=False)
    order      = Column(Integer, default=0, nullable=False, server_default="0")
    duty_type  = Column(
        SAEnum("morning_endofday", "break", name="duty_type_enum"),
        nullable=False,
        default="morning_endofday",
        server_default="morning_endofday",
    )
    shift_locations = relationship("ShiftLocation", back_populates="shift")


# ─── Week Planning ────────────────────────────────────────────────────────────

class WeekPlan(Base):
    __tablename__ = "week_plans"
    id                     = Column(Integer, primary_key=True, index=True)
    week_start_date        = Column(Date, nullable=False, unique=True)
    status                 = Column(
        SAEnum("draft", "published", name="week_status"),
        default="draft",
        nullable=False,
        server_default="draft",
    )
    version                = Column(Integer, default=1, nullable=False, server_default="1")
    cloned_from_week_start = Column(Date, nullable=True)
    created_at             = Column(DateTime, default=_utcnow)
    updated_at             = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    day_plans   = relationship(
        "DayPlan",
        back_populates="week_plan",
        cascade="all, delete-orphan",
        order_by="DayPlan.date"
    )
    change_logs = relationship(
        "ChangeLog",
        back_populates="week_plan",
        cascade="all, delete-orphan"
    )


class DayPlan(Base):
    __tablename__ = "day_plans"
    id           = Column(Integer, primary_key=True, index=True)
    week_plan_id = Column(Integer, ForeignKey("week_plans.id"), nullable=False)
    date         = Column(Date, nullable=False)
    is_published = Column(Boolean, default=False, nullable=False, server_default="false")

    week_plan       = relationship("WeekPlan",      back_populates="day_plans")
    shift_locations = relationship(
        "ShiftLocation",
        back_populates="day_plan",
        cascade="all, delete-orphan"
    )

class ShiftLocation(Base):
    __tablename__ = "shift_locations"
    id          = Column(Integer, primary_key=True, index=True)
    day_plan_id = Column(Integer, ForeignKey("day_plans.id"),  nullable=False)
    shift_id    = Column(Integer, ForeignKey("shifts.id"),     nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"),  nullable=True)  # NULL for break duties
    slots_count = Column(Integer, default=1, nullable=False, server_default="1")
    order       = Column(Integer, default=0, nullable=False, server_default="0")
    day_plan    = relationship("DayPlan",    back_populates="shift_locations")
    shift       = relationship("Shift",      back_populates="shift_locations")
    location    = relationship("Location",   back_populates="shift_locations")
    assignments = relationship("Assignment", back_populates="shift_location",
                               cascade="all, delete-orphan", order_by="Assignment.slot_index")


class Assignment(Base):
    __tablename__ = "assignments"
    id                = Column(Integer, primary_key=True, index=True)
    shift_location_id = Column(Integer, ForeignKey("shift_locations.id"), nullable=False)
    slot_index        = Column(Integer, nullable=False)
    teacher_id        = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    grade_class       = Column(String(100), nullable=True)
    shift_location = relationship("ShiftLocation",   back_populates="assignments")
    teacher        = relationship("Teacher",          back_populates="assignments")
    confirmation   = relationship("DutyConfirmation", back_populates="assignment",
                                   uselist=False, cascade="all, delete-orphan")


class ChangeLog(Base):
    __tablename__ = "change_logs"
    id           = Column(Integer, primary_key=True, index=True)
    week_plan_id = Column(Integer, ForeignKey("week_plans.id"), nullable=False)
    actor        = Column(String(100), nullable=False)
    action       = Column(String(100), nullable=False)
    payload_json = Column(Text, nullable=True)
    created_at   = Column(DateTime, default=_utcnow)
    week_plan    = relationship("WeekPlan", back_populates="change_logs")


# ─── Points System ────────────────────────────────────────────────────────────

class DutyConfirmation(Base):
    __tablename__ = "duty_confirmations"
    id            = Column(Integer, primary_key=True, index=True)
    teacher_id    = Column(Integer, ForeignKey("teachers.id"),    nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    confirmed_at  = Column(DateTime, nullable=False, default=_utcnow)
    points_earned = Column(Integer, nullable=False, default=0, server_default="0")
    __table_args__ = (
        UniqueConstraint("teacher_id", "assignment_id", name="uq_confirmation"),
        Index("ix_conf_teacher_month", "teacher_id", "confirmed_at"),
    )
    teacher    = relationship("Teacher",    back_populates="confirmations")
    assignment = relationship("Assignment", back_populates="confirmation")


class MonthlyPointsSummary(Base):
    __tablename__ = "monthly_points_summary"
    id           = Column(Integer, primary_key=True, index=True)
    teacher_id   = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    year         = Column(Integer, nullable=False)
    month        = Column(Integer, nullable=False)
    total_points = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at   = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    __table_args__ = (
        UniqueConstraint("teacher_id", "year", "month", name="uq_monthly_summary"),
        Index("ix_monthly_year_month", "year", "month"),
    )
    teacher = relationship("Teacher", back_populates="monthly_summaries")