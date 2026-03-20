"""
notification_service.py — Push notification delivery for Firduty.

Production token hygiene added:
  - in-memory token de-duplication before every send
  - invalid / unregistered tokens are deleted from device_tokens immediately
  - send_notification_to_tokens() keeps backward-compatible return type (int)
"""

import logging
import os
from typing import Callable, Dict, List, Optional

import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy import text

from config import settings
from database import SessionLocal

logger = logging.getLogger(__name__)
_firebase_initialized = False


INVALID_TOKEN_CODES = {
    "registration-token-not-registered",
    "invalid-registration-token",
    "invalid-argument",
    "unregistered",
}


def _init_firebase() -> None:
    global _firebase_initialized
    if _firebase_initialized:
        return

    cred_path = settings.FIREBASE_CREDENTIALS_PATH
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        logger.info("Firebase Admin SDK initialized.")
    else:
        logger.warning(
            "Firebase credentials not found at %s. FCM push notifications disabled.",
            cred_path,
        )


TEMPLATES: dict = {
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
            "body": "تم تعديل مناوبتك للأسبوع — راجع التطبيق",
        },
        "en": {
            "title": "Duty Roster",
            "body": "Your duty schedule has been updated — Please check the app",
        },
    },
}


def get_notification_text(template_key: str, lang: str, **kwargs: str) -> dict:
    lang = lang if lang in ("ar", "en") else "ar"
    tmpl: dict = TEMPLATES.get(template_key, {}).get(lang, {})
    return {
        "title": tmpl.get("title", "Duty Roster"),
        "body": tmpl.get("body", "").format(**kwargs),
    }


def _dedupe_tokens(tokens: List[str]) -> List[str]:
    seen = set()
    unique: List[str] = []
    for token in tokens:
        token = (token or "").strip()
        if token and token not in seen:
            seen.add(token)
            unique.append(token)
    return unique


def _is_invalid_token_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if code in INVALID_TOKEN_CODES:
        return True

    msg = str(exc).lower()
    return (
        "not registered" in msg
        or "registration-token-not-registered" in msg
        or "invalid registration token" in msg
        or "invalid-registration-token" in msg
        or "invalid argument" in msg
        or "unregistered" in msg
    )


def _delete_invalid_tokens(tokens: List[str]) -> None:
    tokens = _dedupe_tokens(tokens)
    if not tokens:
        return

    db = SessionLocal()
    try:
        db.execute(
            text("DELETE FROM device_tokens WHERE token = ANY(:tokens)"),
            {"tokens": tokens},
        )
        db.commit()
        logger.info("Deleted %d invalid device token(s)", len(tokens))
    except Exception:
        db.rollback()
        logger.exception("Failed to delete invalid device token(s)")
    finally:
        db.close()


def send_notification_to_tokens_report(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[dict] = None,
    invalid_token_cleanup: Optional[Callable[[List[str]], None]] = None,
) -> Dict[str, object]:
    """
    Send push notifications with token dedupe and invalid-token cleanup.

    Returns a detailed report:
      {
        "success_count": int,
        "failure_count": int,
        "invalid_tokens": [..],
        "tokens_sent": [..],
      }
    """
    _init_firebase()

    deduped_tokens = _dedupe_tokens(tokens)
    if not _firebase_initialized or not deduped_tokens:
        return {
            "success_count": 0,
            "failure_count": 0,
            "invalid_tokens": [],
            "tokens_sent": deduped_tokens,
        }

    message = messaging.MulticastMessage(
        tokens=deduped_tokens,
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        android=messaging.AndroidConfig(priority="high"),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(aps=messaging.Aps(sound="default"))
        ),
        webpush=messaging.WebpushConfig(
            notification=messaging.WebpushNotification(
                title=title,
                body=body,
                icon="/icons/Icon-192.png",
                badge="/icons/Icon-192.png",
            ),
            fcm_options=messaging.WebpushFCMOptions(link="/"),
        ),
    )

    invalid_tokens: List[str] = []
    success_count = 0
    failure_count = 0

    try:
        response = messaging.send_each_for_multicast(message)
    except Exception as exc:
        logger.error("FCM send error: %s", exc)
        return {
            "success_count": 0,
            "failure_count": len(deduped_tokens),
            "invalid_tokens": [],
            "tokens_sent": deduped_tokens,
        }

    for token, result in zip(deduped_tokens, response.responses):
        if result.success:
            success_count += 1
            continue

        failure_count += 1
        if result.exception and _is_invalid_token_error(result.exception):
            invalid_tokens.append(token)

    invalid_tokens = _dedupe_tokens(invalid_tokens)
    if invalid_tokens:
        (invalid_token_cleanup or _delete_invalid_tokens)(invalid_tokens)

    logger.info(
        "FCM multicast: %d success, %d fail, %d invalid removed",
        success_count,
        failure_count,
        len(invalid_tokens),
    )
    return {
        "success_count": success_count,
        "failure_count": failure_count,
        "invalid_tokens": invalid_tokens,
        "tokens_sent": deduped_tokens,
    }


def send_notification_to_tokens(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> int:
    """Backward-compatible wrapper used by the rest of the codebase."""
    report = send_notification_to_tokens_report(tokens, title, body, data=data)
    return int(report["success_count"])


def notify_teacher_updated(teacher_tokens: List[str], lang: str) -> None:
    text = get_notification_text("updated", lang)
    send_notification_to_tokens(
        teacher_tokens,
        text["title"],
        text["body"],
        data={"type": "schedule_updated"},
    )


def notify_duty_reminder(
    teacher_tokens: List[str],
    lang: str,
    shift: str,
    duty_type: str = "morning_endofday",
    location: Optional[str] = None,
    grade_class: Optional[str] = None,
) -> None:
    if duty_type == "break" and grade_class:
        text = get_notification_text(
            "reminder_break", lang, shift=shift, grade_class=grade_class
        )
        data: dict = {"type": "duty_reminder", "duty_type": "break"}
    else:
        text = get_notification_text(
            "reminder_location", lang, shift=shift, location=location or ""
        )
        data = {"type": "duty_reminder", "duty_type": "morning_endofday"}

    send_notification_to_tokens(teacher_tokens, text["title"], text["body"], data=data)


def notify_duty_start(
    teacher_tokens: List[str],
    lang: str,
    duty_type: str = "morning_endofday",
    location: Optional[str] = None,
    grade_class: Optional[str] = None,
) -> None:
    if duty_type == "break" and grade_class:
        text = get_notification_text("start_break", lang, grade_class=grade_class)
        data: dict = {"type": "duty_start", "duty_type": "break"}
    else:
        text = get_notification_text("start_location", lang, location=location or "")
        data = {"type": "duty_start", "duty_type": "morning_endofday"}

    send_notification_to_tokens(teacher_tokens, text["title"], text["body"], data=data)
