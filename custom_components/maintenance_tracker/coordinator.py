"""Counter bookkeeping and automatic cycle detection."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ACTIVE_STATES,
    CONF_DETECTION_MODE,
    CONF_IDLE_DEBOUNCE,
    CONF_MIN_ACTIVE_DURATION,
    CONF_POWER_THRESHOLD,
    CONF_SOURCE_ENTITY,
    DEFAULT_IDLE_DEBOUNCE,
    DEFAULT_MIN_ACTIVE_DURATION,
    DEFAULT_POWER_THRESHOLD,
    DETECTION_MODE_NONE,
    DETECTION_MODE_STATE,
    DETECTION_MODE_THRESHOLD,
    DOMAIN,
    EVENT_CYCLE_COMPLETED,
    EVENT_MAINTENANCE_COMPLETED,
    EVENT_MAINTENANCE_DUE,
    RECOMPUTE_INTERVAL_MINUTES,
    RUNTIME_TICK_SECONDS,
    SECONDS_PER_HOUR,
    STATUS_OVERDUE,
    STORAGE_VERSION,
    SUBENTRY_TYPE_TASK,
)
from .models import (
    ApplianceState,
    MaintenanceData,
    TaskLimits,
    TaskState,
    compute_progress,
)

_LOGGER = logging.getLogger(__name__)

type MaintenanceConfigEntry = ConfigEntry[MaintenanceCoordinator]

_IGNORED_STATES = {STATE_UNAVAILABLE, STATE_UNKNOWN, None}

#: Delay before the debounced write of counters to disk.
_SAVE_DELAY = 10


class MaintenanceCoordinator(DataUpdateCoordinator[MaintenanceData]):
    """Own the appliance counters and keep every task's progress up to date.

    The coordinator is the single writer of the persisted state. Entities and
    services never mutate counters themselves; they call the ``async_*`` methods
    here, which update, persist, recompute and notify in one place.
    """

    config_entry: MaintenanceConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: MaintenanceConfigEntry
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=config_entry.title,
            # Calendar-based tasks must be able to fall due on their own, with
            # no state change anywhere to trigger a refresh.
            update_interval=timedelta(minutes=RECOMPUTE_INTERVAL_MINUTES),
        )
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{DOMAIN}.{config_entry.entry_id}"
        )
        self._state = MaintenanceData()
        self._cancel_tick: CALLBACK_TYPE | None = None
        self._cancel_idle: CALLBACK_TYPE | None = None

    # -- Configuration shortcuts ---------------------------------------------

    @property
    def _options(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def detection_mode(self) -> str:
        """Return the configured automatic cycle detection mode."""
        return self._options.get(CONF_DETECTION_MODE, DETECTION_MODE_NONE)

    @property
    def source_entity_id(self) -> str | None:
        """Return the entity cycles are detected from, if any."""
        if self.detection_mode == DETECTION_MODE_NONE:
            return None
        return self._options.get(CONF_SOURCE_ENTITY)

    @property
    def _min_active_duration(self) -> float:
        return float(
            self._options.get(CONF_MIN_ACTIVE_DURATION, DEFAULT_MIN_ACTIVE_DURATION)
        )

    @property
    def _idle_debounce(self) -> float:
        return float(self._options.get(CONF_IDLE_DEBOUNCE, DEFAULT_IDLE_DEBOUNCE))

    def task_limits(self, subentry_id: str) -> TaskLimits:
        """Return the limits configured for a task."""
        subentry = self.config_entry.subentries[subentry_id]
        return TaskLimits.from_subentry(dict(subentry.data))

    def task_title(self, subentry_id: str) -> str:
        """Return a task's user-facing name."""
        return self.config_entry.subentries[subentry_id].title

    # -- Setup / teardown ----------------------------------------------------

    async def async_setup(self) -> None:
        """Load persisted state, reconcile tasks and start cycle detection."""
        stored = await self._store.async_load() or {}
        self._state = MaintenanceData(
            appliance=ApplianceState.from_dict(stored.get("appliance", {})),
            tasks={
                subentry_id: TaskState.from_dict(data)
                for subentry_id, data in stored.get("tasks", {}).items()
            },
        )
        self._reconcile_tasks()
        await self._async_restore_in_flight_cycle()
        self._async_start_detection()

    def _reconcile_tasks(self) -> None:
        """Create state for new tasks and drop state for deleted ones."""
        now = dt_util.utcnow()
        configured = {
            subentry_id
            for subentry_id, subentry in self.config_entry.subentries.items()
            if subentry.subentry_type == SUBENTRY_TYPE_TASK
        }

        for subentry_id in configured - self._state.tasks.keys():
            # A brand new task starts its clock now, at the current totals.
            self._state.tasks[subentry_id] = TaskState(
                baseline_cycles=self._state.appliance.cycles,
                baseline_runtime=self._state.appliance.runtime,
                last_service=now,
            )

        for subentry_id in self._state.tasks.keys() - configured:
            del self._state.tasks[subentry_id]

    def _async_start_detection(self) -> None:
        """Subscribe to the source entity, when automatic detection is on."""
        source = self.source_entity_id
        if not source:
            return

        self.config_entry.async_on_unload(
            async_track_state_change_event(
                self.hass, [source], self._async_source_changed
            )
        )
        self.config_entry.async_on_unload(self._async_stop_timers)

    def _async_stop_timers(self) -> None:
        """Cancel the runtime tick and the idle debounce."""
        if self._cancel_tick is not None:
            self._cancel_tick()
            self._cancel_tick = None
        if self._cancel_idle is not None:
            self._cancel_idle()
            self._cancel_idle = None

    async def async_shutdown(self) -> None:
        """Flush counters to disk before going away."""
        self._async_stop_timers()
        await self._async_save(immediate=True)
        await super().async_shutdown()

    # -- Persistence ---------------------------------------------------------

    def _as_stored(self) -> dict[str, Any]:
        return {
            "appliance": self._state.appliance.as_dict(),
            "tasks": {
                subentry_id: task.as_dict()
                for subentry_id, task in self._state.tasks.items()
            },
        }

    async def _async_save(self, *, immediate: bool = False) -> None:
        """Persist counters, debounced unless the write must not be lost."""
        if immediate:
            await self._store.async_save(self._as_stored())
        else:
            self._store.async_delay_save(self._as_stored, _SAVE_DELAY)

    async def async_remove_storage(self) -> None:
        """Delete persisted counters, when the appliance is removed."""
        await self._store.async_remove()

    # -- Refresh -------------------------------------------------------------

    async def _async_update_data(self) -> MaintenanceData:
        """Recompute every task's progress and raise due notifications."""
        now = dt_util.utcnow()
        self._state.progress = {
            subentry_id: compute_progress(
                self._state.appliance, task, self.task_limits(subentry_id), now
            )
            for subentry_id, task in self._state.tasks.items()
            if subentry_id in self.config_entry.subentries
        }
        if self._async_handle_due_tasks():
            # Remember that the alert was raised, so a restart does not repeat it.
            await self._async_save()
        return self._state

    def _async_handle_due_tasks(self) -> bool:
        """Fire events and notifications on entering the overdue state.

        Returns whether any alert flag changed, and therefore needs persisting.
        """
        changed = False
        for subentry_id, progress in self._state.progress.items():
            task = self._state.tasks[subentry_id]
            if progress.status == STATUS_OVERDUE and not task.notified:
                task.notified = True
                changed = True
                self._async_notify_due(subentry_id, progress.ratio)
            elif progress.status != STATUS_OVERDUE and task.notified:
                # Raising the limit clears the alert without a service entry.
                task.notified = False
                changed = True
        return changed

    def _async_notify_due(self, subentry_id: str, ratio: float) -> None:
        """Announce that a task has reached its limit."""
        title = self.task_title(subentry_id)
        self.hass.bus.async_fire(
            EVENT_MAINTENANCE_DUE,
            {
                "entry_id": self.config_entry.entry_id,
                "appliance": self.config_entry.title,
                "subentry_id": subentry_id,
                "task": title,
                "ratio": round(ratio, 3),
            },
        )

        if not self.task_limits(subentry_id).notify:
            return

        persistent_notification.async_create(
            self.hass,
            title=f"{self.config_entry.title} — {title}",
            message=(
                f"Maintenance is due: **{title}** on **{self.config_entry.title}**.\n\n"
                "Mark it as serviced once done to reset the counters."
            ),
            notification_id=f"{DOMAIN}_{subentry_id}",
        )

    def _async_dismiss_notification(self, subentry_id: str) -> None:
        """Clear the notification raised for a task, if any."""
        persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_{subentry_id}")

    # -- Public actions ------------------------------------------------------

    async def async_add_cycles(self, count: int = 1) -> None:
        """Add (or subtract) cycles to the appliance counter."""
        await self.async_set_cycles(self._state.appliance.cycles + count)

    async def async_set_cycles(self, count: int) -> None:
        """Set the lifetime cycle counter to an absolute value."""
        self._state.appliance.cycles = max(count, 0)
        await self._async_commit()

    async def async_add_runtime_hours(self, hours: float) -> None:
        """Add (or subtract) runtime to the appliance counter."""
        appliance = self._state.appliance
        appliance.runtime = max(appliance.runtime + hours * SECONDS_PER_HOUR, 0.0)
        await self._async_commit()

    async def async_mark_serviced(
        self,
        subentry_id: str,
        *,
        note: str | None = None,
        serviced_at: datetime | None = None,
    ) -> None:
        """Record a task as serviced: rebase its counters and clear the alert."""
        task = self._state.tasks.get(subentry_id)
        if task is None:
            return

        task.baseline_cycles = self._state.appliance.cycles
        task.baseline_runtime = self._state.appliance.runtime
        # `serviced_at` arrives from a service call as a naive datetime; treat
        # it as local time, which is what the user typed.
        task.last_service = (
            dt_util.as_utc(serviced_at) if serviced_at else dt_util.utcnow()
        )
        task.service_count += 1
        task.last_note = note
        task.notified = False

        self._async_dismiss_notification(subentry_id)
        self.hass.bus.async_fire(
            EVENT_MAINTENANCE_COMPLETED,
            {
                "entry_id": self.config_entry.entry_id,
                "appliance": self.config_entry.title,
                "subentry_id": subentry_id,
                "task": self.task_title(subentry_id),
                "service_count": task.service_count,
                "note": note,
            },
        )
        await self._async_commit()

    async def _async_commit(self) -> None:
        """Persist and publish the new state to the entities."""
        await self._async_save()
        await self.async_refresh()

    # -- Cycle detection -----------------------------------------------------

    def _is_active(self, state: Any) -> bool | None:
        """Return whether the source reads as running.

        ``None`` means "no usable reading": unavailable sources are ignored
        rather than treated as idle, so a flaky sensor cannot cut a cycle short.
        """
        if state is None or state.state in _IGNORED_STATES:
            return None

        if self.detection_mode == DETECTION_MODE_STATE:
            active_states = self._options.get(CONF_ACTIVE_STATES) or []
            return state.state in active_states

        if self.detection_mode == DETECTION_MODE_THRESHOLD:
            try:
                value = float(state.state)
            except (TypeError, ValueError):
                return None
            threshold = float(
                self._options.get(CONF_POWER_THRESHOLD, DEFAULT_POWER_THRESHOLD)
            )
            return value > threshold

        return None

    async def _async_restore_in_flight_cycle(self) -> None:
        """Resume or close a cycle that was running when Home Assistant stopped."""
        appliance = self._state.appliance
        if appliance.active_since is None:
            return

        source = self.source_entity_id
        if source is None:
            # Detection was turned off mid-cycle; drop the in-flight state.
            self._discard_cycle()
            return

        if self._is_active(self.hass.states.get(source)):
            # Still running. The downtime itself is not credited as runtime,
            # since there is no way to know the appliance stayed on.
            appliance.last_tick = dt_util.utcnow()
            self._async_schedule_tick()
            return

        # It stopped while we were down: close it at the last accounted instant.
        await self._async_finish_cycle(ended_at=appliance.last_tick)

    async def _async_source_changed(self, event: Event[EventStateChangedData]) -> None:
        """React to the source entity, driving the cycle state machine."""
        active = self._is_active(event.data["new_state"])
        if active is None:
            return

        if active:
            await self._async_on_active()
        else:
            await self._async_on_inactive()

    async def _async_on_active(self) -> None:
        """Start a cycle, or cancel a pending end of cycle."""
        if self._cancel_idle is not None:
            # The appliance dipped below the threshold and came back: same cycle.
            self._cancel_idle()
            self._cancel_idle = None

        appliance = self._state.appliance
        if appliance.active_since is None:
            now = dt_util.utcnow()
            appliance.active_since = now
            appliance.last_tick = now
            appliance.cycle_runtime = 0.0
            _LOGGER.debug("%s: cycle started", self.config_entry.title)

        self._async_schedule_tick()

    async def _async_on_inactive(self) -> None:
        """Account the runtime so far and arm the end-of-cycle debounce."""
        if self._state.appliance.active_since is None or self._cancel_idle is not None:
            return

        self._async_accumulate_runtime()
        if self._cancel_tick is not None:
            self._cancel_tick()
            self._cancel_tick = None

        self._cancel_idle = async_call_later(
            self.hass, self._idle_debounce, self._async_idle_elapsed
        )

    async def _async_idle_elapsed(self, _now: datetime) -> None:
        """Close the cycle: the source stayed idle for the whole debounce."""
        self._cancel_idle = None
        await self._async_finish_cycle(ended_at=self._state.appliance.last_tick)

    def _async_schedule_tick(self) -> None:
        """Flush runtime regularly, so a crash costs at most one interval."""
        if self._cancel_tick is not None:
            return
        self._cancel_tick = async_track_time_interval(
            self.hass, self._async_tick, timedelta(seconds=RUNTIME_TICK_SECONDS)
        )

    async def _async_tick(self, _now: datetime) -> None:
        """Credit the runtime elapsed since the previous tick."""
        self._async_accumulate_runtime()
        await self._async_commit()

    def _async_accumulate_runtime(self) -> None:
        """Move the wall clock elapsed since ``last_tick`` into the counters."""
        appliance = self._state.appliance
        if appliance.active_since is None or appliance.last_tick is None:
            return

        now = dt_util.utcnow()
        elapsed = (now - appliance.last_tick).total_seconds()
        appliance.last_tick = now
        if elapsed <= 0:
            return

        appliance.runtime += elapsed
        appliance.cycle_runtime += elapsed

    def _discard_cycle(self) -> None:
        """Roll back an in-flight cycle without counting it."""
        appliance = self._state.appliance
        appliance.runtime = max(appliance.runtime - appliance.cycle_runtime, 0.0)
        self._clear_cycle()

    def _clear_cycle(self) -> None:
        """Reset the in-flight cycle bookkeeping."""
        appliance = self._state.appliance
        appliance.active_since = None
        appliance.last_tick = None
        appliance.cycle_runtime = 0.0

    async def _async_finish_cycle(self, *, ended_at: datetime | None) -> None:
        """Count or discard the cycle that just ended."""
        self._async_stop_timers()

        appliance = self._state.appliance
        started_at = appliance.active_since
        if started_at is None:
            return

        ended_at = ended_at or dt_util.utcnow()
        duration = (ended_at - started_at).total_seconds()

        if duration < self._min_active_duration:
            _LOGGER.debug(
                "%s: ignoring %.0f s of activity, below the %.0f s minimum",
                self.config_entry.title,
                duration,
                self._min_active_duration,
            )
            self._discard_cycle()
            await self._async_commit()
            return

        appliance.cycles += 1
        cycle_runtime = appliance.cycle_runtime
        self._clear_cycle()

        _LOGGER.debug(
            "%s: cycle #%d completed after %.0f s",
            self.config_entry.title,
            appliance.cycles,
            duration,
        )
        self.hass.bus.async_fire(
            EVENT_CYCLE_COMPLETED,
            {
                "entry_id": self.config_entry.entry_id,
                "appliance": self.config_entry.title,
                "cycles": appliance.cycles,
                "duration": round(cycle_runtime, 1),
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
            },
        )
        await self._async_commit()
