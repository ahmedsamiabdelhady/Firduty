"""
notification_service.py — Push notification delivery for Firduty.

Delivery paths:
- platform = 'android' → FCM via firebase-admin SDK (native token)
- platform = 'web' → FCM Web Push via firebase-admin SDK (VAPID token)

Key guarantees:
- send_notification_to_tokens() returns (success_count, failed_tokens)
- invalid/expired tokens are returned so callers can clean DB rows
- reminder / start / update notifications all carry visible title/body and data
- send_data_only_notification() is kept for compatibility, but now sends a
  visible notification too when title/body are present in the payload so
  Android can display reminder/start notifications reliably
"""

import logging
import os
from typing import List, Optional, Tuple

import firebase_admin
from firebase_admin import credentials, messaging

from config import settings

logger = logging.getLogger(__name__)

_firebase_initialized = False
_firebase_init_attempted = False


# ── Firebase initialisation ───────────────────────────────────────────────────
def _init_firebase() -> None:
    global _firebase_initialized, _firebase_init_attempted

    if _firebase_initialized:
        return
    if _firebase_init_attempted:
        return

    _firebase_init_attempted = True
    cred_path = settings.FIREBASE_CREDENTIALS_PATH

    if not os.path.exists(cred_path):
        logger.error(
            "[FCM] Firebase credentials file NOT FOUND at '%s'. "
            "Push notifications are disabled. "
            "Set FIREBASE_CREDENTIALS_JSON or FIREBASE_CREDENTIALS_PATH.",
            cred_path,
        )
        return

    try:
        if firebase_admin._DEFAULT_APP_NAME in firebase_admin._apps:
            _firebase_initialized = True
            logger.info("[FCM] Firebase Admin SDK already initialized — reusing.")
            return

        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        logger.info("[FCM] Firebase Admin SDK initialized successfully.")
    except Exception as exc:
        logger.error("[FCM] Firebase Admin SDK init FAILED: %s", exc)


# ── Notification templates ────────────────────────────────────────────────────
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


# ── Core FCM sender ───────────────────────────────────────────────────────────
def send_notification_to_tokens(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> Tuple[int, List[str]]:
    """
    Send an FCM multicast push notification.

    Returns:
      (success_count, failed_tokens)
    """
    _init_firebase()

    if not tokens:
        return 0, []

    if not _firebase_initialized:
        logger.error(
            "[FCM] Cannot send — Firebase not initialized. "
            "Check FIREBASE_CREDENTIALS_JSON / FIREBASE_CREDENTIALS_PATH."
        )
        return 0, list(tokens)

    unique_tokens = list(dict.fromkeys(tokens))
    if len(unique_tokens) < len(tokens):
        logger.debug("[FCM] Deduplicated %d → %d tokens", len(tokens), len(unique_tokens))

    str_data = {k: str(v) for k, v in (data or {}).items()}
    if title:
        str_data.setdefault("title", title)
    if body:
        str_data.setdefault("body", body)

    web_base_url = (
        os.getenv("WEB_APP_URL")
        or os.getenv("APP_BASE_URL")
        or "https://naval-donnamarie-firduty-6e288803.koyeb.app"
    ).rstrip("/")

    message = messaging.MulticastMessage(
        tokens=unique_tokens,
        notification=messaging.Notification(title=title, body=body),
        data=str_data,
        android=messaging.AndroidConfig(priority="high"),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default", content_available=True)
            )
        ),
        webpush=messaging.WebpushConfig(
            notification=messaging.WebpushNotification(
                title=title,
                body=body,
                icon="/icons/Icon-192.png",
                badge="/icons/Icon-192.png",
            ),
            fcm_options=messaging.WebpushFCMOptions(link=f"{web_base_url}/"),
        ),
    )

    try:
        response = messaging.send_each_for_multicast(message)
    except Exception as exc:
        logger.error("[FCM] send_each_for_multicast raised: %s", exc)
        return 0, unique_tokens

    failed_tokens: List[str] = []
    invalid_codes = {
        "registration-token-not-registered",
        "invalid-registration-token",
        "invalid-argument",
    }

    for idx, result in enumerate(response.responses):
        token = unique_tokens[idx]
        if result.success:
            logger.debug("[FCM] ✓ token[%d] delivered", idx)
            continue

        err = result.exception
        err_code = getattr(err, "code", "") or ""
        err_msg = str(err) if err else "unknown error"
        logger.warning(
            "[FCM] ✗ token[%d] failed — code=%s msg=%s",
            idx,
            err_code,
            err_msg,
        )
        if err_code in invalid_codes:
            failed_tokens.append(token)

    logger.info(
        "[FCM] Multicast result: %d/%d succeeded, %d invalid tokens to remove",
        response.success_count,
        len(unique_tokens),
        len(failed_tokens),
    )
    return response.success_count, failed_tokens


def remove_invalid_tokens(db, failed_tokens: List[str]) -> None:
    if not failed_tokens:
        return

    try:
        from models.models import DeviceToken

        deleted = (
            db.query(DeviceToken)
            .filter(DeviceToken.token.in_(failed_tokens))
            .delete(synchronize_session=False)
        )
        db.commit()
        if deleted:
            logger.info("[FCM] Removed %d invalid/expired device token(s).", deleted)
    except Exception as exc:
        logger.error("[FCM] Failed to remove invalid tokens: %s", exc)
        db.rollback()


# ── High-level helpers ────────────────────────────────────────────────────────
def notify_teacher_updated(teacher_tokens: List[str], lang: str) -> int:
    text = get_notification_text("updated", lang)
    success, _ = send_notification_to_tokens(
        teacher_tokens,
        text["title"],
        text["body"],
        data={
            "type": "schedule_updated",
            "title": text["title"],
            "body": text["body"],
        },
    )
    return success


def notify_duty_reminder(
    teacher_tokens: List[str],
    lang: str,
    shift: str,
    duty_type: str = "morning_endofday",
    location: Optional[str] = None,
    grade_class: Optional[str] = None,
) -> Tuple[int, List[str]]:
    if duty_type == "break" and grade_class:
        text = get_notification_text(
            "reminder_break",
            lang,
            shift=shift,
            grade_class=grade_class,
        )
        data: dict = {"type": "duty_reminder", "duty_type": "break"}
    else:
        text = get_notification_text(
            "reminder_location",
            lang,
            shift=shift,
            location=location or "",
        )
        data = {"type": "duty_reminder", "duty_type": "morning_endofday"}

    data["title"] = text["title"]
    data["body"] = text["body"]
    return send_notification_to_tokens(teacher_tokens, text["title"], text["body"], data=data)



def notify_duty_start(
    teacher_tokens: List[str],
    lang: str,
    duty_type: str = "morning_endofday",
    location: Optional[str] = None,
    grade_class: Optional[str] = None,
) -> Tuple[int, List[str]]:
    if duty_type == "break" and grade_class:
        text = get_notification_text("start_break", lang, grade_class=grade_class)
        data: dict = {"type": "duty_start", "duty_type": "break"}
    else:
        text = get_notification_text("start_location", lang, location=location or "")
        data = {"type": "duty_start", "duty_type": "morning_endofday"}

    data["title"] = text["title"]
    data["body"] = text["body"]
    return send_notification_to_tokens(teacher_tokens, text["title"], text["body"], data=data)



def send_data_only_notification(teacher_id: int, data: dict) -> Tuple[int, List[str]]:
    """
    Backward-compatible helper used by the reminder job.

    It still accepts a teacher_id + data payload, but it now sends a visible
    notification too whenever `data['title']` / `data['body']` are present so
    Android and iOS/web behave consistently.
    """
    from database import SessionLocal
    from models.models import DeviceToken

    db = SessionLocal()
    try:
        rows = (
            db.query(DeviceToken.token)
            .filter(DeviceToken.teacher_id == teacher_id)
            .all()
        )
        tokens = [row[0] for row in rows if row[0]]
        if not tokens:
            return 0, []

        title = str(data.get("title") or "Firduty")
        body = str(data.get("body") or "")

        success_count, invalid_tokens = send_notification_to_tokens(
            tokens=tokens,
            title=title,
            body=body,
            data=data,
        )

        if invalid_tokens:
            (
                db.query(DeviceToken)
                .filter(DeviceToken.token.in_(invalid_tokens))
                .delete(synchronize_session=False)
            )
            db.commit()

        return success_count, invalid_tokens
    except Exception as exc:
        logger.exception("[FCM] send_data_only_notification failed: %s", exc)
        return 0, []
    finally:
        db.close()
