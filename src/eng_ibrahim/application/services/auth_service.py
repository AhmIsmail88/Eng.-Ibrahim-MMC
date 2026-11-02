"""Local accounts, login and role enforcement (SPEC 21.3, ADR-025).

Enforcement lives here, not in widgets: every mutating call takes the acting
user and rejects it when the role lacks the permission. The UI mirrors these
rules by hiding/disabling controls, but a disabled button is never the guard.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...domain.enums import UserRole
from ...domain.permissions import can_edit, can_print, is_admin
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import AppUser, LocalRecoveryCode
from ...infrastructure.database.orm_models.base import utcnow_iso
from ...infrastructure.security.passwords import (
    MIN_PASSWORD_LEN,
    RESET_SENTINEL,
    generate_recovery_code,
    hash_secret,
    verify_secret,
)
from ..dto.result import Result
from .audit import write_audit
from .settings_service import SettingsService

LOCAL_LOGIN_ENABLED = "local_login_enabled"

# Verified against a wrong password so a missing username costs the same time.
_DUMMY_HASH = hash_secret("eng-ibrahim-dummy-password")


@dataclass(frozen=True)
class AuthUser:
    id: str
    username: str
    display_name: str
    role: str
    is_active: bool
    created_at: str

    @property
    def can_edit(self) -> bool:
        return can_edit(self.role)

    @property
    def can_print(self) -> bool:
        return can_print(self.role)

    @property
    def is_admin(self) -> bool:
        return is_admin(self.role)

    @property
    def role_label_key(self) -> str:
        return f"users.role.{self.role}"


def _to_dto(row: AppUser) -> AuthUser:
    return AuthUser(
        id=row.id,
        username=row.username,
        display_name=row.display_name,
        role=row.role,
        is_active=bool(row.is_active),
        created_at=row.created_at,
    )


def _validate_password(password: str) -> Result[None]:
    if len(password or "") < MIN_PASSWORD_LEN:
        return Result.failure("err.password_too_short",
                              f"min length is {MIN_PASSWORD_LEN}")
    return Result.success()


class AuthService:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._settings = SettingsService(db)

    # ---------------- state ----------------
    def active_count(self) -> int:
        with self._db.session() as s:
            return int(s.scalar(
                select(func.count()).select_from(AppUser).where(AppUser.is_active == 1)
            ) or 0)

    def login_required(self) -> bool:
        """Owner mode: a single password-less admin never sees a login screen."""
        count = self.active_count()
        if count == 0:
            return False
        if count > 1:
            return True
        return bool(self._settings.get(LOCAL_LOGIN_ENABLED, False))

    def list_users(self) -> list[AuthUser]:
        with self._db.session() as s:
            rows = s.scalars(select(AppUser).order_by(func.lower(AppUser.username))).all()
            return [_to_dto(r) for r in rows]

    def get_user(self, user_id: str) -> AuthUser | None:
        with self._db.session() as s:
            row = s.get(AppUser, user_id)
            return _to_dto(row) if row else None

    def sole_active_user(self) -> AuthUser | None:
        """Owner mode: the single active account acts without a login screen."""
        with self._db.session() as s:
            rows = s.scalars(
                select(AppUser).where(AppUser.is_active == 1).limit(2)).all()
            return _to_dto(rows[0]) if len(rows) == 1 else None

    # ---------------- login ----------------
    def authenticate(self, username: str, password: str) -> Result[AuthUser]:
        name = (username or "").strip().lower()
        if not name or not password:
            return Result.failure("err.login_failed")
        with self._db.session() as s:
            row = s.scalar(select(AppUser).where(func.lower(AppUser.username) == name))
            if row is None:
                # Same failure shape and cost as a wrong password (no user enumeration).
                verify_secret(_DUMMY_HASH, password)
                return Result.failure("err.login_failed")
            if row.password_hash == RESET_SENTINEL:
                return Result.failure("err.password_reset_required")
            if not verify_secret(row.password_hash, password):
                return Result.failure("err.login_failed")
            if not row.is_active:
                return Result.failure("err.user_disabled")
            return Result.success(_to_dto(row))

    # ---------------- admin commands ----------------
    def create_user(self, actor: AuthUser | None, username: str, display_name: str,
                    role: str, password: str) -> Result[AuthUser]:
        guard = self._admin_guard(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        name = (username or "").strip()
        if not name:
            return Result.failure("err.username_required")
        if role not in {r.value for r in UserRole}:
            return Result.failure("err.role_invalid")
        check = _validate_password(password)
        if not check.ok:
            return Result.failure(check.error_code or "err.password_too_short")
        with self._db.unit_of_work() as s:
            exists = s.scalar(select(AppUser.id).where(
                func.lower(AppUser.username) == name.lower()))
            if exists:
                return Result.failure("err.username_exists")
            row = AppUser(
                username=name,
                display_name=(display_name or name).strip(),
                password_hash=hash_secret(password),
                role=role,
            )
            s.add(row)
            s.flush()
            write_audit(s, "app_user", row.id, "user_created", actor_id=actor.id if actor else None,
                        after={"username": row.username, "role": role})
            return Result.success(_to_dto(row))

    def set_role(self, actor: AuthUser | None, user_id: str, role: str) -> Result[None]:
        guard = self._admin_guard(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if role not in {r.value for r in UserRole}:
            return Result.failure("err.role_invalid")
        with self._db.unit_of_work() as s:
            row = s.get(AppUser, user_id)
            if row is None:
                return Result.failure("err.user_not_found")
            if row.role == role:
                return Result.success()
            if (row.role == UserRole.ADMIN.value and bool(row.is_active)
                    and not self._other_active_admin(s, row.id)):
                return Result.failure("err.last_admin")
            before = row.role
            row.role = role
            write_audit(s, "app_user", row.id, "user_role_changed",
                        actor_id=actor.id if actor else None,
                        before={"role": before}, after={"role": role})
            return Result.success()

    def set_active(self, actor: AuthUser | None, user_id: str, active: bool) -> Result[None]:
        guard = self._admin_guard(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if actor is not None and actor.id == user_id and not active:
            return Result.failure("err.cannot_disable_self")
        with self._db.unit_of_work() as s:
            row = s.get(AppUser, user_id)
            if row is None:
                return Result.failure("err.user_not_found")
            if bool(row.is_active) == active:
                return Result.success()
            if (not active and row.role == UserRole.ADMIN.value
                    and not self._other_active_admin(s, row.id)):
                return Result.failure("err.last_admin")
            row.is_active = 1 if active else 0
            write_audit(s, "app_user", row.id,
                        "user_enabled" if active else "user_disabled",
                        actor_id=actor.id if actor else None)
            return Result.success()

    def reset_password(self, actor: AuthUser | None, user_id: str,
                       new_password: str) -> Result[str]:
        """Admin reset. Returns a fresh one-time recovery code for the target user."""
        guard = self._admin_guard(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        check = _validate_password(new_password)
        if not check.ok:
            return Result.failure(check.error_code or "err.password_too_short")
        with self._db.unit_of_work() as s:
            row = s.get(AppUser, user_id)
            if row is None:
                return Result.failure("err.user_not_found")
            row.password_hash = hash_secret(new_password)
            # Only the code handed out now stays valid.
            now = utcnow_iso()
            for old in s.scalars(select(LocalRecoveryCode).where(
                    LocalRecoveryCode.user_id == row.id,
                    LocalRecoveryCode.used_at.is_(None))):
                old.used_at = now
            code = generate_recovery_code()
            s.add(LocalRecoveryCode(user_id=row.id, code_hash=hash_secret(code)))
            write_audit(s, "app_user", row.id, "password_reset",
                        actor_id=actor.id if actor else None)
            return Result.success(code)

    # ---------------- self service ----------------
    def change_password(self, user_id: str, current_password: str,
                        new_password: str) -> Result[None]:
        check = _validate_password(new_password)
        if not check.ok:
            return Result.failure(check.error_code or "err.password_too_short")
        with self._db.unit_of_work() as s:
            row = s.get(AppUser, user_id)
            if row is None:
                return Result.failure("err.user_not_found")
            if not verify_secret(row.password_hash, current_password):
                return Result.failure("err.current_password_wrong")
            row.password_hash = hash_secret(new_password)
            self._settings.set_in(s, LOCAL_LOGIN_ENABLED, True)
            write_audit(s, "app_user", row.id, "password_changed", actor_id=row.id)
            return Result.success()

    # ---------------- helpers ----------------
    @staticmethod
    def _admin_guard(actor: AuthUser | None) -> Result[None]:
        if actor is None or not actor.is_admin:
            return Result.failure("err.permission_denied")
        return Result.success()

    @staticmethod
    def _other_active_admin(session: Session, exclude_id: str) -> bool:
        return bool(session.scalar(
            select(func.count()).select_from(AppUser).where(
                AppUser.role == UserRole.ADMIN.value,
                AppUser.is_active == 1,
                AppUser.id != exclude_id,
            )
        ))
