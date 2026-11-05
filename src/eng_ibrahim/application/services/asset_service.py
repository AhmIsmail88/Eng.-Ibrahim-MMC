"""Asset registry: create/update/archive, location & status history, search (SPEC 5)."""
from __future__ import annotations

import builtins
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from ...domain.permissions import can_edit
from ...domain.text_normalization import normalize_code, normalize_search, search_pattern
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    Asset,
    AssetCategory,
    AssetLocationHistory,
    AssetSpecification,
    AssetStatusHistory,
    AssetType,
    Location,
    MeterDefinition,
    MeterReading,
)
from ...infrastructure.database.orm_models.base import utcnow_iso
from ...infrastructure.database.orm_models.operations import (
    CONDITION,
    CRITICALITY,
    METER_TYPE,
    OPERATIONAL_STATUS,
    STRATEGY,
)
from ..dto.asset import (
    AssetDetail,
    AssetInput,
    AssetRow,
    HistoryRow,
    MeterRow,
    ReadingRow,
    SpecRow,
)
from ..dto.result import Result
from .audit import write_audit
from .auth_service import AuthUser


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


def _today() -> str:
    return date.today().isoformat()


class AssetService:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ---------------- reads ----------------
    def list(self, query: str = "", category_id: str | None = None,
             location_id: str | None = None, status: str | None = None,
             include_archived: bool = False) -> builtins.list[AssetRow]:
        with self._db.session() as s:
            stmt = (
                select(Asset, AssetCategory, Location)
                .join(AssetCategory, Asset.category_id == AssetCategory.id)
                .join(Location, Asset.location_id == Location.id)
                .order_by(func.lower(Asset.asset_code))
            )
            if not include_archived:
                stmt = stmt.where(Asset.is_active == 1)
            if category_id:
                stmt = stmt.where(Asset.category_id == category_id)
            if location_id:
                stmt = stmt.where(Asset.location_id == location_id)
            if status:
                stmt = stmt.where(Asset.operational_status == status)
            term = search_pattern(query)
            if term:
                stmt = stmt.where(or_(
                    Asset.search_norm.like(f"%{term}%", escape="\\"),
                    func.lower(func.trim(Asset.asset_code)).like(f"%{term}%", escape="\\"),
                ))
            rows = s.execute(stmt).all()
            return [
                AssetRow(
                    id=a.id, code=a.asset_code,
                    name_ar=a.asset_name_ar, name_en=a.asset_name_en,
                    category=c.name_ar, location=loc.name_ar,
                    status=a.operational_status, criticality=a.criticality,
                    is_active=bool(a.is_active),
                )
                for a, c, loc in rows
            ]

    def detail(self, asset_id: str) -> AssetDetail | None:
        with self._db.session() as s:
            row = s.get(Asset, asset_id)
            if row is None:
                return None
            category = s.get(AssetCategory, row.category_id)
            location = s.get(Location, row.location_id)
            asset_type = s.get(AssetType, row.type_id) if row.type_id else None
            parent = s.get(Asset, row.parent_asset_id) if row.parent_asset_id else None
            specs = [
                SpecRow(key=sp.spec_key, value=sp.value_text or sp.value_number_text or "",
                        unit_code=sp.unit_code)
                for sp in s.scalars(select(AssetSpecification)
                                    .where(AssetSpecification.asset_id == asset_id)
                                    .order_by(AssetSpecification.spec_key))
            ]
            meters: builtins.list[MeterRow] = []
            meter_by_id: dict[str, MeterDefinition] = {}
            for m in s.scalars(select(MeterDefinition)
                               .where(MeterDefinition.asset_id == asset_id)
                               .order_by(MeterDefinition.meter_code)):
                meter_by_id[m.id] = m
                last = s.scalars(
                    select(MeterReading)
                    .where(MeterReading.meter_id == m.id, MeterReading.quality != "rejected")
                    .order_by(MeterReading.reading_at.desc()).limit(1)
                ).first()
                meters.append(MeterRow(id=m.id, code=m.meter_code, kind=m.kind,
                                       unit_code=m.unit_code,
                                       latest_value=last.value_decimal if last else None,
                                       latest_at=last.reading_at if last else None))
            readings = []
            for r in s.scalars(select(MeterReading)
                               .where(MeterReading.asset_id == asset_id)
                               .order_by(MeterReading.reading_at.desc()).limit(100)):
                meter = meter_by_id.get(r.meter_id)
                readings.append(ReadingRow(
                    id=r.id, meter_code=meter.meter_code if meter else "",
                    value=r.value_decimal, unit_code=meter.unit_code if meter else "",
                    reading_at=r.reading_at, quality=r.quality, notes=r.notes))
            history: builtins.list[HistoryRow] = []
            for h in s.scalars(select(AssetStatusHistory)
                               .where(AssetStatusHistory.asset_id == asset_id)
                               .order_by(AssetStatusHistory.changed_at.desc())):
                history.append(HistoryRow(kind="status", at=h.changed_at, title=h.new_status,
                                          detail=h.reason or "", actor_id=h.actor_id))
            for move in s.scalars(select(AssetLocationHistory)
                               .where(AssetLocationHistory.asset_id == asset_id)
                               .order_by(AssetLocationHistory.moved_at.desc())):
                to_loc = s.get(Location, move.to_location_id)
                history.append(HistoryRow(kind="location", at=move.moved_at,
                                          title=to_loc.name_ar if to_loc else "",
                                          detail=move.reason or "", actor_id=move.actor_id))
            history.sort(key=lambda x: x.at, reverse=True)
            return AssetDetail(
                id=row.id, code=row.asset_code, name_ar=row.asset_name_ar,
                name_en=row.asset_name_en, category_id=row.category_id,
                category_name=category.name_ar if category else "",
                type_id=row.type_id, type_name=asset_type.name_ar if asset_type else None,
                location_id=row.location_id, location_name=location.name_ar if location else "",
                parent_asset_id=row.parent_asset_id,
                parent_code=parent.asset_code if parent else None,
                manufacturer=row.manufacturer, model=row.model, serial_number=row.serial_number,
                criticality=row.criticality, operational_status=row.operational_status,
                asset_condition=row.asset_condition,
                maintenance_strategy=row.maintenance_strategy, meter_type=row.meter_type,
                default_meter_unit=row.default_meter_unit,
                commissioning_date=row.commissioning_date, purchase_date=row.purchase_date,
                purchase_cost_minor=row.purchase_cost_minor,
                replacement_cost_minor=row.replacement_cost_minor,
                currency_code=row.currency_code, warranty_expiry=row.warranty_expiry,
                notes=row.notes, is_active=bool(row.is_active),
                specs=specs, meters=meters, readings=readings, history=history,
            )

    # ---------------- commands ----------------
    def create(self, actor: AuthUser | None, data: AssetInput) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        try:
            with self._db.unit_of_work() as s:
                return self.create_in(s, actor, data)
        except IntegrityError:
            return Result.failure("err.asset_code_exists")

    def create_in(self, s, actor: AuthUser | None, data: AssetInput) -> Result[str]:
        """Create inside the caller's transaction (used for composite records: vehicles)."""
        error = self._validate(s, data)
        if error:
            return Result.failure(error)
        code = normalize_code(data.asset_code)
        if s.scalar(select(Asset.id).where(
                func.lower(func.trim(Asset.asset_code)) == code.lower())):
            return Result.failure("err.asset_code_exists")
        row = Asset(
            asset_code=code,
            asset_name_ar=data.asset_name_ar.strip(),
            asset_name_en=(data.asset_name_en or "").strip() or None,
            category_id=data.category_id, type_id=data.type_id,
            location_id=data.location_id, parent_asset_id=data.parent_asset_id,
            operating_calendar_id=data.operating_calendar_id,
            manufacturer=data.manufacturer, model=data.model,
            serial_number=data.serial_number, criticality=data.criticality,
            operational_status=data.operational_status,
            asset_condition=data.asset_condition,
            maintenance_strategy=data.maintenance_strategy,
            meter_type=data.meter_type, default_meter_unit=data.default_meter_unit,
            commissioning_date=data.commissioning_date,
            purchase_date=data.purchase_date,
            purchase_cost_minor=data.purchase_cost_minor,
            replacement_cost_minor=data.replacement_cost_minor,
            currency_code=data.currency_code,
            warranty_expiry=data.warranty_expiry, notes=data.notes,
            search_norm=self._norm(data),
        )
        s.add(row)
        s.flush()
        s.add(AssetStatusHistory(asset_id=row.id, old_status=None,
                                 new_status=row.operational_status,
                                 reason="created",
                                 actor_id=actor.id if actor else None))
        write_audit(s, "asset", row.id, "asset_created",
                    actor_id=actor.id if actor else None,
                    after={"code": code, "name": row.asset_name_ar})
        return Result.success(row.id)

    def update(self, actor: AuthUser | None, asset_id: str, data: AssetInput) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        try:
            with self._db.unit_of_work() as s:
                row = s.get(Asset, asset_id)
                if row is None:
                    return Result.failure("err.asset_not_found")
                error = self._validate(s, data, asset_id=asset_id)
                if error:
                    return Result.failure(error)
                code = normalize_code(data.asset_code)
                clash = s.scalar(
                    select(Asset.id).where(
                        func.lower(func.trim(Asset.asset_code)) == code.lower(),
                        Asset.id != asset_id))
                if clash:
                    return Result.failure("err.asset_code_exists")
                old_status, old_location = row.operational_status, row.location_id
                row.asset_code = code
                row.asset_name_ar = data.asset_name_ar.strip()
                row.asset_name_en = (data.asset_name_en or "").strip() or None
                row.category_id = data.category_id
                row.type_id = data.type_id
                row.location_id = data.location_id
                row.parent_asset_id = data.parent_asset_id
                row.operating_calendar_id = data.operating_calendar_id
                row.manufacturer = data.manufacturer
                row.model = data.model
                row.serial_number = data.serial_number
                row.criticality = data.criticality
                row.operational_status = data.operational_status
                row.asset_condition = data.asset_condition
                row.maintenance_strategy = data.maintenance_strategy
                row.meter_type = data.meter_type
                row.default_meter_unit = data.default_meter_unit
                row.commissioning_date = data.commissioning_date
                row.purchase_date = data.purchase_date
                row.purchase_cost_minor = data.purchase_cost_minor
                row.replacement_cost_minor = data.replacement_cost_minor
                row.currency_code = data.currency_code
                row.warranty_expiry = data.warranty_expiry
                row.notes = data.notes
                row.search_norm = self._norm(data)
                if data.operational_status != old_status:
                    s.add(AssetStatusHistory(asset_id=row.id, old_status=old_status,
                                             new_status=data.operational_status,
                                             reason="edit",
                                             actor_id=actor.id if actor else None))
                if data.location_id != old_location:
                    s.add(AssetLocationHistory(asset_id=row.id, from_location_id=old_location,
                                               to_location_id=data.location_id,
                                               reason="edit",
                                               actor_id=actor.id if actor else None))
                write_audit(s, "asset", row.id, "asset_updated",
                            actor_id=actor.id if actor else None,
                            before={"code": code, "status": old_status},
                            after={"status": data.operational_status})
                return Result.success()
        except IntegrityError:
            return Result.failure("err.asset_code_exists")

    def archive(self, actor: AuthUser | None, asset_id: str, reason: str | None = None) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            row = s.get(Asset, asset_id)
            if row is None:
                return Result.failure("err.asset_not_found")
            if not row.is_active:
                return Result.success()
            row.is_active = 0
            row.archived_at = utcnow_iso()
            write_audit(s, "asset", row.id, "asset_archived",
                        actor_id=actor.id if actor else None, reason=reason)
            return Result.success()

    def restore(self, actor: AuthUser | None, asset_id: str) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            row = s.get(Asset, asset_id)
            if row is None:
                return Result.failure("err.asset_not_found")
            row.is_active = 1
            row.archived_at = None
            write_audit(s, "asset", row.id, "asset_restored",
                        actor_id=actor.id if actor else None)
            return Result.success()

    def change_status(self, actor: AuthUser | None, asset_id: str, new_status: str,
                      reason: str | None = None) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if new_status not in OPERATIONAL_STATUS:
            return Result.failure("err.status_invalid")
        with self._db.unit_of_work() as s:
            row = s.get(Asset, asset_id)
            if row is None:
                return Result.failure("err.asset_not_found")
            if row.operational_status == new_status:
                return Result.success()
            old = row.operational_status
            row.operational_status = new_status
            s.add(AssetStatusHistory(asset_id=row.id, old_status=old, new_status=new_status,
                                     reason=reason, actor_id=actor.id if actor else None))
            write_audit(s, "asset", row.id, "asset_status_changed",
                        actor_id=actor.id if actor else None,
                        before={"status": old}, after={"status": new_status}, reason=reason)
            return Result.success()

    def move_location(self, actor: AuthUser | None, asset_id: str, to_location_id: str,
                      reason: str | None = None) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            row = s.get(Asset, asset_id)
            if row is None:
                return Result.failure("err.asset_not_found")
            target = s.get(Location, to_location_id)
            if target is None or not target.is_active:
                return Result.failure("err.location_required")
            if row.location_id == to_location_id:
                return Result.success()
            s.add(AssetLocationHistory(asset_id=row.id, from_location_id=row.location_id,
                                       to_location_id=to_location_id, reason=reason,
                                       actor_id=actor.id if actor else None))
            row.location_id = to_location_id
            write_audit(s, "asset", row.id, "asset_moved",
                        actor_id=actor.id if actor else None,
                        before={"location": to_location_id}, reason=reason)
            return Result.success()

    def set_spec(self, actor: AuthUser | None, asset_id: str, key: str, value: str,
                 unit_code: str | None = None, is_numeric: bool = False) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        key = (key or "").strip()
        if not key:
            return Result.failure("err.spec_key_required")
        with self._db.unit_of_work() as s:
            row = s.get(AssetSpecification, (asset_id, key))
            if row is None:
                row = AssetSpecification(asset_id=asset_id, spec_key=key)
                s.add(row)
            if is_numeric:
                row.value_number_text = value
                row.value_text = None
            else:
                row.value_text = value
                row.value_number_text = None
            row.unit_code = unit_code
            write_audit(s, "asset", asset_id, "asset_spec_set",
                        actor_id=actor.id if actor else None, after={"key": key})
            return Result.success()

    # ---------------- helpers ----------------
    @staticmethod
    def _norm(data: AssetInput) -> str:
        return normalize_search(" ".join(filter(None, [
            data.asset_code, data.asset_name_ar, data.asset_name_en,
            data.serial_number, data.model, data.manufacturer,
        ])))

    def _validate(self, s, data: AssetInput, asset_id: str | None = None) -> str | None:
        if not normalize_code(data.asset_code):
            return "err.asset_code_required"
        if not (data.asset_name_ar or "").strip():
            return "err.asset_name_required"
        if data.criticality not in CRITICALITY:
            return "err.criticality_invalid"
        if data.operational_status not in OPERATIONAL_STATUS:
            return "err.status_invalid"
        if data.asset_condition not in CONDITION:
            return "err.condition_invalid"
        if data.maintenance_strategy not in STRATEGY:
            return "err.strategy_invalid"
        if data.meter_type not in METER_TYPE:
            return "err.meter_type_invalid"
        if (data.purchase_cost_minor or 0) < 0 or (data.replacement_cost_minor or 0) < 0:
            return "err.cost_negative"
        category = s.get(AssetCategory, data.category_id)
        if category is None:
            return "err.category_required"
        location = s.get(Location, data.location_id)
        if location is None or not location.is_active:
            return "err.location_required"
        if data.type_id:
            asset_type = s.get(AssetType, data.type_id)
            if asset_type is None or asset_type.category_id != category.id:
                return "err.type_category_mismatch"
        if data.parent_asset_id:
            if data.parent_asset_id == asset_id:
                return "err.parent_cycle"
            if self._would_cycle(s, data.parent_asset_id, asset_id):
                return "err.parent_cycle"
        return None

    @staticmethod
    def _would_cycle(s, parent_id: str, asset_id: str | None) -> bool:
        """Walk up from the candidate parent; hitting asset_id (or a loop) is a cycle."""
        seen: set[str] = set()
        current: str | None = parent_id
        while current and len(seen) < 100:
            if current == asset_id or current in seen:
                return True
            seen.add(current)
            parent = s.get(Asset, current)
            current = parent.parent_asset_id if parent else None
        return False
