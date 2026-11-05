"""Attachments list with Add / Open, reused by assets, work orders and failures (F-13)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...application.context import AppContext
from ...application.services.attachment_service import AttachmentService
from .tables import polish_table

FILE_FILTER = "Images/PDF (*.png *.jpg *.jpeg *.webp *.pdf *.docx *.xlsx *.txt)"


class AttachmentsPanel(QWidget):
    def __init__(self, ctx: AppContext, owner_type: str, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.owner_type = owner_type
        self.owner_id: str | None = None
        self.service = AttachmentService(ctx.db, ctx.paths.root)
        self._rows: list = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 3)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        polish_table(self.table, lambda: self.ctx.tr("attachments.empty"))
        self.table.cellDoubleClicked.connect(lambda _r, _c: self.open_selected())
        bar = QHBoxLayout()
        self.btn_add = QPushButton()
        self.btn_add.clicked.connect(self.add)
        self.btn_open = QPushButton()
        self.btn_open.clicked.connect(self.open_selected)
        bar.addWidget(self.btn_add)
        bar.addWidget(self.btn_open)
        bar.addStretch(1)
        lay.addWidget(self.table, 1)
        lay.addLayout(bar)
        self.retranslate()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.btn_add.setText(tr("attachments.add"))
        self.btn_open.setText(tr("attachments.open"))
        self.table.setHorizontalHeaderLabels([tr(k) for k in (
            "attachments.name", "attachments.size", "attachments.date")])

    def set_owner(self, owner_id: str | None, editable: bool = True) -> None:
        self.owner_id = owner_id
        self.btn_add.setEnabled(owner_id is not None and editable and self.ctx.can_edit)
        self.reload()

    def reload(self) -> None:
        self._rows = self.service.list(self.owner_type, self.owner_id) if self.owner_id else []
        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            cells = (row.filename, f"{row.size_bytes / 1024:.0f} KB", row.added_at[:10])
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.id)
                self.table.setItem(i, col, item)
        self.btn_open.setEnabled(bool(self._rows))

    def add(self) -> None:
        if self.owner_id is None or not self.ctx.can_edit:
            return
        path, _f = QFileDialog.getOpenFileName(self, self.ctx.tr("attachments.add"), "",
                                               FILE_FILTER)
        if not path:
            return
        self.add_file(Path(path))

    def add_file(self, path: Path) -> bool:
        result = self.service.add(self.ctx.current_user, self.owner_type, self.owner_id, path)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("attachments.add"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return False
        self.reload()
        return True

    def open_selected(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self._rows):
            row = 0 if len(self._rows) == 1 else -1
        if row < 0:
            return
        path = self.service.path(self._rows[row].id)
        if path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
