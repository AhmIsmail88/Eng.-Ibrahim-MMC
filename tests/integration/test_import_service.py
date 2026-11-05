"""Basic template import: preview, validation, atomic commit (SPEC 18)."""
from __future__ import annotations

import pytest

from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.import_service import ImportService
from eng_ibrahim.application.services.master_data_service import MasterDataService

PASSWORD = "Admin#2026"

HEADER = "asset_code,asset_name_ar,category_code,location_code\n"


@pytest.fixture
def world(ctx, paths, tmp_path):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    admin = AuthService(ctx.db).authenticate("admin", PASSWORD).value
    return ctx, admin, ImportService(ctx.db), tmp_path


def _csv(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(HEADER + body, encoding="utf-8")
    return path


def test_preview_reports_problems(world):
    _ctx, _admin, service, tmp_path = world
    path = _csv(tmp_path, "a.csv",
                "PMP-1,مضخة,PUMP,MAIN\nPMP-2,مضخة 2,NOPE,MAIN\n")
    result = service.preview("assets", path)
    assert result.ok
    data = result.value
    assert data.total == 2 and data.valid == 1 and len(data.problems) == 1
    assert data.problems[0].field == "category_code"


def test_commit_is_blocked_by_any_error(world):
    _ctx, admin, service, tmp_path = world
    path = _csv(tmp_path, "b.csv",
                "PMP-1,مضخة,PUMP,MAIN\n,بلا كود,PUMP,MAIN\n")
    assert service.commit(admin, "assets", path).error_code == "err.import_invalid"
    assert AssetService(_ctx.db).list() == []


def test_valid_import_creates_rows(world):
    ctx, admin, service, tmp_path = world
    path = _csv(tmp_path, "c.csv",
                "PMP-1,مضخة,PUMP,MAIN\nPMP-2,مضخة 2,PUMP,MAIN\n")
    result = service.commit(admin, "assets", path)
    assert result.ok and result.value == 2
    assert {r.code for r in AssetService(ctx.db).list()} == {"PMP-1", "PMP-2"}


def test_duplicate_against_database_is_rejected(world):
    ctx, admin, service, tmp_path = world
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    AssetService(ctx.db).create(admin, __import__(
        "eng_ibrahim.application.dto.asset", fromlist=["AssetInput"]).AssetInput(
            asset_code="PMP-1", asset_name_ar="موجود", category_id=category.id,
            location_id=masters.locations()[0].id))
    path = _csv(tmp_path, "d.csv", "pmp-1,مضخة,PUMP,MAIN\n")
    preview = service.preview("assets", path).value
    assert preview.problems[0].message == "err.import_duplicate_db"


def test_parts_import(world):
    _ctx, admin, service, tmp_path = world
    path = tmp_path / "parts.csv"
    path.write_text("part_code,name_ar,unit_code\nBRG-1,بلي,pcs\n", encoding="utf-8")
    assert service.commit(admin, "parts", path).value == 1


def test_parts_import_keeps_unit_code_case(world):
    _ctx, admin, service, tmp_path = world
    path = tmp_path / "parts.csv"
    path.write_text("part_code,name_ar,unit_code\nOIL-1,زيت,l\nGAU-1,مانومتر,KPA\n",
                    encoding="utf-8")
    assert service.commit(admin, "parts", path).value == 2


def test_asset_import_validates_criticality(world):
    _ctx, _admin, service, tmp_path = world
    path = tmp_path / "bad.csv"
    path.write_text(HEADER.strip() + ",criticality\nPMP-9,مضخة,PUMP,MAIN,Urgent\n",
                    encoding="utf-8")
    preview = service.preview("assets", path).value
    assert any(p.field == "criticality" for p in preview.problems)


def test_preview_lists_columns_that_will_be_ignored(world):
    _ctx, admin, service, tmp_path = world
    path = tmp_path / "extra.csv"
    path.write_text(HEADER.strip() + ",type_code,criticality\nPMP-7,مضخة,PUMP,MAIN,X,High\n",
                    encoding="utf-8")
    preview = service.preview("assets", path).value
    assert preview.ok and preview.ignored_columns == ["type_code"]
    assert service.commit(admin, "assets", path).value == 1
