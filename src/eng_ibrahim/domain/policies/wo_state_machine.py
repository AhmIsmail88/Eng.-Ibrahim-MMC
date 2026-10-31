"""Work-order state machine as data (SPEC 10.3.1, ADR-007).

The table in SPEC 10.3.1 is the single source of truth. Services call
`check()` before any status write; tests are generated from `TRANSITIONS`.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..enums import UserRole
from ..exceptions import DomainError
from ..permissions import can_edit, is_admin

DRAFT = "Draft"
OPEN = "Open"
ASSIGNED = "Assigned"
IN_PROGRESS = "InProgress"
ON_HOLD = "OnHold"
COMPLETED = "Completed"
CLOSED = "Closed"
CANCELLED = "Cancelled"

STATUSES = (DRAFT, OPEN, ASSIGNED, IN_PROGRESS, ON_HOLD, COMPLETED, CLOSED, CANCELLED)

EDITOR = "editor"
ADMIN = "admin"


@dataclass(frozen=True)
class Transition:
    source: str
    target: str
    guard: str
    required: tuple[str, ...] = ()
    min_role: str = EDITOR


TRANSITIONS: tuple[Transition, ...] = (
    Transition(DRAFT, OPEN, "asset+title+priority+requested_at",
               ("asset_id", "title", "priority", "requested_at")),
    Transition(DRAFT, CANCELLED, "reason", ("reason",)),
    Transition(OPEN, ASSIGNED, "active technician",
               ("technician_id", "assigned_at")),
    Transition(OPEN, IN_PROGRESS, "direct start", ("actual_start_at",)),
    Transition(OPEN, CANCELLED, "reason", ("reason",)),
    Transition(ASSIGNED, IN_PROGRESS, "", ("actual_start_at",)),
    Transition(ASSIGNED, ON_HOLD, "reason", ("reason",)),
    Transition(ASSIGNED, CANCELLED, "reason", ("reason",)),
    Transition(IN_PROGRESS, ON_HOLD, "reason", ("reason",)),
    Transition(ON_HOLD, IN_PROGRESS, "resume", ()),
    Transition(IN_PROGRESS, COMPLETED,
               "required tasks answered + equipment_returned_to_service",
               ("actual_end_at", "completed_at")),
    Transition(COMPLETED, CLOSED, "verification", ("closed_at",), min_role=ADMIN),
    Transition(COMPLETED, IN_PROGRESS, "reopen with reason", ("reason",), min_role=ADMIN),
    Transition(CLOSED, IN_PROGRESS, "authorized reopen with reason", ("reason",), min_role=ADMIN),
)

_BY_SOURCE: dict[str, tuple[Transition, ...]] = {}
for _t in TRANSITIONS:
    _BY_SOURCE[_t.source] = _BY_SOURCE.get(_t.source, ()) + (_t,)


def transitions_from(status: str) -> tuple[Transition, ...]:
    return _BY_SOURCE.get(status, ())


def find(source: str, target: str) -> Transition | None:
    for transition in _BY_SOURCE.get(source, ()):
        if transition.target == target:
            return transition
    return None


def role_satisfies(role: str | UserRole | None, min_role: str) -> bool:
    if role is None:
        return False
    value = role.value if isinstance(role, UserRole) else str(role)
    if min_role == ADMIN:
        return is_admin(value)
    return can_edit(value)


def allowed_targets(status: str, role: str | UserRole | None) -> list[str]:
    return [t.target for t in transitions_from(status) if role_satisfies(role, t.min_role)]


def check(status: str, target: str, role: str | UserRole | None,
          payload: dict[str, object]) -> Transition:
    """Raise DomainError when the move is not allowed or a required field is missing."""
    transition = find(status, target)
    if transition is None:
        raise DomainError("err.wo_transition_invalid", current=status, target=target)
    if not role_satisfies(role, transition.min_role):
        raise DomainError("err.wo_transition_forbidden", target=target)
    missing = [field for field in transition.required if not payload.get(field)]
    if missing:
        raise DomainError("err.wo_transition_required", fields=", ".join(missing))
    return transition
