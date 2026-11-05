"""Reports center: preview + PDF/XLSX export (SPEC 17)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, QThreadPool
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...application.context import AppContext
from ...application.services.inventory_service import InventoryService
from ...application.services.master_data_service import MasterDataService
from ...application.services.report_service import (
    REPORTS,
    ReportResult,
    ReportService,
    localized,
)
from ...application.services.work_order_service import WorkOrderService
from ...infrastructure.database.orm_models.maintenance import WO_STATUS, WO_TYPE
from ...infrastructure.database.orm_models.operations import OPERATIONAL_STATUS
from ..widgets.tables import polish_table
from ..workers.export_worker import ExportWorker
from .base import BasePage, make_card, make_title, vbox

_PERIOD_REPORTS = ("REP-003", "REP-005", "REP-013")
_WO_REPORTS = ("REP-006",)
# report → filter combos it offers (review F-07); each maps to a ReportService.build argument
_FILTERS = {"REP-001": ("category", "asset_status"), "REP-005": ("wo_type", "wo_status"),
            "REP-009": ("warehouse",)}
_FILTER_ARG = {"category": "category_id", "asset_status": "status", "wo_type": "wo_type",
               "wo_status": "status", "warehouse": "warehouse_id"}


class ReportsPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = ReportService(ctx.db)
        self.orders = WorkOrderService(ctx.db)
        self.masters = MasterDataService(ctx.db)
        self.inventory = InventoryService(ctx.db)
        self._report: ReportResult | None = None
        self._build()
        self.retranslate()

    def _build(self) -> None:
        lay = vbox(self)
        self.title = make_title()
        lay.addWidget(self.title)

        bar = QHBoxLayout()
        self.report = QComboBox()
        for code, _title_key, _ in REPORTS:
            self.report.addItem("", code)
        self.report.currentIndexChanged.connect(lambda _i: self._on_report_changed())
        start, end = ReportService.default_period()
        self.date_from = QDateEdit(QDate.fromString(start, "yyyy-MM-dd"))
        self.date_to = QDateEdit(QDate.fromString(end, "yyyy-MM-dd"))
        for widget in (self.date_from, self.date_to):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("yyyy-MM-dd")
        self.lbl_from, self.lbl_to = QLabel(), QLabel()
        self.wo = QComboBox()
        self.lbl_wo = QLabel()
        self.filters: dict[str, tuple[QLabel, QComboBox]] = {}
        for name in _FILTER_ARG:
            combo = QComboBox()
            combo.currentIndexChanged.connect(lambda _i: self.refresh())
            self.filters[name] = (QLabel(), combo)
        self.btn_preview = QPushButton()
        self.btn_preview.clicked.connect(self.refresh)
        self.btn_pdf = QPushButton()
        self.btn_pdf.clicked.connect(lambda: self._export("pdf"))
        self.btn_xlsx = QPushButton()
        self.btn_xlsx.clicked.connect(lambda: self._export("xlsx"))
        bar.addWidget(self.report, 2)
        bar.addWidget(self.lbl_from)
        bar.addWidget(self.date_from)
        bar.addWidget(self.lbl_to)
        bar.addWidget(self.date_to)
        bar.addWidget(self.lbl_wo)
        bar.addWidget(self.wo)
        for label, combo in self.filters.values():
            bar.addWidget(label)
            bar.addWidget(combo)
        bar.addStretch(1)
        bar.addWidget(self.btn_preview)
        bar.addWidget(self.btn_pdf)
        bar.addWidget(self.btn_xlsx)
        lay.addLayout(bar)

        card = make_card()
        card_lay = QVBoxLayout(card)
        self.totals = QLabel()
        self.totals.setObjectName("hint")
        self.table = QTableWidget(0, 0)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        polish_table(self.table, lambda: self.ctx.tr("common.no_data"))
        card_lay.addWidget(self.totals)
        card_lay.addWidget(self.table, 1)
        lay.addWidget(card, 1)

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("reports.title"))
        self.lbl_from.setText(tr("reports.from"))
        self.lbl_to.setText(tr("reports.to"))
        self.lbl_wo.setText(tr("reports.work_order"))
        self.btn_preview.setText(tr("reports.preview"))
        self.btn_pdf.setText(tr("reports.export_pdf"))
        self.btn_xlsx.setText(tr("reports.export_xlsx"))
        for index, (code, title_key, _) in enumerate(REPORTS):
            self.report.setItemText(index, f"{code} — {tr(title_key)}")
        self._fill_filters()
        self._sync_period()
        self.refresh()

    def _on_report_changed(self) -> None:
        self._sync_period()
        self.refresh()

    def _sync_period(self) -> None:
        code = self.report.currentData()
        needs_period = code in _PERIOD_REPORTS
        needs_wo = code in _WO_REPORTS
        for widget in (self.date_from, self.date_to, self.lbl_from, self.lbl_to):
            widget.setVisible(needs_period)
        for widget in (self.wo, self.lbl_wo):
            widget.setVisible(needs_wo)
        offered = _FILTERS.get(code, ())
        for name, (label, combo) in self.filters.items():
            label.setVisible(name in offered)
            combo.setVisible(name in offered)
        if needs_wo and self.wo.count() == 0:
            for row in self.orders.list():
                self.wo.addItem(row.number, row.id)

    def _fill_filters(self) -> None:
        tr = self.ctx.tr
        rtl = self.ctx.localizer.is_rtl
        options = {
            "category": [(c.label(rtl), c.id) for c in self.masters.categories()],
            "asset_status": [(tr(f"value.status.{s}"), s) for s in OPERATIONAL_STATUS],
            "wo_type": [(tr(f"value.wotype.{w}"), w) for w in WO_TYPE],
            "wo_status": [(tr(f"value.wo.{s}"), s) for s in WO_STATUS],
            "warehouse": [(f"{code} — {name}", wid)
                          for wid, code, name in self.inventory.warehouses()],
        }
        labels = {"category": "rep.col.category", "asset_status": "rep.col.status",
                  "wo_type": "rep.col.type", "wo_status": "rep.col.status",
                  "warehouse": "parts.warehouse"}
        for name, (label, combo) in self.filters.items():
            label.setText(tr(labels[name]))
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(tr("assets.all"), None)
            for text, value in options[name]:
                combo.addItem(text, value)
            combo.setCurrentIndex(max(0, combo.findData(current)))
            combo.blockSignals(False)

    def _filter_values(self) -> dict:
        code = self.report.currentData()
        values: dict = {}
        if code in _PERIOD_REPORTS:
            values["date_from"] = self.date_from.date().toString("yyyy-MM-dd")
            values["date_to"] = self.date_to.date().toString("yyyy-MM-dd")
        if code in _WO_REPORTS:
            values["wo_id"] = self.wo.currentData()
        for name in _FILTERS.get(code, ()):
            value = self.filters[name][1].currentData()
            if value is not None:
                values[_FILTER_ARG[name]] = value
        return values

    # ---------------- data ----------------
    def refresh(self) -> None:
        code = self.report.currentData()
        if code is None:
            return
        self._report = localized(self.service.build(code, **self._filter_values()),
                                 self.ctx.tr)
        columns = self._report.columns
        self.table.clear()
        self.table.setColumnCount(len(columns))
        self.table.setRowCount(len(self._report.rows))
        self.table.setHorizontalHeaderLabels([self.ctx.tr(c.title_key) for c in columns])
        for row_index, data in enumerate(self._report.rows):
            for col, column in enumerate(columns):
                self.table.setItem(row_index, col,
                                   QTableWidgetItem(str(data.get(column.key, ""))))
        if self._report.totals:
            parts = [f"{self.ctx.tr('reports.count')}: {self._report.totals.get('count', '')}"
                     if "count" in self._report.totals else ""]
            parts += [f"{key}: {value}" for key, value in self._report.totals.items()
                      if key != "count"]
            self.totals.setText(" · ".join(p for p in parts if p))
        else:
            self.totals.setText("")

    # ---------------- export ----------------
    def _export(self, kind: str) -> None:
        if self._report is None:
            return
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        default = Path.home() / "Documents" / f"ENG_IBRAHIM_{self._report.code}_{stamp}.{kind}"
        path, _filter = QFileDialog.getSaveFileName(
            self, self.ctx.tr(f"reports.export_{kind}"), str(default),
            "PDF (*.pdf)" if kind == "pdf" else "Excel (*.xlsx)")
        if not path:
            return
        target = Path(path)
        title = self.ctx.tr(self._report.title_key)
        columns = [self.ctx.tr(c.title_key) for c in self._report.columns]
        meta = [
            self.ctx.tr("app.name"),
            self.ctx.tr("reports.generated", when=datetime.now().strftime("%Y-%m-%d %H:%M")),
        ]
        if self._report.meta.get("from"):
            meta.append(f"{self.ctx.tr('reports.from')}: {self._report.meta['from']} → "
                        f"{self._report.meta['to']}")
        labels = {"totals": self.ctx.tr("reports.totals")}
        # The export uses exactly the filters of the preview on screen.
        filters = self._filter_values()
        for name in _FILTERS.get(self._report.code, ()):
            label, combo = self.filters[name]
            if combo.currentData() is not None:
                meta.append(f"{label.text()}: {combo.currentText()}")
        worker = ExportWorker(self.ctx.db, self._report.code, kind, target, title,
                              columns, meta, labels, filters, translate=self.ctx.tr)
        worker.signals.finished.connect(self._on_export_done)
        worker.signals.failed.connect(self._on_export_failed)
        self._worker = worker  # keep a reference until the signal arrives
        self.btn_pdf.setEnabled(False)
        self.btn_xlsx.setEnabled(False)
        self.totals.setText(self.ctx.tr("reports.working"))
        QThreadPool.globalInstance().start(worker)

    def _on_export_done(self, path: str) -> None:
        self.btn_pdf.setEnabled(True)
        self.btn_xlsx.setEnabled(True)
        self.refresh()
        QMessageBox.information(self, self.ctx.tr("reports.title"),
                                self.ctx.tr("reports.saved", path=path))

    def _on_export_failed(self, message: str) -> None:
        self.btn_pdf.setEnabled(True)
        self.btn_xlsx.setEnabled(True)
        self.refresh()
        QMessageBox.critical(self, self.ctx.tr("reports.title"), message)
