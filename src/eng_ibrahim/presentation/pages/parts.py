"""Spare parts screen: catalog, receipt, issue, returns, adjustments (SPEC 12)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
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
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...application.context import AppContext
from ...application.services.inventory_service import InventoryService
from ...application.services.master_data_service import MasterDataService
from ...application.services.work_order_service import WorkOrderService
from ...domain.policies import wo_state_machine as sm
from ..widgets.import_flow import run_import
from ..widgets.tables import polish_table
from .base import BasePage, make_card, make_title, select_row, vbox


class NewPartDialog(QDialog):
    def __init__(self, ctx: AppContext, units, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setModal(True)
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        self.code, self.name_ar = QLineEdit(), QLineEdit()
        self.unit = QComboBox()
        for unit in units:
            self.unit.addItem(f"{unit.code} — {unit.name_ar}", unit.id)
        self.precision = QSpinBox()
        self.precision.setRange(0, 6)
        self.reorder = QLineEdit()
        self.min_stock = QLineEdit()
        labels = [QLabel(ctx.tr("parts.code")), QLabel(ctx.tr("parts.name")),
                  QLabel(ctx.tr("parts.unit")), QLabel(ctx.tr("parts.precision")),
                  QLabel(ctx.tr("parts.reorder")), QLabel(ctx.tr("parts.min_stock"))]
        for label, widget in zip(labels, (self.code, self.name_ar, self.unit,
                                          self.precision, self.reorder, self.min_stock),
                                 strict=False):
            form.addRow(label, widget)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        self.setWindowTitle(ctx.tr("parts.new"))

    def payload(self) -> dict:
        return dict(part_code=self.code.text(), name_ar=self.name_ar.text(),
                    unit_code=self.unit.currentData(), precision=self.precision.value(),
                    reorder_point=self.reorder.text().strip() or None,
                    min_stock=self.min_stock.text().strip() or None)


class ReceiveDialog(QDialog):
    def __init__(self, ctx: AppContext, suppliers, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setModal(True)
        form = QFormLayout(self)
        self.qty = QLineEdit("1")
        self.cost = QDoubleSpinBox()
        self.cost.setMaximum(1_000_000_000)
        self.cost.setDecimals(2)
        self.supplier = QComboBox()
        self.supplier.addItem("—", None)
        for s in suppliers:
            self.supplier.addItem(s.name_ar, s.id)
        self.purchase_ref = QLineEdit()
        self.lbl_qty = QLabel(ctx.tr("parts.quantity"))
        self.lbl_cost = QLabel(ctx.tr("parts.unit_cost"))
        self.lbl_sup = QLabel(ctx.tr("parts.supplier"))
        self.lbl_po = QLabel(ctx.tr("parts.purchase_ref"))
        for label, widget in ((self.lbl_qty, self.qty), (self.lbl_cost, self.cost),
                              (self.lbl_sup, self.supplier),
                              (self.lbl_po, self.purchase_ref)):
            form.addRow(label, widget)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        self.setWindowTitle(ctx.tr("parts.receive"))

    def payload(self) -> dict:
        return dict(quantity=self.qty.text(),
                    unit_cost_minor=int(round(self.cost.value() * 100)),
                    supplier_id=self.supplier.currentData(),
                    purchase_ref=self.purchase_ref.text().strip() or None)


class IssueDialog(QDialog):
    def __init__(self, ctx: AppContext, orders: WorkOrderService, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setModal(True)
        form = QFormLayout(self)
        self.qty = QLineEdit("1")
        self.wo = QComboBox()
        for row in orders.list():
            if row.status in (sm.OPEN, sm.ASSIGNED, sm.IN_PROGRESS, sm.ON_HOLD):
                self.wo.addItem(f"{row.number} — {row.asset_code}", row.id)
        self.lbl_qty = QLabel(ctx.tr("parts.quantity"))
        self.lbl_wo = QLabel(ctx.tr("parts.work_order"))
        form.addRow(self.lbl_qty, self.qty)
        form.addRow(self.lbl_wo, self.wo)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        self.setWindowTitle(ctx.tr("parts.issue"))

    def payload(self) -> dict:
        return dict(wo_id=self.wo.currentData(), quantity=self.qty.text())


class PartsPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.inventory = InventoryService(ctx.db)
        self.masters = MasterDataService(ctx.db)
        self.orders = WorkOrderService(ctx.db)
        self._rows: list = []
        self._build()
        self.retranslate()

    def _build(self) -> None:
        lay = vbox(self)
        self.title = make_title()
        lay.addWidget(self.title)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self.refresh())
        self.low_only = QCheckBox()
        self.low_only.stateChanged.connect(lambda _s: self.refresh())
        self.btn_new = QPushButton()
        self.btn_new.setObjectName("primary")
        self.btn_new.clicked.connect(self._new_part)
        self.btn_receive = QPushButton()
        self.btn_receive.clicked.connect(self._receive)
        self.btn_issue = QPushButton()
        self.btn_issue.clicked.connect(self._issue)
        self.btn_adjust = QPushButton()
        self.btn_adjust.clicked.connect(self._adjust)
        self.btn_count = QPushButton()
        self.btn_count.clicked.connect(self._stock_count)
        self.btn_import = QPushButton()
        self.btn_import.clicked.connect(self._import)
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        bar.addWidget(self.search)
        bar.addWidget(self.low_only)
        bar.addStretch(1)
        for btn in (self.btn_new, self.btn_receive, self.btn_issue, self.btn_adjust,
                    self.btn_count, self.btn_import, self.btn_refresh):
            bar.addWidget(btn)
        lay.addLayout(bar)

        split = QSplitter(Qt.Orientation.Vertical)
        table_card = make_card()
        table_lay = QVBoxLayout(table_card)
        self.table = QTableWidget(0, 7)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        polish_table(self.table, lambda: self.ctx.tr("common.no_data"))
        table_lay.addWidget(self.table)
        split.addWidget(table_card)

        history_card = make_card()
        history_lay = QVBoxLayout(history_card)
        self.moves = QTableWidget(0, 5)
        self.moves.verticalHeader().setVisible(False)
        self.moves.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        polish_table(self.moves, lambda: self.ctx.tr("common.no_data"))
        history_lay.addWidget(self.moves)
        split.addWidget(history_card)
        split.setSizes([420, 240])
        lay.addWidget(split, 1)

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("parts.title"))
        self.search.setPlaceholderText(tr("assets.search_hint"))
        self.low_only.setText(tr("parts.low_only"))
        self.btn_new.setText(tr("parts.new"))
        self.btn_receive.setText(tr("parts.receive"))
        self.btn_issue.setText(tr("parts.issue"))
        self.btn_adjust.setText(tr("parts.adjust"))
        self.btn_count.setText(tr("parts.count"))
        self.btn_import.setText(tr("parts.import"))
        self.btn_import.setToolTip(tr("parts.import_hint"))
        self.btn_refresh.setText(tr("common.refresh"))
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "parts.code", "parts.name", "parts.on_hand", "parts.reserved",
            "parts.available", "parts.avg_cost", "parts.unit")])
        self.moves.setHorizontalHeaderLabels([tr(k) for k in (
            "parts.movement", "parts.date", "parts.type", "parts.quantity", "parts.value")])
        self.refresh()

    def _unit_label(self, code: str) -> str:
        unit = self._units.get(code)
        if unit is None:
            return code
        return (unit.name_ar if self.ctx.localizer.is_rtl else unit.name_en) or code

    def refresh(self) -> None:
        self._units = {u.code: u for u in self.masters.units()}
        self._rows = self.inventory.list_parts(query=self.search.text(),
                                               low_only=self.low_only.isChecked())
        self.table.setRowCount(len(self._rows))
        for i, part in enumerate(self._rows):
            cells = (part.code, part.name(self.ctx.localizer.is_rtl), part.on_hand,
                     part.reserved, part.available,
                     f"{part.average_cost_minor / 100:,.2f} {part.currency}",
                     self._unit_label(part.unit_code))
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, part.id)
                if part.is_low and col == 4:
                    item.setText(f"⚠ {text}")
                self.table.setItem(i, col, item)
        if self._rows and self.table.currentRow() < 0:
            self.table.setCurrentCell(0, 0)
        self._reload_moves()

    def _selected(self):
        row = self.table.currentRow()
        if row < 0 and self._rows:
            row = 0
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _reload_moves(self) -> None:
        part = self._selected()
        moves = self.inventory.movements(part_id=part.id if part else None, limit=50)
        self.moves.setRowCount(len(moves))
        for i, move in enumerate(moves):
            self.moves.setItem(i, 0, QTableWidgetItem(move.number))
            self.moves.setItem(i, 1, QTableWidgetItem(move.posted_at[:16].replace("T", " ")))
            self.moves.setItem(i, 2, QTableWidgetItem(self.ctx.tr(f"parts.type.{move.type}")))
            self.moves.setItem(i, 3, QTableWidgetItem(
                f"{move.quantity} {self._unit_label(part.unit_code) if part else ''}"))
            self.moves.setItem(i, 4, QTableWidgetItem(
                f"{move.total_minor / 100:,.2f} {move.currency}"))

    def select_record(self, part_id: str) -> bool:
        self.search.clear()
        self.low_only.setChecked(False)
        self.refresh()
        if not select_row(self.table, self._rows, part_id):
            return False
        self._reload_moves()
        return True

    def apply_filter(self, name: str | None) -> None:
        self.search.clear()
        self.low_only.setChecked(name == "low")

    # ---------------- commands ----------------
    def _import(self) -> None:
        if run_import(self, self.ctx, "parts", self.ctx.tr("parts.import")):
            self.refresh()

    def _new_part(self) -> None:
        if not self.ctx.can_edit:
            return
        dialog = NewPartDialog(self.ctx, self.masters.units(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.inventory.create_part(self.ctx.current_user, **dialog.payload())
        self._after(result)

    def _receive(self) -> None:
        part = self._selected()
        if part is None or not self.ctx.can_edit:
            return
        dialog = ReceiveDialog(self.ctx, self.masters.suppliers(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        result = self.inventory.receive(self.ctx.current_user, part.id, **payload)
        self._after(result)

    def _issue(self) -> None:
        part = self._selected()
        if part is None or not self.ctx.can_edit:
            return
        dialog = IssueDialog(self.ctx, self.orders, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        if not payload["wo_id"]:
            return
        result = self.inventory.issue_to_wo(self.ctx.current_user, part.id, **payload)
        self._after(result)

    def _adjust(self) -> None:
        part = self._selected()
        if part is None or not self.ctx.can_edit:
            return
        from PySide6.QtWidgets import QInputDialog
        qty, ok = QInputDialog.getText(self, self.ctx.tr("parts.adjust"),
                                       self.ctx.tr("parts.quantity"))
        if not ok or not qty.strip():
            return
        reason, ok = QInputDialog.getText(self, self.ctx.tr("parts.adjust"),
                                          self.ctx.tr("wo.reason"))
        if not ok or not reason.strip():
            return
        result = self.inventory.adjust(self.ctx.current_user, part.id, qty, reason)
        self._after(result)

    def _stock_count(self) -> None:
        if not self.ctx.can_edit or not self._rows:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.ctx.tr("parts.count"))
        dialog.setMinimumSize(560, 420)
        lay = QVBoxLayout(dialog)
        hint = QLabel(self.ctx.tr("parts.count_hint"))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        table = QTableWidget(len(self._rows), 3)
        table.setHorizontalHeaderLabels([
            self.ctx.tr("parts.code"), self.ctx.tr("parts.on_hand"),
            self.ctx.tr("parts.counted")])
        table.verticalHeader().setVisible(False)
        polish_table(table, lambda: self.ctx.tr("common.no_data"))
        for row, part in enumerate(self._rows):
            code = QTableWidgetItem(part.code)
            code.setFlags(code.flags() & ~Qt.ItemFlag.ItemIsEditable)
            system = QTableWidgetItem(part.on_hand)
            system.setFlags(system.flags() & ~Qt.ItemFlag.ItemIsEditable)
            counted = QTableWidgetItem(part.on_hand)
            table.setItem(row, 0, code)
            table.setItem(row, 1, system)
            table.setItem(row, 2, counted)
        lay.addWidget(table)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                               | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(dialog.accept)
        box.rejected.connect(dialog.reject)
        lay.addWidget(box)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        applied = 0
        for row, part in enumerate(self._rows):
            value = table.item(row, 2).text().strip()
            if not value or value == part.on_hand:
                continue
            try:
                delta = float(value) - float(part.on_hand)
            except ValueError:
                continue
            if abs(delta) < 1e-9:
                continue
            result = self.inventory.adjust(self.ctx.current_user, part.id, str(delta),
                                           self.ctx.tr("parts.count_reason"))
            if result.ok:
                applied += 1
        self.refresh()
        QMessageBox.information(self, self.ctx.tr("parts.count"),
                                self.ctx.tr("parts.count_done", count=applied))

    def _after(self, result) -> None:
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("parts.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()
