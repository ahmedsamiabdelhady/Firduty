# ──────────────────────────────────────────────────────────────────────────────
# PATCH: Replace the DeviceToken class in backend/models/models.py
#
# Old class (4 data columns):
#   id, teacher_id, token, platform, updated_at
#
# New class (adds installation_id + UniqueConstraint):
#   id, teacher_id, token, platform, installation_id, updated_at
# ──────────────────────────────────────────────────────────────────────────────
#
# 1. Make sure UniqueConstraint is in your models.py imports, e.g.:
#    from sqlalchemy import Column, Integer, String, Boolean, DateTime, \
#                          ForeignKey, Time, Date, Text, Enum as SAEnum, \
#                          UniqueConstraint
#
# 2. Replace the old DeviceToken class with this one:

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

    installation_id
        A stable UUID generated once per device/browser and stored in
        SharedPreferences (mobile) or localStorage (web).
        UNIQUE(teacher_id, installation_id) ensures that when FCM rotates a
        token for the same physical device, the existing row is UPDATED rather
        than a new row being inserted — which would cause duplicate notifications.
        Nullable for backward compatibility with older app versions that do not
        send installation_id. When NULL, PostgreSQL's unique constraint allows
        multiple NULL rows (NULL ≠ NULL), so legacy clients continue to work.
    """
    __tablename__ = "device_tokens"
    __table_args__ = (
        # Core deduplication constraint.
        # When a device re-registers with a new FCM token (token rotation),
        # the backend UPSERTs on this key: same teacher + same installation
        # → UPDATE token, not INSERT new row.
        UniqueConstraint(
            "teacher_id", "installation_id",
            name="uq_device_token_teacher_installation",
        ),
    )
    id              = Column(Integer, primary_key=True, index=True)
    teacher_id      = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    token           = Column(String(500), nullable=False, unique=True)
    platform        = Column(String(10),  nullable=False)   # 'android' | 'web'
    installation_id = Column(String(100), nullable=True,  index=True)
    updated_at      = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    teacher         = relationship("Teacher", back_populates="device_tokens")
