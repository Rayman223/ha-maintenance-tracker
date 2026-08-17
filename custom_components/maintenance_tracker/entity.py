"""Base entities for Maintenance Tracker."""

from __future__ import annotations

from datetime import datetime
from typing import NoReturn

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MaintenanceCoordinator
from .models import TaskProgress


class MaintenanceEntity(CoordinatorEntity[MaintenanceCoordinator]):
    """An entity describing the appliance as a whole."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MaintenanceCoordinator, key: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Maintenance Tracker",
            model="Appliance",
            entry_type=DeviceEntryType.SERVICE,
        )

    # Entity services are registered for a whole platform, so every sensor of
    # this integration exposes them. These defaults turn "right service, wrong
    # entity" into an actionable message instead of an AttributeError.

    def _wrong_target(self, service: str, expected: str) -> NoReturn:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="wrong_target",
            translation_placeholders={
                "service": service,
                "entity_id": self.entity_id,
                "expected": expected,
            },
        )

    async def async_add_cycles(self, count: int) -> None:
        """Reject the service on entities that hold no cycle counter."""
        self._wrong_target("add_cycles", "cycles")

    async def async_set_cycles(self, count: int) -> None:
        """Reject the service on entities that hold no cycle counter."""
        self._wrong_target("set_cycles", "cycles")

    async def async_mark_serviced(
        self, note: str | None = None, serviced_at: datetime | None = None
    ) -> None:
        """Reject the service on entities that are not a maintenance task."""
        self._wrong_target("mark_serviced", "task status")


class MaintenanceTaskEntity(MaintenanceEntity):
    """An entity describing one maintenance task of the appliance.

    Task entities live on the appliance device but belong to their own
    subentry, so removing a task removes exactly its own entities.
    """

    def __init__(
        self, coordinator: MaintenanceCoordinator, subentry_id: str, key: str
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator, key)
        self._subentry_id = subentry_id
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{subentry_id}_{key}"
        )
        self._attr_translation_placeholders = {
            "task": coordinator.task_title(subentry_id)
        }

    @property
    def available(self) -> bool:
        """Return False once the task has been removed from the appliance."""
        return super().available and self._subentry_id in self.coordinator.data.progress

    @property
    def progress(self) -> TaskProgress:
        """Return the task's current progress."""
        return self.coordinator.data.progress[self._subentry_id]
