"""Vehicles workshop (UI-007, SPEC 6): fleet list, vehicle profile, odometer, service plans."""
from __future__ import annotations

from PySide6.QtCore import QDate, QDateTime, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
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
from ...application.dto.vehicle import (
    DOC_EXPIRED,
    DOC_SOON,
    FUEL_TYPES,
    VehicleDetail,
    VehicleInput,
)
from ...application.services.asset_service import AssetService
from ...application.services.master_data_service import MasterDataService
from ...application.services.meter_service import MeterService
from ...application.services.pm_service import PMService
from ...application.services.vehicle_service import VehicleService
from ...application.services.work_order_service import WorkOrderService
from ...domain.policies import pm_schedule as sched
from ..theme.tokens import LIGHT
from ..widgets.meter_correction import CorrectionBox
from ..widgets.tables import polish_table, sortable
from .base import BasePage, isolate, make_card, make_title, scrollable, select_row, vbox
from .work_orders import NewWorkOrderDialog

_ALERT_STATES = (sched.DUE, sched.OVERDUE)


def _dialog_buttons(ctx: AppContext, dialog: QDialog) -> QDialogButtonBox:
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
    return buttons


def _optional_date(value: str | None) -> tuple[QCheckBox, QDateEdit]:
    """A date that may be blank: the checkbox says whether it is set."""
    enabled = QCheckBox()
    editor = QDateEdit(QDate.fromString(value, "yyyy-MM-dd") if value
                       else QDate.currentDate().addYears(1))
    editor.setCalendarPopup(True)
    editor.setDisplayFormat("yyyy-MM-dd")
    enabled.setChecked(bool(value))
    editor.setEnabled(bool(value))
    enabled.toggled.connect(editor.setEnabled)
    return enabled, editor


class VehicleDialog(QDialog):
    """Create or edit a vehicle; the odometer start value is asked for on create only."""

    def __init__(self, ctx: AppContext, locations, detail: VehicleDetail | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        tr = ctx.tr
        self.setModal(True)
        self.setMinimumWidth(560)
        outer = QVBoxLayout(self)
        body = QWidget()
        form = QFormLayout(body)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        d = detail
        self.fleet_code = QLineEdit(d.fleet_code if d else "")
        self.plate = QLineEdit(d.plate_number or "" if d else "")
        self.name_ar = QLineEdit(d.name_ar if d else "")
        self.name_en = QLineEdit(d.name_en or "" if d else "")
        self.location = QComboBox()
        for loc in locations:
            self.location.addItem(loc.label(ctx.localizer.is_rtl), loc.id)
        if d:
            self.location.setCurrentIndex(max(0, self.location.findData(d.location_id)))
        self.make = QLineEdit(d.make or "" if d else "")
        self.model = QLineEdit(d.model or "" if d else "")
        self.year = QSpinBox()
        self.year.setRange(0, QDate.currentDate().year() + 1)
        self.year.setSpecialValueText("—")
        self.year.setValue(d.year or 0 if d else 0)
        self.vin = QLineEdit(d.vin or "" if d else "")
        self.fuel = QComboBox()
        self.fuel.addItem("—", None)
        for fuel in FUEL_TYPES:
            self.fuel.addItem(tr(f"value.fuel.{fuel}"), fuel)
        if d and d.fuel_type:
            self.fuel.setCurrentIndex(max(0, self.fuel.findData(d.fuel_type)))
        self.odometer = QLineEdit()
        self.odometer.setPlaceholderText("0")
        self.department = QLineEdit(d.department or "" if d else "")
        self.driver = QLineEdit(d.assigned_driver or "" if d else "")
        self.contact = QLineEdit(d.maintenance_contact or "" if d else "")
        self.has_insurance, self.insurance = _optional_date(d.insurance_expiry if d else None)
        self.has_registration, self.registration = _optional_date(
            d.registration_expiry if d else None)
        self.notes = QPlainTextEdit(d.notes or "" if d else "")
        self.notes.setFixedHeight(64)

        def dated(check: QCheckBox, editor: QDateEdit) -> QWidget:
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(check)
            lay.addWidget(editor, 1)
            return row

        rows = [("veh.fleet_code", self.fleet_code), ("veh.plate", self.plate),
                ("veh.name_ar", self.name_ar), ("veh.name_en", self.name_en),
                ("veh.location", self.location), ("veh.make", self.make),
                ("veh.model", self.model), ("veh.year", self.year), ("veh.vin", self.vin),
                ("veh.fuel", self.fuel)]
        if d is None:
            rows.append(("veh.initial_odometer", self.odometer))
        rows += [("veh.department", self.department), ("veh.driver", self.driver),
                 ("veh.contact", self.contact),
                 ("veh.insurance", dated(self.has_insurance, self.insurance)),
                 ("veh.registration", dated(self.has_registration, self.registration)),
                 ("veh.notes", self.notes)]
        for key, widget in rows:
            form.addRow(QLabel(tr(key)), widget)
        outer.addWidget(scrollable(body), 1)
        self.buttons = _dialog_buttons(ctx, self)
        outer.addWidget(self.buttons)
        self.setWindowTitle(tr("veh.edit" if d else "veh.new"))
        self.resize(600, 640)

    def payload(self) -> VehicleInput:
        def text(widget: QLineEdit) -> str | None:
            return widget.text().strip() or None

        return VehicleInput(
            fleet_code=self.fleet_code.text(), name_ar=self.name_ar.text(),
            location_id=self.location.currentData(), plate_number=text(self.plate),
            name_en=text(self.name_en), make=text(self.make), model=text(self.model),
            year=self.year.value() or None, vin=text(self.vin),
            fuel_type=self.fuel.currentData(), department=text(self.department),
            assigned_driver=text(self.driver), maintenance_contact=text(self.contact),
            insurance_expiry=(self.insurance.date().toString("yyyy-MM-dd")
                              if self.has_insurance.isChecked() else None),
            registration_expiry=(self.registration.date().toString("yyyy-MM-dd")
                                 if self.has_registration.isChecked() else None),
            notes=self.notes.toPlainText().strip() or None,
            initial_odometer=text(self.odometer))


class OdometerDialog(QDialog):
    def __init__(self, ctx: AppContext, current: str | None, unit: str,
                 parent: QWidget | None = None, last=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(380)
        form = QFormLayout(self)
        self.value = QLineEdit()
        self.value.setPlaceholderText(current or "0")
        self.when = QDateEdit(QDate.currentDate())
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("yyyy-MM-dd")
        self.notes = QLineEdit()
        form.addRow(QLabel(ctx.tr("veh.odometer_value", unit=unit)), self.value)
        form.addRow(QLabel(ctx.tr("assets.reading.date")), self.when)
        form.addRow(QLabel(ctx.tr("assets.reading.notes")), self.notes)
        hint = QLabel(ctx.tr("veh.odometer_hint", value=current or "—"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form.addRow(hint)
        self.correction = CorrectionBox(ctx, last)
        form.addRow(self.correction)
        self.buttons = _dialog_buttons(ctx, self)
        form.addRow(self.buttons)
        self.setWindowTitle(ctx.tr("veh.add_odometer"))

    def payload(self) -> tuple[str, str, str | None]:
        # Today's reading carries the current time so it sorts after earlier ones that day.
        day = self.when.date()
        time = QDateTime.currentDateTime().time() if day == QDate.currentDate() else None
        stamp = day.toString("yyyy-MM-dd") + "T" + (time.toString("HH:mm:ss") if time
                                                       else "12:00:00")
        return self.value.text().strip(), stamp, self.notes.text().strip() or None


class ServicePlanDialog(QDialog):
    """'Every N km OR every M months, whichever comes first' (SPEC 6.3)."""

    def __init__(self, ctx: AppContext, unit: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        self.title = QComboBox()
        self.title.setEditable(True)
        for key in ("oil", "gearbox", "brakes", "belts", "cooling", "battery", "tyres",
                    "alignment", "ac", "general", "documents"):
            self.title.addItem(ctx.tr(f"veh.service.{key}"))
        self.every_km = QLineEdit()
        self.every_km.setPlaceholderText("10000")
        self.every_months = QSpinBox()
        self.every_months.setRange(0, 60)
        self.every_months.setSpecialValueText("—")
        self.every_months.setValue(6)
        form.addRow(QLabel(ctx.tr("veh.plan.title")), self.title)
        form.addRow(QLabel(ctx.tr("veh.plan.every_km", unit=unit)), self.every_km)
        form.addRow(QLabel(ctx.tr("veh.plan.every_months")), self.every_months)
        hint = QLabel(ctx.tr("veh.plan.hint"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form.addRow(hint)
        self.buttons = _dialog_buttons(ctx, self)
        form.addRow(self.buttons)
        self.setWindowTitle(ctx.tr("veh.add_plan"))

    def payload(self) -> tuple[str, str | None, int | None]:
        return (self.title.currentText().strip(), self.every_km.text().strip() or None,
                self.every_months.value() or None)


class VehiclesPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.vehicles = VehicleService(ctx.db)
        self.masters = MasterDataService(ctx.db)
        self._rows: list = []
        self._detail: VehicleDetail | None = None
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
        self.alerts_only = QCheckBox()
        self.alerts_only.toggled.connect(lambda _c: self.refresh())
        self.btn_new = QPushButton()
        self.btn_new.setObjectName("primary")
        self.btn_new.clicked.connect(self._new)
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        bar.addWidget(self.search)
        bar.addWidget(self.alerts_only)
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
        polish_table(self.table, lambda: self.ctx.tr("veh.empty"))
        sortable(self.table, self)  # header click sorts (F-14)
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
        self.tabs.addTab(self._build_overview(), "")
        self.tabs.addTab(self._build_plans(), "")
        self.tabs.addTab(self._build_history(), "")
        self.tabs.addTab(self._build_odometer(), "")
        actions = QHBoxLayout()
        self.btn_edit = QPushButton()
        self.btn_edit.clicked.connect(self._edit)
        self.btn_wo = QPushButton()
        self.btn_wo.clicked.connect(self._new_work_order)
        actions.addStretch(1)
        actions.addWidget(self.btn_wo)
        actions.addWidget(self.btn_edit)
        right_lay.addWidget(self.head)
        right_lay.addWidget(self.meta)
        right_lay.addWidget(self.tabs, 1)
        right_lay.addLayout(actions)
        split.addWidget(right)
        split.setSizes([720, 520])
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)
        self._set_detail_enabled(False)

    def _build_overview(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(12, 12, 12, 12)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.ov: dict[str, QLabel] = {}
        self.ov_labels: dict[str, QLabel] = {}
        for key in ("fleet_code", "plate", "name_ar", "location", "make", "model", "year",
                    "vin", "fuel", "odometer", "department", "driver", "contact",
                    "insurance", "registration", "notes"):
            label = QLabel()
            label.setObjectName("fieldLabel")
            value = QLabel("—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.ov[key], self.ov_labels[key] = value, label
            form.addRow(label, value)
        return scrollable(page)

    def _build_plans(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.plans = QTableWidget(0, 4)
        self.plans.verticalHeader().setVisible(False)
        self.plans.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.plans.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        polish_table(self.plans, lambda: self.ctx.tr("veh.no_plans"))
        bar = QHBoxLayout()
        self.btn_plan = QPushButton()
        self.btn_plan.clicked.connect(self._add_plan)
        self.btn_generate = QPushButton()
        self.btn_generate.clicked.connect(self._generate)
        bar.addWidget(self.btn_generate)
        bar.addStretch(1)
        bar.addWidget(self.btn_plan)
        lay.addWidget(self.plans, 1)
        lay.addLayout(bar)
        return page

    def _build_history(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.history = QTableWidget(0, 4)
        self.history.verticalHeader().setVisible(False)
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        polish_table(self.history, lambda: self.ctx.tr("veh.no_history"))
        lay.addWidget(self.history)
        return page

    def _build_odometer(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.readings = QTableWidget(0, 2)
        self.readings.verticalHeader().setVisible(False)
        self.readings.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        polish_table(self.readings, lambda: self.ctx.tr("common.no_data"))
        bar = QHBoxLayout()
        self.btn_odometer = QPushButton()
        self.btn_odometer.clicked.connect(self._add_odometer)
        bar.addStretch(1)
        bar.addWidget(self.btn_odometer)
        lay.addWidget(self.readings, 1)
        lay.addLayout(bar)
        return page

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("nav.vehicles"))
        self.search.setPlaceholderText(tr("veh.search_hint"))
        self.alerts_only.setText(tr("veh.alerts_only"))
        self.btn_new.setText(tr("veh.new"))
        self.btn_refresh.setText(tr("common.refresh"))
        self.btn_edit.setText(tr("veh.edit"))
        self.btn_wo.setText(tr("wo.new"))
        self.btn_plan.setText(tr("veh.add_plan"))
        self.btn_generate.setText(tr("pm.generate"))
        self.btn_odometer.setText(tr("veh.add_odometer"))
        for i, key in enumerate(("veh.tab.overview", "veh.tab.plans", "veh.tab.history",
                                 "veh.tab.odometer")):
            self.tabs.setTabText(i, tr(key))
        for key, label in self.ov_labels.items():
            label.setText(tr("veh.odometer" if key == "odometer" else f"veh.{key}"))
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "veh.fleet_code", "veh.plate", "veh.name_ar", "veh.odometer", "veh.next_service",
            "veh.alerts")])
        self.plans.setHorizontalHeaderLabels([tr(k) for k in (
            "veh.plan.title", "pm.next_due", "pm.state", "pm.code")])
        self.history.setHorizontalHeaderLabels([tr(k) for k in (
            "wo.number", "wo.form.title_label", "wo.status", "wo.form.due")])
        self.readings.setHorizontalHeaderLabels([tr("assets.reading.date"),
                                                 tr("assets.reading.value")])
        self.refresh()

    # ---------------- data ----------------
    def refresh(self) -> None:
        rtl = self.ctx.localizer.is_rtl
        self._rows = self.vehicles.list(query=self.search.text(),
                                        alerts_only=self.alerts_only.isChecked())
        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            odometer = (f"{self._fmt(row.odometer)} {row.odometer_unit}" if row.odometer
                        else "—")
            cells = (row.fleet_code, row.plate_number or "—", row.name(rtl), odometer,
                     row.next_service or "—", self._alert_text(row))
            for col, text in enumerate(cells):
                # Numbers with units and dates keep their own direction inside Arabic rows.
                item = QTableWidgetItem(isolate(text) if col in (3, 4) else text)
                item.setToolTip(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.asset_id)
                if col == 5 and text != "—":
                    severe = (row.service_state in _ALERT_STATES
                              or row.doc_state == DOC_EXPIRED)
                    item.setForeground(QColor(LIGHT["danger" if severe else "warning"]))
                self.table.setItem(i, col, item)
        selected = self._detail.asset_id if self._detail else None
        index = next((i for i, r in enumerate(self._rows) if r.asset_id == selected), 0)
        if self._rows:
            self.table.setCurrentCell(index, 0)
            self._on_select()
        else:
            self._detail = None
            self._set_detail_enabled(False)
        self.btn_new.setEnabled(self.ctx.can_edit)

    def select_record(self, asset_id: str) -> bool:
        self.search.clear()
        self.alerts_only.setChecked(False)
        self.refresh()
        if not select_row(self.table, self._rows, asset_id, attr="asset_id"):
            return False
        self._on_select()
        return True

    def _alert_text(self, row) -> str:
        tr = self.ctx.tr
        parts = []
        if row.service_state in (sched.DUE_SOON, sched.DUE, sched.OVERDUE):
            parts.append(tr(f"pm.state.{row.service_state}"))
        if row.doc_state == DOC_EXPIRED:
            parts.append(tr("veh.doc.expired"))
        elif row.doc_state == DOC_SOON:
            parts.append(tr("veh.doc.soon"))
        return " · ".join(parts) or "—"

    @staticmethod
    def _fmt(value: str | None) -> str:
        if not value:
            return "—"
        try:
            number = float(value)
        except ValueError:
            return value
        return f"{number:,.0f}" if number == int(number) else f"{number:,}"

    def _on_select(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._rows)):
            return
        self._detail = self.vehicles.detail(self._rows[row].asset_id)
        self._render()

    def _set_detail_enabled(self, enabled: bool) -> None:
        for widget in (self.btn_edit, self.btn_wo, self.btn_plan, self.btn_generate,
                       self.btn_odometer, self.tabs):
            widget.setEnabled(enabled and (widget is self.tabs or self.ctx.can_edit))
        if not enabled:
            self.head.setText(self.ctx.tr("veh.select"))
            self.meta.setText("")

    def _render(self) -> None:
        d = self._detail
        self._set_detail_enabled(d is not None)
        if d is None:
            return
        tr = self.ctx.tr
        rtl = self.ctx.localizer.is_rtl
        name = (d.name_ar if rtl else d.name_en) or d.name_ar
        self.head.setText(f"{d.fleet_code} — {name}")
        plate = f" · {d.plate_number}" if d.plate_number else ""
        odometer = (f" · {isolate(self._fmt(d.odometer) + ' ' + d.odometer_unit)}"
                    if d.odometer else "")
        self.meta.setText(f"{tr(f'value.status.{d.status}')}{plate}{odometer}")

        def doc(value: str | None, state: str | None) -> str:
            if not value:
                return "—"
            suffix = {DOC_EXPIRED: tr("veh.doc.expired"), DOC_SOON: tr("veh.doc.soon")}
            return f"{value}  ({suffix[state]})" if state in suffix else value

        values = {
            "fleet_code": d.fleet_code, "plate": d.plate_number or "—", "name_ar": d.name_ar,
            "location": d.location or "—", "make": d.make or "—", "model": d.model or "—",
            "year": str(d.year) if d.year else "—", "vin": d.vin or "—",
            "fuel": tr(f"value.fuel.{d.fuel_type}") if d.fuel_type else "—",
            "odometer": (f"{self._fmt(d.odometer)} {d.odometer_unit}" if d.odometer
                         else "—"),
            "department": d.department or "—", "driver": d.assigned_driver or "—",
            "contact": d.maintenance_contact or "—",
            "insurance": doc(d.insurance_expiry, d.insurance_state),
            "registration": doc(d.registration_expiry, d.registration_state),
            "notes": d.notes or "—",
        }
        side = Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
        for key, text in values.items():
            self.ov[key].setText(isolate(text))
            self.ov[key].setAlignment(Qt.AlignmentFlag.AlignAbsolute | side
                                      | Qt.AlignmentFlag.AlignVCenter)

        self.plans.setRowCount(len(d.plans))
        for i, plan in enumerate(d.plans):
            due = " / ".join(filter(None, (
                f"{self._fmt(plan.next_due_meter)} {d.odometer_unit}"
                if plan.next_due_meter else None, plan.next_due_date))) or "—"
            cells = (plan.title, due, tr(f"pm.state.{plan.state}"), plan.code)
            for col, text in enumerate(cells):
                item = QTableWidgetItem(isolate(text) if col == 1 else text)
                item.setToolTip(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, plan.id)
                if col == 2 and plan.state in _ALERT_STATES + (sched.DUE_SOON,):
                    item.setForeground(QColor(LIGHT[
                        "danger" if plan.state in _ALERT_STATES else "warning"]))
                self.plans.setItem(i, col, item)
        if d.plans:
            self.plans.setCurrentCell(0, 0)  # selectRow() is a no-op under RTL

        self.history.setRowCount(len(d.work_orders))
        for i, wo in enumerate(d.work_orders):
            cells = (wo.number, wo.title, tr(f"value.wo.{wo.status}"), wo.due_at or "—")
            for col, text in enumerate(cells):
                self.history.setItem(i, col, QTableWidgetItem(text))

        self.readings.setRowCount(len(d.readings))
        for i, reading in enumerate(d.readings):
            self.readings.setItem(i, 0, QTableWidgetItem(reading.reading_at[:16]
                                                         .replace("T", " ")))
            text = isolate(f"{self._fmt(reading.value)} {d.odometer_unit}")
            if reading.quality == "rejected":  # replaced by a documented correction
                text += f"  ({self.ctx.tr('meter.rejected')})"
            self.readings.setItem(i, 1, QTableWidgetItem(text))

    # ---------------- commands ----------------
    def _warn(self, code: str | None) -> None:
        QMessageBox.warning(self, self.ctx.tr("nav.vehicles"),
                            self.ctx.tr(code or "err.invalid"))

    def _new(self) -> None:
        if not self.ctx.can_edit:
            return
        locations = self.masters.locations()
        if not locations:
            QMessageBox.information(self, self.ctx.tr("assets.new_location"),
                                    self.ctx.tr("assets.new_location_hint"))
            return
        dialog = VehicleDialog(self.ctx, locations, parent=self)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            result = self.vehicles.create(self.ctx.current_user, dialog.payload())
            if result.ok:
                self._detail = self.vehicles.detail(result.value)
                self.refresh()
                return
            self._warn(result.error_code)  # keep what was typed and let the user fix it

    def _edit(self) -> None:
        d = self._detail
        if d is None or not self.ctx.can_edit:
            return
        dialog = VehicleDialog(self.ctx, self.masters.locations(), d, parent=self)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            result = self.vehicles.update(self.ctx.current_user, d.asset_id, dialog.payload())
            if result.ok:
                self.refresh()
                return
            self._warn(result.error_code)

    def _add_odometer(self) -> None:
        d = self._detail
        if d is None:
            return
        last = MeterService(self.ctx.db).last_reading(d.meter_id) if d.meter_id else None
        dialog = OdometerDialog(self.ctx, self._fmt(d.odometer) if d.odometer else None,
                                d.odometer_unit, self, last=last)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value, stamp, notes = dialog.payload()
        result = self.vehicles.add_odometer(
            self.ctx.current_user, d.asset_id, value, stamp, notes,
            correction_reason=dialog.correction.correction_reason())
        if not result.ok:
            self._warn(result.error_code)
            return
        self.refresh()

    def _add_plan(self) -> None:
        d = self._detail
        if d is None:
            return
        dialog = ServicePlanDialog(self.ctx, d.odometer_unit, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        title, every_km, every_months = dialog.payload()
        result = self.vehicles.add_service_plan(self.ctx.current_user, d.asset_id, title,
                                                every_km, every_months)
        if not result.ok:
            self._warn(result.error_code)
            return
        self.refresh()
        self.tabs.setCurrentIndex(1)

    def _generate(self) -> None:
        row = self.plans.currentRow()
        if self._detail is None or not (0 <= row < len(self._detail.plans)):
            return
        plan = self._detail.plans[row]
        result = PMService(self.ctx.db).generate(self.ctx.current_user, plan.id)
        if not result.ok:
            self._warn(result.error_code)
            return
        QMessageBox.information(self, self.ctx.tr("nav.vehicles"),
                                self.ctx.tr("veh.wo_created"))
        self.refresh()

    def _new_work_order(self) -> None:
        d = self._detail
        if d is None or not self.ctx.can_edit:
            return
        service = WorkOrderService(self.ctx.db)
        dialog = NewWorkOrderDialog(self.ctx, service, AssetService(self.ctx.db), self)
        dialog.asset.setCurrentIndex(max(0, dialog.asset.findData(d.asset_id)))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = service.create(self.ctx.current_user, **dialog.payload())
        if not result.ok:
            self._warn(result.error_code)
            return
        self.refresh()
        self.tabs.setCurrentIndex(2)
