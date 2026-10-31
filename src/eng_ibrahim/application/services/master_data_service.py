"""Reference lookups and simple master-data commands (SPEC 4, ADR-025 permissions)."""
from __future__ import annotations

from sqlalchemy import func, select

from ...domain.permissions import can_edit
from ...domain.text_normalization import normalize_code, normalize_search
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    AssetCategory,
    AssetType,
    Location,
    OperatingCalendar,
    Supplier,
    Technician,
    Unit,
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

    def types(self, category_id: str | None = None) -> list[Lookup]:
        with self._db.session() as s:
            stmt = select(AssetType).order_by(AssetType.code)
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

    def units(self) -> list[Lookup]:
        with self._db.session() as s:
            return [Lookup(id=r.code, code=r.code, name_ar=r.label_ar, name_en=r.label_en)
                    for r in s.scalars(select(Unit).order_by(Unit.code))]

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
