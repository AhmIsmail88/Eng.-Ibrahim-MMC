"""Asset registry screen: list + profile tabs + create/edit dialog (SPEC 5)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
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
from ...application.dto.asset import AssetDetail, AssetInput
from ...application.services.asset_service import AssetService
from ...application.services.attachment_service import AttachmentService
from ...application.services.import_service import ImportService
from ...application.services.inventory_service import InventoryService
from ...application.services.master_data_service import MasterDataService
from ...application.services.meter_service import MeterService
from ...infrastructure.database.orm_models.operations import (
    CONDITION,
    CRITICALITY,
    METER_TYPE,
    OPERATIONAL_STATUS,
    STRATEGY,
)
from ...infrastructure.exports.qr_labels import write_sheet
from .base import BasePage, make_card, make_title, set_ltr_value, vbox


class AssetDialog(QDialog):
    def __init__(self, ctx: AppContext, assets: AssetService, masters: MasterDataService,
                 detail: AssetDetail | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.assets = assets
        self.masters = masters
        self.detail = detail
        self.setModal(True)
        self.setMinimumWidth(560)
        self._build()
        self.retranslate()
        if detail:
            self._load(detail)

    # ---------------- UI ----------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)
        self.code, self.name_ar, self.name_en = QLineEdit(), QLineEdit(), QLineEdit()
        self.category, self.type, self.location = QComboBox(), QComboBox(), QComboBox()
        self.parent = QComboBox()
        self.criticality, self.status = QComboBox(), QComboBox()
        self.condition, self.strategy = QComboBox(), QComboBox()
        self.meter_type, self.meter_unit = QComboBox(), QComboBox()
        self.manufacturer, self.model, self.serial = QLineEdit(), QLineEdit(), QLineEdit()
        self.commissioned = QLineEdit()
        self.commissioned.setPlaceholderText("YYYY-MM-DD")
        self.purchased = QLineEdit()
        self.purchased.setPlaceholderText("YYYY-MM-DD")
        self.warranty = QLineEdit()
        self.warranty.setPlaceholderText("YYYY-MM-DD")
        self.purchase_cost, self.replacement_cost = QDoubleSpinBox(), QDoubleSpinBox()
        for box in (self.purchase_cost, self.replacement_cost):
            box.setMaximum(1_000_000_000)
            box.setDecimals(2)
            box.setGroupSeparatorShown(True)
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(70)

        self.lbl_code, self.lbl_name_ar, self.lbl_name_en = QLabel(), QLabel(), QLabel()
        self.lbl_category, self.lbl_type, self.lbl_location = QLabel(), QLabel(), QLabel()
        self.lbl_parent, self.lbl_criticality, self.lbl_status = QLabel(), QLabel(), QLabel()
        self.lbl_condition, self.lbl_strategy = QLabel(), QLabel()
        self.lbl_meter_type, self.lbl_meter_unit = QLabel(), QLabel()
        self.lbl_man, self.lbl_model, self.lbl_serial = QLabel(), QLabel(), QLabel()
        self.lbl_comm, self.lbl_purch, self.lbl_warranty = QLabel(), QLabel(), QLabel()
        self.lbl_pcost, self.lbl_rcost, self.lbl_notes = QLabel(), QLabel(), QLabel()

        for pair in (
            (self.lbl_code, self.code), (self.lbl_name_ar, self.name_ar),
            (self.lbl_name_en, self.name_en), (self.lbl_category, self.category),
            (self.lbl_type, self.type), (self.lbl_location, self.location),
            (self.lbl_parent, self.parent), (self.lbl_criticality, self.criticality),
            (self.lbl_status, self.status), (self.lbl_condition, self.condition),
            (self.lbl_strategy, self.strategy), (self.lbl_meter_type, self.meter_type),
            (self.lbl_meter_unit, self.meter_unit), (self.lbl_man, self.manufacturer),
            (self.lbl_model, self.model), (self.lbl_serial, self.serial),
            (self.lbl_comm, self.commissioned), (self.lbl_purch, self.purchased),
            (self.lbl_warranty, self.warranty), (self.lbl_pcost, self.purchase_cost),
            (self.lbl_rcost, self.replacement_cost), (self.lbl_notes, self.notes),
        ):
            form.addRow(pair[0], pair[1])
        outer.addLayout(form)

        self.error = QLabel()
        self.error.setObjectName("formError")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        outer.addWidget(self.error)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        self._fill_combos()
        self.category.currentIndexChanged.connect(self._reload_types)

    def _fill_combos(self) -> None:
        arabic = self.ctx.localizer.is_rtl
        self._cats = self.masters.categories()
        self._locs = self.masters.locations()
        self._units = self.masters.units()
        for combo, values, tr_prefix in (
            (self.criticality, CRITICALITY, "value.criticality"),
            (self.status, OPERATIONAL_STATUS, "value.status"),
            (self.condition, CONDITION, "value.condition"),
            (self.strategy, STRATEGY, "value.strategy"),
            (self.meter_type, METER_TYPE, "value.meter"),
        ):
            combo.clear()
            for value in values:
                combo.addItem(self.ctx.tr(f"{tr_prefix}.{value}"), value)
        self.category.clear()
        for c in self._cats:
            self.category.addItem(c.label(arabic), c.id)
        self.location.clear()
        for loc in self._locs:
            self.location.addItem(loc.label(arabic), loc.id)
        self.meter_unit.clear()
        self.meter_unit.addItem(self.ctx.tr("assets.form.meter_unit"), "")
        for u in self._units:
            self.meter_unit.addItem(u.label(arabic), u.id)
        self._reload_types()
        self._reload_parents()

    def _reload_types(self) -> None:
        arabic = self.ctx.localizer.is_rtl
        self.type.clear()
        self.type.addItem("—", None)
        category_id = self.category.currentData()
        if category_id:
            for t in self.masters.types(category_id):
                self.type.addItem(t.label(arabic), t.id)

    def _reload_parents(self) -> None:
        arabic = self.ctx.localizer.is_rtl
        self.parent.clear()
        self.parent.addItem("—", None)
        for row in self.assets.list(include_archived=False):
            if self.detail and row.id == self.detail.id:
                continue
            self.parent.addItem(f"{row.code} — {row.name(arabic)}", row.id)

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.setWindowTitle(tr("assets.form.edit_title" if self.detail
                               else "assets.form.new_title"))
        for label, key in (
            (self.lbl_code, "assets.form.code"), (self.lbl_name_ar, "assets.form.name_ar"),
            (self.lbl_name_en, "assets.form.name_en"),
            (self.lbl_category, "assets.form.category"), (self.lbl_type, "assets.form.type"),
            (self.lbl_location, "assets.form.location"),
            (self.lbl_parent, "assets.form.parent"),
            (self.lbl_criticality, "assets.form.criticality"),
            (self.lbl_status, "assets.form.status"),
            (self.lbl_condition, "assets.form.condition"),
            (self.lbl_strategy, "assets.form.strategy"),
            (self.lbl_meter_type, "assets.form.meter_type"),
            (self.lbl_meter_unit, "assets.form.meter_unit"),
            (self.lbl_man, "assets.form.manufacturer"), (self.lbl_model, "assets.form.model"),
            (self.lbl_serial, "assets.form.serial"),
            (self.lbl_comm, "assets.form.commissioning"),
            (self.lbl_purch, "assets.form.purchase_date"),
            (self.lbl_warranty, "assets.form.warranty"),
            (self.lbl_pcost, "assets.form.purchase_cost"),
            (self.lbl_rcost, "assets.form.replacement_cost"),
            (self.lbl_notes, "assets.form.notes"),
        ):
            label.setText(tr(key))
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("common.cancel"))

    def _load(self, d: AssetDetail) -> None:
        self.code.setText(d.code)
        self.name_ar.setText(d.name_ar)
        self.name_en.setText(d.name_en or "")
        self._set_combo(self.category, d.category_id)
        self._reload_types()
        self._set_combo(self.type, d.type_id)
        self._set_combo(self.location, d.location_id)
        self._reload_parents()
        self._set_combo(self.parent, d.parent_asset_id)
        for combo, value in ((self.criticality, d.criticality), (self.status, d.operational_status),
                             (self.condition, d.asset_condition),
                             (self.strategy, d.maintenance_strategy),
                             (self.meter_type, d.meter_type)):
            self._set_combo(combo, value)
        self._set_combo(self.meter_unit, d.default_meter_unit or "")
        self.manufacturer.setText(d.manufacturer or "")
        self.model.setText(d.model or "")
        self.serial.setText(d.serial_number or "")
        self.commissioned.setText(d.commissioning_date or "")
        self.purchased.setText(d.purchase_date or "")
        self.warranty.setText(d.warranty_expiry or "")
        if d.purchase_cost_minor is not None:
            self.purchase_cost.setValue(d.purchase_cost_minor / 100)
        if d.replacement_cost_minor is not None:
            self.replacement_cost.setValue(d.replacement_cost_minor / 100)
        self.notes.setPlainText(d.notes or "")

    @staticmethod
    def _set_combo(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def payload(self) -> AssetInput:
        def money(box: QDoubleSpinBox) -> int | None:
            return int(round(box.value() * 100)) if box.value() > 0 else None

        currency = self.ctx.settings.get("currency_code", "EGP")
        return AssetInput(
            asset_code=self.code.text(),
            asset_name_ar=self.name_ar.text(),
            asset_name_en=self.name_en.text().strip() or None,
            category_id=self.category.currentData() or "",
            type_id=self.type.currentData(),
            location_id=self.location.currentData() or "",
            parent_asset_id=self.parent.currentData(),
            manufacturer=self.manufacturer.text().strip() or None,
            model=self.model.text().strip() or None,
            serial_number=self.serial.text().strip() or None,
            criticality=self.criticality.currentData(),
            operational_status=self.status.currentData(),
            asset_condition=self.condition.currentData(),
            maintenance_strategy=self.strategy.currentData(),
            meter_type=self.meter_type.currentData(),
            default_meter_unit=self.meter_unit.currentData() or None,
            commissioning_date=self.commissioned.text().strip() or None,
            purchase_date=self.purchased.text().strip() or None,
            purchase_cost_minor=money(self.purchase_cost),
            replacement_cost_minor=money(self.replacement_cost),
            currency_code=currency if money(self.purchase_cost) else None,
            warranty_expiry=self.warranty.text().strip() or None,
            notes=self.notes.toPlainText().strip() or None,
        )

    def _save(self) -> None:
        data = self.payload()
        result = (self.assets.update(self.ctx.current_user, self.detail.id, data)
                  if self.detail else self.assets.create(self.ctx.current_user, data))
        if not result.ok:
            self.error.setText(self.ctx.tr(result.error_code or "err.invalid"))
            self.error.setVisible(True)
            return
        self.accept()


class ReadingDialog(QDialog):
    def __init__(self, ctx: AppContext, meters, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setModal(True)
        self.setMinimumWidth(360)
        form = QFormLayout(self)
        self.meter = QComboBox()
        for m in meters:
            self.meter.addItem(f"{m.code} ({m.unit_code})", m.id)
        self.value = QLineEdit()
        self.when = QDateEdit(QDate.currentDate())
        self.when.setCalendarPopup(True)
        self.notes = QLineEdit()
        self.lbl_meter = QLabel(ctx.tr("assets.meter.name"))
        self.lbl_value = QLabel(ctx.tr("assets.reading.value"))
        self.lbl_when = QLabel(ctx.tr("assets.reading.date"))
        self.lbl_notes = QLabel(ctx.tr("assets.reading.notes"))
        form.addRow(self.lbl_meter, self.meter)
        form.addRow(self.lbl_value, self.value)
        form.addRow(self.lbl_when, self.when)
        form.addRow(self.lbl_notes, self.notes)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        self.setWindowTitle(ctx.tr("assets.reading.title"))

    def payload(self) -> tuple[str, str, str, str | None]:
        return (self.meter.currentData(), self.value.text(),
                self.when.date().toString("yyyy-MM-dd"), self.notes.text().strip() or None)


class AssetsPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.assets = AssetService(ctx.db)
        self.masters = MasterDataService(ctx.db)
        self.meters = MeterService(ctx.db)
        self.inventory = InventoryService(ctx.db)
        self.importer = ImportService(ctx.db)
        self.attachments = AttachmentService(ctx.db, ctx.paths.root)
        self._rows: list = []
        self._detail: AssetDetail | None = None
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
        self.search.returnPressed.connect(self.refresh)
        self.search.textChanged.connect(lambda _t: self._apply_filter())
        self.cat = QComboBox()
        self.cat.currentIndexChanged.connect(lambda _i: self.refresh())
        self.status = QComboBox()
        self.status.currentIndexChanged.connect(lambda _i: self.refresh())
        self.archived = QCheckBox()
        self.archived.stateChanged.connect(lambda _s: self.refresh())
        self.btn_new = QPushButton()
        self.btn_new.clicked.connect(self._new)
        self.btn_import = QPushButton()
        self.btn_import.clicked.connect(self._import)
        self.btn_qr = QPushButton()
        self.btn_qr.clicked.connect(self._qr_sheet)
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        for w in (self.search, self.cat, self.status, self.archived):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(self.btn_new)
        bar.addWidget(self.btn_import)
        bar.addWidget(self.btn_qr)
        bar.addWidget(self.btn_refresh)
        lay.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = make_card()
        left_lay = QVBoxLayout(left)
        self.table = QTableWidget(0, 6)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.currentCellChanged.connect(lambda *_a: self._on_select())
        left_lay.addWidget(self.table)
        split.addWidget(left)

        right = make_card()
        right_lay = QVBoxLayout(right)
        self.detail_title = QLabel()
        self.detail_title.setObjectName("pageTitle")
        self.detail_hint = QLabel()
        self.detail_hint.setObjectName("hint")
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview(), "")
        self.tabs.addTab(self._build_technical(), "")
        self.tabs.addTab(self._build_meters(), "")
        self.tabs.addTab(self._build_parts(), "")
        self.tabs.addTab(self._build_attachments(), "")
        self.tabs.addTab(self._build_history(), "")
        actions = QHBoxLayout()
        self.btn_edit = QPushButton()
        self.btn_edit.clicked.connect(self._edit)
        self.btn_archive = QPushButton()
        self.btn_archive.clicked.connect(self._toggle_archive)
        actions.addStretch(1)
        actions.addWidget(self.btn_edit)
        actions.addWidget(self.btn_archive)
        right_lay.addWidget(self.detail_title)
        right_lay.addWidget(self.detail_hint)
        right_lay.addWidget(self.tabs, 1)
        right_lay.addLayout(actions)
        split.addWidget(right)
        split.setSizes([640, 560])
        lay.addWidget(split, 1)

        self._set_detail_enabled(False)

    def _build_overview(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.ov: dict[str, QLabel] = {}
        for key in ("code", "name_ar", "name_en", "category", "type", "location", "parent",
                    "criticality", "status", "condition", "strategy", "manufacturer",
                    "model", "serial", "commissioning", "purchase_date", "purchase_cost",
                    "replacement_cost", "warranty", "notes"):
            label = QLabel()
            value = QLabel("—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.ov[key] = value
            form.addRow(label, value)
            setattr(self, f"ovl_{key}", label)
        return page

    def _build_technical(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.specs = QTableWidget(0, 2)
        self.specs.verticalHeader().setVisible(False)
        self.specs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.specs.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.btn_spec = QPushButton()
        self.btn_spec.clicked.connect(self._add_spec)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(self.btn_spec)
        lay.addWidget(self.specs, 1)
        lay.addLayout(bar)
        return page

    def _build_meters(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.meter_table = QTableWidget(0, 4)
        self.meter_table.verticalHeader().setVisible(False)
        self.meter_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.meter_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.btn_reading = QPushButton()
        self.btn_reading.clicked.connect(self._add_reading)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(self.btn_reading)
        lay.addWidget(self.meter_table, 1)
        lay.addLayout(bar)
        return page

    def _build_parts(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.parts_table = QTableWidget(0, 7)
        self.parts_table.verticalHeader().setVisible(False)
        self.parts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.parts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lay.addWidget(self.parts_table)
        return page

    def _build_attachments(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.attach_table = QTableWidget(0, 3)
        self.attach_table.verticalHeader().setVisible(False)
        self.attach_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.attach_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        bar = QHBoxLayout()
        self.btn_attach = QPushButton()
        self.btn_attach.clicked.connect(self._add_attachment)
        self.btn_attach_open = QPushButton()
        self.btn_attach_open.clicked.connect(self._open_attachment)
        bar.addWidget(self.btn_attach)
        bar.addWidget(self.btn_attach_open)
        bar.addStretch(1)
        lay.addWidget(self.attach_table, 1)
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

    # ---------------- i18n ----------------
    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("assets.title"))
        self.search.setPlaceholderText(tr("assets.search_hint"))
        self.btn_new.setText(tr("assets.new"))
        self.btn_import.setText(tr("assets.import"))
        self.btn_qr.setText(tr("assets.qr"))
        self.btn_refresh.setText(tr("common.refresh"))
        self.archived.setText(tr("assets.include_archived"))
        self.btn_edit.setText(tr("assets.form.edit_title"))
        self.btn_spec.setText(tr("assets.spec.add"))
        self.btn_reading.setText(tr("assets.meter.add"))
        self.tabs.setTabText(0, tr("assets.tab.overview"))
        self.tabs.setTabText(1, tr("assets.tab.technical"))
        self.tabs.setTabText(2, tr("assets.tab.meters"))
        self.tabs.setTabText(3, tr("assets.tab.parts"))
        self.tabs.setTabText(4, tr("assets.tab.attachments"))
        self.tabs.setTabText(5, tr("assets.tab.history"))
        self.btn_attach.setText(tr("attachments.add"))
        self.btn_attach_open.setText(tr("attachments.open"))
        self.attach_table.setHorizontalHeaderLabels([tr(k) for k in (
            "attachments.name", "attachments.size", "attachments.date")])
        self.detail_title.setText(tr("assets.select_hint") if self._detail is None
                                  else f"{self._detail.code} — {self._detail.name_ar}")
        self.detail_hint.setText("" if self._detail else tr("assets.select_hint"))
        for key, label in (
            ("code", "assets.col.code"), ("name_ar", "assets.form.name_ar"),
            ("name_en", "assets.form.name_en"), ("category", "assets.form.category"),
            ("type", "assets.form.type"), ("location", "assets.form.location"),
            ("parent", "assets.form.parent"), ("criticality", "assets.form.criticality"),
            ("status", "assets.form.status"), ("condition", "assets.form.condition"),
            ("strategy", "assets.form.strategy"),
            ("manufacturer", "assets.form.manufacturer"), ("model", "assets.form.model"),
            ("serial", "assets.form.serial"),
            ("commissioning", "assets.form.commissioning"),
            ("purchase_date", "assets.form.purchase_date"),
            ("purchase_cost", "assets.form.purchase_cost"),
            ("replacement_cost", "assets.form.replacement_cost"),
            ("warranty", "assets.form.warranty"), ("notes", "assets.form.notes"),
        ):
            getattr(self, f"ovl_{key}").setText(tr(label))
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "assets.col.code", "assets.col.name", "assets.col.category",
            "assets.col.location", "assets.col.status", "assets.col.criticality")])
        self.specs.setHorizontalHeaderLabels([tr("assets.spec.key"), tr("assets.spec.value")])
        self.meter_table.setHorizontalHeaderLabels([tr(k) for k in (
            "assets.meter.name", "assets.meter.kind", "assets.meter.latest", "")])
        self.history.setHorizontalHeaderLabels([tr(k) for k in (
            "assets.history.kind", "assets.history.at", "assets.history.title")])
        self.parts_table.setHorizontalHeaderLabels([tr(k) for k in (
            "parts.col.part", "parts.col.qty", "parts.col.value", "parts.col.date",
            "parts.col.technician", "parts.col.wo", "parts.col.supplier")])
        self._reload_filters()
        self._apply_filter()

    def _reload_filters(self) -> None:
        arabic = self.ctx.localizer.is_rtl
        current = self.cat.currentData()
        self.cat.blockSignals(True)
        self.cat.clear()
        self.cat.addItem(self.ctx.tr("assets.all"), None)
        for c in self.masters.categories():
            self.cat.addItem(c.label(arabic), c.id)
        self._combo_select(self.cat, current)
        self.cat.blockSignals(False)
        current = self.status.currentData()
        self.status.blockSignals(True)
        self.status.clear()
        self.status.addItem(self.ctx.tr("assets.all"), None)
        for s in OPERATIONAL_STATUS:
            self.status.addItem(self.ctx.tr(f"value.status.{s}"), s)
        self._combo_select(self.status, current)
        self.status.blockSignals(False)

    @staticmethod
    def _combo_select(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    # ---------------- data ----------------
    def refresh(self) -> None:
        self._apply_filter()

    def _apply_filter(self) -> None:
        self._rows = self.assets.list(
            query=self.search.text(),
            category_id=self.cat.currentData(),
            status=self.status.currentData(),
            include_archived=self.archived.isChecked(),
        )
        arabic = self.ctx.localizer.is_rtl
        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            for col, text in enumerate((row.code, row.name(arabic), row.category, row.location,
                                        self.ctx.tr(f"value.status.{row.status}"),
                                        self.ctx.tr(f"value.criticality.{row.criticality}"))):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.id)
                self.table.setItem(i, col, item)
        if self._rows:
            # Master-detail: keep something in the panel instead of an empty right side.
            if self.table.currentRow() < 0:
                self.table.setCurrentCell(0, 0)
            if self._detail is None:
                self._on_select()
        elif self._detail is None:
            self.detail_hint.setText(self.ctx.tr("assets.empty_hint"))

    def _on_select(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._rows)):
            return
        self._detail = self.assets.detail(self._rows[row].id)
        self._render_detail()

    def _render_detail(self) -> None:
        d = self._detail
        self._set_detail_enabled(d is not None)
        if d is None:
            return
        tr = self.ctx.tr
        self.detail_title.setText(f"{d.code} — {d.name_ar}")
        self.detail_hint.setText("" if d.is_active else tr("assets.include_archived"))
        values = {
            "code": d.code, "name_ar": d.name_ar, "name_en": d.name_en or "—",
            "category": d.category_name, "type": d.type_name or "—",
            "location": d.location_name, "parent": d.parent_code or "—",
            "criticality": tr(f"value.criticality.{d.criticality}"),
            "status": tr(f"value.status.{d.operational_status}"),
            "condition": tr(f"value.condition.{d.asset_condition}"),
            "strategy": tr(f"value.strategy.{d.maintenance_strategy}"),
            "manufacturer": d.manufacturer or "—", "model": d.model or "—",
            "serial": d.serial_number or "—", "commissioning": d.commissioning_date or "—",
            "purchase_date": d.purchase_date or "—",
            "purchase_cost": self._money(d.purchase_cost_minor, d.currency_code),
            "replacement_cost": self._money(d.replacement_cost_minor, d.currency_code),
            "warranty": d.warranty_expiry or "—", "notes": d.notes or "—",
        }
        for key, text in values.items():
            set_ltr_value(self.ov[key], text, self.ctx.localizer.is_rtl)
        self.btn_archive.setText(tr("assets.archive" if d.is_active else "assets.restore"))
        self.btn_edit.setEnabled(self.ctx.can_edit)
        self.btn_archive.setEnabled(self.ctx.can_edit)
        self.btn_spec.setEnabled(self.ctx.can_edit)
        self.btn_reading.setEnabled(self.ctx.can_edit)
        self._render_specs(d)
        self._render_meters(d)
        self._render_parts(d)
        self._render_attachments(d)
        self._render_history(d)

    @staticmethod
    def _money(minor: int | None, currency: str | None) -> str:
        if minor is None:
            return "—"
        return f"{minor / 100:,.2f} {currency or ''}".strip()

    def _render_specs(self, d: AssetDetail) -> None:
        self.specs.setRowCount(len(d.specs))
        for i, spec in enumerate(d.specs):
            self.specs.setItem(i, 0, QTableWidgetItem(spec.key))
            self.specs.setItem(i, 1, QTableWidgetItem(
                f"{spec.value} {spec.unit_code or ''}".strip()))

    def _render_meters(self, d: AssetDetail) -> None:
        self.meter_table.setRowCount(len(d.meters))
        for i, m in enumerate(d.meters):
            latest = (f"{m.latest_value} {m.unit_code}" if m.latest_value is not None else "—")
            self.meter_table.setItem(i, 0, QTableWidgetItem(m.code))
            self.meter_table.setItem(i, 1, QTableWidgetItem(self.ctx.tr(f"value.kind.{m.kind}")))
            self.meter_table.setItem(i, 2, QTableWidgetItem(latest))
            self.meter_table.setItem(i, 3, QTableWidgetItem(m.latest_at or ""))

    def _render_parts(self, d: AssetDetail) -> None:
        rows = self.inventory.asset_part_usage(d.id)
        self.parts_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            supplier = row.supplier or "—"
            if row.purchase_ref:
                supplier = f"{supplier} · {row.purchase_ref}"
            cells = (f"{row.part_code} — {row.part_name}",
                     f"{row.quantity} {row.unit_code}",
                     f"{row.total_minor / 100:,.2f} {row.currency}",
                     row.posted_at[:10], row.technician or "—",
                     row.wo_number or "—", supplier)
            for col, text in enumerate(cells):
                self.parts_table.setItem(i, col, QTableWidgetItem(text))

    def _render_attachments(self, d: AssetDetail) -> None:
        rows = self.attachments.list("asset", d.id)
        self._attach_rows = rows
        self.attach_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            cells = (row.filename, f"{row.size_bytes / 1024:.0f} KB", row.added_at[:10])
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.id)
                self.attach_table.setItem(i, col, item)

    def _add_attachment(self) -> None:
        if self._detail is None or not self.ctx.can_edit:
            return
        path, _f = QFileDialog.getOpenFileName(
            self, self.ctx.tr("attachments.add"), "",
            "Images/PDF (*.png *.jpg *.jpeg *.webp *.pdf *.docx *.xlsx *.txt)")
        if not path:
            return
        result = self.attachments.add(self.ctx.current_user, "asset", self._detail.id, Path(path))
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("attachments.add"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self._render_attachments(self._detail)

    def _open_attachment(self) -> None:
        row = self.attach_table.currentRow()
        rows = getattr(self, "_attach_rows", [])
        if not (0 <= row < len(rows)):
            return
        path = self.attachments.path(rows[row].id)
        if path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _render_history(self, d: AssetDetail) -> None:
        self.history.setRowCount(len(d.history))
        for i, h in enumerate(d.history):
            self.history.setItem(i, 0, QTableWidgetItem(self.ctx.tr(f"value.history.{h.kind}")))
            self.history.setItem(i, 1, QTableWidgetItem(h.at[:19].replace("T", " ")))
            detail = f"{h.title} — {h.detail}" if h.detail else h.title
            self.history.setItem(i, 2, QTableWidgetItem(detail))

    def _set_detail_enabled(self, enabled: bool) -> None:
        self.tabs.setEnabled(enabled)
        for btn in (getattr(self, "btn_edit", None), getattr(self, "btn_archive", None)):
            if btn is not None:
                btn.setEnabled(enabled and self.ctx.can_edit)

    # ---------------- commands ----------------
    def _ensure_location(self) -> bool:
        if self.masters.locations():
            return True
        QMessageBox.information(self, self.ctx.tr("assets.new_location"),
                                self.ctx.tr("assets.new_location_hint"))
        return False

    def _qr_sheet(self) -> None:
        if not self._rows:
            return
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        default = Path.home() / "Documents" / f"ENG_IBRAHIM_QR_{stamp}.png"
        path, _f = QFileDialog.getSaveFileName(self, self.ctx.tr("assets.qr"),
                                               str(default), "PNG (*.png)")
        if not path:
            return
        arabic = self.ctx.localizer.is_rtl
        items = [(row.code, row.name(arabic)) for row in self._rows[:40]]
        try:
            write_sheet(items, Path(path))
        except Exception as exc:
            QMessageBox.critical(self, self.ctx.tr("assets.qr"), str(exc))
            return
        QMessageBox.information(self, self.ctx.tr("assets.qr"),
                                self.ctx.tr("reports.saved", path=path))

    def _import(self) -> None:
        if not self.ctx.can_edit:
            QMessageBox.warning(self, self.ctx.tr("assets.import"),
                                self.ctx.tr("err.permission_denied"))
            return
        path, _f = QFileDialog.getOpenFileName(
            self, self.ctx.tr("assets.import"), "",
            "Excel / CSV (*.xlsx *.csv)")
        if not path:
            return
        preview = self.importer.preview("assets", Path(path))
        if not preview.ok:
            QMessageBox.warning(self, self.ctx.tr("assets.import"),
                                self.ctx.tr(preview.error_code or "err.import_failed"))
            return
        data = preview.value
        if data is None:
            return
        if not data.ok:
            detail = "\n".join(f"{p.row}: {self.ctx.tr(p.message)}"
                               for p in data.problems[:8])
            QMessageBox.warning(
                self, self.ctx.tr("assets.import"),
                self.ctx.tr("import.problems", valid=data.valid, total=data.total,
                            detail=detail))
            return
        answer = QMessageBox.question(
            self, self.ctx.tr("assets.import"),
            self.ctx.tr("import.confirm", valid=data.valid))
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = self.importer.commit(self.ctx.current_user, "assets", Path(path))
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("assets.import"),
                                self.ctx.tr(result.error_code or "err.import_failed"))
            return
        QMessageBox.information(self, self.ctx.tr("assets.import"),
                                self.ctx.tr("import.done", count=result.value))
        self.refresh()

    def _new(self) -> None:
        if not self.ctx.can_edit:
            QMessageBox.warning(self, self.ctx.tr("assets.new"),
                                self.ctx.tr("err.permission_denied"))
            return
        if not self._ensure_location():
            return
        dialog = AssetDialog(self.ctx, self.assets, self.masters, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _edit(self) -> None:
        if self._detail is None or not self.ctx.can_edit:
            return
        dialog = AssetDialog(self.ctx, self.assets, self.masters, self._detail, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._detail = self.assets.detail(self._detail.id)
            self.refresh()
            self._render_detail()

    def _toggle_archive(self) -> None:
        if self._detail is None or not self.ctx.can_edit:
            return
        if self._detail.is_active:
            answer = QMessageBox.question(self, self.ctx.tr("assets.archive"),
                                          self.ctx.tr("assets.confirm_archive"))
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.assets.archive(self.ctx.current_user, self._detail.id, "user")
        else:
            self.assets.restore(self.ctx.current_user, self._detail.id)
        self._detail = self.assets.detail(self._detail.id)
        self.refresh()
        self._render_detail()

    def _add_spec(self) -> None:
        if self._detail is None or not self.ctx.can_edit:
            return
        key, ok = QInputDialog.getText(self, self.ctx.tr("assets.spec.add"),
                                       self.ctx.tr("assets.spec.key"))
        if not ok or not key.strip():
            return
        value, ok = QInputDialog.getText(self, self.ctx.tr("assets.spec.add"),
                                         self.ctx.tr("assets.spec.value"))
        if not ok:
            return
        result = self.assets.set_spec(self.ctx.current_user, self._detail.id, key, value)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("assets.spec.add"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self._detail = self.assets.detail(self._detail.id)
        self._render_detail()

    def _add_reading(self) -> None:
        if self._detail is None or not self.ctx.can_edit:
            return
        self.meters.ensure_asset_meter(self._detail.id)
        meters = self.meters.meters(self._detail.id)
        if not meters:
            QMessageBox.information(self, self.ctx.tr("assets.tab.meters"),
                                    self.ctx.tr("assets.meter.empty"))
            return
        dialog = ReadingDialog(self.ctx, meters, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        meter_id, value, when, notes = dialog.payload()
        result = self.meters.add_reading(self.ctx.current_user, self._detail.id,
                                         meter_id, value, when, notes)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("assets.reading.title"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self._detail = self.assets.detail(self._detail.id)
        self._render_detail()
