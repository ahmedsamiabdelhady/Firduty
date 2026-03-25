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

_FIREBASE_INIT_ATTEMPTED = False
_FIREBASE_INITIALIZED = False
_MAX_MULTICAST_TOKENS = 500


def _ensure_firebase_initialized() -> bool:
    """Initialize Firebase Admin lazily and never crash module import."""
    global _FIREBASE_INIT_ATTEMPTED, _FIREBASE_INITIALIZED

    if firebase_admin._apps:
        _FIREBASE_INITIALIZED = True
        return True

    if _FIREBASE_INIT_ATTEMPTED:
        return _FIREBASE_INITIALIZED

    _FIREBASE_INIT_ATTEMPTED = True

    creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON", "").strip()
    creds_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip()

    try:
        if creds_json:
            cred = credentials.Certificate(json.loads(creds_json))
            firebase_admin.initialize_app(cred)
            logger.info("[FCM] Firebase initialized from FIREBASE_CREDENTIALS_JSON")
        elif creds_path and os.path.exists(creds_path):
            cred = credentials.Certificate(creds_path)
            firebase_admin.initialize_app(cred)
            logger.info("[FCM] Firebase initialized from FIREBASE_CREDENTIALS_PATH=%s", creds_path)
        else:
            firebase_admin.initialize_app()
            logger.info("[FCM] Firebase initialized with default application credentials")

        _FIREBASE_INITIALIZED = True
        return True
    except Exception:
        logger.exception("[FCM] Firebase initialization failed")
        _FIREBASE_INITIALIZED = False
        return False



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
    return "unregistered" in name or "invalidargument" in name or any(marker in text for marker in markers)



def _chunked(items: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]



def _dedupe_latest_token_rows(token_rows: Iterable[DeviceToken]) -> list[DeviceToken]:
    deduped: list[DeviceToken] = []
    seen_installations: set[str] = set()
    seen_tokens: set[str] = set()

    for row in token_rows:
        token = str(getattr(row, "token", "") or "").strip()
        if not token or token in seen_tokens:
            continue

        installation_id = str(getattr(row, "installation_id", "") or "").strip()
        installation_key = installation_id or f"legacy:{token}"
        if installation_key in seen_installations:
            continue

        seen_installations.add(installation_key)
        seen_tokens.add(token)
        deduped.append(row)

    return deduped



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
        rows = (
            db.query(DeviceToken)
            .filter(DeviceToken.teacher_id == teacher_id)
            .order_by(DeviceToken.updated_at.desc(), DeviceToken.id.desc())
            .all()
        )
        return _dedupe_latest_token_rows(rows)
    finally:
        db.close()



def _fetch_token_rows(tokens: Iterable[str]) -> list[DeviceToken]:
    tokens = [str(token).strip() for token in tokens if str(token).strip()]
    if not tokens:
        return []

    db = SessionLocal()
    try:
        rows = (
            db.query(DeviceToken)
            .filter(DeviceToken.token.in_(tokens))
            .order_by(DeviceToken.updated_at.desc(), DeviceToken.id.desc())
            .all()
        )
        return _dedupe_latest_token_rows(rows)
    finally:
        db.close()



def _delete_invalid_tokens(invalid_tokens: Iterable[str]) -> int:
    invalid_tokens = [str(token).strip() for token in invalid_tokens if str(token).strip()]
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



def _build_android_message(tokens: list[str], data: dict) -> messaging.MulticastMessage:
    return messaging.MulticastMessage(
        data=_safe_str_dict(data),
        tokens=tokens,
        android=messaging.AndroidConfig(priority="high"),
    )



def _build_web_multicast(title: str, body: str, data: dict, tokens: list[str]) -> messaging.MulticastMessage:
    web_link = (os.getenv("WEB_APP_URL") or "").strip()

    if web_link and not web_link.startswith("https://"):
        logger.warning("[FCM] Invalid WEB_APP_URL=%r; omitting webpush link because it must be HTTPS", web_link)
        web_link = None

    webpush_config = messaging.WebpushConfig(
        headers={"Urgency": "high", "TTL": "300"},
        notification=messaging.WebpushNotification(
            title=title,
            body=body,
            icon="/icons/Icon-192.png",
            badge="/icons/Icon-192.png",
            tag=str(
                data.get("event_id")
                or data.get("assignment_id")
                or data.get("notification_type")
                or "firduty"
            ),
            renotify=False,
        ),
    )

    if web_link:
        webpush_config.fcm_options = messaging.WebpushFCMOptions(link=web_link)

    return messaging.MulticastMessage(
        data=_safe_str_dict(data),
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        webpush=webpush_config,
    )



def _send_multicast(*, tokens: list[str], data: dict, platform: str) -> tuple[int, list[str], int]:
    if not tokens:
        return 0, [], 0

    if not _ensure_firebase_initialized():
        logger.error("[FCM] Skipping %s dispatch because Firebase is not initialized", platform)
        return 0, list(tokens), len(tokens)

    total_success = 0
    total_failure = 0
    invalid_tokens: list[str] = []

    for chunk_index, token_chunk in enumerate(_chunked(tokens, _MAX_MULTICAST_TOKENS), start=1):
        try:
            if platform == "android":
                message = _build_android_message(token_chunk, data)
            else:
                message = _build_web_multicast(token_chunk, data)

            response = messaging.send_each_for_multicast(message)
        except Exception as exc:
            logger.exception(
                "[FCM] %s dispatch chunk=%s size=%s raised: %s",
                platform,
                chunk_index,
                len(token_chunk),
                exc,
            )
            total_failure += len(token_chunk)
            invalid_tokens.extend(token_chunk)
            continue

        for index, item in enumerate(response.responses):
            if item.success:
                continue
            total_failure += 1
            token = token_chunk[index]
            if _is_invalid_token_error(item.exception):
                invalid_tokens.append(token)
            logger.warning(
                "[FCM] %s token send failed chunk=%s token_index=%s error=%s",
                platform,
                chunk_index,
                index,
                item.exception,
            )

        total_success += int(response.success_count or 0)

    return total_success, invalid_tokens, total_failure



def _dispatch_token_rows(token_rows: list[DeviceToken], data: dict) -> Tuple[int, List[str]]:
    if not token_rows:
        logger.info("[FCM] No device tokens found")
        return 0, []

    android_tokens, web_tokens = _split_tokens_by_platform(token_rows)
    success_total = 0
    failure_total = 0
    invalid_tokens: list[str] = []

    if android_tokens:
        ok, invalid, failed = _send_multicast(tokens=android_tokens, data=data, platform="android")
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
        ok, invalid, failed = _send_multicast(tokens=web_tokens, data=data, platform="web")
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
