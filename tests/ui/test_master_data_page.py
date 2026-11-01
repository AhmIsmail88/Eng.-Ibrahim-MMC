"""Master data screen: locations/categories/types (UI-019)."""
from __future__ import annotations

from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.presentation.pages.master_data import MasterDataPage

PASSWORD = "Admin#2026"


def _seed(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    ctx.current_user = AuthService(ctx.db).authenticate("admin", PASSWORD).value


def test_tabs_and_seeded_rows(qtbot, ctx, paths):
    _seed(ctx, paths)
    page = MasterDataPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert page.tabs.count() == 7
    assert page.loc_table.rowCount() >= 1      # seeded MAIN location
    assert page.cat_table.rowCount() >= 1      # seeded categories
    assert page.type_table.rowCount() >= 1     # seeded types
