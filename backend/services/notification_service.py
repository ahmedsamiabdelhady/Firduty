"""Firebase Cloud Messaging notification service."""

import logging
import os
from typing import List, Optional
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, messaging
from config import settings

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK once
_firebase_initialized = False

def _init_firebase():
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
    "reminder": {
        "ar": {
            "title": "المناوبات",
            "body": "تذكير: مناوبتك بعد 15 دقيقة — المكان: {location} — الفترة: {shift}"
        },
        "en": {
            "title": "Duty Roster",
            "body": "Reminder: Your duty starts in 15 minutes — Location: {location} — Shift: {shift}"
        }
    },
    "start": {
        "ar": {
            "title": "المناوبات",
            "body": "بدأت مناوبتك الآن — المكان: {location}"
        },
        "en": {
            "title": "Duty Roster",
            "body": "Your duty has started — Location: {location}"
        }
    },
    "updated": {
        "ar": {
            "title": "المناوبات",
            "body": "تم تعديل مناوبتك للأسبوع — راجع التطبيق"
        },
        "en": {
            "title": "Duty Roster",
            "body": "Your duty schedule has been updated — Please check the app"
        }
    }
}


def get_notification_text(template_key: str, lang: str, **kwargs) -> dict:
    """Return title+body for a notification template in the given language."""
    lang = lang if lang in ("ar", "en") else "ar"
    tmpl = TEMPLATES.get(template_key, {}).get(lang, {})
    return {
        "title": tmpl.get("title", "Duty Roster"),
        "body": tmpl.get("body", "").format(**kwargs)
    }


def send_notification_to_tokens(tokens: List[str], title: str, body: str, data: dict = None) -> int:
    """
    Send a multicast push notification to a list of FCM tokens.
    Returns the number of successful sends.
    """
    _init_firebase()
    if not _firebase_initialized or not tokens:
        return 0

    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        android=messaging.AndroidConfig(priority="high"),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default")
            )
        )
    )
    try:
        response = messaging.send_multicast(message)
        logger.info(f"FCM multicast: {response.success_count} success, {response.failure_count} fail")
        return response.success_count
    except Exception as e:
        logger.error(f"FCM send error: {e}")
        return 0


def notify_teacher_updated(teacher_tokens: List[str], lang: str):
    """Notify a teacher that their weekly schedule was modified."""
    text = get_notification_text("updated", lang)
    send_notification_to_tokens(teacher_tokens, text["title"], text["body"],
                                  data={"type": "schedule_updated"})


def notify_duty_reminder(teacher_tokens: List[str], lang: str, location: str, shift: str):
    """Send 15-minute reminder before a duty."""
    text = get_notification_text("reminder", lang, location=location, shift=shift)
    send_notification_to_tokens(teacher_tokens, text["title"], text["body"],
                                  data={"type": "duty_reminder"})


def notify_duty_start(teacher_tokens: List[str], lang: str, location: str):
    """Notify teacher that their duty has started."""
    text = get_notification_text("start", lang, location=location)
    send_notification_to_tokens(teacher_tokens, text["title"], text["body"],
                                  data={"type": "duty_start"})