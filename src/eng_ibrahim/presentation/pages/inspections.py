"""Inspections screen: templates and form execution (SPEC 11)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...application.context import AppContext
from ...application.services.asset_service import AssetService
from ...application.services.inspection_service import InspectionService
from ..widgets.tables import polish_table
from .base import BasePage, make_card, make_title, vbox

_CHOICES = {
    "pass_fail": [("", ""), ("pass", "✓"), ("fail", "✗")],
    "yes_no": [("", ""), ("yes", "نعم"), ("no", "لا")],
    "done_na": [("", ""), ("done", "تم"), ("na", "لا ينطبق")],
}


class NewTemplateDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setModal(True)
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        self.code, self.title = QLineEdit(), QLineEdit()
        self.items = QPlainTextEdit()
        self.items.setFixedHeight(120)
        self.lbl_code = QLabel(ctx.tr("insp.code"))
        self.lbl_title = QLabel(ctx.tr("insp.template_title"))
        self.lbl_items = QLabel(ctx.tr("insp.items_hint"))
        form.addRow(self.lbl_code, self.code)
        form.addRow(self.lbl_title, self.title)
        form.addRow(self.lbl_items, self.items)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        self.setWindowTitle(ctx.tr("insp.new_template"))

    def payload(self) -> dict:
        items = [(line.strip(), "pass_fail", True)
                 for line in self.items.toPlainText().splitlines() if line.strip()]
        return dict(template_code=self.code.text(), title_ar=self.title.text(), items=items)


class FillDialog(QDialog):
    def __init__(self, ctx: AppContext, service: InspectionService,
                 inspection_id: str, parent=None) -> None:
        super().__init__(parent)
        self.ctx, self.service, self.inspection_id = ctx, service, inspection_id
        self.setModal(True)
        self.setMinimumWidth(520)
        self._inputs: list[tuple[str, QWidget, str]] = []
        outer = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        outer.addWidget(self.title)
        form = QFormLayout()
        for answer in service.answers(inspection_id):
            kind = answer.response_type
            if kind in _CHOICES:
                widget = QComboBox()
                for value, label in _CHOICES[kind]:
                    widget.addItem(label, value)
                index = widget.findData(answer.pass_fail or "")
                widget.setCurrentIndex(max(0, index))
            else:
                widget = QLineEdit(answer.answer)
            required = "*" if answer.required else ""
            form.addRow(QLabel(f"{answer.label}{required}"), widget)
            self._inputs.append((answer.id, widget, kind))
        outer.addLayout(form)
        self.error = QLabel()
        self.error.setObjectName("formError")
        self.error.setVisible(False)
        outer.addWidget(self.error)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            ctx.tr("common.cancel"))
        self.setWindowTitle(ctx.tr("insp.fill"))

    def _save(self) -> None:
        for answer_id, widget, _kind in self._inputs:
            if isinstance(widget, QComboBox):
                value = widget.currentData()
                pass_fail = value or None
                text = "pass" if value == "pass" else ("fail" if value == "fail" else value)
            else:
                text, pass_fail = widget.text().strip(), None
            result = self.service.answer(self.ctx.current_user, self.inspection_id,
                                         answer_id, text, pass_fail)
            if not result.ok:
                self.error.setText(self.ctx.tr(result.error_code or "err.invalid"))
                self.error.setVisible(True)
                return
        self.accept()


class InspectionsPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = InspectionService(ctx.db)
        self.assets = AssetService(ctx.db)
        self._templates: list = []
        self._inspections: list = []
        self._build()
        self.retranslate()

    def _build(self) -> None:
        lay = vbox(self)
        self.title = make_title()
        lay.addWidget(self.title)

        split = QSplitter(Qt.Orientation.Horizontal)
        templates_card = make_card()
        t_lay = QVBoxLayout(templates_card)
        self.templates_title = QLabel()
        self.templates_title.setObjectName("sectionTitle")
        self.template_table = QTableWidget(0, 3)
        self.template_table.verticalHeader().setVisible(False)
        self.template_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        polish_table(self.template_table, lambda: self.ctx.tr("common.no_data"))
        self.btn_template = QPushButton()
        self.btn_template.clicked.connect(self._new_template)
        t_lay.addWidget(self.templates_title)
        t_lay.addWidget(self.template_table, 1)
        t_lay.addWidget(self.btn_template)
        split.addWidget(templates_card)

        runs_card = make_card()
        r_lay = QVBoxLayout(runs_card)
        self.runs_title = QLabel()
        self.runs_title.setObjectName("sectionTitle")
        self.table = QTableWidget(0, 5)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        polish_table(self.table, lambda: self.ctx.tr("common.no_data"))
        actions = QHBoxLayout()
        self.btn_start = QPushButton()
        self.btn_start.clicked.connect(self._start)
        self.btn_open = QPushButton()
        self.btn_open.clicked.connect(self._open)
        actions.addWidget(self.btn_start)
        actions.addWidget(self.btn_open)
        actions.addStretch(1)
        r_lay.addWidget(self.runs_title)
        r_lay.addWidget(self.table, 1)
        r_lay.addLayout(actions)
        split.addWidget(runs_card)
        split.setSizes([420, 620])
        lay.addWidget(split, 1)

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("insp.title"))
        self.templates_title.setText(tr("insp.templates"))
        self.runs_title.setText(tr("insp.runs"))
        self.btn_template.setText(tr("insp.new_template"))
        self.btn_start.setText(tr("insp.start"))
        self.btn_open.setText(tr("insp.open"))
        self.template_table.setHorizontalHeaderLabels([tr(k) for k in (
            "insp.code", "insp.template_title", "insp.item_count")])
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "insp.number", "wo.asset", "insp.template_title", "wo.status", "insp.failed")])
        self.refresh()

    def refresh(self) -> None:
        self._templates = self.service.templates()
        self.template_table.setRowCount(len(self._templates))
        for i, template in enumerate(self._templates):
            for col, text in enumerate((template.code, template.title_ar,
                                        str(template.item_count))):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, template.id)
                self.template_table.setItem(i, col, item)
        if self._templates and self.template_table.currentRow() < 0:
            self.template_table.setCurrentCell(0, 0)

        self._inspections = self.service.list()
        self.table.setRowCount(len(self._inspections))
        for i, run in enumerate(self._inspections):
            cells = (run.number, run.asset_code, run.template_title or "—",
                     self.ctx.tr(f"insp.status.{run.status}"), str(run.failed_items))
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, run.id)
                self.table.setItem(i, col, item)
        if self._inspections and self.table.currentRow() < 0:
            self.table.setCurrentCell(0, 0)

    # ---------------- commands ----------------
    def _new_template(self) -> None:
        if not self.ctx.can_edit:
            return
        dialog = NewTemplateDialog(self.ctx, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.service.create_template(self.ctx.current_user, **dialog.payload())
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("insp.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()

    def _start(self) -> None:
        if not self.ctx.can_edit or not self._templates:
            return
        assets = self.assets.list()
        if not assets:
            return
        from PySide6.QtWidgets import QInputDialog
        labels = [f"{a.code} — {a.name(self.ctx.localizer.is_rtl)}" for a in assets]
        choice, ok = QInputDialog.getItem(self, self.ctx.tr("insp.start"),
                                          self.ctx.tr("wo.asset"), labels, 0, False)
        if not ok:
            return
        template_labels = [f"{t.code} — {t.title_ar}" for t in self._templates]
        t_choice, ok = QInputDialog.getItem(self, self.ctx.tr("insp.start"),
                                            self.ctx.tr("insp.template_title"),
                                            template_labels, 0, False)
        if not ok:
            return
        asset_id = assets[labels.index(choice)].id
        template_id = self._templates[template_labels.index(t_choice)].id
        result = self.service.start(self.ctx.current_user, asset_id, template_id)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("insp.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()
        self._fill(result.value)

    def _open(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._inspections)):
            return
        self._fill(self._inspections[row].id)

    def _fill(self, inspection_id: str) -> None:
        dialog = FillDialog(self.ctx, self.service, inspection_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = self.service.complete(self.ctx.current_user, inspection_id)
            if not result.ok:
                QMessageBox.warning(self, self.ctx.tr("insp.title"),
                                    self.ctx.tr(result.error_code or "err.invalid"))
        self.refresh()
