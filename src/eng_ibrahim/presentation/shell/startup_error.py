from __future__ import annotations

import os
import sys

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from ...config import AppPaths
from ...localization.service import Localizer

RETRY, EXIT = 1, 0


class StartupErrorDialog(QDialog):
    """Shown instead of silently creating an empty DB over a damaged one (SPEC 24.4)."""

    def __init__(self, loc: Localizer, paths: AppPaths, details: str) -> None:
        super().__init__()
        tr = loc.tr
        self.paths = paths
        self.setWindowTitle(tr("startup.error_title"))
        self.setMinimumSize(560, 360)
        lay = QVBoxLayout(self)
        head = QLabel(tr("startup.error_title"))
        head.setStyleSheet("font-size: 14pt; font-weight: 700;")
        body = QLabel(tr("startup.error_body"))
        body.setWordWrap(True)
        self.details = QPlainTextEdit(details)
        self.details.setReadOnly(True)
        row = QHBoxLayout()
        btn_retry, btn_logs = QPushButton(tr("common.retry")), QPushButton(tr("common.open_logs"))
        btn_copy, btn_exit = QPushButton(tr("common.copy")), QPushButton(tr("common.exit"))
        btn_retry.clicked.connect(lambda: self.done(RETRY))
        btn_exit.clicked.connect(lambda: self.done(EXIT))
        btn_copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(details))
        btn_logs.clicked.connect(self._open_logs)
        for b in (btn_retry, btn_logs, btn_copy, btn_exit):
            row.addWidget(b)
        for w in (head, body, self.details):
            lay.addWidget(w)
        lay.addLayout(row)

    def _open_logs(self) -> None:
        folder = str(self.paths.logs)
        if sys.platform == "win32":
            os.startfile(folder)
