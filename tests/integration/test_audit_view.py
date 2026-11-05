"""Audit log reading: period/user filters, paging past 300, CSV export (review F-08/F-23)."""
from __future__ import annotations

import csv

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.audit import write_audit
from eng_ibrahim.application.services.audit_view import AuditFilter, AuditViewService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.infrastructure.database.orm_models import AuditLog


def test_paging_filters_export_and_codes(ctx, paths, tmp_path):
    FirstRunService(ctx.db).complete(FirstRunInput(
        "محطة", "Station", "EGP", "Africa/Cairo", "admin", "M", paths.backups, "Admin#2026"))
    admin = AuthService(ctx.db).authenticate("admin", "Admin#2026").value
    masters = MasterDataService(ctx.db)
    category = next(c for c in masters.categories() if c.code == "PUMP")
    asset_id = AssetService(ctx.db).create(admin, AssetInput(
        asset_code="PMP-900", asset_name_ar="مضخة", category_id=category.id,
        location_id=masters.locations()[0].id)).value
    with ctx.db.unit_of_work() as s:
        for i in range(650):
            write_audit(s, "test", None, f"bulk_{i}", actor_id=admin.id)
        # An old event, outside a recent period; and one that looks like a formula.
        s.add(AuditLog(entity_type="test", action="old", created_at="2020-01-01T00:00:00Z"))
        write_audit(s, "test", None, "=HYPERLINK(\"x\")", actor_id=admin.id)
    view = AuditViewService(ctx.db)
    everything = view.count()
    assert everything > 650
    first = view.list(limit=300)
    second = view.list(limit=300, offset=300)
    assert len(first) == len(second) == 300
    assert not {(r.at, r.action) for r in first} & {(r.at, r.action) for r in second}
    recent = AuditFilter(since="2025-01-01T00:00:00")
    assert view.count(recent) == everything - 1
    assert view.count(AuditFilter(actor_id=admin.id, entity_type="test")) == 651
    # The asset shows by its code, not by 8 characters of its id.
    asset_row = next(r for r in view.list(flt=AuditFilter(entity_type="asset")))
    assert asset_row.entity_code == "PMP-900" and asset_row.entity_id == asset_id
    # CSV export: every matching event, no formula injection.
    out = tmp_path / "audit.csv"
    assert view.export_csv(out, AuditFilter(entity_type="test")) == 652
    with out.open(encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) == 653 and rows[0][0] == "at_utc"
    assert any(r[2].startswith("'=HYPERLINK") for r in rows[1:])
