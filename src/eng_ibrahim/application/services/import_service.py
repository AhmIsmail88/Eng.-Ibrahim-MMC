"""Basic template import (SPEC 18.2): preview/validate everything, then one transaction."""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import func, select

from ...domain.permissions import can_edit
from ...domain.text_normalization import normalize_code, normalize_search
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    Asset,
    AssetCategory,
    ImportBatch,
    Location,
    Part,
    Unit,
)
from ...infrastructure.database.orm_models.operations import (
    CRITICALITY,
    OPERATIONAL_STATUS,
)
from ..dto.result import Result
from .audit import write_audit
from .auth_service import AuthUser
from .settings_service import SettingsService

log = logging.getLogger(__name__)

KINDS = {
    "assets": ("asset_code", "asset_name_ar", "category_code", "location_code"),
    "parts": ("part_code", "name_ar", "unit_code"),
}
# Columns read when present; anything else in the file is reported, never silently used.
OPTIONAL = {"assets": ("criticality", "status"), "parts": ("reorder_point",)}
MAX_ROWS = 5000


@dataclass(frozen=True)
class RowProblem:
    row: int
    field: str
    message: str


@dataclass(frozen=True)
class ImportPreview:
    kind: str
    total: int
    valid: int
    problems: list[RowProblem] = field(default_factory=list)
    sample: list[dict] = field(default_factory=list)
    ignored_columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list, repr=False)  # what commit will write

    @property
    def ok(self) -> bool:
        return not self.problems and self.valid > 0


def _read_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as fh:
            return [{k.strip(): (v or "").strip() for k, v in row.items()}
                    for row in csv.DictReader(fh)]
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        rows = list(book.active.iter_rows(values_only=True))
    finally:
        book.close()  # read-only workbooks keep the file locked on Windows
    if not rows:
        return []
    header = [str(cell or "").strip() for cell in rows[0]]
    return [{header[i]: ("" if cell is None else str(cell).strip())
             for i, cell in enumerate(row) if i < len(header)}
            for row in rows[1:]]


def _is_non_negative_number(value: str) -> bool:
    try:
        number = Decimal(value)
    except InvalidOperation:
        return False
    return number.is_finite() and number >= 0


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


class ImportService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def preview(self, kind: str, path: Path) -> Result[ImportPreview]:
        path = Path(path)
        if not path.is_file():
            return Result.failure("err.file_not_found")
        if kind not in KINDS:
            return Result.failure("err.import_unknown_kind")
        rows = [r for r in _read_rows(path) if any(v for v in r.values())]
        if not rows:
            return Result.failure("err.import_empty")
        if len(rows) > MAX_ROWS:
            return Result.failure("err.import_too_many")
        required = KINDS[kind]
        problems: list[RowProblem] = []
        seen: dict[str, int] = {}
        with self._db.session() as s:
            categories = {c.code.lower(): c.id for c in s.scalars(select(AssetCategory))}
            locations = {loc.code.lower(): loc.id for loc in s.scalars(select(Location))}
            units = {u.code.lower(): u.code for u in s.scalars(select(Unit))}
            existing = set()
            if kind == "assets":
                existing = {c.lower() for c in s.scalars(select(Asset.asset_code))}
            else:
                existing = {c.lower() for c in s.scalars(select(Part.part_code))}
        for index, row in enumerate(rows, start=2):
            for key in required:
                if not row.get(key):
                    problems.append(RowProblem(index, key, "err.import_required"))
            code = normalize_code(row.get(required[0], "")).lower()
            if not code:
                continue
            if code in seen:
                problems.append(RowProblem(index, required[0], "err.import_duplicate_file"))
            seen[code] = index
            if code in existing:
                problems.append(RowProblem(index, required[0], "err.import_duplicate_db"))
            if kind == "assets":
                if row.get("category_code") and row["category_code"].lower() not in categories:
                    problems.append(RowProblem(index, "category_code", "err.import_lookup"))
                if row.get("location_code") and row["location_code"].lower() not in locations:
                    problems.append(RowProblem(index, "location_code", "err.import_lookup"))
                if row.get("criticality") and row["criticality"] not in CRITICALITY:
                    problems.append(RowProblem(index, "criticality", "err.import_lookup"))
                if row.get("status") and row["status"] not in OPERATIONAL_STATUS:
                    problems.append(RowProblem(index, "status", "err.import_lookup"))
            else:
                if row.get("unit_code") and row["unit_code"].lower() not in units:
                    problems.append(RowProblem(index, "unit_code", "err.import_lookup"))
                reorder = row.get("reorder_point")
                if reorder and not _is_non_negative_number(reorder):
                    problems.append(RowProblem(index, "reorder_point", "err.quantity_invalid"))
        valid = len(rows) - len({p.row for p in problems})
        known = set(KINDS[kind]) | set(OPTIONAL[kind])
        present = {k for row in rows for k in row if k}
        return Result.success(ImportPreview(
            kind=kind, total=len(rows), valid=max(0, valid), problems=problems,
            sample=rows[:20], ignored_columns=sorted(present - known), rows=rows))

    def commit(self, actor: AuthUser | None, kind: str, path: Path) -> Result[int]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        preview = self.preview(kind, Path(path))
        if not preview.ok:
            return Result.failure(preview.error_code or "err.import_failed")
        data = preview.value
        if data is None or not data.ok:
            return Result.failure("err.import_invalid")
        rows = data.rows  # exactly the rows the preview checked: the file is read once
        currency = SettingsService(self._db).get("currency_code", "EGP")
        try:
            with self._db.unit_of_work() as s:
                # Unit codes are case-sensitive keys ('L', 'kPa'); map the file's spelling.
                units = {u.code.lower(): u.code for u in s.scalars(select(Unit))}
                for row in rows:
                    if kind == "assets":
                        category = s.scalar(select(AssetCategory).where(
                            func.lower(AssetCategory.code) == row["category_code"].lower()))
                        location = s.scalar(select(Location).where(
                            func.lower(Location.code) == row["location_code"].lower()))
                        assert category is not None and location is not None  # validated
                        code = normalize_code(row["asset_code"])
                        s.add(Asset(
                            asset_code=code, asset_name_ar=row["asset_name_ar"].strip(),
                            category_id=category.id, location_id=location.id,
                            criticality=(row.get("criticality") or "Medium"),
                            operational_status=(row.get("status") or "In Service"),
                            maintenance_strategy="PM", meter_type="None",
                            search_norm=normalize_search(
                                f"{code} {row['asset_name_ar']}")))
                    else:
                        unit = units[row["unit_code"].lower()]
                        code = normalize_code(row["part_code"])
                        s.add(Part(part_code=code, name_ar=row["name_ar"].strip(),
                                   unit_code=unit, precision=0,
                                   reorder_point_decimal=row.get("reorder_point") or None,
                                   currency=currency,
                                   search_norm=normalize_search(
                                       f"{code} {row['name_ar']}")))
                batch = ImportBatch(type=kind, filename=Path(path).name, status="committed",
                                    summary_json=f'{{"rows": {len(rows)}}}',
                                    created_by=actor.id if actor else None)
                s.add(batch)
                s.flush()
                write_audit(s, "import_batch", batch.id, "import_committed",
                            actor_id=actor.id if actor else None,
                            after={"kind": kind, "rows": len(rows)})
                return Result.success(len(rows))
        except Exception:
            # The user sees a short message; the cause goes to the log for support.
            log.exception("Import of %s failed (%s)", Path(path).name, kind)
            return Result.failure("err.import_failed")
