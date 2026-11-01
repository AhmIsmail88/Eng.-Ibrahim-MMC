"""Downtime events (SPEC 8.4): one open event per asset, no negative durations."""
from __future__ import annotations

from sqlalchemy import select

from ...domain.permissions import can_edit
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import Asset, DowntimeEvent, FailureReport, WorkOrder
from ...infrastructure.database.orm_models.base import utcnow_iso
from ...infrastructure.database.orm_models.maintenance import DOWNTIME_TYPE
from ..dto.result import Result
from .audit import write_audit
from .auth_service import AuthUser


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


class DowntimeService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def list_for_asset(self, asset_id: str, limit: int = 50):
        """(id, started_at, ended_at, type, reason) newest first."""
        with self._db.session() as s:
            rows = s.scalars(select(DowntimeEvent)
                             .where(DowntimeEvent.asset_id == asset_id)
                             .order_by(DowntimeEvent.started_at.desc()).limit(limit))
            return [(r.id, r.started_at, r.ended_at, r.downtime_type, r.reason) for r in rows]

    def open_event(self, asset_id: str) -> DowntimeEvent | None:
        with self._db.session() as s:
            return s.scalars(select(DowntimeEvent).where(
                DowntimeEvent.asset_id == asset_id,
                DowntimeEvent.ended_at.is_(None)).limit(1)).first()

    def start(self, actor: AuthUser | None, asset_id: str, started_at: str,
              downtime_type: str = "unplanned", reason: str | None = None,
              failure_id: str | None = None, work_order_id: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if downtime_type not in DOWNTIME_TYPE:
            return Result.failure("err.downtime_type_invalid")
        if not started_at:
            return Result.failure("err.downtime_start_required")
        with self._db.unit_of_work() as s:
            asset = s.get(Asset, asset_id)
            if asset is None:
                return Result.failure("err.asset_not_found")
            if failure_id and s.get(FailureReport, failure_id) is None:
                return Result.failure("err.failure_not_found")
            if work_order_id and s.get(WorkOrder, work_order_id) is None:
                return Result.failure("err.wo_not_found")
            already = s.scalar(select(DowntimeEvent.id).where(
                DowntimeEvent.asset_id == asset_id,
                DowntimeEvent.ended_at.is_(None)))
            if already:
                return Result.failure("err.downtime_open_exists")
            row = DowntimeEvent(
                asset_id=asset_id, failure_id=failure_id, work_order_id=work_order_id,
                started_at=started_at, downtime_type=downtime_type, reason=reason,
                actor_id=actor.id if actor else None)
            s.add(row)
            s.flush()
            write_audit(s, "downtime", row.id, "downtime_started",
                        actor_id=actor.id if actor else None,
                        after={"asset": asset.asset_code, "type": downtime_type})
            return Result.success(row.id)

    def end(self, actor: AuthUser | None, downtime_id: str, ended_at: str,
            approved_by: str | None = None) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if not ended_at:
            return Result.failure("err.downtime_end_required")
        with self._db.unit_of_work() as s:
            row = s.get(DowntimeEvent, downtime_id)
            if row is None:
                return Result.failure("err.downtime_not_found")
            if row.ended_at is not None:
                return Result.failure("err.downtime_already_closed")
            if ended_at < row.started_at:
                return Result.failure("err.downtime_end_before_start")
            row.ended_at = ended_at
            row.approved_by = approved_by
            write_audit(s, "downtime", row.id, "downtime_ended",
                        actor_id=actor.id if actor else None, after={"ended_at": ended_at})
            return Result.success()

    def close_for_asset(self, actor: AuthUser | None, asset_id: str) -> Result[None]:
        """Convenience: end the currently open event at 'now'."""
        event = self.open_event(asset_id)
        if event is None:
            return Result.success()
        return self.end(actor, event.id, utcnow_iso())
