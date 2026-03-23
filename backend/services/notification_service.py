"""
notification_service.py — Push notification delivery for Firduty.

Delivery paths:
  platform = 'android'  → FCM via firebase-admin SDK (native token)
  platform = 'web'      → FCM Web Push via firebase-admin SDK (VAPID token)

Both paths use send_notification_to_tokens() — Firebase routes by token type.

Key guarantees (v3.2 rewrite):
  • send_notification_to_tokens() returns (success_count, failed_tokens)
  • Callers can check success_count > 0 before recording delivery
  • Invalid/expired tokens are returned so the caller can clean them from DB
  • Firebase init failure is logged clearly; every send returns 0 + all tokens failed
  • notify_duty_reminder / notify_duty_start return success_count (not None)
"""

import logging
import os
from typing import List, Optional, Tuple

import firebase_admin
from firebase_admin import credentials, messaging
from config import settings

logger = logging.getLogger(__name__)

_firebase_initialized = False
_firebase_init_attempted = False   # prevent repeated noisy warnings


# ── Firebase initialisation ───────────────────────────────────────────────────

def _init_firebase() -> None:
    global _firebase_initialized, _firebase_init_attempted

    if _firebase_initialized:
        return

    if _firebase_init_attempted:
        # Already tried and failed — don't spam the logs on every notification
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
        # Guard against duplicate-app error on hot reload / test environments
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
    """Return {title, body} for the given template + language."""
    lang = lang if lang in ("ar", "en") else "ar"
    tmpl: dict = TEMPLATES.get(template_key, {}).get(lang, {})
    return {
        "title": tmpl.get("title", "Duty Roster"),
        "body":  tmpl.get("body", "").format(**kwargs),
    }


# ── Core FCM sender ───────────────────────────────────────────────────────────

def send_notification_to_tokens(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> Tuple[int, List[str]]:
    """
    Send a DATA-ONLY FCM multicast push notification.

    Returns:
        (success_count, failed_tokens)

    Notes:
    - No top-level notification payload is sent.
    - Client platforms are responsible for rendering the notification locally.
    - This prevents duplicate OS + app + service-worker rendering.
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

    payload_data = {
        "title": title,
        "body": body,
        **{k: str(v) for k, v in (data or {}).items()},
    }

    web_base_url = (
        os.getenv("WEB_APP_URL")
        or os.getenv("APP_BASE_URL")
        or "https://naval-donnamarie-firduty-6e288803.koyeb.app"
    ).rstrip("/")

    message = messaging.MulticastMessage(
        tokens=unique_tokens,
        data=payload_data,
        android=messaging.AndroidConfig(
            priority="high",
            data=payload_data,
        ),
        apns=messaging.APNSConfig(
            headers={
                "apns-priority": "10",
                "apns-push-type": "background",
            },
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    content_available=True,
                )
            ),
        ),
        webpush=messaging.WebpushConfig(
            headers={
                "Urgency": "high",
            },
            data=payload_data,
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
            logger.debug("[FCM] ✓ token[%d] accepted", idx)
        else:
            err = result.exception
            err_code = getattr(err, "code", "") or ""
            err_msg = str(err) if err else "unknown error"
            logger.warning(
                "[FCM] ✗ token[%d] failed — code=%s msg=%s",
                idx, err_code, err_msg,
            )
            if err_code in invalid_codes:
                failed_tokens.append(token)

    logger.info(
        "[FCM] Data-only multicast result: %d/%d succeeded, %d invalid tokens to remove",
        response.success_count,
        len(unique_tokens),
        len(failed_tokens),
    )

    return response.success_count, failed_tokens

def remove_invalid_tokens(db, failed_tokens: List[str]) -> None:
    """
    Delete invalid/expired FCM tokens from the device_tokens table.
    Called by duty_reminders after a send reports failed tokens.
    """
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
    """Notify a teacher that their weekly schedule was updated. Returns success_count."""
    text = get_notification_text("updated", lang)
    success, _ = send_notification_to_tokens(
        teacher_tokens, text["title"], text["body"],
        data={"type": "schedule_updated"},
    )
    return success


def notify_duty_reminder(
    teacher_tokens: List[str],
    lang: str,
    shift: str,
    duty_type: str = "morning_endofday",
    location: Optional[str] = None,
    grade_class: Optional[str] = None,
    assignment_id: Optional[int] = None,
    teacher_id: Optional[int] = None,
) -> Tuple[int, List[str]]:
    """
    Send 15-minute reminder before a duty.
    Returns (success_count, failed_tokens).
    """
    if duty_type == "break" and grade_class:
        text = get_notification_text(
            "reminder_break", lang, shift=shift, grade_class=grade_class
    )
        data: dict = {
            "type": "duty_reminder",
            "duty_type": "break",
            "assignment_id": assignment_id or "",
            "teacher_id": teacher_id or "",
    }
    else:
        text = get_notification_text(
            "reminder_location", lang, shift=shift, location=location or ""
    )
    data = {
        "type": "duty_reminder",
        "duty_type": "morning_endofday",
        "assignment_id": assignment_id or "",
        "teacher_id": teacher_id or "",
    }


def notify_duty_start(
    teacher_tokens: List[str],
    lang: str,
    duty_type: str = "morning_endofday",
    location: Optional[str] = None,
    grade_class: Optional[str] = None,
    assignment_id: Optional[int] = None,
    teacher_id: Optional[int] = None,
) -> Tuple[int, List[str]]:
    """
    Notify teacher that their duty has started.
    Returns (success_count, failed_tokens).
    """
    if duty_type == "break" and grade_class:
        text = get_notification_text("start_break", lang, grade_class=grade_class)
        data: dict = {
            "type": "duty_start",
            "duty_type": "break",
            "assignment_id": assignment_id or "",
            "teacher_id": teacher_id or "",
        }
    else:
        text = get_notification_text(
            "start_location", lang, location=location or ""
        )
        data = {
            "type": "duty_start",
            "duty_type": "morning_endofday",
            "assignment_id": assignment_id or "",
            "teacher_id": teacher_id or "",
        }