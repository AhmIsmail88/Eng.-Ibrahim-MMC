"""Vehicles workshop (SPEC 6): fleet profile, odometer rules, km-or-months service plans."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from eng_ibrahim.application.dto.vehicle import DOC_EXPIRED, DOC_SOON, VehicleInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.pm_service import PMService
from eng_ibrahim.application.services.vehicle_service import VehicleService
from eng_ibrahim.domain.enums import UserRole
from eng_ibrahim.domain.policies import pm_schedule as sched

PASSWORD = "Admin#2026"


@pytest.fixture
def world(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    auth = AuthService(ctx.db)
    admin = auth.authenticate("admin", PASSWORD).value
    location = MasterDataService(ctx.db).locations()[0]
    return ctx, auth, admin, location.id, VehicleService(ctx.db)


def _truck(location_id, **kw):
    data = dict(fleet_code=" TRK-002 ", name_ar="شاحنة نقل", location_id=location_id,
                plate_number="ن ق ل 123", make="Isuzu", model="NPR", year=2021,
                fuel_type="Diesel", initial_odometer="78560")
    data.update(kw)
    return VehicleInput(**data)


def test_create_writes_asset_profile_and_odometer_together(world):
    ctx, _auth, admin, location_id, vehicles = world
    asset_id = vehicles.create(admin, _truck(location_id)).value
    detail = vehicles.detail(asset_id)
    assert detail.fleet_code == "TRK-002" and detail.asset_code == "TRK-002"
    assert detail.odometer == "78560" and detail.meter_id
    asset = AssetService(ctx.db).detail(asset_id)
    assert asset.meter_type == "Kilometer"
    # The plate is searchable from the general asset list too.
    assert [r.code for r in AssetService(ctx.db).list(query="123")] == ["TRK-002"]


def test_fleet_code_is_unique_and_nothing_half_written(world):
    ctx, _auth, admin, location_id, vehicles = world
    assert vehicles.create(admin, _truck(location_id)).ok
    again = vehicles.create(admin, _truck(location_id, plate_number="other"))
    assert again.error_code == "err.fleet_code_exists"
    assert len(AssetService(ctx.db).list()) == 1


def test_validation(world):
    _ctx, _auth, admin, location_id, vehicles = world
    assert vehicles.create(admin, _truck(location_id, fleet_code=" ")).error_code \
        == "err.fleet_code_required"
    assert vehicles.create(admin, _truck(location_id, year=1800)).error_code \
        == "err.vehicle_year_invalid"
    assert vehicles.create(admin, _truck(location_id, fuel_type="Steam")).error_code \
        == "err.fuel_type_invalid"
    assert vehicles.create(admin, _truck(location_id, insurance_expiry="31/12/2026")) \
        .error_code == "err.date_invalid"


def test_odometer_cannot_go_backwards(world):
    _ctx, _auth, admin, location_id, vehicles = world
    asset_id = vehicles.create(admin, _truck(location_id)).value
    later = (date.today() + timedelta(days=1)).isoformat() + "T08:00:00"
    assert vehicles.add_odometer(admin, asset_id, "70000", later).error_code \
        == "err.meter_decrease"
    assert vehicles.add_odometer(admin, asset_id, "79000", later).ok
    assert vehicles.detail(asset_id).odometer == "79000"


def test_km_or_months_plan_is_due_on_whichever_comes_first(world):
    ctx, _auth, admin, location_id, vehicles = world
    asset_id = vehicles.create(admin, _truck(location_id)).value
    plan_id = vehicles.add_service_plan(admin, asset_id, "زيت وفلتر", "10000", 6).value
    plan = PMService(ctx.db).detail(plan_id)
    assert plan.trigger_policy == "FIRST_DUE"
    assert plan.next_due_meter == "88560"
    assert vehicles.list()[0].service_state == sched.NOT_DUE
    # Driving past the km threshold makes it due long before the 6 months.
    tomorrow = (date.today() + timedelta(days=1)).isoformat() + "T08:00:00"
    vehicles.add_odometer(admin, asset_id, "88600", tomorrow)
    row = vehicles.list()[0]
    assert row.service_state in (sched.DUE, sched.OVERDUE)
    assert vehicles.list(alerts_only=True)
    assert PMService(ctx.db).generate(admin, plan_id).ok


def test_plan_needs_an_interval(world):
    _ctx, _auth, admin, location_id, vehicles = world
    asset_id = vehicles.create(admin, _truck(location_id)).value
    assert vehicles.add_service_plan(admin, asset_id, "x", "", None).error_code \
        == "err.vehicle_plan_interval"


def test_document_expiry_flags(world):
    _ctx, _auth, admin, location_id, vehicles = world
    soon = (date.today() + timedelta(days=10)).isoformat()
    past = (date.today() - timedelta(days=1)).isoformat()
    vehicles.create(admin, _truck(location_id, insurance_expiry=soon))
    vehicles.create(admin, _truck(location_id, fleet_code="CAR-1", initial_odometer=None,
                                  registration_expiry=past))
    states = {r.fleet_code: r.doc_state for r in vehicles.list()}
    assert states == {"CAR-1": DOC_EXPIRED, "TRK-002": DOC_SOON}


def test_update_changes_profile_and_asset(world):
    ctx, _auth, admin, location_id, vehicles = world
    asset_id = vehicles.create(admin, _truck(location_id)).value
    assert vehicles.update(admin, asset_id, _truck(
        location_id, plate_number="أ ب ج 999", assigned_driver="سائق 1",
        name_ar="شاحنة نقل المياه")).ok
    detail = vehicles.detail(asset_id)
    assert detail.plate_number == "أ ب ج 999" and detail.assigned_driver == "سائق 1"
    assert AssetService(ctx.db).detail(asset_id).name_ar == "شاحنة نقل المياه"


def test_viewer_cannot_create(world):
    _ctx, auth, admin, location_id, vehicles = world
    viewer = auth.create_user(admin, "viewer", "Viewer", UserRole.VIEWER.value,
                              "Viewer#2026").value
    assert vehicles.create(viewer, _truck(location_id)).error_code == "err.permission_denied"
