"""Read models for failures, work orders and the dashboard board."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FailureRow:
    id: str
    number: str
    asset_id: str
    asset_code: str
    symptom: str
    priority: str
    status: str
    observed_at: str
    work_order_id: str | None = None


@dataclass(frozen=True)
class WoRow:
    id: str
    number: str
    asset_id: str
    asset_code: str
    type: str
    title: str
    status: str
    priority: str
    due_at: str | None
    assigned_to: str | None


@dataclass(frozen=True)
class TaskRow:
    id: str
    sequence: int
    title: str
    required: bool
    response_type: str
    result: str | None
    is_completed: bool


@dataclass(frozen=True)
class TimeLogRow:
    id: str
    technician: str
    start_at: str
    end_at: str
    category: str
    minutes: int
    cost_minor: int | None


@dataclass(frozen=True)
class StatusEventRow:
    at: str
    from_status: str | None
    to_status: str
    reason: str | None


@dataclass(frozen=True)
class WoCost:
    labour_minor: int
    external_minor: int
    parts_minor: int | None
    currency: str
    completeness: str

    @property
    def total_minor(self) -> int:
        return self.labour_minor + self.external_minor + (self.parts_minor or 0)


@dataclass(frozen=True)
class WoDetail:
    id: str
    number: str
    asset_id: str
    asset_code: str
    type: str
    title: str
    description: str | None
    status: str
    priority: str
    requested_at: str
    due_at: str | None
    actual_start_at: str | None
    actual_end_at: str | None
    completed_at: str | None
    closed_at: str | None
    closeout_notes: str | None
    equipment_returned_to_service: bool | None
    failure_id: str | None
    tasks: list[TaskRow] = field(default_factory=list)
    time_logs: list[TimeLogRow] = field(default_factory=list)
    events: list[StatusEventRow] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    cost: WoCost | None = None


@dataclass(frozen=True)
class BoardRow:
    asset_id: str
    code: str
    name: str
    category: str
    location: str
    recorded_status: str
    derived_status: str  # running | faulty | under_maintenance | retired
    fault_at: str | None
    repair_at: str | None
    open_wo: str | None
    priority: str | None
    conflict: bool


@dataclass(frozen=True)
class Kpis:
    total_assets: int
    open_work_orders: int
    open_failures: int
    overdue_work_orders: int
    overdue_pm: int = 0
    due_soon_pm: int = 0
    low_stock: int = 0
