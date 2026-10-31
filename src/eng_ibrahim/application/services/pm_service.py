"""Preventive maintenance: plans, occurrences and work-order generation (SPEC 9)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from ...domain.permissions import can_edit
from ...domain.policies import pm_schedule as sched
from ...domain.text_normalization import search_pattern
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import (
    Asset,
    MeterReading,
    PMOccurrence,
    PMPlan,
    PMPlanTask,
    WorkOrder,
    WorkOrderStatusEvent,
    WorkOrderTask,
)
from ...infrastructure.database.orm_models.base import utcnow_iso
from ...infrastructure.database.orm_models.preventive import (
    ANCHOR_POLICY,
    CATCH_UP_POLICY,
    INTERVAL_UNIT,
    PLAN_STATUS,
    PLAN_STRATEGY,
    TRIGGER_POLICY,
)
from ..dto.preventive import OccurrenceRow, PlanDetail, PlanRow, PlanTaskRow
from ..dto.result import Result
from .audit import write_audit
from .auth_service import AuthUser
from .numbering import next_number, next_plain_number

OPEN_WO_STATUSES = ("Open", "Assigned", "InProgress", "OnHold")


def _require_editor(actor: AuthUser | None) -> Result[None]:
    if actor is None or not can_edit(actor.role):
        return Result.failure("err.permission_denied")
    return Result.success()


def _dec(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class PMService:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ---------------- reads ----------------
    def list(self, status: str | None = None, query: str = "") -> list[PlanRow]:
        with self._db.session() as s:
            stmt = (select(PMPlan, Asset)
                    .join(Asset, PMPlan.asset_id == Asset.id)
                    .order_by(PMPlan.plan_code))
            if status:
                stmt = stmt.where(PMPlan.status == status)
            term = search_pattern(query)
            if term:
                stmt = stmt.where(or_(
                    PMPlan.plan_code.like(f"%{term}%", escape="\\"),
                    PMPlan.title.like(f"%{term}%", escape="\\"),
                    Asset.search_norm.like(f"%{term}%", escape="\\"),
                ))
            rows = []
            for plan, asset in s.execute(stmt).all():
                latest = self._latest_meter(s, plan)
                open_wo = self._has_open_wo(s, plan.id)
                state = self._state(plan, latest, open_wo)
                rows.append(PlanRow(
                    id=plan.id, code=plan.plan_code, asset_id=asset.id,
                    asset_code=asset.asset_code, title=plan.title,
                    strategy=plan.strategy, trigger_policy=plan.trigger_policy,
                    next_due_date=plan.next_due_date, next_due_meter=plan.next_due_meter,
                    latest_meter=str(latest) if latest is not None else None,
                    state=state, status=plan.status))
            return rows

    def detail(self, plan_id: str) -> PlanDetail | None:
        with self._db.session() as s:
            plan = s.get(PMPlan, plan_id)
            if plan is None:
                return None
            asset = s.get(Asset, plan.asset_id)
            tasks = [PlanTaskRow(id=t.id, sequence=t.sequence, title=t.title_snapshot,
                                 required=bool(t.required), response_type=t.response_type)
                     for t in s.scalars(select(PMPlanTask)
                                        .where(PMPlanTask.plan_id == plan_id)
                                        .order_by(PMPlanTask.sequence))]
            occurrences = []
            for occ in s.scalars(select(PMOccurrence)
                                 .where(PMOccurrence.plan_id == plan_id)
                                 .order_by(PMOccurrence.created_at.desc()).limit(50)):
                wo = s.get(WorkOrder, occ.generated_wo_id) if occ.generated_wo_id else None
                occurrences.append(OccurrenceRow(
                    id=occ.id, due_key=occ.due_key, due_date=occ.due_date_snapshot,
                    due_meter=occ.due_meter_snapshot, status=occ.status,
                    wo_number=wo.wo_number if wo else None, skip_reason=occ.skip_reason))
            return PlanDetail(
                id=plan.id, code=plan.plan_code, asset_id=plan.asset_id,
                asset_code=asset.asset_code if asset else "", title=plan.title,
                description=plan.description, strategy=plan.strategy,
                trigger_policy=plan.trigger_policy,
                calendar_interval_value=plan.calendar_interval_value,
                calendar_interval_unit=plan.calendar_interval_unit,
                meter_id=plan.meter_id, meter_interval_value=plan.meter_interval_value,
                next_due_date=plan.next_due_date, next_due_meter=plan.next_due_meter,
                warning_days=plan.warning_days, lead_days=plan.lead_days,
                completion_anchor_policy=plan.completion_anchor_policy,
                status=plan.status, tasks=tasks, occurrences=occurrences)

    # ---------------- commands ----------------
    def create(self, actor: AuthUser | None, asset_id: str, title: str,
               strategy: str, trigger_policy: str,
               calendar_interval_value: int | None = None,
               calendar_interval_unit: str | None = None,
               meter_id: str | None = None, meter_interval_value: str | None = None,
               base_date: str | None = None, base_meter_value: str | None = None,
               warning_days: int = 7, warning_meter: str | None = None,
               lead_days: int = 7, description: str | None = None,
               completion_anchor_policy: str = "FROM_COMPLETION",
               catch_up_policy: str = "LATEST_ONLY_AND_LOG_SKIPPED",
               tasks: list[tuple[str, bool]] | None = None) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if strategy not in PLAN_STRATEGY:
            return Result.failure("err.pm_strategy_invalid")
        if trigger_policy not in TRIGGER_POLICY:
            return Result.failure("err.pm_trigger_invalid")
        if completion_anchor_policy not in ANCHOR_POLICY:
            return Result.failure("err.pm_anchor_invalid")
        if catch_up_policy not in CATCH_UP_POLICY:
            return Result.failure("err.pm_catchup_invalid")
        title = (title or "").strip()
        if not title:
            return Result.failure("err.pm_title_required")
        needs_date = trigger_policy in ("DATE_ONLY", "FIRST_DUE", "BOTH_REQUIRED")
        needs_meter = trigger_policy in ("METER_ONLY", "FIRST_DUE", "BOTH_REQUIRED")
        if needs_date:
            if not calendar_interval_value or calendar_interval_value <= 0:
                return Result.failure("err.pm_interval_required")
            if calendar_interval_unit not in INTERVAL_UNIT:
                return Result.failure("err.pm_interval_unit_invalid")
        if needs_meter:
            if not meter_id:
                return Result.failure("err.pm_meter_required")
            interval = _dec(meter_interval_value)
            if interval is None or interval <= 0:
                return Result.failure("err.pm_meter_interval_required")
        if warning_days < 0 or lead_days < 0:
            return Result.failure("err.pm_offsets_invalid")
        today = date.today()
        base = sched.parse_date(base_date) or today
        with self._db.unit_of_work() as s:
            asset = s.get(Asset, asset_id)
            if asset is None or not asset.is_active:
                return Result.failure("err.asset_not_found")
            next_due_date = None
            if needs_date:
                next_due_date = sched.add_interval(
                    base, int(calendar_interval_value), calendar_interval_unit).isoformat()
            next_due_meter = None
            if needs_meter:
                base_meter = _dec(base_meter_value)
                if base_meter is None:
                    return Result.failure("err.pm_base_meter_required")
                next_due_meter = str(base_meter + Decimal(str(meter_interval_value)))
            plan = PMPlan(
                plan_code=next_plain_number(s, "PM"), asset_id=asset_id, title=title,
                description=description, strategy=strategy, trigger_policy=trigger_policy,
                calendar_interval_value=(int(calendar_interval_value) if needs_date else None),
                calendar_interval_unit=(calendar_interval_unit if needs_date else None),
                meter_id=meter_id if needs_meter else None,
                meter_interval_value=(str(meter_interval_value) if needs_meter else None),
                base_date=base.isoformat(), base_meter_value=(base_meter_value or None),
                next_due_date=next_due_date, next_due_meter=next_due_meter,
                warning_days=warning_days, warning_meter=warning_meter, lead_days=lead_days,
                completion_anchor_policy=completion_anchor_policy,
                catch_up_policy=catch_up_policy, status="Active")
            s.add(plan)
            s.flush()
            for index, (task_title, required) in enumerate(tasks or [], start=1):
                s.add(PMPlanTask(plan_id=plan.id, sequence=index,
                                 title_snapshot=(task_title or "").strip() or f"#{index}",
                                 required=1 if required else 0))
            write_audit(s, "pm_plan", plan.id, "pm_plan_created",
                        actor_id=actor.id if actor else None,
                        after={"code": plan.plan_code, "asset": asset.asset_code})
            return Result.success(plan.id)

    def set_status(self, actor: AuthUser | None, plan_id: str, status: str) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if status not in PLAN_STATUS:
            return Result.failure("err.pm_status_invalid")
        with self._db.unit_of_work() as s:
            plan = s.get(PMPlan, plan_id)
            if plan is None:
                return Result.failure("err.pm_not_found")
            before = plan.status
            plan.status = status
            write_audit(s, "pm_plan", plan.id, "pm_plan_status",
                        actor_id=actor.id if actor else None,
                        before={"status": before}, after={"status": status})
            return Result.success()

    def skip(self, actor: AuthUser | None, plan_id: str, reason: str) -> Result[None]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        if not (reason or "").strip():
            return Result.failure("err.reason_required")
        with self._db.unit_of_work() as s:
            plan = s.get(PMPlan, plan_id)
            if plan is None:
                return Result.failure("err.pm_not_found")
            due_date = sched.parse_date(plan.next_due_date)
            due_meter = plan.next_due_meter
            key = sched.due_key(plan.id, due_date, _dec(due_meter))
            if s.scalar(select(PMOccurrence.id).where(PMOccurrence.plan_id == plan.id,
                                                      PMOccurrence.due_key == key)):
                return Result.failure("err.pm_occurrence_exists")
            occ = PMOccurrence(plan_id=plan.id, due_key=key,
                               due_date_snapshot=plan.next_due_date,
                               due_meter_snapshot=due_meter, status="Skipped",
                               skip_reason=reason)
            s.add(occ)
            self._advance(s, plan, due_date)
            write_audit(s, "pm_plan", plan.id, "pm_occurrence_skipped",
                        actor_id=actor.id if actor else None, reason=reason)
            return Result.success()

    def generate(self, actor: AuthUser | None, plan_id: str) -> Result[str]:
        guard = _require_editor(actor)
        if not guard.ok:
            return Result.failure(guard.error_code or "err.permission_denied")
        try:
            return self._generate(actor, plan_id)
        except IntegrityError:
            # Concurrent click: the unique (plan_id, due_key) index already won.
            with self._db.session() as s:
                occ = s.scalars(select(PMOccurrence)
                                .where(PMOccurrence.plan_id == plan_id)
                                .order_by(PMOccurrence.created_at.desc()).limit(1)).first()
                if occ and occ.generated_wo_id:
                    return Result.success(occ.generated_wo_id)
            return Result.failure("err.pm_occurrence_exists")

    def _generate(self, actor: AuthUser | None, plan_id: str) -> Result[str]:
        today = date.today()
        with self._db.unit_of_work() as s:
            plan = s.get(PMPlan, plan_id)
            if plan is None:
                return Result.failure("err.pm_not_found")
            if plan.status != "Active":
                return Result.failure("err.pm_paused")
            self._catch_up(s, plan, today)
            latest = self._latest_meter(s, plan)
            state = self._state(plan, latest, self._has_open_wo(s, plan.id))
            if state == sched.NO_VALID_METER:
                return Result.failure("err.pm_no_meter")
            if state == sched.AWAITING:
                return Result.failure("err.pm_awaiting")
            if state == sched.NOT_DUE:
                return Result.failure("err.pm_not_due")
            due_date = sched.parse_date(plan.next_due_date)
            key = sched.due_key(plan.id, due_date, _dec(plan.next_due_meter))
            existing = s.scalars(select(PMOccurrence).where(
                PMOccurrence.plan_id == plan.id, PMOccurrence.due_key == key)).first()
            if existing is not None:
                if existing.generated_wo_id:
                    return Result.success(existing.generated_wo_id)
                return Result.failure("err.pm_occurrence_exists")
            occurrence = PMOccurrence(plan_id=plan.id, due_key=key,
                                      due_date_snapshot=plan.next_due_date,
                                      due_meter_snapshot=plan.next_due_meter,
                                      status="Generated")
            s.add(occurrence)
            s.flush()
            asset = s.get(Asset, plan.asset_id)
            wo = WorkOrder(
                wo_number=next_number(s, "WO"), asset_id=plan.asset_id, type="PM",
                pm_plan_id=plan.id, occurrence_id=occurrence.id, status="Draft",
                title=plan.title,
                description=plan.description,
                priority="High" if asset and asset.criticality in ("Critical", "High") else "Medium",
                due_at=plan.next_due_date,
                created_by=actor.id if actor else None)
            s.add(wo)
            s.flush()
            for task in s.scalars(select(PMPlanTask).where(PMPlanTask.plan_id == plan.id)
                                  .order_by(PMPlanTask.sequence)):
                s.add(WorkOrderTask(work_order_id=wo.id, sequence=task.sequence,
                                    title_snapshot=task.title_snapshot,
                                    required=task.required,
                                    response_type=task.response_type))
            s.add(WorkOrderStatusEvent(work_order_id=wo.id, from_status=None,
                                       to_status="Draft", reason="pm_generated",
                                       actor_id=actor.id if actor else None))
            occurrence.generated_wo_id = wo.id
            write_audit(s, "pm_plan", plan.id, "pm_work_order_generated",
                        actor_id=actor.id if actor else None,
                        after={"wo": wo.wo_number, "due": plan.next_due_date})
            return Result.success(wo.id)

    # ---------------- completion hook ----------------
    def on_work_order_completed(self, session, wo: WorkOrder) -> None:
        """Called by WorkOrderService in the same transaction when a PM WO completes."""
        if not wo.pm_plan_id:
            return
        occurrence = session.scalars(select(PMOccurrence).where(
            PMOccurrence.generated_wo_id == wo.id)).first()
        plan = session.get(PMPlan, wo.pm_plan_id)
        if plan is None:
            return
        completed_on = sched.parse_date(wo.actual_end_at or wo.completed_at) or date.today()
        if occurrence is not None and occurrence.status != "Completed":
            occurrence.status = "Completed"
            occurrence.completed_at = wo.completed_at or utcnow_iso()
        if plan.completion_anchor_policy == "FROM_COMPLETION":
            base = completed_on
        else:
            base = sched.parse_date(plan.next_due_date) or completed_on
        if plan.calendar_interval_value and plan.calendar_interval_unit:
            nxt = sched.add_interval(base, plan.calendar_interval_value,
                                     plan.calendar_interval_unit)
            if plan.completion_anchor_policy == "FROM_FIXED_BASELINE":
                while nxt <= completed_on:
                    nxt = sched.add_interval(nxt, plan.calendar_interval_value,
                                             plan.calendar_interval_unit)
            plan.next_due_date = nxt.isoformat()
        if plan.meter_id and plan.meter_interval_value:
            latest = self._latest_meter(session, plan) or Decimal(0)
            plan.next_due_meter = str(latest + Decimal(plan.meter_interval_value))
        plan.version = (plan.version or 1) + 1
        write_audit(session, "pm_plan", plan.id, "pm_completed",
                    after={"wo": wo.wo_number, "next_due": plan.next_due_date})

    # ---------------- helpers ----------------
    @staticmethod
    def _latest_meter(session, plan: PMPlan) -> Decimal | None:
        if not plan.meter_id:
            return None
        row = session.scalars(select(MeterReading)
                              .where(MeterReading.meter_id == plan.meter_id)
                              .where(MeterReading.quality != "rejected")
                              .order_by(MeterReading.reading_at.desc()).limit(1)).first()
        return _dec(row.value_decimal) if row else None

    @staticmethod
    def _has_open_wo(session, plan_id: str) -> bool:
        return bool(session.scalar(select(WorkOrder.id).where(
            WorkOrder.pm_plan_id == plan_id,
            WorkOrder.status.in_(OPEN_WO_STATUSES))))

    @staticmethod
    def _state(plan: PMPlan, latest: Decimal | None, open_wo: bool) -> str:
        schedule = sched.Schedule(
            trigger_policy=plan.trigger_policy,
            next_due_date=sched.parse_date(plan.next_due_date),
            next_due_meter=_dec(plan.next_due_meter),
            warning_days=plan.warning_days,
            warning_meter=_dec(plan.warning_meter),
            latest_meter=latest, status=plan.status, open_work_order=open_wo)
        return schedule.state(date.today())

    def _catch_up(self, session, plan: PMPlan, today: date) -> None:
        if not (plan.next_due_date and plan.calendar_interval_value
                and plan.calendar_interval_unit):
            return
        due = sched.parse_date(plan.next_due_date)
        if due is None or due >= today:
            return
        nxt, skipped = sched.advance_to_future(
            due, plan.calendar_interval_value, plan.calendar_interval_unit, today)
        for missed in skipped:
            key = sched.due_key(plan.id, missed, None)
            if not session.scalar(select(PMOccurrence.id).where(
                    PMOccurrence.plan_id == plan.id, PMOccurrence.due_key == key)):
                session.add(PMOccurrence(plan_id=plan.id, due_key=key,
                                         due_date_snapshot=missed.isoformat(),
                                         status="Skipped",
                                         skip_reason="missed while app was closed"))
        plan.next_due_date = nxt.isoformat()

    @staticmethod
    def _advance(session, plan: PMPlan, due: date | None) -> None:
        if plan.calendar_interval_value and plan.calendar_interval_unit and due is not None:
            plan.next_due_date = sched.add_interval(
                due, plan.calendar_interval_value, plan.calendar_interval_unit).isoformat()
        if plan.meter_id and plan.meter_interval_value and plan.next_due_meter:
            plan.next_due_meter = str(Decimal(plan.next_due_meter)
                                      + Decimal(plan.meter_interval_value))
        plan.version = (plan.version or 1) + 1
