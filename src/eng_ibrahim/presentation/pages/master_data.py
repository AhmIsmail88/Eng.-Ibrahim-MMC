"""Master data (UI-019): locations, categories and asset types (SPEC 4)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from ...application.context import AppContext
from ...application.services.master_data_service import MasterDataService
from ...infrastructure.database.orm_models import FailureCode, MaintenanceTask, Unit
from .base import BasePage, make_card, make_title, vbox


class _Dialog(QDialog):
    def __init__(self, ctx: AppContext, title: str, fields: list[tuple[str, QWidget]],
                 parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setModal(True)
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        for label, widget in fields:
            form.addRow(QLabel(label), widget)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        self.setWindowTitle(title)


class MasterDataPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = MasterDataService(ctx.db)
        self._build()
        self.retranslate()

    def _build(self) -> None:
        lay = vbox(self)
        self.title = make_title()
        lay.addWidget(self.title)
        card = make_card()
        card_lay = QVBoxLayout(card)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_locations(), "")
        self.tabs.addTab(self._tab_categories(), "")
        self.tabs.addTab(self._tab_types(), "")
        self.fc_table = self._table()
        self.task_table = self._table()
        self.unit_table = self._table()
        fc_page = QWidget()
        fc_lay = QVBoxLayout(fc_page)
        self.btn_fc = QPushButton()
        self.btn_fc.clicked.connect(self._new_failure_code)
        fc_bar = QHBoxLayout()
        fc_bar.addStretch(1)
        fc_bar.addWidget(self.btn_fc)
        fc_lay.addWidget(self.fc_table, 1)
        fc_lay.addLayout(fc_bar)
        self.tabs.addTab(fc_page, "")
        for table in (self.task_table, self.unit_table):
            page = QWidget()
            inner = QVBoxLayout(page)
            inner.addWidget(table)
            self.tabs.addTab(page, "")
        card_lay.addWidget(self.tabs)
        lay.addWidget(card, 1)

    def _table(self) -> QTableWidget:
        table = QTableWidget(0, 3)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def _tab_locations(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.loc_table, self.btn_loc = self._table(), QPushButton()
        self.btn_loc.clicked.connect(self._new_location)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(self.btn_loc)
        lay.addWidget(self.loc_table, 1)
        lay.addLayout(bar)
        return page

    def _tab_categories(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.cat_table, self.btn_cat = self._table(), QPushButton()
        self.btn_cat.clicked.connect(self._new_category)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(self.btn_cat)
        lay.addWidget(self.cat_table, 1)
        lay.addLayout(bar)
        return page

    def _tab_types(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.type_table, self.btn_type = self._table(), QPushButton()
        self.btn_type.clicked.connect(self._new_type)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(self.btn_type)
        lay.addWidget(self.type_table, 1)
        lay.addLayout(bar)
        return page

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("master.title"))
        self.tabs.setTabText(0, tr("master.locations"))
        self.tabs.setTabText(1, tr("master.categories"))
        self.tabs.setTabText(2, tr("master.types"))
        self.tabs.setTabText(3, tr("master.failure_codes"))
        self.tabs.setTabText(4, tr("master.task_library"))
        self.tabs.setTabText(5, tr("master.units"))
        self.btn_fc.setText(tr("master.new_failure_code"))
        for table in (self.fc_table, self.task_table, self.unit_table):
            table.setHorizontalHeaderLabels([tr("master.code"), tr("master.name"),
                                             tr("master.extra")])
        self.btn_loc.setText(tr("master.new_location"))
        self.btn_cat.setText(tr("master.new_category"))
        self.btn_type.setText(tr("master.new_type"))
        for table in (self.loc_table, self.cat_table, self.type_table):
            table.setHorizontalHeaderLabels([tr("master.code"), tr("master.name"),
                                             tr("master.extra")])
        self.refresh()

    def refresh(self) -> None:
        locations = self.service.locations(active_only=False)
        self.loc_table.setRowCount(len(locations))
        for i, loc in enumerate(locations):
            self.loc_table.setItem(i, 0, QTableWidgetItem(loc.code))
            self.loc_table.setItem(i, 1, QTableWidgetItem(loc.name_ar))
            self.loc_table.setItem(i, 2, QTableWidgetItem(loc.name_en or "—"))
        categories = self.service.categories(active_only=False)
        self.cat_table.setRowCount(len(categories))
        for i, cat in enumerate(categories):
            self.cat_table.setItem(i, 0, QTableWidgetItem(cat.code))
            self.cat_table.setItem(i, 1, QTableWidgetItem(cat.name_ar))
            self.cat_table.setItem(i, 2, QTableWidgetItem(cat.name_en or "—"))
        types = self.service.types_with_category()
        self.type_table.setRowCount(len(types))
        for i, (_tid, code, name, category) in enumerate(types):
            self.type_table.setItem(i, 0, QTableWidgetItem(code))
            self.type_table.setItem(i, 1, QTableWidgetItem(name))
            self.type_table.setItem(i, 2, QTableWidgetItem(category))
        for btn in (self.btn_loc, self.btn_cat, self.btn_type, self.btn_fc):
            btn.setEnabled(self.ctx.can_edit)
        with self.ctx.db.session() as session:
            codes = session.scalars(select(FailureCode).order_by(FailureCode.code)).all()
            self.fc_table.setRowCount(len(codes))
            for i, code in enumerate(codes):
                self.fc_table.setItem(i, 0, QTableWidgetItem(code.code))
                self.fc_table.setItem(i, 1, QTableWidgetItem(code.name_ar))
                self.fc_table.setItem(i, 2, QTableWidgetItem(code.group_code))
            tasks = session.scalars(select(MaintenanceTask)
                                    .order_by(MaintenanceTask.task_code)).all()
            self.task_table.setRowCount(len(tasks))
            for i, task in enumerate(tasks):
                self.task_table.setItem(i, 0, QTableWidgetItem(task.task_code))
                self.task_table.setItem(i, 1, QTableWidgetItem(task.title_ar))
                self.task_table.setItem(i, 2, QTableWidgetItem(
                    f"{task.estimated_min} min" if task.estimated_min else ""))
            units = session.scalars(select(Unit).order_by(Unit.code)).all()
            self.unit_table.setRowCount(len(units))
            for i, unit in enumerate(units):
                self.unit_table.setItem(i, 0, QTableWidgetItem(unit.code))
                self.unit_table.setItem(i, 1, QTableWidgetItem(unit.label_ar))
                self.unit_table.setItem(i, 2, QTableWidgetItem(unit.dimension))

    # ---------------- commands ----------------
    def _new_location(self) -> None:
        code, name, name_en = QLineEdit(), QLineEdit(), QLineEdit()
        dialog = _Dialog(self.ctx, self.ctx.tr("master.new_location"), [
            (self.ctx.tr("master.code"), code), (self.ctx.tr("master.name"), name),
            (self.ctx.tr("master.name_en"), name_en)], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.service.create_location(self.ctx.current_user, code.text(), name.text(),
                                             name_en.text().strip() or None)
        self._done(result)

    def _new_category(self) -> None:
        code, name, name_en = QLineEdit(), QLineEdit(), QLineEdit()
        dialog = _Dialog(self.ctx, self.ctx.tr("master.new_category"), [
            (self.ctx.tr("master.code"), code), (self.ctx.tr("master.name"), name),
            (self.ctx.tr("master.name_en"), name_en)], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.service.create_category(self.ctx.current_user, code.text(), name.text(),
                                             name_en.text().strip() or None)
        self._done(result)

    def _new_type(self) -> None:
        categories = self.service.categories()
        if not categories:
            return
        code, name = QLineEdit(), QLineEdit()
        category = QComboBox()
        for item in categories:
            category.addItem(f"{item.code} — {item.name_ar}", item.id)
        dialog = _Dialog(self.ctx, self.ctx.tr("master.new_type"), [
            (self.ctx.tr("master.code"), code), (self.ctx.tr("master.name"), name),
            (self.ctx.tr("master.category"), category)], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.service.create_type(self.ctx.current_user, category.currentData(),
                                          code.text(), name.text())
        self._done(result)

    def _new_failure_code(self) -> None:
        group = QComboBox()
        group.addItems(["MECH", "ELEC", "INST", "OPER", "EXT", "OTH"])
        code, name = QLineEdit(), QLineEdit()
        dialog = _Dialog(self.ctx, self.ctx.tr("master.new_failure_code"), [
            (self.ctx.tr("master.group"), group), (self.ctx.tr("master.code"), code),
            (self.ctx.tr("master.name"), name)], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.service.create_failure_code(self.ctx.current_user,
                                                  group.currentText(), code.text(),
                                                  name.text())
        self._done(result)

    def _done(self, result) -> None:
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("master.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()
