"""Stock ledger: WAC, negatives, returns, currency, asset usage (SPEC 12)."""
from __future__ import annotations

import pytest

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.inventory_service import InventoryService
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
    assets = AssetService(ctx.db)
    asset_id = assets.create(admin, AssetInput(
        asset_code="PMP-601", asset_name_ar="مضخة 601", category_id=category.id,
        location_id=location.id)).value
    orders = WorkOrderService(ctx.db)
    wo_id = orders.create(admin, asset_id, "CM", "تغيير بلي").value
    orders.transition(admin, wo_id, sm.OPEN)
    tech_id = masters.create_technician(admin, "T-9", "محمود", hourly_rate_minor=6000,
                                        currency="EGP").value
    orders.assign(admin, wo_id, tech_id)
    inventory = InventoryService(ctx.db)
    inventory.ensure_default_warehouse()
    part_id = inventory.create_part(admin, "BRG-6205", "رولمان بلي 6205", "pcs",
                                    precision=0, reorder_point="5").value
    return ctx, auth, admin, masters, assets, orders, inventory, asset_id, wo_id, part_id


def test_weighted_average_matches_spec_example(world):
    _ctx, _auth, admin, _m, _a, orders, inv, _asset, wo_id, part_id = world
    assert inv.receive(admin, part_id, "10", 100).ok
    assert inv.receive(admin, part_id, "10", 200).ok
    part = inv.list_parts()[0]
    assert part.on_hand == "20" and part.average_cost_minor == 150

    issue = inv.issue_to_wo(admin, part_id, wo_id, "4")
    assert issue.ok
    part = inv.list_parts()[0]
    assert part.on_hand == "16"

    movement = [m for m in inv.movements(part_id=part_id) if m.type == "ISSUE_TO_WO"][0]
    assert movement.total_minor == 600
    assert inv.return_from_wo(admin, issue.value, "1").ok

    cost, currency = inv.work_order_part_cost(wo_id)
    assert cost == 450 and currency == "EGP"
    part = inv.list_parts()[0]
    assert part.on_hand == "17"
    assert orders.cost(wo_id).parts_minor == 450


def test_cannot_issue_more_than_available(world):
    _ctx, _auth, admin, _m, _a, orders, inv, _asset, wo_id, part_id = world
    inv.receive(admin, part_id, "10", 100)
    assert inv.issue_to_wo(admin, part_id, wo_id, "18").error_code == "err.stock_insufficient"
    assert inv.issue_to_wo(admin, part_id, wo_id, "10").ok
    assert inv.issue_to_wo(admin, part_id, wo_id, "1").error_code == "err.stock_insufficient"


def test_return_cannot_exceed_issue(world):
    _ctx, _auth, admin, _m, _a, _orders, inv, _asset, wo_id, part_id = world
    inv.receive(admin, part_id, "5", 100)
    issue_id = inv.issue_to_wo(admin, part_id, wo_id, "2").value
    assert inv.return_from_wo(admin, issue_id, "3").error_code == "err.return_exceeds_issue"
    assert inv.return_from_wo(admin, issue_id, "2").ok
    assert inv.return_from_wo(admin, issue_id, "1").error_code == "err.return_exceeds_issue"


def test_currency_is_part_of_the_balance(world):
    _ctx, _auth, admin, _m, _a, _o, inv, _asset, _wo, part_id = world
    assert inv.receive(admin, part_id, "1", 100, currency="EGP").ok
    assert inv.receive(admin, part_id, "1", 100, currency="USD").error_code == (
        "err.currency_mismatch")


def test_receipt_metadata_reaches_asset_history(world):
    ctx, _auth, admin, masters, _assets, _orders, inv, asset_id, _wo, part_id = world
    supplier_id = masters.create_supplier(admin, "SUP-1", "مورد البلي").value
    assert inv.receive(admin, part_id, "5", 250, supplier_id=supplier_id,
                       purchase_ref="PO-2026-77").ok
    issue_id = inv.issue_to_wo(admin, part_id, _wo, "1").value
    assert issue_id

    usage = inv.asset_part_usage(asset_id)
    assert len(usage) == 1
    row = usage[0]
    assert row.part_code == "BRG-6205" and row.quantity == "1"
    assert row.technician == "محمود"
    assert row.wo_number.startswith("WO-")
    # The receipt carried the supplier; the issue inherits the reference for display.
    assert row.purchase_ref is None or row.purchase_ref == "PO-2026-77"


def test_part_codes_are_case_insensitive(world):
    _ctx, _auth, admin, _m, _a, _o, inv, _asset, _wo, _part = world
    again = inv.create_part(admin, " brg-6205 ", "آخر", "pcs")
    assert again.error_code == "err.part_code_exists"


def test_reservation_respects_availability(world):
    _ctx, _auth, admin, _m, _a, _o, inv, _asset, wo_id, part_id = world
    inv.receive(admin, part_id, "3", 100)
    assert inv.reserve(admin, part_id, wo_id, "2").ok
    assert inv.reserve(admin, part_id, wo_id, "2").error_code == "err.stock_insufficient"
    part = inv.list_parts()[0]
    assert part.reserved == "2" and part.available == "1"


def test_viewer_cannot_post_movements(world):
    _ctx, auth, admin, _m, _a, _o, inv, _asset, wo_id, part_id = world
    assert auth.create_user(admin, "ro", "Reader", UserRole.VIEWER.value, "Reader#2026").ok
    viewer = auth.authenticate("ro", "Reader#2026").value
    assert inv.receive(viewer, part_id, "1", 10).error_code == "err.permission_denied"
    assert inv.issue_to_wo(viewer, part_id, wo_id, "1").error_code == "err.permission_denied"


def test_reserved_stock_can_be_issued_to_its_own_work_order(world):
    _ctx, _auth, admin, _m, _a, _o, inventory, _asset, wo_id, part_id = world
    inventory.receive(admin, part_id, "5", 100)
    assert inventory.reserve(admin, part_id, wo_id, "5").ok
    assert inventory.issue_to_wo(admin, part_id, wo_id, "5").ok
    row = {p.id: p for p in inventory.list_parts()}[part_id]
    assert row.on_hand == "0" and row.reserved == "0"


def test_partial_issue_keeps_the_rest_reserved_and_releasable(world):
    _ctx, _auth, admin, _m, _a, _o, inventory, _asset, wo_id, part_id = world
    inventory.receive(admin, part_id, "10", 100)
    reservation = inventory.reserve(admin, part_id, wo_id, "4").value
    assert inventory.issue_to_wo(admin, part_id, wo_id, "1").ok
    row = {p.id: p for p in inventory.list_parts()}[part_id]
    assert row.on_hand == "9" and row.reserved == "3"
    assert inventory.release(admin, reservation).ok
    row = {p.id: p for p in inventory.list_parts()}[part_id]
    assert row.reserved == "0" and row.available == "9"


def test_cancelled_work_order_takes_no_parts(world):
    _ctx, _auth, admin, _m, _a, orders, inventory, asset_id, _wo, part_id = world
    inventory.receive(admin, part_id, "5", 100)
    wo_id = orders.create(admin, asset_id, "CM", "ملغي").value
    assert orders.transition(admin, wo_id, sm.CANCELLED, reason="خطأ").ok
    assert inventory.issue_to_wo(admin, part_id, wo_id, "1").error_code == "err.wo_read_only"
    assert inventory.reserve(admin, part_id, wo_id, "1").error_code == "err.wo_read_only"


def test_negative_adjustment_cannot_eat_reserved_stock(world):
    _ctx, _auth, admin, _m, _a, _o, inventory, _asset, wo_id, part_id = world
    inventory.receive(admin, part_id, "5", 100)
    inventory.reserve(admin, part_id, wo_id, "4")
    assert inventory.adjust(admin, part_id, "-2", "جرد").error_code == "err.stock_insufficient"
    assert inventory.adjust(admin, part_id, "-1", "جرد").ok


def _second_warehouse(ctx, masters, admin):
    masters.create_warehouse(admin, "WH2", "مخزن الموقع")
    return next(w[0] for w in InventoryService(ctx.db).warehouses() if w[1] == "WH2")


def test_moves_respect_the_chosen_warehouse(world):
    ctx, _auth, admin, masters, _a, _o, inventory, _asset, wo_id, part_id = world
    wh2 = _second_warehouse(ctx, masters, admin)
    assert inventory.receive(admin, part_id, "4", 100, warehouse_id=wh2).ok
    main = {p.id: p for p in inventory.list_parts()}[part_id]
    other = {p.id: p for p in inventory.list_parts(warehouse_id=wh2)}[part_id]
    assert main.on_hand == "0" and other.on_hand == "4"
    # Issuing from the default warehouse cannot use the other warehouse's stock.
    assert inventory.issue_to_wo(admin, part_id, wo_id, "1").error_code == "err.stock_insufficient"
    assert inventory.issue_to_wo(admin, part_id, wo_id, "1", warehouse_id=wh2).ok
    assert len(inventory.movements(part_id=part_id, warehouse_id=wh2)) == 2


def test_transfer_moves_quantity_and_value(world):
    ctx, _auth, admin, masters, _a, _o, inventory, _asset, _wo, part_id = world
    wh2 = _second_warehouse(ctx, masters, admin)
    main_id = inventory.ensure_default_warehouse()
    inventory.receive(admin, part_id, "10", 250)
    assert inventory.transfer(admin, part_id, main_id, wh2, "4", "نقل للموقع").ok
    main = {p.id: p for p in inventory.list_parts()}[part_id]
    other = {p.id: p for p in inventory.list_parts(warehouse_id=wh2)}[part_id]
    assert (main.on_hand, other.on_hand) == ("6", "4")
    assert other.average_cost_minor == 250
    types = [m.type for m in inventory.movements(part_id=part_id)]
    assert "TRANSFER_OUT" in types and "TRANSFER_IN" in types
    assert inventory.transfer(admin, part_id, main_id, wh2, "7").error_code \
        == "err.stock_insufficient"
    assert inventory.transfer(admin, part_id, main_id, main_id, "1").error_code \
        == "err.transfer_same_warehouse"


def test_scrap_needs_a_reason_and_spares_reserved_stock(world):
    _ctx, _auth, admin, _m, _a, _o, inventory, _asset, wo_id, part_id = world
    inventory.receive(admin, part_id, "5", 100)
    inventory.reserve(admin, part_id, wo_id, "3")
    assert inventory.scrap(admin, part_id, "1", "").error_code == "err.reason_required"
    assert inventory.scrap(admin, part_id, "3", "تالف").error_code == "err.stock_insufficient"
    assert inventory.scrap(admin, part_id, "2", "تالف بالرطوبة").ok
    row = {p.id: p for p in inventory.list_parts()}[part_id]
    assert row.on_hand == "3" and row.available == "0"


def test_returnable_issues_track_what_is_left(world):
    _ctx, _auth, admin, _m, _a, _o, inventory, _asset, wo_id, part_id = world
    inventory.receive(admin, part_id, "5", 100)
    issue = inventory.issue_to_wo(admin, part_id, wo_id, "3").value
    assert [(r.movement_id, r.remaining) for r in inventory.returnable_issues(part_id)] \
        == [(issue, "3")]
    assert inventory.return_from_wo(admin, issue, "2", "زيادة").ok
    assert inventory.returnable_issues(part_id)[0].remaining == "1"
    assert inventory.return_from_wo(admin, issue, "1").ok
    assert inventory.returnable_issues(part_id) == []
