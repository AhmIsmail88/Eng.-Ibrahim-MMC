"""Purchase requests screen (P1): draft → approved → received into stock."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...application.context import AppContext
from ...application.services.inventory_service import InventoryService
from ...application.services.master_data_service import MasterDataService
from ...application.services.purchase_service import PurchaseService
from ..widgets.tables import polish_table
from .base import BasePage, make_card, make_title, vbox


class NewRequestDialog(QDialog):
    def __init__(self, ctx: AppContext, suppliers, parts, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setModal(True)
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        self.supplier = QComboBox()
        self.supplier.addItem("—", None)
        for supplier in suppliers:
            self.supplier.addItem(supplier.name_ar, supplier.id)
        self.part = QComboBox()
        for part in parts:
            self.part.addItem(f"{part.code} — {part.name(ctx.localizer.is_rtl)}", part.id)
        self.qty = QLineEdit("1")
        self.cost = QDoubleSpinBox()
        self.cost.setMaximum(1_000_000)
        self.cost.setDecimals(2)
        self.notes = QLineEdit()
        for label, widget in ((ctx.tr("sup.title"), self.supplier),
                              (ctx.tr("parts.code"), self.part),
                              (ctx.tr("parts.quantity"), self.qty),
                              (ctx.tr("parts.unit_cost"), self.cost),
                              (ctx.tr("wo.expense.notes"), self.notes)):
            form.addRow(QLabel(label), widget)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        self.setWindowTitle(ctx.tr("pr.new"))

    def payload(self) -> dict:
        return dict(supplier_id=self.supplier.currentData(),
                    lines=[(self.part.currentData(), self.qty.text(),
                            int(round(self.cost.value() * 100)))],
                    notes=self.notes.text().strip() or None)


class PurchasesPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = PurchaseService(ctx.db)
        self.masters = MasterDataService(ctx.db)
        self.inventory = InventoryService(ctx.db)
        self._rows: list = []
        lay = vbox(self)
        self.title = make_title()
        lay.addWidget(self.title)
        card = make_card()
        card_lay = QVBoxLayout(card)
        bar = QHBoxLayout()
        self.btn_new = QPushButton()
        self.btn_new.setObjectName("primary")
        self.btn_new.clicked.connect(self._new)
        self.btn_approve = QPushButton()
        self.btn_approve.clicked.connect(lambda: self._act("approve"))
        self.btn_receive = QPushButton()
        self.btn_receive.clicked.connect(lambda: self._act("receive"))
        self.btn_cancel = QPushButton()
        self.btn_cancel.clicked.connect(lambda: self._act("cancel"))
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        bar.addStretch(1)
        for btn in (self.btn_new, self.btn_approve, self.btn_receive, self.btn_cancel,
                    self.btn_refresh):
            bar.addWidget(btn)
        card_lay.addLayout(bar)
        self.table = QTableWidget(0, 5)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        polish_table(self.table, lambda: self.ctx.tr("common.no_data"))
        card_lay.addWidget(self.table)
        lay.addWidget(card, 1)
        self.retranslate()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("pr.title"))
        self.btn_new.setText(tr("pr.new"))
        self.btn_approve.setText(tr("pr.approve"))
        self.btn_receive.setText(tr("pr.receive"))
        self.btn_cancel.setText(tr("failures.cancel"))
        self.btn_refresh.setText(tr("common.refresh"))
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "rep.col.number", "sup.title", "users.status", "pr.total", "pr.lines")])
        self.refresh()

    def refresh(self) -> None:
        self._rows = self.service.list()
        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            cells = (row.number, row.supplier, self.ctx.tr(f"pr.status.{row.status}"),
                     f"{row.total_minor / 100:,.2f}", str(row.lines))
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.id)
                self.table.setItem(i, col, item)
        if self._rows and self.table.currentRow() < 0:
            self.table.setCurrentCell(0, 0)
        for btn in (self.btn_approve, self.btn_receive, self.btn_cancel):
            btn.setEnabled(self.ctx.can_edit)

    def _selected(self):
        row = self.table.currentRow()
        if row < 0 and self._rows:
            row = 0
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _new(self) -> None:
        if not self.ctx.can_edit:
            return
        parts = self.inventory.list_parts()
        if not parts:
            QMessageBox.information(self, self.ctx.tr("pr.new"),
                                    self.ctx.tr("parts.empty"))
            return
        dialog = NewRequestDialog(self.ctx, self.masters.suppliers(), parts, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.service.create(self.ctx.current_user, **dialog.payload())
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("pr.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()

    def _act(self, action: str) -> None:
        row = self._selected()
        if row is None or not self.ctx.can_edit:
            return
        if action == "approve":
            result = self.service.approve(self.ctx.current_user, row.id)
        elif action == "receive":
            result = self.service.receive(self.ctx.current_user, row.id)
        else:
            from PySide6.QtWidgets import QInputDialog
            reason, ok = QInputDialog.getMultiLineText(
                self, self.ctx.tr("failures.cancel"), self.ctx.tr("wo.reason"))
            if not ok or not reason.strip():
                return
            result = self.service.cancel(self.ctx.current_user, row.id, reason)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("pr.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()
