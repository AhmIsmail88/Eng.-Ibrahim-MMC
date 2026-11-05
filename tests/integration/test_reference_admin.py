"""Edit and archive master data (SPEC 3.8, review F-01)."""
from __future__ import annotations

import pytest

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.inventory_service import InventoryService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.reference_admin import KINDS, ReferenceAdminService
from eng_ibrahim.domain.enums import UserRole

PASSWORD = "Admin#2026"


@pytest.fixture
def world(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    auth = AuthService(ctx.db)
    admin = auth.authenticate("admin", PASSWORD).value
    return ctx, auth, admin, MasterDataService(ctx.db), ReferenceAdminService(ctx.db)


def _row(admin_service, kind, code):
    return next(r for r in admin_service.rows(kind) if r.code == code)


def test_every_list_can_be_listed(world):
    *_rest, refs = world
    for kind in KINDS:
        assert isinstance(refs.rows(kind), list)


def test_typo_code_is_fixable_while_unused(world):
    _ctx, _auth, admin, masters, refs = world
    masters.create_category(admin, "PUMPX", "مضخات خطأ")
    row = _row(refs, "category", "PUMPX")
    assert refs.update(admin, "category", row.id, {"name_ar": "مضخات غاطسة"},
                       code="SUBM").ok
    fixed = _row(refs, "category", "SUBM")
    assert fixed.name == "مضخات غاطسة"
    # Names stay unique per code: an existing code is refused.
    assert refs.update(admin, "category", fixed.id, {}, code="PUMP").error_code \
        == "err.code_exists"


def test_code_in_use_is_locked_but_name_editable(world):
    ctx, _auth, admin, masters, refs = world
    location = masters.locations()[0]
    category = next(c for c in masters.categories() if c.code == "PUMP")
    AssetService(ctx.db).create(admin, AssetInput(
        asset_code="P-1", asset_name_ar="مضخة", category_id=category.id,
        location_id=location.id))
    assert refs.update(admin, "category", category.id, {}, code="PMP").error_code \
        == "err.code_in_use"
    assert refs.update(admin, "category", category.id, {"name_ar": "المضخات"}).ok
    assert _row(refs, "category", "PUMP").name == "المضخات"


def test_archive_is_refused_while_in_use_and_hides_from_new_forms(world):
    ctx, _auth, admin, masters, refs = world
    location = masters.locations()[0]
    category = next(c for c in masters.categories() if c.code == "PUMP")
    asset_id = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="P-2", asset_name_ar="مضخة", category_id=category.id,
        location_id=location.id)).value
    assert refs.set_active(admin, "location", location.id, False).error_code \
        == "err.archive_in_use"
    masters.create_location(admin, "OLD", "موقع قديم")
    old = _row(refs, "location", "OLD")
    assert refs.set_active(admin, "location", old.id, False).ok
    assert "OLD" not in {loc.code for loc in masters.locations()}
    assert not _row(refs, "location", "OLD").is_active
    assert refs.set_active(admin, "location", old.id, True).ok
    assert asset_id


def test_units_currencies_and_defaults(world):
    ctx, _auth, admin, masters, refs = world
    # Unit: code is the primary key and never changes; labels can.
    assert refs.update(admin, "unit", "pcs", {"label_ar": "عدد"}, code="pc").error_code \
        == "err.code_locked"
    assert refs.update(admin, "unit", "pcs", {"label_ar": "عدد", "label_en": "pieces",
                                              "dimension": "count", "precision": 0}).ok
    assert {u.code: u.name_ar for u in masters.units()}["pcs"] == "عدد"
    # An unused unit can be archived and leaves the new-entry list.
    assert refs.set_active(admin, "unit", "rpm", False).ok
    assert "rpm" not in {u.code for u in masters.units(active_only=True)}
    assert "rpm" in {u.code for u in masters.units()}
    # The base currency and the default warehouse are never archived.
    assert refs.set_active(admin, "currency", "EGP", False).error_code \
        == "err.archive_default"
    wh = InventoryService(ctx.db).ensure_default_warehouse()
    assert refs.set_active(admin, "warehouse", wh, False).error_code == "err.archive_default"


def test_currency_scale_locked_after_first_use(world):
    ctx, _auth, admin, _masters, refs = world
    assert refs.update(admin, "currency", "USD", {"name": "US Dollar", "minor_units": 3}).ok
    InventoryService(ctx.db).create_part(admin, "X-1", "قطعة", "pcs", currency="USD")
    assert refs.update(admin, "currency", "USD", {"name": "US Dollar", "minor_units": 2}) \
        .error_code == "err.currency_locked"


def test_warehouse_with_stock_cannot_be_archived(world):
    ctx, _auth, admin, masters, refs = world
    inv = InventoryService(ctx.db)
    inv.ensure_default_warehouse()
    masters.create_warehouse(admin, "WH2", "مخزن 2")
    wh2 = _row(refs, "warehouse", "WH2")
    part = inv.create_part(admin, "X-2", "قطعة", "pcs").value
    assert inv.receive(admin, part, "3", 100, warehouse_id=wh2.id).ok
    assert refs.set_active(admin, "warehouse", wh2.id, False).error_code \
        == "err.archive_in_use"


def test_viewer_cannot_edit(world):
    _ctx, auth, admin, masters, refs = world
    viewer = auth.create_user(admin, "v", "Viewer", UserRole.VIEWER.value, "Viewer#2026").value
    location = masters.locations()[0]
    assert refs.update(viewer, "location", location.id, {"name_ar": "x"}).error_code \
        == "err.permission_denied"
    assert refs.set_active(viewer, "location", location.id, False).error_code \
        == "err.permission_denied"
