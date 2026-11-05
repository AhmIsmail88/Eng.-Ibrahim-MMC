"""Reference lookups and simple master-data commands (SPEC 4, ADR-025 permissions)."""
from __future__ import annotations

from sqlalchemy import func, select

from ...domain.permissions import can_edit
from ...domain.text_normalization import normalize_code, normalize_search
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    AssetCategory,
    AssetType,
    Currency,
    FailureCode,
    Location,
    MaintenanceTask,
    OperatingCalendar,
    OperatingCalendarShift,
    Supplier,
    Technician,
    Unit,
    Warehouse,
)
from ..dto.asset import Lookup
from ..dto.result import Result
from .audit import write_audit
from .auth_service import AuthUser


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


def _lookup(row) -> Lookup:
    return Lookup(id=row.id, code=row.code, name_ar=row.name_ar, name_en=row.name_en)


class MasterDataService:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ---------------- reads ----------------
    def locations(self, active_only: bool = True) -> list[Lookup]:
        with self._db.session() as s:
            stmt = select(Location).order_by(Location.code)
            if active_only:
                stmt = stmt.where(Location.is_active == 1)
            return [_lookup(r) for r in s.scalars(stmt)]

    def categories(self, active_only: bool = True) -> list[Lookup]:
        with self._db.session() as s:
            stmt = select(AssetCategory).order_by(AssetCategory.code)
            if active_only:
                stmt = stmt.where(AssetCategory.is_active == 1)
            return [_lookup(r) for r in s.scalars(stmt)]

    def types(self, category_id: str | None = None, active_only: bool = True) -> list[Lookup]:
        with self._db.session() as s:
            stmt = select(AssetType).order_by(AssetType.code)
            if active_only:
                stmt = stmt.where(AssetType.is_active == 1)
            if category_id:
                stmt = stmt.where(AssetType.category_id == category_id)
            return [_lookup(r) for r in s.scalars(stmt)]

    def technicians(self, active_only: bool = True) -> list[Lookup]:
        with self._db.session() as s:
            stmt = select(Technician).order_by(Technician.technician_code)
            if active_only:
                stmt = stmt.where(Technician.is_active == 1)
            return [Lookup(id=r.id, code=r.technician_code, name_ar=r.full_name) for r in s.scalars(stmt)]

    def suppliers(self, active_only: bool = True) -> list[Lookup]:
        with self._db.session() as s:
            stmt = select(Supplier).order_by(Supplier.supplier_code)
            if active_only:
                stmt = stmt.where(Supplier.is_active == 1)
            return [Lookup(id=r.id, code=r.supplier_code, name_ar=r.name) for r in s.scalars(stmt)]

    def calendars(self, active_only: bool = True) -> list[Lookup]:
        with self._db.session() as s:
            stmt = select(OperatingCalendar).order_by(OperatingCalendar.code)
            if active_only:
                stmt = stmt.where(OperatingCalendar.is_active == 1)
            return [_lookup(r) for r in s.scalars(stmt)]

    def units(self, active_only: bool = False) -> list[Lookup]:
        """All units by default (labels for existing records); active ones for new entries."""
        with self._db.session() as s:
            stmt = select(Unit).order_by(Unit.code)
            if active_only:
                stmt = stmt.where(Unit.is_active == 1)
            return [Lookup(id=r.code, code=r.code, name_ar=r.label_ar, name_en=r.label_en)
                    for r in s.scalars(stmt)]

    # ---------------- commands ----------------
    def create_location(self, actor: AuthUser | None, code: str, name_ar: str,
                        name_en: str | None = None, parent_id: str | None = None,
                        location_type: str = "area") -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        code, name_ar = normalize_code(code), (name_ar or "").strip()
        if not code or not name_ar:
            return Result.failure("err.location_required")
        with self._db.unit_of_work() as s:
            if s.scalar(select(Location.id).where(func.lower(Location.code) == code.lower())):
                return Result.failure("err.code_exists")
            if parent_id and s.get(Location, parent_id) is None:
                return Result.failure("err.not_found")
            row = Location(code=code, name_ar=name_ar, name_en=name_en,
                           parent_id=parent_id, location_type=location_type)
            s.add(row)
            s.flush()
            write_audit(s, "location", row.id, "location_created",
                        actor_id=actor.id if actor else None, after={"code": code})
            return Result.success(row.id)

    def create_category(self, actor: AuthUser | None, code: str, name_ar: str,
                        name_en: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        code, name_ar = normalize_code(code), (name_ar or "").strip()
        if not code or not name_ar:
            return Result.failure("err.category_required")
        with self._db.unit_of_work() as s:
            if s.scalar(select(AssetCategory.id).where(
                    func.lower(AssetCategory.code) == code.lower())):
                return Result.failure("err.code_exists")
            row = AssetCategory(code=code, name_ar=name_ar, name_en=name_en)
            s.add(row)
            s.flush()
            write_audit(s, "asset_category", row.id, "category_created",
                        actor_id=actor.id if actor else None, after={"code": code})
            return Result.success(row.id)

    def create_technician(self, actor: AuthUser | None, code: str, full_name: str,
                          trade: str | None = None, department: str | None = None,
                          hourly_rate_minor: int | None = None,
                          currency: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        code, full_name = normalize_code(code), (full_name or "").strip()
        if not code or not full_name:
            return Result.failure("err.technician_required")
        with self._db.unit_of_work() as s:
            if s.scalar(select(Technician.id).where(
                    func.lower(Technician.technician_code) == code.lower())):
                return Result.failure("err.code_exists")
            row = Technician(technician_code=code, full_name=full_name, trade=trade,
                             department=department, hourly_rate_minor=hourly_rate_minor,
                             currency=currency, search_norm=normalize_search(f"{code} {full_name}"))
            s.add(row)
            s.flush()
            write_audit(s, "technician", row.id, "technician_created",
                        actor_id=actor.id if actor else None, after={"code": code})
            return Result.success(row.id)

    def create_type(self, actor: AuthUser | None, category_id: str, code: str,
                    name_ar: str, name_en: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        code, name = normalize_code(code), (name_ar or "").strip()
        if not code or not name:
            return Result.failure("err.type_required")
        with self._db.unit_of_work() as s:
            if s.get(AssetCategory, category_id) is None:
                return Result.failure("err.category_required")
            if s.scalar(select(AssetType.id).where(
                    func.lower(AssetType.code) == code.lower())):
                return Result.failure("err.code_exists")
            row = AssetType(category_id=category_id, code=code, name_ar=name, name_en=name_en)
            s.add(row)
            s.flush()
            write_audit(s, "asset_type", row.id, "type_created",
                        actor_id=actor.id if actor else None, after={"code": code})
            return Result.success(row.id)

    def types_with_category(self) -> list[tuple[str, str, str, str]]:
        """(id, code, name, category_code) for the master-data screen."""
        with self._db.session() as s:
            categories = {c.id: c.code for c in s.scalars(select(AssetCategory))}
            return [(t.id, t.code, t.name_ar, categories.get(t.category_id, "—"))
                    for t in s.scalars(select(AssetType).order_by(AssetType.code))]

    def create_warehouse(self, actor: AuthUser | None, code: str, name_ar: str,
                         name_en: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        code, name = normalize_code(code), (name_ar or "").strip()
        if not code or not name:
            return Result.failure("err.warehouse_required")
        with self._db.unit_of_work() as s:
            if s.scalar(select(Warehouse.id).where(
                    func.lower(Warehouse.warehouse_code) == code.lower())):
                return Result.failure("err.code_exists")
            row = Warehouse(warehouse_code=code, name_ar=name, name_en=name_en)
            s.add(row)
            s.flush()
            write_audit(s, "warehouse", row.id, "warehouse_created",
                        actor_id=actor.id if actor else None, after={"code": code})
            return Result.success(row.id)

    def create_failure_code(self, actor: AuthUser | None, group_code: str, code: str,
                            name_ar: str, name_en: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        group, code = normalize_code(group_code), normalize_code(code)
        name = (name_ar or "").strip()
        if not group or not code or not name:
            return Result.failure("err.failure_code_required")
        with self._db.unit_of_work() as s:
            exists = s.scalar(select(FailureCode.id).where(
                FailureCode.group_code == group, func.lower(FailureCode.code) == code.lower()))
            if exists:
                return Result.failure("err.code_exists")
            row = FailureCode(group_code=group, code=code, name_ar=name, name_en=name_en)
            s.add(row)
            s.flush()
            write_audit(s, "failure_code", row.id, "failure_code_created",
                        actor_id=actor.id if actor else None, after={"code": code})
            return Result.success(row.id)

    def create_task(self, actor: AuthUser | None, task_code: str, title_ar: str,
                    estimated_min: int | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        code, title = normalize_code(task_code), (title_ar or "").strip()
        if not code or not title:
            return Result.failure("err.task_required")
        with self._db.unit_of_work() as s:
            if s.scalar(select(MaintenanceTask.id).where(
                    func.lower(MaintenanceTask.task_code) == code.lower())):
                return Result.failure("err.code_exists")
            row = MaintenanceTask(task_code=code, title_ar=title, estimated_min=estimated_min)
            s.add(row)
            s.flush()
            write_audit(s, "task_library", row.id, "task_created",
                        actor_id=actor.id if actor else None, after={"code": code})
            return Result.success(row.id)

    def technician_rows(self) -> list[tuple[str, str, str, str, str, bool]]:
        """(id, code, name, trade, department, active) for the roster screen."""
        with self._db.session() as s:
            return [(r.id, r.technician_code, r.full_name, r.trade or "—",
                     r.department or "—", bool(r.is_active))
                    for r in s.scalars(select(Technician)
                                       .order_by(Technician.technician_code))]

    def set_technician_active(self, actor: AuthUser | None, technician_id: str,
                              active: bool) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            row = s.get(Technician, technician_id)
            if row is None:
                return Result.failure("err.not_found")
            row.is_active = 1 if active else 0
            write_audit(s, "technician", row.id,
                        "technician_enabled" if active else "technician_disabled",
                        actor_id=actor.id if actor else None)
            return Result.success()

    def create_supplier(self, actor: AuthUser | None, code: str, name: str,
                        contact_info: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        code, name = normalize_code(code), (name or "").strip()
        if not code or not name:
            return Result.failure("err.supplier_required")
        with self._db.unit_of_work() as s:
            if s.scalar(select(Supplier.id).where(
                    func.lower(Supplier.supplier_code) == code.lower())):
                return Result.failure("err.code_exists")
            row = Supplier(supplier_code=code, name=name, contact_info=contact_info)
            s.add(row)
            s.flush()
            write_audit(s, "supplier", row.id, "supplier_created",
                        actor_id=actor.id if actor else None, after={"code": code})
            return Result.success(row.id)

    def supplier_rows(self) -> list[tuple[str, str, str, str, bool]]:
        with self._db.session() as s:
            return [(r.id, r.supplier_code, r.name, r.contact_info or "—", bool(r.is_active))
                    for r in s.scalars(select(Supplier).order_by(Supplier.supplier_code))]

    def set_supplier_active(self, actor: AuthUser | None, supplier_id: str,
                            active: bool) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            row = s.get(Supplier, supplier_id)
            if row is None:
                return Result.failure("err.not_found")
            row.is_active = 1 if active else 0
            write_audit(s, "supplier", row.id,
                        "supplier_enabled" if active else "supplier_disabled",
                        actor_id=actor.id if actor else None)
            return Result.success()

    def create_calendar(self, actor: AuthUser | None, code: str, name_ar: str,
                        name_en: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        code, name_ar = normalize_code(code), (name_ar or "").strip()
        if not code or not name_ar:
            return Result.failure("err.calendar_required")
        with self._db.unit_of_work() as s:
            if s.scalar(select(OperatingCalendar.id).where(
                    func.lower(OperatingCalendar.code) == code.lower())):
                return Result.failure("err.code_exists")
            row = OperatingCalendar(code=code, name_ar=name_ar, name_en=name_en)
            s.add(row)
            s.flush()
            write_audit(s, "operating_calendar", row.id, "calendar_created",
                        actor_id=actor.id if actor else None, after={"code": code})
            return Result.success(row.id)

    # ---------------- currencies (SPEC 4.4) ----------------
    def currency_rows(self) -> list[tuple[str, str, int]]:
        with self._db.session() as s:
            return [(c.code, c.name, c.minor_units)
                    for c in s.scalars(select(Currency).order_by(Currency.code))]

    def create_currency(self, actor: AuthUser | None, code: str, name: str,
                        minor_units: int = 2) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        code, name = (code or "").strip().upper(), (name or "").strip()
        if not (len(code) == 3 and code.isascii() and code.isalpha()):
            return Result.failure("err.currency_code_invalid")
        if not name:
            return Result.failure("err.name_required")
        if not 0 <= minor_units <= 4:
            return Result.failure("err.currency_minor_invalid")
        with self._db.unit_of_work() as s:
            if s.get(Currency, code) is not None:
                return Result.failure("err.code_exists")
            s.add(Currency(code=code, name=name, minor_units=minor_units))
            write_audit(s, "currency", code, "currency_created",
                        actor_id=actor.id if actor else None, after={"code": code})
            return Result.success(code)

    # ---------------- units (SPEC 4.4) ----------------
    def create_unit(self, actor: AuthUser | None, code: str, label_ar: str, label_en: str,
                    dimension: str, precision: int = 2) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        code = (code or "").strip()
        label_ar, label_en = (label_ar or "").strip(), (label_en or "").strip()
        dimension = (dimension or "").strip().lower()
        if not code or len(code) > 16 or " " in code:
            return Result.failure("err.unit_code_invalid")
        if not label_ar or not dimension:
            return Result.failure("err.name_required")
        if not 0 <= precision <= 6:
            return Result.failure("err.part_precision_invalid")
        with self._db.unit_of_work() as s:
            # Unit codes are case-sensitive keys ("L", "kPa") but "kpa" next to "kPa" would
            # only confuse; refuse a case-insensitive clash.
            if s.scalar(select(Unit.code).where(func.lower(Unit.code) == code.lower())):
                return Result.failure("err.code_exists")
            s.add(Unit(code=code, label_ar=label_ar, label_en=label_en or label_ar,
                       dimension=dimension, precision=precision))
            write_audit(s, "unit", code, "unit_created",
                        actor_id=actor.id if actor else None, after={"code": code})
            return Result.success(code)

    # ---------------- operating calendars (SPEC 16.3) ----------------
    def calendar_week(self, calendar_id: str) -> dict[int, tuple[str, str]]:
        """Weekday (0 = Sunday) → first shift (start, end) in local HH:MM."""
        with self._db.session() as s:
            return {row.weekday: (row.start_time_local, row.end_time_local)
                    for row in s.scalars(select(OperatingCalendarShift).where(
                        OperatingCalendarShift.calendar_id == calendar_id,
                        OperatingCalendarShift.shift_no == 1))}

    def calendar_rows(self) -> list[tuple[str, str, str, float, int]]:
        """(id, code, name, weekly hours, working days) for the calendars tab."""
        rows = []
        for cal in self.calendars(active_only=False):
            week = self.calendar_week(cal.id)
            hours = sum(_shift_hours(start, end) for start, end in week.values())
            rows.append((cal.id, cal.code, cal.name_ar, round(hours, 2), len(week)))
        return rows

    def set_calendar_week(self, actor: AuthUser | None, calendar_id: str,
                          week: dict[int, tuple[str, str]]) -> Result[None]:
        """Replace the weekly pattern; an end at or before the start crosses midnight."""
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        for weekday, (start, end) in week.items():
            if not 0 <= weekday <= 6 or not (_is_hhmm(start) and _is_hhmm(end)):
                return Result.failure("err.calendar_time_invalid")
            if start == end:
                return Result.failure("err.calendar_time_invalid")
        with self._db.unit_of_work() as s:
            if s.get(OperatingCalendar, calendar_id) is None:
                return Result.failure("err.not_found")
            for row in s.scalars(select(OperatingCalendarShift).where(
                    OperatingCalendarShift.calendar_id == calendar_id)):
                s.delete(row)
            s.flush()
            for weekday, (start, end) in sorted(week.items()):
                s.add(OperatingCalendarShift(
                    calendar_id=calendar_id, weekday=weekday, shift_no=1,
                    start_time_local=start, end_time_local=end,
                    ends_next_day=1 if end <= start else 0))
            write_audit(s, "operating_calendar", calendar_id, "calendar_week_set",
                        actor_id=actor.id if actor else None,
                        after={str(k): f"{v[0]}-{v[1]}" for k, v in sorted(week.items())})
            return Result.success()


def _is_hhmm(value: str) -> bool:
    try:
        hours, minutes = value.split(":")
        return len(hours) == 2 and len(minutes) == 2 and 0 <= int(hours) <= 23 \
            and 0 <= int(minutes) <= 59
    except ValueError:
        return False


def _shift_hours(start: str, end: str) -> float:
    def minutes(value: str) -> int:
        h, m = value.split(":")
        return int(h) * 60 + int(m)
    span = minutes(end) - minutes(start)
    return (span if span > 0 else span + 24 * 60) / 60
