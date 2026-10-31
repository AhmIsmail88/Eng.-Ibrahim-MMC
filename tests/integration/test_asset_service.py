"""Asset registry: uniqueness, hierarchy, search, archive, permissions (SPEC 5)."""
from __future__ import annotations

import pytest

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.domain.enums import UserRole
from eng_ibrahim.infrastructure.database.orm_models import Asset, AssetLocationHistory

PASSWORD = "Admin#2026"


@pytest.fixture
def world(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    auth = AuthService(ctx.db)
    admin = auth.authenticate("admin", PASSWORD).value
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    location = masters.locations()[0]
    assets = AssetService(ctx.db)
    return ctx, assets, masters, admin, auth, category.id, location.id


def _input(category_id: str, location_id: str, **kw) -> AssetInput:
    base = dict(asset_code="PMP-101", asset_name_ar="مضخة 101", category_id=category_id,
                location_id=location_id, criticality="High", meter_type="Runtime Hours",
                default_meter_unit="h")
    base.update(kw)
    return AssetInput(**base)


def test_create_and_read_back(world):
    _ctx, assets, _m, admin, _a, cat, loc = world
    created = assets.create(admin, _input(cat, loc))
    assert created.ok and created.value

    detail = assets.detail(created.value)
    assert detail is not None
    assert detail.code == "PMP-101" and detail.category_name and detail.location_name
    assert detail.operational_status == "In Service"
    assert [h.kind for h in detail.history] == ["status"]


def test_duplicate_code_is_rejected_ignoring_case_and_spaces(world):
    _ctx, assets, _m, admin, _a, cat, loc = world
    assert assets.create(admin, _input(cat, loc)).ok
    again = assets.create(admin, _input(cat, loc, asset_code="  pmp-101 ", asset_name_ar="أخرى"))
    assert again.error_code == "err.asset_code_exists"


def test_required_fields_and_lookups(world):
    _ctx, assets, _m, admin, _a, cat, loc = world
    assert assets.create(admin, _input(cat, loc, asset_code=" ")).error_code == (
        "err.asset_code_required")
    assert assets.create(admin, _input(cat, loc, asset_name_ar=" ")).error_code == (
        "err.asset_name_required")
    assert assets.create(admin, _input(cat, "missing", asset_code="X-1")).error_code == (
        "err.location_required")
    assert assets.create(admin, _input("missing", loc, asset_code="X-2")).error_code == (
        "err.category_required")


def test_parent_cycle_is_rejected(world):
    _ctx, assets, _m, admin, _a, cat, loc = world
    parent = assets.create(admin, _input(cat, loc)).value
    child = assets.create(admin, _input(cat, loc, asset_code="PMP-102",
                                        parent_asset_id=parent)).value
    assert parent and child
    cycle = assets.update(admin, parent, _input(cat, loc, parent_asset_id=child))
    assert cycle.error_code == "err.parent_cycle"
    self_parent = assets.update(admin, parent, _input(cat, loc, parent_asset_id=parent))
    assert self_parent.error_code == "err.parent_cycle"


def test_search_folds_arabic_and_matches_code(world):
    _ctx, assets, _m, admin, _a, cat, loc = world
    assets.create(admin, _input(cat, loc, asset_name_ar="مضخة طرد مركزي"))
    assets.create(admin, _input(cat, loc, asset_code="MTR-7", asset_name_ar="محرك كهربائي"))

    assert [r.code for r in assets.list(query="مضخه")] == ["PMP-101"]
    assert [r.code for r in assets.list(query="pmp")] == ["PMP-101"]
    assert {r.code for r in assets.list(query="كهرباء")} == set()


def test_archive_hides_from_active_list_and_keeps_history(world):
    _ctx, assets, _m, admin, _a, cat, loc = world
    asset_id = assets.create(admin, _input(cat, loc)).value
    assert assets.archive(admin, asset_id, "scrapped").ok
    assert assets.list() == []
    assert len(assets.list(include_archived=True)) == 1
    assert assets.detail(asset_id).is_active is False
    assert assets.restore(admin, asset_id).ok
    assert len(assets.list()) == 1


def test_location_move_is_recorded(world):
    ctx, assets, masters, admin, _a, cat, loc = world
    asset_id = assets.create(admin, _input(cat, loc)).value
    second = masters.create_location(admin, "PS-1", "محطة الرفع", "Pump Station").value
    assert assets.move_location(admin, asset_id, second, "نقل تشغيلي").ok
    detail = assets.detail(asset_id)
    assert any(h.kind == "location" for h in detail.history)
    with ctx.db.session() as s:
        assert s.query(AssetLocationHistory).count() == 1
        assert s.get(Asset, asset_id).location_id == second


def test_viewer_cannot_create_or_archive(world):
    ctx, assets, _m, admin, auth, cat, loc = world
    assert auth.create_user(admin, "reader", "Reader", UserRole.VIEWER.value, "Reader#2026").ok
    viewer = auth.authenticate("reader", "Reader#2026").value
    result = assets.create(viewer, _input(cat, loc))
    assert result.error_code == "err.permission_denied"
    asset_id = assets.create(admin, _input(cat, loc)).value
    assert assets.archive(viewer, asset_id).error_code == "err.permission_denied"


def test_status_change_records_history(world):
    _ctx, assets, _m, admin, _a, cat, loc = world
    asset_id = assets.create(admin, _input(cat, loc)).value
    assert assets.change_status(admin, asset_id, "Under Maintenance", "bearing").ok
    detail = assets.detail(asset_id)
    assert detail.operational_status == "Under Maintenance"
    assert len([h for h in detail.history if h.kind == "status"]) == 2
    assert assets.change_status(admin, asset_id, "Flying").error_code == "err.status_invalid"
