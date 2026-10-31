"""Backup/restore: consistency, corruption refusal, real restore (SPEC 23)."""
from __future__ import annotations

import zipfile

import pytest

from eng_ibrahim.app import build_context
from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.backup_service import BackupService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService

PASSWORD = "Admin#2026"


@pytest.fixture
def world(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    admin = AuthService(ctx.db).authenticate("admin", PASSWORD).value
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    assets = AssetService(ctx.db)
    assets.create(admin, AssetInput(asset_code="PMP-C1", asset_name_ar="مضخة",
                                    category_id=category.id,
                                    location_id=masters.locations()[0].id))
    service = BackupService(ctx.db, paths, ctx.schema_revision)
    return ctx, admin, masters, assets, service, category


def test_backup_contains_manifest_and_database(world):
    _ctx, _admin, _m, _a, service, _cat = world
    result = service.create()
    assert result.ok
    archive = result.value
    assert archive.suffix == ".eibak" and archive.stat().st_size > 1000
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        assert "manifest.json" in names and "data/maintenance.sqlite3" in names
    info = service.inspect(archive)
    assert info.ok and info.value.files >= 0
    assert service.verify(archive).ok


def test_corrupt_archive_is_refused(world):
    _ctx, _admin, _m, _a, service, _cat = world
    archive = service.create().value
    data = bytearray(archive.read_bytes())
    data[len(data) // 2] ^= 0xFF
    archive.write_bytes(bytes(data))
    assert service.verify(archive).error_code in ("err.backup_corrupt", "err.backup_invalid")


def test_restore_brings_data_back(world, ctx, paths):
    _ctx, admin, masters, assets, service, category = world
    archive = service.create().value
    assets.create(admin, AssetInput(asset_code="PMP-C2", asset_name_ar="مضخة 2",
                                    category_id=category.id,
                                    location_id=masters.locations()[0].id))
    ctx.db.dispose()
    assert service.restore(archive).ok

    fresh, _report = build_context(paths)
    try:
        rows = AssetService(fresh.db).list(include_archived=True)
        assert [r.code for r in rows] == ["PMP-C1"]
    finally:
        fresh.db.dispose()


def test_non_zip_is_invalid(world, tmp_path):
    _ctx, _admin, _m, _a, service, _cat = world
    bad = tmp_path / "bad.eibak"
    bad.write_bytes(b"not a zip")
    assert service.verify(bad).error_code == "err.backup_invalid"


def test_prune_keeps_newest(world, tmp_path):
    _ctx, _admin, _m, _a, service, _cat = world
    folder = tmp_path / "rotated"
    folder.mkdir()
    for index in range(3):
        archive = folder / f"ENG_IBRAHIM_BACKUP_2026-01-0{index + 1}_1200{index}.eibak"
        archive.write_bytes(b"x")
    assert service.prune(keep=2, directory=folder) == 1
    left = sorted(p.name for p in folder.glob("*.eibak"))
    assert left == ["ENG_IBRAHIM_BACKUP_2026-01-02_12001.eibak",
                    "ENG_IBRAHIM_BACKUP_2026-01-03_12002.eibak"]
