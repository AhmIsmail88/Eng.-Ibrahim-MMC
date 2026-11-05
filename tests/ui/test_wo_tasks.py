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


def test_time_downtime_and_expense_forms(qtbot, ctx, paths):
    from PySide6.QtCore import QDateTime

    from eng_ibrahim.presentation.pages.work_orders import (
        DowntimeDialog,
        ExpenseDialog,
        TimeLogDialog,
    )
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    admin = AuthService(ctx.db).authenticate("admin", PASSWORD).value
    ctx.current_user = admin
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    asset_id = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-T3", asset_name_ar="مضخة", category_id=category.id,
        location_id=masters.locations()[0].id)).value
    tech = masters.create_technician(admin, "T-7", "سعيد", hourly_rate_minor=6000,
                                     currency="EGP").value
    supplier = masters.create_supplier(admin, "SUP-7", "ورشة خارجية").value
    orders = WorkOrderService(ctx.db)
    wo_id = orders.create(admin, asset_id, "CM", "إصلاح").value
    orders.transition(admin, wo_id, sm.OPEN)

    # Time: "Travel" chosen from the list, dates from pickers.
    time = TimeLogDialog(ctx, masters.technicians())
    qtbot.addWidget(time)
    time.category.setCurrentIndex(time.category.findData("Travel"))
    start = QDateTime.fromString("2026-03-01T08:00", "yyyy-MM-ddTHH:mm")
    time.start.setDateTime(start)
    time.end.setDateTime(start.addSecs(2 * 3600))
    assert orders.add_time_log(admin, wo_id, **time.payload()).ok
    log = orders.detail(wo_id).time_logs[0]
    assert (log.category, log.minutes) == ("Travel", 120)
    assert time.payload()["technician_id"] == tech

    # Downtime: planned, with a reason, linked to the order.
    from eng_ibrahim.application.services.downtime_service import DowntimeService
    down = DowntimeDialog(ctx)
    qtbot.addWidget(down)
    down.kind.setCurrentIndex(down.kind.findData("planned"))
    down.reason.setText("إيقاف مخطط لتغيير الجلاند")
    assert DowntimeService(ctx.db).start(admin, asset_id, work_order_id=wo_id,
                                         **down.payload()).ok
    event = DowntimeService(ctx.db).open_event(asset_id)
    assert event.downtime_type == "planned" and event.reason and event.work_order_id == wo_id
    assert event.started_at.endswith("Z")

    # Expense: dated in the past, with a supplier.
    expense = ExpenseDialog(ctx, masters.suppliers())
    qtbot.addWidget(expense)
    expense.amount.setValue(350)
    expense.date.setDate(expense.date.date().addDays(-3))
    expense.supplier.setCurrentIndex(expense.supplier.findData(supplier))
    payload = expense.payload()
    assert payload["supplier_id"] == supplier and payload["amount_minor"] == 35000
    assert orders.add_expense(admin, wo_id, **payload).ok
    assert orders.cost(wo_id).external_minor == 35000


def test_attachments_on_work_orders_and_failures(qtbot, ctx, paths, tmp_path):
    from eng_ibrahim.application.services.attachment_service import AttachmentService
    from eng_ibrahim.application.services.failure_service import FailureService
    from eng_ibrahim.presentation.pages.failures import FailuresPage
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    admin = AuthService(ctx.db).authenticate("admin", PASSWORD).value
    ctx.current_user = admin
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    asset_id = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-T4", asset_name_ar="مضخة", category_id=category.id,
        location_id=masters.locations()[0].id)).value
    photo = tmp_path / "leak.png"
    photo.write_bytes(b"\x89PNG fake image")
    orders = WorkOrderService(ctx.db)
    wo_id = orders.create(admin, asset_id, "CM", "تسريب").value
    page = WorkOrdersPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    page.table.setCurrentCell(0, 0)
    assert page.attach_panel.owner_id == wo_id
    assert page.attach_panel.add_file(photo)
    assert page.attach_panel.table.rowCount() == 1

    failure = FailureService(ctx.db).create(admin, asset_id, "صوت عالي",
                                            "2026-03-01T08:00:00Z").value
    failures = FailuresPage(ctx)
    qtbot.addWidget(failures)
    failures.refresh()
    failures.table.setCurrentCell(0, 0)
    assert failures.attach_panel.owner_id == failure
    assert failures.attach_panel.add_file(photo)
    service = AttachmentService(ctx.db, paths.root)
    assert len(service.list("failure", failure)) == 1
    assert len(service.list("work_order", wo_id)) == 1
    # An attachment never points at a record that does not exist.
    assert service.add(admin, "work_order", "no-such-id", photo).error_code == "err.not_found"
