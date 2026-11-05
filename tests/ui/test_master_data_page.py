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


def test_rows_can_be_edited_and_archived_from_the_tabs(qtbot, ctx, paths, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from eng_ibrahim.application.services.master_data_service import MasterDataService
    from eng_ibrahim.presentation.pages import master_data as md
    _seed(ctx, paths)
    MasterDataService(ctx.db).create_category(ctx.current_user, "PUMPX", "خطأ")
    page = MasterDataPage(ctx)
    qtbot.addWidget(page)
    # Shown, as in the app: Qt's selectRow() needs visible columns (it ignores the call
    # on an unshown table once an earlier test has switched the app to right-to-left).
    page.show()
    page.tabs.setCurrentIndex(1)  # the categories tab, where the user would be
    qtbot.waitExposed(page)
    page.refresh()
    row = next(i for i, r in enumerate(page._rows["category"]) if r.code == "PUMPX")
    page.cat_table.setCurrentCell(row, 0)
    edit, archive = page._row_buttons["category"]
    assert edit.isEnabled() and archive.text()

    # Edit: the dialog opens with the current values; change code and name.
    def fake_exec(dialog):
        line_edits = dialog.findChildren(md.QLineEdit)
        line_edits[0].setText("SUBM")
        line_edits[1].setText("مضخات غاطسة")
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(md._Dialog, "exec", fake_exec)
    page._edit_selected("category")
    codes = {r.code: r.name for r in page._rows["category"]}
    assert codes.get("SUBM") == "مضخات غاطسة" and "PUMPX" not in codes

    # Archive: the row stays, marked archived, and the button offers Restore.
    row = next(i for i, r in enumerate(page._rows["category"]) if r.code == "SUBM")
    page.cat_table.setCurrentCell(row, 0)
    page._toggle_archive("category")
    row = next(i for i, r in enumerate(page._rows["category"]) if r.code == "SUBM")
    assert "(" in page.cat_table.item(row, 1).text()
    page.cat_table.setCurrentCell(row, 0)
    assert page._row_buttons["category"][1].text() == ctx.tr("master.restore")
