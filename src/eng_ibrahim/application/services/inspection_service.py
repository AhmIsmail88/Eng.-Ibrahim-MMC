"""Inspection templates and forms (SPEC 11).

An answer stores a snapshot of its item definition, so editing a template later
never rewrites a completed inspection.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import func, select

from ...domain.permissions import can_edit
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    Asset,
    Inspection,
    InspectionAnswer,
    InspectionTemplate,
    InspectionTemplateItem,
    WorkOrder,
)
from ...infrastructure.database.orm_models.base import utcnow_iso
from ..dto.preventive import InspectionRow, InspectionTemplateRow
from ..dto.result import Result
from .audit import write_audit
from .auth_service import AuthUser
from .numbering import next_number, next_plain_number

RESPONSE_TYPES = ("pass_fail", "yes_no", "done_na", "numeric", "text", "photo")


@dataclass(frozen=True)
class ItemRow:
    id: str
    sequence: int
    label: str
    response_type: str
    required: bool


@dataclass(frozen=True)
class AnswerRow:
    id: str
    item_id: str | None
    sequence: int
    label: str
    response_type: str
    required: bool
    answer: str
    pass_fail: str | None
    notes: str | None


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


class InspectionService:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ---------------- templates ----------------
    def create_template(self, actor: AuthUser | None, template_code: str, title_ar: str,
                        items: list[tuple[str, str, bool]],
                        asset_type_id: str | None = None,
                        title_en: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        code, title = (template_code or "").strip(), (title_ar or "").strip()
        if not code or not title:
            return Result.failure("err.template_required")
        if not items:
            return Result.failure("err.template_needs_items")
        for label, response_type, _required in items:
            if not (label or "").strip():
                return Result.failure("err.template_item_required")
            if response_type not in RESPONSE_TYPES:
                return Result.failure("err.response_type_invalid")
        with self._db.unit_of_work() as s:
            if s.scalar(select(InspectionTemplate.id).where(
                    func.lower(InspectionTemplate.template_code) == code.lower())):
                return Result.failure("err.template_code_exists")
            template = InspectionTemplate(template_code=code, title_ar=title,
                                          title_en=title_en, asset_type_id=asset_type_id)
            s.add(template)
            s.flush()
            for index, (label, response_type, required) in enumerate(items, start=1):
                s.add(InspectionTemplateItem(
                    template_id=template.id, sequence=index, label_ar=label.strip(),
                    response_type=response_type, required=1 if required else 0))
            write_audit(s, "inspection_template", template.id, "template_created",
                        actor_id=actor.id if actor else None, after={"code": code})
            return Result.success(template.id)

    def templates(self) -> list[InspectionTemplateRow]:
        with self._db.session() as s:
            rows = []
            for template in s.scalars(select(InspectionTemplate)
                                      .where(InspectionTemplate.status == "Active")
                                      .order_by(InspectionTemplate.template_code)):
                count = int(s.scalar(select(func.count()).select_from(InspectionTemplateItem)
                                     .where(InspectionTemplateItem.template_id == template.id)) or 0)
                rows.append(InspectionTemplateRow(
                    id=template.id, code=template.template_code, title_ar=template.title_ar,
                    item_count=count, version=template.version, status=template.status))
            return rows

    def template_items(self, template_id: str) -> list[ItemRow]:
        with self._db.session() as s:
            return [ItemRow(id=item.id, sequence=item.sequence, label=item.label_ar,
                            response_type=item.response_type, required=bool(item.required))
                    for item in s.scalars(select(InspectionTemplateItem)
                                          .where(InspectionTemplateItem.template_id == template_id)
                                          .order_by(InspectionTemplateItem.sequence))]

    # ---------------- inspections ----------------
    def start(self, actor: AuthUser | None, asset_id: str, template_id: str,
              wo_id: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            asset = s.get(Asset, asset_id)
            template = s.get(InspectionTemplate, template_id)
            if asset is None:
                return Result.failure("err.asset_not_found")
            if template is None:
                return Result.failure("err.template_not_found")
            if wo_id and s.get(WorkOrder, wo_id) is None:
                return Result.failure("err.wo_not_found")
            inspection = Inspection(
                inspection_no=next_number(s, "INS"), asset_id=asset_id,
                template_id=template_id, template_version=template.version,
                wo_id=wo_id, inspector_id=actor.id if actor else None, status="InProgress")
            s.add(inspection)
            s.flush()
            for item in s.scalars(select(InspectionTemplateItem)
                                  .where(InspectionTemplateItem.template_id == template_id)
                                  .order_by(InspectionTemplateItem.sequence)):
                snapshot = {"label": item.label_ar, "type": item.response_type,
                            "required": bool(item.required), "sequence": item.sequence}
                s.add(InspectionAnswer(
                    inspection_id=inspection.id, item_id=item.id,
                    item_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
                    answer_json=json.dumps({"value": ""}, ensure_ascii=False)))
            write_audit(s, "inspection", inspection.id, "inspection_started",
                        actor_id=actor.id if actor else None,
                        after={"asset": asset.asset_code, "template": template.template_code})
            return Result.success(inspection.id)

    def answers(self, inspection_id: str) -> list[AnswerRow]:
        with self._db.session() as s:
            rows = []
            for answer in s.scalars(select(InspectionAnswer)
                                    .where(InspectionAnswer.inspection_id == inspection_id)):
                snapshot = json.loads(answer.item_snapshot_json or "{}")
                value = json.loads(answer.answer_json or "{}").get("value", "")
                rows.append(AnswerRow(
                    id=answer.id, item_id=answer.item_id,
                    sequence=int(snapshot.get("sequence", 0)),
                    label=snapshot.get("label", ""), response_type=snapshot.get("type", ""),
                    required=bool(snapshot.get("required", True)), answer=value,
                    pass_fail=answer.pass_fail_state, notes=answer.notes))
            rows.sort(key=lambda r: r.sequence)
            return rows

    def answer(self, actor: AuthUser | None, inspection_id: str, answer_id: str,
               value: str, pass_fail: str | None = None,
               notes: str | None = None) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            inspection = s.get(Inspection, inspection_id)
            if inspection is None:
                return Result.failure("err.inspection_not_found")
            if inspection.status == "Completed":
                return Result.failure("err.inspection_completed")
            row = s.get(InspectionAnswer, answer_id)
            if row is None or row.inspection_id != inspection_id:
                return Result.failure("err.not_found")
            row.answer_json = json.dumps({"value": value}, ensure_ascii=False)
            row.pass_fail_state = pass_fail
            row.notes = notes
            return Result.success()

    def complete(self, actor: AuthUser | None, inspection_id: str) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            inspection = s.get(Inspection, inspection_id)
            if inspection is None:
                return Result.failure("err.inspection_not_found")
            if inspection.status == "Completed":
                return Result.success()
            for answer in s.scalars(select(InspectionAnswer)
                                    .where(InspectionAnswer.inspection_id == inspection_id)):
                snapshot = json.loads(answer.item_snapshot_json or "{}")
                value = json.loads(answer.answer_json or "{}").get("value", "")
                if snapshot.get("required", True) and not str(value).strip():
                    return Result.failure("err.inspection_incomplete")
            inspection.status = "Completed"
            inspection.completed_at = utcnow_iso()
            write_audit(s, "inspection", inspection.id, "inspection_completed",
                        actor_id=actor.id if actor else None)
            return Result.success()

    def list(self, asset_id: str | None = None, status: str | None = None) -> list[InspectionRow]:
        with self._db.session() as s:
            stmt = (select(Inspection, Asset)
                    .join(Asset, Inspection.asset_id == Asset.id)
                    .order_by(Inspection.started_at.desc()))
            if asset_id:
                stmt = stmt.where(Inspection.asset_id == asset_id)
            if status:
                stmt = stmt.where(Inspection.status == status)
            rows = []
            for inspection, asset in s.execute(stmt).all():
                template = (s.get(InspectionTemplate, inspection.template_id)
                            if inspection.template_id else None)
                failed = int(s.scalar(select(func.count()).select_from(InspectionAnswer).where(
                    InspectionAnswer.inspection_id == inspection.id,
                    InspectionAnswer.pass_fail_state == "fail")) or 0)
                rows.append(InspectionRow(
                    id=inspection.id, number=inspection.inspection_no,
                    asset_code=asset.asset_code,
                    template_title=template.title_ar if template else None,
                    status=inspection.status, started_at=inspection.started_at,
                    completed_at=inspection.completed_at, failed_items=failed))
            return rows

    def create_template_code(self, actor: AuthUser | None) -> str:
        with self._db.unit_of_work() as s:
            return next_plain_number(s, "TPL")
