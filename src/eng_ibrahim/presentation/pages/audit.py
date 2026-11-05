"""Audit log screen (UI-022): read-only history of sensitive changes.

Filters by period, user and record type; pages through the whole history 300 events at
a time; exports what is filtered; a double-click opens the record (review F-08/F-23).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, QDateTime, QTime, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ...application.context import AppContext
from ...application.services.audit_view import PAGE_SIZE, AuditFilter, AuditViewService
from ..widgets.tables import polish_table, sortable
from .base import BasePage, local_time, make_card, make_title, vbox

# audit entity types that have a screen to open
_OPENABLE = {"asset": "asset", "work_order": "work_order", "part": "part",
             "vehicle": "vehicle"}


class AuditPage(BasePage):
    open_requested = Signal(str, str)  # search kind, record id

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = AuditViewService(ctx.db)
        self._rows: list = []
        lay = vbox(self)
        self.title = make_title()
        lay.addWidget(self.title)
        card = make_card()
        card_lay = QHBoxLayout(card)
        self.filter = QComboBox()
        self.actor = QComboBox()
        self.lbl_from, self.lbl_to = QLabel(), QLabel()
        self.date_from = QDateEdit(QDate.currentDate().addDays(-30))
        self.date_to = QDateEdit(QDate.currentDate())
        for edit in (self.date_from, self.date_to):
            edit.setCalendarPopup(True)
            edit.dateChanged.connect(lambda _d: self.refresh())
        for combo in (self.filter, self.actor):
            combo.currentIndexChanged.connect(lambda _i: self.refresh())
        self.btn_export = QPushButton()
        self.btn_export.clicked.connect(self._export)
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        for widget in (self.filter, self.actor, self.lbl_from, self.date_from, self.lbl_to,
                       self.date_to):
            card_lay.addWidget(widget)
        card_lay.addStretch(1)
        card_lay.addWidget(self.btn_export)
        card_lay.addWidget(self.btn_refresh)
        lay.addWidget(card)
        self.table = QTableWidget(0, 6)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        polish_table(self.table, lambda: self.ctx.tr("common.no_data"))
        sortable(self.table, self)  # header click sorts (F-14)
        self.table.cellDoubleClicked.connect(self._open_row)
        lay.addWidget(self.table, 1)
        footer = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("hint")
        self.btn_more = QPushButton()
        self.btn_more.clicked.connect(self._more)
        footer.addWidget(self.status)
        footer.addStretch(1)
        footer.addWidget(self.btn_more)
        lay.addLayout(footer)
        self.retranslate()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("audit.title"))
        self.btn_refresh.setText(tr("common.refresh"))
        self.btn_export.setText(tr("audit.export"))
        self.btn_more.setText(tr("audit.more"))
        self.lbl_from.setText(tr("reports.from"))
        self.lbl_to.setText(tr("reports.to"))
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "audit.at", "audit.actor", "audit.action", "audit.entity", "audit.record",
            "audit.reason")])
        self._fill(self.filter, tr("audit.all_records"),
                   [(kind, kind) for kind in self.service.entity_types()])
        self._fill(self.actor, tr("audit.all_users"),
                   [(name, uid) for uid, name in self.service.actors()])
        self.refresh()

    @staticmethod
    def _fill(combo: QComboBox, everything: str, items) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(everything, None)
        for text, value in items:
            combo.addItem(text, value)
        combo.setCurrentIndex(max(0, combo.findData(current)))
        combo.blockSignals(False)

    def _filter(self) -> AuditFilter:
        # The period is picked in local days; the log stores UTC.
        since = QDateTime(self.date_from.date(), QTime(0, 0)).toUTC()
        until = QDateTime(self.date_to.date(), QTime(23, 59, 59)).toUTC()
        return AuditFilter(entity_type=self.filter.currentData(),
                           actor_id=self.actor.currentData(),
                           since=since.toString("yyyy-MM-ddTHH:mm:ss"),
                           until=until.toString("yyyy-MM-ddTHH:mm:ss") + ".999999Z")

    def refresh(self) -> None:
        self._rows = []
        self.table.setRowCount(0)
        self._load_page()

    def _more(self) -> None:
        self._load_page()

    def _load_page(self) -> None:
        flt = self._filter()
        page = self.service.list(offset=len(self._rows), limit=PAGE_SIZE, flt=flt)
        start = len(self._rows)
        self._rows.extend(page)
        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(page, start=start):
            record = row.entity_code or (row.entity_id or "")[:8]
            cells = (local_time(row.at), row.actor, row.action, row.entity_type, record,
                     row.reason or "")
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 4 and row.entity_id:
                    item.setToolTip(row.entity_id)
                self.table.setItem(i, col, item)
        total = self.service.count(flt)
        self.status.setText(self.ctx.tr("audit.showing", shown=len(self._rows), total=total))
        self.btn_more.setEnabled(len(self._rows) < total)

    def _open_row(self, row: int, _column: int) -> None:
        if not 0 <= row < len(self._rows):
            return
        entry = self._rows[row]
        kind = _OPENABLE.get(entry.entity_type)
        if kind and entry.entity_id:
            self.open_requested.emit(kind, entry.entity_id)

    def _export(self) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        default = str(Path.home() / "Documents" / f"ENG_IBRAHIM_audit_{stamp}.csv")
        path, _f = QFileDialog.getSaveFileName(self, self.ctx.tr("audit.export"), default,
                                               "CSV (*.csv)")
        if not path:
            return
        count = self.service.export_csv(Path(path), self._filter())
        QMessageBox.information(self, self.ctx.tr("audit.export"),
                                self.ctx.tr("audit.exported", count=count, path=path))
