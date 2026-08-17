"""Unit tests for the progress computation."""

from __future__ import annotations

from datetime import timedelta

import pytest
from custom_components.maintenance_tracker.const import (
    CONF_LIMIT_CYCLES,
    CONF_LIMIT_DAYS,
    CONF_LIMIT_HOURS,
    CONF_WARN_RATIO,
    SECONDS_PER_HOUR,
    STATUS_DUE_SOON,
    STATUS_OK,
    STATUS_OVERDUE,
)
from custom_components.maintenance_tracker.models import (
    ApplianceState,
    TaskLimits,
    TaskState,
    compute_progress,
)
from homeassistant.util import dt as dt_util

NOW = dt_util.utcnow()


def _progress(appliance: ApplianceState, task: TaskState, **limits_data):
    limits = TaskLimits.from_subentry({CONF_WARN_RATIO: 90, **limits_data})
    return compute_progress(appliance, task, limits, NOW)


@pytest.mark.parametrize(
    ("cycles", "expected"),
    [(0, STATUS_OK), (26, STATUS_OK), (27, STATUS_DUE_SOON), (30, STATUS_OVERDUE)],
)
def test_cycle_limit_thresholds(cycles: int, expected: str) -> None:
    """The 90 % warning and the limit itself land on the right cycle."""
    progress = _progress(
        ApplianceState(cycles=cycles), TaskState(), **{CONF_LIMIT_CYCLES: 30}
    )
    assert progress.status == expected


def test_progress_counts_from_the_baseline() -> None:
    """A serviced task measures from the totals it was last serviced at."""
    progress = _progress(
        ApplianceState(cycles=100),
        TaskState(baseline_cycles=90),
        **{CONF_LIMIT_CYCLES: 30},
    )
    assert progress.cycles_since == 10
    assert progress.remaining_cycles == 20
    assert progress.status == STATUS_OK


def test_nearest_limit_wins() -> None:
    """The task is driven by whichever limit is closest to being reached."""
    progress = _progress(
        ApplianceState(cycles=3, runtime=95 * SECONDS_PER_HOUR),
        TaskState(last_service=NOW - timedelta(days=1)),
        **{CONF_LIMIT_CYCLES: 100, CONF_LIMIT_HOURS: 100, CONF_LIMIT_DAYS: 365},
    )
    assert progress.status == STATUS_DUE_SOON
    assert progress.ratio == pytest.approx(0.95)


def test_calendar_limit_alone() -> None:
    """A task can fall due purely on elapsed days."""
    progress = _progress(
        ApplianceState(),
        TaskState(last_service=NOW - timedelta(days=200)),
        **{CONF_LIMIT_DAYS: 180},
    )
    assert progress.status == STATUS_OVERDUE
    assert progress.remaining_days == pytest.approx(-20, abs=0.1)


def test_task_without_limits_never_falls_due() -> None:
    """A task with no threshold stays OK, and reports a zero ratio."""
    progress = _progress(ApplianceState(cycles=10_000), TaskState())
    assert progress.status == STATUS_OK
    assert progress.ratio == 0
    assert progress.remaining_cycles is None


def test_zero_limits_are_treated_as_unset() -> None:
    """The config flow writes 0 for "not tracked"; it must not divide by zero."""
    limits = TaskLimits.from_subentry(
        {CONF_LIMIT_CYCLES: 0, CONF_LIMIT_HOURS: 0.0, CONF_LIMIT_DAYS: 0}
    )
    assert limits.is_empty
    assert limits.cycles is None


def test_counters_never_go_negative() -> None:
    """Lowering the totals below a baseline must not produce negative progress."""
    progress = _progress(
        ApplianceState(cycles=5, runtime=0),
        TaskState(baseline_cycles=50, baseline_runtime=10 * SECONDS_PER_HOUR),
        **{CONF_LIMIT_CYCLES: 30},
    )
    assert progress.cycles_since == 0
    assert progress.hours_since == 0


def test_round_trip_through_storage() -> None:
    """State survives serialisation without losing precision or timestamps."""
    original = ApplianceState(
        cycles=42, runtime=1234.5, active_since=NOW, last_tick=NOW, cycle_runtime=60.0
    )
    assert ApplianceState.from_dict(original.as_dict()) == original

    task = TaskState(
        baseline_cycles=10,
        baseline_runtime=99.5,
        last_service=NOW,
        service_count=3,
        last_note="filter",
        notified=True,
    )
    assert TaskState.from_dict(task.as_dict()) == task
