"""Read side of the audit log (UI-022). The write side never changes these rows."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import AppUser, AuditLog


@dataclass(frozen=True)
class AuditRow:
    at: str
    actor: str
    action: str
    entity_type: str
    entity_id: str | None
    reason: str | None


class AuditViewService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def entity_types(self) -> list[str]:
        with self._db.session() as s:
            return sorted(set(s.scalars(select(AuditLog.entity_type))))

    def list(self, entity_type: str | None = None, limit: int = 300) -> list[AuditRow]:
        with self._db.session() as s:
            stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
            if entity_type:
                stmt = stmt.where(AuditLog.entity_type == entity_type)
            users = {u.id: u.username for u in s.scalars(select(AppUser))}
            return [AuditRow(at=row.created_at, actor=users.get(row.actor_id or "", "—"),
                             action=row.action, entity_type=row.entity_type,
                             entity_id=(row.entity_id or "")[:8] or None,
                             reason=row.reason) for row in s.scalars(stmt)]
