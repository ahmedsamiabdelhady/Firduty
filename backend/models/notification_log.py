"""
models/notification_log.py — Notification deduplication log.

Tracks every push notification sent so the scheduler never fires twice
for the same teacher + assignment + notification type.

Schema is additive — existing tables are unaffected.
Add this model to your Alembic env or run the Supabase SQL below.

SQL (idempotent — safe to run multiple times):
─────────────────────────────────────────────
  CREATE TABLE IF NOT EXISTS notification_logs (
      id                SERIAL PRIMARY KEY,
      teacher_id        INTEGER NOT NULL REFERENCES teachers(id)    ON DELETE CASCADE,
      assignment_id     INTEGER NOT NULL REFERENCES assignments(id)  ON DELETE CASCADE,
      notification_type VARCHAR(30)  NOT NULL,   -- 'reminder_15m' | 'duty_started' | 'duty_updated'
      sent_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
      status            VARCHAR(10)  NOT NULL DEFAULT 'sent',       -- 'sent' | 'skipped' | 'failed'
      CONSTRAINT uq_notif_teacher_assignment_type
          UNIQUE (teacher_id, assignment_id, notification_type)
  );
  CREATE INDEX IF NOT EXISTS ix_notif_teacher_id ON notification_logs (teacher_id);
  CREATE INDEX IF NOT EXISTS ix_notif_sent_at    ON notification_logs (sent_at);
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class NotificationLog(Base):
    """
    One row per (teacher_id, assignment_id, notification_type).

    The UNIQUE constraint is the deduplication key.
    The scheduler uses INSERT … ON CONFLICT DO NOTHING so it's idempotent
    even if called multiple times within the same minute window.
    """
    __tablename__ = "notification_logs"
    __table_args__ = (
        UniqueConstraint(
            "teacher_id", "assignment_id", "notification_type",
            name="uq_notif_teacher_assignment_type",
        ),
        Index("ix_notif_teacher_id", "teacher_id"),
        Index("ix_notif_sent_at",    "sent_at"),
    )

    id                = Column(Integer, primary_key=True, index=True)
    teacher_id        = Column(
        Integer, ForeignKey("teachers.id",    ondelete="CASCADE"), nullable=False,
    )
    assignment_id     = Column(
        Integer, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False,
    )
    notification_type = Column(String(30), nullable=False)
    sent_at           = Column(DateTime, nullable=False, default=_utcnow)
    status            = Column(String(10), nullable=False, default="sent")

    teacher    = relationship("Teacher",    foreign_keys=[teacher_id])
    assignment = relationship("Assignment", foreign_keys=[assignment_id])
