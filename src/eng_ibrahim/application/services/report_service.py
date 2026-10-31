"""Report definitions and data (SPEC 17). One query per report, reused by screen + exports."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select

from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    Asset,
    AssetCategory,
    Location,
    Part,
    StockBalance,
    Warehouse,
    WorkOrder,
)
from .inventory_service import InventoryService
from .pm_service import PMService
from .work_order_service import WorkOrderService


@dataclass(frozen=True)
class ReportColumn:
    key: str
    title_key: str
    numeric: bool = False
    width: int = 18


@dataclass(frozen=True)
class ReportResult:
    code: str
    title_key: str
    columns: list[ReportColumn]
    rows: list[dict]
    totals: dict[str, str] = field(default_factory=dict)
    meta: dict[str, str] = field(default_factory=dict)


REPORTS = (
    ("REP-001", "report.assets_register", True),
    ("REP-003", "report.pm_schedule", False),
    ("REP-005", "report.wo_register", False),
    ("REP-006", "report.wo_card", False),
    ("REP-009", "report.stock_balance", True),
    ("REP-013", "report.maintenance_cost", False),
)


class ReportService:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._orders = WorkOrderService(db)
        self._inventory = InventoryService(db)

    def build(self, code: str, *, date_from: str | None = None,
              date_to: str | None = None, category_id: str | None = None,
              status: str | None = None, wo_id: str | None = None) -> ReportResult:
        if code == "REP-001":
            return self._assets_register(category_id, status)
        if code == "REP-003":
            return self._pm_schedule(date_from, date_to)
        if code == "REP-006":
            return self._wo_card(wo_id)
        if code == "REP-005":
            return self._wo_register(date_from, date_to)
        if code == "REP-009":
            return self._stock_balance()
        if code == "REP-013":
            return self._maintenance_cost(date_from, date_to)
        raise ValueError(f"unknown report: {code}")

    # ---------------- REP-001 ----------------
    def _assets_register(self, category_id: str | None, status: str | None) -> ReportResult:
        with self._db.session() as s:
            stmt = (select(Asset, AssetCategory, Location)
                    .join(AssetCategory, Asset.category_id == AssetCategory.id)
                    .join(Location, Asset.location_id == Location.id)
                    .where(Asset.is_active == 1)
                    .order_by(func.lower(Asset.asset_code)))
            if category_id:
                stmt = stmt.where(Asset.category_id == category_id)
            if status:
                stmt = stmt.where(Asset.operational_status == status)
            rows = [{
                "code": a.asset_code, "name": a.asset_name_ar,
                "category": c.name_ar, "location": loc.name_ar,
                "criticality": a.criticality, "status": a.operational_status,
                "condition": a.asset_condition,
            } for a, c, loc in s.execute(stmt).all()]
        return ReportResult(
            code="REP-001", title_key="report.assets_register",
            columns=[ReportColumn("code", "rep.col.code"), ReportColumn("name", "rep.col.name"),
                     ReportColumn("category", "rep.col.category"),
                     ReportColumn("location", "rep.col.location"),
                     ReportColumn("criticality", "rep.col.criticality"),
                     ReportColumn("status", "rep.col.status"),
                     ReportColumn("condition", "rep.col.condition")],
            rows=rows, totals={"count": str(len(rows))})

    # ---------------- REP-005 ----------------
    def _wo_register(self, date_from: str | None, date_to: str | None) -> ReportResult:
        with self._db.session() as s:
            stmt = (select(WorkOrder, Asset)
                    .join(Asset, WorkOrder.asset_id == Asset.id)
                    .order_by(WorkOrder.requested_at.desc()))
            if date_from:
                stmt = stmt.where(WorkOrder.requested_at >= date_from)
            if date_to:
                stmt = stmt.where(WorkOrder.requested_at <= f"{date_to}T23:59:59")
            rows = [{
                "number": wo.wo_number, "asset": asset.asset_code,
                "type": wo.type, "title": wo.title, "status": wo.status,
                "priority": wo.priority, "due": wo.due_at or "",
                "completed": (wo.completed_at or "")[:10],
            } for wo, asset in s.execute(stmt).all()]
        return ReportResult(
            code="REP-005", title_key="report.wo_register",
            columns=[ReportColumn("number", "rep.col.number"),
                     ReportColumn("asset", "rep.col.asset"),
                     ReportColumn("type", "rep.col.type"),
                     ReportColumn("title", "rep.col.title", width=32),
                     ReportColumn("status", "rep.col.status"),
                     ReportColumn("priority", "rep.col.priority"),
                     ReportColumn("due", "rep.col.due"),
                     ReportColumn("completed", "rep.col.completed")],
            rows=rows, totals={"count": str(len(rows))},
            meta={"from": date_from or "", "to": date_to or ""})


    # ---------------- REP-003 ----------------
    def _pm_schedule(self, date_from: str | None, date_to: str | None) -> ReportResult:
        rows = []
        for plan in PMService(self._db).list():
            due = plan.next_due_date or plan.next_due_meter or ""
            if date_from and plan.next_due_date and plan.next_due_date < date_from:
                continue
            if date_to and plan.next_due_date and plan.next_due_date > date_to:
                continue
            rows.append({"code": plan.code, "asset": plan.asset_code, "title": plan.title,
                         "due": due, "state": plan.state, "status": plan.status})
        return ReportResult(
            code="REP-003", title_key="report.pm_schedule",
            columns=[ReportColumn("code", "rep.col.code"),
                     ReportColumn("asset", "rep.col.asset"),
                     ReportColumn("title", "rep.col.title", width=30),
                     ReportColumn("due", "rep.col.next_due"),
                     ReportColumn("state", "rep.col.state"),
                     ReportColumn("status", "rep.col.status")],
            rows=rows, totals={"count": str(len(rows))},
            meta={"from": date_from or "", "to": date_to or ""})

    # ---------------- REP-006 ----------------
    def _wo_card(self, wo_id: str | None) -> ReportResult:
        columns = [ReportColumn("label", "rep.col.label", width=26),
                   ReportColumn("value", "rep.col.value", width=54)]
        if not wo_id:
            return ReportResult(code="REP-006", title_key="report.wo_card",
                                columns=columns, rows=[])
        detail = self._orders.detail(wo_id)
        if detail is None:
            return ReportResult(code="REP-006", title_key="report.wo_card",
                                columns=columns, rows=[])
        rows = [
            {"label": "WO", "value": detail.number},
            {"label": "Asset", "value": detail.asset_code},
            {"label": "Type", "value": detail.type},
            {"label": "Status", "value": detail.status},
            {"label": "Priority", "value": detail.priority},
            {"label": "Requested", "value": detail.requested_at[:10]},
            {"label": "Started", "value": (detail.actual_start_at or "")[:10]},
            {"label": "Completed", "value": (detail.completed_at or "")[:10]},
            {"label": "Tasks", "value": ""},
        ]
        for task in detail.tasks:
            rows.append({"label": f"  {task.sequence}.", "value": task.title
                         + (" ✓" if task.is_completed else "")})
        usage = self._inventory.asset_part_usage(detail.asset_id)
        issued = [u for u in usage if u.wo_number == detail.number]
        rows.append({"label": "Parts", "value": ""})
        for part in issued:
            rows.append({"label": f"  {part.part_code}",
                         "value": f"{part.quantity} {part.unit_code} — "
                                  f"{part.total_minor / 100:.2f} {part.currency}"})
        cost = detail.cost
        if cost is not None:
            rows.append({"label": "Cost", "value": ""})
            rows.append({"label": "  Parts", "value": f"{(cost.parts_minor or 0) / 100:.2f}"})
            rows.append({"label": "  Labour", "value": f"{cost.labour_minor / 100:.2f}"})
            rows.append({"label": "  External", "value": f"{cost.external_minor / 100:.2f}"})
            rows.append({"label": "  Total", "value": f"{cost.total_minor / 100:.2f} {cost.currency}"})
        rows += [
            {"label": "Prepared By", "value": "____________________"},
            {"label": "Executed By", "value": "____________________"},
            {"label": "Reviewed/Approved By", "value": "____________________"},
            {"label": "Signature / Date", "value": "____________________"},
        ]
        return ReportResult(code="REP-006", title_key="report.wo_card",
                            columns=columns, rows=rows,
                            totals={"count": str(len(detail.tasks))},
                            meta={"wo": detail.number})

    # ---------------- REP-009 ----------------
    def _stock_balance(self) -> ReportResult:
        with self._db.session() as s:
            parts = {p.id: p for p in s.scalars(select(Part))}
            balances = s.execute(select(StockBalance, Warehouse)
                                 .join(Warehouse, StockBalance.warehouse_id == Warehouse.id)
                                 .order_by(func.lower(Warehouse.warehouse_code))).all()
            rows = []
            total_value = 0
            for balance, warehouse in balances:
                part = parts.get(balance.part_id)
                if part is None:
                    continue
                total_value += balance.inventory_value_minor
                rows.append({
                    "part": part.part_code, "name": part.name_ar,
                    "warehouse": warehouse.warehouse_code,
                    "on_hand": balance.on_hand_decimal,
                    "reserved": balance.reserved_decimal,
                    "available": str(float(balance.on_hand_decimal)
                                     - float(balance.reserved_decimal)),
                    "avg_cost": f"{float(balance.average_unit_cost_precise):.2f}",
                    "value": f"{balance.inventory_value_minor / 100:.2f}",
                })
        return ReportResult(
            code="REP-009", title_key="report.stock_balance",
            columns=[ReportColumn("part", "rep.col.part"),
                     ReportColumn("name", "rep.col.name", width=28),
                     ReportColumn("warehouse", "rep.col.warehouse"),
                     ReportColumn("on_hand", "rep.col.on_hand", numeric=True),
                     ReportColumn("reserved", "rep.col.reserved", numeric=True),
                     ReportColumn("available", "rep.col.available", numeric=True),
                     ReportColumn("avg_cost", "rep.col.avg_cost", numeric=True),
                     ReportColumn("value", "rep.col.value", numeric=True)],
            rows=rows, totals={"value": f"{total_value / 100:.2f}"})

    # ---------------- REP-013 ----------------
    def _maintenance_cost(self, date_from: str | None, date_to: str | None) -> ReportResult:
        with self._db.session() as s:
            stmt = (select(WorkOrder, Asset)
                    .join(Asset, WorkOrder.asset_id == Asset.id)
                    .order_by(func.lower(Asset.asset_code)))
            if date_from:
                stmt = stmt.where(WorkOrder.requested_at >= date_from)
            if date_to:
                stmt = stmt.where(WorkOrder.requested_at <= f"{date_to}T23:59:59")
            orders = s.execute(stmt).all()

        buckets: dict[str, dict[str, float]] = {}
        for wo, asset in orders:
            cost = self._orders.cost(wo.id)
            if cost is None:
                continue
            bucket = buckets.setdefault(asset.asset_code, {
                "parts": 0.0, "labour": 0.0, "external": 0.0})
            bucket["parts"] += cost.parts_minor or 0
            bucket["labour"] += cost.labour_minor
            bucket["external"] += cost.external_minor
        rows = []
        totals = {"parts": 0.0, "labour": 0.0, "external": 0.0, "total": 0.0}
        for asset_code, values in buckets.items():
            total = values["parts"] + values["labour"] + values["external"]
            for key in ("parts", "labour", "external"):
                totals[key] += values[key]
            totals["total"] += total
            rows.append({
                "asset": asset_code,
                "parts": f"{values['parts'] / 100:.2f}",
                "labour": f"{values['labour'] / 100:.2f}",
                "external": f"{values['external'] / 100:.2f}",
                "total": f"{total / 100:.2f}",
            })
        return ReportResult(
            code="REP-013", title_key="report.maintenance_cost",
            columns=[ReportColumn("asset", "rep.col.asset"),
                     ReportColumn("parts", "rep.col.parts", numeric=True),
                     ReportColumn("labour", "rep.col.labour", numeric=True),
                     ReportColumn("external", "rep.col.external", numeric=True),
                     ReportColumn("total", "rep.col.total", numeric=True)],
            rows=rows,
            totals={k: f"{v / 100:.2f}" for k, v in totals.items()},
            meta={"from": date_from or "", "to": date_to or ""})

    @staticmethod
    def default_period() -> tuple[str, str]:
        today = date.today()
        return today.replace(day=1).isoformat(), today.isoformat()
