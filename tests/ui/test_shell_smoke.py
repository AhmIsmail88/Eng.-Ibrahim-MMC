import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.domain.enums import ThemeMode
from eng_ibrahim.presentation.shell.first_run_wizard import FirstRunWizard
from eng_ibrahim.presentation.shell.main_window import NAV_ITEMS, MainWindow
from eng_ibrahim.presentation.theme.manager import ThemeManager, build_qss


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


def test_navigation_covers_all_sections(window):
    assert window.current_key() == "nav.dashboard"
    for key, _g, _p in NAV_ITEMS:
        window.navigate(key)
        assert window.current_key() == key
        assert window._nav_buttons[key].isChecked()


def test_sidebar_matches_spec_menu(window):
    keys = [k for k, _, _ in NAV_ITEMS]
    assert keys == ["nav.dashboard", "nav.assets", "nav.work_orders", "nav.preventive",
                    "nav.corrective", "nav.pm_calendar", "nav.vehicles", "nav.checklists", "nav.spare_parts",
                    "nav.technicians", "nav.master_data", "nav.audit", "nav.notifications", "nav.suppliers", "nav.reports", "nav.users",
                    "nav.settings"]


def test_language_switch_rtl_ltr_and_persistence(window, ctx):
    window.set_language("ar")
    assert window.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert window._nav_buttons["nav.settings"].toolTip() == "الإعدادات"
    window.set_language("en")
    assert window.layoutDirection() == Qt.LayoutDirection.LeftToRight
    assert window._nav_buttons["nav.settings"].toolTip() == "Settings"
    assert ctx.prefs.get("language") == "en"
    assert "Dashboard" in window._pages["nav.dashboard"].title.text()


def test_theme_toggle_persists_and_changes_stylesheet(window, ctx):
    before = QApplication.instance().styleSheet()
    window.toggle_theme()
    assert ctx.prefs.get("theme") == "dark"
    assert QApplication.instance().styleSheet() != before
    assert "#101722" in QApplication.instance().styleSheet()
    window.toggle_theme()
    assert ctx.prefs.get("theme") == "light"


def test_no_dead_controls_search_and_bell_disabled(window):
    assert not window.search.isEnabled() and not window.btn_notifications.isEnabled()
    assert window.btn_theme.isEnabled() and window.btn_settings.isEnabled()


def test_status_bar_shows_real_state(window):
    assert "OK" in window.st_db.text() or "سليمة" in window.st_db.text()
    assert window.ctx.schema_revision in window.st_version.text()
    assert "المهندس" in window.st_profile.text()


def test_sidebar_collapse_persists(window, ctx):
    wide = window.sidebar.width()
    window.toggle_sidebar()
    assert window.sidebar.width() < wide and ctx.prefs.get("sidebar_collapsed") is True
    window.toggle_sidebar()
    assert window.sidebar.width() == wide


def test_window_geometry_saved_on_close(window, ctx):
    window.close()
    g = ctx.prefs.get("window")
    assert g and g["w"] >= 1100 and g["h"] >= 700


def test_window_minimum_size(window):
    assert window.minimumWidth() == 1100 and window.minimumHeight() == 700


def test_qss_defined_for_both_themes():
    assert "#F4F7FB" in build_qss(ThemeMode.LIGHT)
    assert "#101722" in build_qss(ThemeMode.DARK)


def test_wizard_end_to_end(qtbot, ctx, paths):
    wiz = FirstRunWizard(ctx, show_recovery_dialog=False)
    qtbot.addWidget(wiz)
    wiz.show()
    wiz.btn_next.click()                       # welcome -> station
    wiz.btn_next.click()                       # empty station -> blocked
    assert wiz.stack.currentIndex() == 1 and wiz.error.text()
    wiz.station_ar.setText("محطة الاختبار")
    wiz.btn_next.click()                       # -> currency
    wiz.btn_next.click()                       # -> user
    wiz.password.setText("abc12345")
    wiz.password2.setText("different")
    wiz.btn_next.click()
    assert wiz.stack.currentIndex() == 3 and "غير متطابقتين" in wiz.error.text()
    wiz.password.clear()
    wiz.password2.clear()
    wiz.btn_next.click()                       # empty password -> blocked (ADR-025)
    assert wiz.stack.currentIndex() == 3 and wiz.error.text()
    wiz.password.setText("abc12345")
    wiz.password2.setText("abc12345")
    wiz.btn_next.click()                       # -> backup
    wiz.btn_next.click()                       # -> summary
    assert "محطة الاختبار" in wiz.summary.toPlainText()
    wiz.btn_next.click()                       # create
    assert wiz.result() == wiz.DialogCode.Accepted
    assert ctx.settings.is_first_run_completed()


def test_wizard_language_switch(qtbot, ctx):
    wiz = FirstRunWizard(ctx)
    qtbot.addWidget(wiz)
    wiz.lang_combo.setCurrentIndex(wiz.lang_combo.findData("en"))
    assert wiz.btn_next.text() == "Next" and wiz.welcome_title.text() == "Welcome to ENG. IBRAHIM"
    wiz.lang_combo.setCurrentIndex(wiz.lang_combo.findData("ar"))
    assert wiz.btn_next.text() == "التالي"
