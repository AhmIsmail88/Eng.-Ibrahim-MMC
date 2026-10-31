"""Meter readings: monotonic cumulative counters and corrections (SPEC 7)."""
from __future__ import annotations

import pytest

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.meter_service import MeterService
from eng_ibrahim.domain.enums import UserRole

PASSWORD = "Admin#2026"


@pytest.fixture
def meters(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    auth = AuthService(ctx.db)
    admin = auth.authenticate("admin", PASSWORD).value
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    location = masters.locations()[0]
    assets = AssetService(ctx.db)
    asset_id = assets.create(admin, AssetInput(
        asset_code="PMP-201", asset_name_ar="مضخة 201", category_id=category.id,
        location_id=location.id, meter_type="Runtime Hours", default_meter_unit="h")).value
    service = MeterService(ctx.db)
    meter_id = service.ensure_asset_meter(asset_id)
    return ctx, auth, admin, service, asset_id, meter_id


def test_default_meter_is_created_once(meters):
    _ctx, _auth, _admin, service, asset_id, meter_id = meters
    assert meter_id
    assert service.ensure_asset_meter(asset_id) == meter_id  # idempotent
    rows = service.meters(asset_id)
    assert len(rows) == 1 and rows[0].code == "HOURS" and rows[0].unit_code == "h"


def test_cumulative_reading_cannot_go_backwards(meters):
    _ctx, _auth, admin, service, asset_id, meter_id = meters
    assert service.add_reading(admin, asset_id, meter_id, "100", "2026-01-01T08:00").ok
    back = service.add_reading(admin, asset_id, meter_id, "90", "2026-01-02T08:00")
    assert back.error_code == "err.meter_decrease"
    assert service.add_reading(admin, asset_id, meter_id, "110", "2026-01-03T08:00").ok


def test_documented_correction_allows_a_lower_value(meters):
    _ctx, _auth, admin, service, asset_id, meter_id = meters
    first = service.add_reading(admin, asset_id, meter_id, "100", "2026-01-01T08:00").value
    correction = service.add_reading(
        admin, asset_id, meter_id, "80", "2026-01-01T09:00",
        notes="عداد استُبدل", correction_of_id=first)
    assert correction.ok


def test_reading_values_are_validated(meters):
    _ctx, _auth, admin, service, asset_id, meter_id = meters
    for bad in ("abc", "-5", "", "NaN"):
        assert service.add_reading(admin, asset_id, meter_id, bad,
                                   "2026-01-01T08:00").error_code == "err.meter_value_invalid"
    assert service.add_reading(admin, asset_id, meter_id, "5", "").error_code == (
        "err.reading_date_required")


def test_viewer_cannot_add_readings(meters):
    _ctx, auth, admin, service, asset_id, meter_id = meters
    assert auth.create_user(admin, "reader", "Reader", UserRole.VIEWER.value, "Reader#2026").ok
    viewer = auth.authenticate("reader", "Reader#2026").value
    result = service.add_reading(viewer, asset_id, meter_id, "50", "2026-01-01T08:00")
    assert result.error_code == "err.permission_denied"
