"""Vehicles workshop screen (UI-007)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QDialog

from eng_ibrahim.application.dto.vehicle import VehicleInput
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.vehicle_service import VehicleService
from eng_ibrahim.presentation.pages.vehicles import VehicleDialog, VehiclesPage

PASSWORD = "Admin#2026"


@pytest.fixture
def world(qtbot, ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    ctx.current_user = AuthService(ctx.db).authenticate("admin", PASSWORD).value
    location_id = MasterDataService(ctx.db).locations()[0].id
    vehicles = VehicleService(ctx.db)
    asset_id = vehicles.create(ctx.current_user, VehicleInput(
        fleet_code="TRK-002", name_ar="شاحنة نقل", location_id=location_id,
        plate_number="XYZ-123", make="Isuzu", fuel_type="Diesel", initial_odometer="78560",
        insurance_expiry=(date.today() + timedelta(days=5)).isoformat())).value
    page = VehiclesPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    return ctx, vehicles, asset_id, page


def test_list_and_profile(world):
    _ctx, _vehicles, asset_id, page = world
    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "TRK-002"
    assert "78,560" in page.table.item(0, 3).text()
    assert page.table.item(0, 5).text() != "—"  # insurance expires in 5 days
    assert page._detail.asset_id == asset_id
    assert "XYZ-123" in page.ov["plate"].text()
    assert page.btn_odometer.isEnabled() and page.btn_plan.isEnabled()


def test_service_plan_and_alert_filter(world):
    ctx, vehicles, asset_id, page = world
    vehicles.add_service_plan(ctx.current_user, asset_id, "زيت", "10000", 6)
    page.refresh()
    assert page.plans.rowCount() == 1
    assert "88,560" in page.plans.item(0, 1).text()
    page.alerts_only.setChecked(True)
    assert page.table.rowCount() == 1  # documents still flag it
    page.search.setText("no-such-vehicle")
    assert page.table.rowCount() == 0 and page._detail is None


def test_edit_dialog_round_trips_the_profile(world, qtbot):
    ctx, _vehicles, _asset_id, page = world
    dialog = VehicleDialog(ctx, MasterDataService(ctx.db).locations(), page._detail)
    qtbot.addWidget(dialog)
    data = dialog.payload()
    assert (data.fleet_code, data.plate_number, data.make, data.fuel_type) == (
        "TRK-002", "XYZ-123", "Isuzu", "Diesel")
    assert data.insurance_expiry == page._detail.insurance_expiry
    assert data.registration_expiry is None


def test_new_vehicle_keeps_the_form_open_on_error(world, monkeypatch):
    _ctx, _vehicles, _asset_id, page = world
    calls = iter([QDialog.DialogCode.Accepted, QDialog.DialogCode.Rejected])
    monkeypatch.setattr(VehicleDialog, "exec", lambda self: next(calls))
    warnings: list[str] = []
    monkeypatch.setattr(page, "_warn", lambda code: warnings.append(code))
    page._new()  # empty form: refused, dialog re-opened, then cancelled
    assert warnings == ["err.fleet_code_required"]
    assert page.table.rowCount() == 1
