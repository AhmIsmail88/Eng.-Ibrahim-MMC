"""Meter definitions and readings (SPEC 7).

Cumulative counters never go backwards in time: a lower value is rejected unless
the user records an explicit correction event (which keeps the original row).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select

from ...domain.permissions import can_edit
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    Asset,
    MeterDefinition,
    MeterReading,
)
from ...infrastructure.database.orm_models.base import utcnow_iso
from ...infrastructure.database.orm_models.operations import METER_KIND
from ..dto.asset import MeterRow
from ..dto.result import Result
from .audit import write_audit
from .auth_service import AuthUser


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


def _to_decimal(value: str) -> Decimal | None:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return number


class MeterService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def meters(self, asset_id: str) -> list[MeterRow]:
        with self._db.session() as s:
            rows = s.scalars(select(MeterDefinition)
                             .where(MeterDefinition.asset_id == asset_id)
                             .order_by(MeterDefinition.meter_code)).all()
            result = []
            for m in rows:
                last = s.scalars(select(MeterReading)
                                 .where(MeterReading.meter_id == m.id,
                                        MeterReading.quality != "rejected")
                                 .order_by(MeterReading.reading_at.desc()).limit(1)).first()
                result.append(MeterRow(id=m.id, code=m.meter_code, kind=m.kind,
                                       unit_code=m.unit_code,
                                       latest_value=last.value_decimal if last else None,
                                       latest_at=last.reading_at if last else None))
            return result

    def add_meter(self, actor: AuthUser | None, asset_id: str, meter_code: str,
                  unit_code: str, kind: str = "cumulative") -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if kind not in METER_KIND:
            return Result.failure("err.meter_kind_invalid")
        code = (meter_code or "").strip()
        if not code:
            return Result.failure("err.meter_code_required")
        with self._db.unit_of_work() as s:
            if s.get(Asset, asset_id) is None:
                return Result.failure("err.asset_not_found")
            exists = s.scalar(select(MeterDefinition.id).where(
                MeterDefinition.asset_id == asset_id, MeterDefinition.meter_code == code))
            if exists:
                return Result.failure("err.meter_code_exists")
            row = MeterDefinition(asset_id=asset_id, meter_code=code, kind=kind,
                                  unit_code=unit_code)
            s.add(row)
            s.flush()
            write_audit(s, "meter", row.id, "meter_created",
                        actor_id=actor.id if actor else None, after={"code": code})
            return Result.success(row.id)

    def ensure_asset_meter(self, asset_id: str) -> str | None:
        """Create the default meter implied by `assets.meter_type`, if missing.

        Idempotent and silent: it is a convenience used by the reading dialog.
        """
        with self._db.unit_of_work() as s:
            asset = s.get(Asset, asset_id)
            if asset is None or asset.meter_type == "None":
                return None
            unit = asset.default_meter_unit
            if not unit:
                return None
            existing = s.scalar(select(MeterDefinition.id).where(
                MeterDefinition.asset_id == asset_id,
                MeterDefinition.is_primary == 1))
            if existing:
                return existing
            code = {"Runtime Hours": "HOURS", "Kilometer": "KM", "Cycle": "CYC"}[
                asset.meter_type]
            row = MeterDefinition(asset_id=asset_id, meter_code=code, kind="cumulative",
                                  unit_code=unit, is_primary=1)
            s.add(row)
            s.flush()
            return row.id

    def add_reading(self, actor: AuthUser | None, asset_id: str, meter_id: str,
                    value: str, reading_at: str, notes: str | None = None,
                    quality: str = "valid",
                    correction_of_id: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        number = _to_decimal(value)
        if number is None:
            return Result.failure("err.meter_value_invalid")
        if not reading_at:
            return Result.failure("err.reading_date_required")
        with self._db.unit_of_work() as s:
            asset = s.get(Asset, asset_id)
            meter = s.get(MeterDefinition, meter_id)
            if asset is None or meter is None or meter.asset_id != asset_id:
                return Result.failure("err.asset_not_found")
            if meter.kind == "cumulative" and correction_of_id is None:
                previous = s.scalars(
                    select(MeterReading)
                    .where(MeterReading.meter_id == meter_id,
                           MeterReading.reading_at < reading_at,
                           MeterReading.quality != "rejected")
                    .order_by(MeterReading.reading_at.desc()).limit(1)
                ).first()
                if previous is not None and number < Decimal(previous.value_decimal):
                    return Result.failure("err.meter_decrease")
                # A back-dated reading must not exceed the one recorded after it either.
                following = s.scalars(
                    select(MeterReading)
                    .where(MeterReading.meter_id == meter_id,
                           MeterReading.reading_at > reading_at,
                           MeterReading.quality != "rejected")
                    .order_by(MeterReading.reading_at.asc()).limit(1)
                ).first()
                if following is not None and number > Decimal(following.value_decimal):
                    return Result.failure("err.meter_decrease")
            row = MeterReading(
                asset_id=asset_id, meter_id=meter_id, value_decimal=str(number),
                reading_at=reading_at, entered_at=utcnow_iso(), source="manual",
                quality=quality, correction_of_id=correction_of_id, notes=notes,
                actor_id=actor.id if actor else None,
            )
            s.add(row)
            s.flush()
            write_audit(s, "meter_reading", row.id, "reading_added",
                        actor_id=actor.id if actor else None,
                        after={"meter": meter.meter_code, "value": str(number)})
            return Result.success(row.id)

    def latest(self, meter_id: str) -> Decimal | None:
        with self._db.session() as s:
            row = s.scalars(select(MeterReading)
                            .where(MeterReading.meter_id == meter_id,
                                   MeterReading.quality != "rejected")
                            .order_by(MeterReading.reading_at.desc()).limit(1)).first()
            return Decimal(row.value_decimal) if row else None

    def count(self, asset_id: str) -> int:
        with self._db.session() as s:
            return int(s.scalar(
                select(func.count()).select_from(MeterReading)
                .where(MeterReading.asset_id == asset_id)) or 0)

    def correct_last_reading(self, actor: AuthUser | None, asset_id: str, meter_id: str,
                             value: str, reading_at: str, reason: str) -> Result[str]:
        """Documented meter correction (SPEC 6.3, 7.3; review F-02).

        The wrong latest reading keeps its value in history but is marked `rejected`, so
        it no longer drives due dates or the no-decrease rule. The new reading points at
        it through `correction_of_id` and carries the reason. A correction may go below
        the wrong value, never below the last good reading before it.
        """
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if not (reason or "").strip():
            return Result.failure("err.reason_required")
        number = _to_decimal(value)
        if number is None:
            return Result.failure("err.meter_value_invalid")
        if not reading_at:
            return Result.failure("err.reading_date_required")
        with self._db.unit_of_work() as s:
            meter = s.get(MeterDefinition, meter_id)
            if meter is None or meter.asset_id != asset_id:
                return Result.failure("err.asset_not_found")
            wrong = s.scalars(select(MeterReading)
                              .where(MeterReading.meter_id == meter_id,
                                     MeterReading.quality != "rejected")
                              .order_by(MeterReading.reading_at.desc()).limit(1)).first()
            if wrong is None:
                return Result.failure("err.meter_nothing_to_correct")
            if reading_at < wrong.reading_at[:len(reading_at)]:
                return Result.failure("err.meter_correction_date")
            good = s.scalars(select(MeterReading)
                             .where(MeterReading.meter_id == meter_id,
                                    MeterReading.quality != "rejected",
                                    MeterReading.id != wrong.id,
                                    MeterReading.reading_at <= wrong.reading_at)
                             .order_by(MeterReading.reading_at.desc()).limit(1)).first()
            if meter.kind == "cumulative" and good is not None \
                    and number < Decimal(good.value_decimal):
                return Result.failure("err.meter_decrease")
            wrong.quality = "rejected"
            row = MeterReading(
                asset_id=asset_id, meter_id=meter_id, value_decimal=str(number),
                reading_at=reading_at, entered_at=utcnow_iso(), source="manual",
                quality="valid", correction_of_id=wrong.id, notes=reason.strip(),
                actor_id=actor.id if actor else None)
            s.add(row)
            s.flush()
            write_audit(s, "meter_reading", row.id, "reading_corrected",
                        actor_id=actor.id if actor else None,
                        before={"value": wrong.value_decimal, "at": wrong.reading_at},
                        after={"value": str(number), "at": reading_at}, reason=reason.strip())
            return Result.success(row.id)

    def last_reading(self, meter_id: str) -> tuple[str, str] | None:
        """(value, reading_at) of the reading a correction would replace."""
        with self._db.session() as s:
            row = s.scalars(select(MeterReading)
                            .where(MeterReading.meter_id == meter_id,
                                   MeterReading.quality != "rejected")
                            .order_by(MeterReading.reading_at.desc()).limit(1)).first()
            return (row.value_decimal, row.reading_at) if row else None
