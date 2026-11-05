"""Vehicles workshop (SPEC 6): a vehicle is an asset with a fleet profile and an odometer.

Creation writes the asset, its vehicle profile and its primary odometer meter in one
transaction. Service programmes are ordinary PM plans on the vehicle's asset
("every 10,000 km OR 6 months" = FIRST_DUE), so due states, generation and history
reuse the PM engine instead of a second scheduler.
"""
from __future__ import annotations

import builtins
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from ...domain.permissions import can_edit
from ...domain.policies import pm_schedule as sched
from ...domain.text_normalization import normalize_code, normalize_search, search_pattern
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    Asset,
    AssetCategory,
    Location,
    MeterDefinition,
    MeterReading,
    Unit,
    Vehicle,
)
from ..dto.asset import AssetInput
from ..dto.result import Result
from ..dto.vehicle import (
    DOC_EXPIRED,
    DOC_OK,
    DOC_SOON,
    FUEL_TYPES,
    ReadingRow,
    VehicleDetail,
    VehicleInput,
    VehicleRow,
)
from .asset_service import AssetService
from .audit import write_audit
from .auth_service import AuthUser
from .meter_service import MeterService
from .pm_service import PMService
from .work_order_service import WorkOrderService

VEHICLE_CATEGORY = "VEH"
ODOMETER_CODE = "ODO"
DOC_WARNING = timedelta(days=30)


class _Abort(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def doc_state(expiry: str | None, today: date | None = None) -> str | None:
    if not expiry:
        return None
    try:
        when = date.fromisoformat(expiry[:10])
    except ValueError:
        return None
    today = today or date.today()
    if when < today:
        return DOC_EXPIRED
    if when - today <= DOC_WARNING:
        return DOC_SOON
    return DOC_OK


def _worst_doc(*states: str | None) -> str | None:
    order = {DOC_OK: 0, DOC_SOON: 1, DOC_EXPIRED: 2}
    present = [s for s in states if s]
    return max(present, key=order.__getitem__) if present else None


class VehicleService:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ---------------- reads ----------------
    def list(self, query: str = "", alerts_only: bool = False,
             include_archived: bool = False) -> builtins.list[VehicleRow]:
        plans_by_asset = defaultdict(list)
        for plan in PMService(self._db).list():
            if plan.status == "Active":
                plans_by_asset[plan.asset_id].append(plan)
        with self._db.session() as s:
            stmt = (select(Vehicle, Asset).join(Asset, Vehicle.asset_id == Asset.id)
                    .order_by(func.lower(Vehicle.fleet_code)))
            if not include_archived:
                stmt = stmt.where(Asset.is_active == 1)
            term = search_pattern(query)
            if term:
                stmt = stmt.where(or_(
                    Asset.search_norm.like(f"%{term}%", escape="\\"),
                    func.lower(Vehicle.plate_number).like(f"%{term}%", escape="\\"),
                    func.lower(Vehicle.fleet_code).like(f"%{term}%", escape="\\"),
                ))
            rows = []
            for vehicle, asset in s.execute(stmt).all():
                plans = plans_by_asset.get(asset.id, [])
                state = sched.worst(*(p.state for p in plans)) if plans else None
                docs = _worst_doc(doc_state(vehicle.insurance_expiry),
                                  doc_state(vehicle.registration_expiry))
                row = VehicleRow(
                    asset_id=asset.id, fleet_code=vehicle.fleet_code or asset.asset_code,
                    plate_number=vehicle.plate_number, name_ar=asset.asset_name_ar,
                    name_en=asset.asset_name_en, make=asset.manufacturer, model=asset.model,
                    odometer=self._odometer(s, asset.id),
                    odometer_unit=vehicle.odometer_unit or "km",
                    service_state=state, next_service=self._next_service(plans),
                    doc_state=docs, status=asset.operational_status,
                    is_active=bool(asset.is_active))
                if alerts_only and not self._needs_attention(row):
                    continue
                rows.append(row)
            return rows

    def detail(self, asset_id: str) -> VehicleDetail | None:
        with self._db.session() as s:
            vehicle = s.get(Vehicle, asset_id)
            asset = s.get(Asset, asset_id)
            if vehicle is None or asset is None:
                return None
            location = s.get(Location, asset.location_id)
            meter_id = self._meter_id(s, asset_id)
            readings = [] if meter_id is None else [
                ReadingRow(value=r.value_decimal, reading_at=r.reading_at, quality=r.quality)
                for r in s.scalars(select(MeterReading)
                                   .where(MeterReading.meter_id == meter_id)
                                   .order_by(MeterReading.reading_at.desc()).limit(50))]
            odometer = self._odometer(s, asset_id)
            base: dict[str, Any] = dict(
                asset_id=asset.id, asset_code=asset.asset_code,
                fleet_code=vehicle.fleet_code or asset.asset_code,
                name_ar=asset.asset_name_ar, name_en=asset.asset_name_en,
                location_id=asset.location_id,
                location=location.name_ar if location else "",
                plate_number=vehicle.plate_number, make=asset.manufacturer, model=asset.model,
                year=vehicle.year, vin=vehicle.vin, fuel_type=vehicle.fuel_type,
                odometer_unit=vehicle.odometer_unit or "km", department=vehicle.department,
                assigned_driver=vehicle.assigned_driver,
                maintenance_contact=vehicle.maintenance_contact,
                insurance_expiry=vehicle.insurance_expiry,
                registration_expiry=vehicle.registration_expiry,
                insurance_state=doc_state(vehicle.insurance_expiry),
                registration_state=doc_state(vehicle.registration_expiry),
                notes=asset.notes, status=asset.operational_status,
                is_active=bool(asset.is_active), odometer=odometer, meter_id=meter_id,
                readings=readings)
        plans = [p for p in PMService(self._db).list() if p.asset_id == asset_id]
        orders = WorkOrderService(self._db).list(asset_id=asset_id)
        return VehicleDetail(**base, plans=plans, work_orders=orders)

    # ---------------- commands ----------------
    def create(self, actor: AuthUser | None, data: VehicleInput) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        error = self._validate(data)
        if error:
            return Result.failure(error)
        try:
            with self._db.unit_of_work() as s:
                category = s.scalar(select(AssetCategory).where(
                    AssetCategory.code == VEHICLE_CATEGORY))
                if category is None:
                    raise _Abort("err.vehicle_category_missing")
                if s.get(Unit, data.odometer_unit) is None:
                    raise _Abort("err.unit_invalid")
                code = normalize_code(data.fleet_code)
                if s.scalar(select(Vehicle.asset_id).where(
                        func.lower(Vehicle.fleet_code) == code.lower())):
                    raise _Abort("err.fleet_code_exists")
                created = AssetService(self._db).create_in(s, actor, AssetInput(
                    asset_code=code, asset_name_ar=data.name_ar,
                    asset_name_en=_clean(data.name_en), category_id=category.id,
                    location_id=data.location_id, manufacturer=_clean(data.make),
                    model=_clean(data.model), serial_number=_clean(data.vin),
                    meter_type="Kilometer", default_meter_unit=data.odometer_unit,
                    notes=_clean(data.notes)))
                if not created.ok or created.value is None:
                    raise _Abort(created.error_code or "err.asset_not_found")
                asset_id = created.value
                s.add(Vehicle(asset_id=asset_id, fleet_code=code, **self._profile(data)))
                self._refresh_search(s, asset_id, data)
                meter = MeterDefinition(asset_id=asset_id, meter_code=ODOMETER_CODE,
                                        kind="cumulative", unit_code=data.odometer_unit,
                                        is_primary=1)
                s.add(meter)
                s.flush()
                start = self._number(data.initial_odometer)
                if start is not None:
                    s.add(MeterReading(asset_id=asset_id, meter_id=meter.id,
                                       value_decimal=str(start),
                                       reading_at=date.today().isoformat() + "T00:00:00",
                                       source="manual", quality="valid",
                                       notes="initial", actor_id=actor.id if actor else None))
                write_audit(s, "vehicle", asset_id, "vehicle_created",
                            actor_id=actor.id if actor else None,
                            after={"fleet_code": code, "plate": _clean(data.plate_number)})
                return Result.success(asset_id)
        except _Abort as exc:
            return Result.failure(exc.code)
        except IntegrityError:
            return Result.failure("err.fleet_code_exists")

    def update(self, actor: AuthUser | None, asset_id: str,
               data: VehicleInput) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        error = self._validate(data)
        if error:
            return Result.failure(error)
        try:
            with self._db.unit_of_work() as s:
                vehicle = s.get(Vehicle, asset_id)
                asset = s.get(Asset, asset_id)
                if vehicle is None or asset is None:
                    return Result.failure("err.vehicle_not_found")
                if s.get(Location, data.location_id) is None:
                    return Result.failure("err.location_required")
                code = normalize_code(data.fleet_code)
                clash = s.scalar(select(Vehicle.asset_id).where(
                    func.lower(Vehicle.fleet_code) == code.lower(),
                    Vehicle.asset_id != asset_id))
                asset_clash = s.scalar(select(Asset.id).where(
                    func.lower(func.trim(Asset.asset_code)) == code.lower(),
                    Asset.id != asset_id))
                if clash or asset_clash:
                    return Result.failure("err.fleet_code_exists")
                before = {"fleet_code": vehicle.fleet_code, "plate": vehicle.plate_number}
                vehicle.fleet_code = code
                for key, value in self._profile(data).items():
                    if key != "odometer_unit":  # the meter's unit is fixed once readings exist
                        setattr(vehicle, key, value)
                asset.asset_code = code
                asset.asset_name_ar = data.name_ar.strip()
                asset.asset_name_en = _clean(data.name_en)
                asset.location_id = data.location_id
                asset.manufacturer = _clean(data.make)
                asset.model = _clean(data.model)
                asset.serial_number = _clean(data.vin)
                asset.notes = _clean(data.notes)
                self._refresh_search(s, asset_id, data)
                write_audit(s, "vehicle", asset_id, "vehicle_updated",
                            actor_id=actor.id if actor else None, before=before,
                            after={"fleet_code": code, "plate": vehicle.plate_number})
                return Result.success()
        except IntegrityError:
            return Result.failure("err.fleet_code_exists")

    def add_odometer(self, actor: AuthUser | None, asset_id: str, value: str,
                     reading_at: str, notes: str | None = None,
                     correction_reason: str | None = None) -> Result[str]:
        """Same rules as any cumulative meter: a lower value needs a documented correction,
        which replaces the last reading (`correction_reason` given)."""
        with self._db.session() as s:
            meter_id = self._meter_id(s, asset_id)
        if meter_id is None:
            return Result.failure("err.vehicle_not_found")
        meters = MeterService(self._db)
        if correction_reason is not None:
            return meters.correct_last_reading(actor, asset_id, meter_id, value, reading_at,
                                               correction_reason)
        return meters.add_reading(actor, asset_id, meter_id, value, reading_at, notes=notes)

    def add_service_plan(self, actor: AuthUser | None, asset_id: str, title: str,
                         every_km: str | None, every_months: int | None,
                         tasks: builtins.list[tuple[str, bool]] | None = None) -> Result[str]:
        """'Every N km OR every M months, whichever comes first' (SPEC 6.3)."""
        km = self._number(every_km)
        months = every_months if every_months and every_months > 0 else None
        if km is None and months is None:
            return Result.failure("err.vehicle_plan_interval")
        with self._db.session() as s:
            meter_id = self._meter_id(s, asset_id)
            odometer = self._odometer(s, asset_id)
        if km is not None and meter_id is None:
            return Result.failure("err.vehicle_not_found")
        policy = "FIRST_DUE" if km and months else ("METER_ONLY" if km else "DATE_ONLY")
        strategy = "Hybrid" if km and months else ("Meter" if km else "Calendar")
        return PMService(self._db).create(
            actor, asset_id=asset_id, title=title, strategy=strategy, trigger_policy=policy,
            calendar_interval_value=months, calendar_interval_unit="months" if months else None,
            meter_id=meter_id if km else None,
            meter_interval_value=str(km) if km else None,
            base_meter_value=(odometer or "0") if km else None,
            warning_meter=str((km * Decimal("0.1")).quantize(Decimal(1))) if km else None,
            tasks=tasks)

    # ---------------- helpers ----------------
    @staticmethod
    def _validate(data: VehicleInput) -> str | None:
        if not normalize_code(data.fleet_code):
            return "err.fleet_code_required"
        if not (data.name_ar or "").strip():
            return "err.asset_name_required"
        if not data.location_id:
            return "err.location_required"
        if data.fuel_type and data.fuel_type not in FUEL_TYPES:
            return "err.fuel_type_invalid"
        if data.year is not None and not (1950 <= data.year <= date.today().year + 1):
            return "err.vehicle_year_invalid"
        for value in (data.insurance_expiry, data.registration_expiry):
            if value:
                try:
                    date.fromisoformat(value)
                except ValueError:
                    return "err.date_invalid"
        if data.initial_odometer not in (None, "") and \
                VehicleService._number(data.initial_odometer) is None:
            return "err.meter_value_invalid"
        return None

    @staticmethod
    def _profile(data: VehicleInput) -> dict:
        return dict(plate_number=_clean(data.plate_number), vin=_clean(data.vin),
                    year=data.year, fuel_type=data.fuel_type or None,
                    insurance_expiry=_clean(data.insurance_expiry),
                    registration_expiry=_clean(data.registration_expiry),
                    assigned_driver=_clean(data.assigned_driver),
                    department=_clean(data.department),
                    maintenance_contact=_clean(data.maintenance_contact),
                    odometer_unit=data.odometer_unit)

    @staticmethod
    def _refresh_search(s, asset_id: str, data: VehicleInput) -> None:
        """The plate is searchable from every asset list, not only from this screen."""
        asset = s.get(Asset, asset_id)
        asset.search_norm = normalize_search(" ".join(filter(None, [
            normalize_code(data.fleet_code), data.name_ar, data.name_en, data.plate_number,
            data.make, data.model, data.vin, data.assigned_driver])))

    @staticmethod
    def _number(value: str | None) -> Decimal | None:
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            return None
        return number if number.is_finite() and number >= 0 else None

    @staticmethod
    def _meter_id(s, asset_id: str) -> str | None:
        return s.scalar(select(MeterDefinition.id).where(
            MeterDefinition.asset_id == asset_id,
            MeterDefinition.is_primary == 1).limit(1))

    def _odometer(self, s, asset_id: str) -> str | None:
        meter_id = self._meter_id(s, asset_id)
        if meter_id is None:
            return None
        return s.scalar(select(MeterReading.value_decimal)
                        .where(MeterReading.meter_id == meter_id,
                               MeterReading.quality != "rejected")
                        .order_by(MeterReading.reading_at.desc()).limit(1))

    @staticmethod
    def _next_service(plans) -> str | None:
        """The nearest threshold across plans: an ISO date and/or a meter value."""
        dates = sorted(p.next_due_date for p in plans if p.next_due_date)
        meters = sorted(Decimal(p.next_due_meter) for p in plans if p.next_due_meter)
        parts = []
        if meters:
            nearest = meters[0]
            parts.append(f"{int(nearest):,}" if nearest == nearest.to_integral_value()
                         else f"{nearest:,}")
        if dates:
            parts.append(dates[0])
        return " / ".join(parts) or None

    @staticmethod
    def _needs_attention(row: VehicleRow) -> bool:
        return (row.service_state in (sched.DUE_SOON, sched.DUE, sched.OVERDUE)
                or row.doc_state in (DOC_SOON, DOC_EXPIRED))
