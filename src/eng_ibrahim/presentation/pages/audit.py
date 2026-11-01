"""Audit log screen (UI-022): read-only history of sensitive changes."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ...application.context import AppContext
from ...application.services.audit_view import AuditViewService
from .base import BasePage, make_card, make_title, vbox


class AuditPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = AuditViewService(ctx.db)
        lay = vbox(self)
        self.title = make_title()
        lay.addWidget(self.title)
        card = make_card()
        card_lay = QHBoxLayout(card)
        self.filter = QComboBox()
        self.filter.currentIndexChanged.connect(lambda _i: self.refresh())
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        card_lay.addWidget(self.filter)
        card_lay.addStretch(1)
        card_lay.addWidget(self.btn_refresh)
        lay.addWidget(card)
        self.table = QTableWidget(0, 5)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)
        self.retranslate()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("audit.title"))
        self.btn_refresh.setText(tr("common.refresh"))
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "audit.at", "audit.actor", "audit.action", "audit.entity", "audit.reason")])
        current = self.filter.currentData()
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.addItem(tr("assets.all"), None)
        for kind in self.service.entity_types():
            self.filter.addItem(kind, kind)
        index = self.filter.findData(current)
        self.filter.setCurrentIndex(max(0, index))
        self.filter.blockSignals(False)
        self.refresh()

    def refresh(self) -> None:
        rows = self.service.list(self.filter.currentData())
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            cells = (row.at[:19].replace("T", " "), row.actor, row.action,
                     row.entity_type, row.reason or "")
            for col, text in enumerate(cells):
                self.table.setItem(i, col, QTableWidgetItem(text))
