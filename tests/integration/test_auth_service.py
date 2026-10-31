"""Local accounts: login, admin commands, and the last-admin invariant (ADR-025)."""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.domain.enums import UserRole
from eng_ibrahim.infrastructure.database.orm_models import AppUser
from eng_ibrahim.infrastructure.security.passwords import hash_secret

PASSWORD = "Workshop#2026"


def _add_user(db, username: str, role: str, password: str | None = PASSWORD,
              active: bool = True) -> str:
    with db.unit_of_work() as s:
        row = AppUser(
            username=username,
            display_name=username.title(),
            password_hash=hash_secret(password) if password else "!reset-required",
            role=role,
            is_active=1 if active else 0,
        )
        s.add(row)
        s.flush()
        return row.id


@pytest.fixture
def seeded(ctx):
    admin_id = _add_user(ctx.db, "admin", UserRole.ADMIN.value)
    auth = AuthService(ctx.db)
    return ctx, auth, auth.get_user(admin_id)


def test_login_success_and_failure(seeded) -> None:
    _ctx, auth, _admin = seeded
    ok = auth.authenticate("ADMIN", PASSWORD)  # username is case-insensitive
    assert ok.ok and ok.value is not None and ok.value.username == "admin"

    assert auth.authenticate("admin", "wrong-password").error_code == "err.login_failed"
    assert auth.authenticate("missing", PASSWORD).error_code == "err.login_failed"


def test_disabled_account_cannot_log_in(seeded) -> None:
    ctx, auth, admin = seeded
    uid = _add_user(ctx.db, "viewer1", UserRole.VIEWER.value, active=False)
    assert auth.authenticate("viewer1", PASSWORD).error_code == "err.user_disabled"
    assert auth.set_active(admin, uid, True).ok
    assert auth.authenticate("viewer1", PASSWORD).ok


def test_viewer_cannot_manage_users(seeded) -> None:
    ctx, auth, _admin = seeded
    uid = _add_user(ctx.db, "reader", UserRole.VIEWER.value)
    viewer = auth.get_user(uid)
    assert viewer is not None and not viewer.is_admin
    result = auth.create_user(viewer, "sneaky", "Sneaky", UserRole.ADMIN.value, PASSWORD)
    assert not result.ok and result.error_code == "err.permission_denied"


def test_admin_creates_user_with_role(seeded) -> None:
    _ctx, auth, admin = seeded
    created = auth.create_user(admin, "tech1", "Technician One", UserRole.EDITOR.value, PASSWORD)
    assert created.ok and created.value is not None
    assert created.value.role == UserRole.EDITOR.value

    duplicate = auth.create_user(admin, "TECH1", "Duplicate", UserRole.VIEWER.value, PASSWORD)
    assert duplicate.error_code == "err.username_exists"

    short = auth.create_user(admin, "tech2", "Short", UserRole.VIEWER.value, "123")
    assert short.error_code == "err.password_too_short"

    bad_role = auth.create_user(admin, "tech3", "Bad", "storekeeper", PASSWORD)
    assert bad_role.error_code == "err.role_invalid"


def test_last_active_admin_is_protected(seeded) -> None:
    _ctx, auth, admin = seeded
    assert admin is not None
    assert auth.set_role(admin, admin.id, UserRole.EDITOR.value).error_code == "err.last_admin"
    assert auth.set_active(admin, admin.id, False).error_code == "err.cannot_disable_self"

    # With a second admin the demotion becomes legal.
    second = auth.create_user(admin, "admin2", "Second", UserRole.ADMIN.value, PASSWORD)
    assert second.ok and second.value is not None
    assert auth.set_role(admin, admin.id, UserRole.EDITOR.value).ok


def test_reset_password_returns_recovery_code_and_new_password_works(seeded) -> None:
    ctx, auth, admin = seeded
    uid = _add_user(ctx.db, "store", UserRole.EDITOR.value)
    result = auth.reset_password(admin, uid, "NewPass#2026")
    assert result.ok and result.value and result.value.count("-") == 3
    assert auth.authenticate("store", "NewPass#2026").ok
    assert not auth.authenticate("store", PASSWORD).ok


def test_change_password_requires_current_password(seeded) -> None:
    _ctx, auth, admin = seeded
    assert admin is not None
    assert auth.change_password(admin.id, "wrong", "Another#2026").error_code == (
        "err.current_password_wrong")
    assert auth.change_password(admin.id, PASSWORD, "Another#2026").ok
    assert auth.authenticate("admin", "Another#2026").ok


def test_login_required_only_when_needed(seeded) -> None:
    ctx, auth, admin = seeded
    assert not auth.login_required()  # single account, owner mode

    _add_user(ctx.db, "second", UserRole.VIEWER.value)
    assert auth.login_required()  # more than one active account


def test_password_reset_sentinel_blocks_login(ctx) -> None:
    uid = _add_user(ctx.db, "legacy", UserRole.ADMIN.value, password=None)
    auth = AuthService(ctx.db)
    assert auth.get_user(uid) is not None
    assert auth.authenticate("legacy", "").error_code == "err.login_failed"
    assert auth.authenticate("legacy", "anything").error_code == "err.password_reset_required"


def test_schema_rejects_legacy_roles(ctx) -> None:
    with pytest.raises(IntegrityError):
        with ctx.db.unit_of_work() as s:
            s.execute(text(
                "INSERT INTO app_users (id, username, display_name, password_hash, role,"
                " is_active, created_at) VALUES ('x1','legacy','Legacy','h','storekeeper',1,'now')"
            ))
