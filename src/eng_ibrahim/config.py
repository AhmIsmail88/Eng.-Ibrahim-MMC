"""Application constants and persistent-location resolution (SPEC 19.2)."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__

APP_NAME = "ENG. IBRAHIM"
APP_SUBTITLE = "Maintenance Management System"
APP_TAGLINE = "Reliable Equipment · Continuous Operation"
APP_DIR_NAME = "ENG_IBRAHIM"
APP_VERSION = __version__
DB_FILENAME = "maintenance.sqlite3"
ENV_DATA_DIR = "ENG_IBRAHIM_DATA_DIR"  # override for tests / portable runs


def project_root() -> Path:
    """Folder containing read-only resources (assets, migrations)."""
    if getattr(sys, "frozen", False):  # PyInstaller / Nuitka standalone
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def default_data_root() -> Path:
    override = os.environ.get(ENV_DATA_DIR)
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_DIR_NAME


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def db_file(self) -> Path:
        return self.data / DB_FILENAME

    @property
    def attachments(self) -> Path:
        return self.root / "attachments"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def preferences_file(self) -> Path:
        return self.config / "user_preferences.json"

    def ensure(self) -> None:
        for p in (self.data, self.attachments, self.backups, self.logs,
                  self.exports, self.cache, self.config):
            p.mkdir(parents=True, exist_ok=True)


def get_paths(root: Path | None = None) -> AppPaths:
    return AppPaths(root or default_data_root())
