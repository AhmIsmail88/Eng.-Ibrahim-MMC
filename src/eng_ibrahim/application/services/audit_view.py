"""Read side of the audit log (UI-022). The write side never changes these rows.

Review F-08/F-23: filter by period and user, page through everything (not only the last
300 events), export what is filtered, and show each record by its human code.
"""
from __future__ import annotations

import builtins
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    AppUser,
    Asset,
    AssetCategory,
    AuditLog,
    FailureReport,
    Location,
    Part,
    PMPlan,
    PurchaseRequest,
    Supplier,
    Technician,
    Vehicle,
    WorkOrder,
)

PAGE_SIZE = 300

# entity type → (model, human-code column) to label rows without the raw UUID
_CODES: dict[str, tuple[Any, str]] = {
    "asset": (Asset, "asset_code"), "work_order": (WorkOrder, "wo_number"),
    "part": (Part, "part_code"), "failure": (FailureReport, "failure_no"),
    "pm_plan": (PMPlan, "plan_code"), "purchase_request": (PurchaseRequest, "request_no"),
    "technician": (Technician, "technician_code"), "supplier": (Supplier, "supplier_code"),
    "location": (Location, "code"), "category": (AssetCategory, "code"),
}


@dataclass(frozen=True)
class AuditRow:
    at: str
    actor: str
    action: str
    entity_type: str
    entity_id: str | None
    entity_code: str | None
    reason: str | None


@dataclass(frozen=True)
class AuditFilter:
    entity_type: str | None = None
    actor_id: str | None = None
    since: str | None = None  # UTC ISO bounds (inclusive)
    until: str | None = None


class AuditViewService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def entity_types(self) -> list[str]:
        with self._db.session() as s:
            return sorted(set(s.scalars(select(AuditLog.entity_type))))

    def actors(self) -> list[tuple[str, str]]:
        with self._db.session() as s:
            return [(u.id, u.username) for u in s.scalars(select(AppUser)
                                                         .order_by(AppUser.username))]

    def count(self, flt: AuditFilter | None = None) -> int:
        with self._db.session() as s:
            stmt = self._where(select(func.count()).select_from(AuditLog), flt)
            return int(s.scalar(stmt) or 0)

    def list(self, entity_type: str | None = None, limit: int = PAGE_SIZE,
             offset: int = 0, flt: AuditFilter | None = None) -> builtins.list[AuditRow]:
        flt = flt or AuditFilter(entity_type=entity_type)
        with self._db.session() as s:
            stmt = self._where(select(AuditLog), flt).order_by(
                AuditLog.created_at.desc(), AuditLog.id.desc()).offset(offset).limit(limit)
            return self._rows(s, list(s.scalars(stmt)))

    def export_csv(self, path: Path, flt: AuditFilter | None = None) -> int:
        """Every matching event (no paging), UTF-8 with BOM so Excel shows Arabic."""
        with self._db.session() as s:
            stmt = self._where(select(AuditLog), flt).order_by(AuditLog.created_at.desc())
            rows = self._rows(s, list(s.scalars(stmt)))
        with Path(path).open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["at_utc", "actor", "action", "entity_type", "entity_code",
                             "entity_id", "reason"])
            for r in rows:
                writer.writerow([_safe(v) for v in (r.at, r.actor, r.action, r.entity_type,
                                                    r.entity_code or "", r.entity_id or "",
                                                    r.reason or "")])
        return len(rows)

    # ---------------- helpers ----------------
    @staticmethod
    def _where(stmt, flt: AuditFilter | None):
        if flt is None:
            return stmt
        if flt.entity_type:
            stmt = stmt.where(AuditLog.entity_type == flt.entity_type)
        if flt.actor_id:
            stmt = stmt.where(AuditLog.actor_id == flt.actor_id)
        if flt.since:
            stmt = stmt.where(AuditLog.created_at >= flt.since)
        if flt.until:
            stmt = stmt.where(AuditLog.created_at <= flt.until)
        return stmt

    @staticmethod
    def _rows(s, logs: builtins.list[AuditLog]) -> builtins.list[AuditRow]:
        users = {u.id: u.username for u in s.scalars(select(AppUser))}
        codes: dict[tuple[str, str], str] = {}
        wanted: dict[str, set[str]] = {}
        for row in logs:
            if row.entity_id and row.entity_type in _CODES | {"vehicle": None}:
                wanted.setdefault(row.entity_type, set()).add(row.entity_id)
        for kind, ids in wanted.items():
            if kind == "vehicle":
                for v in s.scalars(select(Vehicle).where(Vehicle.asset_id.in_(ids))):
                    codes[(kind, v.asset_id)] = v.fleet_code or ""
                continue
            model, column = _CODES[kind]
            for obj in s.scalars(select(model).where(model.id.in_(ids))):
                codes[(kind, obj.id)] = getattr(obj, column)
        return [AuditRow(at=row.created_at, actor=users.get(row.actor_id or "", "—"),
                         action=row.action, entity_type=row.entity_type,
                         entity_id=row.entity_id,
                         entity_code=codes.get((row.entity_type, row.entity_id or "")),
                         reason=row.reason) for row in logs]


def _safe(value: str) -> str:
    """CSV opened in Excel: never let a cell start a formula."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text
