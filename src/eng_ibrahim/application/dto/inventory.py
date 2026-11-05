"""Read models for inventory and asset part usage."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PartRow:
    id: str
    code: str
    name_ar: str
    name_en: str | None
    unit_code: str
    on_hand: str
    reserved: str
    available: str
    average_cost_minor: int
    currency: str
    reorder_point: str | None
    is_low: bool

    def name(self, arabic: bool) -> str:
        return (self.name_ar if arabic else self.name_en) or self.name_ar


@dataclass(frozen=True)
class MovementRow:
    number: str
    posted_at: str
    type: str
    quantity: str
    unit_cost_minor: int
    total_minor: int
    currency: str
    reference: str | None
    actor_id: str | None


@dataclass(frozen=True)
class PartUsageRow:
    """One issued part on an asset: what, when, who fitted it, from where."""
    movement_id: str
    part_code: str
    part_name: str
    quantity: str
    unit_code: str
    unit_cost_minor: int
    total_minor: int
    currency: str
    posted_at: str
    wo_number: str | None
    technician: str | None
    supplier: str | None
    purchase_ref: str | None


@dataclass(frozen=True)
class ReturnableIssue:
    movement_id: str
    movement_no: str
    wo_number: str
    posted_at: str
    issued: str
    remaining: str
