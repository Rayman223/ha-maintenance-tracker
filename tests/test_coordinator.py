"""Tests for counter bookkeeping and automatic cycle detection."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta

import pytest
from custom_components.maintenance_tracker.const import (
    EVENT_CYCLE_COMPLETED,
    EVENT_MAINTENANCE_COMPLETED,
    EVENT_MAINTENANCE_DUE,
    SECONDS_PER_HOUR,
    STATUS_OVERDUE,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)


async def _advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: int):
    """Move the clock forward and let scheduled callbacks run."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _coordinator(entry: MockConfigEntry):
    return entry.runtime_data


def _only_task(entry: MockConfigEntry) -> str:
    return next(iter(entry.subentries))


async def test_manual_increment(
    hass: HomeAssistant,
    manual_entry: MockConfigEntry,
    setup_integration: Callable[[MockConfigEntry], Awaitable[None]],
) -> None:
    """Pressing the button adds one cycle and moves the task forward."""
    await setup_integration(manual_entry)

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.washing_machine_register_a_cycle"},
        blocking=True,
    )

    assert _coordinator(manual_entry).data.appliance.cycles == 1
    assert hass.states.get("sensor.washing_machine_cycles").state == "1"


async def test_task_falls_due_and_is_serviced(
    hass: HomeAssistant,
    manual_entry: MockConfigEntry,
    setup_integration: Callable[[MockConfigEntry], Awaitable[None]],
) -> None:
    """Reaching the limit raises the alert; servicing clears it."""
    await setup_integration(manual_entry)
    coordinator = _coordinator(manual_entry)
    subentry_id = _only_task(manual_entry)

    due_events = []
    hass.bus.async_listen(EVENT_MAINTENANCE_DUE, due_events.append)
    done_events = []
    hass.bus.async_listen(EVENT_MAINTENANCE_COMPLETED, done_events.append)

    await coordinator.async_set_cycles(30)
    await hass.async_block_till_done()

    assert coordinator.data.progress[subentry_id].status == STATUS_OVERDUE
    assert (
        hass.states.get("binary_sensor.washing_machine_maintenance_required").state
        == "on"
    )
    assert len(due_events) == 1

    await coordinator.async_mark_serviced(subentry_id, note="Vinegar cycle")
    await hass.async_block_till_done()

    progress = coordinator.data.progress[subentry_id]
    assert progress.status != STATUS_OVERDUE
    assert progress.cycles_since == 0
    assert progress.service_count == 1
    assert progress.last_note == "Vinegar cycle"
    assert len(done_events) == 1


async def test_due_notification_is_raised_once(
    hass: HomeAssistant,
    manual_entry: MockConfigEntry,
    setup_integration: Callable[[MockConfigEntry], Awaitable[None]],
) -> None:
    """A task that stays overdue does not re-notify on every refresh."""
    await setup_integration(manual_entry)
    coordinator = _coordinator(manual_entry)

    events = []
    hass.bus.async_listen(EVENT_MAINTENANCE_DUE, events.append)

    await coordinator.async_set_cycles(30)
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(events) == 1


async def test_full_cycle_is_detected(
    hass: HomeAssistant,
    detecting_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    setup_integration: Callable[[MockConfigEntry], Awaitable[None]],
    source_entity: str,
) -> None:
    """A long run followed by the grace period counts exactly one cycle."""
    hass.states.async_set(source_entity, "0")
    await setup_integration(detecting_entry)
    coordinator = _coordinator(detecting_entry)

    events = []
    hass.bus.async_listen(EVENT_CYCLE_COMPLETED, events.append)

    hass.states.async_set(source_entity, "450")
    await hass.async_block_till_done()
    assert coordinator.data.appliance.active_since is not None

    await _advance(hass, freezer, 3600)

    hass.states.async_set(source_entity, "0")
    await hass.async_block_till_done()
    # Still within the grace period: the cycle is not closed yet.
    assert coordinator.data.appliance.cycles == 0

    await _advance(hass, freezer, 200)

    assert coordinator.data.appliance.cycles == 1
    assert coordinator.data.appliance.active_since is None
    assert coordinator.data.appliance.runtime == pytest.approx(3600, abs=90)
    assert len(events) == 1


async def test_short_burst_is_ignored(
    hass: HomeAssistant,
    detecting_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    setup_integration: Callable[[MockConfigEntry], Awaitable[None]],
    source_entity: str,
) -> None:
    """Standby draw below the minimum duration counts no cycle and no runtime."""
    hass.states.async_set(source_entity, "0")
    await setup_integration(detecting_entry)
    coordinator = _coordinator(detecting_entry)

    hass.states.async_set(source_entity, "50")
    await hass.async_block_till_done()
    await _advance(hass, freezer, 60)
    hass.states.async_set(source_entity, "0")
    await hass.async_block_till_done()
    await _advance(hass, freezer, 200)

    assert coordinator.data.appliance.cycles == 0
    # The runtime credited to the discarded burst is rolled back.
    assert coordinator.data.appliance.runtime == 0


async def test_pause_does_not_split_a_cycle(
    hass: HomeAssistant,
    detecting_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    setup_integration: Callable[[MockConfigEntry], Awaitable[None]],
    source_entity: str,
) -> None:
    """A dip below the threshold shorter than the grace period stays one cycle."""
    hass.states.async_set(source_entity, "0")
    await setup_integration(detecting_entry)
    coordinator = _coordinator(detecting_entry)

    hass.states.async_set(source_entity, "450")
    await hass.async_block_till_done()
    await _advance(hass, freezer, 1800)

    hass.states.async_set(source_entity, "2")  # soaking
    await hass.async_block_till_done()
    await _advance(hass, freezer, 60)
    hass.states.async_set(source_entity, "450")
    await hass.async_block_till_done()
    await _advance(hass, freezer, 1800)

    hass.states.async_set(source_entity, "0")
    await hass.async_block_till_done()
    await _advance(hass, freezer, 200)

    assert coordinator.data.appliance.cycles == 1
    # The 60 s pause is not credited as runtime.
    assert coordinator.data.appliance.runtime == pytest.approx(3600, abs=120)


async def test_unavailable_source_does_not_end_a_cycle(
    hass: HomeAssistant,
    detecting_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    setup_integration: Callable[[MockConfigEntry], Awaitable[None]],
    source_entity: str,
) -> None:
    """A flaky sensor going unavailable must not cut a running cycle short."""
    hass.states.async_set(source_entity, "0")
    await setup_integration(detecting_entry)
    coordinator = _coordinator(detecting_entry)

    hass.states.async_set(source_entity, "450")
    await hass.async_block_till_done()
    await _advance(hass, freezer, 600)

    hass.states.async_set(source_entity, "unavailable")
    await hass.async_block_till_done()
    await _advance(hass, freezer, 600)

    assert coordinator.data.appliance.active_since is not None
    assert coordinator.data.appliance.cycles == 0


async def test_counters_survive_a_reload(
    hass: HomeAssistant,
    manual_entry: MockConfigEntry,
    setup_integration: Callable[[MockConfigEntry], Awaitable[None]],
) -> None:
    """Counters and service history are restored from storage."""
    await setup_integration(manual_entry)
    coordinator = _coordinator(manual_entry)
    subentry_id = _only_task(manual_entry)

    await coordinator.async_set_cycles(17)
    await coordinator.async_add_runtime_hours(5)
    await coordinator.async_mark_serviced(subentry_id, note="done")
    await hass.async_block_till_done()

    await hass.config_entries.async_reload(manual_entry.entry_id)
    await hass.async_block_till_done()

    restored = _coordinator(manual_entry)
    assert restored.data.appliance.cycles == 17
    assert restored.data.appliance.runtime == pytest.approx(5 * SECONDS_PER_HOUR)
    assert restored.data.tasks[subentry_id].service_count == 1
    assert restored.data.tasks[subentry_id].last_note == "done"


async def test_removing_a_task_drops_its_state(
    hass: HomeAssistant,
    manual_entry: MockConfigEntry,
    setup_integration: Callable[[MockConfigEntry], Awaitable[None]],
) -> None:
    """Deleting a subentry removes its bookkeeping and its entities."""
    await setup_integration(manual_entry)
    subentry_id = _only_task(manual_entry)
    assert hass.states.get("sensor.washing_machine_clean_the_drum") is not None

    hass.config_entries.async_remove_subentry(manual_entry, subentry_id)
    await hass.async_block_till_done()

    assert subentry_id not in _coordinator(manual_entry).data.tasks
    assert hass.states.get("sensor.washing_machine_clean_the_drum") is None
