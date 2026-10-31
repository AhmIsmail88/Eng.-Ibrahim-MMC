"""Phase 2: failure reports, work orders, time logs, downtime (SPEC 8, 10)."""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UuidPk, utcnow_iso

WO_TYPE = ("PM", "CM", "INSPECTION", "OTHER")
WO_STATUS = ("Draft", "Open", "Assigned", "InProgress", "OnHold", "Completed", "Closed", "Cancelled")
PRIORITY = ("Critical", "High", "Medium", "Low")
FAILURE_STATUS = ("New", "Investigating", "Converted", "Resolved", "Cancelled")
TIME_CATEGORY = ("Work", "Travel", "Waiting")
DOWNTIME_TYPE = ("unplanned", "planned", "external")
EXPENSE_TYPE = ("External Repair", "Transport", "Other")
ASSIGNMENT_ROLE = ("Primary", "Assistant")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class FailureReport(Base, UuidPk):
    __tablename__ = "failure_reports"
    failure_no: Mapped[str] = mapped_column(sa.String(24), nullable=False, unique=True)
    asset_id: Mapped[str] = mapped_column(sa.ForeignKey("assets.id"), nullable=False)
    observed_at: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    reported_at: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=utcnow_iso)
    symptom: Mapped[str] = mapped_column(sa.Text, nullable=False)
    failure_code_id: Mapped[str | None] = mapped_column(sa.ForeignKey("failure_codes.id"))
    priority: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="Medium")
    root_cause_code_id: Mapped[str | None] = mapped_column(sa.ForeignKey("failure_codes.id"))
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="New")
    reporter_id: Mapped[str | None] = mapped_column(sa.String(36))
    __table_args__ = (
        sa.CheckConstraint(f"priority IN ({_in(PRIORITY)})", name="priority_valid"),
        sa.CheckConstraint(f"status IN ({_in(FAILURE_STATUS)})", name="status_valid"),
    )


sa.Index("ix_failure_asset_observed", FailureReport.asset_id, FailureReport.observed_at)
sa.Index("ix_failure_status", FailureReport.status)


class WorkOrder(Base, UuidPk, Timestamps):
    __tablename__ = "work_orders"
    wo_number: Mapped[str] = mapped_column(sa.String(24), nullable=False, unique=True)
    asset_id: Mapped[str] = mapped_column(sa.ForeignKey("assets.id"), nullable=False)
    type: Mapped[str] = mapped_column(sa.String(12), nullable=False, default="CM")
    pm_plan_id: Mapped[str | None] = mapped_column(sa.String(36))
    occurrence_id: Mapped[str | None] = mapped_column(sa.String(36))
    failure_id: Mapped[str | None] = mapped_column(sa.ForeignKey("failure_reports.id"))
    parent_work_order_id: Mapped[str | None] = mapped_column(sa.ForeignKey("work_orders.id"))
    priority: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="Medium")
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="Draft")
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text)
    requested_at: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=utcnow_iso)
    scheduled_start: Mapped[str | None] = mapped_column(sa.String(32))
    due_at: Mapped[str | None] = mapped_column(sa.String(32))
    actual_start_at: Mapped[str | None] = mapped_column(sa.String(32))
    actual_end_at: Mapped[str | None] = mapped_column(sa.String(32))
    completed_at: Mapped[str | None] = mapped_column(sa.String(32))
    closed_at: Mapped[str | None] = mapped_column(sa.String(32))
    closeout_notes: Mapped[str | None] = mapped_column(sa.Text)
    equipment_returned_to_service: Mapped[int | None] = mapped_column(sa.Integer)
    created_by: Mapped[str | None] = mapped_column(sa.String(36))
    __table_args__ = (
        sa.CheckConstraint(f"type IN ({_in(WO_TYPE)})", name="type_valid"),
        sa.CheckConstraint(f"status IN ({_in(WO_STATUS)})", name="status_valid"),
        sa.CheckConstraint(f"priority IN ({_in(PRIORITY)})", name="priority_valid"),
        sa.CheckConstraint(
            "equipment_returned_to_service IS NULL OR equipment_returned_to_service IN (0,1)",
            name="returned_bool"),
        sa.CheckConstraint("parent_work_order_id IS NULL OR parent_work_order_id <> id",
                           name="no_self_parent"),
    )


sa.Index("ix_work_orders_asset_status", WorkOrder.asset_id, WorkOrder.status)
sa.Index("ix_work_orders_due", WorkOrder.due_at, WorkOrder.status)


class WorkOrderTask(Base, UuidPk):
    __tablename__ = "work_order_tasks"
    work_order_id: Mapped[str] = mapped_column(sa.ForeignKey("work_orders.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    task_code_snapshot: Mapped[str | None] = mapped_column(sa.String(32))
    title_snapshot: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    required: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    response_type: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="done")
    result_json: Mapped[str | None] = mapped_column(sa.Text)
    is_completed: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    completed_at: Mapped[str | None] = mapped_column(sa.String(32))
    __table_args__ = (
        sa.UniqueConstraint("work_order_id", "sequence"),
        sa.CheckConstraint("required IN (0,1)", name="required_bool"),
        sa.CheckConstraint("is_completed IN (0,1)", name="completed_bool"),
    )


class WorkOrderAssignment(Base, UuidPk):
    __tablename__ = "work_order_assignments"
    work_order_id: Mapped[str] = mapped_column(sa.ForeignKey("work_orders.id"), nullable=False)
    technician_id: Mapped[str] = mapped_column(sa.ForeignKey("technicians.id"), nullable=False)
    assignment_role: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="Primary")
    assigned_at: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=utcnow_iso)
    assigned_by: Mapped[str | None] = mapped_column(sa.String(36))
    __table_args__ = (
        sa.UniqueConstraint("work_order_id", "technician_id"),
        sa.CheckConstraint(f"assignment_role IN ({_in(ASSIGNMENT_ROLE)})", name="role_valid"),
    )


class WorkOrderTimeLog(Base, UuidPk):
    __tablename__ = "work_order_time_logs"
    work_order_id: Mapped[str] = mapped_column(sa.ForeignKey("work_orders.id"), nullable=False)
    technician_id: Mapped[str] = mapped_column(sa.ForeignKey("technicians.id"), nullable=False)
    start_at: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    end_at: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    category: Mapped[str] = mapped_column(sa.String(12), nullable=False, default="Work")
    hourly_rate_minor_snapshot: Mapped[int | None] = mapped_column(sa.Integer)
    currency: Mapped[str | None] = mapped_column(sa.ForeignKey("currencies.code"))
    notes: Mapped[str | None] = mapped_column(sa.Text)
    __table_args__ = (
        sa.CheckConstraint(f"category IN ({_in(TIME_CATEGORY)})", name="category_valid"),
        sa.CheckConstraint("end_at >= start_at", name="interval_positive"),
        sa.CheckConstraint(
            "hourly_rate_minor_snapshot IS NULL OR hourly_rate_minor_snapshot >= 0",
            name="rate_nonneg"),
    )


sa.Index("ix_time_logs_wo", WorkOrderTimeLog.work_order_id, WorkOrderTimeLog.start_at)
sa.Index("ix_time_logs_tech", WorkOrderTimeLog.technician_id, WorkOrderTimeLog.start_at)


class WorkOrderStatusEvent(Base, UuidPk):
    __tablename__ = "work_order_status_events"
    work_order_id: Mapped[str] = mapped_column(sa.ForeignKey("work_orders.id"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(sa.String(16))
    to_status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    changed_at: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=utcnow_iso)
    actor_id: Mapped[str | None] = mapped_column(sa.String(36))
    reason: Mapped[str | None] = mapped_column(sa.Text)
    __table_args__ = (sa.CheckConstraint(f"to_status IN ({_in(WO_STATUS)})", name="to_status_valid"),)


sa.Index("ix_status_events_wo", WorkOrderStatusEvent.work_order_id,
         WorkOrderStatusEvent.changed_at)


class WorkOrderExternalExpense(Base, UuidPk):
    __tablename__ = "work_order_external_expenses"
    work_order_id: Mapped[str] = mapped_column(sa.ForeignKey("work_orders.id"), nullable=False)
    expense_date: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    expense_type: Mapped[str] = mapped_column(sa.String(24), nullable=False, default="Other")
    amount_minor: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    currency: Mapped[str] = mapped_column(sa.ForeignKey("currencies.code"), nullable=False)
    notes: Mapped[str | None] = mapped_column(sa.Text)
    supplier_id: Mapped[str | None] = mapped_column(sa.ForeignKey("suppliers.id"))
    __table_args__ = (sa.CheckConstraint("amount_minor >= 0", name="amount_nonneg"),)


class DowntimeEvent(Base, UuidPk):
    __tablename__ = "downtime_events"
    asset_id: Mapped[str] = mapped_column(sa.ForeignKey("assets.id"), nullable=False)
    failure_id: Mapped[str | None] = mapped_column(sa.ForeignKey("failure_reports.id"))
    work_order_id: Mapped[str | None] = mapped_column(sa.ForeignKey("work_orders.id"))
    started_at: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    ended_at: Mapped[str | None] = mapped_column(sa.String(32))
    downtime_type: Mapped[str] = mapped_column(sa.String(12), nullable=False, default="unplanned")
    affected_function: Mapped[str | None] = mapped_column(sa.String(120))
    reason: Mapped[str | None] = mapped_column(sa.Text)
    actor_id: Mapped[str | None] = mapped_column(sa.String(36))
    approved_by: Mapped[str | None] = mapped_column(sa.String(36))
    __table_args__ = (
        sa.CheckConstraint(f"downtime_type IN ({_in(DOWNTIME_TYPE)})", name="type_valid"),
        sa.CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="end_after_start"),
    )


sa.Index("ix_downtime_asset_start", DowntimeEvent.asset_id, DowntimeEvent.started_at)
