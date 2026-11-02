"""PM scheduling rules as pure functions (SPEC 9.3, ADR-032).

No DB and no Qt: the same functions are used by the scheduler, the UI badge and
the tests, so a due date cannot be computed two different ways.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

NOT_DUE = "NotDue"
DUE_SOON = "DueSoon"
DUE = "Due"
OVERDUE = "Overdue"
PAUSED = "Paused"
NO_VALID_METER = "NoValidMeter"
AWAITING = "AwaitingCompletion"

_SEVERITY = {NOT_DUE: 0, DUE_SOON: 1, DUE: 2, OVERDUE: 3}


def add_months(base: date, months: int) -> date:
    """Add months with CLAMP_TO_LAST_DAY (Jan 31 + 1 month = Feb 28/29)."""
    index = base.month - 1 + months
    year = base.year + index // 12
    month = index % 12 + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def add_interval(base: date, value: int, unit: str) -> date:
    if value <= 0:
        raise ValueError("interval must be positive")
    if unit == "days":
        return base + timedelta(days=value)
    if unit == "weeks":
        return base + timedelta(weeks=value)
    if unit == "months":
        return add_months(base, value)
    if unit == "years":
        return add_months(base, value * 12)
    raise ValueError(f"unknown interval unit: {unit}")


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def worst(*states: str) -> str:
    """Return the most severe state (overdue beats due beats soon)."""
    return max(states, key=lambda s: _SEVERITY.get(s, -1))


@dataclass(frozen=True)
class Schedule:
    trigger_policy: str
    next_due_date: date | None
    next_due_meter: float | None
    warning_days: int
    warning_meter: float | None
    latest_meter: float | None
    status: str  # Active / Paused / Archived
    open_work_order: bool = False

    def state(self, today: date) -> str:
        if self.status != "Active":
            return PAUSED
        if self.open_work_order:
            return AWAITING
        states: list[str] = []
        if self.trigger_policy in ("DATE_ONLY", "FIRST_DUE", "BOTH_REQUIRED"):
            if self.next_due_date is not None:
                if today > self.next_due_date:
                    states.append(OVERDUE)
                elif today == self.next_due_date:
                    states.append(DUE)
                elif today >= self.next_due_date - timedelta(days=self.warning_days):
                    states.append(DUE_SOON)
                else:
                    states.append(NOT_DUE)
            elif self.trigger_policy == "DATE_ONLY":
                states.append(NO_VALID_METER)
        if self.trigger_policy in ("METER_ONLY", "FIRST_DUE", "BOTH_REQUIRED"):
            if self.next_due_meter is None or self.latest_meter is None:
                states.append(NO_VALID_METER)
            else:
                if self.latest_meter > self.next_due_meter:
                    states.append(OVERDUE)
                elif self.latest_meter >= self.next_due_meter:
                    states.append(DUE)
                elif (self.warning_meter is not None
                      and self.latest_meter >= self.next_due_meter - self.warning_meter):
                    states.append(DUE_SOON)
                else:
                    states.append(NOT_DUE)
        if not states:
            return NOT_DUE
        if self.trigger_policy == "FIRST_DUE":
            if NO_VALID_METER in states and all(s == NO_VALID_METER for s in states):
                return NO_VALID_METER
            return worst(*[s for s in states if s != NO_VALID_METER] or [NO_VALID_METER])
        if self.trigger_policy == "BOTH_REQUIRED":
            if NO_VALID_METER in states:
                return NO_VALID_METER
            return NOT_DUE if any(s == NOT_DUE for s in states) else worst(*states)
        return states[0]


def due_key(plan_id: str, due_date: date | None, due_meter: float | None) -> str:
    anchor = due_date.isoformat() if due_date else (
        f"m{int(due_meter)}" if due_meter is not None else "none")
    return f"{plan_id}:{anchor}"


def advance_to_future(start: date, value: int, unit: str, today: date,
                      limit: int = 200) -> tuple[date, list[date]]:
    """Skip past missed occurrences; return (next future date, skipped dates)."""
    current = start
    skipped: list[date] = []
    while current < today and len(skipped) < limit:
        skipped.append(current)
        current = add_interval(current, value, unit)
    return current, skipped


def latest_missed(start: date, value: int, unit: str, today: date,
                  limit: int = 200) -> tuple[date, list[date]]:
    """SPEC 9.4 (8) LATEST_ONLY_AND_LOG_SKIPPED: keep the most recent due date that is
    not after `today` and return the older missed ones to be logged as skipped."""
    current = start
    skipped: list[date] = []
    while len(skipped) < limit:
        following = add_interval(current, value, unit)
        if following > today:
            break
        skipped.append(current)
        current = following
    return current, skipped
