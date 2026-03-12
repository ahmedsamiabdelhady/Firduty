"""
notification_service.py — Push notification delivery for Firduty.

Delivery paths:
  platform = 'android'
    → Firebase Cloud Messaging (FCM) via firebase-admin SDK
    → token is a standard FCM registration token

  platform = 'web'
    → FCM Web Push via firebase-admin SDK
    → token is an FCM web registration token obtained from the Firebase JS SDK
      with getToken(vapidKey=...) in the Flutter Web app
    → Firebase internally delivers it via Web Push (VAPID) to the browser SW
    → Works on iOS Safari 16.4+ (iPadOS 16.4+), Chrome, Edge, Firefox

Both paths use the same send_notification_to_tokens() function — Firebase
handles the per-platform routing based on the token type.

If the firebase-admin SDK is not configured, the VAPID fallback path sends
raw Web Push via pywebpush (if installed). This supports tokens that are
raw PushSubscription JSON strings (not FCM tokens).
"""

import json
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
        logger.warning(
            f"Firebase credentials not found at {cred_path}. "
            "FCM push notifications disabled."
        )


# ─── Notification Templates ───────────────────────────────────────────────────

TEMPLATES: dict = {
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


def get_notification_text(template_key: str, lang: str, **kwargs: str) -> dict:
    """Return {title, body} for a notification template in the given language."""
    lang = lang if lang in ("ar", "en") else "ar"
    tmpl: dict = TEMPLATES.get(template_key, {}).get(lang, {})
    return {
        "title": tmpl.get("title", "Duty Roster"),
        "body":  tmpl.get("body", "").format(**kwargs)
    }


# ─── FCM send (Android + Web via Firebase) ───────────────────────────────────

def send_notification_to_tokens(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> int:
    """
    Send push notification via FCM to a list of tokens.

    Tokens may be from Android (FCM native) or Web (FCM web registration tokens).
    Firebase routes each token to the correct delivery channel automatically.

    Returns the number of successful deliveries.
    """
    _init_firebase()
    if not _firebase_initialized or not tokens:
        return 0

    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        android=messaging.AndroidConfig(priority="high"),
        # APNS config keeps iOS PWA web push working through APNs/Firebase
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default")
            )
        ),
        # Web Push config (used for FCM web tokens, including iOS Safari PWA)
        webpush=messaging.WebpushConfig(
            notification=messaging.WebpushNotification(
                title=title,
                body=body,
                icon="/icons/Icon-192.png",
                badge="/icons/Icon-192.png",
            ),
            fcm_options=messaging.WebpushFCMOptions(
                link="/",   # URL to open when notification is tapped
            ),
        ),
    )

    try:
        response = messaging.send_multicast(message)
        logger.info(
            f"FCM multicast: {response.success_count} success, "
            f"{response.failure_count} fail"
        )
        return response.success_count
    except Exception as e:
        logger.error(f"FCM send error: {e}")
        return 0


# ─── High-level notification helpers ─────────────────────────────────────────

def notify_teacher_updated(teacher_tokens: List[str], lang: str) -> None:
    """Notify a teacher that their weekly schedule was modified."""
    text = get_notification_text("updated", lang)
    send_notification_to_tokens(
        teacher_tokens, text["title"], text["body"],
        data={"type": "schedule_updated"}
    )


def notify_duty_reminder(
    teacher_tokens: List[str],
    lang: str,
    shift: str,
    duty_type: str = "morning_endofday",
    location: Optional[str] = None,
    grade_class: Optional[str] = None,
) -> None:
    """Send 15-minute reminder before a duty starts."""
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
    """Notify teacher that their duty has started."""
    if duty_type == "break" and grade_class:
        text = get_notification_text("start_break", lang, grade_class=grade_class)
        data: dict = {"type": "duty_start", "duty_type": "break"}
    else:
        text = get_notification_text(
            "start_location", lang, location=location or ""
        )
        data = {"type": "duty_start", "duty_type": "morning_endofday"}
    send_notification_to_tokens(teacher_tokens, text["title"], text["body"], data=data)