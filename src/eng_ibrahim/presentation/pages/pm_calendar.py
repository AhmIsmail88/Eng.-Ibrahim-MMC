"""PM calendar (UI-012): month grid of preventive-maintenance due dates."""
from __future__ import annotations

import calendar as cal
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ...application.context import AppContext
from ...application.services.pm_service import PMService
from .base import BasePage, make_card, make_title, vbox


class PMCalendarPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = PMService(ctx.db)
        today = date.today()
        self.year, self.month = today.year, today.month
        lay = vbox(self)
        self.title = make_title()
        lay.addWidget(self.title)
        card = make_card()
        bar = QHBoxLayout(card)
        self.btn_prev = QPushButton("◀")
        self.btn_prev.clicked.connect(lambda: self._shift(-1))
        self.btn_next = QPushButton("▶")
        self.btn_next.clicked.connect(lambda: self._shift(1))
        self.period = QLabel()
        self.period.setStyleSheet("font-weight: 600;")
        bar.addWidget(self.btn_prev)
        bar.addWidget(self.period)
        bar.addWidget(self.btn_next)
        bar.addStretch(1)
        lay.addWidget(card)
        self.grid = QTableWidget(6, 7)
        self.grid.verticalHeader().setVisible(False)
        self.grid.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.grid, 1)
        self.retranslate()

    def _shift(self, delta: int) -> None:
        month = self.month + delta
        self.year += (month - 1) // 12
        self.month = (month - 1) % 12 + 1
        self.refresh()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("cal.title"))
        self.grid.setHorizontalHeaderLabels([
            tr("cal.dow.0"), tr("cal.dow.1"), tr("cal.dow.2"), tr("cal.dow.3"),
            tr("cal.dow.4"), tr("cal.dow.5"), tr("cal.dow.6")])
        self.refresh()

    def refresh(self) -> None:
        self.period.setText(f"{self.year}-{self.month:02d}")
        due: dict[str, list[str]] = {}
        for plan in self.service.list():
            if plan.next_due_date:
                due.setdefault(plan.next_due_date, []).append(plan.code)
        first = date(self.year, self.month, 1)
        offset = (first.weekday() + 1) % 7  # Sunday = 0
        days = cal.monthrange(self.year, self.month)[1]
        self.grid.clearContents()
        for day in range(1, days + 1):
            index = offset + day - 1
            row, col = divmod(index, 7)
            if row >= 6:
                break
            iso = f"{self.year}-{self.month:02d}-{day:02d}"
            codes = due.get(iso, [])
            text = f"{day}"
            if codes:
                text += "\n" + "\n".join(codes[:3])
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            if codes:
                item.setToolTip(", ".join(codes))
            self.grid.setItem(row, col, item)
