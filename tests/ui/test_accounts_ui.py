"""Login dialog + role-based navigation (SPEC 21.3 / ADR-025)."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication, QDialog

from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.domain.enums import ThemeMode, UserRole
from eng_ibrahim.presentation.shell.login_dialog import LoginDialog
from eng_ibrahim.presentation.shell.main_window import MainWindow
from eng_ibrahim.presentation.theme.manager import ThemeManager

PASSWORD = "Admin#2026"


def _onboard(ctx, paths) -> AuthService:
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "المدير", paths.backups, PASSWORD))
    return AuthService(ctx.db)


def test_login_dialog_accepts_valid_credentials(qtbot, ctx, paths):
    auth = _onboard(ctx, paths)
    dlg = LoginDialog(ctx, auth)
    qtbot.addWidget(dlg)
    dlg.username.setText("admin")
    dlg.password.setText("wrong")
    dlg.try_login()
    assert dlg.user is None and not dlg.error.isHidden()

    dlg.password.setText(PASSWORD)
    dlg.try_login()
    assert dlg.user is not None and dlg.user.role == UserRole.ADMIN.value
    assert dlg.result() == QDialog.DialogCode.Accepted


def test_admin_sees_users_nav_and_viewer_does_not(qtbot, ctx, paths):
    auth = _onboard(ctx, paths)
    admin = auth.authenticate("admin", PASSWORD).value
    assert admin is not None

    assert auth.create_user(admin, "reader", "Reader", UserRole.VIEWER.value, "Reader#2026").ok
    viewer = auth.authenticate("reader", "Reader#2026").value
    assert viewer is not None and not viewer.is_admin

    theme = ThemeManager(QApplication.instance(), ThemeMode.LIGHT)
    theme.apply()

    ctx.current_user = viewer
    w_viewer = MainWindow(ctx, theme)
    qtbot.addWidget(w_viewer)
    assert "nav.users" not in w_viewer._nav_buttons
    assert not ctx.can_edit and not ctx.can_print

    ctx.current_user = admin
    w_admin = MainWindow(ctx, theme)
    qtbot.addWidget(w_admin)
    assert "nav.users" in w_admin._nav_buttons
