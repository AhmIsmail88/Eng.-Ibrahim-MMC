"""Failure reports screen: register, triage, convert to work order (SPEC 8)."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...application.context import AppContext
from ...application.services.asset_service import AssetService
from ...application.services.failure_service import FailureService
from ...application.services.work_order_service import WorkOrderService
from ..widgets.attachments_panel import AttachmentsPanel
from ..widgets.tables import polish_table, sortable
from .base import BasePage, make_card, make_title, vbox


class NewFailureDialog(QDialog):
    def __init__(self, ctx: AppContext, assets: AssetService,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setModal(True)
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        self.asset = QComboBox()
        for row in assets.list():
            self.asset.addItem(f"{row.code} — {row.name(ctx.localizer.is_rtl)}", row.id)
        self.symptom = QPlainTextEdit()
        self.symptom.setFixedHeight(80)
        self.observed = QDateEdit(QDate.currentDate())
        self.observed.setCalendarPopup(True)
        self.priority = QComboBox()
        for value in ("Critical", "High", "Medium", "Low"):
            self.priority.addItem(ctx.tr(f"value.criticality.{value}"), value)
        self.priority.setCurrentIndex(2)
        self.lbl_asset = QLabel(ctx.tr("failures.asset"))
        self.lbl_symptom = QLabel(ctx.tr("failures.form.symptom"))
        self.lbl_observed = QLabel(ctx.tr("failures.form.observed"))
        self.lbl_priority = QLabel(ctx.tr("failures.priority"))
        for label, widget in ((self.lbl_asset, self.asset), (self.lbl_symptom, self.symptom),
                              (self.lbl_observed, self.observed),
                              (self.lbl_priority, self.priority)):
            form.addRow(label, widget)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        self.setWindowTitle(ctx.tr("failures.form.title"))

    def payload(self) -> dict:
        return dict(asset_id=self.asset.currentData(),
                    symptom=self.symptom.toPlainText(),
                    observed_at=self.observed.date().toString("yyyy-MM-dd"),
                    priority=self.priority.currentData())


class FailuresPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.failures = FailureService(ctx.db)
        self.orders = WorkOrderService(ctx.db)
        self.assets = AssetService(ctx.db)
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
        self.status = QComboBox()
        self.status.currentIndexChanged.connect(lambda _i: self.refresh())
        self.btn_new = QPushButton()
        self.btn_new.setObjectName("primary")
        self.btn_new.clicked.connect(self._new)
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        bar.addWidget(self.search)
        bar.addWidget(self.status)
        bar.addStretch(1)
        bar.addWidget(self.btn_new)
        bar.addWidget(self.btn_refresh)
        lay.addLayout(bar)

        card = make_card()
        card_lay = QVBoxLayout(card)
        self.table = QTableWidget(0, 5)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        polish_table(self.table, lambda: self.ctx.tr("common.no_data"))
        sortable(self.table, self)  # header click sorts (F-14)
        self.table.itemSelectionChanged.connect(self._sync_buttons)
        self.table.currentCellChanged.connect(lambda *_a: self._sync_buttons())
        card_lay.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.btn_triage = QPushButton()
        self.btn_triage.clicked.connect(lambda: self._simple(self.failures.triage))
        self.btn_convert = QPushButton()
        self.btn_convert.clicked.connect(self._convert)
        self.btn_resolve = QPushButton()
        self.btn_resolve.clicked.connect(lambda: self._simple(self.failures.resolve))
        self.btn_cancel = QPushButton()
        self.btn_cancel.clicked.connect(self._cancel)
        for btn in (self.btn_triage, self.btn_convert, self.btn_resolve, self.btn_cancel):
            actions.addWidget(btn)
        actions.addStretch(1)
        card_lay.addLayout(actions)
        lay.addWidget(card, 1)
        # Photos of the fault or a supplier's report stay with the report itself (F-13).
        attach_card = make_card()
        attach_lay = QVBoxLayout(attach_card)
        self.attach_title = QLabel()
        self.attach_title.setObjectName("sectionTitle")
        self.attach_panel = AttachmentsPanel(self.ctx, "failure")
        self.attach_panel.setMinimumHeight(170)
        attach_lay.addWidget(self.attach_title)
        attach_lay.addWidget(self.attach_panel)
        lay.addWidget(attach_card)

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("failures.title"))
        self.attach_title.setText(tr("failures.attachments"))
        self.attach_panel.retranslate()
        self.search.setPlaceholderText(tr("assets.search_hint"))
        self.btn_new.setText(tr("failures.new"))
        self.btn_refresh.setText(tr("common.refresh"))
        self.btn_triage.setText(tr("failures.triage"))
        self.btn_convert.setText(tr("failures.convert"))
        self.btn_resolve.setText(tr("failures.resolve"))
        self.btn_cancel.setText(tr("failures.cancel"))
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "failures.number", "failures.asset", "failures.symptom", "failures.priority",
            "failures.status")])
        current = self.status.currentData()
        self.status.blockSignals(True)
        self.status.clear()
        self.status.addItem(tr("assets.all"), None)
        for value in ("New", "Investigating", "Converted", "Resolved", "Cancelled"):
            self.status.addItem(tr(f"value.failure.{value}"), value)
        index = self.status.findData(current)
        self.status.setCurrentIndex(max(0, index))
        self.status.blockSignals(False)
        self.refresh()

    # ---------------- data ----------------
    def refresh(self) -> None:
        self._rows = self.failures.list(status=self.status.currentData(),
                                        query=self.search.text())
        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            cells = (row.number, row.asset_code, row.symptom,
                     self.ctx.tr(f"value.criticality.{row.priority}"),
                     self.ctx.tr(f"value.failure.{row.status}"))
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.id)
                self.table.setItem(i, col, item)
        if self._rows and self.table.currentRow() < 0:
            self.table.setCurrentCell(0, 0)
        self._sync_buttons()

    def _selected(self):
        row = self.table.currentRow()
        if row < 0 and self._rows:
            row = 0
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _sync_buttons(self) -> None:
        row = self._selected()
        if hasattr(self, "attach_panel"):
            self.attach_panel.set_owner(row.id if row else None)
        editable = self.ctx.can_edit
        self.btn_triage.setEnabled(editable and row is not None and row.status == "New")
        self.btn_convert.setEnabled(editable and row is not None
                                    and row.status in ("New", "Investigating"))
        self.btn_resolve.setEnabled(editable and row is not None
                                    and row.status in ("New", "Investigating"))
        self.btn_cancel.setEnabled(editable and row is not None
                                   and row.status in ("New", "Investigating"))

    # ---------------- commands ----------------
    def _new(self) -> None:
        if not self.ctx.can_edit:
            QMessageBox.warning(self, self.ctx.tr("failures.new"),
                                self.ctx.tr("err.permission_denied"))
            return
        if not self.assets.list():
            QMessageBox.information(self, self.ctx.tr("failures.new"),
                                    self.ctx.tr("assets.empty_hint"))
            return
        dialog = NewFailureDialog(self.ctx, self.assets, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.failures.create(self.ctx.current_user, **dialog.payload())
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("failures.new"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()

    def _convert(self) -> None:
        row = self._selected()
        if row is None:
            return
        result = self.orders.create_from_failure(self.ctx.current_user, row.id)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("failures.convert"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        detail = self.orders.detail(result.value)
        QMessageBox.information(self, self.ctx.tr("failures.convert"),
                                detail.number if detail else "")
        self.refresh()

    def _cancel(self) -> None:
        row = self._selected()
        if row is None:
            return
        reason, ok = QInputDialog.getMultiLineText(
            self, self.ctx.tr("failures.cancel"), self.ctx.tr("wo.reason"))
        if not ok or not reason.strip():
            return
        self._simple(lambda actor, fid: self.failures.cancel(actor, fid, reason))

    def _simple(self, command) -> None:
        row = self._selected()
        if row is None:
            return
        result = command(self.ctx.current_user, row.id)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("failures.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()
