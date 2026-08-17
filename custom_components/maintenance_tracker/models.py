"""Data model for the Maintenance Tracker integration.

Counters are stored once per appliance, as lifetime totals, and every
maintenance task records the totals it was last serviced at. A task's progress
is then always ``total - baseline``, which keeps a single writer per counter and
makes "mark as serviced" a baseline update rather than a destructive reset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Self

from homeassistant.util import dt as dt_util

from .const import (
    CONF_LIMIT_CYCLES,
    CONF_LIMIT_DAYS,
    CONF_LIMIT_HOURS,
    CONF_NOTIFY,
    CONF_WARN_RATIO,
    DEFAULT_NOTIFY,
    DEFAULT_WARN_RATIO,
    SECONDS_PER_HOUR,
    STATUS_DUE_SOON,
    STATUS_OK,
    STATUS_OVERDUE,
)


def _parse_dt(value: Any) -> datetime | None:
    """Parse a stored ISO timestamp, tolerating missing or corrupt values."""
    if not value:
        return None
    return dt_util.parse_datetime(value)


def _dump_dt(value: datetime | None) -> str | None:
    """Serialise a timestamp for storage."""
    return value.isoformat() if value else None


@dataclass
class ApplianceState:
    """Persisted lifetime counters and in-flight cycle bookkeeping."""

    cycles: int = 0
    runtime: float = 0.0
    """Cumulated runtime, in seconds."""

    active_since: datetime | None = None
    """Start of the cycle currently in progress, if any."""

    last_tick: datetime | None = None
    """Last instant runtime was accounted for; end of cycle on restart."""

    cycle_runtime: float = 0.0
    """Runtime credited to the in-flight cycle, rolled back if it is discarded."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Restore from storage."""
        return cls(
            cycles=int(data.get("cycles", 0)),
            runtime=float(data.get("runtime", 0.0)),
            active_since=_parse_dt(data.get("active_since")),
            last_tick=_parse_dt(data.get("last_tick")),
            cycle_runtime=float(data.get("cycle_runtime", 0.0)),
        )

    def as_dict(self) -> dict[str, Any]:
        """Serialise for storage."""
        return {
            "cycles": self.cycles,
            "runtime": self.runtime,
            "active_since": _dump_dt(self.active_since),
            "last_tick": _dump_dt(self.last_tick),
            "cycle_runtime": self.cycle_runtime,
        }


@dataclass
class TaskState:
    """Persisted per-task bookkeeping, keyed by subentry id."""

    baseline_cycles: int = 0
    baseline_runtime: float = 0.0
    last_service: datetime | None = None
    service_count: int = 0
    last_note: str | None = None
    notified: bool = False
    """Whether the current overdue period already produced a notification."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Restore from storage."""
        return cls(
            baseline_cycles=int(data.get("baseline_cycles", 0)),
            baseline_runtime=float(data.get("baseline_runtime", 0.0)),
            last_service=_parse_dt(data.get("last_service")),
            service_count=int(data.get("service_count", 0)),
            last_note=data.get("last_note"),
            notified=bool(data.get("notified", False)),
        )

    def as_dict(self) -> dict[str, Any]:
        """Serialise for storage."""
        return {
            "baseline_cycles": self.baseline_cycles,
            "baseline_runtime": self.baseline_runtime,
            "last_service": _dump_dt(self.last_service),
            "service_count": self.service_count,
            "last_note": self.last_note,
            "notified": self.notified,
        }


@dataclass(frozen=True, slots=True)
class TaskLimits:
    """The thresholds configured for a task, as read from its subentry."""

    cycles: int | None = None
    hours: float | None = None
    days: int | None = None
    warn_ratio: float = DEFAULT_WARN_RATIO / 100
    notify: bool = DEFAULT_NOTIFY

    @classmethod
    def from_subentry(cls, data: dict[str, Any]) -> Self:
        """Build limits from stored subentry data.

        A limit that is absent, ``None`` or ``0`` means "not tracked", which is
        how the config flow represents an omitted field.
        """
        cycles = data.get(CONF_LIMIT_CYCLES)
        hours = data.get(CONF_LIMIT_HOURS)
        days = data.get(CONF_LIMIT_DAYS)
        return cls(
            cycles=int(cycles) if cycles else None,
            hours=float(hours) if hours else None,
            days=int(days) if days else None,
            warn_ratio=float(data.get(CONF_WARN_RATIO, DEFAULT_WARN_RATIO)) / 100,
            notify=bool(data.get(CONF_NOTIFY, DEFAULT_NOTIFY)),
        )

    @property
    def is_empty(self) -> bool:
        """Return True when no threshold at all is configured."""
        return self.cycles is None and self.hours is None and self.days is None


@dataclass(frozen=True, slots=True)
class TaskProgress:
    """Computed view of a task, refreshed by the coordinator."""

    status: str
    ratio: float
    """Progress towards the nearest limit, 0.0 to 1.0+ (unclamped past 1.0)."""

    cycles_since: int
    hours_since: float
    days_since: float | None
    limits: TaskLimits
    last_service: datetime | None
    service_count: int
    last_note: str | None

    @property
    def is_overdue(self) -> bool:
        """Return True when at least one limit has been reached."""
        return self.status == STATUS_OVERDUE

    @property
    def remaining_cycles(self) -> int | None:
        """Cycles left before the limit, negative once exceeded."""
        if self.limits.cycles is None:
            return None
        return self.limits.cycles - self.cycles_since

    @property
    def remaining_hours(self) -> float | None:
        """Runtime hours left before the limit, negative once exceeded."""
        if self.limits.hours is None:
            return None
        return round(self.limits.hours - self.hours_since, 2)

    @property
    def remaining_days(self) -> float | None:
        """Days left before the limit, negative once exceeded."""
        if self.limits.days is None or self.days_since is None:
            return None
        return round(self.limits.days - self.days_since, 1)


def compute_progress(
    appliance: ApplianceState,
    task: TaskState,
    limits: TaskLimits,
    now: datetime,
) -> TaskProgress:
    """Derive a task's progress and status from the appliance counters."""
    cycles_since = max(appliance.cycles - task.baseline_cycles, 0)
    hours_since = max(appliance.runtime - task.baseline_runtime, 0.0) / SECONDS_PER_HOUR

    days_since: float | None = None
    if task.last_service is not None:
        days_since = max((now - task.last_service).total_seconds(), 0.0) / 86400

    ratios: list[float] = []
    if limits.cycles:
        ratios.append(cycles_since / limits.cycles)
    if limits.hours:
        ratios.append(hours_since / limits.hours)
    if limits.days and days_since is not None:
        ratios.append(days_since / limits.days)

    # The task is driven by whichever limit is closest to being reached.
    ratio = max(ratios) if ratios else 0.0

    if ratio >= 1:
        status = STATUS_OVERDUE
    elif ratios and ratio >= limits.warn_ratio:
        status = STATUS_DUE_SOON
    else:
        status = STATUS_OK

    return TaskProgress(
        status=status,
        ratio=ratio,
        cycles_since=cycles_since,
        hours_since=round(hours_since, 3),
        days_since=round(days_since, 3) if days_since is not None else None,
        limits=limits,
        last_service=task.last_service,
        service_count=task.service_count,
        last_note=task.last_note,
    )


@dataclass
class MaintenanceData:
    """Everything the entities need, rebuilt on every coordinator refresh."""

    appliance: ApplianceState = field(default_factory=ApplianceState)
    tasks: dict[str, TaskState] = field(default_factory=dict)
    progress: dict[str, TaskProgress] = field(default_factory=dict)
