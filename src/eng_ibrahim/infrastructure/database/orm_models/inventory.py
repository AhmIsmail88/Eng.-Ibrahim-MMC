"""Phase 4: spare parts, warehouses and the immutable stock ledger (SPEC 12)."""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UuidPk, utcnow_iso

MOVEMENT_TYPE = (
    "OPENING_BALANCE", "RECEIPT", "ISSUE_TO_WO", "ISSUE_OTHER",
    "RETURN_FROM_WO", "ADJUSTMENT_POSITIVE", "ADJUSTMENT_NEGATIVE",
    "TRANSFER_OUT", "TRANSFER_IN", "SCRAP",
)
ISSUE_TYPES = ("ISSUE_TO_WO", "ISSUE_OTHER")
RETURN_TYPES = ("RETURN_FROM_WO",)
RESERVATION_STATUS = ("active", "released", "consumed", "cancelled")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class Warehouse(Base, UuidPk, Timestamps):
    __tablename__ = "warehouses"
    warehouse_code: Mapped[str] = mapped_column(sa.String(32), nullable=False, unique=True)
    name_ar: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    name_en: Mapped[str | None] = mapped_column(sa.String(160))
    location_id: Mapped[str | None] = mapped_column(sa.ForeignKey("locations.id"))
    is_active: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    __table_args__ = (sa.CheckConstraint("is_active IN (0,1)", name="is_active_bool"),)


class Part(Base, UuidPk, Timestamps):
    __tablename__ = "parts"
    part_code: Mapped[str] = mapped_column(sa.String(48), nullable=False)
    name_ar: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    name_en: Mapped[str | None] = mapped_column(sa.String(200))
    category: Mapped[str | None] = mapped_column(sa.String(64))
    unit_code: Mapped[str] = mapped_column(sa.ForeignKey("units.code"), nullable=False)
    precision: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    min_stock_decimal: Mapped[str | None] = mapped_column(sa.String(40))
    reorder_point_decimal: Mapped[str | None] = mapped_column(sa.String(40))
    target_stock_decimal: Mapped[str | None] = mapped_column(sa.String(40))
    reference_cost_minor: Mapped[int | None] = mapped_column(sa.Integer)
    currency: Mapped[str | None] = mapped_column(sa.ForeignKey("currencies.code"))
    default_supplier_id: Mapped[str | None] = mapped_column(sa.ForeignKey("suppliers.id"))
    search_norm: Mapped[str] = mapped_column(sa.String(400), nullable=False, default="")
    is_active: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    __table_args__ = (
        sa.CheckConstraint("is_active IN (0,1)", name="is_active_bool"),
        sa.CheckConstraint("precision BETWEEN 0 AND 6", name="precision_range"),
    )


sa.Index("uq_parts_code_ci", sa.func.lower(sa.func.trim(Part.part_code)), unique=True)
sa.Index("ix_parts_search_norm", Part.search_norm)


class PartCompatibility(Base):
    __tablename__ = "part_compatibility"
    part_id: Mapped[str] = mapped_column(sa.ForeignKey("parts.id"), primary_key=True)
    asset_id: Mapped[str] = mapped_column(sa.ForeignKey("assets.id"), primary_key=True)
    notes: Mapped[str | None] = mapped_column(sa.Text)


class StockMovement(Base, UuidPk):
    __tablename__ = "stock_movements"
    movement_no: Mapped[str] = mapped_column(sa.String(24), nullable=False, unique=True)
    part_id: Mapped[str] = mapped_column(sa.ForeignKey("parts.id"), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(sa.ForeignKey("warehouses.id"), nullable=False)
    movement_type: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    quantity_decimal: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    signed_quantity_decimal: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    posted_at: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=utcnow_iso)
    currency_code: Mapped[str] = mapped_column(sa.ForeignKey("currencies.code"), nullable=False)
    unit_cost_minor_snapshot: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    total_value_minor: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    wo_id: Mapped[str | None] = mapped_column(sa.ForeignKey("work_orders.id"))
    original_movement_id: Mapped[str | None] = mapped_column(
        sa.ForeignKey("stock_movements.id"))
    reversal_of_id: Mapped[str | None] = mapped_column(sa.ForeignKey("stock_movements.id"))
    supplier_id: Mapped[str | None] = mapped_column(sa.ForeignKey("suppliers.id"))
    purchase_ref: Mapped[str | None] = mapped_column(sa.String(64))
    actor_id: Mapped[str | None] = mapped_column(sa.String(36))
    reason: Mapped[str | None] = mapped_column(sa.Text)
    __table_args__ = (
        sa.CheckConstraint(f"movement_type IN ({_in(MOVEMENT_TYPE)})", name="type_valid"),
        sa.CheckConstraint("unit_cost_minor_snapshot >= 0", name="unit_cost_nonneg"),
        sa.CheckConstraint("total_value_minor >= 0", name="total_nonneg"),
    )


sa.Index("ix_movements_part_wh_posted", StockMovement.part_id, StockMovement.warehouse_id,
         StockMovement.posted_at)
sa.Index("ix_movements_wo", StockMovement.wo_id)


class StockBalance(Base):
    __tablename__ = "stock_balances"
    part_id: Mapped[str] = mapped_column(sa.ForeignKey("parts.id"), primary_key=True)
    warehouse_id: Mapped[str] = mapped_column(sa.ForeignKey("warehouses.id"), primary_key=True)
    currency_code: Mapped[str] = mapped_column(sa.ForeignKey("currencies.code"), nullable=False)
    on_hand_decimal: Mapped[str] = mapped_column(sa.String(40), nullable=False, default="0")
    reserved_decimal: Mapped[str] = mapped_column(sa.String(40), nullable=False, default="0")
    inventory_value_minor: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    average_unit_cost_precise: Mapped[str] = mapped_column(sa.String(40), nullable=False,
                                                          default="0")


class StockReservation(Base, UuidPk):
    __tablename__ = "stock_reservations"
    part_id: Mapped[str] = mapped_column(sa.ForeignKey("parts.id"), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(sa.ForeignKey("warehouses.id"), nullable=False)
    wo_id: Mapped[str] = mapped_column(sa.ForeignKey("work_orders.id"), nullable=False)
    quantity_decimal: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    reserved_at: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=utcnow_iso)
    released_at: Mapped[str | None] = mapped_column(sa.String(32))
    status: Mapped[str] = mapped_column(sa.String(12), nullable=False, default="active")
    __table_args__ = (
        sa.CheckConstraint(f"status IN ({_in(RESERVATION_STATUS)})", name="status_valid"),
    )
