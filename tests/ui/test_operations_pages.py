"""Work orders and failures screens construct and list real rows."""
from __future__ import annotations

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.failure_service import FailureService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.work_order_service import WorkOrderService
from eng_ibrahim.presentation.pages.failures import FailuresPage
from eng_ibrahim.presentation.pages.preventive import PMPage
from eng_ibrahim.presentation.pages.work_orders import WorkOrdersPage

PASSWORD = "Admin#2026"


def _seed(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    auth = AuthService(ctx.db)
    admin = auth.authenticate("admin", PASSWORD).value
    ctx.current_user = admin
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    asset_id = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-401", asset_name_ar="مضخة 401", category_id=category.id,
        location_id=masters.locations()[0].id)).value
    return admin, asset_id


def test_work_orders_page_lists_created_order(qtbot, ctx, paths):
    admin, asset_id = _seed(ctx, paths)
    WorkOrderService(ctx.db).create(admin, asset_id, "CM", "إصلاح")
    page = WorkOrdersPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert page.table.rowCount() == 1
    assert page.tabs.count() == 4
    page.table.selectRow(0)
    assert page._detail is not None


def test_failures_page_lists_report_and_converts(qtbot, ctx, paths):
    admin, asset_id = _seed(ctx, paths)
    FailureService(ctx.db).create(admin, asset_id, "تسريب", "2026-05-01T08:00")
    page = FailuresPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert page.table.rowCount() == 1
    page.table.selectRow(0)
    assert page.btn_convert.isEnabled()


def test_pm_page_lists_plan_and_state(qtbot, ctx, paths):
    from datetime import date, timedelta

    from eng_ibrahim.application.services.pm_service import PMService

    admin, asset_id = _seed(ctx, paths)
    base = (date.today() - timedelta(days=60)).isoformat()
    assert PMService(ctx.db).create(
        admin, asset_id=asset_id, title="فحص دوري", strategy="Calendar",
        trigger_policy="DATE_ONLY", calendar_interval_value=30,
        calendar_interval_unit="days", base_date=base).ok
    page = PMPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text().startswith("PM-")
    assert page.tabs.count() == 2
