from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

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
