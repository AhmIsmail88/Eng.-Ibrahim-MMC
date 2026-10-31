"""Composition root data holder (no global singletons holding sessions)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..config import AppPaths
from ..infrastructure.database.engine import Database
from ..infrastructure.storage.preferences import PreferencesStore
from ..localization.service import Localizer
from .services.settings_service import SettingsService

if TYPE_CHECKING:  # pragma: no cover
    from .services.auth_service import AuthUser


@dataclass
class AppContext:
    paths: AppPaths
    db: Database
    prefs: PreferencesStore
    localizer: Localizer
    settings: SettingsService
    schema_revision: str = ""
    db_ok: bool = True
    profile_name: str = ""
    extras: dict[str, object] = field(default_factory=dict)
    current_user: AuthUser | None = None

    def tr(self, key: str, **params: object) -> str:
        return self.localizer.tr(key, **params)

    # ---- permission mirrors for the UI (enforcement lives in the services) ----
    @property
    def can_edit(self) -> bool:
        return bool(self.current_user and self.current_user.can_edit)

    @property
    def can_print(self) -> bool:
        return bool(self.current_user and self.current_user.can_print)

    @property
    def is_admin(self) -> bool:
        return bool(self.current_user and self.current_user.is_admin)
