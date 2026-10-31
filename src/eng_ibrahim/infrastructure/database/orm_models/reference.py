from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UuidPk


class Location(Base, UuidPk, Timestamps):
    __tablename__ = "locations"
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name_ar: Mapped[str] = mapped_column(String(160), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(160))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"))
    location_type: Mapped[str] = mapped_column(String(24), nullable=False, default="area")
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (
        CheckConstraint("is_active IN (0,1)", name="is_active_bool"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="no_self_parent"),
    )


class AssetCategory(Base, UuidPk, Timestamps):
    __tablename__ = "asset_categories"
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name_ar: Mapped[str] = mapped_column(String(160), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(160))
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (CheckConstraint("is_active IN (0,1)", name="is_active_bool"),)


class AssetType(Base, UuidPk, Timestamps):
    __tablename__ = "asset_types"
    category_id: Mapped[str] = mapped_column(ForeignKey("asset_categories.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name_ar: Mapped[str] = mapped_column(String(160), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(160))
    spec_schema_json: Mapped[str | None] = mapped_column(Text)


class MaintenanceTask(Base, UuidPk, Timestamps):
    __tablename__ = "maintenance_task_library"
    task_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    title_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(200))
    instructions: Mapped[str | None] = mapped_column(Text)
    estimated_min: Mapped[int | None] = mapped_column(Integer)
    safety_flags_json: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (
        CheckConstraint("estimated_min IS NULL OR estimated_min >= 0", name="est_nonneg"),
    )


class FailureCode(Base, UuidPk, Timestamps):
    __tablename__ = "failure_codes"
    group_code: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(160), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(160))
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (UniqueConstraint("group_code", "code"),)


class Unit(Base):
    __tablename__ = "units"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    dimension: Mapped[str] = mapped_column(String(24), nullable=False)
    label_ar: Mapped[str] = mapped_column(String(60), nullable=False)
    label_en: Mapped[str] = mapped_column(String(60), nullable=False)
    precision: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    __table_args__ = (CheckConstraint("precision BETWEEN 0 AND 6", name="precision_range"),)


class Currency(Base):
    __tablename__ = "currencies"
    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    minor_units: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    __table_args__ = (CheckConstraint("minor_units BETWEEN 0 AND 4", name="minor_range"),)
