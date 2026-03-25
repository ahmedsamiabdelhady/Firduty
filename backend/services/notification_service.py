from __future__ import annotations

import json
import logging
import os
from typing import Iterable, List, Tuple

import firebase_admin
from firebase_admin import credentials, messaging

from database import SessionLocal
from models.models import DeviceToken

logger = logging.getLogger("services.notification_service")


def _ensure_firebase_initialized() -> None:
    """Initialize Firebase Admin once, with clear logging for production."""
    if firebase_admin._apps:
        return

    creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON", "").strip()
    creds_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip()

    try:
        if creds_json:
            cred = credentials.Certificate(json.loads(creds_json))
            firebase_admin.initialize_app(cred)
            logger.info("[FCM] Firebase initialized from FIREBASE_CREDENTIALS_JSON")
            return

        if creds_path and os.path.exists(creds_path):
            cred = credentials.Certificate(creds_path)
            firebase_admin.initialize_app(cred)
            logger.info("[FCM] Firebase initialized from FIREBASE_CREDENTIALS_PATH=%s", creds_path)
            return

        firebase_admin.initialize_app()
        logger.info("[FCM] Firebase initialized with default application credentials")
    except Exception:
        logger.exception("[FCM] Firebase initialization failed")
        raise


_ensure_firebase_initialized()


def _safe_str_dict(data: dict | None) -> dict[str, str]:
    return {str(k): "" if v is None else str(v) for k, v in (data or {}).items()}


def _is_invalid_token_error(exc: Exception | None) -> bool:
    if exc is None:
        return False
    name = exc.__class__.__name__.lower()
    text = str(exc).lower()
    markers = (
        "unregistered",
        "registration token is not a valid fcm registration token",
        "requested entity was not found",
        "notregistered",
        "invalid registration token",
        "mismatchsenderid",
        "sender id mismatch",
    )
    return "unregistered" in name or "invalidargument" in name or any(m in text for m in markers)


def _split_tokens_by_platform(token_rows: Iterable[DeviceToken]) -> tuple[list[str], list[str]]:
    android: list[str] = []
    web: list[str] = []

    for row in token_rows:
        token = str(getattr(row, "token", "") or "").strip()
        if not token:
            continue

        platform = str(getattr(row, "platform", "") or "").strip().lower()
        if platform == "android":
            android.append(token)
        else:
            web.append(token)

    return android, web


def _fetch_teacher_tokens(teacher_id: int) -> list[DeviceToken]:
    db = SessionLocal()
    try:
        return (
            db.query(DeviceToken)
            .filter(DeviceToken.teacher_id == teacher_id)
            .order_by(DeviceToken.updated_at.desc(), DeviceToken.id.desc())
            .all()
        )
    finally:
        db.close()


def _fetch_token_rows(tokens: Iterable[str]) -> list[DeviceToken]:
    tokens = [str(t).strip() for t in tokens if str(t).strip()]
    if not tokens:
        return []

    db = SessionLocal()
    try:
        return db.query(DeviceToken).filter(DeviceToken.token.in_(tokens)).all()
    finally:
        db.close()


def _delete_invalid_tokens(invalid_tokens: Iterable[str]) -> int:
    invalid_tokens = [str(t).strip() for t in invalid_tokens if str(t).strip()]
    if not invalid_tokens:
        return 0

    db = SessionLocal()
    try:
        rows = db.query(DeviceToken).filter(DeviceToken.token.in_(invalid_tokens)).all()
        count = len(rows)
        for row in rows:
            db.delete(row)
        if count:
            db.commit()
            logger.warning("[FCM] Removed %s invalid token(s) from database", count)
        return count
    except Exception:
        db.rollback()
        logger.exception("[FCM] Failed deleting invalid tokens")
        return 0
    finally:
        db.close()


def _send_multicast(*, tokens: list[str], data: dict, include_notification: bool) -> tuple[int, list[str], int]:
    if not tokens:
        return 0, [], 0

    message_kwargs = {
        "data": _safe_str_dict(data),
        "tokens": tokens,
    }
    if include_notification:
        message_kwargs["notification"] = messaging.Notification(
            title=str(data.get("title", "Firduty") or "Firduty"),
            body=str(data.get("body", "") or ""),
        )

    message = messaging.MulticastMessage(**message_kwargs)
    response = messaging.send_each_for_multicast(message)

    invalid_tokens: list[str] = []
    failure_count = 0

    for index, item in enumerate(response.responses):
        if item.success:
            continue
        failure_count += 1
        if _is_invalid_token_error(item.exception):
            invalid_tokens.append(tokens[index])
        logger.warning(
            "[FCM] token send failed include_notification=%s token_index=%s error=%s",
            include_notification,
            index,
            item.exception,
        )

    return int(response.success_count or 0), invalid_tokens, failure_count


def _dispatch_token_rows(token_rows: list[DeviceToken], data: dict) -> Tuple[int, List[str]]:
    if not token_rows:
        logger.info("[FCM] No device tokens found")
        return 0, []

    android_tokens, web_tokens = _split_tokens_by_platform(token_rows)
    success_total = 0
    failure_total = 0
    invalid_tokens: list[str] = []

    if android_tokens:
        ok, invalid, failed = _send_multicast(
            tokens=android_tokens,
            data=data,
            include_notification=False,
        )
        success_total += ok
        failure_total += failed
        invalid_tokens.extend(invalid)
        logger.info(
            "[FCM] Android dispatch success=%s failures=%s tokens=%s",
            ok,
            failed,
            len(android_tokens),
        )

    if web_tokens:
        ok, invalid, failed = _send_multicast(
            tokens=web_tokens,
            data=data,
            include_notification=True,
        )
        success_total += ok
        failure_total += failed
        invalid_tokens.extend(invalid)
        logger.info(
            "[FCM] Web/PWA dispatch success=%s failures=%s tokens=%s",
            ok,
            failed,
            len(web_tokens),
        )

    removed = _delete_invalid_tokens(invalid_tokens)
    logger.info(
        "[FCM] Dispatch complete success_count=%s failure_count=%s invalid_tokens=%s removed=%s",
        success_total,
        failure_total,
        len(invalid_tokens),
        removed,
    )
    return success_total, invalid_tokens


def send_notification(teacher_id: int, data: dict) -> Tuple[int, List[str]]:
    """Platform-aware send: Android=data-only, Web/iOS PWA=notification+data."""
    token_rows = _fetch_teacher_tokens(teacher_id)
    logger.info("[FCM] Sending notification teacher_id=%s token_rows=%s", teacher_id, len(token_rows))
    return _dispatch_token_rows(token_rows, data)


def send_data_only_notification(teacher_id: int, data: dict) -> Tuple[int, List[str]]:
    """
    Backward-compatible API used by reminder jobs.
    Still respects platform behavior required by production:
    Android receives data-only, Web/PWA receives notification+data.
    """
    return send_notification(teacher_id, data)


def notify_teacher_updated(tokens: List[str], lang: str = "ar") -> int:
    """
    Backward-compatible helper for week publish notifications.
    Accepts raw token strings, rehydrates platform metadata from DB,
    then sends with the same platform-aware behavior.
    """
    is_ar = str(lang or "ar").lower() == "ar"
    data = {
        "type": "duty_update",
        "notification_type": "duty_update",
        "title": "تم تحديث المناوبات" if is_ar else "Duties updated",
        "body": (
            "تم تحديث جدول المناوبات. افتح التطبيق لمراجعة التغييرات."
            if is_ar
            else "Your duty roster has been updated. Open the app to review the changes."
        ),
    }
    token_rows = _fetch_token_rows(tokens)
    success_count, _invalid_tokens = _dispatch_token_rows(token_rows, data)
    return success_count
