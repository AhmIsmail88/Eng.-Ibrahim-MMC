"""Marking a work-order task done from the UI (P0 blocker)."""
from __future__ import annotations

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.work_order_service import WorkOrderService
from eng_ibrahim.domain.policies import wo_state_machine as sm
from eng_ibrahim.presentation.pages.work_orders import WorkOrdersPage

PASSWORD = "Admin#2026"


def test_toggle_task_lets_the_order_complete(qtbot, ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    auth = AuthService(ctx.db)
    admin = auth.authenticate("admin", PASSWORD).value
    ctx.current_user = admin
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    asset_id = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-T1", asset_name_ar="مضخة", category_id=category.id,
        location_id=masters.locations()[0].id)).value
    orders = WorkOrderService(ctx.db)
    wo_id = orders.create(admin, asset_id, "CM", "إصلاح", tasks=[("فحص", True)]).value
    orders.transition(admin, wo_id, sm.OPEN)
    orders.transition(admin, wo_id, sm.IN_PROGRESS)

    page = WorkOrdersPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    page.table.selectRow(0)
    assert page._detail is not None

    page.tasks.selectRow(0)
    page._toggle_task()
    detail = orders.detail(wo_id)
    assert detail.tasks[0].is_completed is True
    assert orders.transition(admin, wo_id, sm.COMPLETED, equipment_returned=True).ok

    page._detail = orders.detail(wo_id)
    page._render()
    page.tasks.selectRow(0)
    page._toggle_task()
    assert orders.detail(wo_id).tasks[0].is_completed is False


def test_every_transition_button_has_a_label(qtbot, ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    admin = AuthService(ctx.db).authenticate("admin", PASSWORD).value
    ctx.current_user = admin
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    asset_id = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-T2", asset_name_ar="مضخة", category_id=category.id,
        location_id=masters.locations()[0].id)).value
    orders = WorkOrderService(ctx.db)
    wo_id = orders.create(admin, asset_id, "CM", "إصلاح").value
    orders.transition(admin, wo_id, sm.OPEN)

    page = WorkOrdersPage(ctx)
    qtbot.addWidget(page)
    page.show()
    page.refresh()
    page.table.selectRow(0)
    visible = [b for b in page._buttons.values() if b.isVisibleTo(page)]
    assert visible and all(b.text() for b in visible)
    # "Start" exists separately from "reopen" even though both lead to InProgress.
    assert page._buttons["wo.action.start"].isVisibleTo(page)
    assert not page._buttons["wo.action.reopen"].isVisibleTo(page)

    page._buttons["wo.action.start"].click()
    assert orders.detail(wo_id).status == sm.IN_PROGRESS
