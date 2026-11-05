"""Purchase requests screen (P1): draft → approved → received into stock."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

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
from ...application.services.inventory_service import InventoryService
from ...application.services.master_data_service import MasterDataService
from ...application.services.purchase_service import PurchaseService
from ..widgets.tables import polish_table, sortable
from .base import BasePage, make_card, make_title, vbox


class NewRequestDialog(QDialog):
    """Supplier + a grid of lines (part, quantity, unit cost) with a running total (F-06)."""

    def __init__(self, ctx: AppContext, suppliers, parts, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._parts = parts
        self.setModal(True)
        self.setMinimumSize(720, 460)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.supplier = QComboBox()
        self.supplier.addItem("—", None)
        for supplier in suppliers:
            self.supplier.addItem(supplier.name_ar, supplier.id)
        self.notes = QLineEdit()
        form.addRow(QLabel(ctx.tr("sup.title")), self.supplier)
        form.addRow(QLabel(ctx.tr("wo.expense.notes")), self.notes)
        lay.addLayout(form)
        self.lines = QTableWidget(0, 4)
        self.lines.setHorizontalHeaderLabels([ctx.tr("parts.code"), ctx.tr("parts.quantity"),
                                              ctx.tr("parts.unit_cost"), ctx.tr("pr.line_total")])
        self.lines.verticalHeader().setVisible(False)
        self.lines.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self.lines.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.lines, 1)
        bar = QHBoxLayout()
        self.btn_add = QPushButton(ctx.tr("pr.add_line"))
        self.btn_add.clicked.connect(lambda: self.add_line())
        self.btn_remove = QPushButton(ctx.tr("pr.remove_line"))
        self.btn_remove.clicked.connect(self.remove_line)
        self.total = QLabel()
        self.total.setObjectName("sectionTitle")
        bar.addWidget(self.btn_add)
        bar.addWidget(self.btn_remove)
        bar.addStretch(1)
        bar.addWidget(self.total)
        lay.addLayout(bar)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        lay.addWidget(self.buttons)
        self.setWindowTitle(ctx.tr("pr.new"))
        self.add_line()

    def add_line(self, part_id: str | None = None, qty: str = "1", cost_minor: int = 0) -> None:
        row = self.lines.rowCount()
        self.lines.insertRow(row)
        part = QComboBox()
        for p in self._parts:
            part.addItem(f"{p.code} — {p.name(self.ctx.localizer.is_rtl)}", p.id)
        if part_id:
            part.setCurrentIndex(max(0, part.findData(part_id)))
        quantity = QLineEdit(qty)
        cost = QDoubleSpinBox()
        cost.setMaximum(10_000_000)
        cost.setDecimals(2)
        cost.setValue(cost_minor / 100)
        quantity.textChanged.connect(lambda _t: self._update_total())
        cost.valueChanged.connect(lambda _v: self._update_total())
        self.lines.setCellWidget(row, 0, part)
        self.lines.setCellWidget(row, 1, quantity)
        self.lines.setCellWidget(row, 2, cost)
        self.lines.setItem(row, 3, QTableWidgetItem("0.00"))
        self._update_total()

    def remove_line(self) -> None:
        row = self.lines.currentRow()
        if self.lines.rowCount() > 1 and row >= 0:
            self.lines.removeRow(row)
            self._update_total()

    def load(self, detail) -> None:
        """Edit a draft: its supplier, notes and lines."""
        self.setWindowTitle(self.ctx.tr("pr.edit") + f" — {detail.number}")
        self.supplier.setCurrentIndex(max(0, self.supplier.findData(detail.supplier_id)))
        self.notes.setText(detail.notes or "")
        self.lines.setRowCount(0)
        for part_id, qty, cost_minor in detail.lines:
            self.add_line(part_id, qty, cost_minor)

    def _update_total(self) -> None:
        total = Decimal(0)
        for row in range(self.lines.rowCount()):
            try:
                qty = Decimal(self.lines.cellWidget(row, 1).text().strip() or "0")
            except InvalidOperation:
                qty = Decimal(0)
            line = qty * Decimal(str(self.lines.cellWidget(row, 2).value()))
            total += line
            item = self.lines.item(row, 3)
            if item is not None:
                item.setText(f"{line:,.2f}")
        currency = self.ctx.settings.get("currency_code", "EGP")
        self.total.setText(self.ctx.tr("pr.total_amount", total=f"{total:,.2f}", currency=currency))

    def payload(self) -> dict:
        lines = [(self.lines.cellWidget(r, 0).currentData(),
                  self.lines.cellWidget(r, 1).text().strip(),
                  int(round(self.lines.cellWidget(r, 2).value() * 100)))
                 for r in range(self.lines.rowCount())]
        return dict(supplier_id=self.supplier.currentData(), lines=lines,
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
        self.btn_edit = QPushButton()
        self.btn_edit.clicked.connect(self._edit)
        self.btn_approve = QPushButton()
        self.btn_approve.clicked.connect(lambda: self._act("approve"))
        self.btn_receive = QPushButton()
        self.btn_receive.clicked.connect(lambda: self._act("receive"))
        self.btn_cancel = QPushButton()
        self.btn_cancel.clicked.connect(lambda: self._act("cancel"))
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        bar.addStretch(1)
        for btn in (self.btn_new, self.btn_edit, self.btn_approve, self.btn_receive,
                    self.btn_cancel, self.btn_refresh):
            bar.addWidget(btn)
        card_lay.addLayout(bar)
        self.table = QTableWidget(0, 5)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        polish_table(self.table, lambda: self.ctx.tr("common.no_data"))
        sortable(self.table, self)  # header click sorts (F-14)
        card_lay.addWidget(self.table)
        lay.addWidget(card, 1)
        self.retranslate()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("pr.title"))
        self.btn_new.setText(tr("pr.new"))
        self.btn_approve.setText(tr("pr.approve"))
        self.btn_edit.setText(tr("pr.edit"))
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
        for btn in (self.btn_edit, self.btn_approve, self.btn_receive, self.btn_cancel):
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
        while dialog.exec() == QDialog.DialogCode.Accepted:
            result = self.service.create(self.ctx.current_user, **dialog.payload())
            if result.ok:
                self.refresh()
                return
            QMessageBox.warning(self, self.ctx.tr("pr.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))

    def _edit(self) -> None:
        row = self._selected()
        if row is None or not self.ctx.can_edit:
            return
        detail = self.service.detail(row.id)
        if detail is None or detail.status != "Draft":
            QMessageBox.information(self, self.ctx.tr("pr.edit"),
                                    self.ctx.tr("err.pr_status_invalid"))
            return
        dialog = NewRequestDialog(self.ctx, self.masters.suppliers(),
                                  self.inventory.list_parts(), self)
        dialog.load(detail)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            result = self.service.update(self.ctx.current_user, row.id, **dialog.payload())
            if result.ok:
                self.refresh()
                return
            QMessageBox.warning(self, self.ctx.tr("pr.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))

    def _choose_warehouse(self) -> str | None | bool:
        """None = the default warehouse (only one exists); False = the user cancelled."""
        warehouses = InventoryService(self.ctx.db).warehouses()
        if len(warehouses) <= 1:
            return None
        from PySide6.QtWidgets import QInputDialog
        labels = [f"{code} — {name}" for _id, code, name in warehouses]
        last = self.ctx.prefs.get("parts_warehouse")
        current = next((i for i, w in enumerate(warehouses) if w[0] == last), 0)
        choice, ok = QInputDialog.getItem(self, self.ctx.tr("pr.receive"),
                                          self.ctx.tr("parts.warehouse"), labels, current, False)
        if not ok:
            return False
        return warehouses[labels.index(choice)][0]

    def _act(self, action: str) -> None:
        row = self._selected()
        if row is None or not self.ctx.can_edit:
            return
        if action == "approve":
            result = self.service.approve(self.ctx.current_user, row.id)
        elif action == "receive":
            warehouse_id = self._choose_warehouse()
            if warehouse_id is False:
                return
            result = self.service.receive(self.ctx.current_user, row.id,
                                          warehouse_id=warehouse_id)
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
