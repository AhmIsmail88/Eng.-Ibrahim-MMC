"""Technicians roster: list + enable/disable (UI-016)."""
from __future__ import annotations

from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.presentation.pages.technicians import TechniciansPage

PASSWORD = "Admin#2026"


def _seed(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    admin = AuthService(ctx.db).authenticate("admin", PASSWORD).value
    ctx.current_user = admin
    return admin, MasterDataService(ctx.db)


def test_roster_lists_and_toggles(qtbot, ctx, paths):
    admin, masters = _seed(ctx, paths)
    assert masters.create_technician(admin, "T-1", "أحمد", trade="Mechanical",
                                     hourly_rate_minor=6000, currency="EGP").ok
    page = TechniciansPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "T-1"
    assert page.table.item(0, 4).text() == ctx.tr("users.active")

    page.table.selectRow(0)
    page._toggle()
    assert page.table.item(0, 4).text() == ctx.tr("users.inactive")
    assert list(masters.technicians(active_only=True)) == []
