"""Notifications screen (UI-018): derived alerts, read-only."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ...application.context import AppContext
from ...application.services.notification_service import NotificationService
from ..widgets.tables import polish_table
from .base import BasePage, make_card, make_title, vbox


class NotificationsPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = NotificationService(ctx.db)
        lay = vbox(self)
        self.title = make_title()
        lay.addWidget(self.title)
        self.summary = QLabel()
        self.summary.setObjectName("hint")
        lay.addWidget(self.summary)
        card = make_card()
        card_lay = QHBoxLayout(card)
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        card_lay.addStretch(1)
        card_lay.addWidget(self.btn_refresh)
        lay.addWidget(card)
        self.table = QTableWidget(0, 3)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        polish_table(self.table, lambda: self.ctx.tr("common.no_data"))
        lay.addWidget(self.table, 1)
        self.retranslate()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("notify.title"))
        self.btn_refresh.setText(tr("common.refresh"))
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "notify.severity", "notify.message", "notify.detail")])
        self.refresh()

    def refresh(self) -> None:
        rows = self.service.scan()
        critical = sum(1 for r in rows if r.severity == "critical")
        warning = len(rows) - critical
        self.summary.setText(self.ctx.tr("notify.summary", critical=critical,
                                         warning=warning))
        self.table.setRowCount(len(rows))
        for i, notice in enumerate(rows):
            cells = (self.ctx.tr(f"severity.{notice.severity}"),
                     self.ctx.tr(notice.title_key), notice.detail)
            for col, text in enumerate(cells):
                self.table.setItem(i, col, QTableWidgetItem(text))
