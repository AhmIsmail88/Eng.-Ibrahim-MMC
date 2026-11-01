"""Suppliers (P1): roster used by receipts and external expenses."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
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


class NewSupplierDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setModal(True)
        self.setMinimumWidth(440)
        form = QFormLayout(self)
        self.code, self.name, self.contact = QLineEdit(), QLineEdit(), QLineEdit()
        for label, widget in ((ctx.tr("sup.code"), self.code), (ctx.tr("sup.name"), self.name),
                              (ctx.tr("sup.contact"), self.contact)):
            form.addRow(QLabel(label), widget)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        self.setWindowTitle(ctx.tr("sup.new"))

    def payload(self) -> dict:
        return dict(code=self.code.text(), name=self.name.text(),
                    contact_info=self.contact.text().strip() or None)


class SuppliersPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = MasterDataService(ctx.db)
        self._rows: list = []
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
        self.table = QTableWidget(0, 4)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        card_lay.addWidget(self.table)
        lay.addWidget(card, 1)
        self.retranslate()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("sup.title"))
        self.btn_new.setText(tr("sup.new"))
        self.btn_toggle.setText(tr("tech.toggle"))
        self.btn_refresh.setText(tr("common.refresh"))
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "sup.code", "sup.name", "sup.contact", "users.status")])
        self.refresh()

    def refresh(self) -> None:
        self._rows = self.service.supplier_rows()
        self.table.setRowCount(len(self._rows))
        for i, (sid, code, name, contact, active) in enumerate(self._rows):
            cells = (code, name, contact,
                     self.ctx.tr("users.active" if active else "users.inactive"))
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, sid)
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
        dialog = NewSupplierDialog(self.ctx, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.service.create_supplier(self.ctx.current_user, **dialog.payload())
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("sup.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()

    def _toggle(self) -> None:
        row = self._selected()
        if row is None:
            return
        sid, _code, _name, _contact, active = row
        result = self.service.set_supplier_active(self.ctx.current_user, sid, not active)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("sup.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()
