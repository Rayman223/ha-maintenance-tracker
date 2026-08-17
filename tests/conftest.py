"""Shared fixtures for the Maintenance Tracker tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Generator
from typing import Any

import pytest
from custom_components.maintenance_tracker.const import (
    CONF_DETECTION_MODE,
    CONF_IDLE_DEBOUNCE,
    CONF_LIMIT_CYCLES,
    CONF_MIN_ACTIVE_DURATION,
    CONF_POWER_THRESHOLD,
    CONF_SOURCE_ENTITY,
    CONF_WARN_RATIO,
    DETECTION_MODE_NONE,
    DETECTION_MODE_THRESHOLD,
    DOMAIN,
    SUBENTRY_TYPE_TASK,
)
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

SOURCE_ENTITY = "sensor.washer_power"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Make the custom integration loadable in every test."""
    return


@pytest.fixture
def source_entity() -> str:
    """Return the entity id used as a cycle detection source."""
    return SOURCE_ENTITY


@pytest.fixture
def setup_integration(
    hass: HomeAssistant,
) -> Callable[[MockConfigEntry], Awaitable[None]]:
    """Return a helper that adds and sets up a config entry."""

    async def _setup(entry: MockConfigEntry) -> None:
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return _setup


def task_subentry(title: str, **data: Any) -> ConfigSubentryData:
    """Build a maintenance task subentry."""
    return ConfigSubentryData(
        data={CONF_NAME: title, CONF_WARN_RATIO: 90, **data},
        subentry_type=SUBENTRY_TYPE_TASK,
        title=title,
        unique_id=None,
    )


@pytest.fixture
def manual_entry() -> MockConfigEntry:
    """Return an appliance counted by hand, with a single 30-cycle task."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Washing machine",
        data={CONF_NAME: "Washing machine", CONF_DETECTION_MODE: DETECTION_MODE_NONE},
        subentries_data=[task_subentry("Clean the drum", **{CONF_LIMIT_CYCLES: 30})],
    )


@pytest.fixture
def detecting_entry() -> MockConfigEntry:
    """Return an appliance whose cycles are detected from a power sensor."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Washing machine",
        data={
            CONF_NAME: "Washing machine",
            CONF_DETECTION_MODE: DETECTION_MODE_THRESHOLD,
            CONF_SOURCE_ENTITY: SOURCE_ENTITY,
            CONF_POWER_THRESHOLD: 10,
            CONF_MIN_ACTIVE_DURATION: 300,
            CONF_IDLE_DEBOUNCE: 180,
        },
        subentries_data=[task_subentry("Clean the drum", **{CONF_LIMIT_CYCLES: 30})],
    )
