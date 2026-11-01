"""Work orders screen: list, state-machine actions, tasks, time logs (SPEC 10)."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...application.context import AppContext
from ...application.dto.maintenance import WoDetail
from ...application.services.asset_service import AssetService
from ...application.services.downtime_service import DowntimeService
from ...application.services.inspection_service import InspectionService
from ...application.services.master_data_service import MasterDataService
from ...application.services.work_order_service import WorkOrderService
from ...domain.policies import wo_state_machine as sm
from .base import BasePage, make_card, make_title, vbox
from .inspections import FillDialog

# (button key, source statuses, target)
_ACTIONS = (
    ("wo.action.submit", (sm.DRAFT,), sm.OPEN),
    ("wo.action.assign", (sm.OPEN,), sm.ASSIGNED),
    ("wo.action.start", (sm.OPEN, sm.ASSIGNED), sm.IN_PROGRESS),
    ("wo.action.hold", (sm.ASSIGNED, sm.IN_PROGRESS), sm.ON_HOLD),
    ("wo.action.resume", (sm.ON_HOLD,), sm.IN_PROGRESS),
    ("wo.action.complete", (sm.IN_PROGRESS,), sm.COMPLETED),
    ("wo.action.close", (sm.COMPLETED,), sm.CLOSED),
    ("wo.action.reopen", (sm.COMPLETED, sm.CLOSED), sm.IN_PROGRESS),
    ("wo.action.cancel", (sm.DRAFT, sm.OPEN, sm.ASSIGNED), sm.CANCELLED),
)


class NewWorkOrderDialog(QDialog):
    def __init__(self, ctx: AppContext, service: WorkOrderService,
                 assets: AssetService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx, self.service, self.assets = ctx, service, assets
        self.setModal(True)
        self.setMinimumWidth(520)
        form = QFormLayout(self)
        self.asset = QComboBox()
        for row in assets.list():
            self.asset.addItem(f"{row.code} — {row.name(ctx.localizer.is_rtl)}", row.id)
        self.type = QComboBox()
        for value in ("CM", "PM", "INSPECTION", "OTHER"):
            self.type.addItem(ctx.tr(f"value.wotype.{value}"), value)
        self.title = QLineEdit()
        self.description = QPlainTextEdit()
        self.description.setFixedHeight(70)
        self.priority = QComboBox()
        for value in ("Critical", "High", "Medium", "Low"):
            self.priority.addItem(ctx.tr(f"value.criticality.{value}"), value)
        self.priority.setCurrentIndex(2)
        self.due = QDateEdit(QDate.currentDate().addDays(3))
        self.due.setCalendarPopup(True)
        self.lbl_asset = QLabel(ctx.tr("wo.asset"))
        self.lbl_type = QLabel(ctx.tr("wo.form.type"))
        self.lbl_title = QLabel(ctx.tr("wo.form.title_label"))
        self.lbl_desc = QLabel(ctx.tr("wo.form.description"))
        self.lbl_priority = QLabel(ctx.tr("wo.form.priority"))
        self.lbl_due = QLabel(ctx.tr("wo.form.due"))
        for label, widget in ((self.lbl_asset, self.asset), (self.lbl_type, self.type),
                              (self.lbl_title, self.title), (self.lbl_desc, self.description),
                              (self.lbl_priority, self.priority), (self.lbl_due, self.due)):
            form.addRow(label, widget)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        self.setWindowTitle(ctx.tr("wo.form.title"))

    def payload(self) -> dict:
        return dict(
            asset_id=self.asset.currentData(), type_=self.type.currentData(),
            title=self.title.text(), description=self.description.toPlainText().strip() or None,
            priority=self.priority.currentData(),
            due_at=self.due.date().toString("yyyy-MM-dd"))


class WorkOrdersPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = WorkOrderService(ctx.db)
        self.inspections = InspectionService(ctx.db)
        self.downtime = DowntimeService(ctx.db)
        self.assets = AssetService(ctx.db)
        self.masters = MasterDataService(ctx.db)
        self._rows: list = []
        self._detail: WoDetail | None = None
        self._build()
        self.retranslate()

    # ---------------- UI ----------------
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
        self.btn_new.clicked.connect(self._new)
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        bar.addWidget(self.search)
        bar.addWidget(self.status)
        bar.addStretch(1)
        bar.addWidget(self.btn_new)
        bar.addWidget(self.btn_refresh)
        lay.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = make_card()
        left_lay = QVBoxLayout(left)
        self.table = QTableWidget(0, 7)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
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
        self.tabs.addTab(self._build_time(), "")
        self.tabs.addTab(self._build_history(), "")
        self.tabs.addTab(self._build_inspections(), "")
        self.tabs.addTab(self._build_downtime(), "")
        right_lay.addWidget(self.head)
        right_lay.addWidget(self.meta)
        right_lay.addWidget(self.tabs, 1)

        actions = QHBoxLayout()
        self.btn_expense = QPushButton()
        self.btn_expense.clicked.connect(self._add_expense)
        actions.addWidget(self.btn_expense)
        self._buttons: dict[str, QPushButton] = {}
        for _key, _sources, target in _ACTIONS:
            btn = QPushButton()
            btn.clicked.connect(lambda _c=False, t=target: self._move(t))
            self._buttons[target] = btn
            actions.addWidget(btn)
        right_lay.addLayout(actions)
        split.addWidget(right)
        split.setSizes([620, 620])
        lay.addWidget(split, 1)

    def _build_tasks(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.tasks = QTableWidget(0, 3)
        self.tasks.verticalHeader().setVisible(False)
        self.tasks.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tasks.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.btn_task = QPushButton()
        self.btn_task.clicked.connect(self._add_task)
        bar = QHBoxLayout()
        self.btn_task_done = QPushButton()
        self.btn_task_done.clicked.connect(self._toggle_task)
        bar.addWidget(self.btn_task_done)
        bar.addStretch(1)
        bar.addWidget(self.btn_task)
        lay.addWidget(self.tasks, 1)
        lay.addLayout(bar)
        return page

    def _build_time(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.time = QTableWidget(0, 4)
        self.time.verticalHeader().setVisible(False)
        self.time.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.time.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.btn_time = QPushButton()
        self.btn_time.clicked.connect(self._add_time)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(self.btn_time)
        lay.addWidget(self.time, 1)
        lay.addLayout(bar)
        return page

    def _build_history(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.history = QTableWidget(0, 3)
        self.history.verticalHeader().setVisible(False)
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lay.addWidget(self.history)
        return page

    def _build_inspections(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.insp_table = QTableWidget(0, 4)
        self.insp_table.verticalHeader().setVisible(False)
        self.insp_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.insp_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.insp_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.btn_insp_start = QPushButton()
        self.btn_insp_start.clicked.connect(self._start_inspection)
        self.btn_insp_open = QPushButton()
        self.btn_insp_open.clicked.connect(self._open_inspection)
        bar = QHBoxLayout()
        bar.addWidget(self.btn_insp_start)
        bar.addWidget(self.btn_insp_open)
        bar.addStretch(1)
        lay.addWidget(self.insp_table, 1)
        lay.addLayout(bar)
        return page

    def _build_downtime(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.down_table = QTableWidget(0, 3)
        self.down_table.verticalHeader().setVisible(False)
        self.down_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.down_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.btn_down_start = QPushButton()
        self.btn_down_start.clicked.connect(self._start_downtime)
        self.btn_down_stop = QPushButton()
        self.btn_down_stop.clicked.connect(self._stop_downtime)
        bar = QHBoxLayout()
        bar.addWidget(self.btn_down_start)
        bar.addWidget(self.btn_down_stop)
        bar.addStretch(1)
        lay.addWidget(self.down_table, 1)
        lay.addLayout(bar)
        return page

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("wo.title"))
        self.search.setPlaceholderText(tr("assets.search_hint"))
        self.btn_new.setText(tr("wo.new"))
        self.btn_refresh.setText(tr("common.refresh"))
        self.tabs.setTabText(0, tr("wo.tab.tasks"))
        self.tabs.setTabText(1, tr("wo.tab.time"))
        self.tabs.setTabText(2, tr("wo.tab.history"))
        self.tabs.setTabText(3, tr("wo.tab.inspections"))
        self.tabs.setTabText(4, tr("wo.tab.downtime"))
        self.btn_down_start.setText(tr("wo.downtime.start"))
        self.btn_down_stop.setText(tr("wo.downtime.stop"))
        self.down_table.setHorizontalHeaderLabels([tr(k) for k in (
            "wo.downtime.from", "wo.downtime.to", "wo.downtime.type")])
        self.btn_insp_start.setText(tr("insp.start"))
        self.btn_insp_open.setText(tr("insp.open"))
        self.insp_table.setHorizontalHeaderLabels([tr(k) for k in (
            "insp.number", "insp.template_title", "wo.status", "insp.failed")])
        self.btn_task.setText(tr("wo.task.add"))
        self.btn_task_done.setText(tr("wo.task.toggle"))
        self.btn_time.setText(tr("wo.time.add"))
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "wo.number", "wo.asset", "wo.type", "wo.form.title_label", "wo.status",
            "wo.priority", "wo.assignee")])
        self.tasks.setHorizontalHeaderLabels([tr("wo.task.title"), tr("wo.task.required"),
                                              tr("wo.task.done")])
        self.time.setHorizontalHeaderLabels([tr("wo.time.technician"), tr("wo.time.start"),
                                             tr("wo.time.end"), tr("wo.time.category")])
        self.history.setHorizontalHeaderLabels([tr("assets.history.at"), tr("wo.status"),
                                                tr("wo.reason")])
        for key, _sources, target in _ACTIONS:
            self._buttons[target].setText(tr(key))
        self.btn_expense.setText(tr("wo.expense.add"))
        self._reload_statuses()
        self.refresh()

    def _reload_statuses(self) -> None:
        current = self.status.currentData()
        self.status.blockSignals(True)
        self.status.clear()
        self.status.addItem(self.ctx.tr("assets.all"), None)
        for value in sm.STATUSES:
            self.status.addItem(self.ctx.tr(f"value.wo.{value}"), value)
        index = self.status.findData(current)
        self.status.setCurrentIndex(max(0, index))
        self.status.blockSignals(False)

    # ---------------- data ----------------
    def refresh(self) -> None:
        self._rows = self.service.list(status=self.status.currentData(),
                                       query=self.search.text())
        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            cells = (row.number, row.asset_code, self.ctx.tr(f"value.wotype.{row.type}"),
                     row.title, self.ctx.tr(f"value.wo.{row.status}"),
                     self.ctx.tr(f"value.criticality.{row.priority}"),
                     row.assigned_to or "—")
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.id)
                self.table.setItem(i, col, item)
        if self._rows and self._detail is None:
            self.table.setCurrentCell(0, 0)
            self._on_select()

    def _on_select(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._rows)):
            return
        self._detail = self.service.detail(self._rows[row].id)
        self._render()

    def _render(self) -> None:
        d = self._detail
        if d is None:
            return
        self.head.setText(f"{d.number} — {d.title}")
        cost = d.cost
        self.meta.setText(
            f"{d.asset_code} · {self.ctx.tr(f'value.wotype.{d.type}')} · "
            f"{self.ctx.tr(f'value.wo.{d.status}')}"
            + (f" · {cost.total_minor / 100:,.2f} {cost.currency}" if cost else ""))
        self.tasks.setRowCount(len(d.tasks))
        for i, task in enumerate(d.tasks):
            first = QTableWidgetItem(f"{task.sequence}. {task.title}")
            first.setData(Qt.ItemDataRole.UserRole, task.id)
            self.tasks.setItem(i, 0, first)
            self.tasks.setItem(i, 1, QTableWidgetItem(
                "✓" if task.required else "—"))
            self.tasks.setItem(i, 2, QTableWidgetItem(
                self.ctx.tr("common.ok") if task.is_completed else "—"))
        self.time.setRowCount(len(d.time_logs))
        for i, log in enumerate(d.time_logs):
            self.time.setItem(i, 0, QTableWidgetItem(log.technician))
            self.time.setItem(i, 1, QTableWidgetItem(log.start_at[:16].replace("T", " ")))
            self.time.setItem(i, 2, QTableWidgetItem(log.end_at[:16].replace("T", " ")))
            self.time.setItem(i, 3, QTableWidgetItem(self.ctx.tr(f"value.timec.{log.category}")))
        self.history.setRowCount(len(d.events))
        for i, event in enumerate(d.events):
            self.history.setItem(i, 0, QTableWidgetItem(event.at[:19].replace("T", " ")))
            self.history.setItem(i, 1, QTableWidgetItem(
                f"{event.from_status or '—'} → {event.to_status}"))
            self.history.setItem(i, 2, QTableWidgetItem(event.reason or ""))

        editable = self.ctx.can_edit and d.status in (sm.DRAFT, sm.OPEN, sm.ASSIGNED,
                                                      sm.IN_PROGRESS, sm.ON_HOLD)
        self.btn_expense.setEnabled(self.ctx.can_edit)
        self.btn_task.setEnabled(editable)
        self.btn_task_done.setEnabled(editable)
        self.btn_time.setEnabled(editable)
        self.btn_insp_start.setEnabled(self.ctx.can_edit and d.status != sm.CANCELLED)
        self._render_inspections(d)
        self.btn_down_start.setEnabled(self.ctx.can_edit)
        self.btn_down_stop.setEnabled(self.ctx.can_edit)
        self._render_downtime(d)
        allowed = set(sm.allowed_targets(d.status, self.ctx.current_user.role
                                         if self.ctx.current_user else None))
        for _key, sources, target in _ACTIONS:
            btn = self._buttons[target]
            btn.setVisible(d.status in sources)
            btn.setEnabled(d.status in sources and target in allowed)

    def _render_inspections(self, d) -> None:
        rows = self.inspections.list(asset_id=d.asset_id)
        self._insp_rows = rows
        self.insp_table.setRowCount(len(rows))
        for i, run in enumerate(rows):
            cells = (run.number, run.template_title or "—",
                     self.ctx.tr(f"insp.status.{run.status}"), str(run.failed_items))
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, run.id)
                self.insp_table.setItem(i, col, item)

    def _render_downtime(self, d) -> None:
        rows = self.downtime.list_for_asset(d.asset_id)
        self._down_rows = rows
        self.down_table.setRowCount(len(rows))
        for i, (downtime_id, started, ended, kind, _reason) in enumerate(rows):
            cells = (started[:16].replace("T", " "),
                     (ended or "…")[:16].replace("T", " "),
                     self.ctx.tr(f"value.downtime.{kind}"))
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, downtime_id)
                self.down_table.setItem(i, col, item)

    # ---------------- commands ----------------
    def _new(self) -> None:
        if not self.ctx.can_edit:
            QMessageBox.warning(self, self.ctx.tr("wo.new"),
                                self.ctx.tr("err.permission_denied"))
            return
        if not self.assets.list():
            QMessageBox.information(self, self.ctx.tr("wo.new"),
                                    self.ctx.tr("assets.empty_hint"))
            return
        dialog = NewWorkOrderDialog(self.ctx, self.service, self.assets, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.service.create(self.ctx.current_user, **dialog.payload())
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("wo.new"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self._detail = None
        self.refresh()

    def _move(self, target: str) -> None:
        if self._detail is None:
            return
        reason = None
        equipment_returned = None
        closeout = None
        if target == sm.CANCELLED:
            reason, ok = QInputDialog.getMultiLineText(
                self, self.ctx.tr("wo.action.cancel"), self.ctx.tr("wo.reason"))
            if not ok:
                return
        elif target == sm.ON_HOLD:
            reason, ok = QInputDialog.getText(
                self, self.ctx.tr("wo.action.hold"), self.ctx.tr("wo.reason"))
            if not ok:
                return
        elif target == sm.IN_PROGRESS and self._detail.status in (sm.COMPLETED, sm.CLOSED):
            reason, ok = QInputDialog.getText(
                self, self.ctx.tr("wo.action.reopen"), self.ctx.tr("wo.reason"))
            if not ok:
                return
        elif target == sm.COMPLETED:
            answer = QMessageBox.question(
                self, self.ctx.tr("wo.action.complete"),
                self.ctx.tr("wo.complete.returned"))
            equipment_returned = answer == QMessageBox.StandardButton.Yes
        elif target == sm.CLOSED:
            closeout, ok = QInputDialog.getMultiLineText(
                self, self.ctx.tr("wo.action.close"), self.ctx.tr("wo.close.notes"))
            if not ok:
                return
        elif target == sm.ASSIGNED:
            techs = self.masters.technicians()
            if not techs:
                QMessageBox.information(self, self.ctx.tr("wo.action.assign"),
                                        self.ctx.tr("err.technician_inactive"))
                return
            labels = [t.name_ar for t in techs]
            choice, ok = QInputDialog.getItem(
                self, self.ctx.tr("wo.action.assign"), self.ctx.tr("wo.time.technician"),
                labels, 0, False)
            if not ok:
                return
            result = self.service.assign(self.ctx.current_user, self._detail.id,
                                         techs[labels.index(choice)].id)
            self._after(result)
            return

        result = self.service.transition(
            self.ctx.current_user, self._detail.id, target, reason=reason,
            equipment_returned=equipment_returned, closeout_notes=closeout)
        self._after(result)

    def _after(self, result) -> None:
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("wo.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self._detail = self.service.detail(self._detail.id)
        self.refresh()
        self._render()

    def _start_inspection(self) -> None:
        if self._detail is None:
            return
        templates = self.inspections.templates()
        if not templates:
            QMessageBox.information(self, self.ctx.tr("insp.title"),
                                    self.ctx.tr("insp.templates") + ": —")
            return
        labels = [f"{t.code} — {t.title_ar}" for t in templates]
        choice, ok = QInputDialog.getItem(
            self, self.ctx.tr("insp.start"), self.ctx.tr("insp.template_title"),
            labels, 0, False)
        if not ok:
            return
        template_id = templates[labels.index(choice)].id
        result = self.inspections.start(self.ctx.current_user, self._detail.asset_id,
                                        template_id, wo_id=self._detail.id)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("insp.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self._open_inspection(result.value)
        self._render_inspections(self._detail)

    def _open_inspection(self, inspection_id: str | None = None) -> None:
        if inspection_id is None:
            row = self.insp_table.currentRow()
            rows = getattr(self, "_insp_rows", [])
            if not (0 <= row < len(rows)):
                return
            inspection_id = rows[row].id
        dialog = FillDialog(self.ctx, self.inspections, inspection_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = self.inspections.complete(self.ctx.current_user, inspection_id)
            if not result.ok:
                QMessageBox.warning(self, self.ctx.tr("insp.title"),
                                    self.ctx.tr(result.error_code or "err.invalid"))
        if self._detail is not None:
            self._render_inspections(self._detail)

    def _toggle_task(self) -> None:
        if self._detail is None or not self.ctx.can_edit:
            return
        row = self.tasks.currentRow()
        if row < 0 and self.tasks.rowCount():
            row = 0
        item = self.tasks.item(row, 0) if row >= 0 else None
        if item is None:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        current = next((t for t in self._detail.tasks if t.id == task_id), None)
        if current is None:
            return
        result = self.service.set_task_result(
            self.ctx.current_user, self._detail.id, task_id,
            self.ctx.tr("wo.task.done_result"), not current.is_completed)
        self._after(result)

    def _start_downtime(self) -> None:
        if self._detail is None or not self.ctx.can_edit:
            return
        from ...infrastructure.database.orm_models.base import utcnow_iso
        result = self.downtime.start(self.ctx.current_user, self._detail.asset_id,
                                     utcnow_iso(), "unplanned")
        self._after(result)

    def _stop_downtime(self) -> None:
        if self._detail is None or not self.ctx.can_edit:
            return
        from ...infrastructure.database.orm_models.base import utcnow_iso
        event = self.downtime.open_event(self._detail.asset_id)
        if event is None:
            return
        self._after(self.downtime.end(self.ctx.current_user, event.id, utcnow_iso()))

    def _add_expense(self) -> None:
        if self._detail is None or not self.ctx.can_edit:
            return
        from datetime import date

        from PySide6.QtWidgets import QDoubleSpinBox
        amount = QDoubleSpinBox()
        amount.setMaximum(1_000_000)
        amount.setDecimals(2)
        kind = QComboBox()
        for value in ("External Repair", "Transport", "Other"):
            kind.addItem(value, value)
        notes = QLineEdit()
        dialog = QDialog(self)
        dialog.setWindowTitle(self.ctx.tr("wo.expense.add"))
        form = QFormLayout(dialog)
        form.addRow(QLabel(self.ctx.tr("wo.expense.amount")), amount)
        form.addRow(QLabel(self.ctx.tr("wo.expense.type")), kind)
        form.addRow(QLabel(self.ctx.tr("wo.expense.notes")), notes)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                               | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(dialog.accept)
        box.rejected.connect(dialog.reject)
        form.addRow(box)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.service.add_expense(
            self.ctx.current_user, self._detail.id, date.today().isoformat(),
            kind.currentData(), int(round(amount.value() * 100)),
            notes=notes.text().strip() or None)
        self._after(result)

    def _add_task(self) -> None:
        if self._detail is None:
            return
        title, ok = QInputDialog.getText(self, self.ctx.tr("wo.task.add"),
                                         self.ctx.tr("wo.task.title"))
        if not ok or not title.strip():
            return
        result = self.service.add_task(self.ctx.current_user, self._detail.id, title)
        self._after(result)

    def _add_time(self) -> None:
        if self._detail is None:
            return
        techs = self.masters.technicians()
        if not techs:
            return
        labels = [t.name_ar for t in techs]
        choice, ok = QInputDialog.getItem(
            self, self.ctx.tr("wo.time.add"), self.ctx.tr("wo.time.technician"),
            labels, 0, False)
        if not ok:
            return
        start, ok = QInputDialog.getText(self, self.ctx.tr("wo.time.add"),
                                         f"{self.ctx.tr('wo.time.start')} (YYYY-MM-DDTHH:MM)")
        if not ok:
            return
        end, ok = QInputDialog.getText(self, self.ctx.tr("wo.time.add"),
                                       f"{self.ctx.tr('wo.time.end')} (YYYY-MM-DDTHH:MM)")
        if not ok:
            return
        result = self.service.add_time_log(self.ctx.current_user, self._detail.id,
                                           techs[labels.index(choice)].id, start, end)
        self._after(result)
