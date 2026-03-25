from __future__ import annotations

import logging
from typing import List, Tuple
from firebase_admin import messaging

from database import SessionLocal
from models.models import DeviceToken

import firebase_admin
from firebase_admin import credentials
import os
import json

# ✅ Ensure Firebase initialized once
if not firebase_admin._apps:
    creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")

    if creds_json:
        cred = credentials.Certificate(json.loads(creds_json))
        firebase_admin.initialize_app(cred)
    else:
        firebase_admin.initialize_app()

logger = logging.getLogger("services.notification_service")


def _split_tokens_by_platform(tokens: List[DeviceToken]):
    android = []
    web = []

    for t in tokens:
        if t.platform == "android":
            android.append(t.token)
        else:
            web.append(t.token)

    return android, web


def send_notification(teacher_id: int, data: dict) -> Tuple[int, List[str]]:
    db = SessionLocal()
    try:
        tokens = (
            db.query(DeviceToken)
            .filter(DeviceToken.teacher_id == teacher_id)
            .all()
        )

        if not tokens:
            return 0, []

        android_tokens, web_tokens = _split_tokens_by_platform(tokens)

        success_total = 0
        invalid_tokens = []

        # ✅ ANDROID → DATA ONLY
        if android_tokens:
            message = messaging.MulticastMessage(
                data={k: str(v) for k, v in data.items()},
                tokens=android_tokens,
            )

            response = messaging.send_each_for_multicast(message)

            success_total += response.success_count

            for i, resp in enumerate(response.responses):
                if not resp.success:
                    invalid_tokens.append(android_tokens[i])

        # ✅ WEB / iOS PWA → NOTIFICATION + DATA
        if web_tokens:
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=data.get("title", "Firduty"),
                    body=data.get("body", ""),
                ),
                data={k: str(v) for k, v in data.items()},
                tokens=web_tokens,
            )

            response = messaging.send_each_for_multicast(message)

            success_total += response.success_count

            for i, resp in enumerate(response.responses):
                if not resp.success:
                    invalid_tokens.append(web_tokens[i])

        logger.info(f"[FCM] sent={success_total}")

        return success_total, invalid_tokens

    finally:
        db.close()