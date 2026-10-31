"""Dashboard board and headline counts (SPEC 15.1, 15.1.1)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select

from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    Asset,
    AssetCategory,
    DowntimeEvent,
    FailureReport,
    Location,
    WorkOrder,
)
from ..dto.maintenance import BoardRow, Kpis

OPEN_WO_STATUSES = ("Open", "Assigned", "InProgress", "OnHold")
ACTIVE_FAILURE_STATUSES = ("New", "Investigating")


def _day(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value[:10]


class DashboardService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def kpis(self) -> Kpis:
        today = date.today().isoformat()
        with self._db.session() as s:
            total = int(s.scalar(select(func.count()).select_from(Asset)
                                 .where(Asset.is_active == 1)) or 0)
            open_wos = int(s.scalar(select(func.count()).select_from(WorkOrder)
                                    .where(WorkOrder.status.in_(OPEN_WO_STATUSES))) or 0)
            open_failures = int(s.scalar(select(func.count()).select_from(FailureReport)
                                         .where(FailureReport.status.in_(
                                             ACTIVE_FAILURE_STATUSES))) or 0)
            overdue = int(s.scalar(select(func.count()).select_from(WorkOrder).where(
                WorkOrder.status.in_(OPEN_WO_STATUSES),
                WorkOrder.due_at.is_not(None),
                WorkOrder.due_at < today)) or 0)
        return Kpis(total_assets=total, open_work_orders=open_wos,
                    open_failures=open_failures, overdue_work_orders=overdue)

    def board(self, category_code: str | None = "PUMP",
              include_retired: bool = False) -> list[BoardRow]:
        with self._db.session() as s:
            stmt = (select(Asset, AssetCategory, Location)
                    .join(AssetCategory, Asset.category_id == AssetCategory.id)
                    .join(Location, Asset.location_id == Location.id)
                    .where(Asset.is_active == 1)
                    .order_by(func.lower(Asset.asset_code)))
            if category_code:
                stmt = stmt.where(AssetCategory.code == category_code)
            rows: list[BoardRow] = []
            for asset, category, location in s.execute(stmt).all():
                failure = s.scalars(select(FailureReport).where(
                    FailureReport.asset_id == asset.id,
                    FailureReport.status.in_(ACTIVE_FAILURE_STATUSES),
                ).order_by(FailureReport.observed_at.desc()).limit(1)).first()
                open_wo = s.scalars(select(WorkOrder).where(
                    WorkOrder.asset_id == asset.id,
                    WorkOrder.status.in_(OPEN_WO_STATUSES),
                ).order_by(WorkOrder.requested_at.desc()).limit(1)).first()
                last_repair = s.scalar(select(func.max(WorkOrder.actual_end_at)).where(
                    WorkOrder.asset_id == asset.id,
                    WorkOrder.type == "CM",
                    WorkOrder.status.in_(("Completed", "Closed"))))
                last_downtime_end = s.scalar(select(func.max(DowntimeEvent.ended_at)).where(
                    DowntimeEvent.asset_id == asset.id,
                    DowntimeEvent.ended_at.is_not(None)))
                derived = self._derive(asset.operational_status, failure, open_wo)
                if derived == "retired" and not include_retired:
                    continue
                conflict = self._conflict(asset.operational_status, derived)
                rows.append(BoardRow(
                    asset_id=asset.id, code=asset.asset_code, name=asset.asset_name_ar,
                    category=category.name_ar, location=location.name_ar,
                    recorded_status=asset.operational_status, derived_status=derived,
                    fault_at=_day(failure.observed_at) if failure else None,
                    repair_at=_day(last_repair or last_downtime_end),
                    open_wo=open_wo.wo_number if open_wo else None,
                    priority=failure.priority if failure else (
                        open_wo.priority if open_wo else None),
                    conflict=conflict))
        order = {"faulty": 0, "under_maintenance": 1, "running": 2, "retired": 3}
        rows.sort(key=lambda r: (order.get(r.derived_status, 9), r.code))
        return rows

    @staticmethod
    def _derive(recorded: str, failure, open_wo) -> str:
        if recorded == "Retired":
            return "retired"
        if recorded == "Out of Service" or failure is not None:
            return "faulty"
        if recorded == "Under Maintenance" or open_wo is not None:
            return "under_maintenance"
        return "running"

    @staticmethod
    def _conflict(recorded: str, derived: str) -> bool:
        if recorded == "Retired" or derived == "retired":
            return False
        if recorded in ("In Service", "Standby") and derived != "running":
            return True
        if recorded == "Under Maintenance" and derived == "faulty":
            return True
        return False
