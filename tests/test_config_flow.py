"""Tests for the config, options and subentry flows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from custom_components.maintenance_tracker.const import (
    CONF_DETECTION_MODE,
    CONF_IDLE_DEBOUNCE,
    CONF_LIMIT_CYCLES,
    CONF_LIMIT_DAYS,
    CONF_LIMIT_HOURS,
    CONF_MIN_ACTIVE_DURATION,
    CONF_POWER_THRESHOLD,
    CONF_SOURCE_ENTITY,
    CONF_WARN_RATIO,
    DETECTION_MODE_NONE,
    DETECTION_MODE_THRESHOLD,
    DOMAIN,
    SUBENTRY_TYPE_TASK,
)
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_manual_appliance_flow(hass: HomeAssistant) -> None:
    """Creating a manually counted appliance takes a single step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Coffee maker", CONF_DETECTION_MODE: DETECTION_MODE_NONE},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Coffee maker"
    assert result["data"][CONF_DETECTION_MODE] == DETECTION_MODE_NONE


async def test_detection_flow_asks_for_the_source(
    hass: HomeAssistant,
    source_entity: str,
) -> None:
    """Picking automatic detection adds a second step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Washing machine", CONF_DETECTION_MODE: DETECTION_MODE_THRESHOLD},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "detection"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SOURCE_ENTITY: source_entity,
            CONF_POWER_THRESHOLD: 12,
            CONF_MIN_ACTIVE_DURATION: 300,
            CONF_IDLE_DEBOUNCE: 180,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SOURCE_ENTITY] == source_entity
    assert result["data"][CONF_POWER_THRESHOLD] == 12


async def test_duplicate_appliance_is_rejected(
    hass: HomeAssistant, manual_entry: MockConfigEntry
) -> None:
    """Two appliances cannot share a name."""
    manual_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Washing machine", CONF_DETECTION_MODE: DETECTION_MODE_NONE},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_add_task_subentry(
    hass: HomeAssistant,
    manual_entry: MockConfigEntry,
    setup_integration: Callable[[MockConfigEntry], Awaitable[None]],
) -> None:
    """A task can be added to an existing appliance."""
    await setup_integration(manual_entry)
    registry = er.async_get(hass)
    original_entities = er.async_entries_for_config_entry(
        registry, manual_entry.entry_id
    )
    device_ids = {entity.device_id for entity in original_entities}
    assert len(device_ids) == 1
    assert None not in device_ids

    result = await hass.config_entries.subentries.async_init(
        (manual_entry.entry_id, SUBENTRY_TYPE_TASK),
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Descale",
            CONF_LIMIT_CYCLES: 0,
            CONF_LIMIT_HOURS: 0,
            CONF_LIMIT_DAYS: 180,
            CONF_WARN_RATIO: 90,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(manual_entry.subentries) == 2
    assert hass.states.get("sensor.washing_machine_descale") is not None
    assert all(hass.states.get(entity.entity_id) for entity in original_entities)
    assert {
        entity.device_id
        for entity in er.async_entries_for_config_entry(registry, manual_entry.entry_id)
    } == device_ids

    added_subentry_id = next(
        subentry_id
        for subentry_id, subentry in manual_entry.subentries.items()
        if subentry.title == "Descale"
    )
    added_entities = [
        entity
        for entity in er.async_entries_for_config_entry(registry, manual_entry.entry_id)
        if entity.config_subentry_id == added_subentry_id
    ]
    assert len(added_entities) == 5

    hass.config_entries.async_remove_subentry(manual_entry, added_subentry_id)
    await hass.async_block_till_done()

    assert all(hass.states.get(entity.entity_id) for entity in original_entities)
    assert all(
        registry.async_get(entity.entity_id) is None for entity in added_entities
    )
    assert all(hass.states.get(entity.entity_id) is None for entity in added_entities)


async def test_existing_device_is_kept_on_the_appliance(
    hass: HomeAssistant,
    manual_entry: MockConfigEntry,
) -> None:
    """Recover an appliance whose shared device was assigned to a task."""
    manual_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=manual_entry.entry_id,
        config_subentry_id=next(iter(manual_entry.subentries)),
        identifiers={(DOMAIN, manual_entry.entry_id)},
        name=manual_entry.title,
    )
    registry = er.async_get(hass)
    button = registry.async_get_or_create(
        "button",
        DOMAIN,
        f"{manual_entry.entry_id}_register_cycle",
        config_entry=manual_entry,
        device_id=device.id,
        suggested_object_id="my_washer_cycle",
    )
    await hass.async_block_till_done()

    assert await hass.config_entries.async_setup(manual_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(button.entity_id) is not None
    assert hass.states.get("sensor.washing_machine_clean_the_drum") is not None
    assert {
        entity.device_id
        for entity in er.async_entries_for_config_entry(registry, manual_entry.entry_id)
    } == {device.id}


async def test_task_without_any_limit_is_rejected(
    hass: HomeAssistant,
    manual_entry: MockConfigEntry,
    setup_integration: Callable[[MockConfigEntry], Awaitable[None]],
) -> None:
    """A task with every limit left at zero could never fall due."""
    await setup_integration(manual_entry)

    result = await hass.config_entries.subentries.async_init(
        (manual_entry.entry_id, SUBENTRY_TYPE_TASK),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Nothing",
            CONF_LIMIT_CYCLES: 0,
            CONF_LIMIT_HOURS: 0,
            CONF_LIMIT_DAYS: 0,
            CONF_WARN_RATIO: 90,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_limit"}


async def test_options_flow_turns_detection_off(
    hass: HomeAssistant,
    detecting_entry: MockConfigEntry,
    setup_integration: Callable[[MockConfigEntry], Awaitable[None]],
) -> None:
    """Switching back to manual clears the stale detection settings."""
    await setup_integration(detecting_entry)

    result = await hass.config_entries.options.async_init(detecting_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_DETECTION_MODE: DETECTION_MODE_NONE}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert detecting_entry.options == {CONF_DETECTION_MODE: DETECTION_MODE_NONE}
    assert detecting_entry.runtime_data.source_entity_id is None
