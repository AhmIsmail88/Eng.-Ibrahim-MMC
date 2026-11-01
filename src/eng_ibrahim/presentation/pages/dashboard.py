"""Dashboard: KPI cards + asset status board (SPEC 15.1, 15.1.1)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...application.context import AppContext
from ...application.services.dashboard_service import DashboardService
from ...application.services.master_data_service import MasterDataService
from .base import BasePage, make_card, make_title, set_ltr_value, vbox


class _Card(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        self.value = QLabel("—")
        self.value.setObjectName("kpiValue")
        self.value.setStyleSheet("font-size: 22pt; font-weight: 600;")
        self.caption = QLabel()
        self.caption.setObjectName("hint")
        lay.addWidget(self.value)
        lay.addWidget(self.caption)


class DashboardPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.service = DashboardService(ctx.db)
        self.masters = MasterDataService(ctx.db)
        self._build()
        self.retranslate()

    def _build(self) -> None:
        lay = vbox(self)
        self.title = make_title()
        lay.addWidget(self.title)

        cards = QHBoxLayout()
        self.card_assets, self.card_wos = _Card(), _Card()
        self.card_pm_overdue, self.card_pm_soon = _Card(), _Card()
        self.card_low = _Card()
        for card in (self.card_assets, self.card_wos, self.card_pm_overdue,
                     self.card_pm_soon, self.card_low):
            cards.addWidget(card)
        lay.addLayout(cards)

        board_card = make_card()
        board_lay = QVBoxLayout(board_card)
        head = QHBoxLayout()
        self.board_title = QLabel()
        self.board_title.setStyleSheet("font-weight: 600;")
        self.cat = QComboBox()
        self.cat.currentIndexChanged.connect(lambda _i: self.refresh())
        head.addWidget(self.board_title)
        head.addStretch(1)
        head.addWidget(self.cat)
        board_lay.addLayout(head)

        self.table = QTableWidget(0, 7)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        board_lay.addWidget(self.table, 1)
        lay.addWidget(board_card, 1)

        system = QGridLayout()
        self.db_label, self.db_value = QLabel(), QLabel()
        self.schema_label, self.schema_value = QLabel(), QLabel()
        system.addWidget(self.db_label, 0, 0)
        system.addWidget(self.db_value, 0, 1)
        system.addWidget(self.schema_label, 1, 0)
        system.addWidget(self.schema_value, 1, 1)
        lay.addLayout(system)

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("dashboard.title"))
        self.board_title.setText(tr("board.title"))
        self.card_assets.caption.setText(tr("kpi.total_assets"))
        self.card_wos.caption.setText(tr("kpi.open_wos"))
        self.card_pm_overdue.caption.setText(tr("kpi.overdue_pm"))
        self.card_pm_soon.caption.setText(tr("kpi.due_soon_pm"))
        self.card_low.caption.setText(tr("kpi.low_stock"))
        headers = ("board.col.asset", "board.col.category", "board.col.location",
                   "board.col.status", "board.col.fault", "board.col.repair", "board.col.wo")
        self.table.setHorizontalHeaderLabels([tr(k) for k in headers])
        self.db_label.setText(tr("dashboard.db_path"))
        self.schema_label.setText(tr("dashboard.schema"))
        set_ltr_value(self.db_value, str(self.ctx.paths.db_file), self.ctx.localizer.is_rtl)
        set_ltr_value(self.schema_value, self.ctx.schema_revision, self.ctx.localizer.is_rtl)
        self._reload_categories()
        self.refresh()

    def _reload_categories(self) -> None:
        current = self.cat.currentData()
        self.cat.blockSignals(True)
        self.cat.clear()
        self.cat.addItem(self.ctx.tr("board.all_categories"), None)
        for c in self.masters.categories():
            self.cat.addItem(c.label(self.ctx.localizer.is_rtl), c.code)
        index = self.cat.findData(current) if current else self.cat.findData("PUMP")
        self.cat.setCurrentIndex(max(0, index))
        self.cat.blockSignals(False)

    def refresh(self) -> None:
        kpis = self.service.kpis()
        self.card_assets.value.setText(str(kpis.total_assets))
        self.card_wos.value.setText(str(kpis.open_work_orders))
        self.card_pm_overdue.value.setText(str(kpis.overdue_pm))
        self.card_pm_soon.value.setText(str(kpis.due_soon_pm))
        self.card_low.value.setText(str(kpis.low_stock))

        rows = self.service.board(self.cat.currentData())
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            status = self.ctx.tr(f"board.state.{row.derived_status}")
            if row.conflict:
                status = f"⚠ {status}"
            cells = (f"{row.code} — {row.name}", row.category, row.location, status,
                     row.fault_at or "—", row.repair_at or "—", row.open_wo or "—")
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.asset_id)
                self.table.setItem(i, col, item)
