"""UI regressions: blank buttons, stale translations, table sizing, empty states."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.work_order_service import WorkOrderService
from eng_ibrahim.domain.enums import Language
from eng_ibrahim.domain.policies import wo_state_machine as sm
from eng_ibrahim.presentation.pages.settings import SettingsPage
from eng_ibrahim.presentation.pages.work_orders import WorkOrdersPage
from eng_ibrahim.presentation.widgets.tables import polish_table

PASSWORD = "Admin#2026"


def _admin(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    ctx.current_user = AuthService(ctx.db).authenticate("admin", PASSWORD).value
    return ctx.current_user


def test_settings_backup_section_is_labelled(qtbot, ctx, paths):
    _admin(ctx, paths)
    page = SettingsPage(ctx)
    qtbot.addWidget(page)
    for widget in (page.backup_title, page.last_label, page.last_val,
                   page.btn_backup, page.btn_restore, page.btn_folder):
        assert widget.text().strip()


def test_work_order_detail_follows_language_switch(qtbot, ctx, paths):
    admin = _admin(ctx, paths)
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    asset_id = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-L1", asset_name_ar="مضخة", category_id=category.id,
        location_id=masters.locations()[0].id)).value
    orders = WorkOrderService(ctx.db)
    wo_id = orders.create(admin, asset_id, "CM", "إصلاح").value
    orders.transition(admin, wo_id, sm.OPEN)

    page = WorkOrdersPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    page.table.selectRow(0)
    assert "مفتوح" in page.meta.text()
    ctx.localizer.set_language(Language.EN)
    page.retranslate()
    assert "Open" in page.meta.text() and "مفتوح" not in page.meta.text()


def test_table_helper_fits_columns_and_shows_empty_state(qtbot):
    table = QTableWidget(0, 3)
    table.setHorizontalHeaderLabels(["Code *", "Title", "State"])
    polish_table(table, lambda: "Nothing here")
    qtbot.addWidget(table)
    table.resize(600, 300)
    table.show()
    qtbot.waitExposed(table)
    empty = table.viewport().findChild(QLabel, "emptyState")
    assert table.horizontalHeaderItem(0).text() == "Code"
    assert empty is not None and empty.isVisible() and empty.text() == "Nothing here"

    table.setRowCount(2)
    for row, cells in enumerate((("WO-2026-000001", "A very long work order title " * 3, "Open"),
                                 ("WO-2026-000002", "Short", "Closed"))):
        for col, text in enumerate(cells):
            table.setItem(row, col, QTableWidgetItem(text))
    qtbot.waitUntil(lambda: not empty.isVisible())
    qtbot.wait(20)
    header = table.horizontalHeader()
    widths = [header.sectionSize(c) for c in range(3)]
    # Fills the row without horizontal scrolling; the identifier stays whole.
    assert sum(widths) <= table.viewport().width() + 1
    assert widths[0] >= table.sizeHintForColumn(0)


def test_bundled_cairo_font_is_the_ui_font(qapp):
    from eng_ibrahim.presentation.fonts import resolve_ui_family
    assert resolve_ui_family() == "Cairo"


def test_about_has_linkedin_contact(qtbot, ctx, paths, monkeypatch):
    from PySide6.QtGui import QDesktopServices

    from eng_ibrahim import config
    _admin(ctx, paths)
    page = SettingsPage(ctx)
    qtbot.addWidget(page)
    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    assert page.btn_linkedin.text()
    page.btn_linkedin.click()
    assert opened == [config.DEVELOPER_LINKEDIN]
    assert config.DEVELOPER_LINKEDIN == "https://www.linkedin.com/in/ahmed-ismail-soliman"


def test_user_guide_opens_in_the_current_language(qtbot, ctx, paths):
    from eng_ibrahim.localization.service import guide_path
    from eng_ibrahim.presentation.widgets.help_dialog import HelpDialog
    _admin(ctx, paths)
    for lang, heading in ((Language.AR, "دليل الاستخدام"), (Language.EN, "User guide")):
        assert guide_path(lang).is_file()
        ctx.localizer.set_language(lang)
        dialog = HelpDialog(ctx)
        qtbot.addWidget(dialog)
        text = dialog.browser.toPlainText()
        assert heading in text and "Ctrl+K" in text



def test_date_fields_read_left_to_right_in_arabic(qtbot, qapp):
    from PySide6.QtCore import QDate, Qt
    from PySide6.QtWidgets import QDateEdit

    from eng_ibrahim.presentation.widgets import date_fields
    handler = date_fields.install(qapp)
    try:
        editor = QDateEdit(QDate(2026, 11, 5))
        editor.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        qtbot.addWidget(editor)
        editor.show()
        qtbot.waitExposed(editor)
        assert editor.layoutDirection() == Qt.LayoutDirection.LeftToRight
        assert editor.text() == "2026-11-05"
    finally:
        qapp.removeEventFilter(handler)


def test_header_click_sorts_table_and_rows_together(qtbot):
    from PySide6.QtCore import QObject

    from eng_ibrahim.presentation.widgets.tables import sort_key, sortable

    assert sort_key("10 قطعة") > sort_key("9 قطعة")          # by value, not text
    assert sort_key("147,600 km") > sort_key("78,560 km")
    assert sort_key("EGP 1,250.00") > sort_key("EGP 999.00")
    assert sort_key("2026-11-05") > sort_key("2026-02-01")   # ISO dates as text
    assert sort_key("—") > sort_key("zzz")                    # blanks last

    class Page(QObject):
        def __init__(self):
            super().__init__()
            self.table = QTableWidget(0, 2)
            self._rows: list = []
            sortable(self.table, self)

        def fill(self, records):
            self._rows = list(records)
            self.table.setRowCount(len(records))
            for i, (code, qty) in enumerate(records):
                self.table.setItem(i, 0, QTableWidgetItem(code))
                self.table.setItem(i, 1, QTableWidgetItem(f"{qty} قطعة"))

    page = Page()
    qtbot.addWidget(page.table)
    page.fill([("A", 9), ("B", 10), ("C", 2)])
    page.table.setCurrentCell(0, 0)  # record A selected
    page.table.horizontalHeader().sectionClicked.emit(1)
    assert [r[0] for r in page._rows] == ["C", "A", "B"]
    assert [page.table.item(i, 0).text() for i in range(3)] == ["C", "A", "B"]
    assert page._rows[page.table.currentRow()][0] == "A"  # selection follows the record
    page.table.horizontalHeader().sectionClicked.emit(1)  # second click: descending
    assert [r[0] for r in page._rows] == ["B", "A", "C"]
    # A refresh keeps the chosen order.
    page.fill([("D", 1), ("E", 50)])
    qtbot.waitUntil(lambda: page._rows[0][0] == "E")
    assert page.table.item(0, 0).text() == "E"


def test_date_time_fields_keep_section_order_in_rtl(qtbot, qapp):
    from PySide6.QtCore import QDateTime, Qt
    from PySide6.QtWidgets import QDateTimeEdit, QDialog, QFormLayout

    from eng_ibrahim.presentation.widgets import date_fields
    handler = date_fields.install(qapp)
    previous = qapp.layoutDirection()
    qapp.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    try:
        dialog = QDialog()
        qtbot.addWidget(dialog)
        edit = QDateTimeEdit(QDateTime.fromString("2026-11-05T08:10", "yyyy-MM-ddTHH:mm"))
        edit.setDisplayFormat("yyyy-MM-dd HH:mm")  # set while still RTL, as in the forms
        QFormLayout(dialog).addRow("x", edit)
        dialog.show()
        qtbot.waitExposed(dialog)
        assert edit.text() == "2026-11-05 08:10"
    finally:
        qapp.setLayoutDirection(previous)
        qapp.removeEventFilter(handler)
