"""Global search dialog (Ctrl+K): type, arrow to a result, Enter opens it."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from ...application.context import AppContext
from ...application.services.search_service import MIN_QUERY, SearchHit, SearchService

# result kind → screen that shows it
KIND_TO_NAV = {"asset": "nav.assets", "vehicle": "nav.vehicles",
               "work_order": "nav.work_orders", "part": "nav.spare_parts"}


class GlobalSearchDialog(QDialog):
    chosen = Signal(str, str)  # kind, record id

    def __init__(self, ctx: AppContext, parent=None, text: str = "") -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.service = SearchService(ctx.db)
        self.setModal(True)
        self.setMinimumSize(560, 420)
        self.setWindowTitle(ctx.tr("search.title"))
        lay = QVBoxLayout(self)
        self.query = QLineEdit(text)
        self.query.setPlaceholderText(ctx.tr("search.placeholder"))
        # No clear button: under RTL + the stylesheet it renders outside the field; Esc closes.
        self.results = QListWidget()
        self.results.setObjectName("searchResults")
        self.results.itemActivated.connect(self._open)
        self.status = QLabel()
        self.status.setObjectName("hint")
        lay.addWidget(self.query)
        lay.addWidget(self.results, 1)
        lay.addWidget(self.status)
        # Debounce: one query per pause in typing, not one per keystroke.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self.run_search)
        self.query.textChanged.connect(lambda _t: self._timer.start())
        self.query.installEventFilter(self)
        self.hits: list[SearchHit] = []
        self.run_search()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        """Up/Down move through results while typing; Enter opens the selection."""
        if watched is self.query and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.results.count():
                step = 1 if event.key() == Qt.Key.Key_Down else -1
                row = max(0, min(self.results.count() - 1, self.results.currentRow() + step))
                self.results.setCurrentRow(row)
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._timer.stop()
                if not self.hits:
                    self.run_search()
                item = self.results.currentItem()
                if item is not None:
                    self._open(item)
                return True
        return super().eventFilter(watched, event)

    def run_search(self) -> None:
        tr = self.ctx.tr
        text = self.query.text().strip()
        self.hits = self.service.search(text, arabic=self.ctx.localizer.is_rtl)
        self.results.clear()
        for hit in self.hits:
            line = f"{tr(f'search.kind.{hit.kind}')}  ·  {hit.code} — {hit.title}"
            if hit.detail:
                line += f"   ({hit.detail})"
            item = QListWidgetItem(line)
            item.setData(Qt.ItemDataRole.UserRole, (hit.kind, hit.record_id))
            self.results.addItem(item)
        if self.hits:
            self.results.setCurrentRow(0)
            self.status.setText(tr("search.count", count=len(self.hits)))
        elif len(text) < MIN_QUERY:
            self.status.setText(tr("search.hint"))
        else:
            self.status.setText(tr("search.none"))

    def _open(self, item: QListWidgetItem) -> None:
        kind, record_id = item.data(Qt.ItemDataRole.UserRole)
        self.chosen.emit(kind, record_id)
        self.accept()
