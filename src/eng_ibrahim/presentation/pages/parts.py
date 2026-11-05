"""Spare parts screen: catalog, receipt, issue, returns, adjustments (SPEC 12)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
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
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...application.context import AppContext
from ...application.services.inventory_service import InventoryService
from ...application.services.master_data_service import MasterDataService
from ...application.services.work_order_service import WorkOrderService
from ...domain.policies import wo_state_machine as sm
from ..widgets.import_flow import run_import
from ..widgets.tables import polish_table, sortable
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


class _MoveDialog(QDialog):
    """Quantity + reason form shared by return, transfer and scrap."""

    def __init__(self, ctx: AppContext, title: str, rows: list[tuple[str, QWidget]],
                 reason_required: bool, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setWindowTitle(title)
        form = QFormLayout(self)
        for label, widget in rows:
            form.addRow(QLabel(label), widget)
        self.qty = QLineEdit()
        self.qty.setPlaceholderText("0")
        self.reason = QLineEdit()
        form.addRow(QLabel(ctx.tr("parts.quantity")), self.qty)
        form.addRow(QLabel(ctx.tr("wo.reason") + (" *" if reason_required else "")),
                    self.reason)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            ctx.tr("common.cancel"))
        form.addRow(self.buttons)

    def values(self) -> tuple[str, str]:
        return self.qty.text().strip(), self.reason.text().strip()


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
        # Every stock movement acts on the warehouse chosen here (review F-03/F-04).
        self.warehouse_label = QLabel()
        self.warehouse = QComboBox()
        self.warehouse.currentIndexChanged.connect(self._on_warehouse)
        self.btn_moves = QToolButton()
        self.btn_moves.setObjectName("menuButton")
        self.btn_moves.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.move_menu = QMenu(self.btn_moves)
        self.actions: dict[str, QAction] = {}
        for key, handler in (("parts.receive", self._receive), ("parts.issue", self._issue),
                             ("parts.return", self._return), ("parts.transfer", self._transfer),
                             ("parts.scrap", self._scrap), ("parts.adjust", self._adjust),
                             ("parts.count", self._stock_count)):
            action = self.move_menu.addAction("")
            action.triggered.connect(handler)
            self.actions[key] = action
        self.btn_moves.setMenu(self.move_menu)
        self.btn_import = QPushButton()
        self.btn_import.clicked.connect(self._import)
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        bar.addWidget(self.search)
        bar.addWidget(self.low_only)
        bar.addWidget(self.warehouse_label)
        bar.addWidget(self.warehouse)
        bar.addStretch(1)
        for btn in (self.btn_new, self.btn_moves, self.btn_import, self.btn_refresh):
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
        sortable(self.table, self)  # header click sorts (F-14)
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
        self.btn_moves.setText(tr("parts.moves") + "  ▾")
        self.warehouse_label.setText(tr("parts.warehouse"))
        for key, action in self.actions.items():
            action.setText(tr(key))
        self._reload_warehouses()
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
                                               low_only=self.low_only.isChecked(),
                                               warehouse_id=self._warehouse_id())
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
        moves = self.inventory.movements(part_id=part.id if part else None, limit=50,
                                         warehouse_id=self._warehouse_id())
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
        dialog = NewPartDialog(self.ctx, self.masters.units(active_only=True), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.inventory.create_part(self.ctx.current_user, **dialog.payload())
        self._after(result)

    # ---------------- warehouse ----------------
    def _reload_warehouses(self) -> None:
        current = self.warehouse.currentData() or self.ctx.prefs.get("parts_warehouse")
        self.warehouse.blockSignals(True)
        self.warehouse.clear()
        self.inventory.ensure_default_warehouse()
        for wh_id, code, name in self.inventory.warehouses():
            self.warehouse.addItem(f"{code} — {name}", wh_id)
        self.warehouse.setCurrentIndex(max(0, self.warehouse.findData(current)))
        self.warehouse.blockSignals(False)
        single = self.warehouse.count() <= 1
        # One warehouse: nothing to choose, keep the toolbar quiet.
        self.warehouse.setVisible(not single)
        self.warehouse_label.setVisible(not single)

    def _warehouse_id(self) -> str | None:
        return self.warehouse.currentData()

    def _on_warehouse(self, _index: int) -> None:
        self.ctx.prefs.set("parts_warehouse", self._warehouse_id())
        self.refresh()

    def _receive(self) -> None:
        part = self._selected()
        if part is None or not self.ctx.can_edit:
            return
        dialog = ReceiveDialog(self.ctx, self.masters.suppliers(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        result = self.inventory.receive(self.ctx.current_user, part.id,
                                        warehouse_id=self._warehouse_id(), **payload)
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
        result = self.inventory.issue_to_wo(self.ctx.current_user, part.id,
                                            warehouse_id=self._warehouse_id(), **payload)
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
        result = self.inventory.adjust(self.ctx.current_user, part.id, qty, reason,
                                       warehouse_id=self._warehouse_id())
        self._after(result)

    def _return(self) -> None:
        part = self._selected()
        if part is None or not self.ctx.can_edit:
            return
        issues = self.inventory.returnable_issues(part.id, self._warehouse_id())
        if not issues:
            QMessageBox.information(self, self.ctx.tr("parts.return"),
                                    self.ctx.tr("parts.return_none"))
            return
        source = QComboBox()
        for issue in issues:
            source.addItem(self.ctx.tr("parts.return_item", wo=issue.wo_number,
                                       move=issue.movement_no, left=issue.remaining),
                           issue.movement_id)
        dialog = _MoveDialog(self.ctx, self.ctx.tr("parts.return"),
                             [(self.ctx.tr("parts.return_from"), source)], False, self)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            qty, reason = dialog.values()
            result = self.inventory.return_from_wo(self.ctx.current_user,
                                                   source.currentData(), qty, reason or None)
            if result.ok:
                self.refresh()
                return
            self._warn(result.error_code)

    def _transfer(self) -> None:
        part = self._selected()
        if part is None or not self.ctx.can_edit:
            return
        targets = [w for w in self.inventory.warehouses() if w[0] != self._warehouse_id()]
        if not targets:
            QMessageBox.information(self, self.ctx.tr("parts.transfer"),
                                    self.ctx.tr("parts.transfer_needs_two"))
            return
        target = QComboBox()
        for wh_id, code, name in targets:
            target.addItem(f"{code} — {name}", wh_id)
        dialog = _MoveDialog(self.ctx, self.ctx.tr("parts.transfer"),
                             [(self.ctx.tr("parts.transfer_to"), target)], False, self)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            qty, reason = dialog.values()
            result = self.inventory.transfer(self.ctx.current_user, part.id,
                                             self._warehouse_id(), target.currentData(), qty,
                                             reason or None)
            if result.ok:
                self.refresh()
                return
            self._warn(result.error_code)

    def _scrap(self) -> None:
        part = self._selected()
        if part is None or not self.ctx.can_edit:
            return
        dialog = _MoveDialog(self.ctx, self.ctx.tr("parts.scrap"), [], True, self)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            qty, reason = dialog.values()
            result = self.inventory.scrap(self.ctx.current_user, part.id, qty, reason,
                                          warehouse_id=self._warehouse_id())
            if result.ok:
                self.refresh()
                return
            self._warn(result.error_code)

    def _warn(self, code: str | None) -> None:
        QMessageBox.warning(self, self.ctx.tr("parts.title"), self.ctx.tr(code or "err.invalid"))

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
                delta = Decimal(value) - Decimal(part.on_hand)
            except InvalidOperation:
                continue
            if delta == 0:
                continue
            result = self.inventory.adjust(self.ctx.current_user, part.id, str(delta),
                                           self.ctx.tr("parts.count_reason"),
                                           warehouse_id=self._warehouse_id())
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
