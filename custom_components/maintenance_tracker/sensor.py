"""Sensor platform for Maintenance Tracker."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import (
    ATTR_COUNT,
    ATTR_NOTE,
    ATTR_SERVICED_AT,
    SECONDS_PER_HOUR,
    SERVICE_ADD_CYCLES,
    SERVICE_MARK_SERVICED,
    SERVICE_SET_CYCLES,
    STATUSES,
    SUBENTRY_TYPE_TASK,
)
from .coordinator import MaintenanceConfigEntry, MaintenanceCoordinator
from .entity import MaintenanceEntity, MaintenanceTaskEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MaintenanceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the appliance and task sensors."""
    coordinator = config_entry.runtime_data

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_ADD_CYCLES,
        {vol.Optional(ATTR_COUNT, default=1): vol.Coerce(int)},
        "async_add_cycles",
    )
    platform.async_register_entity_service(
        SERVICE_SET_CYCLES,
        {vol.Required(ATTR_COUNT): vol.All(vol.Coerce(int), vol.Range(min=0))},
        "async_set_cycles",
    )
    platform.async_register_entity_service(
        SERVICE_MARK_SERVICED,
        {
            vol.Optional(ATTR_NOTE): cv.string,
            vol.Optional(ATTR_SERVICED_AT): cv.datetime,
        },
        "async_mark_serviced",
    )

    async_add_entities([CyclesSensor(coordinator), RuntimeSensor(coordinator)])

    for subentry_id, subentry in config_entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_TASK:
            continue
        async_add_entities(
            [
                TaskStatusSensor(coordinator, subentry_id),
                TaskProgressSensor(coordinator, subentry_id),
                TaskLastServiceSensor(coordinator, subentry_id),
            ],
            config_subentry_id=subentry_id,
        )


class CyclesSensor(MaintenanceEntity, SensorEntity):
    """Lifetime number of cycles run by the appliance."""

    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: MaintenanceCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "cycles")

    @property
    def native_value(self) -> int:
        """Return the cycle count."""
        return self.coordinator.data.appliance.cycles

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the in-flight cycle, useful for troubleshooting detection."""
        appliance = self.coordinator.data.appliance
        return {
            "cycle_in_progress": appliance.active_since is not None,
            "cycle_started_at": appliance.active_since,
        }

    async def async_add_cycles(self, count: int) -> None:
        """Handle the ``add_cycles`` service."""
        await self.coordinator.async_add_cycles(count)

    async def async_set_cycles(self, count: int) -> None:
        """Handle the ``set_cycles`` service."""
        await self.coordinator.async_set_cycles(count)


class RuntimeSensor(MaintenanceEntity, SensorEntity):
    """Lifetime running time of the appliance."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: MaintenanceCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "runtime")

    @property
    def native_value(self) -> float:
        """Return the cumulated runtime, in hours."""
        return round(self.coordinator.data.appliance.runtime / SECONDS_PER_HOUR, 3)


class TaskStatusSensor(MaintenanceTaskEntity, SensorEntity):
    """Whether a maintenance task is due, with all its details attached."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES

    def __init__(self, coordinator: MaintenanceCoordinator, subentry_id: str) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, subentry_id, "task_status")

    @property
    def native_value(self) -> str:
        """Return the task status."""
        return self.progress.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose everything the dashboard card needs in a single entity."""
        progress = self.progress
        return {
            "task": self.coordinator.task_title(self._subentry_id),
            "progress": round(min(progress.ratio, 1.0) * 100, 1),
            "cycles_since_service": progress.cycles_since,
            "cycles_limit": progress.limits.cycles,
            "cycles_remaining": progress.remaining_cycles,
            "hours_since_service": round(progress.hours_since, 1),
            "hours_limit": progress.limits.hours,
            "hours_remaining": progress.remaining_hours,
            "days_since_service": (
                round(progress.days_since, 1)
                if progress.days_since is not None
                else None
            ),
            "days_limit": progress.limits.days,
            "days_remaining": progress.remaining_days,
            "last_service": progress.last_service,
            "service_count": progress.service_count,
            "last_note": progress.last_note,
        }

    async def async_mark_serviced(
        self, note: str | None = None, serviced_at: datetime | None = None
    ) -> None:
        """Handle the ``mark_serviced`` service."""
        await self.coordinator.async_mark_serviced(
            self._subentry_id, note=note, serviced_at=serviced_at
        )


class TaskProgressSensor(MaintenanceTaskEntity, SensorEntity):
    """How far a task is towards its nearest limit, as a percentage."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:progress-wrench"

    def __init__(self, coordinator: MaintenanceCoordinator, subentry_id: str) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, subentry_id, "task_progress")

    @property
    def native_value(self) -> float:
        """Return the progress, capped at 100 %."""
        return round(min(self.progress.ratio, 1.0) * 100, 1)


class TaskLastServiceSensor(MaintenanceTaskEntity, SensorEntity):
    """When a task was last marked as serviced."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: MaintenanceCoordinator, subentry_id: str) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, subentry_id, "task_last_service")

    @property
    def native_value(self) -> StateType | datetime:
        """Return the last service timestamp."""
        return self.progress.last_service
