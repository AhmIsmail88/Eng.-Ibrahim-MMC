"""Purchase requests (P1): approve, then receive straight into the stock ledger."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select

from ...domain.permissions import can_edit
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    Part,
    PurchaseRequest,
    PurchaseRequestLine,
    Supplier,
)
from ..dto.result import Result
from .audit import write_audit
from .auth_service import AuthUser
from .inventory_service import InventoryService
from .numbering import next_number


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


def _qty(value) -> Decimal | None:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return number if number > 0 else None


@dataclass(frozen=True)
class RequestRow:
    id: str
    number: str
    supplier: str
    status: str
    total_minor: int
    lines: int


class PurchaseService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def list(self) -> list[RequestRow]:
        with self._db.session() as s:
            rows = []
            for req in s.scalars(select(PurchaseRequest)
                                 .order_by(PurchaseRequest.requested_at.desc())):
                supplier = s.get(Supplier, req.supplier_id) if req.supplier_id else None
                count = int(s.scalar(select(func.count()).select_from(PurchaseRequestLine)
                                     .where(PurchaseRequestLine.request_id == req.id)) or 0)
                rows.append(RequestRow(id=req.id, number=req.request_no,
                                       supplier=supplier.name if supplier else "—",
                                       status=req.status,
                                       total_minor=req.estimated_total_minor, lines=count))
            return rows

    def create(self, actor: AuthUser | None, supplier_id: str | None,
               lines: list[tuple[str, str, int]], notes: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if not lines:
            return Result.failure("err.pr_lines_required")
        with self._db.unit_of_work() as s:
            if supplier_id and s.get(Supplier, supplier_id) is None:
                return Result.failure("err.not_found")
            total = 0
            prepared = []
            for part_id, quantity, cost_minor in lines:
                qty = _qty(quantity)
                if qty is None or cost_minor < 0:
                    return Result.failure("err.quantity_invalid")
                if s.get(Part, part_id) is None:
                    return Result.failure("err.part_not_found")
                prepared.append((part_id, str(qty), cost_minor))
                total += int(qty * cost_minor)
            request = PurchaseRequest(
                request_no=next_number(s, "PR"), supplier_id=supplier_id,
                status="Draft", requested_by=actor.id if actor else None, notes=notes,
                estimated_total_minor=total)
            s.add(request)
            s.flush()
            for part_id, qty, cost_minor in prepared:
                s.add(PurchaseRequestLine(request_id=request.id, part_id=part_id,
                                          quantity_decimal=qty,
                                          estimated_cost_minor=cost_minor))
            write_audit(s, "purchase_request", request.id, "pr_created",
                        actor_id=actor.id if actor else None,
                        after={"number": request.request_no, "total": total})
            return Result.success(request.id)

    def approve(self, actor: AuthUser | None, request_id: str) -> Result[None]:
        return self._status(actor, request_id, "Approved", ("Draft",))

    def cancel(self, actor: AuthUser | None, request_id: str, reason: str) -> Result[None]:
        if not (reason or "").strip():
            return Result.failure("err.reason_required")
        return self._status(actor, request_id, "Cancelled", ("Draft", "Approved"))

    def _status(self, actor, request_id, target, allowed) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            row = s.get(PurchaseRequest, request_id)
            if row is None:
                return Result.failure("err.not_found")
            if row.status not in allowed:
                return Result.failure("err.pr_status_invalid")
            row.status = target
            write_audit(s, "purchase_request", row.id, f"pr_{target.lower()}",
                        actor_id=actor.id if actor else None)
            return Result.success()

    def receive(self, actor: AuthUser | None, request_id: str,
                warehouse_id: str | None = None) -> Result[int]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.session() as s:
            request = s.get(PurchaseRequest, request_id)
            if request is None:
                return Result.failure("err.not_found")
            if request.status != "Approved":
                return Result.failure("err.pr_not_approved")
            supplier_id = request.supplier_id
            number = request.request_no
            lines = [(line.part_id, line.quantity_decimal, line.estimated_cost_minor)
                     for line in s.scalars(select(PurchaseRequestLine)
                                           .where(PurchaseRequestLine.request_id == request_id))]
        inventory = InventoryService(self._db)
        received = 0
        for part_id, quantity, cost_minor in lines:
            result = inventory.receive(actor, part_id, quantity, cost_minor,
                                       warehouse_id=warehouse_id,
                                       supplier_id=supplier_id, purchase_ref=number)
            if not result.ok:
                return Result.failure(result.error_code or "err.stock_insufficient")
            received += 1
        return self._finish(request_id, received)

    def _finish(self, request_id: str, received: int) -> Result[int]:
        with self._db.unit_of_work() as s:
            row = s.get(PurchaseRequest, request_id)
            if row is None:
                return Result.failure("err.not_found")
            row.status = "Received"
            write_audit(s, "purchase_request", row.id, "pr_received",
                        after={"lines": received})
            return Result.success(received)
