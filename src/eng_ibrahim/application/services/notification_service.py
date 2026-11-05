"""Derived notifications (UI-018): PM due/overdue, low stock, overdue work orders.

Nothing is persisted: the list is recomputed from live data, so a notification
cannot go stale or duplicate itself (SPEC 14.2).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ...infrastructure.database.engine import Database
from .inventory_service import InventoryService
from .pm_service import PMService
from .work_order_service import WorkOrderService


@dataclass(frozen=True)
class Notice:
    severity: str          # critical | warning | info
    title_key: str
    detail: str
    source: str
    source_id: str


class NotificationService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def scan(self) -> list[Notice]:
        today = date.today().isoformat()
        notices: list[Notice] = []
        for plan in PMService(self._db).list():
            if plan.state == "Overdue":
                notices.append(Notice("critical", "notify.pm_overdue",
                                      f"{plan.code} · {plan.asset_code}", "pm", plan.id))
            elif plan.state == "DueSoon":
                due = plan.next_due_date or plan.next_due_meter or ""
                notices.append(Notice("warning", "notify.pm_due", f"{plan.code} · {due}",
                                      "pm", plan.id))
        for part in InventoryService(self._db).list_parts(low_only=True):
            notices.append(Notice("warning", "notify.low_stock",
                                  f"{part.code} · {part.available} {part.unit_code}",
                                  "part", part.id))
        for order in WorkOrderService(self._db).list():
            if (order.status in ("Open", "Assigned", "InProgress", "OnHold")
                    and order.due_at and order.due_at < today):
                notices.append(Notice("critical", "notify.wo_overdue",
                                      f"{order.number} · {order.asset_code}", "wo", order.id))
        rank = {"critical": 0, "warning": 1, "info": 2}
        notices.sort(key=lambda n: rank.get(n.severity, 9))
        return notices
