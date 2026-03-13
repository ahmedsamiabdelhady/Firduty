"""
seed_data.py — Insert required master data (shifts + locations).

Safe to run multiple times.
Used automatically by main.py on startup.
"""

from datetime import time
import logging

from models.models import Shift, Location

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# SHIFTS
# ─────────────────────────────────────────

SHIFTS = [
    {
        "name_en": "Morning Duty",
        "name_ar": "المناوبة الصباحية",
        "start_time": time(7, 0),
        "end_time": time(7, 40),
        "order": 0,
        "duty_type": "morning_endofday",
    },
    {
        "name_en": "First Break",
        "name_ar": "البريك الأول",
        "start_time": time(9, 0),
        "end_time": time(9, 20),
        "order": 1,
        "duty_type": "break",
    },
    {
        "name_en": "Second Break",
        "name_ar": "البريك الثاني",
        "start_time": time(10, 40),
        "end_time": time(11, 0),
        "order": 2,
        "duty_type": "break",
    },
    {
        "name_en": "End of Day Duty",
        "name_ar": "المناوبة المسائية",
        "start_time": time(13, 30),
        "end_time": time(14, 0),
        "order": 3,
        "duty_type": "morning_endofday",
    },
]


# ─────────────────────────────────────────
# LOCATIONS
# ─────────────────────────────────────────

LOCATIONS = [
    # Morning duty
    ("First floor - Interior corridor", "الطابق الأول - الممر الداخلي"),
    ("First floor - Main corridor", "الطابق الأول - الممر الرئيسي"),
    ("First floor - Beside teachers room", "الطابق الأول - بجانب غرفة المعلمين"),
    ("Area A", "المنطقة A"),
    ("Area B", "المنطقة B"),
    ("Area C", "المنطقة C"),
    ("Area D", "المنطقة D"),
    ("Second floor - Interior corridor", "الطابق الثاني - الممر الداخلي"),
    ("Second floor - Main corridor", "الطابق الثاني - الممر الرئيسي"),
    ("Second floor - Beside teachers room", "الطابق الثاني - بجانب غرفة المعلمين"),
    ("Play ground", "الملعب"),
    ("Ground floor", "الطابق الأرضي"),
    ("Ground floor / KG2A", "الطابق الأرضي / KG2A"),
    ("General supervision", "إشراف عام"),

    # End of day
    ("Waiting room", "غرفة الانتظار"),
    ("Glass door", "الباب الزجاجي"),
    ("Stairs - KG", "السلالم - KG"),
    ("Basement floor", "القبو"),
    ("First floor", "الطابق الأول"),
    ("Second floor", "الطابق الثاني"),
]


# ─────────────────────────────────────────
# Seed Shifts
# ─────────────────────────────────────────

def seed_shifts(db):
    created = 0
    updated = 0

    for data in SHIFTS:
        existing = db.query(Shift).filter(Shift.name_en == data["name_en"]).first()

        if not existing:
            db.add(Shift(**data))
            created += 1
            continue

        changed = False

        if existing.name_ar != data["name_ar"]:
            existing.name_ar = data["name_ar"]
            changed = True

        if existing.start_time != data["start_time"]:
            existing.start_time = data["start_time"]
            changed = True

        if existing.end_time != data["end_time"]:
            existing.end_time = data["end_time"]
            changed = True

        if existing.order != data["order"]:
            existing.order = data["order"]
            changed = True

        if existing.duty_type != data["duty_type"]:
            existing.duty_type = data["duty_type"]
            changed = True

        if changed:
            updated += 1

    logger.info(f"Shifts seeded → created={created}, updated={updated}")


# ─────────────────────────────────────────
# Seed Locations
# ─────────────────────────────────────────

def seed_locations(db):
    created = 0
    updated = 0

    for index, (name_en, name_ar) in enumerate(LOCATIONS):
        existing = db.query(Location).filter(Location.name_en == name_en).first()

        if not existing:
            db.add(
                Location(
                    name_en=name_en,
                    name_ar=name_ar,
                    order=index
                )
            )
            created += 1
            continue

        changed = False

        if existing.name_ar != name_ar:
            existing.name_ar = name_ar
            changed = True

        if existing.order != index:
            existing.order = index
            changed = True

        if changed:
            updated += 1

    logger.info(f"Locations seeded → created={created}, updated={updated}")