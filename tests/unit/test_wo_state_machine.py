"""The SPEC 10.3.1 transition table is the contract (ADR-007)."""
from __future__ import annotations

import pytest

from eng_ibrahim.domain.exceptions import DomainError
from eng_ibrahim.domain.policies import wo_state_machine as sm


def test_table_matches_spec_rows() -> None:
    pairs = {(t.source, t.target) for t in sm.TRANSITIONS}
    assert len(sm.TRANSITIONS) == 14
    for pair in [
        (sm.DRAFT, sm.OPEN), (sm.DRAFT, sm.CANCELLED),
        (sm.OPEN, sm.ASSIGNED), (sm.OPEN, sm.IN_PROGRESS), (sm.OPEN, sm.CANCELLED),
        (sm.ASSIGNED, sm.IN_PROGRESS), (sm.ASSIGNED, sm.ON_HOLD), (sm.ASSIGNED, sm.CANCELLED),
        (sm.IN_PROGRESS, sm.ON_HOLD), (sm.ON_HOLD, sm.IN_PROGRESS),
        (sm.IN_PROGRESS, sm.COMPLETED), (sm.COMPLETED, sm.CLOSED),
        (sm.COMPLETED, sm.IN_PROGRESS), (sm.CLOSED, sm.IN_PROGRESS),
    ]:
        assert pair in pairs


def test_unknown_transition_raises() -> None:
    with pytest.raises(DomainError) as exc:
        sm.check(sm.DRAFT, sm.CLOSED, "admin", {"asset_id": "x"})
    assert exc.value.code == "err.wo_transition_invalid"


def test_admin_only_transitions() -> None:
    with pytest.raises(DomainError) as exc:
        sm.check(sm.COMPLETED, sm.CLOSED, "editor", {"closed_at": "now"})
    assert exc.value.code == "err.wo_transition_forbidden"
    assert sm.find(sm.COMPLETED, sm.CLOSED).min_role == sm.ADMIN


def test_required_fields_are_enforced() -> None:
    with pytest.raises(DomainError) as exc:
        sm.check(sm.DRAFT, sm.OPEN, "editor", {"asset_id": "a", "title": "t"})
    assert exc.value.code == "err.wo_transition_required"


def test_allowed_targets_depend_on_role() -> None:
    assert set(sm.allowed_targets(sm.COMPLETED, "admin")) == {sm.CLOSED, sm.IN_PROGRESS}
    assert sm.allowed_targets(sm.COMPLETED, "editor") == []
    assert set(sm.allowed_targets(sm.IN_PROGRESS, "editor")) == {sm.ON_HOLD, sm.COMPLETED}
    assert sm.allowed_targets(sm.CLOSED, "viewer") == []
