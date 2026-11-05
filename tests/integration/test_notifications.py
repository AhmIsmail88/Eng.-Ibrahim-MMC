"""Derived notifications: PM overdue, low stock, overdue WO (SPEC 14)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.inventory_service import InventoryService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.notification_service import NotificationService
from eng_ibrahim.application.services.pm_service import PMService

PASSWORD = "Admin#2026"


@pytest.fixture
def world(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    auth = AuthService(ctx.db)
    admin = auth.authenticate("admin", PASSWORD).value
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    asset_id = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-N1", asset_name_ar="مضخة", category_id=category.id,
        location_id=masters.locations()[0].id)).value
    return ctx, admin, asset_id, NotificationService(ctx.db), PMService(ctx.db)


def test_empty_when_nothing_is_due(world):
    _ctx, _admin, _asset, notices, _pm = world
    assert notices.scan() == []


def test_overdue_pm_and_low_stock_are_reported(world):
    ctx, admin, asset_id, notices, pm = world
    base = (date.today() - timedelta(days=60)).isoformat()
    assert pm.create(admin, asset_id=asset_id, title="فحص", strategy="Calendar",
                     trigger_policy="DATE_ONLY", calendar_interval_value=30,
                     calendar_interval_unit="days", base_date=base).ok
    inv = InventoryService(ctx.db)
    part_id = inv.create_part(admin, "BRG-9", "بلي", "pcs", reorder_point="5").value
    inv.receive(admin, part_id, "2", 1000)

    rows = notices.scan()
    keys = {row.title_key for row in rows}
    assert "notify.pm_overdue" in keys and "notify.low_stock" in keys
    assert rows[0].severity == "critical"


def test_due_soon_plan_appears_without_crashing(ctx, paths):
    """A 'due soon' plan used to raise AttributeError (PlanRow has no `due`)."""
    from datetime import date, timedelta

    from eng_ibrahim.application.dto.asset import AssetInput
    from eng_ibrahim.application.services.asset_service import AssetService
    from eng_ibrahim.application.services.auth_service import AuthService
    from eng_ibrahim.application.services.first_run_service import (
        FirstRunInput,
        FirstRunService,
    )
    from eng_ibrahim.application.services.master_data_service import MasterDataService
    from eng_ibrahim.application.services.notification_service import NotificationService
    from eng_ibrahim.application.services.pm_service import PMService
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "M", paths.backups, "Admin#2026"))
    admin = AuthService(ctx.db).authenticate("admin", "Admin#2026").value
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    asset = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="P-SOON", asset_name_ar="مضخة", category_id=category.id,
        location_id=masters.locations()[0].id)).value
    # Due in 3 days with a 7-day warning window: "due soon".
    PMService(ctx.db).create(admin, asset_id=asset, title="فحص", strategy="Calendar",
                             trigger_policy="DATE_ONLY", calendar_interval_value=30,
                             calendar_interval_unit="days", warning_days=7,
                             base_date=(date.today() - timedelta(days=27)).isoformat())
    notices = NotificationService(ctx.db).scan()
    soon = [n for n in notices if n.title_key == "notify.pm_due"]
    assert len(soon) == 1 and (date.today() + timedelta(days=3)).isoformat() in soon[0].detail
