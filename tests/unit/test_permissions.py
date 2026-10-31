"""Role → permission matrix (SPEC 21.3, ADR-025)."""
from __future__ import annotations

import pytest

from eng_ibrahim.domain.enums import UserRole
from eng_ibrahim.domain.permissions import (
    Permission,
    assignable_roles,
    can_edit,
    can_print,
    can_view,
    has_permission,
    is_admin,
    permissions_for,
)


def test_admin_has_every_permission() -> None:
    assert permissions_for(UserRole.ADMIN) == frozenset(Permission)
    assert is_admin(UserRole.ADMIN)
    assert can_edit(UserRole.ADMIN) and can_print(UserRole.ADMIN)


def test_editor_may_edit_and_print_but_not_administer() -> None:
    assert can_edit(UserRole.EDITOR)
    assert can_print(UserRole.EDITOR)
    assert not is_admin(UserRole.EDITOR)


def test_reports_may_print_but_not_edit() -> None:
    assert can_view(UserRole.REPORTS)
    assert can_print(UserRole.REPORTS)
    assert not can_edit(UserRole.REPORTS)
    assert not is_admin(UserRole.REPORTS)


def test_viewer_is_read_only() -> None:
    assert can_view(UserRole.VIEWER)
    assert not can_edit(UserRole.VIEWER)
    assert not can_print(UserRole.VIEWER)


@pytest.mark.parametrize("role", ["storekeeper", "maintenance_engineer", "", "root"])
def test_unknown_role_fails_closed(role: str) -> None:
    assert permissions_for(role) == frozenset({Permission.VIEW})
    assert not can_edit(role) and not can_print(role) and not is_admin(role)


def test_missing_role_is_denied() -> None:
    assert not can_view(None)
    assert not has_permission(None, Permission.VIEW)


def test_assignable_roles_cover_the_four_p0_roles() -> None:
    assert set(assignable_roles()) == {
        UserRole.ADMIN, UserRole.EDITOR, UserRole.REPORTS, UserRole.VIEWER
    }
