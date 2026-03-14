"""
seed_data.py — Insert required master data (shifts + locations + grade classes).

Safe to run multiple times.
Used automatically by main.py on startup.
"""

from datetime import time
import logging

from models.models import Shift, Location, GradeClass

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
    ("Waiting room", "غرفة الانتظار"),
    ("Glass door", "الباب الزجاجي"),
    ("Stairs - KG", "السلالم - KG"),
    ("Basement floor", "القبو"),
    ("First floor", "الطابق الأول"),
    ("Second floor", "الطابق الثاني"),
]


# ─────────────────────────────────────────
# GRADE CLASSES
# ─────────────────────────────────────────

GRADE_CLASSES = [
    ("1/A", "1/A"),
    ("1/B", "1/B"),
    ("1/C", "1/C"),
    ("1/D", "1/D"),
    ("2/A", "2/A"),
    ("2/B", "2/B"),
    ("2/C", "2/C"),
    ("2/D", "2/D"),
    ("3/A", "3/A"),
    ("3/B", "3/B"),
    ("3/C", "3/C"),
    ("4/A", "4/A"),
    ("4/B", "4/B"),
    ("4/C", "4/C"),
    ("5/A", "5/A"),
    ("5/B", "5/B"),
    ("6/A", "6/A"),
    ("6/B", "6/B"),
    ("7/A", "7/A"),
    ("7/B", "7/B"),
    ("8/AB", "8/AB"),
    ("9", "9"),
]


def seed_shifts(db):
    logger.info("Starting seed_shifts...")
    created = 0
    updated = 0
    try:
        for data in SHIFTS:
            logger.info(f"Processing shift: {data['name_en']}")
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
    except Exception:
        logger.exception("Error while seeding shifts.")
        raise


def seed_locations(db):
    logger.info("Starting seed_locations...")
    created = 0
    updated = 0
    try:
        for index, (name_en, name_ar) in enumerate(LOCATIONS):
            logger.info(f"Processing location: {name_en}")
            existing = db.query(Location).filter(Location.name_en == name_en).first()
            if not existing:
                db.add(Location(name_en=name_en, name_ar=name_ar, order=index))
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
    except Exception:
        logger.exception("Error while seeding locations.")
        raise


def seed_grade_classes(db):
    logger.info("Starting seed_grade_classes...")
    created = 0
    updated = 0
    try:
        for index, (name_en, name_ar) in enumerate(GRADE_CLASSES):
            logger.info(f"Processing grade class: {name_en}")
            existing = db.query(GradeClass).filter(GradeClass.name_en == name_en).first()
            if not existing:
                db.add(GradeClass(name_en=name_en, name_ar=name_ar, order=index, active=True))
                created += 1
                continue

            changed = False
            if existing.name_ar != name_ar:
                existing.name_ar = name_ar
                changed = True
            if existing.order != index:
                existing.order = index
                changed = True
            if not existing.active:
                existing.active = True
                changed = True
            if changed:
                updated += 1
        logger.info(f"Grade classes seeded → created={created}, updated={updated}")
    except Exception:
        logger.exception("Error while seeding grade classes.")
        raise
