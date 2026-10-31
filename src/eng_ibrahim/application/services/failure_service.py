"""Failure reports (SPEC 8): registration, triage, resolve, cancel."""
from __future__ import annotations

from sqlalchemy import or_, select

from ...domain.permissions import can_edit
from ...domain.text_normalization import search_pattern
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import Asset, FailureReport
from ...infrastructure.database.orm_models.maintenance import PRIORITY
from ..dto.maintenance import FailureRow
from ..dto.result import Result
from .audit import write_audit
from .auth_service import AuthUser
from .numbering import next_number


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


class FailureService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def list(self, status: str | None = None, asset_id: str | None = None,
             query: str = "") -> list[FailureRow]:
        with self._db.session() as s:
            stmt = (select(FailureReport, Asset)
                    .join(Asset, FailureReport.asset_id == Asset.id)
                    .order_by(FailureReport.observed_at.desc()))
            if status:
                stmt = stmt.where(FailureReport.status == status)
            if asset_id:
                stmt = stmt.where(FailureReport.asset_id == asset_id)
            term = search_pattern(query)
            if term:
                stmt = stmt.where(or_(
                    FailureReport.failure_no.like(f"%{term}%", escape="\\"),
                    FailureReport.symptom.like(f"%{term}%", escape="\\"),
                    Asset.search_norm.like(f"%{term}%", escape="\\"),
                ))
            rows = []
            for failure, asset in s.execute(stmt).all():
                rows.append(FailureRow(
                    id=failure.id, number=failure.failure_no, asset_id=asset.id,
                    asset_code=asset.asset_code, symptom=failure.symptom,
                    priority=failure.priority, status=failure.status,
                    observed_at=failure.observed_at))
            return rows

    def get(self, failure_id: str) -> FailureRow | None:
        with self._db.session() as s:
            row = s.get(FailureReport, failure_id)
            if row is None:
                return None
            asset = s.get(Asset, row.asset_id)
            return FailureRow(id=row.id, number=row.failure_no, asset_id=row.asset_id,
                              asset_code=asset.asset_code if asset else "",
                              symptom=row.symptom, priority=row.priority,
                              status=row.status, observed_at=row.observed_at)

    def create(self, actor: AuthUser | None, asset_id: str, symptom: str,
               observed_at: str, priority: str = "Medium",
               failure_code_id: str | None = None,
               root_cause_code_id: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        symptom = (symptom or "").strip()
        if not symptom:
            return Result.failure("err.failure_symptom_required")
        if not observed_at:
            return Result.failure("err.observed_at_required")
        if priority not in PRIORITY:
            return Result.failure("err.priority_invalid")
        with self._db.unit_of_work() as s:
            asset = s.get(Asset, asset_id)
            if asset is None or not asset.is_active:
                return Result.failure("err.asset_not_found")
            row = FailureReport(
                failure_no=next_number(s, "BR"), asset_id=asset_id, observed_at=observed_at,
                symptom=symptom, priority=priority, failure_code_id=failure_code_id,
                root_cause_code_id=root_cause_code_id, status="New",
                reporter_id=actor.id if actor else None,
            )
            s.add(row)
            s.flush()
            write_audit(s, "failure_report", row.id, "failure_created",
                        actor_id=actor.id if actor else None,
                        after={"number": row.failure_no, "asset": asset.asset_code})
            return Result.success(row.id)

    def triage(self, actor: AuthUser | None, failure_id: str) -> Result[None]:
        return self._set_status(actor, failure_id, "Investigating", ("New",))

    def resolve(self, actor: AuthUser | None, failure_id: str,
                root_cause_code_id: str | None = None) -> Result[None]:
        result = self._set_status(actor, failure_id, "Resolved", ("New", "Investigating"))
        if result.ok and root_cause_code_id:
            with self._db.unit_of_work() as s:
                row = s.get(FailureReport, failure_id)
                if row is not None:
                    row.root_cause_code_id = root_cause_code_id
        return result

    def cancel(self, actor: AuthUser | None, failure_id: str, reason: str) -> Result[None]:
        if not (reason or "").strip():
            return Result.failure("err.reason_required")
        return self._set_status(actor, failure_id, "Cancelled",
                                ("New", "Investigating"), reason=reason)

    def mark_converted(self, session, failure_id: str, actor_id: str | None) -> None:
        """Called by WorkOrderService inside its transaction."""
        row = session.get(FailureReport, failure_id)
        if row is not None:
            row.status = "Converted"
            write_audit(session, "failure_report", failure_id, "failure_converted",
                        actor_id=actor_id)

    def _set_status(self, actor: AuthUser | None, failure_id: str, new_status: str,
                    allowed_from: tuple[str, ...], reason: str | None = None) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            row = s.get(FailureReport, failure_id)
            if row is None:
                return Result.failure("err.failure_not_found")
            if row.status not in allowed_from:
                return Result.failure("err.failure_transition_invalid")
            before = row.status
            row.status = new_status
            write_audit(s, "failure_report", row.id, "failure_status_changed",
                        actor_id=actor.id if actor else None,
                        before={"status": before}, after={"status": new_status},
                        reason=reason)
            return Result.success()
