"""Dashboard board: derived states, fault/repair dates, conflicts (SPEC 15.1.1)."""
from __future__ import annotations

import pytest

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.dashboard_service import DashboardService
from eng_ibrahim.application.services.failure_service import FailureService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
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
    ids = {}
    for code in ("PMP-1", "PMP-2", "PMP-3"):
        ids[code] = assets.create(admin, AssetInput(
            asset_code=code, asset_name_ar=f"مضخة {code[-1]}", category_id=category.id,
            location_id=location.id)).value
    return ctx, admin, assets, ids, DashboardService(ctx.db)


def test_running_asset(world):
    _ctx, _admin, _assets, ids, dashboard = world
    board = {row.code: row for row in dashboard.board()}
    row = board["PMP-1"]
    assert row.derived_status == "running" and row.fault_at is None
    assert row.repair_at is None and row.open_wo is None and not row.conflict


def test_faulty_asset_from_open_failure(world):
    ctx, admin, _assets, ids, dashboard = world
    FailureService(ctx.db).create(admin, ids["PMP-2"], "اهتزاز زائد", "2026-05-01T10:00",
                                  priority="Critical")
    row = {r.code: r for r in dashboard.board()}["PMP-2"]
    assert row.derived_status == "faulty"
    assert row.fault_at == "2026-05-01"
    assert row.priority == "Critical"
    assert row.conflict  # recorded In Service, derived faulty


def test_under_maintenance_from_open_work_order(world):
    ctx, admin, _assets, ids, dashboard = world
    orders = WorkOrderService(ctx.db)
    wo_id = orders.create(admin, ids["PMP-3"], "CM", "صيانة").value
    orders.transition(admin, wo_id, sm.OPEN)
    orders.transition(admin, wo_id, sm.IN_PROGRESS)
    row = {r.code: r for r in dashboard.board()}["PMP-3"]
    assert row.derived_status == "under_maintenance"
    assert row.open_wo == orders.detail(wo_id).number


def test_repair_date_comes_from_last_completed_cm(world):
    ctx, admin, _assets, ids, dashboard = world
    orders = WorkOrderService(ctx.db)
    wo_id = orders.create(admin, ids["PMP-1"], "CM", "إصلاح").value
    orders.transition(admin, wo_id, sm.OPEN)
    orders.transition(admin, wo_id, sm.IN_PROGRESS)
    orders.transition(admin, wo_id, sm.COMPLETED, equipment_returned=True)
    row = {r.code: r for r in dashboard.board()}["PMP-1"]
    assert row.repair_at is not None
    assert row.derived_status == "running"


def test_retired_assets_are_hidden_by_default(world):
    ctx, admin, assets, ids, dashboard = world
    assets.change_status(admin, ids["PMP-1"], "Retired", "scrapped")
    assert "PMP-1" not in {r.code for r in dashboard.board()}
    assert "PMP-1" in {r.code for r in dashboard.board(include_retired=True)}


def test_kpis_counts(world):
    ctx, admin, _assets, ids, dashboard = world
    FailureService(ctx.db).create(admin, ids["PMP-2"], "عطل", "2026-05-01T10:00")
    kpis = dashboard.kpis()
    assert kpis.total_assets == 3
    assert kpis.open_failures == 1
    assert kpis.open_work_orders == 0
