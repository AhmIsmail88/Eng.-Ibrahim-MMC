"""Purchase requests (P1): approval → receipt into stock, linked to the ledger."""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UuidPk, utcnow_iso

PR_STATUS = ("Draft", "Approved", "Received", "Cancelled")


class PurchaseRequest(Base, UuidPk, Timestamps):
    __tablename__ = "purchase_requests"
    request_no: Mapped[str] = mapped_column(sa.String(24), nullable=False, unique=True)
    supplier_id: Mapped[str | None] = mapped_column(sa.ForeignKey("suppliers.id"))
    requested_at: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=utcnow_iso)
    status: Mapped[str] = mapped_column(sa.String(12), nullable=False, default="Draft")
    requested_by: Mapped[str | None] = mapped_column(sa.String(36))
    notes: Mapped[str | None] = mapped_column(sa.Text)
    estimated_total_minor: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    warehouse_id: Mapped[str | None] = mapped_column(sa.ForeignKey("warehouses.id"))
    __table_args__ = (
        sa.CheckConstraint("status IN ('Draft','Approved','Received','Cancelled')",
                           name="status_valid"),
        sa.CheckConstraint("estimated_total_minor >= 0", name="total_nonneg"),
    )


class PurchaseRequestLine(Base, UuidPk):
    __tablename__ = "purchase_request_lines"
    request_id: Mapped[str] = mapped_column(sa.ForeignKey("purchase_requests.id"),
                                           nullable=False)
    part_id: Mapped[str] = mapped_column(sa.ForeignKey("parts.id"), nullable=False)
    quantity_decimal: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    estimated_cost_minor: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    __table_args__ = (sa.CheckConstraint("estimated_cost_minor >= 0", name="cost_nonneg"),)
