"""Background export worker (SPEC 17.1)."""
from __future__ import annotations

from PySide6.QtCore import QThreadPool

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.presentation.workers.export_worker import ExportWorker

PASSWORD = "Admin#2026"
COLUMNS = ["code", "name", "category", "location", "criticality", "status", "condition"]


def _seed(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    admin = AuthService(ctx.db).authenticate("admin", PASSWORD).value
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-B1", asset_name_ar="مضخة", category_id=category.id,
        location_id=masters.locations()[0].id))


def _run(qtbot, worker):
    with qtbot.waitSignal(worker.signals.finished, timeout=20000):
        QThreadPool.globalInstance().start(worker)


def test_worker_writes_xlsx(qtbot, ctx, paths, tmp_path):
    _seed(ctx, paths)
    target = tmp_path / "r.xlsx"
    worker = ExportWorker(ctx.db, "REP-001", "xlsx", target, "تقرير", COLUMNS, [], {})
    _run(qtbot, worker)
    assert target.exists() and target.read_bytes()[:2] == b"PK"


def test_worker_writes_pdf(qtbot, ctx, paths, tmp_path):
    _seed(ctx, paths)
    target = tmp_path / "r.pdf"
    worker = ExportWorker(ctx.db, "REP-001", "pdf", target, "تقرير", COLUMNS, [], {})
    _run(qtbot, worker)
    assert target.exists() and target.read_bytes()[:4] == b"%PDF"
