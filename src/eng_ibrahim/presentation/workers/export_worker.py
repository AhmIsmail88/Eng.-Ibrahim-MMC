"""Background export (SPEC 17.1: heavy operations never block the UI thread)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from ...application.services.report_service import ReportService
from ...infrastructure.database.engine import Database
from ...infrastructure.exports.pdf_renderer import write_pdf
from ...infrastructure.exports.xlsx_renderer import write_xlsx


class ExportWorker(QRunnable):
    """Builds one report and writes it, off the UI thread.

    Each worker uses its own short-lived DB sessions through `Database`; no ORM
    object or Qt widget is shared with the UI thread.
    """

    class Signals(QObject):
        finished = Signal(str)
        failed = Signal(str)

    def __init__(self, db: Database, code: str, kind: str, target: Path,
                 title: str, column_titles: list[str], meta_lines: list[str],
                 total_labels: dict[str, str], filters: dict | None = None) -> None:
        super().__init__()
        self.signals = ExportWorker.Signals()
        self._db = db
        self._code = code
        self._kind = kind
        self._target = target
        self._title = title
        self._columns = column_titles
        self._meta = meta_lines
        self._labels = total_labels
        self._filters = filters or {}

    def run(self) -> None:
        try:
            report = ReportService(self._db).build(self._code, **self._filters)
            if self._kind == "pdf":
                write_pdf(self._target, report, self._title, self._columns,
                          self._meta, self._labels)
            else:
                write_xlsx(self._target, report, self._title, self._columns,
                           self._meta, self._labels)
        except Exception as exc:  # surfaced to the user, never swallowed
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(str(self._target))
