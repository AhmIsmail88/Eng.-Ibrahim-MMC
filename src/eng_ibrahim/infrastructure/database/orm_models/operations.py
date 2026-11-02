"""Phase 1 operations: assets, meters, technicians, suppliers, operating calendars.

Field names follow SPEC 19.3.1 exactly (`*_id`, `*_minor`, `*_decimal`, `*_at`,
`*_date`, `*_snapshot`, `*_code`). Status/condition/strategy values are canonical
English strings stored in the DB and translated only in the UI.
"""
from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UuidPk, utcnow_iso

CRITICALITY = ("Critical", "High", "Medium", "Low")
CONDITION = ("Excellent", "Good", "Fair", "Poor", "Unassessed")
OPERATIONAL_STATUS = ("In Service", "Standby", "Out of Service", "Under Maintenance", "Retired")
STRATEGY = ("PM", "CM", "Both", "Run-to-Failure")
METER_TYPE = ("Runtime Hours", "Kilometer", "Cycle", "None")
METER_KIND = ("cumulative", "condition")
READING_SOURCE = ("manual", "imported")
READING_QUALITY = ("valid", "suspect", "rejected")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class Asset(Base, UuidPk, Timestamps):
    __tablename__ = "assets"
    asset_code: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_name_en: Mapped[str | None] = mapped_column(String(200))
    category_id: Mapped[str] = mapped_column(ForeignKey("asset_categories.id"), nullable=False)
    type_id: Mapped[str | None] = mapped_column(ForeignKey("asset_types.id"))
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)
    parent_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    operating_calendar_id: Mapped[str | None] = mapped_column(ForeignKey("operating_calendars.id"))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    serial_number: Mapped[str | None] = mapped_column(String(120))
    criticality: Mapped[str] = mapped_column(String(16), nullable=False, default="Medium")
    operational_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="In Service")
    asset_condition: Mapped[str] = mapped_column(
        String(16), nullable=False, default="Unassessed")
    maintenance_strategy: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PM")
    meter_type: Mapped[str] = mapped_column(String(16), nullable=False, default="None")
    default_meter_unit: Mapped[str | None] = mapped_column(ForeignKey("units.code"))
    commissioning_date: Mapped[str | None] = mapped_column(String(10))
    purchase_date: Mapped[str | None] = mapped_column(String(10))
    purchase_cost_minor: Mapped[int | None] = mapped_column(Integer)
    replacement_cost_minor: Mapped[int | None] = mapped_column(Integer)
    currency_code: Mapped[str | None] = mapped_column(ForeignKey("currencies.code"))
    warranty_expiry: Mapped[str | None] = mapped_column(String(10))
    notes: Mapped[str | None] = mapped_column(Text)
    search_norm: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    archived_at: Mapped[str | None] = mapped_column(String(32))
    __table_args__ = (
        CheckConstraint(f"criticality IN ({_in(CRITICALITY)})", name="criticality_valid"),
        CheckConstraint(f"asset_condition IN ({_in(CONDITION)})", name="condition_valid"),
        CheckConstraint(
            f"operational_status IN ({_in(OPERATIONAL_STATUS)})", name="status_valid"),
        CheckConstraint(f"maintenance_strategy IN ({_in(STRATEGY)})", name="strategy_valid"),
        CheckConstraint(f"meter_type IN ({_in(METER_TYPE)})", name="meter_type_valid"),
        CheckConstraint("is_active IN (0,1)", name="is_active_bool"),
        CheckConstraint("parent_asset_id IS NULL OR parent_asset_id <> id",
                        name="no_self_parent"),
        CheckConstraint("purchase_cost_minor IS NULL OR purchase_cost_minor >= 0",
                        name="purchase_cost_nonneg"),
        CheckConstraint("replacement_cost_minor IS NULL OR replacement_cost_minor >= 0",
                        name="replacement_cost_nonneg"),
    )


Index("uq_assets_code_ci", func.lower(func.trim(Asset.asset_code)), unique=True)
Index("ix_assets_category_location", Asset.category_id, Asset.location_id, Asset.is_active)
Index("ix_assets_status", Asset.operational_status)
Index("ix_assets_search_norm", Asset.search_norm)


class AssetSpecification(Base):
    __tablename__ = "asset_specifications"
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    spec_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_text: Mapped[str | None] = mapped_column(String(200))
    value_number_text: Mapped[str | None] = mapped_column(String(40))
    unit_code: Mapped[str | None] = mapped_column(ForeignKey("units.code"))


class AssetLocationHistory(Base, UuidPk):
    __tablename__ = "asset_location_history"
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)
    from_location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"))
    to_location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)
    moved_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utcnow_iso)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[str | None] = mapped_column(String(36))


Index("ix_location_history_asset", AssetLocationHistory.asset_id, AssetLocationHistory.moved_at)


class AssetStatusHistory(Base, UuidPk):
    __tablename__ = "asset_status_history"
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(24))
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    changed_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utcnow_iso)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[str | None] = mapped_column(String(36))


Index("ix_status_history_asset", AssetStatusHistory.asset_id, AssetStatusHistory.changed_at)


class Vehicle(Base):
    __tablename__ = "vehicles"
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    fleet_code: Mapped[str | None] = mapped_column(String(32), unique=True)
    plate_number: Mapped[str | None] = mapped_column(String(32))
    vin: Mapped[str | None] = mapped_column(String(32))
    year: Mapped[int | None] = mapped_column(Integer)
    fuel_type: Mapped[str | None] = mapped_column(String(24))
    insurance_expiry: Mapped[str | None] = mapped_column(String(10))
    registration_expiry: Mapped[str | None] = mapped_column(String(10))
    assigned_driver: Mapped[str | None] = mapped_column(String(120))
    odometer_unit: Mapped[str | None] = mapped_column(ForeignKey("units.code"))
    department: Mapped[str | None] = mapped_column(String(120))
    maintenance_contact: Mapped[str | None] = mapped_column(String(160))


class MeterDefinition(Base, UuidPk):
    __tablename__ = "meter_definitions"
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)
    meter_code: Mapped[str] = mapped_column(String(24), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="cumulative")
    unit_code: Mapped[str] = mapped_column(ForeignKey("units.code"), nullable=False)
    min_limit: Mapped[str | None] = mapped_column(String(40))
    max_limit: Mapped[str | None] = mapped_column(String(40))
    is_primary: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint("asset_id", "meter_code"),
        CheckConstraint(f"kind IN ({_in(METER_KIND)})", name="kind_valid"),
        CheckConstraint("is_primary IN (0,1)", name="is_primary_bool"),
    )


Index("ix_meter_definitions_asset", MeterDefinition.asset_id)


class MeterReading(Base, UuidPk):
    __tablename__ = "meter_readings"
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)
    meter_id: Mapped[str] = mapped_column(ForeignKey("meter_definitions.id"), nullable=False)
    value_decimal: Mapped[str] = mapped_column(String(40), nullable=False)
    reading_at: Mapped[str] = mapped_column(String(32), nullable=False)
    entered_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utcnow_iso)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    quality: Mapped[str] = mapped_column(String(16), nullable=False, default="valid")
    correction_of_id: Mapped[str | None] = mapped_column(ForeignKey("meter_readings.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (
        CheckConstraint(f"source IN ({_in(READING_SOURCE)})", name="source_valid"),
        CheckConstraint(f"quality IN ({_in(READING_QUALITY)})", name="quality_valid"),
    )


Index("ix_meter_readings_meter_at", MeterReading.meter_id, MeterReading.reading_at)


class Technician(Base, UuidPk, Timestamps):
    __tablename__ = "technicians"
    technician_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    trade: Mapped[str | None] = mapped_column(String(32))
    department: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))
    hourly_rate_minor: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(ForeignKey("currencies.code"))
    search_norm: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (
        CheckConstraint("is_active IN (0,1)", name="is_active_bool"),
        CheckConstraint("hourly_rate_minor IS NULL OR hourly_rate_minor >= 0",
                        name="rate_nonneg"),
    )


class Supplier(Base, UuidPk, Timestamps):
    __tablename__ = "suppliers"
    supplier_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    contact_info: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (CheckConstraint("is_active IN (0,1)", name="is_active_bool"),)


class OperatingCalendar(Base, UuidPk, Timestamps):
    __tablename__ = "operating_calendars"
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name_ar: Mapped[str] = mapped_column(String(160), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(160))
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (CheckConstraint("is_active IN (0,1)", name="is_active_bool"),)


class OperatingCalendarShift(Base):
    __tablename__ = "operating_calendar_shifts"
    calendar_id: Mapped[str] = mapped_column(
        ForeignKey("operating_calendars.id"), primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer, primary_key=True)  # 0=Sunday .. 6=Saturday
    shift_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_time_local: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM
    end_time_local: Mapped[str] = mapped_column(String(5), nullable=False)
    ends_next_day: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("shift_no >= 1", name="shift_no_positive"),
        CheckConstraint("ends_next_day IN (0,1)", name="ends_next_day_bool"),
    )


class CalendarException(Base, UuidPk):
    __tablename__ = "calendar_exceptions"
    calendar_id: Mapped[str] = mapped_column(ForeignKey("operating_calendars.id"), nullable=False)
    exception_date: Mapped[str] = mapped_column(String(10), nullable=False)  # local date
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (UniqueConstraint("calendar_id", "exception_date"),)


class CalendarExceptionShift(Base):
    __tablename__ = "calendar_exception_shifts"
    exception_id: Mapped[str] = mapped_column(
        ForeignKey("calendar_exceptions.id"), primary_key=True)
    shift_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_time_local: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time_local: Mapped[str] = mapped_column(String(5), nullable=False)
    ends_next_day: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
