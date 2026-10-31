"""Phase 3: preventive maintenance plans/occurrences and inspection forms (SPEC 9, 11)."""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UuidPk, utcnow_iso

PLAN_STRATEGY = ("Calendar", "Meter", "Hybrid")
TRIGGER_POLICY = ("DATE_ONLY", "METER_ONLY", "FIRST_DUE", "BOTH_REQUIRED")
INTERVAL_UNIT = ("days", "weeks", "months", "years")
PLAN_STATUS = ("Active", "Paused", "Archived")
ANCHOR_POLICY = ("FROM_COMPLETION", "FROM_FIXED_BASELINE")
CATCH_UP_POLICY = ("LATEST_ONLY_AND_LOG_SKIPPED", "ALL_MISSED")
OCCURRENCE_STATUS = ("Scheduled", "Generated", "Completed", "Skipped", "Missed")
INSPECTION_STATUS = ("Draft", "InProgress", "Completed", "Cancelled")
TEMPLATE_STATUS = ("Active", "Archived")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class PMPlan(Base, UuidPk, Timestamps):
    __tablename__ = "pm_plans"
    plan_code: Mapped[str] = mapped_column(sa.String(40), nullable=False, unique=True)
    asset_id: Mapped[str] = mapped_column(sa.ForeignKey("assets.id"), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text)
    strategy: Mapped[str] = mapped_column(sa.String(12), nullable=False, default="Calendar")
    trigger_policy: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="DATE_ONLY")
    calendar_interval_value: Mapped[int | None] = mapped_column(sa.Integer)
    calendar_interval_unit: Mapped[str | None] = mapped_column(sa.String(8))
    meter_id: Mapped[str | None] = mapped_column(sa.ForeignKey("meter_definitions.id"))
    meter_interval_value: Mapped[str | None] = mapped_column(sa.String(40))
    base_date: Mapped[str | None] = mapped_column(sa.String(10))
    base_meter_value: Mapped[str | None] = mapped_column(sa.String(40))
    next_due_date: Mapped[str | None] = mapped_column(sa.String(10))
    next_due_meter: Mapped[str | None] = mapped_column(sa.String(40))
    warning_days: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=7)
    warning_meter: Mapped[str | None] = mapped_column(sa.String(40))
    lead_days: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=7)
    completion_anchor_policy: Mapped[str] = mapped_column(
        sa.String(24), nullable=False, default="FROM_COMPLETION")
    catch_up_policy: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, default="LATEST_ONLY_AND_LOG_SKIPPED")
    status: Mapped[str] = mapped_column(sa.String(12), nullable=False, default="Active")
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    __table_args__ = (
        sa.CheckConstraint(f"strategy IN ({_in(PLAN_STRATEGY)})", name="strategy_valid"),
        sa.CheckConstraint(f"trigger_policy IN ({_in(TRIGGER_POLICY)})", name="trigger_valid"),
        sa.CheckConstraint(f"status IN ({_in(PLAN_STATUS)})", name="status_valid"),
        sa.CheckConstraint(f"completion_anchor_policy IN ({_in(ANCHOR_POLICY)})",
                           name="anchor_valid"),
        sa.CheckConstraint(f"catch_up_policy IN ({_in(CATCH_UP_POLICY)})", name="catchup_valid"),
        sa.CheckConstraint(
            "calendar_interval_unit IS NULL OR calendar_interval_unit IN "
            "('days','weeks','months','years')", name="interval_unit_valid"),
        sa.CheckConstraint("calendar_interval_value IS NULL OR calendar_interval_value > 0",
                           name="interval_positive"),
        sa.CheckConstraint("warning_days >= 0 AND lead_days >= 0", name="offsets_nonneg"),
    )


sa.Index("ix_pm_plans_status_due", PMPlan.status, PMPlan.next_due_date)
sa.Index("ix_pm_plans_asset", PMPlan.asset_id)


class PMPlanTask(Base, UuidPk):
    __tablename__ = "pm_plan_tasks"
    plan_id: Mapped[str] = mapped_column(sa.ForeignKey("pm_plans.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    title_snapshot: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    instructions: Mapped[str | None] = mapped_column(sa.Text)
    required: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    response_type: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="done")
    __table_args__ = (
        sa.UniqueConstraint("plan_id", "sequence"),
        sa.CheckConstraint("required IN (0,1)", name="required_bool"),
    )


class PMOccurrence(Base, UuidPk):
    __tablename__ = "pm_occurrences"
    plan_id: Mapped[str] = mapped_column(sa.ForeignKey("pm_plans.id"), nullable=False)
    due_key: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    due_date_snapshot: Mapped[str | None] = mapped_column(sa.String(10))
    due_meter_snapshot: Mapped[str | None] = mapped_column(sa.String(40))
    status: Mapped[str] = mapped_column(sa.String(12), nullable=False, default="Scheduled")
    generated_wo_id: Mapped[str | None] = mapped_column(sa.ForeignKey("work_orders.id"))
    completed_at: Mapped[str | None] = mapped_column(sa.String(32))
    skip_reason: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=utcnow_iso)
    __table_args__ = (
        sa.UniqueConstraint("plan_id", "due_key", name="uq_pm_occurrence"),
        sa.CheckConstraint(f"status IN ({_in(OCCURRENCE_STATUS)})", name="status_valid"),
    )


sa.Index("ix_pm_occurrences_plan_status", PMOccurrence.plan_id, PMOccurrence.status)


class InspectionTemplate(Base, UuidPk, Timestamps):
    __tablename__ = "inspection_templates"
    template_code: Mapped[str] = mapped_column(sa.String(32), nullable=False, unique=True)
    title_ar: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    title_en: Mapped[str | None] = mapped_column(sa.String(200))
    asset_type_id: Mapped[str | None] = mapped_column(sa.ForeignKey("asset_types.id"))
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(sa.String(12), nullable=False, default="Active")
    __table_args__ = (
        sa.CheckConstraint(f"status IN ({_in(TEMPLATE_STATUS)})", name="status_valid"),
    )


class InspectionTemplateItem(Base, UuidPk):
    __tablename__ = "inspection_template_items"
    template_id: Mapped[str] = mapped_column(sa.ForeignKey("inspection_templates.id"),
                                             nullable=False)
    sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    label_ar: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    label_en: Mapped[str | None] = mapped_column(sa.String(200))
    response_type: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="pass_fail")
    unit_code: Mapped[str | None] = mapped_column(sa.ForeignKey("units.code"))
    required: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    fail_action: Mapped[str | None] = mapped_column(sa.String(200))
    __table_args__ = (
        sa.UniqueConstraint("template_id", "sequence"),
        sa.CheckConstraint("required IN (0,1)", name="required_bool"),
    )


class Inspection(Base, UuidPk):
    __tablename__ = "inspections"
    inspection_no: Mapped[str] = mapped_column(sa.String(24), nullable=False, unique=True)
    asset_id: Mapped[str] = mapped_column(sa.ForeignKey("assets.id"), nullable=False)
    template_id: Mapped[str | None] = mapped_column(sa.ForeignKey("inspection_templates.id"))
    template_version: Mapped[int | None] = mapped_column(sa.Integer)
    wo_id: Mapped[str | None] = mapped_column(sa.ForeignKey("work_orders.id"))
    inspector_id: Mapped[str | None] = mapped_column(sa.String(36))
    started_at: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=utcnow_iso)
    completed_at: Mapped[str | None] = mapped_column(sa.String(32))
    status: Mapped[str] = mapped_column(sa.String(12), nullable=False, default="Draft")
    notes: Mapped[str | None] = mapped_column(sa.Text)
    __table_args__ = (
        sa.CheckConstraint(f"status IN ({_in(INSPECTION_STATUS)})", name="status_valid"),
    )


sa.Index("ix_inspections_asset", Inspection.asset_id, Inspection.started_at)


class InspectionAnswer(Base, UuidPk):
    __tablename__ = "inspection_answers"
    inspection_id: Mapped[str] = mapped_column(sa.ForeignKey("inspections.id"), nullable=False)
    item_id: Mapped[str | None] = mapped_column(sa.ForeignKey("inspection_template_items.id"))
    item_snapshot_json: Mapped[str] = mapped_column(sa.Text, nullable=False)
    answer_json: Mapped[str] = mapped_column(sa.Text, nullable=False)
    pass_fail_state: Mapped[str | None] = mapped_column(sa.String(12))
    notes: Mapped[str | None] = mapped_column(sa.Text)
    __table_args__ = (sa.UniqueConstraint("inspection_id", "item_id"),)
