"""Read models for assets and lookups (Qt-free, no ORM objects leave the layer)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Lookup:
    id: str
    code: str
    name_ar: str
    name_en: str | None = None

    def label(self, arabic: bool) -> str:
        primary, secondary = (self.name_ar, self.name_en) if arabic else (self.name_en, self.name_ar)
        return f"{self.code} — {primary or secondary or self.code}"


@dataclass(frozen=True)
class AssetRow:
    id: str
    code: str
    name_ar: str
    name_en: str | None
    category: str
    location: str
    status: str
    criticality: str
    is_active: bool

    def name(self, arabic: bool) -> str:
        return (self.name_ar if arabic else self.name_en) or self.name_ar


@dataclass(frozen=True)
class AssetInput:
    asset_code: str
    asset_name_ar: str
    category_id: str
    location_id: str
    asset_name_en: str | None = None
    type_id: str | None = None
    parent_asset_id: str | None = None
    operating_calendar_id: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    criticality: str = "Medium"
    operational_status: str = "In Service"
    asset_condition: str = "Unassessed"
    maintenance_strategy: str = "PM"
    meter_type: str = "None"
    default_meter_unit: str | None = None
    commissioning_date: str | None = None
    purchase_date: str | None = None
    purchase_cost_minor: int | None = None
    replacement_cost_minor: int | None = None
    currency_code: str | None = None
    warranty_expiry: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class SpecRow:
    key: str
    value: str
    unit_code: str | None = None


@dataclass(frozen=True)
class MeterRow:
    id: str
    code: str
    kind: str
    unit_code: str
    latest_value: str | None
    latest_at: str | None


@dataclass(frozen=True)
class ReadingRow:
    id: str
    meter_code: str
    value: str
    unit_code: str
    reading_at: str
    quality: str
    notes: str | None


@dataclass(frozen=True)
class HistoryRow:
    kind: str  # status | location | created | spec
    at: str
    title: str
    detail: str = ""
    actor_id: str | None = None


@dataclass(frozen=True)
class AssetDetail:
    id: str
    code: str
    name_ar: str
    name_en: str | None
    category_id: str
    category_name: str
    type_id: str | None
    type_name: str | None
    location_id: str
    location_name: str
    parent_asset_id: str | None
    parent_code: str | None
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    criticality: str
    operational_status: str
    asset_condition: str
    maintenance_strategy: str
    meter_type: str
    default_meter_unit: str | None
    commissioning_date: str | None
    purchase_date: str | None
    purchase_cost_minor: int | None
    replacement_cost_minor: int | None
    currency_code: str | None
    warranty_expiry: str | None
    notes: str | None
    is_active: bool
    specs: list[SpecRow] = field(default_factory=list)
    meters: list[MeterRow] = field(default_factory=list)
    readings: list[ReadingRow] = field(default_factory=list)
    history: list[HistoryRow] = field(default_factory=list)
