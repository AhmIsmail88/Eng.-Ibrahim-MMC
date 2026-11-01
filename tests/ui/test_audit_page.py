"""Audit log screen: read-only rows + entity filter (UI-022)."""
from __future__ import annotations

from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.presentation.pages.audit import AuditPage

PASSWORD = "Admin#2026"


def _seed(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    ctx.current_user = AuthService(ctx.db).authenticate("admin", PASSWORD).value


def test_audit_rows_and_filter(qtbot, ctx, paths):
    _seed(ctx, paths)
    page = AuditPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert page.table.rowCount() >= 1
    assert page.table.item(0, 2).text()          # action column is filled
    page.filter.setCurrentIndex(0)
    assert page.table.rowCount() >= 1
