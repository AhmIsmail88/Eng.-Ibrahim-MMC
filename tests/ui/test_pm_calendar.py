"""PM calendar grid (UI-012)."""
from __future__ import annotations

from datetime import date, timedelta

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.pm_service import PMService
from eng_ibrahim.presentation.pages.pm_calendar import PMCalendarPage

PASSWORD = "Admin#2026"


def test_month_grid_marks_due_plans(qtbot, ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    admin = AuthService(ctx.db).authenticate("admin", PASSWORD).value
    ctx.current_user = admin
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    asset_id = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-CAL", asset_name_ar="مضخة", category_id=category.id,
        location_id=masters.locations()[0].id)).value
    # due exactly today: base = today - 30 days, interval 30 days
    base = (date.today() - timedelta(days=30)).isoformat()
    assert PMService(ctx.db).create(
        admin, asset_id=asset_id, title="فحص شهري", strategy="Calendar",
        trigger_policy="DATE_ONLY", calendar_interval_value=30,
        calendar_interval_unit="days", base_date=base).ok

    page = PMCalendarPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    texts = [page.grid.item(r, c).text() for r in range(6) for c in range(7)
             if page.grid.item(r, c)]
    assert any("PM-" in text for text in texts)
