"""Attachments: safe storage, limits, integrity scan (SPEC 22)."""
from __future__ import annotations

import hashlib

import pytest

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.attachment_service import AttachmentService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.domain.enums import UserRole

PASSWORD = "Admin#2026"


@pytest.fixture
def world(ctx, paths, tmp_path):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    auth = AuthService(ctx.db)
    admin = auth.authenticate("admin", PASSWORD).value
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    asset_id = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-A1", asset_name_ar="مضخة", category_id=category.id,
        location_id=masters.locations()[0].id)).value
    service = AttachmentService(ctx.db, paths.root)
    return ctx, auth, admin, asset_id, service, tmp_path


def test_add_list_and_locate(world):
    _ctx, _auth, admin, asset_id, service, tmp_path = world
    source = tmp_path / "photo.png"
    source.write_bytes(b"\x89PNG" + b"0" * 128)
    result = service.add(admin, "asset", asset_id, source)
    assert result.ok
    rows = service.list("asset", asset_id)
    assert len(rows) == 1 and rows[0].filename == "photo.png"
    path = service.path(rows[0].id)
    assert path is not None and path.is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest()
    assert str(path).startswith(str(service._root))


def test_rejects_executables_and_missing_files(world):
    _ctx, _auth, admin, asset_id, service, tmp_path = world
    exe = tmp_path / "virus.exe"
    exe.write_bytes(b"MZ")
    assert service.add(admin, "asset", asset_id, exe).error_code == "err.attachment_type"
    assert service.add(admin, "asset", asset_id, tmp_path / "nope.png").error_code == (
        "err.file_not_found")


def test_stored_name_ignores_traversal(world):
    _ctx, _auth, admin, asset_id, service, tmp_path = world
    evil = tmp_path / "..png"
    evil.write_bytes(b"data")
    assert service.add(admin, "asset", asset_id, evil).ok
    row = service.list("asset", asset_id)[0]
    assert ".." not in row.relative_path
    assert row.relative_path.startswith("attachments/asset/")


def test_integrity_scan_detects_missing_file(world):
    _ctx, _auth, admin, asset_id, service, tmp_path = world
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF-1.4")
    service.add(admin, "asset", asset_id, source)
    path = service.path(service.list("asset", asset_id)[0].id)
    path.unlink()
    report = service.integrity_scan()
    assert report["missing"] == 1


def test_viewer_cannot_attach(world):
    _ctx, auth, admin, asset_id, service, tmp_path = world
    assert auth.create_user(admin, "ro", "Reader", UserRole.VIEWER.value, "Reader#2026").ok
    viewer = auth.authenticate("ro", "Reader#2026").value
    source = tmp_path / "b.png"
    source.write_bytes(b"x")
    assert service.add(viewer, "asset", asset_id, source).error_code == "err.permission_denied"
