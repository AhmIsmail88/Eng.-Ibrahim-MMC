"""Sidebar entry whose icon/label follow the layout direction.

A style-sheeted QPushButton always paints its icon to the left of the text, which puts
the icon after the label in Arabic. Laying out a QLabel pair inside the button keeps
icon-then-text in reading order for both directions.
"""
from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from ..icons import ICON_SIZE


class NavButton(QPushButton):
    def __init__(self) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setMinimumHeight(38)
        self._icon = QIcon()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(12)
        self.icon_label = QLabel()
        self.icon_label.setObjectName("navIcon")
        self.icon_label.setFixedSize(ICON_SIZE)
        self.text_label = QLabel()
        self.text_label.setObjectName("navText")
        lay.addStretch(0)
        lay.addWidget(self.icon_label)
        lay.addWidget(self.text_label)
        lay.addStretch(1)
        self.toggled.connect(lambda _checked: self._sync())

    def set_icon(self, icon: QIcon) -> None:
        self._icon = icon
        self._sync()

    def set_label(self, text: str) -> None:
        """An empty label means collapsed: the icon is centred on its own."""
        self.text_label.setText(text)
        self.text_label.setVisible(bool(text))
        lay = self.layout()
        lay.setStretch(0, 0 if text else 1)

    def _sync(self) -> None:
        state = QIcon.State.On if self.isChecked() else QIcon.State.Off
        self.icon_label.setPixmap(self._icon.pixmap(ICON_SIZE, QIcon.Mode.Normal, state))
        self.text_label.setProperty("active", self.isChecked())
        self.text_label.style().unpolish(self.text_label)
        self.text_label.style().polish(self.text_label)
