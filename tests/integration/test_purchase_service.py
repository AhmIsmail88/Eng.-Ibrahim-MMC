"""Purchase requests: approve → receive into the ledger (P1)."""
from __future__ import annotations

import pytest

from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.inventory_service import InventoryService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.purchase_service import PurchaseService

PASSWORD = "Admin#2026"


@pytest.fixture
def world(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    auth = AuthService(ctx.db)
    admin = auth.authenticate("admin", PASSWORD).value
    masters = MasterDataService(ctx.db)
    supplier_id = masters.create_supplier(admin, "SUP-1", "مورد البلي").value
    inventory = InventoryService(ctx.db)
    part_id = inventory.create_part(admin, "BRG-1", "بلي", "pcs").value
    return ctx, admin, supplier_id, part_id, inventory, PurchaseService(ctx.db)


def test_approve_then_receive_posts_stock(world):
    _ctx, admin, supplier_id, part_id, inventory, purchases = world
    request_id = purchases.create(admin, supplier_id, [(part_id, "5", 1000)]).value
    assert purchases.list()[0].status == "Draft"
    assert purchases.approve(admin, request_id).ok

    result = purchases.receive(admin, request_id)
    assert result.ok and result.value == 1
    assert purchases.list()[0].status == "Received"
    part = {p.code: p for p in inventory.list_parts()}["BRG-1"]
    assert part.on_hand == "5" and part.available == "5"
    movement = inventory.movements(part_id=part_id)[0]
    assert movement.type == "RECEIPT" and movement.total_minor == 5000


def test_cannot_receive_twice_or_after_cancel(world):
    _ctx, admin, supplier_id, part_id, _inventory, purchases = world
    request_id = purchases.create(admin, supplier_id, [(part_id, "2", 500)]).value
    assert purchases.receive(admin, request_id).error_code == "err.pr_not_approved"

    purchases.approve(admin, request_id)
    assert purchases.receive(admin, request_id).ok
    assert purchases.receive(admin, request_id).error_code == "err.pr_not_approved"

    other = purchases.create(admin, supplier_id, [(part_id, "1", 500)]).value
    assert purchases.cancel(admin, other, "لم نعد نحتاجه").ok
    assert purchases.approve(admin, other).error_code == "err.pr_status_invalid"


def test_validation(world):
    _ctx, admin, supplier_id, part_id, _inventory, purchases = world
    assert purchases.create(admin, supplier_id, []).error_code == "err.pr_lines_required"
    assert purchases.create(admin, supplier_id, [(part_id, "0", 100)]).error_code == (
        "err.quantity_invalid")
    assert purchases.create(admin, supplier_id, [("missing", "1", 100)]).error_code == (
        "err.part_not_found")
