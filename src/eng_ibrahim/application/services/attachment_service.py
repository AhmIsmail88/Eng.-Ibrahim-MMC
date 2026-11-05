"""Attachments: safe copy into <DATA_ROOT>/attachments, metadata in SQLite (SPEC 22)."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from ...domain.permissions import can_edit
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    Asset,
    Attachment,
    FailureReport,
    Inspection,
    WorkOrder,
)
from ..dto.result import Result
from .audit import write_audit
from .auth_service import AuthUser

MAX_BYTES = 20 * 1024 * 1024
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".docx", ".xlsx", ".txt"}
OWNER_TYPES = ("asset", "work_order", "inspection", "failure")
_OWNER_MODELS = {"asset": Asset, "work_order": WorkOrder, "inspection": Inspection,
                 "failure": FailureReport}


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


@dataclass(frozen=True)
class AttachmentRow:
    id: str
    filename: str
    size_bytes: int
    added_at: str
    relative_path: str


class AttachmentService:
    def __init__(self, db: Database, root: Path) -> None:
        self._db = db
        self._root = root

    def _absolute(self, relative_path: str) -> Path:
        target = (self._root / relative_path).resolve()
        base = self._root.resolve()
        if base not in target.parents and target != base:
            raise ValueError("path outside data root")
        return target

    def add(self, actor: AuthUser | None, owner_type: str, owner_id: str,
            source: Path) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if owner_type not in OWNER_TYPES:
            return Result.failure("err.owner_type_invalid")
        source = Path(source)
        if not source.is_file():
            return Result.failure("err.file_not_found")
        suffix = source.suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            return Result.failure("err.attachment_type")
        size = source.stat().st_size
        if size <= 0:
            return Result.failure("err.file_empty")
        if size > MAX_BYTES:
            return Result.failure("err.attachment_too_large")

        with self._db.session() as s:
            # Every owner must exist: an attachment is never orphaned from the start.
            if s.get(_OWNER_MODELS[owner_type], owner_id) is None:
                return Result.failure("err.not_found")

        folder = self._root / "attachments" / owner_type / owner_id
        folder.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}{suffix}"
        target = folder / stored_name
        digest = hashlib.sha256()
        tmp = target.with_suffix(f"{suffix}.part")
        with source.open("rb") as src, tmp.open("wb") as dst:
            for chunk in iter(lambda: src.read(1024 * 256), b""):
                digest.update(chunk)
                dst.write(chunk)
        tmp.replace(target)
        relative = target.relative_to(self._root).as_posix()

        try:
            with self._db.unit_of_work() as s:
                row = Attachment(
                    owner_type=owner_type, owner_id=owner_id, relative_path=relative,
                    original_filename=source.name, mime_type=None, size_bytes=size,
                    sha256=digest.hexdigest(), added_by=actor.id if actor else None)
                s.add(row)
                s.flush()
                write_audit(s, owner_type, owner_id, "attachment_added",
                            actor_id=actor.id if actor else None,
                            after={"file": source.name, "size": size})
                return Result.success(row.id)
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def list(self, owner_type: str, owner_id: str) -> list[AttachmentRow]:
        with self._db.session() as s:
            rows = s.scalars(select(Attachment).where(
                Attachment.owner_type == owner_type,
                Attachment.owner_id == owner_id,
                ).order_by(Attachment.added_at.desc()))
            return [AttachmentRow(id=r.id, filename=r.original_filename,
                                  size_bytes=r.size_bytes, added_at=r.added_at,
                                  relative_path=r.relative_path) for r in rows]

    def path(self, attachment_id: str) -> Path | None:
        with self._db.session() as s:
            row = s.get(Attachment, attachment_id)
            if row is None:
                return None
            try:
                return self._absolute(row.relative_path)
            except ValueError:
                return None

    def remove(self, actor: AuthUser | None, attachment_id: str) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            row = s.get(Attachment, attachment_id)
            if row is None:
                return Result.failure("err.attachment_not_found")
            try:
                self._absolute(row.relative_path).unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
            s.delete(row)
            write_audit(s, "attachment", attachment_id, "attachment_removed",
                        actor_id=actor.id if actor else None)
            return Result.success()

    def integrity_scan(self) -> dict[str, int]:
        """Count rows whose file is missing, and files with no row (SPEC 22.2)."""
        missing = 0
        known: set[str] = set()
        with self._db.session() as s:
            for row in s.scalars(select(Attachment)):
                known.add(row.relative_path.replace("\\", "/"))
                try:
                    path = self._absolute(row.relative_path)
                except ValueError:
                    missing += 1
                    continue
                if not path.is_file():
                    missing += 1
        orphans = 0
        base = self._root / "attachments"
        if base.exists():
            for file in base.rglob("*"):
                if file.is_file():
                    rel = file.relative_to(self._root).as_posix()
                    if rel not in known:
                        orphans += 1
        return {"missing": missing, "orphans": orphans}
