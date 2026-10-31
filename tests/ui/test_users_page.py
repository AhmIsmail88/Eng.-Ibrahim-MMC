"""Users screen: role shown, self password change wired (ADR-025)."""
from __future__ import annotations

from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.presentation.pages.users import UsersPage

PASSWORD = "Admin#2026"


def _seed(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    admin = AuthService(ctx.db).authenticate("admin", PASSWORD).value
    ctx.current_user = admin
    return admin


def test_page_shows_current_user_and_allows_self_change(qtbot, ctx, paths):
    _seed(ctx, paths)
    page = UsersPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert "Manager" in page.hint.text()
    assert page.btn_self.isEnabled()
    assert page.table.rowCount() == 1


def test_password_change_service_call(qtbot, ctx, paths):
    _seed(ctx, paths)
    result = AuthService(ctx.db).change_password(ctx.current_user.id, PASSWORD, "NewPass#2026")
    assert result.ok
    assert AuthService(ctx.db).authenticate("admin", "NewPass#2026").ok
