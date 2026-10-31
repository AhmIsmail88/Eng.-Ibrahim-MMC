"""Inspection templates and execution (SPEC 11)."""
from __future__ import annotations

import pytest

from eng_ibrahim.application.dto.asset import AssetInput
from eng_ibrahim.application.services.asset_service import AssetService
from eng_ibrahim.application.services.auth_service import AuthService
from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.inspection_service import InspectionService
from eng_ibrahim.application.services.master_data_service import MasterDataService
from eng_ibrahim.domain.enums import UserRole

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
        asset_code="PMP-801", asset_name_ar="مضخة 801", category_id=category.id,
        location_id=masters.locations()[0].id)).value
    service = InspectionService(ctx.db)
    template_id = service.create_template(admin, "TPL-PUMP", "فحص مضخة", [
        ("تسريب من السيل", "yes_no", True),
        ("قراءة الاهتزاز", "numeric", True),
        ("ملاحظات", "text", False),
    ]).value
    return ctx, auth, admin, asset_id, service, template_id


def test_template_items(world):
    _ctx, _auth, _admin, _asset, service, template_id = world
    templates = service.templates()
    assert templates[0].code == "TPL-PUMP" and templates[0].item_count == 3
    items = service.template_items(template_id)
    assert [i.sequence for i in items] == [1, 2, 3]
    assert items[1].response_type == "numeric"


def test_start_creates_snapshotted_answers(world):
    _ctx, _auth, admin, asset_id, service, template_id = world
    inspection_id = service.start(admin, asset_id, template_id).value
    answers = service.answers(inspection_id)
    assert len(answers) == 3
    assert answers[0].label == "تسريب من السيل" and answers[0].required
    assert service.list(asset_id=asset_id)[0].number.startswith("INS-")


def test_complete_requires_required_answers(world):
    _ctx, _auth, admin, asset_id, service, template_id = world
    inspection_id = service.start(admin, asset_id, template_id).value
    assert service.complete(admin, inspection_id).error_code == "err.inspection_incomplete"
    answers = service.answers(inspection_id)
    for answer in answers[:2]:
        assert service.answer(admin, inspection_id, answer.id, "ok", "pass").ok
    assert service.complete(admin, inspection_id).ok
    assert service.list(status="Completed")[0].completed_at


def test_answers_are_frozen_after_template_edit(world):
    ctx, _auth, admin, asset_id, service, template_id = world
    inspection_id = service.start(admin, asset_id, template_id).value
    from eng_ibrahim.infrastructure.database.orm_models import InspectionTemplateItem
    with ctx.db.unit_of_work() as s:
        item = s.query(InspectionTemplateItem).filter_by(template_id=template_id,
                                                         sequence=1).one()
        item.label_ar = "نص معدّل"
    assert service.answers(inspection_id)[0].label == "تسريب من السيل"


def test_completed_inspection_is_read_only(world):
    _ctx, _auth, admin, asset_id, service, template_id = world
    inspection_id = service.start(admin, asset_id, template_id).value
    answers = service.answers(inspection_id)
    for answer in answers[:2]:
        service.answer(admin, inspection_id, answer.id, "ok", "pass")
    service.complete(admin, inspection_id)
    assert service.answer(admin, inspection_id, answers[0].id, "x").error_code == (
        "err.inspection_completed")


def test_viewer_cannot_start_or_answer(world):
    _ctx, auth, admin, asset_id, service, template_id = world
    assert auth.create_user(admin, "ro", "Reader", UserRole.VIEWER.value, "Reader#2026").ok
    viewer = auth.authenticate("ro", "Reader#2026").value
    assert service.start(viewer, asset_id, template_id).error_code == "err.permission_denied"


def test_template_validation(world):
    _ctx, _auth, admin, _asset, service, _template = world
    assert service.create_template(admin, "", "x", [("a", "text", True)]).error_code == (
        "err.template_required")
    assert service.create_template(admin, "T2", "x", []).error_code == "err.template_needs_items"
    assert service.create_template(admin, "T3", "x", [("a", "weird", True)]).error_code == (
        "err.response_type_invalid")
