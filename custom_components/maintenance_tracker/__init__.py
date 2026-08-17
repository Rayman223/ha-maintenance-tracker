"""The Maintenance Tracker integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_loaded_integration

from .const import DOMAIN, PLATFORMS, STORAGE_VERSION
from .coordinator import MaintenanceConfigEntry, MaintenanceCoordinator

_LOGGER = logging.getLogger(__name__)

FRONTEND_DIR = "frontend"
CARD_FILENAME = "maintenance-tracker-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"

#: Guards the one-time, hass-wide frontend registration.
_FRONTEND_KEY = f"{DOMAIN}_frontend_registered"


async def async_setup_entry(hass: HomeAssistant, entry: MaintenanceConfigEntry) -> bool:
    """Set up one appliance from a config entry."""
    await _async_register_frontend(hass)

    coordinator = MaintenanceCoordinator(hass, entry)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Adding, editing or removing a task updates the entry; reloading is what
    # creates and removes the matching entities.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: MaintenanceConfigEntry
) -> bool:
    """Unload an appliance."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def async_remove_entry(
    hass: HomeAssistant, entry: MaintenanceConfigEntry
) -> None:
    """Drop the persisted counters of a deleted appliance.

    The entry is already unloaded at this point, so the store is addressed
    directly rather than through the (gone) coordinator.
    """
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def _async_reload_entry(
    hass: HomeAssistant, entry: MaintenanceConfigEntry
) -> None:
    """Reload the appliance after a configuration change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the bundled Lovelace card and load it, once per Home Assistant.

    Doing this here is what removes the usual "add a Lovelace resource" step:
    installing the integration is enough for `custom:maintenance-tracker-card`
    to exist.

    Everything here is best effort. Tracking maintenance is the point of the
    integration; a dashboard card that cannot be served must never keep the
    appliances from being set up.
    """
    if hass.data.get(_FRONTEND_KEY):
        return
    hass.data[_FRONTEND_KEY] = True

    if "frontend" not in hass.config.components:
        _LOGGER.debug("Frontend not loaded; skipping the bundled card")
        return

    integration = async_get_loaded_integration(hass, DOMAIN)
    card_path = Path(integration.file_path) / FRONTEND_DIR / CARD_FILENAME

    if not await hass.async_add_executor_job(card_path.is_file):
        _LOGGER.warning(
            "Bundled card not found at %s; the integration still works, but "
            "custom:maintenance-tracker-card will be unavailable",
            card_path,
        )
        return

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(card_path))]
        )
        # The version query string busts the browser cache on upgrades.
        add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")
    except Exception:  # Never block setup over the card.
        _LOGGER.exception("Could not register the bundled Lovelace card")
