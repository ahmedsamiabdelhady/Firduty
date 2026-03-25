"""
notification_service.py
Production-safe FCM delivery for Firduty.

Platform behavior:
- Android native: data-only payload (to avoid duplicate rendering)
- Web / iOS PWA: notification + data payload via WebPush

Key guarantees:
- Never deletes tokens on code/config/runtime exceptions
- Deletes tokens only when Firebase explicitly reports invalid token errors
- Skips invalid WEB_APP_URL values instead of crashing WebPush delivery
- Returns structured delivery results for callers and logs clearly
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy import desc

from config import settings
from database import SessionLocal
from models.models import DeviceToken, Teacher

logger = logging.getLogger(__name__)

MAX_MULTICAST_TOKENS = 500

_firebase_initialized = False
_firebase_init_attempted = False


# -------------------------------------------------------------------
# Firebase init
# -------------------------------------------------------------------
def _init_firebase() -> None:
    global _firebase_initialized, _firebase_init_attempted

    if _firebase_initialized:
        return

    if _firebase_init_attempted:
        return

    _firebase_init_attempted = True

    cred_path = getattr(settings, "FIREBASE_CREDENTIALS_PATH", None)
    if not cred_path or not os.path.exists(cred_path):
        logger.error(
            "[FCM] Firebase credentials file not found at %r. "
            "Set FIREBASE_CREDENTIALS_JSON or FIREBASE_CREDENTIALS_PATH.",
            cred_path,
        )
        return

    try:
        if firebase_admin._DEFAULT_APP_NAME in firebase_admin._apps:
            _firebase_initialized = True
            logger.info("[FCM] Firebase already initialized — reusing existing app.")
            return

        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True

        source = "FIREBASE_CREDENTIALS_JSON" if os.getenv("FIREBASE_CREDENTIALS_JSON") else cred_path
        logger.info("[FCM] Firebase initialized from %s", source)
    except Exception as exc:
        logger.exception("[FCM] Firebase initialization failed: %s", exc)


# -------------------------------------------------------------------
# Templates
# -------------------------------------------------------------------
TEMPLATES: Dict[str, Dict[str, Dict[str, str]]] = {
    "reminder_location": {
        "ar": {
            "title": "المناوبات",
            "body": "تذكير: مناوبتك بعد 15 دقيقة — الموقع: {location} — الفترة: {shift}",
        },
        "en": {
            "title": "Duty Roster",
            "body": "Reminder: Your duty starts in 15 minutes — Location: {location} — Shift: {shift}",
        },
    },
    "reminder_break": {
        "ar": {
            "title": "المناوبات",
            "body": "تذكير: فترة الاستراحة بعد 15 دقيقة — الفصل: {grade_class} — الفترة: {shift}",
        },
        "en": {
            "title": "Duty Roster",
            "body": "Reminder: Your break duty starts in 15 minutes — Class: {grade_class} — Shift: {shift}",
        },
    },
    "start_location": {
        "ar": {
            "title": "المناوبات",
            "body": "بدأت مناوبتك الآن — الموقع: {location}",
        },
        "en": {
            "title": "Duty Roster",
            "body": "Your duty has started — Location: {location}",
        },
    },
    "start_break": {
        "ar": {
            "title": "المناوبات",
            "body": "بدأت مناوبتك الآن — الفصل: {grade_class}",
        },
        "en": {
            "title": "Duty Roster",
            "body": "Your break duty has started — Class: {grade_class}",
        },
    },
    "updated": {
        "ar": {
            "title": "المناوبات",
            "body": "تم تعديل مناوبتك — راجع التطبيق",
        },
        "en": {
            "title": "Duty Roster",
            "body": "Your duty schedule has been updated — Please check the app",
        },
    },
}


def get_notification_text(template_key: str, lang: str, **kwargs: str) -> Dict[str, str]:
    lang = lang if lang in ("ar", "en") else "ar"
    tmpl = TEMPLATES.get(template_key, {}).get(lang, {})
    return {
        "title": tmpl.get("title", "Duty Roster"),
        "body": tmpl.get("body", "").format(**kwargs),
    }


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _safe_str_dict(data: Optional[Dict[str, Any]]) -> Dict[str, str]:
    return {str(k): str(v) for k, v in (data or {}).items() if v is not None}


def _chunks(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _normalize_platform(value: Optional[str]) -> str:
    p = (value or "").strip().lower()
    if p in {"android"}:
        return "android"
    return "web"  # web + iOS PWA + unknown fallback


def _is_https_url(url: Optional[str]) -> bool:
    return bool(url and isinstance(url, str) and url.startswith("https://"))


def _get_web_link() -> Optional[str]:
    web_link = (
        os.getenv("WEB_APP_URL")
        or os.getenv("APP_BASE_URL")
        or "https://firduty-dede5.web.app"
    ).strip()

    if not web_link:
        return None

    if not _is_https_url(web_link):
        logger.warning(
            "[FCM] Invalid WEB_APP_URL=%r — omitting WebPush link because it must be HTTPS",
            web_link,
        )
        return None

    return web_link.rstrip("/")


def _is_invalid_token_error(exc: Optional[BaseException]) -> bool:
    if exc is None:
        return False

    code = (getattr(exc, "code", "") or "").lower()
    msg = str(exc).lower()

    invalid_markers = (
        "registration-token-not-registered",
        "invalid-registration-token",
        "requested entity was not found",
        "notregistered",
        "invalid argument",
    )

    if code in {"registration-token-not-registered", "invalid-registration-token"}:
        return True

    return any(marker in msg for marker in invalid_markers)


def _dedupe_token_rows(rows: List[DeviceToken]) -> List[DeviceToken]:
    """
    Keep newest token per installation_id when present.
    Also dedupe repeated raw token strings.
    """
    by_installation: Dict[str, DeviceToken] = {}
    by_token: Dict[str, DeviceToken] = {}

    for row in rows:
        if not row.token:
            continue

        token_key = row.token.strip()
        if not token_key:
            continue

        install_key = (row.installation_id or "").strip()

        existing_token_row = by_token.get(token_key)
        if existing_token_row is None:
            by_token[token_key] = row
        else:
            existing_seen = getattr(existing_token_row, "last_seen_at", None) or getattr(existing_token_row, "created_at", None)
            current_seen = getattr(row, "last_seen_at", None) or getattr(row, "created_at", None)
            if current_seen and (existing_seen is None or current_seen > existing_seen):
                by_token[token_key] = row

        if install_key:
            existing_install_row = by_installation.get(install_key)
            if existing_install_row is None:
                by_installation[install_key] = row
            else:
                existing_seen = getattr(existing_install_row, "last_seen_at", None) or getattr(existing_install_row, "created_at", None)
                current_seen = getattr(row, "last_seen_at", None) or getattr(row, "created_at", None)
                if current_seen and (existing_seen is None or current_seen > existing_seen):
                    by_installation[install_key] = row

    chosen: Dict[str, DeviceToken] = {}

    for row in by_installation.values():
        chosen[row.token] = row

    for token, row in by_token.items():
        if token not in chosen:
            chosen[token] = row

    return list(chosen.values())


def _build_android_multicast(
    title: str,
    body: str,
    data: Dict[str, Any],
    tokens: List[str],
) -> messaging.MulticastMessage:
    # Android native => data-only to avoid duplicate rendering
    return messaging.MulticastMessage(
        data=_safe_str_dict(data),
        tokens=tokens,
        android=messaging.AndroidConfig(priority="high"),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(content_available=True, sound="default")
            )
        ),
    )


def _build_web_multicast(
    title: str,
    body: str,
    data: Dict[str, Any],
    tokens: List[str],
) -> messaging.MulticastMessage:
    web_link = _get_web_link()

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
                or data.get("type")
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


def _send_multicast(
    *,
    title: str,
    body: str,
    data: Dict[str, Any],
    tokens: List[str],
    platform_label: str,
) -> Tuple[int, int, List[str]]:
    """
    Returns:
        success_count, failure_count, invalid_tokens
    """
    if not tokens:
        return 0, 0, []

    total_success = 0
    total_failure = 0
    invalid_tokens: List[str] = []

    for chunk_index, token_chunk in enumerate(_chunks(tokens, MAX_MULTICAST_TOKENS), start=1):
        try:
            if platform_label == "android":
                message = _build_android_multicast(title, body, data, token_chunk)
            else:
                message = _build_web_multicast(title, body, data, token_chunk)

            response = messaging.send_each_for_multicast(message)

            total_success += response.success_count
            total_failure += response.failure_count

            for idx, result in enumerate(response.responses):
                if result.success:
                    continue

                token = token_chunk[idx]
                exc = result.exception

                logger.warning(
                    "[FCM] %s token failed chunk=%s idx=%s code=%s msg=%s",
                    platform_label,
                    chunk_index,
                    idx,
                    getattr(exc, "code", None),
                    exc,
                )

                if _is_invalid_token_error(exc):
                    invalid_tokens.append(token)

        except Exception as exc:
            # IMPORTANT:
            # This is a code/config/runtime failure, not a token-invalid failure.
            # Never delete tokens here.
            total_failure += len(token_chunk)
            logger.exception(
                "[FCM] %s dispatch chunk=%s size=%s raised: %s",
                platform_label,
                chunk_index,
                len(token_chunk),
                exc,
            )

    return total_success, total_failure, list(dict.fromkeys(invalid_tokens))


def remove_invalid_tokens(db, failed_tokens: List[str]) -> int:
    if not failed_tokens:
        return 0

    try:
        deleted = (
            db.query(DeviceToken)
            .filter(DeviceToken.token.in_(failed_tokens))
            .delete(synchronize_session=False)
        )
        db.commit()
        if deleted:
            logger.warning("[FCM] Removed %d invalid token(s) from database", deleted)
        return deleted
    except Exception as exc:
        db.rollback()
        logger.exception("[FCM] Failed removing invalid tokens: %s", exc)
        return 0


# -------------------------------------------------------------------
# Public API used by week_service / jobs
# -------------------------------------------------------------------
def send_notification(
    teacher_id: int,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send notification to all active devices for a teacher.

    Returns:
    {
        "success_count": int,
        "failure_count": int,
        "invalid_tokens": list[str],
        "removed_tokens": int,
        "token_rows": int,
    }
    """
    _init_firebase()

    if not _firebase_initialized:
        logger.error("[FCM] Cannot send notification — Firebase not initialized")
        return {
            "success_count": 0,
            "failure_count": 0,
            "invalid_tokens": [],
            "removed_tokens": 0,
            "token_rows": 0,
        }

    db = SessionLocal()
    try:
        rows = (
            db.query(DeviceToken)
            .filter(DeviceToken.teacher_id == teacher_id)
            .order_by(
                desc(DeviceToken.last_seen_at),
                desc(DeviceToken.created_at),
            )
            .all()
        )

        logger.info("[FCM] Sending notification teacher_id=%s token_rows=%s", teacher_id, len(rows))

        if not rows:
            logger.info("[FCM] No device tokens found")
            return {
                "success_count": 0,
                "failure_count": 0,
                "invalid_tokens": [],
                "removed_tokens": 0,
                "token_rows": 0,
            }

        rows = _dedupe_token_rows(rows)

        android_tokens: List[str] = []
        web_tokens: List[str] = []

        for row in rows:
            platform = _normalize_platform(getattr(row, "platform", None))
            if platform == "android":
                android_tokens.append(row.token)
            else:
                web_tokens.append(row.token)

        success_count = 0
        failure_count = 0
        invalid_tokens: List[str] = []

        if android_tokens:
            a_success, a_failure, a_invalid = _send_multicast(
                title=title,
                body=body,
                data=data or {},
                tokens=android_tokens,
                platform_label="android",
            )
            success_count += a_success
            failure_count += a_failure
            invalid_tokens.extend(a_invalid)
            logger.info(
                "[FCM] Android dispatch success=%s failures=%s tokens=%s",
                a_success,
                a_failure,
                len(android_tokens),
            )

        if web_tokens:
            w_success, w_failure, w_invalid = _send_multicast(
                title=title,
                body=body,
                data=data or {},
                tokens=web_tokens,
                platform_label="web",
            )
            success_count += w_success
            failure_count += w_failure
            invalid_tokens.extend(w_invalid)
            logger.info(
                "[FCM] Web/PWA dispatch success=%s failures=%s tokens=%s",
                w_success,
                w_failure,
                len(web_tokens),
            )

        invalid_tokens = list(dict.fromkeys(invalid_tokens))
        removed = remove_invalid_tokens(db, invalid_tokens)

        logger.info(
            "[FCM] Dispatch complete success_count=%s failure_count=%s invalid_tokens=%s removed=%s",
            success_count,
            failure_count,
            len(invalid_tokens),
            removed,
        )

        return {
            "success_count": success_count,
            "failure_count": failure_count,
            "invalid_tokens": invalid_tokens,
            "removed_tokens": removed,
            "token_rows": len(rows),
        }
    finally:
        db.close()


def send_notification_to_tokens(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> Tuple[int, List[str]]:
    """
    Backward-compatible helper for old callers.
    Sends as generic web-style payload when platform info is not available.
    Returns:
        (success_count, invalid_tokens)
    """
    _init_firebase()

    if not tokens:
        return 0, []

    if not _firebase_initialized:
        logger.error("[FCM] Cannot send — Firebase not initialized")
        return 0, []

    unique_tokens = list(dict.fromkeys([t for t in tokens if t]))
    success, _failure, invalid = _send_multicast(
        title=title,
        body=body,
        data=data or {},
        tokens=unique_tokens,
        platform_label="web",
    )
    return success, invalid


def notify_teacher_updated(teacher_id: int, lang: str = "ar") -> Dict[str, Any]:
    text = get_notification_text("updated", lang)
    return send_notification(
        teacher_id=teacher_id,
        title=text["title"],
        body=text["body"],
        data={
            "type": "schedule_updated",
            "notification_type": "updated",
        },
    )


def notify_duty_reminder(
    teacher_id: int,
    lang: str,
    shift: str,
    duty_type: str = "morning_endofday",
    location: Optional[str] = None,
    grade_class: Optional[str] = None,
    assignment_id: Optional[int] = None,
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    if duty_type == "break" and grade_class:
        text = get_notification_text(
            "reminder_break",
            lang,
            shift=shift,
            grade_class=grade_class,
        )
    else:
        text = get_notification_text(
            "reminder_location",
            lang,
            shift=shift,
            location=location or "",
        )

    return send_notification(
        teacher_id=teacher_id,
        title=text["title"],
        body=text["body"],
        data={
            "type": "duty_reminder",
            "notification_type": "reminder_15m",
            "duty_type": duty_type,
            "assignment_id": assignment_id or "",
            "event_id": event_id or "",
            "shift": shift,
            "location": location or "",
            "grade_class": grade_class or "",
        },
    )


def notify_duty_start(
    teacher_id: int,
    lang: str,
    duty_type: str = "morning_endofday",
    location: Optional[str] = None,
    grade_class: Optional[str] = None,
    assignment_id: Optional[int] = None,
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    if duty_type == "break" and grade_class:
        text = get_notification_text(
            "start_break",
            lang,
            grade_class=grade_class,
        )
    else:
        text = get_notification_text(
            "start_location",
            lang,
            location=location or "",
        )

    return send_notification(
        teacher_id=teacher_id,
        title=text["title"],
        body=text["body"],
        data={
            "type": "duty_start",
            "notification_type": "duty_started",
            "duty_type": duty_type,
            "assignment_id": assignment_id or "",
            "event_id": event_id or "",
            "location": location or "",
            "grade_class": grade_class or "",
        },
    )


def send_data_only_notification(teacher_id: int, data: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    Backward-compatible helper used by older scheduler code.
    Sends data-only to Android devices and regular web message to web devices.
    """
    _init_firebase()

    if not _firebase_initialized:
        logger.error("[FCM] Cannot send data-only notification — Firebase not initialized")
        return 0, []

    db = SessionLocal()
    try:
        rows = (
            db.query(DeviceToken)
            .filter(DeviceToken.teacher_id == teacher_id)
            .order_by(
                desc(DeviceToken.last_seen_at),
                desc(DeviceToken.created_at),
            )
            .all()
        )

        if not rows:
            return 0, []

        rows = _dedupe_token_rows(rows)

        android_tokens: List[str] = []
        web_tokens: List[str] = []

        for row in rows:
            platform = _normalize_platform(getattr(row, "platform", None))
            if platform == "android":
                android_tokens.append(row.token)
            else:
                web_tokens.append(row.token)

        title = str(data.get("title") or "Firduty")
        body = str(data.get("body") or "")

        success_count = 0
        invalid_tokens: List[str] = []

        if android_tokens:
            a_success, _a_failure, a_invalid = _send_multicast(
                title=title,
                body=body,
                data=data,
                tokens=android_tokens,
                platform_label="android",
            )
            success_count += a_success
            invalid_tokens.extend(a_invalid)

        if web_tokens:
            w_success, _w_failure, w_invalid = _send_multicast(
                title=title,
                body=body,
                data=data,
                tokens=web_tokens,
                platform_label="web",
            )
            success_count += w_success
            invalid_tokens.extend(w_invalid)

        invalid_tokens = list(dict.fromkeys(invalid_tokens))
        remove_invalid_tokens(db, invalid_tokens)

        return success_count, invalid_tokens
    finally:
        db.close()


def get_teacher_language(db, teacher_id: int) -> str:
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    lang = getattr(teacher, "language", None) if teacher else None
    return lang if lang in ("ar", "en") else "ar"