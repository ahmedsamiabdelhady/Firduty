"""Firebase Cloud Messaging notification service — bilingual, duty-type aware."""

import logging
import os
from typing import List, Optional

import firebase_admin
from firebase_admin import credentials, messaging
from config import settings

logger = logging.getLogger(__name__)
_firebase_initialized = False


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
        logger.warning(f"Firebase credentials not found at {cred_path}. Push notifications disabled.")


# ─── Notification Templates ───────────────────────────────────────────────────

TEMPLATES = {
    # 15-minute reminder — morning/end-of-day duty (has location)
    "reminder_location": {
        "ar": {
            "title": "المناوبات",
            "body": "تذكير: مناوبتك بعد 15 دقيقة — الموقع: {location} — الفترة: {shift}"
        },
        "en": {
            "title": "Duty Roster",
            "body": "Reminder: Your duty starts in 15 minutes — Location: {location} — Shift: {shift}"
        }
    },
    # 15-minute reminder — break duty (has grade/class, no location)
    "reminder_break": {
        "ar": {
            "title": "المناوبات",
            "body": "تذكير: فترة الاستراحة بعد 15 دقيقة — الفصل: {grade_class} — الفترة: {shift}"
        },
        "en": {
            "title": "Duty Roster",
            "body": "Reminder: Your break duty starts in 15 minutes — Class: {grade_class} — Shift: {shift}"
        }
    },
    # Duty started — morning/end-of-day
    "start_location": {
        "ar": {
            "title": "المناوبات",
            "body": "بدأت مناوبتك الآن — الموقع: {location}"
        },
        "en": {
            "title": "Duty Roster",
            "body": "Your duty has started — Location: {location}"
        }
    },
    # Duty started — break
    "start_break": {
        "ar": {
            "title": "المناوبات",
            "body": "بدأت مناوبتك الآن — الفصل: {grade_class}"
        },
        "en": {
            "title": "Duty Roster",
            "body": "Your break duty has started — Class: {grade_class}"
        }
    },
    # Schedule updated (no location/class detail needed)
    "updated": {
        "ar": {
            "title": "المناوبات",
            "body": "تم تعديل مناوبتك للأسبوع — راجع التطبيق"
        },
        "en": {
            "title": "Duty Roster",
            "body": "Your duty schedule has been updated — Please check the app"
        }
    },
}


def get_notification_text(template_key: str, lang: str, **kwargs) -> dict:
    """Return title+body for a notification template in the given language."""
    lang = lang if lang in ("ar", "en") else "ar"
    tmpl = TEMPLATES.get(template_key, {}).get(lang, {})
    return {
        "title": tmpl.get("title", "Duty Roster"),
        "body": tmpl.get("body", "").format(**kwargs)
    }


def send_notification_to_tokens(
    tokens: List[str], title: str, body: str, data: dict = None
) -> int:
    """Send multicast push notification. Returns success count."""
    _init_firebase()
    if not _firebase_initialized or not tokens:
        return 0
    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        android=messaging.AndroidConfig(priority="high"),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(aps=messaging.Aps(sound="default"))
        )
    )
    try:
        response = messaging.send_multicast(message)
        logger.info(f"FCM multicast: {response.success_count} success, {response.failure_count} fail")
        return response.success_count
    except Exception as e:
        logger.error(f"FCM send error: {e}")
        return 0


def notify_teacher_updated(teacher_tokens: List[str], lang: str) -> None:
    """Notify a teacher that their weekly schedule was modified."""
    text = get_notification_text("updated", lang)
    send_notification_to_tokens(teacher_tokens, text["title"], text["body"],
                                data={"type": "schedule_updated"})


def notify_duty_reminder(
    teacher_tokens: List[str],
    lang: str,
    shift: str,
    duty_type: str = "morning_endofday",
    location: Optional[str] = None,
    grade_class: Optional[str] = None,
) -> None:
    """Send 15-minute reminder. Uses location for morning/end-of-day, grade_class for break."""
    if duty_type == "break" and grade_class:
        text = get_notification_text("reminder_break", lang, shift=shift, grade_class=grade_class)
        data = {"type": "duty_reminder", "duty_type": "break"}
    else:
        loc = location or ""
        text = get_notification_text("reminder_location", lang, shift=shift, location=loc)
        data = {"type": "duty_reminder", "duty_type": "morning_endofday"}
    send_notification_to_tokens(teacher_tokens, text["title"], text["body"], data=data)


def notify_duty_start(
    teacher_tokens: List[str],
    lang: str,
    duty_type: str = "morning_endofday",
    location: Optional[str] = None,
    grade_class: Optional[str] = None,
) -> None:
    """Notify teacher that their duty has started."""
    if duty_type == "break" and grade_class:
        text = get_notification_text("start_break", lang, grade_class=grade_class)
        data = {"type": "duty_start", "duty_type": "break"}
    else:
        loc = location or ""
        text = get_notification_text("start_location", lang, location=loc)
        data = {"type": "duty_start", "duty_type": "morning_endofday"}
    send_notification_to_tokens(teacher_tokens, text["title"], text["body"], data=data)