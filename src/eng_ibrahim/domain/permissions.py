"""Role → permission mapping (SPEC 21.3, ADR-025).

The single source of truth for what a role may do. Application services call
these helpers before mutating anything; the UI only hides/disables controls to
match (a disabled button is never the enforcement).
"""
from __future__ import annotations

from enum import StrEnum

from .enums import UserRole


class Permission(StrEnum):
    VIEW = "view"
    EDIT = "edit"
    PRINT = "print"
    ADMIN = "admin"


_ALL: frozenset[Permission] = frozenset(Permission)
_BY_ROLE: dict[str, frozenset[Permission]] = {
    UserRole.ADMIN.value: _ALL,
    UserRole.EDITOR.value: frozenset({Permission.VIEW, Permission.EDIT, Permission.PRINT}),
    UserRole.REPORTS.value: frozenset({Permission.VIEW, Permission.PRINT}),
    UserRole.VIEWER.value: frozenset({Permission.VIEW}),
}
_FALLBACK: frozenset[Permission] = frozenset({Permission.VIEW})  # fail closed


def role_value(role: UserRole | str) -> str:
    return role.value if isinstance(role, UserRole) else str(role)


def permissions_for(role: UserRole | str) -> frozenset[Permission]:
    """Unknown/legacy role values fall back to read-only, never to admin."""
    return _BY_ROLE.get(role_value(role), _FALLBACK)


def has_permission(role: UserRole | str | None, permission: Permission) -> bool:
    if role is None:
        return False
    return permission in permissions_for(role)


def can_view(role: UserRole | str | None) -> bool:
    return has_permission(role, Permission.VIEW)


def can_edit(role: UserRole | str | None) -> bool:
    return has_permission(role, Permission.EDIT)


def can_print(role: UserRole | str | None) -> bool:
    return has_permission(role, Permission.PRINT)


def is_admin(role: UserRole | str | None) -> bool:
    return has_permission(role, Permission.ADMIN)


def assignable_roles() -> tuple[UserRole, ...]:
    """Roles an admin may grant (all four, admin included)."""
    return (UserRole.ADMIN, UserRole.EDITOR, UserRole.REPORTS, UserRole.VIEWER)
