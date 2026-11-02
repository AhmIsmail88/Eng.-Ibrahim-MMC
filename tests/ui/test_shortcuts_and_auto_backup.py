"""Keyboard shortcuts (SPEC 3.6) and the daily automatic backup (SPEC 23)."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QVBoxLayout

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.backup_service import BackupService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.domain.enums import ThemeMode
from eng_ibrahim.presentation.shell.main_window import MainWindow
from eng_ibrahim.presentation.theme.manager import ThemeManager
from eng_ibrahim.presentation.widgets.dialog_shortcuts import DialogSaveShortcut


@pytest.fixture
def window(qtbot, ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "المهندس", paths.backups,
        "Admin#2026"))
    ctx.current_user = AuthService(ctx.db).sole_active_user()
    theme = ThemeManager(QApplication.instance(), ThemeMode.LIGHT)
    theme.apply()
    w = MainWindow(ctx, theme)
    qtbot.addWidget(w)
    w.show()
    return w


def test_ctrl_n_opens_the_new_form_of_the_current_screen(window, ctx, monkeypatch):
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    AssetService(ctx.db).create(ctx.current_user, AssetInput(
        asset_code="PMP-K1", asset_name_ar="مضخة", category_id=category.id,
        location_id=masters.locations()[0].id))
    opened: list[str] = []
    monkeypatch.setattr(QDialog, "exec",
                        lambda self: opened.append(type(self).__name__) or 0)
    window.navigate("nav.assets")
    window.shortcut_new()
    assert opened == ["AssetDialog"]
    # Screens without a "new" action fall back to a new work order.
    window.navigate("nav.settings")
    window.shortcut_new()
    assert window.current_key() == "nav.work_orders"
    assert opened[-1] == "NewWorkOrderDialog"


def test_ctrl_k_focuses_the_screen_search(window, qtbot):
    window.navigate("nav.assets")
    page = window._pages["nav.assets"]
    page.search.setText("PMP")
    window.activateWindow()
    window.shortcut_search()
    qtbot.waitUntil(lambda: page.search.hasFocus() or QApplication.focusWidget() is page.search)
    assert page.search.selectedText() == "PMP"


def test_ctrl_l_switches_language(window, ctx):
    before = ctx.localizer.language
    window.toggle_language()
    assert ctx.localizer.language != before
    window.toggle_language()
    assert ctx.localizer.language == before


def test_print_and_export_shortcuts_open_reports(window):
    window._click_report("btn_pdf")
    assert window.current_key() == "nav.reports"


def test_ctrl_s_presses_the_save_button_of_the_open_dialog(qtbot):
    dialog = QDialog()
    qtbot.addWidget(dialog)
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                           | QDialogButtonBox.StandardButton.Cancel)
    QVBoxLayout(dialog).addWidget(box)
    saved: list[bool] = []
    box.accepted.connect(lambda: saved.append(True))
    dialog.setModal(True)
    dialog.show()
    qtbot.waitExposed(dialog)
    handler = DialogSaveShortcut()
    ctrl_s = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    assert handler.eventFilter(dialog, ctrl_s) is True
    assert saved == [True]
    # Disabled save: Ctrl+S does nothing.
    box.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
    assert handler.eventFilter(dialog, ctrl_s) is False
    assert saved == [True]


def test_window_runs_the_daily_backup_and_clears_the_warning(window, ctx, paths, qtbot):
    assert window.st_backup.objectName() == "statusWarn"  # never backed up
    assert window.run_auto_backup() is True
    qtbot.waitUntil(lambda: not window._backup_running, timeout=20000)
    service = BackupService(ctx.db, paths, ctx.schema_revision)
    assert service.last_backup() is not None
    assert list(service.folder().glob("*.eibak"))
    assert window.st_backup.objectName() != "statusWarn"
    assert window.run_auto_backup() is False  # not due again today
