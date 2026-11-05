"""Basic template import (SPEC 18.2): pick file → preview/validate → confirm → one commit."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from ...application.context import AppContext
from ...application.services.import_service import ImportService


def run_import(parent: QWidget, ctx: AppContext, kind: str, title: str) -> bool:
    """Returns True when rows were imported (the caller refreshes its list)."""
    tr = ctx.tr
    if not ctx.can_edit:
        QMessageBox.warning(parent, title, tr("err.permission_denied"))
        return False
    path, _f = QFileDialog.getOpenFileName(parent, title, "", "Excel / CSV (*.xlsx *.csv)")
    if not path:
        return False
    importer = ImportService(ctx.db)
    preview = importer.preview(kind, Path(path))
    if not preview.ok or preview.value is None:
        QMessageBox.warning(parent, title, tr(preview.error_code or "err.import_failed"))
        return False
    data = preview.value
    if not data.ok:
        detail = "\n".join(f"{p.row}: {tr(p.message)}" for p in data.problems[:8])
        QMessageBox.warning(parent, title, tr("import.problems", valid=data.valid,
                                              total=data.total, detail=detail))
        return False
    message = tr("import.confirm", valid=data.valid)
    if data.ignored_columns:  # review F-15: say what the file contains that will not be used
        message += "\n\n" + tr("import.ignored", columns=", ".join(data.ignored_columns))
    answer = QMessageBox.question(parent, title, message)
    if answer != QMessageBox.StandardButton.Yes:
        return False
    result = importer.commit(ctx.current_user, kind, Path(path))
    if not result.ok:
        QMessageBox.warning(parent, title, tr(result.error_code or "err.import_failed"))
        return False
    QMessageBox.information(parent, title, tr("import.done", count=result.value))
    return True
