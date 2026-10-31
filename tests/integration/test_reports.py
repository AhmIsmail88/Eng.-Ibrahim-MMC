"""Reports: data + PDF/XLSX files (SPEC 17)."""
from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.inventory_service import InventoryService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.application.services.pm_service import PMService
from eng_ibrahim.application.services.report_service import ReportService
from eng_ibrahim.application.services.work_order_service import WorkOrderService
from eng_ibrahim.domain.policies import wo_state_machine as sm
from eng_ibrahim.infrastructure.exports.pdf_renderer import write_pdf
from eng_ibrahim.infrastructure.exports.xlsx_renderer import write_xlsx

PASSWORD = "Admin#2026"


@pytest.fixture
def world(ctx, paths):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "Manager", paths.backups, PASSWORD))
    auth = AuthService(ctx.db)
    admin = auth.authenticate("admin", PASSWORD).value
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    assets = AssetService(ctx.db)
    asset_id = assets.create(admin, AssetInput(
        asset_code="PMP-901", asset_name_ar="مضخة 901", category_id=category.id,
        location_id=masters.locations()[0].id, criticality="High")).value
    orders = WorkOrderService(ctx.db)
    wo_id = orders.create(admin, asset_id, "CM", "إصلاح").value
    orders.transition(admin, wo_id, sm.OPEN)
    orders.transition(admin, wo_id, sm.IN_PROGRESS)
    tech = masters.create_technician(admin, "T-1", "فني", hourly_rate_minor=10000,
                                     currency="EGP").value
    orders.add_time_log(admin, wo_id, tech, "2026-05-01T08:00", "2026-05-01T10:00")
    inv = InventoryService(ctx.db)
    part_id = inv.create_part(admin, "SEAL-1", "سيل ميكانيكي", "pcs").value
    inv.receive(admin, part_id, "5", 10000)
    inv.issue_to_wo(admin, part_id, wo_id, "2")
    return ctx, admin, assets, orders, inv, ReportService(ctx.db), asset_id, wo_id


def test_assets_register(world):
    _ctx, _admin, _assets, _o, _i, reports, _asset, _wo = world
    result = reports.build("REP-001")
    assert result.code == "REP-001"
    assert len(result.rows) == 1 and result.rows[0]["code"] == "PMP-901"
    assert result.totals["count"] == "1"


def test_work_orders_register_respects_period(world):
    _ctx, _admin, _a, _o, _i, reports, _asset, _wo = world
    today = date.today().isoformat()
    assert len(reports.build("REP-005", date_from=today, date_to=today).rows) == 1
    future = date(2099, 1, 1).isoformat()
    assert reports.build("REP-005", date_from=future).rows == []


def test_stock_balance_after_issue(world):
    _ctx, _admin, _a, _o, _i, reports, _asset, _wo = world
    result = reports.build("REP-009")
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["part"] == "SEAL-1"
    assert row["on_hand"] == "3" and row["value"] == "300.00"
    assert result.totals["value"] == "300.00"


def test_maintenance_cost_combines_labour_and_parts(world):
    _ctx, _admin, _a, _o, _i, reports, _asset, _wo = world
    result = reports.build("REP-013", date_from="2020-01-01", date_to="2099-01-01")
    row = result.rows[0]
    assert row["parts"] == "200.00"
    assert row["labour"] == "200.00"
    assert row["total"] == "400.00"


def test_xlsx_and_pdf_are_real_files(world, tmp_path):
    _ctx, _admin, _a, _o, _i, reports, _asset, _wo = world
    report = reports.build("REP-001")
    xlsx = tmp_path / "report.xlsx"
    write_xlsx(xlsx, report, "سجل المعدات", ["الكود", "الاسم", "الفئة", "الموقع",
                                            "الخطورة", "الحالة", "الحالة الفنية"],
               ["ENG. IBRAHIM"], {"totals": "الإجماليات"})
    assert xlsx.exists() and xlsx.read_bytes()[:2] == b"PK"

    QApplication.instance() or QApplication([])
    pdf = tmp_path / "report.pdf"
    write_pdf(pdf, report, "سجل المعدات", ["الكود", "الاسم", "الفئة", "الموقع",
                                          "الخطورة", "الحالة", "الحالة الفنية"],
              ["ENG. IBRAHIM"], {"totals": "الإجماليات"})
    content = pdf.read_bytes()
    assert content[:4] == b"%PDF" and len(content) > 800


def test_pm_schedule_report(world):
    from datetime import date, timedelta
    _ctx, admin, _a, _o, _i, reports, asset_id, _wo = world
    base = (date.today() - timedelta(days=60)).isoformat()
    assert PMService(_ctx.db).create(
        admin, asset_id=asset_id, title="فحص دوري", strategy="Calendar",
        trigger_policy="DATE_ONLY", calendar_interval_value=30,
        calendar_interval_unit="days", base_date=base).ok
    result = reports.build("REP-003")
    assert result.rows and result.rows[0]["asset"] == "PMP-901"
    assert result.rows[0]["state"] == "Overdue"


def test_work_order_card_report(world):
    _ctx, _admin, _a, _o, _i, reports, _asset, wo_id = world
    result = reports.build("REP-006", wo_id=wo_id)
    labels = [row["label"].strip() for row in result.rows]
    assert "Prepared By" in labels and "Signature / Date" in labels
    assert any("WO-" in row["value"] for row in result.rows)
