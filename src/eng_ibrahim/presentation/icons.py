"""Line icons drawn in the theme colour (24×24 grid, 2px round strokes).

Font glyphs (◧ ⚙ ▤) render as tofu boxes or colour emoji depending on the machine,
so the shell draws its own icons from these SVG paths instead.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS: dict[str, str] = {
    "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1.5"/>'
                 '<rect x="14" y="3" width="7" height="5" rx="1.5"/>'
                 '<rect x="14" y="12" width="7" height="9" rx="1.5"/>'
                 '<rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "assets": '<path d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5z"/><path d="M4 7.5 12 12l8-4.5"/>'
              '<path d="M12 12v9"/>',
    "work_orders": '<rect x="5" y="4" width="14" height="17" rx="2"/>'
                   '<path d="M9 4V3h6v1"/><path d="M9 10h6M9 14h6M9 18h3"/>',
    "preventive": '<path d="M20 12a8 8 0 1 1-2.34-5.66"/><path d="M20 4v5h-5"/>'
                  '<path d="M12 8v4l3 2"/>',
    "corrective": '<path d="M14.5 5.5a4 4 0 0 0 4.9 4.9L21 12l-9 9-3-3 9-9-1.6-1.6a4 4 0 0 1-4.9-4.9'
                  'l2.6 2.6 2.1-.6.6-2.1z"/><path d="M5 19l-2 2"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18"/>'
                '<path d="M8 3v4M16 3v4"/><path d="M8 14h2M14 14h2M8 17h2"/>',
    "vehicles": '<path d="M3 16V7h11v9"/><path d="M14 10h4l3 3v3h-7"/>'
                '<circle cx="7" cy="17.5" r="1.8"/><circle cx="17" cy="17.5" r="1.8"/>',
    "checklists": '<rect x="4" y="4" width="16" height="16" rx="2"/>'
                  '<path d="m8 12 3 3 5-6"/>',
    "spare_parts": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3'
                   'M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    "technicians": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/>'
                   '<path d="M16 4.5a3.5 3.5 0 0 1 0 7M18.5 14.5A6.5 6.5 0 0 1 21.5 20"/>',
    "master_data": '<ellipse cx="12" cy="5.5" rx="8" ry="2.5"/>'
                   '<path d="M4 5.5v13c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5v-13"/>'
                   '<path d="M4 12c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5"/>',
    "audit": '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 7v5l3.5 2"/>',
    "notifications": '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/>'
                     '<path d="M10 20.5a2 2 0 0 0 4 0"/>',
    "suppliers": '<path d="M3 9.5 5 4h14l2 5.5"/><path d="M4 9.5V20h16V9.5"/>'
                 '<path d="M3 9.5h18"/><path d="M10 20v-5h4v5"/>',
    "purchases": '<path d="M3 4h2.5l2.2 11h10.6L20.5 8H7"/>'
                 '<circle cx="9" cy="19.5" r="1.5"/><circle cx="17" cy="19.5" r="1.5"/>',
    "reports": '<path d="M4 20h16"/><rect x="5.5" y="11" width="3" height="6" rx=".5"/>'
               '<rect x="10.5" y="6" width="3" height="11" rx=".5"/>'
               '<rect x="15.5" y="13" width="3" height="4" rx=".5"/>',
    "users": '<path d="M12 3 4.5 6v5.5c0 4.5 3.2 8 7.5 9.5 4.3-1.5 7.5-5 7.5-9.5V6z"/>'
             '<circle cx="12" cy="10" r="2.5"/><path d="M8 16.5a4 4 0 0 1 8 0"/>',
    "settings": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/>'
                '<circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/>'
                '<circle cx="18" cy="18" r="2"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.2a2.6 2.6 0 0 1 5 .9c0 1.7-2.5 2.3-2.5 4"/>'
            '<path d="M12 17.2h0"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2'
           'M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
}


def names() -> list[str]:
    return sorted(_PATHS)


def _svg(name: str, color: str) -> bytes:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="1.9" stroke-linecap="round" '
            f'stroke-linejoin="round">{_PATHS[name]}</svg>').encode()


def pixmap(name: str, color: str, size: int = 20) -> QPixmap:
    app = QGuiApplication.instance()
    ratio = app.devicePixelRatio() if app is not None else 1.0  # type: ignore[attr-defined]
    side = max(1, round(size * ratio))
    pm = QPixmap(side, side)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(_svg(name, color))).render(painter, QRectF(0, 0, side, side))
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str, checked_color: str | None = None, size: int = 20) -> QIcon:
    result = QIcon()
    result.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(pixmap(name, checked_color or color, size), QIcon.Mode.Normal,
                     QIcon.State.On)
    return result


ICON_SIZE = QSize(20, 20)
