"""Localization service (SPEC 0.6): all UI text goes through `tr()`. Qt-free for testing."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ..domain.enums import Language

_DIR = Path(__file__).parent


def _candidates() -> list[Path]:
    """Where the JSON tables can live: source tree, PyInstaller bundle, installed package."""
    roots: list[Path] = [_DIR]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        base = Path(bundle)
        roots += [base / "eng_ibrahim" / "localization", base / "localization"]
    roots += [
        _DIR.parents[2] / "src" / "eng_ibrahim" / "localization",
        _DIR.parent / "localization",
    ]
    seen: list[Path] = []
    for root in roots:
        if root not in seen:
            seen.append(root)
    return seen


def table_path(language: Language) -> Path:
    name = f"{language.value}.json"
    for root in _candidates():
        candidate = root / name
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(root) for root in _candidates())
    raise FileNotFoundError(f"localization table {name} not found; searched: {searched}")
_RTL = {Language.AR}


class Localizer:
    def __init__(self, language: Language | str = Language.AR) -> None:
        self._cache: dict[Language, dict[str, str]] = {}
        self.language = Language(language)

    def _table(self, lang: Language) -> dict[str, str]:
        if lang not in self._cache:
            data = json.loads(table_path(lang).read_text(encoding="utf-8"))
            self._cache[lang] = data
        return self._cache[lang]

    def set_language(self, language: Language | str) -> None:
        self.language = Language(language)

    @property
    def is_rtl(self) -> bool:
        return self.language in _RTL

    def tr(self, key: str, **params: object) -> str:
        text = self._table(self.language).get(key)
        if text is None:  # fallback to English, then to the key (visible, never crash)
            text = self._table(Language.EN).get(key, key)
        try:
            return text.format(**params) if params else text
        except (KeyError, IndexError):
            return text
