"""Button platform for Maintenance Tracker."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SUBENTRY_TYPE_TASK
from .coordinator import MaintenanceConfigEntry, MaintenanceCoordinator
from .entity import MaintenanceEntity, MaintenanceTaskEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MaintenanceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the appliance and task buttons."""
    coordinator = config_entry.runtime_data

    async_add_entities([RegisterCycleButton(coordinator)])

    for subentry_id, subentry in config_entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_TASK:
            continue
        async_add_entities(
            [MarkServicedButton(coordinator, subentry_id)],
            config_subentry_id=subentry_id,
        )


class RegisterCycleButton(MaintenanceEntity, ButtonEntity):
    """Count one cycle by hand, for appliances without a source entity."""

    _attr_icon = "mdi:plus-circle-outline"

    def __init__(self, coordinator: MaintenanceCoordinator) -> None:
        """Initialise the button."""
        super().__init__(coordinator, "register_cycle")

    async def async_press(self) -> None:
        """Add one cycle to the appliance counter."""
        await self.coordinator.async_add_cycles(1)


class MarkServicedButton(MaintenanceTaskEntity, ButtonEntity):
    """Reset a task's counters, recording that it has just been serviced."""

    _attr_icon = "mdi:wrench-check"

    def __init__(self, coordinator: MaintenanceCoordinator, subentry_id: str) -> None:
        """Initialise the button."""
        super().__init__(coordinator, subentry_id, "mark_serviced")

    async def async_press(self) -> None:
        """Mark the task as serviced now."""
        await self.coordinator.async_mark_serviced(self._subentry_id)
