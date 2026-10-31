"""Assets page: list, selection and profile tabs (SPEC 5)."""
from __future__ import annotations

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.presentation.pages.assets import AssetsPage

PASSWORD = "Admin#2026"


def _seed(ctx, paths) -> None:
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    auth = AuthService(ctx.db)
    admin = auth.authenticate("admin", PASSWORD).value
    ctx.current_user = admin
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-101", asset_name_ar="مضخة الطرد", category_id=category.id,
        location_id=masters.locations()[0].id, criticality="High"))


def test_assets_page_lists_and_opens_profile(qtbot, ctx, paths):
    _seed(ctx, paths)
    page = AssetsPage(ctx)
    qtbot.addWidget(page)
    page.refresh()

    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "PMP-101"
    assert page.tabs.count() == 6

    page.table.selectRow(0)
    assert page._detail is not None
    assert page._detail.code == "PMP-101"
    assert "PMP-101" in page.detail_title.text()


def test_empty_search_shows_hint(qtbot, ctx, paths):
    _seed(ctx, paths)
    page = AssetsPage(ctx)
    qtbot.addWidget(page)
    page.search.setText("does-not-exist")
    page.refresh()
    assert page.table.rowCount() == 0
