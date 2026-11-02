"""Preventive maintenance screen: plans, due state, generation, skip (SPEC 9)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
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
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...application.context import AppContext
from ...application.dto.preventive import PlanDetail
from ...application.services.asset_service import AssetService
from ...application.services.meter_service import MeterService
from ...application.services.pm_service import PMService
from ..widgets.tables import polish_table
from .base import BasePage, make_card, make_title, vbox


class NewPlanDialog(QDialog):
    def __init__(self, ctx: AppContext, assets: AssetService,
                 meters: MeterService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx, self.assets, self.meters = ctx, assets, meters
        self.setModal(True)
        self.setMinimumWidth(540)
        form = QFormLayout(self)
        self.asset = QComboBox()
        for row in assets.list():
            self.asset.addItem(f"{row.code} — {row.name(ctx.localizer.is_rtl)}", row.id)
        self.asset.currentIndexChanged.connect(lambda _i: self._reload_meters())
        self.title = QLineEdit()
        self.trigger = QComboBox()
        for value in ("DATE_ONLY", "METER_ONLY", "FIRST_DUE"):
            self.trigger.addItem(ctx.tr(f"pm.trigger.{value}"), value)
        self.trigger.currentIndexChanged.connect(lambda _i: self._sync_enabled())
        self.interval_value = QSpinBox()
        self.interval_value.setRange(1, 3650)
        self.interval_value.setValue(30)
        self.interval_unit = QComboBox()
        for value in ("days", "weeks", "months", "years"):
            self.interval_unit.addItem(ctx.tr(f"pm.unit.{value}"), value)
        self.meter = QComboBox()
        self.meter_interval = QLineEdit()
        self.meter_interval.setPlaceholderText("500")
        self.warning_days = QSpinBox()
        self.warning_days.setRange(0, 365)
        self.warning_days.setValue(7)
        self.tasks = QPlainTextEdit()
        self.tasks.setFixedHeight(70)
        self.lbl_asset = QLabel(ctx.tr("wo.asset"))
        self.lbl_title = QLabel(ctx.tr("pm.title_label"))
        self.lbl_trigger = QLabel(ctx.tr("pm.trigger_label"))
        self.lbl_interval = QLabel(ctx.tr("pm.interval"))
        self.lbl_meter = QLabel(ctx.tr("pm.meter"))
        self.lbl_meter_int = QLabel(ctx.tr("pm.meter_interval"))
        self.lbl_warning = QLabel(ctx.tr("pm.warning_days"))
        self.lbl_tasks = QLabel(ctx.tr("pm.tasks_hint"))
        for label, widget in (
            (self.lbl_asset, self.asset), (self.lbl_title, self.title),
            (self.lbl_trigger, self.trigger), (self.lbl_interval, self.interval_value),
            (None, self.interval_unit), (self.lbl_meter, self.meter),
            (self.lbl_meter_int, self.meter_interval), (self.lbl_warning, self.warning_days),
            (self.lbl_tasks, self.tasks)):
            if label is None:
                form.addRow("", widget)
            else:
                form.addRow(label, widget)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        self.setWindowTitle(ctx.tr("pm.new"))
        self._reload_meters()
        self._sync_enabled()

    def _reload_meters(self) -> None:
        self.meter.clear()
        asset_id = self.asset.currentData()
        if not asset_id:
            return
        self.meters.ensure_asset_meter(asset_id)
        for m in self.meters.meters(asset_id):
            self.meter.addItem(f"{m.code} ({m.unit_code})", m.id)

    def _sync_enabled(self) -> None:
        policy = self.trigger.currentData()
        needs_date = policy in ("DATE_ONLY", "FIRST_DUE")
        needs_meter = policy in ("METER_ONLY", "FIRST_DUE")
        self.interval_value.setEnabled(needs_date)
        self.interval_unit.setEnabled(needs_date)
        self.meter.setEnabled(needs_meter)
        self.meter_interval.setEnabled(needs_meter)

    def payload(self) -> dict:
        policy = self.trigger.currentData()
        needs_meter = policy in ("METER_ONLY", "FIRST_DUE")
        tasks = [(line.strip(), True) for line in self.tasks.toPlainText().splitlines()
                 if line.strip()]
        return dict(
            asset_id=self.asset.currentData(), title=self.title.text(),
            strategy="Calendar" if policy == "DATE_ONLY" else (
                "Meter" if policy == "METER_ONLY" else "Hybrid"),
            trigger_policy=policy,
            calendar_interval_value=self.interval_value.value(),
            calendar_interval_unit=self.interval_unit.currentData(),
            meter_id=self.meter.currentData() if needs_meter else None,
            meter_interval_value=self.meter_interval.text().strip() if needs_meter else None,
            warning_days=self.warning_days.value(), lead_days=self.warning_days.value(),
            tasks=tasks)


class PMPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = PMService(ctx.db)
        self.assets = AssetService(ctx.db)
        self.meters = MeterService(ctx.db)
        self._rows: list = []
        self._detail: PlanDetail | None = None
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
        self.due_state = QComboBox()
        self.due_state.currentIndexChanged.connect(lambda _i: self.refresh())
        self.btn_new = QPushButton()
        self.btn_new.setObjectName("primary")
        self.btn_new.clicked.connect(self._new)
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        bar.addWidget(self.search)
        bar.addWidget(self.status)
        bar.addWidget(self.due_state)
        bar.addStretch(1)
        bar.addWidget(self.btn_new)
        bar.addWidget(self.btn_refresh)
        lay.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = make_card()
        left_lay = QVBoxLayout(left)
        self.table = QTableWidget(0, 6)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        polish_table(self.table, lambda: self.ctx.tr("common.no_data"))
        self.table.itemSelectionChanged.connect(self._on_select)
        left_lay.addWidget(self.table)
        split.addWidget(left)

        right = make_card()
        right_lay = QVBoxLayout(right)
        self.head = QLabel()
        self.head.setObjectName("pageTitle")
        self.meta = QLabel()
        self.meta.setObjectName("hint")
        self.meta.setWordWrap(True)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tasks(), "")
        self.tabs.addTab(self._build_occurrences(), "")
        right_lay.addWidget(self.head)
        right_lay.addWidget(self.meta)
        right_lay.addWidget(self.tabs, 1)
        actions = QHBoxLayout()
        self.btn_generate = QPushButton()
        self.btn_generate.clicked.connect(self._generate)
        self.btn_skip = QPushButton()
        self.btn_skip.clicked.connect(self._skip)
        self.btn_toggle = QPushButton()
        self.btn_toggle.clicked.connect(self._toggle)
        actions.addWidget(self.btn_generate)
        actions.addWidget(self.btn_skip)
        actions.addStretch(1)
        actions.addWidget(self.btn_toggle)
        right_lay.addLayout(actions)
        split.addWidget(right)
        split.setSizes([720, 520])  # the list needs room for its 7 columns
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)

    def _build_tasks(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.tasks = QTableWidget(0, 2)
        self.tasks.verticalHeader().setVisible(False)
        polish_table(self.tasks, lambda: self.ctx.tr("common.no_data"))
        self.tasks.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lay.addWidget(self.tasks)
        return page

    def _build_occurrences(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.occurrences = QTableWidget(0, 3)
        self.occurrences.verticalHeader().setVisible(False)
        polish_table(self.occurrences, lambda: self.ctx.tr("common.no_data"))
        self.occurrences.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lay.addWidget(self.occurrences)
        return page

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("pm.title"))
        self.search.setPlaceholderText(tr("assets.search_hint"))
        self.btn_new.setText(tr("pm.new"))
        self.btn_refresh.setText(tr("common.refresh"))
        self.tabs.setTabText(0, tr("wo.tab.tasks"))
        self.tabs.setTabText(1, tr("pm.occurrences"))
        self.btn_generate.setText(tr("pm.generate"))
        self.btn_skip.setText(tr("pm.skip"))
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "pm.code", "wo.asset", "pm.title_label", "pm.trigger_label",
            "pm.next_due", "pm.state")])
        self.tasks.setHorizontalHeaderLabels([tr("wo.task.title"), tr("wo.task.required")])
        self.occurrences.setHorizontalHeaderLabels([tr("pm.due"), tr("wo.status"),
                                                    tr("wo.number")])
        current = self.status.currentData()
        self.status.blockSignals(True)
        self.status.clear()
        self.status.addItem(tr("assets.all"), None)
        for value in ("Active", "Paused", "Archived"):
            self.status.addItem(tr(f"pm.status.{value}"), value)
        index = self.status.findData(current)
        self.status.setCurrentIndex(max(0, index))
        self.status.blockSignals(False)
        current_state = self.due_state.currentData()
        self.due_state.blockSignals(True)
        self.due_state.clear()
        self.due_state.addItem(tr("pm.any_state"), None)
        for value in ("Overdue", "Due", "DueSoon", "AwaitingCompletion", "NoValidMeter"):
            self.due_state.addItem(tr(f"pm.state.{value}"), value)
        self.due_state.setCurrentIndex(max(0, self.due_state.findData(current_state)))
        self.due_state.blockSignals(False)
        self.refresh()

    def apply_filter(self, state: str | None) -> None:
        """Opened from a dashboard card: show plans in that due state."""
        self.search.clear()
        self.status.setCurrentIndex(max(0, self.status.findData("Active")))
        self.due_state.setCurrentIndex(max(0, self.due_state.findData(state)))

    # ---------------- data ----------------
    def refresh(self) -> None:
        self._rows = self.service.list(status=self.status.currentData(),
                                       query=self.search.text())
        if self.due_state.currentData():
            self._rows = [r for r in self._rows if r.state == self.due_state.currentData()]
        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            due = row.next_due_date or row.next_due_meter or "—"
            cells = (row.code, row.asset_code, row.title,
                     self.ctx.tr(f"pm.trigger.{row.trigger_policy}"), due,
                     self.ctx.tr(f"pm.state.{row.state}"))
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.id)
                self.table.setItem(i, col, item)
        if self._rows and self.table.currentRow() < 0:
            self.table.setCurrentCell(0, 0)
        if self._rows and self._detail is None:
            self._on_select()

    def _on_select(self) -> None:
        row = self.table.currentRow()
        if row < 0 and self._rows:
            row = 0
        if not (0 <= row < len(self._rows)):
            return
        self._detail = self.service.detail(self._rows[row].id)
        self._render()

    def _render(self) -> None:
        d = self._detail
        if d is None:
            return
        self.head.setText(f"{d.code} — {d.title}")
        self.meta.setText(
            f"{d.asset_code} · {self.ctx.tr(f'pm.trigger.{d.trigger_policy}')} · "
            f"{self.ctx.tr(f'pm.status.{d.status}')}")
        self.tasks.setRowCount(len(d.tasks))
        for i, task in enumerate(d.tasks):
            self.tasks.setItem(i, 0, QTableWidgetItem(f"{task.sequence}. {task.title}"))
            self.tasks.setItem(i, 1, QTableWidgetItem("✓" if task.required else "—"))
        self.occurrences.setRowCount(len(d.occurrences))
        for i, occ in enumerate(d.occurrences):
            self.occurrences.setItem(i, 0, QTableWidgetItem(
                occ.due_date or occ.due_meter or occ.due_key))
            self.occurrences.setItem(i, 1, QTableWidgetItem(
                self.ctx.tr(f"pm.occ.{occ.status}")))
            self.occurrences.setItem(i, 2, QTableWidgetItem(occ.wo_number or "—"))
        editable = self.ctx.can_edit and d.status == "Active"
        self.btn_generate.setEnabled(editable)
        self.btn_skip.setEnabled(editable)
        self.btn_toggle.setEnabled(self.ctx.can_edit)
        self.btn_toggle.setText(self.ctx.tr(
            "pm.pause" if d.status == "Active" else "pm.resume"))

    # ---------------- commands ----------------
    def _new(self) -> None:
        if not self.ctx.can_edit:
            QMessageBox.warning(self, self.ctx.tr("pm.new"),
                                self.ctx.tr("err.permission_denied"))
            return
        if not self.assets.list():
            QMessageBox.information(self, self.ctx.tr("pm.new"),
                                    self.ctx.tr("assets.empty_hint"))
            return
        dialog = NewPlanDialog(self.ctx, self.assets, self.meters, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.service.create(self.ctx.current_user, **dialog.payload())
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("pm.new"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self._detail = None
        self.refresh()

    def _generate(self) -> None:
        if self._detail is None:
            return
        result = self.service.generate(self.ctx.current_user, self._detail.id)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("pm.generate"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self._detail = self.service.detail(self._detail.id)
        self.refresh()
        self._render()

    def _skip(self) -> None:
        if self._detail is None:
            return
        reason, ok = QInputDialog.getMultiLineText(
            self, self.ctx.tr("pm.skip"), self.ctx.tr("wo.reason"))
        if not ok or not reason.strip():
            return
        result = self.service.skip(self.ctx.current_user, self._detail.id, reason)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("pm.skip"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self._detail = self.service.detail(self._detail.id)
        self.refresh()
        self._render()

    def _toggle(self) -> None:
        if self._detail is None:
            return
        target = "Paused" if self._detail.status == "Active" else "Active"
        result = self.service.set_status(self.ctx.current_user, self._detail.id, target)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("pm.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self._detail = self.service.detail(self._detail.id)
        self.refresh()
        self._render()
