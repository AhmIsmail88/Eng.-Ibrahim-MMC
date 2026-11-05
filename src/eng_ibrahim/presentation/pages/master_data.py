"""Master data (UI-019, SPEC 3.8): every reference list as one tab, CRUD per SPEC 4."""
from __future__ import annotations

from PySide6.QtCore import QTime
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ...application.context import AppContext
from ...application.services.master_data_service import MasterDataService
from ...application.services.reference_admin import KINDS, ReferenceAdminService, RefRow
from ..widgets.tables import polish_table
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


# Display order Saturday → Friday (the local work week); stored weekday is 0 = Sunday.
_WEEK_ORDER = (6, 0, 1, 2, 3, 4, 5)


class CalendarWeekDialog(QDialog):
    """One shift per day; an end before the start means the shift crosses midnight."""

    def __init__(self, ctx: AppContext, week: dict[int, tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        self.rows: dict[int, tuple[QCheckBox, QTimeEdit, QTimeEdit]] = {}
        for weekday in _WEEK_ORDER:
            on = QCheckBox(ctx.tr(f"master.weekday.{weekday}"))
            start, end = week.get(weekday, ("08:00", "16:00"))
            start_edit = QTimeEdit(QTime.fromString(start, "HH:mm"))
            end_edit = QTimeEdit(QTime.fromString(end, "HH:mm"))
            for edit in (start_edit, end_edit):
                edit.setDisplayFormat("HH:mm")
                edit.setEnabled(weekday in week)
                on.toggled.connect(edit.setEnabled)
            on.setChecked(weekday in week)
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(start_edit)
            lay.addWidget(QLabel("—"))
            lay.addWidget(end_edit)
            form.addRow(on, row)
            self.rows[weekday] = (on, start_edit, end_edit)
        hint = QLabel(ctx.tr("master.calendar_hint"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form.addRow(hint)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        form.addRow(self.buttons)
        self.setWindowTitle(ctx.tr("master.calendar_week"))

    def payload(self) -> dict[int, tuple[str, str]]:
        return {weekday: (start.time().toString("HH:mm"), end.time().toString("HH:mm"))
                for weekday, (on, start, end) in self.rows.items() if on.isChecked()}


# tab order → (reference kind, table attribute)
TAB_KINDS = (("location", "loc_table"), ("category", "cat_table"), ("type", "type_table"),
             ("failure_code", "fc_table"), ("task", "task_table"), ("unit", "unit_table"),
             ("warehouse", "wh_table"), ("currency", "cur_table"), ("calendar", "cal_table"))


class MasterDataPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = MasterDataService(ctx.db)
        self.admin = ReferenceAdminService(ctx.db)
        self._rows: dict[str, list[RefRow]] = {}
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
        task_page = QWidget()
        task_lay = QVBoxLayout(task_page)
        self.btn_task_new = QPushButton()
        self.btn_task_new.clicked.connect(self._new_task)
        task_bar = QHBoxLayout()
        task_bar.addStretch(1)
        task_bar.addWidget(self.btn_task_new)
        task_lay.addWidget(self.task_table, 1)
        task_lay.addLayout(task_bar)
        self.tabs.addTab(task_page, "")
        unit_page = QWidget()
        unit_lay = QVBoxLayout(unit_page)
        self.btn_unit = QPushButton()
        self.btn_unit.clicked.connect(self._new_unit)
        unit_bar = QHBoxLayout()
        unit_bar.addStretch(1)
        unit_bar.addWidget(self.btn_unit)
        unit_lay.addWidget(self.unit_table, 1)
        unit_lay.addLayout(unit_bar)
        self.tabs.addTab(unit_page, "")
        self.wh_table = self._table()
        wh_page = QWidget()
        wh_lay = QVBoxLayout(wh_page)
        self.btn_wh = QPushButton()
        self.btn_wh.clicked.connect(self._new_warehouse)
        wh_bar = QHBoxLayout()
        wh_bar.addStretch(1)
        wh_bar.addWidget(self.btn_wh)
        wh_lay.addWidget(self.wh_table, 1)
        wh_lay.addLayout(wh_bar)
        self.tabs.addTab(wh_page, "")
        self.cur_table = self._table()
        self.btn_cur = QPushButton()
        self.btn_cur.clicked.connect(self._new_currency)
        self.tabs.addTab(self._tab(self.cur_table, self.btn_cur), "")
        self.cal_table = self._table()
        self.cal_table.setColumnCount(4)
        self.btn_cal = QPushButton()
        self.btn_cal.clicked.connect(self._new_calendar)
        self.btn_cal_week = QPushButton()
        self.btn_cal_week.clicked.connect(self._edit_calendar_week)
        self.tabs.addTab(self._tab(self.cal_table, self.btn_cal, self.btn_cal_week), "")
        card_lay.addWidget(self.tabs)
        lay.addWidget(card, 1)
        # Every tab gets Edit and Archive/Restore next to its "New" button (SPEC 3.8).
        self._row_buttons: dict[str, tuple[QPushButton, QPushButton]] = {}
        for index, (kind, table_attr) in enumerate(TAB_KINDS):
            bar = self.tabs.widget(index).layout().itemAt(1).layout()
            edit, archive = QPushButton(), QPushButton()
            edit.clicked.connect(lambda _c=False, k=kind: self._edit_selected(k))
            archive.clicked.connect(lambda _c=False, k=kind: self._toggle_archive(k))
            bar.insertWidget(1, archive)
            bar.insertWidget(1, edit)
            self._row_buttons[kind] = (edit, archive)
            table: QTableWidget = getattr(self, table_attr)
            table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            table.itemSelectionChanged.connect(lambda k=kind: self._sync_buttons(k))
            table.currentCellChanged.connect(lambda *_a, k=kind: self._sync_buttons(k))
            table.itemDoubleClicked.connect(lambda _i, k=kind: self._edit_selected(k))

    @staticmethod
    def _tab(table: QTableWidget, *buttons: QPushButton) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        bar = QHBoxLayout()
        bar.addStretch(1)
        for button in buttons:
            bar.addWidget(button)
        lay.addWidget(table, 1)
        lay.addLayout(bar)
        return page

    def _table(self) -> QTableWidget:
        table = QTableWidget(0, 3)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        polish_table(table, lambda: self.ctx.tr("common.no_data"))
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
        self.btn_task_new.setText(tr("master.new_task"))
        self.tabs.setTabText(6, tr("master.warehouses"))
        self.tabs.setTabText(7, tr("master.currencies"))
        self.tabs.setTabText(8, tr("master.calendars"))
        self.btn_unit.setText(tr("master.new_unit"))
        self.btn_cur.setText(tr("master.new_currency"))
        self.btn_cal.setText(tr("master.new_calendar"))
        self.btn_cal_week.setText(tr("master.calendar_week"))
        self.cur_table.setHorizontalHeaderLabels([tr("master.code"), tr("master.name"),
                                                 tr("master.minor_units")])
        self.cal_table.setHorizontalHeaderLabels([tr("master.code"), tr("master.name"),
                                                 tr("master.working_days"),
                                                 tr("master.weekly_hours")])
        self.btn_wh.setText(tr("master.new_warehouse"))
        self.wh_table.setHorizontalHeaderLabels([tr("master.code"), tr("master.name"),
                                                tr("master.extra")])
        for table in (self.fc_table, self.task_table, self.unit_table):
            table.setHorizontalHeaderLabels([tr("master.code"), tr("master.name"),
                                             tr("master.extra")])
        self.btn_loc.setText(tr("master.new_location"))
        self.btn_cat.setText(tr("master.new_category"))
        self.btn_type.setText(tr("master.new_type"))
        for edit, archive in self._row_buttons.values():
            edit.setText(tr("master.edit"))
            archive.setText(tr("master.archive"))
        for table in (self.loc_table, self.cat_table, self.type_table):
            table.setHorizontalHeaderLabels([tr("master.code"), tr("master.name"),
                                             tr("master.extra")])
        self.refresh()

    def refresh(self) -> None:
        for btn in (self.btn_loc, self.btn_cat, self.btn_type, self.btn_fc, self.btn_wh,
                    self.btn_task_new, self.btn_unit, self.btn_cur, self.btn_cal,
                    self.btn_cal_week):
            btn.setEnabled(self.ctx.can_edit)
        categories = {t[0]: t[3] for t in self.service.types_with_category()}
        self._rows: dict[str, list[RefRow]] = {}
        for kind, table_attr in TAB_KINDS:
            rows = self.admin.rows(kind)
            self._rows[kind] = rows
            table: QTableWidget = getattr(self, table_attr)
            if kind == "calendar":
                week = {c[0]: c for c in self.service.calendar_rows()}
                cells = [(r.code, r.name, str(week[r.id][4]), f"{week[r.id][3]:g}")
                         for r in rows]
            elif kind == "type":
                cells = [(r.code, r.name, categories.get(r.id, "—")) for r in rows]
            elif kind == "task":
                cells = [(r.code, r.name, self.ctx.tr("master.minutes_value", value=r.extra)
                          if r.extra != "—" else "—") for r in rows]
            else:
                cells = [(r.code, r.name, r.extra) for r in rows]
            table.setRowCount(len(rows))
            for i, (row, values) in enumerate(zip(rows, cells, strict=True)):
                for col, text in enumerate(values):
                    if col == 1 and not row.is_active:
                        text = f"{text}  ({self.ctx.tr('master.archived')})"
                    item = QTableWidgetItem(text)
                    if not row.is_active:
                        item.setForeground(self.palette().color(QPalette.ColorRole.PlaceholderText))
                    table.setItem(i, col, item)
            self._sync_buttons(kind)
        # calendar commands work on the same row order as the other tabs
        self._calendars = [(r.id,) for r in self._rows["calendar"]]

    def _selected(self, kind: str) -> RefRow | None:
        table: QTableWidget = getattr(self, dict(TAB_KINDS)[kind])
        # The selection is the truth; the current row can lag behind it.
        selected = table.selectionModel().selectedRows()
        row = selected[0].row() if selected else table.currentRow()
        rows = self._rows.get(kind, [])
        return rows[row] if 0 <= row < len(rows) else None

    def _sync_buttons(self, kind: str) -> None:
        edit, archive = self._row_buttons[kind]
        row = self._selected(kind)
        edit.setEnabled(self.ctx.can_edit and row is not None)
        archive.setEnabled(self.ctx.can_edit and row is not None)
        archive.setText(self.ctx.tr("master.restore" if row is not None and not row.is_active
                                    else "master.archive"))

    def _edit_selected(self, kind: str) -> None:
        row = self._selected(kind)
        if row is None or not self.ctx.can_edit:
            return
        spec = KINDS[kind]
        tr = self.ctx.tr
        code = QLineEdit(row.code)
        locked = spec.pk_is_code or self.admin.code_in_use(kind, row.id)
        code.setReadOnly(locked)
        if locked:
            code.setToolTip(tr("master.code_locked_tip"))
        fields: list[tuple[str, QWidget]] = [(tr("master.code"), code)]
        editors = {}
        for f in spec.fields:
            value = row.values.get(f.attr)
            if f.kind == "int":
                editor = QSpinBox()
                editor.setRange(f.minimum, f.maximum)
                editor.setValue(int(value or 0))
            else:
                editor = QLineEdit(value or "")
            editors[f.attr] = editor
            fields.append((tr(f.label_key), editor))
        dialog = _Dialog(self.ctx, tr("master.edit"), fields, self)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            values = {a: (e.value() if isinstance(e, QSpinBox) else e.text())
                      for a, e in editors.items()}
            result = self.admin.update(self.ctx.current_user, kind, row.id, values,
                                       code=None if locked else code.text())
            if result.ok:
                self.refresh()
                return
            QMessageBox.warning(self, tr("master.title"),
                                tr(result.error_code or "err.invalid"))

    def _toggle_archive(self, kind: str) -> None:
        row = self._selected(kind)
        if row is None or not self.ctx.can_edit:
            return
        result = self.admin.set_active(self.ctx.current_user, kind, row.id, not row.is_active)
        self._done(result)

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

    def _new_unit(self) -> None:
        code, label_ar, label_en, dimension = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        precision = QSpinBox()
        precision.setRange(0, 6)
        precision.setValue(2)
        tr = self.ctx.tr
        dialog = _Dialog(self.ctx, tr("master.new_unit"), [
            (tr("master.code"), code), (tr("master.name"), label_ar),
            (tr("master.name_en"), label_en), (tr("master.dimension"), dimension),
            (tr("master.precision"), precision)], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._done(self.service.create_unit(self.ctx.current_user, code.text(), label_ar.text(),
                                            label_en.text(), dimension.text(), precision.value()))

    def _new_currency(self) -> None:
        code, name = QLineEdit(), QLineEdit()
        code.setMaxLength(3)
        code.setPlaceholderText("USD")
        minor = QSpinBox()
        minor.setRange(0, 4)
        minor.setValue(2)
        tr = self.ctx.tr
        dialog = _Dialog(self.ctx, tr("master.new_currency"), [
            (tr("master.code"), code), (tr("master.name"), name),
            (tr("master.minor_units"), minor)], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._done(self.service.create_currency(self.ctx.current_user, code.text(), name.text(),
                                                minor.value()))

    def _new_calendar(self) -> None:
        code, name, name_en = QLineEdit(), QLineEdit(), QLineEdit()
        tr = self.ctx.tr
        dialog = _Dialog(self.ctx, tr("master.new_calendar"), [
            (tr("master.code"), code), (tr("master.name"), name),
            (tr("master.name_en"), name_en)], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.service.create_calendar(self.ctx.current_user, code.text(), name.text(),
                                              name_en.text().strip() or None)
        self._done(result)
        if result.ok:
            row = next(i for i, c in enumerate(self._calendars) if c[0] == result.value)
            self.cal_table.setCurrentCell(row, 0)
            self._edit_calendar_week()

    def _edit_calendar_week(self) -> None:
        row = self.cal_table.currentRow()
        if not (0 <= row < len(self._calendars)):
            return
        calendar_id = self._calendars[row][0]
        dialog = CalendarWeekDialog(self.ctx, self.service.calendar_week(calendar_id), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._done(self.service.set_calendar_week(self.ctx.current_user, calendar_id,
                                                  dialog.payload()))

    def _new_warehouse(self) -> None:
        code, name = QLineEdit(), QLineEdit()
        dialog = _Dialog(self.ctx, self.ctx.tr("master.new_warehouse"), [
            (self.ctx.tr("master.code"), code), (self.ctx.tr("master.name"), name)], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.service.create_warehouse(self.ctx.current_user, code.text(), name.text())
        self._done(result)

    def _new_task(self) -> None:
        code, title = QLineEdit(), QLineEdit()
        minutes = QLineEdit()
        dialog = _Dialog(self.ctx, self.ctx.tr("master.new_task"), [
            (self.ctx.tr("master.code"), code), (self.ctx.tr("master.name"), title),
            (self.ctx.tr("master.minutes"), minutes)], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        estimate = int(minutes.text()) if minutes.text().strip().isdigit() else None
        result = self.service.create_task(self.ctx.current_user, code.text(), title.text(),
                                          estimate)
        self._done(result)

    def _done(self, result) -> None:
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("master.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()
