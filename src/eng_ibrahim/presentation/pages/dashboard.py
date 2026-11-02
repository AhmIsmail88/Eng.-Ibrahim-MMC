"""Dashboard: KPI cards + asset status board (SPEC 15.1, 15.1.1)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...application.context import AppContext
from ...application.services.dashboard_service import DashboardService
from ...application.services.master_data_service import MasterDataService
from ..widgets.tables import polish_table
from .base import BasePage, make_card, make_title, vbox


class _Card(QFrame):
    """KPI tile; its `tone` (neutral/info/warning/danger) colours the accent and value.

    Clicking it (or Enter/Space when focused) opens the screen behind the number.
    """

    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("kpiCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(2)
        self.value = QLabel("—")
        self.value.setObjectName("kpiValue")
        self.caption = QLabel()
        self.caption.setObjectName("kpiCaption")
        self.caption.setWordWrap(True)
        lay.addWidget(self.value)
        lay.addWidget(self.caption)
        self.set_tone("neutral")

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    def set_value(self, value: int, tone: str) -> None:
        self.value.setText(f"{value:,}")
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        if self.property("tone") == tone:
            return
        for widget in (self, self.value):
            widget.setProperty("tone", tone)
            widget.style().unpolish(widget)
            widget.style().polish(widget)


# card attribute → (screen, filter applied on arrival)
CARD_TARGETS = {
    "card_assets": ("nav.assets", None),
    "card_wos": ("nav.work_orders", "open"),
    "card_pm_overdue": ("nav.preventive", "Overdue"),
    "card_pm_soon": ("nav.preventive", "DueSoon"),
    "card_low": ("nav.spare_parts", "low"),
}


class DashboardPage(BasePage):
    open_requested = Signal(str, object)  # nav key, filter

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
        for name, (key, flt) in CARD_TARGETS.items():
            card = getattr(self, name)
            card.clicked.connect(lambda k=key, f=flt: self.open_requested.emit(k, f))
            cards.addWidget(card)
        lay.addLayout(cards)

        board_card = make_card()
        board_lay = QVBoxLayout(board_card)
        head = QHBoxLayout()
        self.board_title = QLabel()
        self.board_title.setObjectName("sectionTitle")
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
        polish_table(self.table, lambda: self.ctx.tr("common.no_data"))
        board_lay.addWidget(self.table, 1)
        lay.addWidget(board_card, 1)
        # Database path and schema revision live under Settings → About.

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("dashboard.title"))
        self.board_title.setText(tr("board.title"))
        self.card_assets.caption.setText(tr("kpi.total_assets"))
        self.card_wos.caption.setText(tr("kpi.open_wos"))
        self.card_pm_overdue.caption.setText(tr("kpi.overdue_pm"))
        self.card_pm_soon.caption.setText(tr("kpi.due_soon_pm"))
        self.card_low.caption.setText(tr("kpi.low_stock"))
        for name in CARD_TARGETS:
            getattr(self, name).setToolTip(tr("dashboard.card_tip"))
        headers = ("board.col.asset", "board.col.category", "board.col.location",
                   "board.col.status", "board.col.fault", "board.col.repair", "board.col.wo")
        self.table.setHorizontalHeaderLabels([tr(k) for k in headers])
        self._reload_categories()
        self.refresh()

    def _reload_categories(self) -> None:
        current = self.cat.currentData()
        self.cat.blockSignals(True)
        self.cat.clear()
        self.cat.addItem(self.ctx.tr("board.all_categories"), None)
        for c in self.masters.categories():
            self.cat.addItem(c.label(self.ctx.localizer.is_rtl), c.code)
        # Every category by default: a station without pumps must not open on an empty board.
        self.cat.setCurrentIndex(max(0, self.cat.findData(current)) if current else 0)
        self.cat.blockSignals(False)

    def refresh(self) -> None:
        kpis = self.service.kpis()
        self.card_assets.set_value(kpis.total_assets, "neutral")
        self.card_wos.set_value(kpis.open_work_orders,
                                "info" if kpis.open_work_orders else "neutral")
        self.card_pm_overdue.set_value(kpis.overdue_pm,
                                       "danger" if kpis.overdue_pm else "success")
        self.card_pm_soon.set_value(kpis.due_soon_pm,
                                    "warning" if kpis.due_soon_pm else "neutral")
        self.card_low.set_value(kpis.low_stock, "warning" if kpis.low_stock else "success")

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
