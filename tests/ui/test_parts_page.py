"""Parts screen and the asset 'parts used' tab (SPEC 5.6, 12)."""
from __future__ import annotations

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.inventory_service import InventoryService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.work_order_service import WorkOrderService
from eng_ibrahim.domain.policies import wo_state_machine as sm
from eng_ibrahim.presentation.pages.assets import AssetsPage
from eng_ibrahim.presentation.pages.parts import PartsPage

PASSWORD = "Admin#2026"


def _seed(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    auth = AuthService(ctx.db)
    admin = auth.authenticate("admin", PASSWORD).value
    ctx.current_user = admin
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    asset_id = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-701", asset_name_ar="مضخة 701", category_id=category.id,
        location_id=masters.locations()[0].id)).value
    return admin, masters, asset_id


def test_parts_page_lists_received_part(qtbot, ctx, paths):
    admin, _masters, _asset = _seed(ctx, paths)
    inv = InventoryService(ctx.db)
    part_id = inv.create_part(admin, "FLT-10", "فلتر زيت", "pcs").value
    assert inv.receive(admin, part_id, "5", 12000).ok

    page = PartsPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "FLT-10"
    assert page.table.item(0, 2).text() == "5"
    assert page.moves.rowCount() == 1


def test_asset_parts_tab_shows_issued_part(qtbot, ctx, paths):
    admin, masters, asset_id = _seed(ctx, paths)
    orders = WorkOrderService(ctx.db)
    wo_id = orders.create(admin, asset_id, "CM", "تغيير فلتر").value
    orders.transition(admin, wo_id, sm.OPEN)
    tech_id = masters.create_technician(admin, "T-7", "سيد", hourly_rate_minor=5000,
                                        currency="EGP").value
    orders.assign(admin, wo_id, tech_id)

    inv = InventoryService(ctx.db)
    part_id = inv.create_part(admin, "FLT-11", "فلتر هواء", "pcs").value
    inv.receive(admin, part_id, "3", 8000)
    assert inv.issue_to_wo(admin, part_id, wo_id, "1").ok

    page = AssetsPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    page.table.selectRow(0)
    assert page._detail is not None
    assert page.parts_table.rowCount() == 1
    assert "FLT-11" in page.parts_table.item(0, 0).text()
    assert page.parts_table.item(0, 4).text() == "سيد"
