"""PM plans: creation, due state, generation idempotency, completion (SPEC 9)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.meter_service import MeterService
from eng_ibrahim.application.services.pm_service import PMService
from eng_ibrahim.application.services.work_order_service import WorkOrderService
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
    assets = AssetService(ctx.db)
    asset_id = assets.create(admin, AssetInput(
        asset_code="PMP-501", asset_name_ar="مضخة 501", category_id=category.id,
        location_id=location.id, criticality="High")).value
    return ctx, admin, masters, assets, asset_id, PMService(ctx.db), WorkOrderService(ctx.db)


def _overdue_plan(pm, admin, asset_id, **kw):
    base = date.today() - timedelta(days=60)
    params = dict(asset_id=asset_id, title="فحص الرولمان", strategy="Calendar",
                  trigger_policy="DATE_ONLY", calendar_interval_value=30,
                  calendar_interval_unit="days", base_date=base.isoformat(),
                  warning_days=7, tasks=[("فحص البلي", True), ("تزييت", False)])
    params.update(kw)
    result = pm.create(admin, **params)
    assert result.ok, result.error_code
    return result.value


def test_plan_numbering_and_next_due(world):
    _ctx, admin, _m, _a, asset_id, pm, _o = world
    plan_id = _overdue_plan(pm, admin, asset_id)
    detail = pm.detail(plan_id)
    assert detail.code.startswith("PM-0000")
    assert len(detail.tasks) == 2
    assert detail.next_due_date == (date.today() - timedelta(days=30)).isoformat()


def test_not_due_plan_refuses_generation(world):
    _ctx, admin, _m, _a, asset_id, pm, _o = world
    result = pm.create(admin, asset_id=asset_id, title="بعيد", strategy="Calendar",
                       trigger_policy="DATE_ONLY", calendar_interval_value=12,
                       calendar_interval_unit="months", base_date=date.today().isoformat())
    plan_id = result.value
    assert pm.generate(admin, plan_id).error_code == "err.pm_not_due"


def test_generation_is_idempotent(world):
    _ctx, admin, _m, _a, asset_id, pm, orders = world
    plan_id = _overdue_plan(pm, admin, asset_id)
    first = pm.generate(admin, plan_id)
    assert first.ok and first.value
    second = pm.generate(admin, plan_id)
    assert second.ok and second.value == first.value
    wo = orders.detail(first.value)
    assert wo.type == "PM" and len(wo.tasks) == 2


def test_completion_advances_next_due(world):
    _ctx, admin, _m, _a, asset_id, pm, orders = world
    plan_id = _overdue_plan(pm, admin, asset_id)
    wo_id = pm.generate(admin, plan_id).value
    orders.transition(admin, wo_id, sm.OPEN)
    orders.transition(admin, wo_id, sm.IN_PROGRESS)
    for task in orders.detail(wo_id).tasks:
        orders.set_task_result(admin, wo_id, task.id, "تم", True)
    assert orders.transition(admin, wo_id, sm.COMPLETED, equipment_returned=True).ok

    plan = pm.detail(plan_id)
    expected = (date.today() + timedelta(days=30)).isoformat()
    assert plan.next_due_date == expected
    assert plan.occurrences[0].status == "Completed"
    assert plan.occurrences[0].wo_number


def test_paused_plan_cannot_generate(world):
    _ctx, admin, _m, _a, asset_id, pm, _o = world
    plan_id = _overdue_plan(pm, admin, asset_id)
    assert pm.set_status(admin, plan_id, "Paused").ok
    assert pm.generate(admin, plan_id).error_code == "err.pm_paused"


def test_skip_records_and_advances(world):
    _ctx, admin, _m, _a, asset_id, pm, _o = world
    plan_id = _overdue_plan(pm, admin, asset_id)
    before = pm.detail(plan_id).next_due_date
    assert pm.skip(admin, plan_id, "المعدة خارج الخدمة").ok
    after = pm.detail(plan_id)
    assert after.next_due_date > before
    assert after.occurrences[0].status == "Skipped"


def test_meter_plan_waits_for_reading(world):
    ctx, admin, _m, _a, asset_id, pm, _o = world
    meter_id = MeterService(ctx.db).ensure_asset_meter(asset_id)
    if meter_id is None:
        from eng_ibrahim.infrastructure.database.orm_models import Asset
        with ctx.db.unit_of_work() as s:
            s.get(Asset, asset_id).meter_type = "Runtime Hours"
            s.get(Asset, asset_id).default_meter_unit = "h"
        meter_id = MeterService(ctx.db).ensure_asset_meter(asset_id)
    plan_id = pm.create(admin, asset_id=asset_id, title="كل 500 ساعة", strategy="Meter",
                        trigger_policy="METER_ONLY", meter_id=meter_id,
                        meter_interval_value="500", base_meter_value="0").value
    assert pm.generate(admin, plan_id).error_code == "err.pm_no_meter"

    MeterService(ctx.db).add_reading(admin, asset_id, meter_id, "600", "2026-05-01T08:00")
    assert pm.generate(admin, plan_id).ok
