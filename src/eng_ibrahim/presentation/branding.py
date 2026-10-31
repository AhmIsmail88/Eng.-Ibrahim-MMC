"""Brand assets. If the official icon files are missing, a clearly-marked placeholder is
drawn (ASSET_NEEDED, SPEC 3.1) – never a generic system icon presented as final."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

from ..config import project_root

log = logging.getLogger(__name__)
ICON_PNG = "assets/icons/ENG_IBRAHIM_Icon.png"
ICON_ICO = "assets/icons/ENG_IBRAHIM_Icon.ico"


def _placeholder_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#11345A"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    p.setPen(QColor("#08A7B4"))
    f = QFont("Arial", int(size * 0.34), QFont.Weight.Bold)
    p.setFont(f)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "EI")
    p.end()
    return pm


def icon_files_present() -> bool:
    root = project_root()
    return (root / ICON_PNG).exists() or (root / ICON_ICO).exists()


def load_app_icon() -> QIcon:
    root = project_root()
    for rel in (ICON_ICO, ICON_PNG):
        f: Path = root / rel
        if f.exists():
            return QIcon(str(f))
    log.warning("ASSET_NEEDED: assets/icons/ENG_IBRAHIM_Icon.(ico|png) not found; using placeholder")
    icon = QIcon()
    for s in (16, 32, 48, 64, 128, 256):
        icon.addPixmap(_placeholder_pixmap(s))
    return icon


def logo_pixmap(size: int = 40) -> QPixmap:
    return load_app_icon().pixmap(size, size)
