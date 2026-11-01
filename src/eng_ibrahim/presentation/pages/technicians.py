"""Technicians screen (UI-016): roster + create/deactivate (SPEC 13)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...application.context import AppContext
from ...application.services.master_data_service import MasterDataService
from .base import BasePage, make_card, make_title, vbox

TRADES = ("Mechanical", "Electrical", "Instrumentation", "Vehicle", "General")


class NewTechnicianDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setModal(True)
        self.setMinimumWidth(440)
        form = QFormLayout(self)
        self.code, self.name = QLineEdit(), QLineEdit()
        self.trade = QComboBox()
        self.trade.addItems(TRADES)
        self.department = QLineEdit()
        self.rate = QDoubleSpinBox()
        self.rate.setMaximum(1_000_000)
        self.rate.setDecimals(2)
        self.lbl_code = QLabel(ctx.tr("tech.code"))
        self.lbl_name = QLabel(ctx.tr("tech.name"))
        self.lbl_trade = QLabel(ctx.tr("tech.trade"))
        self.lbl_dept = QLabel(ctx.tr("tech.department"))
        self.lbl_rate = QLabel(ctx.tr("tech.rate"))
        for label, widget in ((self.lbl_code, self.code), (self.lbl_name, self.name),
                              (self.lbl_trade, self.trade),
                              (self.lbl_dept, self.department), (self.lbl_rate, self.rate)):
            form.addRow(label, widget)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        self.setWindowTitle(ctx.tr("tech.new"))

    def payload(self) -> dict:
        return dict(code=self.code.text(), full_name=self.name.text(),
                    trade=self.trade.currentText(),
                    department=self.department.text().strip() or None,
                    hourly_rate_minor=int(round(self.rate.value() * 100)) or None,
                    currency=self.ctx.settings.get("currency_code", "EGP"))


class TechniciansPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = MasterDataService(ctx.db)
        self._rows: list = []
        self._build()
        self.retranslate()

    def _build(self) -> None:
        lay = vbox(self)
        self.title = make_title()
        lay.addWidget(self.title)
        card = make_card()
        card_lay = QVBoxLayout(card)
        bar = QHBoxLayout()
        self.btn_new = QPushButton()
        self.btn_new.clicked.connect(self._new)
        self.btn_toggle = QPushButton()
        self.btn_toggle.clicked.connect(self._toggle)
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        bar.addStretch(1)
        for btn in (self.btn_new, self.btn_toggle, self.btn_refresh):
            bar.addWidget(btn)
        card_lay.addLayout(bar)
        self.table = QTableWidget(0, 5)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        card_lay.addWidget(self.table)
        lay.addWidget(card, 1)

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("tech.title"))
        self.btn_new.setText(tr("tech.new"))
        self.btn_toggle.setText(tr("tech.toggle"))
        self.btn_refresh.setText(tr("common.refresh"))
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "tech.code", "tech.name", "tech.trade", "tech.department", "users.status")])
        self.refresh()

    def refresh(self) -> None:
        self._rows = self.service.technician_rows()
        self.table.setRowCount(len(self._rows))
        for i, (tech_id, code, name, trade, dept, active) in enumerate(self._rows):
            cells = (code, name, trade, dept,
                     self.ctx.tr("users.active" if active else "users.inactive"))
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, tech_id)
                self.table.setItem(i, col, item)
        if self._rows and self.table.currentRow() < 0:
            self.table.setCurrentCell(0, 0)
        self.btn_toggle.setEnabled(self.ctx.can_edit)

    def _selected(self):
        row = self.table.currentRow()
        if row < 0 and self._rows:
            row = 0
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _new(self) -> None:
        if not self.ctx.can_edit:
            return
        dialog = NewTechnicianDialog(self.ctx, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.service.create_technician(self.ctx.current_user, **dialog.payload())
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("tech.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()

    def _toggle(self) -> None:
        tech = self._selected()
        if tech is None:
            return
        tech_id, _code, _name, _trade, _dept, active = tech
        result = self.service.set_technician_active(self.ctx.current_user, tech_id, not active)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("tech.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()
