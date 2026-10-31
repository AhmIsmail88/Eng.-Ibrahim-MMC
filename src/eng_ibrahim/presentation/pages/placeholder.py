from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from ...application.context import AppContext
from .base import BasePage, make_card, make_title, vbox


class PlaceholderPage(BasePage):
    """Honest empty state for sections scheduled in later phases: no fake buttons or data."""

    def __init__(self, ctx: AppContext, nav_key: str, phase: int) -> None:
        super().__init__(ctx)
        self.nav_key, self.phase = nav_key, phase
        lay = vbox(self)
        self.title = make_title()
        card = make_card()
        inner = vbox(card, 32, 8)
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size: 13pt; font-weight: 600;")
        self.body = QLabel()
        self.body.setObjectName("hint")
        self.body.setWordWrap(True)
        inner.addWidget(self.heading)
        inner.addWidget(self.body)
        lay.addWidget(self.title)
        lay.addWidget(card)
        lay.addStretch(1)
        self.title.setAlignment(Qt.AlignmentFlag.AlignLeading)
        self.retranslate()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr(self.nav_key))
        self.heading.setText(tr("placeholder.title"))
        self.body.setText(tr("placeholder.body", phase=tr(f"phase.{self.phase}")))
