"""Read/write models for the vehicles workshop (SPEC 6, UI-007)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .maintenance import WoRow
from .preventive import PlanRow

FUEL_TYPES = ("Diesel", "Petrol", "Electric", "Hybrid", "NaturalGas", "Other")

# Document expiry states, most severe last.
DOC_OK, DOC_SOON, DOC_EXPIRED = "ok", "soon", "expired"


@dataclass(frozen=True)
class VehicleInput:
    fleet_code: str
    name_ar: str
    location_id: str
    plate_number: str | None = None
    name_en: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    vin: str | None = None
    fuel_type: str | None = None
    odometer_unit: str = "km"
    department: str | None = None
    assigned_driver: str | None = None
    maintenance_contact: str | None = None
    insurance_expiry: str | None = None
    registration_expiry: str | None = None
    notes: str | None = None
    initial_odometer: str | None = None  # create only


@dataclass(frozen=True)
class VehicleRow:
    asset_id: str
    fleet_code: str
    plate_number: str | None
    name_ar: str
    name_en: str | None
    make: str | None
    model: str | None
    odometer: str | None
    odometer_unit: str
    service_state: str | None  # worst PM state of the vehicle's active plans
    next_service: str | None
    doc_state: str | None
    status: str
    is_active: bool

    def name(self, arabic: bool) -> str:
        return (self.name_ar if arabic else self.name_en) or self.name_ar


@dataclass(frozen=True)
class ReadingRow:
    value: str
    reading_at: str
    quality: str


@dataclass(frozen=True)
class VehicleDetail:
    asset_id: str
    asset_code: str
    fleet_code: str
    name_ar: str
    name_en: str | None
    location_id: str
    location: str
    plate_number: str | None
    make: str | None
    model: str | None
    year: int | None
    vin: str | None
    fuel_type: str | None
    odometer_unit: str
    department: str | None
    assigned_driver: str | None
    maintenance_contact: str | None
    insurance_expiry: str | None
    registration_expiry: str | None
    insurance_state: str | None
    registration_state: str | None
    notes: str | None
    status: str
    is_active: bool
    odometer: str | None
    meter_id: str | None
    plans: list[PlanRow] = field(default_factory=list)
    work_orders: list[WoRow] = field(default_factory=list)
    readings: list[ReadingRow] = field(default_factory=list)
