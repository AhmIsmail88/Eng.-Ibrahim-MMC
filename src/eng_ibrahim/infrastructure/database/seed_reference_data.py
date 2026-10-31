"""Reference seed only: categories, units, currencies, failure codes, task library.
NO assets / work orders / demo data (SPEC 21.1 step 6). Idempotent by natural key."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .orm_models import (
    AssetCategory,
    AssetType,
    Currency,
    FailureCode,
    Location,
    MaintenanceTask,
    Unit,
)

CURRENCIES = [
    ("SAR", 2, "Saudi Riyal"), ("EGP", 2, "Egyptian Pound"), ("USD", 2, "US Dollar"),
    ("EUR", 2, "Euro"), ("AED", 2, "UAE Dirham"), ("QAR", 2, "Qatari Riyal"),
    ("KWD", 3, "Kuwaiti Dinar"), ("BHD", 3, "Bahraini Dinar"), ("OMR", 3, "Omani Rial"),
    ("JOD", 3, "Jordanian Dinar"),
]

# code, dimension, label_ar, label_en, precision
UNITS = [
    ("h", "time", "ساعة", "h", 1), ("min", "time", "دقيقة", "min", 0),
    ("km", "distance", "كم", "km", 0), ("m", "length", "متر", "m", 2),
    ("mm", "length", "مم", "mm", 2), ("bar", "pressure", "بار", "bar", 2),
    ("kPa", "pressure", "كيلو باسكال", "kPa", 1), ("psi", "pressure", "رطل/بوصة²", "psi", 1),
    ("C", "temperature", "°م", "°C", 1), ("V", "electrical", "فولت", "V", 1),
    ("A", "electrical", "أمبير", "A", 2), ("kW", "power", "كيلوواط", "kW", 2),
    ("m3h", "flow", "م³/ساعة", "m³/h", 2), ("rpm", "speed", "دورة/دقيقة", "rpm", 0),
    ("mms", "vibration", "مم/ث", "mm/s", 2), ("L", "volume", "لتر", "L", 2),
    ("kg", "mass", "كجم", "kg", 2), ("pcs", "count", "قطعة", "pcs", 0),
    ("set", "count", "طقم", "set", 0),
]

CATEGORIES = [
    ("PUMP", "مضخات", "Pumps"), ("MOTOR", "محركات كهربائية", "Electric Motors"),
    ("BLOWER", "بلورات", "Blowers"), ("GEN", "مولدات", "Generators"),
    ("COMP", "ضواغط", "Compressors"), ("VALVE", "محابس", "Valves"),
    ("VEH", "سيارات ومعدات متحركة", "Vehicles & Mobile Equipment"),
    ("ELEC", "لوحات ومعدات كهربائية", "Electrical Panels & Equipment"),
    ("INST", "أجهزة قياس وتحكم", "Instruments & Controls"),
    ("OTHER", "أخرى", "Other"),
]

# code, category_code, ar, en
TYPES = [
    ("PUMP-CENT", "PUMP", "مضخة طرد مركزي", "Centrifugal Pump"),
    ("PUMP-SUBM", "PUMP", "مضخة غاطسة", "Submersible Pump"),
    ("PUMP-DOSE", "PUMP", "مضخة جرعات", "Dosing Pump"),
    ("MOTOR-AC", "MOTOR", "محرك تيار متردد", "AC Motor"),
    ("BLOWER-ROOT", "BLOWER", "بلور روتس", "Roots Blower"),
    ("GEN-DIESEL", "GEN", "مولد ديزل", "Diesel Generator"),
    ("VEH-CAR", "VEH", "سيارة", "Car / Pickup"),
    ("VEH-HEAVY", "VEH", "معدة ثقيلة", "Heavy Equipment"),
    ("VALVE-GATE", "VALVE", "محبس بوابة", "Gate Valve"),
    ("OTHER-GEN", "OTHER", "معدة عامة", "General Equipment"),
]

# group, code, ar, en
FAILURE_CODES = [
    ("MECH", "BEARING", "عطل رولمان بلي", "Bearing failure"),
    ("MECH", "SEAL", "تسريب سيل ميكانيكي", "Mechanical seal leak"),
    ("MECH", "VIBRATION", "اهتزاز زائد", "Excessive vibration"),
    ("MECH", "BELT", "قطع/تلف سير", "Belt failure"),
    ("ELEC", "MOTOR-BURN", "احتراق ملفات المحرك", "Motor winding failure"),
    ("ELEC", "TRIP", "فصل حماية", "Protection trip"),
    ("ELEC", "CABLE", "تلف كابل", "Cable fault"),
    ("INST", "SENSOR", "عطل حساس", "Sensor fault"),
    ("OPER", "CLOG", "انسداد", "Blockage / clogging"),
    ("OPER", "DRY-RUN", "تشغيل على الناشف", "Dry running"),
    ("EXT", "POWER-LOSS", "انقطاع التيار", "Power loss"),
    ("OTH", "UNKNOWN", "سبب غير محدد", "Unknown"),
]

# code, ar, en, minutes
TASKS = [
    ("T-VISUAL", "فحص بصري عام", "General visual inspection", 10),
    ("T-LEAK", "فحص التسريبات", "Leak check", 10),
    ("T-NOISE", "فحص الضوضاء والاهتزاز", "Noise and vibration check", 10),
    ("T-LUBE", "تزييت / تشحيم", "Lubrication / greasing", 20),
    ("T-OILCHG", "تغيير زيت", "Oil change", 45),
    ("T-FILTER", "تغيير/تنظيف فلتر", "Replace / clean filter", 30),
    ("T-BELT", "فحص وشد السير", "Belt inspection and tension", 20),
    ("T-TERM", "فحص وتربيط التوصيلات الكهربائية", "Electrical terminals check", 20),
    ("T-AMPS", "قياس تيار التشغيل", "Measure running current", 10),
    ("T-INSUL", "قياس العزل", "Insulation resistance test", 30),
    ("T-CLEAN", "تنظيف", "Cleaning", 20),
    ("T-TEST", "تشغيل تجريبي بعد الصيانة", "Post-maintenance test run", 15),
]


def seed_reference_data(session: Session) -> dict[str, int]:
    added = dict.fromkeys(
        ("currencies", "units", "locations", "categories", "types", "failure_codes", "tasks"), 0)

    # A root location is reference data (not demo operational data): an asset must
    # belong to a location, and the admin can rename or add children later.
    if session.scalar(select(Location).where(Location.code == "MAIN")) is None:
        session.add(Location(code="MAIN", name_ar="الموقع الرئيسي", name_en="Main Site",
                             location_type="site"))
        session.flush()
        added["locations"] += 1

    for code, minor, name in CURRENCIES:
        if session.get(Currency, code) is None:
            session.add(Currency(code=code, minor_units=minor, name=name))
            added["currencies"] += 1
    for code, dim, ar, en, prec in UNITS:
        if session.get(Unit, code) is None:
            session.add(Unit(code=code, dimension=dim, label_ar=ar, label_en=en, precision=prec))
            added["units"] += 1

    cat_ids: dict[str, str] = {}
    for code, ar, en in CATEGORIES:
        existing = session.scalar(select(AssetCategory).where(AssetCategory.code == code))
        if existing is None:
            existing = AssetCategory(code=code, name_ar=ar, name_en=en)
            session.add(existing)
            session.flush()
            added["categories"] += 1
        cat_ids[code] = existing.id

    for code, cat, ar, en in TYPES:
        if session.scalar(select(AssetType).where(AssetType.code == code)) is None:
            session.add(AssetType(code=code, category_id=cat_ids[cat], name_ar=ar, name_en=en))
            added["types"] += 1

    for group, code, ar, en in FAILURE_CODES:
        q = select(FailureCode).where(FailureCode.group_code == group, FailureCode.code == code)
        if session.scalar(q) is None:
            session.add(FailureCode(group_code=group, code=code, name_ar=ar, name_en=en))
            added["failure_codes"] += 1

    for code, ar, en, minutes in TASKS:
        if session.scalar(select(MaintenanceTask).where(MaintenanceTask.task_code == code)) is None:
            session.add(MaintenanceTask(task_code=code, title_ar=ar, title_en=en,
                                        estimated_min=minutes))
            added["tasks"] += 1
    session.flush()
    return added
