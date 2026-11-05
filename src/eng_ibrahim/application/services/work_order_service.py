"""Work orders: creation, the SPEC 10.3.1 state machine, time, cost (SPEC 10)."""
from __future__ import annotations

import builtins
from datetime import datetime

from sqlalchemy import func, or_, select

from ...domain.exceptions import DomainError
from ...domain.permissions import can_edit
from ...domain.policies import wo_state_machine as sm
from ...domain.text_normalization import search_pattern
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    Asset,
    FailureReport,
    Supplier,
    Technician,
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderExternalExpense,
    WorkOrderStatusEvent,
    WorkOrderTask,
    WorkOrderTimeLog,
)
from ...infrastructure.database.orm_models.base import utcnow_iso
from ...infrastructure.database.orm_models.maintenance import (
    EXPENSE_TYPE,
    PRIORITY,
    TIME_CATEGORY,
    WO_STATUS,
    WO_TYPE,
)
from ..dto.maintenance import (
    StatusEventRow,
    TaskRow,
    TimeLogRow,
    WoCost,
    WoDetail,
    WoRow,
)
from ..dto.result import Result
from .audit import write_audit
from .auth_service import AuthUser
from .failure_service import FailureService
from .inventory_service import InventoryService
from .numbering import next_number
from .pm_service import PMService
from .settings_service import SettingsService

# Before work starts the order can still be corrected (review F-05).
EDITABLE_STATUSES = (sm.DRAFT, sm.OPEN, sm.ASSIGNED)


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


def _minutes(start: str, end: str) -> int:
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(0, int((b - a).total_seconds() // 60))


class WorkOrderService:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._settings = SettingsService(db)

    # ---------------- reads ----------------
    def list(self, status: str | None = None, asset_id: str | None = None,
             type_: str | None = None, query: str = "") -> builtins.list[WoRow]:
        with self._db.session() as s:
            stmt = (select(WorkOrder, Asset)
                    .join(Asset, WorkOrder.asset_id == Asset.id)
                    .order_by(WorkOrder.requested_at.desc()))
            if status:
                stmt = stmt.where(WorkOrder.status == status)
            if asset_id:
                stmt = stmt.where(WorkOrder.asset_id == asset_id)
            if type_:
                stmt = stmt.where(WorkOrder.type == type_)
            term = search_pattern(query)
            if term:
                stmt = stmt.where(or_(
                    WorkOrder.wo_number.like(f"%{term}%", escape="\\"),
                    WorkOrder.title.like(f"%{term}%", escape="\\"),
                    Asset.search_norm.like(f"%{term}%", escape="\\"),
                ))
            rows = []
            for wo, asset in s.execute(stmt).all():
                primary = s.scalar(
                    select(Technician.full_name)
                    .join(WorkOrderAssignment,
                          WorkOrderAssignment.technician_id == Technician.id)
                    .where(WorkOrderAssignment.work_order_id == wo.id,
                           WorkOrderAssignment.assignment_role == "Primary"))
                rows.append(WoRow(
                    id=wo.id, number=wo.wo_number, asset_id=asset.id,
                    asset_code=asset.asset_code, type=wo.type, title=wo.title,
                    status=wo.status, priority=wo.priority, due_at=wo.due_at,
                    assigned_to=primary))
            return rows

    def detail(self, wo_id: str) -> WoDetail | None:
        with self._db.session() as s:
            wo = s.get(WorkOrder, wo_id)
            if wo is None:
                return None
            asset = s.get(Asset, wo.asset_id)
            tasks = [TaskRow(id=t.id, sequence=t.sequence, title=t.title_snapshot,
                             required=bool(t.required), response_type=t.response_type,
                             result=t.result_json, is_completed=bool(t.is_completed))
                     for t in s.scalars(select(WorkOrderTask)
                                        .where(WorkOrderTask.work_order_id == wo_id)
                                        .order_by(WorkOrderTask.sequence))]
            logs = []
            for log in s.scalars(select(WorkOrderTimeLog)
                                 .where(WorkOrderTimeLog.work_order_id == wo_id)
                                 .order_by(WorkOrderTimeLog.start_at)):
                tech = s.get(Technician, log.technician_id)
                minutes = _minutes(log.start_at, log.end_at)
                cost = (None if log.hourly_rate_minor_snapshot is None
                        else int(log.hourly_rate_minor_snapshot * minutes / 60))
                logs.append(TimeLogRow(id=log.id, technician=tech.full_name if tech else "",
                                       start_at=log.start_at, end_at=log.end_at,
                                       category=log.category, minutes=minutes, cost_minor=cost))
            events = [StatusEventRow(at=e.changed_at, from_status=e.from_status,
                                     to_status=e.to_status, reason=e.reason)
                      for e in s.scalars(select(WorkOrderStatusEvent)
                                         .where(WorkOrderStatusEvent.work_order_id == wo_id)
                                         .order_by(WorkOrderStatusEvent.changed_at))]
            assignees = [
                tech.full_name for tech in s.scalars(
                    select(Technician)
                    .join(WorkOrderAssignment,
                          WorkOrderAssignment.technician_id == Technician.id)
                    .where(WorkOrderAssignment.work_order_id == wo_id)
                    .order_by(WorkOrderAssignment.assignment_role))
            ]
            return WoDetail(
                id=wo.id, number=wo.wo_number, asset_id=wo.asset_id,
                asset_code=asset.asset_code if asset else "", type=wo.type,
                title=wo.title, description=wo.description, status=wo.status,
                priority=wo.priority, requested_at=wo.requested_at, due_at=wo.due_at,
                actual_start_at=wo.actual_start_at, actual_end_at=wo.actual_end_at,
                completed_at=wo.completed_at, closed_at=wo.closed_at,
                closeout_notes=wo.closeout_notes,
                equipment_returned_to_service=(None if wo.equipment_returned_to_service is None
                                               else bool(wo.equipment_returned_to_service)),
                failure_id=wo.failure_id, tasks=tasks, time_logs=logs, events=events,
                assignees=assignees, cost=self.cost(wo_id))

    def cost(self, wo_id: str) -> WoCost | None:
        currency = self._settings.get("currency_code", "EGP")
        with self._db.session() as s:
            wo = s.get(WorkOrder, wo_id)
            if wo is None:
                return None
            labour = 0
            missing_rate = False
            labour_foreign = False
            for log in s.scalars(select(WorkOrderTimeLog)
                                 .where(WorkOrderTimeLog.work_order_id == wo_id)):
                minutes = _minutes(log.start_at, log.end_at)
                if log.hourly_rate_minor_snapshot is None:
                    missing_rate = True
                elif log.currency and log.currency != currency:
                    labour_foreign = True
                else:
                    labour += int(log.hourly_rate_minor_snapshot * minutes / 60)
            external = 0
            mixed = False
            for exp in s.scalars(select(WorkOrderExternalExpense)
                                 .where(WorkOrderExternalExpense.work_order_id == wo_id)):
                if exp.currency != currency:
                    mixed = True
                    continue
                external += exp.amount_minor
        parts_minor, parts_currency = InventoryService(self._db).work_order_part_cost(wo_id)
        flags: builtins.list[str] = []
        if parts_currency and parts_currency != currency:
            flags.append("parts_currency_excluded")
            parts_minor = 0
        if missing_rate:
            flags.append("labour_rate_missing")
        if labour_foreign:
            flags.append("labour_currency_excluded")
        if mixed:
            flags.append("mixed_currency_excluded")
        completeness = "; ".join(flags) if flags else "complete"
        return WoCost(labour_minor=labour, external_minor=external,
                      parts_minor=parts_minor, currency=currency,
                      completeness=completeness)

    # ---------------- commands ----------------
    def create(self, actor: AuthUser | None, asset_id: str, type_: str, title: str,
               description: str | None = None, priority: str = "Medium",
               due_at: str | None = None, scheduled_start: str | None = None,
               failure_id: str | None = None,
               tasks: builtins.list[tuple[str, bool]] | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if type_ not in WO_TYPE:
            return Result.failure("err.wo_type_invalid")
        if priority not in PRIORITY:
            return Result.failure("err.priority_invalid")
        title = (title or "").strip()
        if not title:
            return Result.failure("err.wo_title_required")
        with self._db.unit_of_work() as s:
            asset = s.get(Asset, asset_id)
            if asset is None or not asset.is_active:
                return Result.failure("err.asset_not_found")
            wo = WorkOrder(
                wo_number=next_number(s, "WO"), asset_id=asset_id, type=type_,
                title=title, description=description, priority=priority,
                status="Draft", due_at=due_at, scheduled_start=scheduled_start,
                failure_id=failure_id, created_by=actor.id if actor else None,
            )
            s.add(wo)
            s.flush()
            for index, (task_title, required) in enumerate(tasks or [], start=1):
                s.add(WorkOrderTask(work_order_id=wo.id, sequence=index,
                                    title_snapshot=(task_title or "").strip() or f"#{index}",
                                    required=1 if required else 0, response_type="done"))
            s.add(WorkOrderStatusEvent(work_order_id=wo.id, from_status=None,
                                       to_status="Draft", reason="created",
                                       actor_id=actor.id if actor else None))
            write_audit(s, "work_order", wo.id, "wo_created",
                        actor_id=actor.id if actor else None,
                        after={"number": wo.wo_number, "asset": asset.asset_code})
            return Result.success(wo.id)

    def create_from_failure(self, actor: AuthUser | None, failure_id: str,
                            title: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            failure = s.get(FailureReport, failure_id)
            if failure is None:
                return Result.failure("err.failure_not_found")
            if failure.status not in ("New", "Investigating"):
                return Result.failure("err.failure_already_converted")
            wo = WorkOrder(
                wo_number=next_number(s, "WO"), asset_id=failure.asset_id, type="CM",
                failure_id=failure.id, priority=failure.priority, status="Draft",
                title=(title or failure.symptom[:120]),
                description=failure.symptom, created_by=actor.id if actor else None,
            )
            s.add(wo)
            s.flush()
            s.add(WorkOrderStatusEvent(work_order_id=wo.id, from_status=None,
                                       to_status="Draft", reason="from_failure",
                                       actor_id=actor.id if actor else None))
            FailureService(self._db).mark_converted(s, failure_id,
                                                    actor.id if actor else None)
            write_audit(s, "work_order", wo.id, "wo_created_from_failure",
                        actor_id=actor.id if actor else None,
                        after={"number": wo.wo_number, "failure": failure.failure_no})
            return Result.success(wo.id)

    def transition(self, actor: AuthUser | None, wo_id: str, target: str,
                   reason: str | None = None,
                   equipment_returned: bool | None = None,
                   closeout_notes: str | None = None) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            wo = s.get(WorkOrder, wo_id)
            if wo is None:
                return Result.failure("err.wo_not_found")
            payload: dict[str, object] = {
                "asset_id": wo.asset_id, "title": wo.title, "priority": wo.priority,
                "requested_at": wo.requested_at, "reason": reason,
                "actual_start_at": wo.actual_start_at or utcnow_iso(),
                "actual_end_at": utcnow_iso(), "completed_at": utcnow_iso(),
                "closed_at": utcnow_iso(),
                "technician_id": s.scalar(select(WorkOrderAssignment.technician_id)
                                          .where(WorkOrderAssignment.work_order_id == wo_id)),
                "assigned_at": utcnow_iso(),
            }
            if target == sm.COMPLETED:
                if equipment_returned is None:
                    return Result.failure("err.equipment_return_required")
                incomplete = s.scalar(
                    select(func.count()).select_from(WorkOrderTask).where(
                        WorkOrderTask.work_order_id == wo_id,
                        WorkOrderTask.required == 1,
                        WorkOrderTask.is_completed == 0))
                if incomplete:
                    return Result.failure("err.wo_tasks_incomplete")
            try:
                sm.check(wo.status, target, actor.role if actor else None, payload)
            except DomainError as exc:
                return Result.failure(exc.code)

            before = wo.status
            now = utcnow_iso()
            wo.status = target
            if target == sm.IN_PROGRESS and wo.actual_start_at is None:
                wo.actual_start_at = now
            if target == sm.COMPLETED:
                wo.actual_end_at = now
                wo.completed_at = now
                wo.equipment_returned_to_service = 1 if equipment_returned else 0
                PMService(self._db).on_work_order_completed(s, wo)
            if target == sm.CLOSED:
                wo.closed_at = now
                wo.closeout_notes = closeout_notes
            if target == sm.IN_PROGRESS and before in (sm.COMPLETED, sm.CLOSED):
                # Reopened: the previous completion/close no longer holds.
                wo.completed_at = None
                wo.closed_at = None
                wo.actual_end_at = None
                wo.equipment_returned_to_service = None
            s.add(WorkOrderStatusEvent(work_order_id=wo.id, from_status=before,
                                       to_status=target, reason=reason,
                                       actor_id=actor.id if actor else None))
            write_audit(s, "work_order", wo.id, "wo_status_changed",
                        actor_id=actor.id if actor else None,
                        before={"status": before}, after={"status": target}, reason=reason)
            return Result.success()

    def update(self, actor: AuthUser | None, wo_id: str, title: str,
               description: str | None, priority: str, due_at: str | None) -> Result[None]:
        """Correct a work order before work starts (review F-05).

        Number, asset and type never change; once In Progress the order is the record of
        what was done and is no longer edited.
        """
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if priority not in PRIORITY:
            return Result.failure("err.priority_invalid")
        title = (title or "").strip()
        if not title:
            return Result.failure("err.wo_title_required")
        with self._db.unit_of_work() as s:
            wo = s.get(WorkOrder, wo_id)
            if wo is None:
                return Result.failure("err.wo_not_found")
            if wo.status not in EDITABLE_STATUSES:
                return Result.failure("err.wo_locked_for_edit")
            fields = {"title": title, "description": (description or "").strip() or None,
                      "priority": priority, "due_at": due_at or None}
            before = {k: getattr(wo, k) for k in fields if getattr(wo, k) != fields[k]}
            if not before:
                return Result.success()
            for key in before:
                setattr(wo, key, fields[key])
            write_audit(s, "work_order", wo.id, "wo_updated",
                        actor_id=actor.id if actor else None, before=before,
                        after={k: fields[k] for k in before})
            return Result.success()

    def assign(self, actor: AuthUser | None, wo_id: str, technician_id: str) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        must_move = False
        with self._db.unit_of_work() as s:
            wo = s.get(WorkOrder, wo_id)
            tech = s.get(Technician, technician_id)
            if wo is None:
                return Result.failure("err.wo_not_found")
            if tech is None or not tech.is_active:
                return Result.failure("err.technician_inactive")
            exists = s.scalar(select(WorkOrderAssignment.id).where(
                WorkOrderAssignment.work_order_id == wo_id,
                WorkOrderAssignment.technician_id == technician_id))
            if exists is None:
                has_primary = s.scalar(select(WorkOrderAssignment.id).where(
                    WorkOrderAssignment.work_order_id == wo_id,
                    WorkOrderAssignment.assignment_role == "Primary"))
                s.add(WorkOrderAssignment(
                    work_order_id=wo_id, technician_id=technician_id,
                    assignment_role="Assistant" if has_primary else "Primary",
                    assigned_by=actor.id if actor else None))
            must_move = wo.status == sm.OPEN
        if must_move:
            return self.transition(actor, wo_id, sm.ASSIGNED, reason="assigned")
        return Result.success()

    def add_task(self, actor: AuthUser | None, wo_id: str, title: str,
                 required: bool = True) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        title = (title or "").strip()
        if not title:
            return Result.failure("err.task_title_required")
        with self._db.unit_of_work() as s:
            wo = s.get(WorkOrder, wo_id)
            if wo is None:
                return Result.failure("err.wo_not_found")
            if wo.status in (sm.CLOSED, sm.CANCELLED):
                return Result.failure("err.wo_read_only")
            sequence = int(s.scalar(select(func.coalesce(func.max(WorkOrderTask.sequence), 0))
                                    .where(WorkOrderTask.work_order_id == wo_id)) or 0) + 1
            row = WorkOrderTask(work_order_id=wo_id, sequence=sequence,
                                title_snapshot=title, required=1 if required else 0)
            s.add(row)
            s.flush()
            return Result.success(row.id)

    def set_task_result(self, actor: AuthUser | None, wo_id: str, task_id: str,
                        result: str, completed: bool) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        with self._db.unit_of_work() as s:
            wo = s.get(WorkOrder, wo_id)
            if wo is None:
                return Result.failure("err.wo_not_found")
            if wo.status in (sm.CLOSED, sm.CANCELLED):
                return Result.failure("err.wo_read_only")
            task = s.get(WorkOrderTask, task_id)
            if task is None or task.work_order_id != wo_id:
                return Result.failure("err.task_not_found")
            task.result_json = result
            task.is_completed = 1 if completed else 0
            task.completed_at = utcnow_iso() if completed else None
            return Result.success()

    def add_time_log(self, actor: AuthUser | None, wo_id: str, technician_id: str,
                     start_at: str, end_at: str, category: str = "Work",
                     notes: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if category not in TIME_CATEGORY:
            return Result.failure("err.time_category_invalid")
        if _minutes(start_at, end_at) <= 0:
            return Result.failure("err.time_interval_invalid")
        with self._db.unit_of_work() as s:
            wo = s.get(WorkOrder, wo_id)
            tech = s.get(Technician, technician_id)
            if wo is None:
                return Result.failure("err.wo_not_found")
            if wo.status in (sm.CLOSED, sm.CANCELLED):
                return Result.failure("err.wo_read_only")
            if tech is None or not tech.is_active:
                return Result.failure("err.technician_inactive")
            overlap = s.scalar(select(WorkOrderTimeLog.id).where(
                WorkOrderTimeLog.technician_id == technician_id,
                WorkOrderTimeLog.start_at < end_at,
                WorkOrderTimeLog.end_at > start_at))
            if overlap:
                return Result.failure("err.time_overlap")
            row = WorkOrderTimeLog(
                work_order_id=wo_id, technician_id=technician_id, start_at=start_at,
                end_at=end_at, category=category,
                hourly_rate_minor_snapshot=tech.hourly_rate_minor,
                currency=tech.currency, notes=notes)
            s.add(row)
            s.flush()
            return Result.success(row.id)

    def add_expense(self, actor: AuthUser | None, wo_id: str, expense_date: str,
                    expense_type: str, amount_minor: int, currency: str | None = None,
                    notes: str | None = None, supplier_id: str | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if amount_minor < 0:
            return Result.failure("err.cost_negative")
        if expense_type not in EXPENSE_TYPE:
            return Result.failure("err.expense_type_invalid")
        currency = currency or self._settings.get("currency_code", "EGP")
        with self._db.unit_of_work() as s:
            wo = s.get(WorkOrder, wo_id)
            if wo is None:
                return Result.failure("err.wo_not_found")
            if wo.status in (sm.CLOSED, sm.CANCELLED):
                return Result.failure("err.wo_read_only")
            if supplier_id and s.get(Supplier, supplier_id) is None:
                return Result.failure("err.not_found")
            row = WorkOrderExternalExpense(
                work_order_id=wo_id, expense_date=expense_date, expense_type=expense_type,
                amount_minor=amount_minor, currency=currency, notes=notes,
                supplier_id=supplier_id)
            s.add(row)
            s.flush()
            return Result.success(row.id)

    def statuses(self) -> tuple[str, ...]:
        return WO_STATUS
