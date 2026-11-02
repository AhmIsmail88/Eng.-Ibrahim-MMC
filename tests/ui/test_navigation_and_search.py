"""Global search (Ctrl+K), dashboard card navigation, scheduled PM generation."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.dto.vehicle import VehicleInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.inventory_service import InventoryService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.pm_service import PMService
from eng_ibrahim.application.services.search_service import SearchService
from eng_ibrahim.application.services.vehicle_service import VehicleService
from eng_ibrahim.application.services.work_order_service import WorkOrderService
from eng_ibrahim.domain.enums import ThemeMode
from eng_ibrahim.domain.policies import wo_state_machine as sm
from eng_ibrahim.presentation.shell.main_window import MainWindow
from eng_ibrahim.presentation.theme.manager import ThemeManager
from eng_ibrahim.presentation.widgets.global_search import GlobalSearchDialog


@pytest.fixture
def world(qtbot, ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "المهندس", paths.backups,
        "Admin#2026"))
    admin = AuthService(ctx.db).authenticate("admin", "Admin#2026").value
    ctx.current_user = admin
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    location_id = masters.locations()[0].id
    pump = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-501", asset_name_ar="مضخة الرفع", category_id=category.id,
        location_id=location_id)).value
    truck = VehicleService(ctx.db).create(admin, VehicleInput(
        fleet_code="TRK-501", name_ar="شاحنة", location_id=location_id,
        plate_number="ABC-501")).value
    orders = WorkOrderService(ctx.db)
    wo = orders.create(admin, pump, "CM", "إصلاح تسريب 501").value
    orders.transition(admin, wo, sm.OPEN)
    inv = InventoryService(ctx.db)
    inv.ensure_default_warehouse()
    part = inv.create_part(admin, "BRG-501", "رولمان 501", "pcs", reorder_point="5").value
    pm = PMService(ctx.db)
    pm.create(admin, asset_id=pump, title="فحص شهري", strategy="Calendar",
              trigger_policy="DATE_ONLY", calendar_interval_value=30,
              calendar_interval_unit="days",
              base_date=(date.today() - timedelta(days=45)).isoformat())
    theme = ThemeManager(QApplication.instance(), ThemeMode.LIGHT)
    theme.apply()
    window = MainWindow(ctx, theme)
    qtbot.addWidget(window)
    window.show()
    return ctx, window, dict(pump=pump, truck=truck, wo=wo, part=part)


def test_search_finds_every_kind_once(world):
    ctx, _window, ids = world
    hits = SearchService(ctx.db).search("501")
    kinds = {(h.kind, h.record_id) for h in hits}
    assert ("asset", ids["pump"]) in kinds and ("vehicle", ids["truck"]) in kinds
    assert ("work_order", ids["wo"]) in kinds and ("part", ids["part"]) in kinds
    # The truck is an asset too, but it is listed once, as a vehicle.
    assert ("asset", ids["truck"]) not in kinds
    assert SearchService(ctx.db).search("5") == []  # too short


def test_search_by_plate_and_open_each_result(world):
    ctx, window, ids = world
    assert [h.kind for h in SearchService(ctx.db).search("ABC")] == ["vehicle"]
    for kind, key in (("asset", "pump"), ("vehicle", "truck"), ("work_order", "wo"),
                      ("part", "part")):
        assert window.open_record(kind, ids[key]) is True
    assert window.current_key() == "nav.spare_parts"
    window.open_record("work_order", ids["wo"])
    assert window._pages["nav.work_orders"]._detail.id == ids["wo"]


def test_dialog_enter_opens_the_first_result(world, qtbot):
    ctx, window, ids = world
    dialog = GlobalSearchDialog(ctx, window, text="PMP-501")
    qtbot.addWidget(dialog)
    opened: list[tuple[str, str]] = []
    dialog.chosen.connect(lambda kind, rid: opened.append((kind, rid)))
    dialog._open(dialog.results.item(0))
    assert opened == [("asset", ids["pump"])]


def test_dashboard_cards_open_filtered_lists(world):
    _ctx, window, _ids = world
    dashboard = window._pages["nav.dashboard"]
    dashboard.card_pm_overdue.clicked.emit()
    assert window.current_key() == "nav.preventive"
    pm_page = window._pages["nav.preventive"]
    assert pm_page.table.rowCount() == 1 and pm_page.due_state.currentData() == "Overdue"
    dashboard.card_low.clicked.emit()
    assert window._pages["nav.spare_parts"].low_only.isChecked()
    dashboard.card_wos.clicked.emit()
    wo_page = window._pages["nav.work_orders"]
    assert wo_page.table.rowCount() == int(dashboard.card_wos.value.text())


def test_board_shows_all_categories_by_default(world):
    _ctx, window, _ids = world
    assert window._pages["nav.dashboard"].cat.currentData() is None


def test_window_runs_daily_pm_generation(world):
    ctx, window, _ids = world
    assert window.run_pm_generation() == 1
    assert window.run_pm_generation() == 0  # once a day
    drafts = [w for w in WorkOrderService(ctx.db).list() if w.type == "PM"]
    assert len(drafts) == 1 and drafts[0].status == "Draft"
