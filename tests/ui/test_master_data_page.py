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
    assert page.tabs.count() == 9  # SPEC 3.8: every reference list has its tab
    assert page.cur_table.rowCount() >= 1      # seeded EGP
    assert page.loc_table.rowCount() >= 1      # seeded MAIN location
    assert page.cat_table.rowCount() >= 1      # seeded categories
    assert page.type_table.rowCount() >= 1     # seeded types


def test_currencies_units_and_calendar_week(qtbot, ctx, paths):
    from eng_ibrahim.application.services.master_data_service import MasterDataService
    _seed(ctx, paths)
    service = MasterDataService(ctx.db)
    admin = ctx.current_user
    assert service.create_currency(admin, "gbp", "Pound Sterling", 2).value == "GBP"
    assert service.create_currency(admin, "GBP", "again").error_code == "err.code_exists"
    assert service.create_currency(admin, "US", "x").error_code == "err.currency_code_invalid"
    assert service.create_unit(admin, "bbl", "برميل", "Barrel", "volume", 2).ok
    assert service.create_unit(admin, "KPA", "x", "x", "pressure").error_code \
        == "err.code_exists"  # "kPa" is seeded; case-insensitive clash

    calendar_id = service.create_calendar(admin, "SHIFT-A", "وردية أ").value
    week = {6: ("08:00", "16:00"), 0: ("08:00", "16:00"), 1: ("22:00", "06:00")}
    assert service.set_calendar_week(admin, calendar_id, week).ok
    assert service.calendar_week(calendar_id) == week
    row = next(r for r in service.calendar_rows() if r[0] == calendar_id)
    assert row[3] == 24 and row[4] == 3  # the night shift counts 8 hours across midnight
    assert service.set_calendar_week(admin, calendar_id, {2: ("25:00", "26:00")}).error_code \
        == "err.calendar_time_invalid"

    page = MasterDataPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    codes = [page.cur_table.item(i, 0).text() for i in range(page.cur_table.rowCount())]
    assert "GBP" in codes
    cal_codes = [page.cal_table.item(i, 0).text() for i in range(page.cal_table.rowCount())]
    assert "SHIFT-A" in cal_codes
