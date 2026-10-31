"""UI preferences (language, theme, window geometry) in user_preferences.json.
Atomic write (temp + replace). Business settings live in the DB (ADR-003)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "language": "ar",
    "theme": "light",
    "sidebar_collapsed": False,
    "window": None,  # {"x":..,"y":..,"w":..,"h":..}
    "last_username": "",  # prefill only; never a secret
}


class PreferencesStore:
    def __init__(self, file: Path) -> None:
        self.file = file
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        self._data = dict(DEFAULTS)
        if not self.file.exists():
            return
        try:
            raw = json.loads(self.file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data.update({k: v for k, v in raw.items() if k in DEFAULTS})
        except (OSError, ValueError):
            log.warning("Preferences file unreadable; using defaults", exc_info=True)

    def get(self, key: str) -> Any:
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        self._data[key] = value
        self.save()

    def save(self) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.file)
