"""First Run Wizard backend (SPEC 21.1): one transaction creates settings, owner user,
reference seed and audit entry. Nothing is half-created if it fails."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select

from ...domain.enums import UserRole
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import AppUser, Currency, LocalRecoveryCode
from ...infrastructure.database.seed_reference_data import seed_reference_data
from ...infrastructure.security.passwords import (
    generate_recovery_code,
    hash_secret,
)
from ..dto.result import Result
from .audit import write_audit
from .settings_service import FIRST_RUN_DONE, SettingsService

MIN_PASSWORD_LEN = 8


class _Abort(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class FirstRunInput:
    station_name_ar: str
    station_name_en: str
    currency_code: str
    timezone: str
    username: str
    display_name: str
    backup_folder: Path
    password: str  # required in 1.0: every account signs in (ADR-025)


@dataclass(frozen=True)
class FirstRunOutput:
    user_id: str
    recovery_code: str | None  # shown ONCE; only its hash is stored


class FirstRunService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def validate(self, data: FirstRunInput) -> Result[None]:
        if not (data.station_name_ar.strip() or data.station_name_en.strip()):
            return Result.failure("err.station_name_required")
        if not data.username.strip():
            return Result.failure("err.username_required")
        if not data.password:
            return Result.failure("err.password_required")
        if len(data.password) < MIN_PASSWORD_LEN:
            return Result.failure("err.password_too_short")
        if not data.currency_code.strip():
            return Result.failure("err.currency_required")
        return Result.success()

    def complete(self, data: FirstRunInput) -> Result[FirstRunOutput]:
        check = self.validate(data)
        if not check.ok:
            return Result.failure(check.error_code or "err.invalid")
        settings = SettingsService(self._db)
        if settings.is_first_run_completed():
            return Result.failure("err.first_run_already_done")

        try:
            return_value = self._create(data)
        except _Abort as abort:  # transaction already rolled back by unit_of_work
            return Result.failure(abort.code)
        return Result.success(return_value)

    def _create(self, data: FirstRunInput) -> FirstRunOutput:
        recovery: str | None = None
        with self._db.unit_of_work() as s:
            seed_reference_data(s)
            if s.get(Currency, data.currency_code) is None:
                raise _Abort("err.currency_unknown")
            exists = s.scalar(select(AppUser.id).where(
                func.lower(AppUser.username) == data.username.strip().lower()))
            if exists:
                raise _Abort("err.username_exists")

            has_password = True
            user = AppUser(
                username=data.username.strip(),
                display_name=(data.display_name or data.username).strip(),
                password_hash=hash_secret(data.password),
                role=UserRole.ADMIN.value,
            )
            s.add(user)
            s.flush()
            recovery = generate_recovery_code()
            s.add(LocalRecoveryCode(user_id=user.id, code_hash=hash_secret(recovery)))

            for key, value in {
                "station_name_ar": data.station_name_ar.strip(),
                "station_name_en": data.station_name_en.strip(),
                "currency_code": data.currency_code,
                "timezone": data.timezone,
                "backup_folder": str(data.backup_folder),
                "backup_retention": 10,
                "local_login_enabled": has_password,
                FIRST_RUN_DONE: True,
            }.items():
                SettingsService.set_in(s, key, value)

            write_audit(s, "app", None, "first_run_completed", actor_id=user.id,
                        after={"station_name_ar": data.station_name_ar.strip(),
                               "station_name_en": data.station_name_en.strip(),
                               "currency_code": data.currency_code,
                               "username": user.username, "password_set": has_password})
            return FirstRunOutput(user_id=user.id, recovery_code=recovery)
