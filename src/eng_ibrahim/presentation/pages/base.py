from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from ...application.context import AppContext


class BasePage(QWidget):
    """Every page implements retranslate() so language switching is live."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.setObjectName("pageRoot")
        self.ctx = ctx

    def retranslate(self) -> None:  # pragma: no cover - overridden
        pass

    def refresh(self) -> None:  # called on F5 / page activation
        pass


def make_card() -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    return card


def make_title(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("pageTitle")
    return lbl


def vbox(parent: QWidget, margins: int = 24, spacing: int = 16) -> QVBoxLayout:
    lay = QVBoxLayout(parent)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    return lay


def set_ltr_value(label: QLabel, text: str, rtl_page: bool) -> None:
    """Paths/versions/codes stay LTR and readable inside an RTL page (SPEC 3.4)."""
    label.setText(text)
    label.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    label.setAlignment((Qt.AlignmentFlag.AlignRight if rtl_page else Qt.AlignmentFlag.AlignLeft)
                       | Qt.AlignmentFlag.AlignVCenter)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setWordWrap(True)


def scrollable(content: QWidget) -> QScrollArea:
    """Wrap content that must never be squeezed below its size (forms, detail panes)."""
    area = QScrollArea()
    area.setObjectName("plainScroll")
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content.setObjectName(content.objectName() or "scrollContent")
    area.setWidget(content)
    return area


def isolate(text: str) -> str:
    """Let each value pick its own direction (codes and dates inside Arabic text)."""
    return f"⁨{text}⁩"


def local_time(iso_utc: str) -> str:
    """Stored timestamps are UTC ISO strings; screens show local wall-clock time."""
    try:
        stamp = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    except ValueError:
        return iso_utc[:16].replace("T", " ")
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone().strftime("%Y-%m-%d %H:%M")


def select_row(table, rows, record_id: str, attr: str = "id") -> bool:
    """Select the table row whose record has `record_id`; False when it is not listed."""
    for index, row in enumerate(rows):
        if getattr(row, attr) == record_id:
            table.setCurrentCell(index, 0)
            table.scrollToItem(table.item(index, 0))
            return True
    return False
