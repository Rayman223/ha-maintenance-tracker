"""Binary sensor platform for Maintenance Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DETECTION_MODE_NONE, STATUS_OVERDUE, SUBENTRY_TYPE_TASK
from .coordinator import MaintenanceConfigEntry, MaintenanceCoordinator
from .entity import MaintenanceEntity, MaintenanceTaskEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MaintenanceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the appliance and task binary sensors."""
    coordinator = config_entry.runtime_data

    entities: list[MaintenanceEntity] = [MaintenanceRequiredBinarySensor(coordinator)]
    if coordinator.detection_mode != DETECTION_MODE_NONE:
        entities.append(CycleRunningBinarySensor(coordinator))
    async_add_entities(entities)

    for subentry_id, subentry in config_entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_TASK:
            continue
        async_add_entities(
            [TaskDueBinarySensor(coordinator, subentry_id)],
            config_subentry_id=subentry_id,
        )


class MaintenanceRequiredBinarySensor(MaintenanceEntity, BinarySensorEntity):
    """On as soon as any task of the appliance has reached its limit."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: MaintenanceCoordinator) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, "maintenance_required")

    @property
    def is_on(self) -> bool:
        """Return whether at least one task is overdue."""
        return any(
            progress.is_overdue for progress in self.coordinator.data.progress.values()
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """List the tasks that are due, so a single card can summarise them."""
        data = self.coordinator.data
        return {
            "overdue_tasks": [
                self.coordinator.task_title(subentry_id)
                for subentry_id, progress in data.progress.items()
                if progress.status == STATUS_OVERDUE
            ],
            "task_count": len(data.progress),
        }


class CycleRunningBinarySensor(MaintenanceEntity, BinarySensorEntity):
    """On while a cycle is being detected on the source entity."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: MaintenanceCoordinator) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, "cycle_running")

    @property
    def is_on(self) -> bool:
        """Return whether a cycle is currently in progress."""
        return self.coordinator.data.appliance.active_since is not None


class TaskDueBinarySensor(MaintenanceTaskEntity, BinarySensorEntity):
    """On once a specific maintenance task has reached its limit."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: MaintenanceCoordinator, subentry_id: str) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, subentry_id, "task_due")

    @property
    def is_on(self) -> bool:
        """Return whether the task is overdue."""
        return self.progress.is_overdue
