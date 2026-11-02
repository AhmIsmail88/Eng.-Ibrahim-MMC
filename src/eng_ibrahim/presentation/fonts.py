"""Font resolution (SPEC 3.2): prefer bundled fonts, fall back to what the OS has.

Qt does not ship fonts. In a packaged build the only guaranteed Arabic coverage is a
font we bundle ourselves under `assets/fonts/`; otherwise we must fall back to a system
family that actually exists, not to a hard-coded name that may be missing.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QFontDatabase

from ..config import project_root

log = logging.getLogger(__name__)

PREFERRED = ["Cairo", "Noto Sans Arabic", "Segoe UI", "Tahoma", "Inter", "Arial"]


def bundled_font_families() -> list[str]:
    folder = Path(project_root()) / "assets" / "fonts"
    families: list[str] = []
    if not folder.exists():
        return families
    for file in sorted(folder.glob("*.ttf")) + sorted(folder.glob("*.otf")):
        font_id = QFontDatabase.addApplicationFont(str(file))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    if families:
        log.info("Bundled fonts registered: %s", ", ".join(families))
    return families


def resolve_ui_family() -> str | None:
    """Return the first preferred family that exists, else the first system family."""
    # Register bundled fonts *before* listing families, or a font that is only bundled
    # (not installed on this machine) is never found.
    bundled = bundled_font_families()
    available = set(QFontDatabase.families())
    for family in PREFERRED + bundled:
        if family in available:
            return family
    if available:
        fallback = sorted(available)[0]
        log.warning("FONT_FALLBACK: none of %s available; using %s", PREFERRED, fallback)
        return fallback
    log.warning("FONT_UNAVAILABLE: Qt sees no fonts. Bundle assets/fonts/*.ttf for a "
                "deterministic Arabic render.")
    return None
