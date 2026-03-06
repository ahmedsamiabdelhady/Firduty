"""
SQLAlchemy ORM models for Firduty.
Includes: Teacher, DeviceToken, Location, Shift, WeekPlan, DayPlan,
          ShiftLocation, Assignment, ChangeLog, AppSetting,
          DutyConfirmation, MonthlyPointsSummary (points system).
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Time,
    ForeignKey, Text, Enum as SAEnum, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from database import Base


class AppSetting(Base):
    """Stores global application settings (e.g. default admin language)."""
    __tablename__ = "app_settings"

    id         = Column(Integer, primary_key=True, index=True)
    key        = Column(String(100), unique=True, nullable=False)
    value      = Column(String(255), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Teacher(Base):
    """Represents a school teacher who can be assigned duties."""
    __tablename__ = "teachers"

    id                 = Column(Integer, primary_key=True, index=True)
    name               = Column(String(200), nullable=False)
    active             = Column(Boolean, default=True, nullable=False)
    preferred_language = Column(String(2), default="ar", nullable=False)  # 'ar' | 'en'
    created_at         = Column(DateTime, default=datetime.utcnow)

    # Relationships
    device_tokens     = relationship("DeviceToken",           back_populates="teacher", cascade="all, delete-orphan")
    assignments       = relationship("Assignment",            back_populates="teacher")
    confirmations     = relationship("DutyConfirmation",      back_populates="teacher", cascade="all, delete-orphan")
    monthly_summaries = relationship("MonthlyPointsSummary",  back_populates="teacher", cascade="all, delete-orphan")


class DeviceToken(Base):
    """FCM device tokens for push notifications."""
    __tablename__ = "device_tokens"

    id         = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    token      = Column(String(500), nullable=False, unique=True)
    platform   = Column(String(10), nullable=False)   # 'android' | 'ios'
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    teacher = relationship("Teacher", back_populates="device_tokens")


class Location(Base):
    """A physical location/post where a duty can take place."""
    __tablename__ = "locations"

    id      = Column(Integer, primary_key=True, index=True)
    name_en = Column(String(200), nullable=False)
    name_ar = Column(String(200), nullable=False)
    order   = Column(Integer, default=0)

    shift_locations = relationship("ShiftLocation", back_populates="location")


class Shift(Base):
    """A time period during the school day (e.g. Morning, Midday)."""
    __tablename__ = "shifts"

    id         = Column(Integer, primary_key=True, index=True)
    name_en    = Column(String(200), nullable=False)
    name_ar    = Column(String(200), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time   = Column(Time, nullable=False)
    order      = Column(Integer, default=0)

    shift_locations = relationship("ShiftLocation", back_populates="shift")


class WeekPlan(Base):
    """A weekly duty plan with a status (draft/published)."""
    __tablename__ = "week_plans"

    id                    = Column(Integer, primary_key=True, index=True)
    week_start_date       = Column(Date, nullable=False, unique=True)  # Always a Sunday
    status                = Column(SAEnum("draft", "published", name="week_status"), default="draft", nullable=False)
    version               = Column(Integer, default=1)
    cloned_from_week_start = Column(Date, nullable=True)
    created_at            = Column(DateTime, default=datetime.utcnow)
    updated_at            = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    day_plans   = relationship("DayPlan",    back_populates="week_plan",  cascade="all, delete-orphan", order_by="DayPlan.date")
    change_logs = relationship("ChangeLog",  back_populates="week_plan",  cascade="all, delete-orphan")


class DayPlan(Base):
    """Represents a single working day within a WeekPlan."""
    __tablename__ = "day_plans"

    id           = Column(Integer, primary_key=True, index=True)
    week_plan_id = Column(Integer, ForeignKey("week_plans.id"), nullable=False)
    date         = Column(Date, nullable=False)

    week_plan       = relationship("WeekPlan",       back_populates="day_plans")
    shift_locations = relationship("ShiftLocation",  back_populates="day_plan", cascade="all, delete-orphan")


class ShiftLocation(Base):
    """A shift+location combination within a day, with a configurable slot count."""
    __tablename__ = "shift_locations"

    id          = Column(Integer, primary_key=True, index=True)
    day_plan_id = Column(Integer, ForeignKey("day_plans.id"),  nullable=False)
    shift_id    = Column(Integer, ForeignKey("shifts.id"),     nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"),  nullable=False)
    slots_count = Column(Integer, default=1)
    order       = Column(Integer, default=0)

    day_plan    = relationship("DayPlan",    back_populates="shift_locations")
    shift       = relationship("Shift",      back_populates="shift_locations")
    location    = relationship("Location",   back_populates="shift_locations")
    assignments = relationship("Assignment", back_populates="shift_location",
                                cascade="all, delete-orphan", order_by="Assignment.slot_index")


class Assignment(Base):
    """A single duty slot assigned (optionally) to a teacher."""
    __tablename__ = "assignments"

    id                = Column(Integer, primary_key=True, index=True)
    shift_location_id = Column(Integer, ForeignKey("shift_locations.id"), nullable=False)
    slot_index        = Column(Integer, nullable=False)   # 0-based index
    teacher_id        = Column(Integer, ForeignKey("teachers.id"), nullable=True)  # NULL = empty

    shift_location = relationship("ShiftLocation",   back_populates="assignments")
    teacher        = relationship("Teacher",          back_populates="assignments")
    confirmation   = relationship("DutyConfirmation", back_populates="assignment",
                                   uselist=False, cascade="all, delete-orphan")


class ChangeLog(Base):
    """Audit log for week plan changes."""
    __tablename__ = "change_logs"

    id           = Column(Integer, primary_key=True, index=True)
    week_plan_id = Column(Integer, ForeignKey("week_plans.id"), nullable=False)
    actor        = Column(String(100), nullable=False)
    action       = Column(String(100), nullable=False)
    payload_json = Column(Text, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    week_plan = relationship("WeekPlan", back_populates="change_logs")


# ─── Points System ────────────────────────────────────────────────────────────

class DutyConfirmation(Base):
    """
    Records when a teacher confirms their presence at a duty location.

    Scoring rules (vs shift start_time in Asia/Muscat TZ):
      confirmed_at <= start_time          → 2 points  (on time / early)
      start_time < confirmed_at <= +5min  → 1 point   (grace window)
      confirmed_at > start_time + 5 min   → 0 points  (too late)
    """
    __tablename__ = "duty_confirmations"

    id            = Column(Integer, primary_key=True, index=True)
    teacher_id    = Column(Integer, ForeignKey("teachers.id"),    nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    confirmed_at  = Column(DateTime, nullable=False, default=datetime.utcnow)  # stored as UTC
    points_earned = Column(Integer, nullable=False, default=0)  # 0, 1, or 2

    __table_args__ = (
        UniqueConstraint("teacher_id", "assignment_id", name="uq_confirmation"),
        Index("ix_conf_teacher_month", "teacher_id", "confirmed_at"),
    )

    teacher    = relationship("Teacher",    back_populates="confirmations")
    assignment = relationship("Assignment", back_populates="confirmation")


class MonthlyPointsSummary(Base):
    """
    Cached monthly aggregation of earned points per teacher.
    Rebuilt by the monthly cron job and updated after each confirmation.
    """
    __tablename__ = "monthly_points_summary"

    id           = Column(Integer, primary_key=True, index=True)
    teacher_id   = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    year         = Column(Integer, nullable=False)
    month        = Column(Integer, nullable=False)   # 1–12
    total_points = Column(Integer, nullable=False, default=0)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("teacher_id", "year", "month", name="uq_monthly_summary"),
        Index("ix_monthly_year_month", "year", "month"),
    )

    teacher = relationship("Teacher", back_populates="monthly_summaries")