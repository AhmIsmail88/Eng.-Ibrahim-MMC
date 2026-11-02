"""Automatic backup off the UI thread (SPEC 17.1, SPEC 23)."""
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from ...application.services.backup_service import BackupService


class BackupWorker(QRunnable):
    """Runs one backup; the service opens its own short-lived DB sessions."""

    class Signals(QObject):
        finished = Signal(str)
        failed = Signal(str)

    def __init__(self, service: BackupService) -> None:
        super().__init__()
        self.signals = BackupWorker.Signals()
        self._service = service

    def run(self) -> None:
        try:
            result = self._service.create()
        except Exception as exc:  # surfaced in the status bar and the log, never swallowed
            self.signals.failed.emit(str(exc))
            return
        if result.ok:
            self.signals.finished.emit(str(result.value))
        else:
            self.signals.failed.emit(result.message or result.error_code or "")
