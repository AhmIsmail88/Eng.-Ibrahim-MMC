"""Spare parts, warehouses and the stock ledger with moving weighted average (SPEC 12)."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from ...domain.permissions import can_edit
from ...domain.text_normalization import normalize_code, normalize_search, search_pattern
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    Part,
    StockBalance,
    StockMovement,
    StockReservation,
    Supplier,
    Technician,
    Unit,
    Warehouse,
    WorkOrder,
    WorkOrderAssignment,
)
from ...infrastructure.database.orm_models.base import utcnow_iso
from ...infrastructure.database.orm_models.inventory import ISSUE_TYPES, RETURN_TYPES
from ..dto.inventory import MovementRow, PartRow, PartUsageRow
from ..dto.result import Result
from .audit import write_audit
from .auth_service import AuthUser
from .numbering import next_number
from .settings_service import SettingsService

DEFAULT_WAREHOUSE_CODE = "MAIN"
WO_READ_ONLY = ("Closed", "Cancelled")


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


def _d(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number


def _money(amount: Decimal) -> int:
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class InventoryService:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._settings = SettingsService(db)

    def default_currency(self) -> str:
        return self._settings.get("currency_code", "EGP")

    # ---------------- warehouses ----------------
    def ensure_default_warehouse(self) -> str:
        with self._db.unit_of_work() as s:
            row = s.scalar(select(Warehouse).where(
                func.lower(Warehouse.warehouse_code) == DEFAULT_WAREHOUSE_CODE.lower()))
            if row is None:
                row = Warehouse(warehouse_code=DEFAULT_WAREHOUSE_CODE,
                                name_ar="المخزن الرئيسي", name_en="Main Store")
                s.add(row)
                s.flush()
            return row.id

    def warehouses(self):
        with self._db.session() as s:
            return [(w.id, w.warehouse_code, w.name_ar)
                    for w in s.scalars(select(Warehouse).order_by(Warehouse.warehouse_code))]

    # ---------------- parts ----------------
    def create_part(self, actor: AuthUser | None, part_code: str, name_ar: str,
                    unit_code: str, precision: int = 0, name_en: str | None = None,
                    category: str | None = None, min_stock: str | None = None,
                    reorder_point: str | None = None, target_stock: str | None = None,
                    reference_cost_minor: int | None = None,
                    currency: str | None = None,
                    supplier_id: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        code, name = normalize_code(part_code), (name_ar or "").strip()
        if not code or not name:
            return Result.failure("err.part_required")
        if not (0 <= precision <= 6):
            return Result.failure("err.part_precision_invalid")
        for value in (min_stock, reorder_point, target_stock):
            number = _d(value)
            if value not in (None, "") and (number is None or number < 0):
                return Result.failure("err.quantity_invalid")
        try:
            with self._db.unit_of_work() as s:
                if s.get(Unit, unit_code) is None:
                    return Result.failure("err.unit_invalid")
                if s.scalar(select(Part.id).where(
                        func.lower(func.trim(Part.part_code)) == code.lower())):
                    return Result.failure("err.part_code_exists")
                row = Part(
                    part_code=code, name_ar=name, name_en=(name_en or "").strip() or None,
                    category=category, unit_code=unit_code, precision=precision,
                    min_stock_decimal=min_stock, reorder_point_decimal=reorder_point,
                    target_stock_decimal=target_stock,
                    reference_cost_minor=reference_cost_minor,
                    currency=currency or self._settings.get("currency_code", "EGP"),
                    default_supplier_id=supplier_id,
                    search_norm=normalize_search(f"{code} {name} {name_en or ''}"))
                s.add(row)
                s.flush()
                write_audit(s, "part", row.id, "part_created",
                            actor_id=actor.id if actor else None,
                            after={"code": code})
                return Result.success(row.id)
        except IntegrityError:
            return Result.failure("err.part_code_exists")

    def list_parts(self, query: str = "", low_only: bool = False) -> list[PartRow]:
        with self._db.session() as s:
            warehouse_id = self._default_warehouse_id(s)
            stmt = select(Part).where(Part.is_active == 1).order_by(func.lower(Part.part_code))
            term = search_pattern(query)
            if term:
                stmt = stmt.where(or_(Part.search_norm.like(f"%{term}%", escape="\\"),
                                      func.lower(Part.part_code).like(f"%{term}%", escape="\\")))
            rows = []
            for part in s.scalars(stmt):
                balance = s.get(StockBalance, (part.id, warehouse_id)) if warehouse_id else None
                on_hand = _d(balance.on_hand_decimal) if balance else Decimal(0)
                reserved = _d(balance.reserved_decimal) if balance else Decimal(0)
                available = on_hand - reserved
                reorder = _d(part.reorder_point_decimal)
                min_stock = _d(part.min_stock_decimal)
                low = bool((reorder is not None and available <= reorder)
                           or (min_stock is not None and on_hand < min_stock))
                if low_only and not low:
                    continue
                rows.append(PartRow(
                    id=part.id, code=part.part_code, name_ar=part.name_ar,
                    name_en=part.name_en, unit_code=part.unit_code,
                    on_hand=str(on_hand), reserved=str(reserved), available=str(available),
                    average_cost_minor=(_money(_d(balance.average_unit_cost_precise))
                                        if balance else 0),
                    currency=(balance.currency_code if balance else (part.currency or "EGP")),
                    reorder_point=part.reorder_point_decimal, is_low=low))
            return rows

    def movements(self, part_id: str | None = None, wo_id: str | None = None,
                  limit: int = 200) -> list[MovementRow]:
        with self._db.session() as s:
            stmt = select(StockMovement).order_by(StockMovement.posted_at.desc()).limit(limit)
            if part_id:
                stmt = stmt.where(StockMovement.part_id == part_id)
            if wo_id:
                stmt = stmt.where(StockMovement.wo_id == wo_id)
            return [MovementRow(
                number=m.movement_no, posted_at=m.posted_at, type=m.movement_type,
                quantity=m.quantity_decimal, unit_cost_minor=m.unit_cost_minor_snapshot,
                total_minor=m.total_value_minor, currency=m.currency_code,
                reference=(m.purchase_ref or (m.wo_id[:8] if m.wo_id else None)),
                actor_id=m.actor_id) for m in s.scalars(stmt)]

    # ---------------- stock commands ----------------
    def receive(self, actor: AuthUser | None, part_id: str, quantity: str,
                unit_cost_minor: int, warehouse_id: str | None = None,
                supplier_id: str | None = None, purchase_ref: str | None = None,
                currency: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        qty = _d(quantity)
        if qty is None or qty <= 0:
            return Result.failure("err.quantity_invalid")
        if unit_cost_minor < 0:
            return Result.failure("err.cost_negative")
        currency = currency or self._settings.get("currency_code", "EGP")
        with self._db.unit_of_work() as s:
            return self.receive_in(s, actor, part_id, qty, unit_cost_minor, currency,
                                   warehouse_id=warehouse_id, supplier_id=supplier_id,
                                   purchase_ref=purchase_ref)

    def receive_in(self, s, actor: AuthUser | None, part_id: str, qty: Decimal,
                   unit_cost_minor: int, currency: str, warehouse_id: str | None = None,
                   supplier_id: str | None = None,
                   purchase_ref: str | None = None) -> Result[str]:
        """Post a receipt inside the caller's transaction (validated qty/cost)."""
        part = s.get(Part, part_id)
        if part is None:
            return Result.failure("err.part_not_found")
        warehouse_id = warehouse_id or self._default_warehouse_id(s)
        balance = self._balance(s, part_id, warehouse_id, currency)
        if balance.currency_code != currency:
            return Result.failure("err.currency_mismatch")
        total = _money(qty * Decimal(unit_cost_minor))
        old_qty = _d(balance.on_hand_decimal) or Decimal(0)
        old_value = Decimal(balance.inventory_value_minor)
        new_qty = old_qty + qty
        new_value = old_value + total
        balance.on_hand_decimal = str(new_qty)
        balance.inventory_value_minor = int(new_value)
        balance.average_unit_cost_precise = str(
            (new_value / new_qty).quantize(Decimal("0.000001")))
        movement = self._movement(
            s, part_id, warehouse_id, "RECEIPT", qty, qty, unit_cost_minor, total,
            currency, actor, supplier_id=supplier_id, purchase_ref=purchase_ref)
        write_audit(s, "stock_movement", movement.id, "stock_received",
                    actor_id=actor.id if actor else None,
                    after={"part": part.part_code, "qty": str(qty)})
        return Result.success(movement.id)

    def issue_to_wo(self, actor: AuthUser | None, part_id: str, wo_id: str,
                    quantity: str, warehouse_id: str | None = None,
                    reason: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        qty = _d(quantity)
        if qty is None or qty <= 0:
            return Result.failure("err.quantity_invalid")
        with self._db.unit_of_work() as s:
            wo = s.get(WorkOrder, wo_id)
            part = s.get(Part, part_id)
            if wo is None:
                return Result.failure("err.wo_not_found")
            if part is None:
                return Result.failure("err.part_not_found")
            if wo.status in WO_READ_ONLY:
                return Result.failure("err.wo_read_only")
            warehouse_id = warehouse_id or self._default_warehouse_id(s)
            balance = s.get(StockBalance, (part_id, warehouse_id))
            if balance is None:
                return Result.failure("err.stock_insufficient")
            on_hand = _d(balance.on_hand_decimal) or Decimal(0)
            reserved = _d(balance.reserved_decimal) or Decimal(0)
            # Stock held for this very work order is available to it.
            own = self._reserved_for(s, part_id, warehouse_id, wo_id)
            if on_hand - reserved + own < qty:
                return Result.failure("err.stock_insufficient")
            average = _d(balance.average_unit_cost_precise) or Decimal(0)
            unit = _money(average)
            total = _money(qty * average)
            balance.on_hand_decimal = str(on_hand - qty)
            balance.inventory_value_minor = max(0, balance.inventory_value_minor - total)
            if (_d(balance.on_hand_decimal) or Decimal(0)) > 0:
                balance.average_unit_cost_precise = str(
                    (Decimal(balance.inventory_value_minor)
                     / Decimal(balance.on_hand_decimal)).quantize(Decimal("0.000001")))
            movement = self._movement(
                s, part_id, warehouse_id, "ISSUE_TO_WO", qty, -qty, unit, total,
                balance.currency_code, actor, wo_id=wo_id, reason=reason)
            self._consume_reservation(s, part_id, warehouse_id, wo_id, qty)
            write_audit(s, "stock_movement", movement.id, "stock_issued",
                        actor_id=actor.id if actor else None,
                        after={"part": part.part_code, "qty": str(qty), "wo": wo.wo_number})
            return Result.success(movement.id)

    def return_from_wo(self, actor: AuthUser | None, issue_movement_id: str,
                       quantity: str, reason: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        qty = _d(quantity)
        if qty is None or qty <= 0:
            return Result.failure("err.quantity_invalid")
        with self._db.unit_of_work() as s:
            issue = s.get(StockMovement, issue_movement_id)
            if issue is None or issue.movement_type not in ISSUE_TYPES:
                return Result.failure("err.return_needs_issue")
            returned = _d(s.scalar(select(func.sum(StockMovement.quantity_decimal)).where(
                StockMovement.original_movement_id == issue.id,
                StockMovement.movement_type.in_(RETURN_TYPES)))) or Decimal(0)
            issued = _d(issue.quantity_decimal) or Decimal(0)
            if qty > issued - returned:
                return Result.failure("err.return_exceeds_issue")
            wo = s.get(WorkOrder, issue.wo_id) if issue.wo_id else None
            if wo is not None and wo.status in WO_READ_ONLY:
                return Result.failure("err.wo_read_only")
            balance = s.get(StockBalance, (issue.part_id, issue.warehouse_id))
            if balance is None:
                return Result.failure("err.part_not_found")
            unit = issue.unit_cost_minor_snapshot
            total = _money(qty * Decimal(unit))
            on_hand = (_d(balance.on_hand_decimal) or Decimal(0)) + qty
            balance.on_hand_decimal = str(on_hand)
            balance.inventory_value_minor += total
            balance.average_unit_cost_precise = str(
                (Decimal(balance.inventory_value_minor) / on_hand).quantize(
                    Decimal("0.000001")))
            movement = self._movement(
                s, issue.part_id, issue.warehouse_id, "RETURN_FROM_WO", qty, qty,
                unit, total, issue.currency_code, actor, wo_id=issue.wo_id,
                original_movement_id=issue.id, reason=reason)
            write_audit(s, "stock_movement", movement.id, "stock_returned",
                        actor_id=actor.id if actor else None,
                        after={"qty": str(qty), "issue": issue.movement_no})
            return Result.success(movement.id)

    def adjust(self, actor: AuthUser | None, part_id: str, quantity_delta: str,
               reason: str, warehouse_id: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        delta = _d(quantity_delta)
        if delta is None or delta == 0:
            return Result.failure("err.quantity_invalid")
        if not (reason or "").strip():
            return Result.failure("err.reason_required")
        with self._db.unit_of_work() as s:
            part = s.get(Part, part_id)
            if part is None:
                return Result.failure("err.part_not_found")
            warehouse_id = warehouse_id or self._default_warehouse_id(s)
            balance = s.get(StockBalance, (part_id, warehouse_id))
            if balance is None:
                return Result.failure("err.part_not_found")
            on_hand = _d(balance.on_hand_decimal) or Decimal(0)
            reserved = _d(balance.reserved_decimal) or Decimal(0)
            if on_hand + delta < (reserved if delta < 0 else 0):
                return Result.failure("err.stock_insufficient")
            average = _d(balance.average_unit_cost_precise) or Decimal(0)
            unit = _money(average)
            total = _money(abs(delta) * average)
            balance.on_hand_decimal = str(on_hand + delta)
            balance.inventory_value_minor = max(
                0, balance.inventory_value_minor + (total if delta > 0 else -total))
            if (_d(balance.on_hand_decimal) or Decimal(0)) > 0:
                balance.average_unit_cost_precise = str(
                    (Decimal(balance.inventory_value_minor)
                     / Decimal(balance.on_hand_decimal)).quantize(Decimal("0.000001")))
            kind = "ADJUSTMENT_POSITIVE" if delta > 0 else "ADJUSTMENT_NEGATIVE"
            movement = self._movement(s, part_id, warehouse_id, kind, abs(delta), delta,
                                      unit, total, balance.currency_code, actor,
                                      reason=reason)
            write_audit(s, "stock_movement", movement.id, "stock_adjusted",
                        actor_id=actor.id if actor else None, reason=reason)
            return Result.success(movement.id)

    # ---------------- reservations ----------------
    def reserve(self, actor: AuthUser | None, part_id: str, wo_id: str, quantity: str,
                warehouse_id: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        qty = _d(quantity)
        if qty is None or qty <= 0:
            return Result.failure("err.quantity_invalid")
        with self._db.unit_of_work() as s:
            wo = s.get(WorkOrder, wo_id)
            if wo is None:
                return Result.failure("err.wo_not_found")
            if wo.status in WO_READ_ONLY:
                return Result.failure("err.wo_read_only")
            warehouse_id = warehouse_id or self._default_warehouse_id(s)
            balance = s.get(StockBalance, (part_id, warehouse_id))
            if balance is None:
                return Result.failure("err.stock_insufficient")
            on_hand = _d(balance.on_hand_decimal) or Decimal(0)
            reserved = _d(balance.reserved_decimal) or Decimal(0)
            if on_hand - reserved < qty:
                return Result.failure("err.stock_insufficient")
            balance.reserved_decimal = str(reserved + qty)
            row = StockReservation(part_id=part_id, warehouse_id=warehouse_id, wo_id=wo_id,
                                   quantity_decimal=str(qty), status="active")
            s.add(row)
            s.flush()
            return Result.success(row.id)

    def release(self, actor: AuthUser | None, reservation_id: str) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            row = s.get(StockReservation, reservation_id)
            if row is None or row.status != "active":
                return Result.failure("err.not_found")
            balance = s.get(StockBalance, (row.part_id, row.warehouse_id))
            if balance is not None:
                reserved = _d(balance.reserved_decimal) or Decimal(0)
                balance.reserved_decimal = str(
                    max(Decimal(0), reserved - (_d(row.quantity_decimal) or Decimal(0))))
            row.status = "released"
            row.released_at = utcnow_iso()
            return Result.success()

    # ---------------- reporting ----------------
    def work_order_part_cost(self, wo_id: str) -> tuple[int, str]:
        with self._db.session() as s:
            rows = s.execute(select(StockMovement.movement_type,
                                    StockMovement.total_value_minor,
                                    StockMovement.currency_code)
                             .where(StockMovement.wo_id == wo_id,
                                    StockMovement.movement_type.in_(
                                        ("ISSUE_TO_WO", "RETURN_FROM_WO")))).all()
        if not rows:
            return 0, self._settings.get("currency_code", "EGP")
        total = sum(value if kind == "ISSUE_TO_WO" else -value for kind, value, _c in rows)
        currency = rows[0][2]
        return total, currency

    def asset_part_usage(self, asset_id: str) -> list[PartUsageRow]:
        with self._db.session() as s:
            stmt = (select(StockMovement, Part, WorkOrder, Supplier, Technician)
                    .join(Part, StockMovement.part_id == Part.id)
                    .join(WorkOrder, StockMovement.wo_id == WorkOrder.id)
                    .outerjoin(Supplier, StockMovement.supplier_id == Supplier.id)
                    .outerjoin(WorkOrderAssignment,
                               (WorkOrderAssignment.work_order_id == WorkOrder.id)
                               & (WorkOrderAssignment.assignment_role == "Primary"))
                    .outerjoin(Technician, WorkOrderAssignment.technician_id == Technician.id)
                    .where(WorkOrder.asset_id == asset_id,
                           StockMovement.movement_type == "ISSUE_TO_WO")
                    .order_by(StockMovement.posted_at.desc()))
            rows = []
            for movement, part, wo, supplier, tech in s.execute(stmt).all():
                rows.append(PartUsageRow(
                    movement_id=movement.id, part_code=part.part_code,
                    part_name=part.name_ar, quantity=movement.quantity_decimal,
                    unit_code=part.unit_code,
                    unit_cost_minor=movement.unit_cost_minor_snapshot,
                    total_minor=movement.total_value_minor,
                    currency=movement.currency_code, posted_at=movement.posted_at,
                    wo_number=wo.wo_number,
                    technician=tech.full_name if tech else None,
                    supplier=supplier.name if supplier else None,
                    purchase_ref=movement.purchase_ref))
            return rows

    # ---------------- helpers ----------------
    @staticmethod
    def _default_warehouse_id(session) -> str:
        row = session.scalar(select(Warehouse).where(
            func.lower(Warehouse.warehouse_code) == DEFAULT_WAREHOUSE_CODE.lower()))
        if row is None:
            row = Warehouse(warehouse_code=DEFAULT_WAREHOUSE_CODE,
                            name_ar="المخزن الرئيسي", name_en="Main Store")
            session.add(row)
            session.flush()
        return row.id

    @staticmethod
    def _balance(session, part_id: str, warehouse_id: str, currency: str) -> StockBalance:
        balance = session.get(StockBalance, (part_id, warehouse_id))
        if balance is None:
            balance = StockBalance(part_id=part_id, warehouse_id=warehouse_id,
                                   currency_code=currency)
            session.add(balance)
            session.flush()
        return balance

    @staticmethod
    def _movement(session, part_id: str, warehouse_id: str, kind: str, qty: Decimal,
                  signed: Decimal, unit_cost_minor: int, total_minor: int, currency: str,
                  actor: AuthUser | None, wo_id: str | None = None,
                  original_movement_id: str | None = None, supplier_id: str | None = None,
                  purchase_ref: str | None = None,
                  reason: str | None = None) -> StockMovement:
        movement = StockMovement(
            movement_no=next_number(session, "STK"), part_id=part_id,
            warehouse_id=warehouse_id, movement_type=kind, quantity_decimal=str(qty),
            signed_quantity_decimal=str(signed), currency_code=currency,
            unit_cost_minor_snapshot=unit_cost_minor, total_value_minor=total_minor,
            wo_id=wo_id, original_movement_id=original_movement_id,
            supplier_id=supplier_id, purchase_ref=purchase_ref,
            actor_id=actor.id if actor else None, reason=reason)
        session.add(movement)
        session.flush()
        return movement

    @staticmethod
    def _active_reservations(session, part_id: str, warehouse_id: str,
                             wo_id: str) -> list[StockReservation]:
        return list(session.scalars(select(StockReservation).where(
            StockReservation.part_id == part_id,
            StockReservation.warehouse_id == warehouse_id,
            StockReservation.wo_id == wo_id,
            StockReservation.status == "active").order_by(StockReservation.id)))

    @classmethod
    def _reserved_for(cls, session, part_id: str, warehouse_id: str, wo_id: str) -> Decimal:
        return sum((_d(r.quantity_decimal) or Decimal(0)
                    for r in cls._active_reservations(session, part_id, warehouse_id, wo_id)),
                   Decimal(0))

    @classmethod
    def _consume_reservation(cls, session, part_id: str, warehouse_id: str, wo_id: str,
                             qty: Decimal) -> None:
        """Draw `qty` down from this WO's reservations; a partial draw keeps the rest active."""
        remaining = qty
        consumed = Decimal(0)
        for row in cls._active_reservations(session, part_id, warehouse_id, wo_id):
            if remaining <= 0:
                break
            reserved_qty = _d(row.quantity_decimal) or Decimal(0)
            used = min(remaining, reserved_qty)
            remaining -= used
            consumed += used
            if used < reserved_qty:
                row.quantity_decimal = str(reserved_qty - used)
            else:
                row.status = "consumed"
                row.released_at = utcnow_iso()
        balance = session.get(StockBalance, (part_id, warehouse_id))
        if balance is not None and consumed:
            reserved = _d(balance.reserved_decimal) or Decimal(0)
            balance.reserved_decimal = str(max(Decimal(0), reserved - consumed))
