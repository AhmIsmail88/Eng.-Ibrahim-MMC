"""Work-order lifecycle, numbering, tasks, time and cost (SPEC 10)."""
from __future__ import annotations

import pytest

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.failure_service import FailureService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.work_order_service import WorkOrderService
from eng_ibrahim.domain.enums import UserRole
from eng_ibrahim.domain.policies import wo_state_machine as sm

PASSWORD = "Admin#2026"


@pytest.fixture
def world(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    auth = AuthService(ctx.db)
    admin = auth.authenticate("admin", PASSWORD).value
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    location = masters.locations()[0]
    asset_id = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-301", asset_name_ar="مضخة 301", category_id=category.id,
        location_id=location.id)).value
    tech_id = masters.create_technician(admin, "T-1", "أحمد", hourly_rate_minor=12000,
                                        currency="EGP").value
    orders = WorkOrderService(ctx.db)
    return ctx, auth, admin, masters, asset_id, tech_id, orders


def _new_order(orders, admin, asset_id, tasks=None):
    result = orders.create(admin, asset_id, "CM", "إصلاح مضخة", priority="High",
                           due_at="2026-12-31", tasks=tasks)
    assert result.ok
    return result.value


def test_numbering_is_sequential(world):
    _ctx, _auth, admin, _m, asset_id, _tech, orders = world
    first = orders.detail(_new_order(orders, admin, asset_id))
    second = orders.detail(_new_order(orders, admin, asset_id))
    year = first.number.split("-")[1]
    assert first.number == f"WO-{year}-000001"
    assert second.number == f"WO-{year}-000002"


def test_full_lifecycle(world):
    _ctx, _auth, admin, _m, asset_id, tech_id, orders = world
    wo_id = _new_order(orders, admin, asset_id, tasks=[("فحص", True)])
    assert orders.detail(wo_id).status == sm.DRAFT

    assert orders.transition(admin, wo_id, sm.OPEN).ok
    assert orders.assign(admin, wo_id, tech_id).ok
    assert orders.detail(wo_id).status == sm.ASSIGNED

    assert orders.transition(admin, wo_id, sm.IN_PROGRESS).ok
    detail = orders.detail(wo_id)
    assert detail.actual_start_at

    task = detail.tasks[0]
    assert orders.transition(admin, wo_id, sm.COMPLETED,
                             equipment_returned=True).error_code == "err.wo_tasks_incomplete"
    assert orders.set_task_result(admin, wo_id, task.id, "تم", True).ok
    assert orders.transition(admin, wo_id, sm.COMPLETED, equipment_returned=True).ok
    assert orders.transition(admin, wo_id, sm.CLOSED, closeout_notes="ok").ok

    final = orders.detail(wo_id)
    assert final.status == sm.CLOSED
    assert final.closed_at and final.equipment_returned_to_service is True
    assert [e.to_status for e in final.events] == [
        "Draft", "Open", "Assigned", "InProgress", "Completed", "Closed"]


def test_invalid_transition_is_rejected(world):
    _ctx, _auth, admin, _m, asset_id, _tech, orders = world
    wo_id = _new_order(orders, admin, asset_id)
    assert orders.transition(admin, wo_id, sm.CLOSED).error_code == "err.wo_transition_invalid"


def test_only_admin_closes(world):
    ctx, auth, admin, _m, asset_id, tech_id, orders = world
    assert auth.create_user(admin, "ed", "Editor", UserRole.EDITOR.value, "Editor#2026").ok
    editor = auth.authenticate("ed", "Editor#2026").value
    wo_id = _new_order(orders, admin, asset_id)
    assert orders.transition(editor, wo_id, sm.OPEN).ok
    assert orders.transition(editor, wo_id, sm.IN_PROGRESS).ok
    assert orders.transition(editor, wo_id, sm.COMPLETED,
                             equipment_returned=False).ok
    assert orders.transition(editor, wo_id, sm.CLOSED).error_code == (
        "err.wo_transition_forbidden")


def test_time_logs_and_cost(world):
    _ctx, _auth, admin, _m, asset_id, tech_id, orders = world
    wo_id = _new_order(orders, admin, asset_id)
    assert orders.add_time_log(admin, wo_id, tech_id, "2026-05-01T08:00",
                               "2026-05-01T10:00").ok
    assert orders.add_time_log(admin, wo_id, tech_id, "2026-05-01T09:00",
                               "2026-05-01T11:00").error_code == "err.time_overlap"
    cost = orders.cost(wo_id)
    assert cost.labour_minor == 24000  # 2h * 120.00
    assert cost.parts_minor == 0
    assert cost.completeness == "complete"
    assert cost.currency == "EGP"


def test_failure_conversion_counts_once(world):
    _ctx, auth, admin, _m, asset_id, _tech, orders = world
    failures = FailureService(world[0].db)
    failure_id = failures.create(admin, asset_id, "تسريب من السيل", "2026-05-01T09:00",
                                 priority="High").value
    wo_id = orders.create_from_failure(admin, failure_id).value
    assert orders.detail(wo_id).failure_id == failure_id
    assert failures.get(failure_id).status == "Converted"
    again = orders.create_from_failure(admin, failure_id)
    assert again.error_code == "err.failure_already_converted"


def test_viewer_cannot_change_state(world):
    ctx, auth, admin, _m, asset_id, _tech, orders = world
    assert auth.create_user(admin, "ro", "Reader", UserRole.VIEWER.value, "Reader#2026").ok
    viewer = auth.authenticate("ro", "Reader#2026").value
    wo_id = _new_order(orders, admin, asset_id)
    assert orders.transition(viewer, wo_id, sm.OPEN).error_code == "err.permission_denied"
    assert orders.list() and orders.list(status=sm.DRAFT)


def test_foreign_currency_labour_is_excluded_from_cost(world):
    _ctx, _auth, admin, masters, asset_id, _tech, orders = world
    usd_tech = masters.create_technician(admin, "T-2", "سامي", hourly_rate_minor=1000,
                                         currency="USD").value
    wo_id = _new_order(orders, admin, asset_id)
    assert orders.add_time_log(admin, wo_id, usd_tech,
                               "2026-03-01T08:00:00Z", "2026-03-01T09:00:00Z").ok
    cost = orders.cost(wo_id)
    assert cost.labour_minor == 0
    assert "labour_currency_excluded" in cost.completeness


def test_cancelled_order_is_read_only_for_time_and_expenses(world):
    _ctx, _auth, admin, _m, asset_id, tech_id, orders = world
    wo_id = _new_order(orders, admin, asset_id)
    assert orders.transition(admin, wo_id, sm.CANCELLED, reason="مكرر").ok
    log = orders.add_time_log(admin, wo_id, tech_id,
                              "2026-03-01T08:00:00Z", "2026-03-01T09:00:00Z")
    assert log.error_code == "err.wo_read_only"
    expense = orders.add_expense(admin, wo_id, "2026-03-01", "Other", 500)
    assert expense.error_code == "err.wo_read_only"


def test_order_can_be_corrected_until_work_starts(world):
    _ctx, _auth, admin, _m, asset_id, tech_id, orders = world
    wo_id = _new_order(orders, admin, asset_id)
    assert orders.update(admin, wo_id, "إصلاح المضخة 3", "تسريب", "Critical",
                         "2027-01-15").ok
    d = orders.detail(wo_id)
    assert (d.title, d.priority, d.due_at, d.description) == (
        "إصلاح المضخة 3", "Critical", "2027-01-15", "تسريب")
    assert orders.update(admin, wo_id, " ", None, "High", None).error_code \
        == "err.wo_title_required"
    orders.transition(admin, wo_id, sm.OPEN)
    orders.assign(admin, wo_id, tech_id)
    assert orders.update(admin, wo_id, "عنوان", None, "High", None).ok  # still Assigned
    orders.transition(admin, wo_id, sm.IN_PROGRESS)
    assert orders.update(admin, wo_id, "تغيير", None, "High", None).error_code \
        == "err.wo_locked_for_edit"
