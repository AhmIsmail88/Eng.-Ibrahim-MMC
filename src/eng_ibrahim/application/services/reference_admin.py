"""Edit and archive every master-data list (SPEC 3.8, review F-01).

One table of definitions drives all nine lists so each gets the same rules:

* names and attributes can always be corrected;
* a code can be corrected only while nothing references it (a typo such as PUMPX);
  codes that are primary keys (units, currencies) never change;
* archiving hides an entry from new-entry forms but keeps it in history, and is refused
  while active records still use it ("prevent archiving when linked", SPEC 3.8);
* the default warehouse and the base currency are never archived.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select

from ...domain.permissions import can_edit
from ...domain.text_normalization import normalize_code
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    Asset,
    AssetCategory,
    AssetType,
    Currency,
    FailureCode,
    FailureReport,
    Location,
    MaintenanceTask,
    MeterDefinition,
    OperatingCalendar,
    Part,
    StockBalance,
    Technician,
    Unit,
    Vehicle,
    Warehouse,
    WorkOrderExternalExpense,
)
from ..dto.result import Result
from .audit import write_audit
from .auth_service import AuthUser
from .inventory_service import DEFAULT_WAREHOUSE_CODE
from .settings_service import SettingsService


@dataclass(frozen=True)
class FieldSpec:
    attr: str
    label_key: str
    kind: str = "text"  # text | int
    required: bool = False
    minimum: int = 0
    maximum: int = 100000


@dataclass(frozen=True)
class KindSpec:
    model: type
    code_attr: str
    fields: tuple[FieldSpec, ...]
    pk_is_code: bool = False  # units / currencies: the code is the primary key
    extra: tuple[str, ...] = ()  # attributes shown in the third column


@dataclass(frozen=True)
class RefRow:
    id: str
    code: str
    name: str
    extra: str
    is_active: bool
    values: dict = field(default_factory=dict)


_NAMES = (FieldSpec("name_ar", "master.name", required=True),
          FieldSpec("name_en", "master.name_en"))

KINDS: dict[str, KindSpec] = {
    "location": KindSpec(Location, "code", _NAMES, extra=("name_en",)),
    "category": KindSpec(AssetCategory, "code", _NAMES, extra=("name_en",)),
    "type": KindSpec(AssetType, "code", _NAMES, extra=("name_en",)),
    "failure_code": KindSpec(FailureCode, "code", _NAMES, extra=("group_code",)),
    "task": KindSpec(MaintenanceTask, "task_code",
                     (FieldSpec("title_ar", "master.name", required=True),
                      FieldSpec("title_en", "master.name_en"),
                      FieldSpec("estimated_min", "master.minutes", kind="int", maximum=100000)),
                     extra=("estimated_min",)),
    "unit": KindSpec(Unit, "code",
                     (FieldSpec("label_ar", "master.name", required=True),
                      FieldSpec("label_en", "master.name_en", required=True),
                      FieldSpec("dimension", "master.dimension", required=True),
                      FieldSpec("precision", "master.precision", kind="int", maximum=6)),
                     pk_is_code=True, extra=("dimension",)),
    "warehouse": KindSpec(Warehouse, "warehouse_code", _NAMES, extra=("name_en",)),
    "currency": KindSpec(Currency, "code",
                         (FieldSpec("name", "master.name", required=True),
                          FieldSpec("minor_units", "master.minor_units", kind="int",
                                    maximum=4)),
                         pk_is_code=True, extra=("minor_units",)),
    "calendar": KindSpec(OperatingCalendar, "code", _NAMES, extra=("name_en",)),
}


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


class ReferenceAdminService:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ---------------- reads ----------------
    def rows(self, kind: str) -> list[RefRow]:
        spec = KINDS[kind]
        name_attr = spec.fields[0].attr
        with self._db.session() as s:
            stmt: Any = select(spec.model).order_by(getattr(spec.model, spec.code_attr))
            result = []
            for row in s.scalars(stmt):
                extra = " · ".join(str(getattr(row, a)) for a in spec.extra
                                   if getattr(row, a) not in (None, ""))
                result.append(RefRow(
                    id=self._key(spec, row), code=getattr(row, spec.code_attr),
                    name=getattr(row, name_attr), extra=extra or "—",
                    is_active=bool(row.is_active),
                    values={f.attr: getattr(row, f.attr) for f in spec.fields}))
            return result

    def code_in_use(self, kind: str, record_id: str) -> bool:
        with self._db.session() as s:
            return self._references(s, kind, record_id, active_only=False) > 0

    # ---------------- commands ----------------
    def update(self, actor: AuthUser | None, kind: str, record_id: str,
               values: dict, code: str | None = None) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        spec = KINDS[kind]
        clean: dict = {}
        for f in spec.fields:
            if f.attr not in values:
                continue
            raw = values[f.attr]
            if f.kind == "int":
                if raw in (None, ""):
                    clean[f.attr] = None
                    continue
                try:
                    number = int(raw)
                except (TypeError, ValueError):
                    return Result.failure("err.number_invalid")
                if not f.minimum <= number <= f.maximum:
                    return Result.failure("err.number_invalid")
                clean[f.attr] = number
            else:
                text = (raw or "").strip()
                if f.required and not text:
                    return Result.failure("err.name_required")
                clean[f.attr] = text or None
        with self._db.unit_of_work() as s:
            row = s.get(spec.model, record_id)
            if row is None:
                return Result.failure("err.not_found")
            before = {a: getattr(row, a) for a in clean}
            new_code = normalize_code(code) if code is not None else None
            if new_code is not None and new_code != getattr(row, spec.code_attr):
                if spec.pk_is_code:
                    return Result.failure("err.code_locked")
                if not new_code:
                    return Result.failure("err.code_required")
                if self._references(s, kind, record_id, active_only=False):
                    return Result.failure("err.code_in_use")
                column = getattr(spec.model, spec.code_attr)
                clash = select(spec.model).where(func.lower(column) == new_code.lower(),
                                                 spec.model.id != record_id)
                if kind == "failure_code":
                    clash = clash.where(FailureCode.group_code == row.group_code)
                if s.scalars(clash).first() is not None:
                    return Result.failure("err.code_exists")
                before[spec.code_attr] = getattr(row, spec.code_attr)
                setattr(row, spec.code_attr, new_code)
            if kind == "currency" and "minor_units" in clean \
                    and clean["minor_units"] != row.minor_units \
                    and self._references(s, kind, record_id, active_only=False):
                # Stored amounts are integers in minor units: changing the scale after the
                # first financial record would silently multiply or divide every amount.
                return Result.failure("err.currency_locked")
            for attr, value in clean.items():
                setattr(row, attr, value)
            write_audit(s, kind, record_id, f"{kind}_updated",
                        actor_id=actor.id if actor else None,
                        before=before,
                        after={**clean, **({spec.code_attr: getattr(row, spec.code_attr)}
                                          if spec.code_attr in before else {})})
            return Result.success()

    def set_active(self, actor: AuthUser | None, kind: str, record_id: str,
                   active: bool) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        spec = KINDS[kind]
        with self._db.unit_of_work() as s:
            row = s.get(spec.model, record_id)
            if row is None:
                return Result.failure("err.not_found")
            if bool(row.is_active) == active:
                return Result.success()
            if not active:
                if kind == "warehouse" and row.warehouse_code.upper() == DEFAULT_WAREHOUSE_CODE:
                    return Result.failure("err.archive_default")
                if kind == "currency" and row.code == SettingsService(self._db).get(
                        "currency_code", "EGP"):
                    return Result.failure("err.archive_default")
                if self._references(s, kind, record_id, active_only=True):
                    return Result.failure("err.archive_in_use")
            row.is_active = 1 if active else 0
            write_audit(s, kind, record_id, f"{kind}_{'restored' if active else 'archived'}",
                        actor_id=actor.id if actor else None)
            return Result.success()

    # ---------------- helpers ----------------
    @staticmethod
    def _key(spec: KindSpec, row) -> str:
        return getattr(row, spec.code_attr) if spec.pk_is_code else row.id

    @staticmethod
    def _references(s, kind: str, key: str, active_only: bool) -> int:
        """How many records point at this entry (active ones only, when archiving)."""
        def count(model, *conditions) -> int:
            stmt = select(func.count()).select_from(model).where(*conditions)
            if active_only and hasattr(model, "is_active"):
                stmt = stmt.where(model.is_active == 1)
            return int(s.scalar(stmt) or 0)

        if kind == "location":
            return (count(Asset, Asset.location_id == key)
                    + count(Location, Location.parent_id == key)
                    + count(Warehouse, Warehouse.location_id == key))
        if kind == "category":
            return count(Asset, Asset.category_id == key) + count(
                AssetType, AssetType.category_id == key)
        if kind == "type":
            return count(Asset, Asset.type_id == key)
        if kind == "failure_code":
            return count(FailureReport, or_(FailureReport.failure_code_id == key,
                                            FailureReport.root_cause_code_id == key))
        if kind == "task":
            return 0  # tasks are copied into plans/work orders as snapshots
        if kind == "calendar":
            return count(Asset, Asset.operating_calendar_id == key)
        if kind == "warehouse":
            if active_only:  # stock still on hand keeps a warehouse open
                quantities = s.scalars(select(StockBalance.on_hand_decimal).where(
                    StockBalance.warehouse_id == key))
                return sum(1 for q in quantities if Decimal(q or "0") != 0)
            return count(StockBalance, StockBalance.warehouse_id == key)
        if kind == "unit":
            return (count(Part, Part.unit_code == key)
                    + count(MeterDefinition, MeterDefinition.unit_code == key)
                    + count(Vehicle, Vehicle.odometer_unit == key)
                    + count(Asset, Asset.default_meter_unit == key))
        if kind == "currency":
            return (count(Part, Part.currency == key)
                    + count(StockBalance, StockBalance.currency_code == key)
                    + count(Technician, Technician.currency == key)
                    + count(Asset, Asset.currency_code == key)
                    + count(WorkOrderExternalExpense, WorkOrderExternalExpense.currency == key))
        return 0
