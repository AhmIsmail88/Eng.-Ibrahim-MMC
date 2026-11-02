"""PM schedule arithmetic and states (SPEC 9.3)."""
from __future__ import annotations

from datetime import date

import pytest

from eng_ibrahim.domain.policies import pm_schedule as sched


def test_month_clamping_to_last_day() -> None:
    assert sched.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert sched.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert sched.add_months(date(2026, 3, 31), 1) == date(2026, 4, 30)
    assert sched.add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)


def test_intervals() -> None:
    base = date(2026, 5, 10)
    assert sched.add_interval(base, 10, "days") == date(2026, 5, 20)
    assert sched.add_interval(base, 2, "weeks") == date(2026, 5, 24)
    assert sched.add_interval(base, 1, "months") == date(2026, 6, 10)
    assert sched.add_interval(base, 1, "years") == date(2027, 5, 10)
    with pytest.raises(ValueError):
        sched.add_interval(base, 0, "days")


def _sched(**kw) -> sched.Schedule:
    base = dict(trigger_policy="DATE_ONLY", next_due_date=date(2026, 5, 20),
                next_due_meter=None, warning_days=7, warning_meter=None,
                latest_meter=None, status="Active", open_work_order=False)
    base.update(kw)
    return sched.Schedule(**base)


def test_date_states() -> None:
    today = date(2026, 5, 10)
    assert _sched().state(today) == sched.NOT_DUE
    assert _sched(next_due_date=date(2026, 5, 15)).state(today) == sched.DUE_SOON
    assert _sched(next_due_date=date(2026, 5, 10)).state(today) == sched.DUE
    assert _sched(next_due_date=date(2026, 5, 9)).state(today) == sched.OVERDUE
    assert _sched(status="Paused").state(today) == sched.PAUSED
    assert _sched(open_work_order=True).state(today) == sched.AWAITING


def test_meter_states() -> None:
    today = date(2026, 5, 10)
    meter = dict(trigger_policy="METER_ONLY", next_due_date=None,
                 next_due_meter=1000.0, warning_meter=100.0)
    assert _sched(**meter).state(today) == sched.NO_VALID_METER
    assert _sched(**meter, latest_meter=800.0).state(today) == sched.NOT_DUE
    assert _sched(**meter, latest_meter=920.0).state(today) == sched.DUE_SOON
    assert _sched(**meter, latest_meter=1000.0).state(today) == sched.DUE
    assert _sched(**meter, latest_meter=1005.0).state(today) == sched.OVERDUE


def test_first_due_takes_the_worst_condition() -> None:
    today = date(2026, 5, 10)
    hybrid = dict(trigger_policy="FIRST_DUE", next_due_date=date(2026, 12, 1),
                  next_due_meter=1000.0, warning_meter=100.0, latest_meter=1000.0)
    assert _sched(**hybrid).state(today) == sched.DUE
    hybrid["next_due_date"] = date(2026, 5, 1)
    hybrid["latest_meter"] = 500.0
    assert _sched(**hybrid).state(today) == sched.OVERDUE


def test_both_required_waits_for_both() -> None:
    today = date(2026, 5, 10)
    both = dict(trigger_policy="BOTH_REQUIRED", next_due_date=date(2026, 5, 10),
                next_due_meter=1000.0, warning_meter=100.0, latest_meter=1000.0)
    assert _sched(**both).state(today) == sched.DUE
    both["latest_meter"] = 500.0
    assert _sched(**both).state(today) == sched.NOT_DUE
    both["latest_meter"] = 1000.0
    both["next_due_date"] = date(2026, 5, 1)
    assert _sched(**both).state(today) == sched.OVERDUE


def test_advance_to_future_logs_missed_periods() -> None:
    nxt, skipped = sched.advance_to_future(date(2026, 1, 1), 30, "days", date(2026, 4, 1))
    assert skipped[0] == date(2026, 1, 1)
    assert nxt >= date(2026, 4, 1)
    assert all(nxt > s for s in skipped)


def test_latest_missed_keeps_the_most_recent_due_date():
    latest, skipped = sched.latest_missed(date(2026, 1, 1), 30, "days", date(2026, 4, 15))
    assert latest == date(2026, 4, 1)  # due 1 Jan, 31 Jan, 2 Mar, 1 Apr
    assert skipped == [date(2026, 1, 1), date(2026, 1, 31), date(2026, 3, 2)]
    assert sched.latest_missed(date(2026, 4, 10), 30, "days", date(2026, 4, 15)) == (
        date(2026, 4, 10), [])
