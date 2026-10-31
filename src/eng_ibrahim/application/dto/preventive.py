"""Read models for preventive maintenance and inspections."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlanRow:
    id: str
    code: str
    asset_id: str
    asset_code: str
    title: str
    strategy: str
    trigger_policy: str
    next_due_date: str | None
    next_due_meter: str | None
    latest_meter: str | None
    state: str
    status: str


@dataclass(frozen=True)
class PlanTaskRow:
    id: str
    sequence: int
    title: str
    required: bool
    response_type: str


@dataclass(frozen=True)
class OccurrenceRow:
    id: str
    due_key: str
    due_date: str | None
    due_meter: str | None
    status: str
    wo_number: str | None
    skip_reason: str | None


@dataclass(frozen=True)
class PlanDetail:
    id: str
    code: str
    asset_id: str
    asset_code: str
    title: str
    description: str | None
    strategy: str
    trigger_policy: str
    calendar_interval_value: int | None
    calendar_interval_unit: str | None
    meter_id: str | None
    meter_interval_value: str | None
    next_due_date: str | None
    next_due_meter: str | None
    warning_days: int
    lead_days: int
    completion_anchor_policy: str
    status: str
    tasks: list[PlanTaskRow] = field(default_factory=list)
    occurrences: list[OccurrenceRow] = field(default_factory=list)


@dataclass(frozen=True)
class InspectionTemplateRow:
    id: str
    code: str
    title_ar: str
    item_count: int
    version: int
    status: str


@dataclass(frozen=True)
class InspectionRow:
    id: str
    number: str
    asset_code: str
    template_title: str | None
    status: str
    started_at: str
    completed_at: str | None
    failed_items: int
