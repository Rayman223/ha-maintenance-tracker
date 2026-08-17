"""Config and subentry flows for Maintenance Tracker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ACTIVE_STATES,
    CONF_DETECTION_MODE,
    CONF_IDLE_DEBOUNCE,
    CONF_LIMIT_CYCLES,
    CONF_LIMIT_DAYS,
    CONF_LIMIT_HOURS,
    CONF_MIN_ACTIVE_DURATION,
    CONF_NOTIFY,
    CONF_POWER_THRESHOLD,
    CONF_SOURCE_ENTITY,
    CONF_WARN_RATIO,
    DEFAULT_IDLE_DEBOUNCE,
    DEFAULT_MIN_ACTIVE_DURATION,
    DEFAULT_NOTIFY,
    DEFAULT_POWER_THRESHOLD,
    DEFAULT_WARN_RATIO,
    DETECTION_MODE_NONE,
    DETECTION_MODE_STATE,
    DETECTION_MODE_THRESHOLD,
    DETECTION_MODES,
    DOMAIN,
    SUBENTRY_TYPE_TASK,
)


def _mode_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the schema selecting how cycles are counted."""
    return vol.Schema(
        {
            vol.Required(
                CONF_DETECTION_MODE,
                default=defaults.get(CONF_DETECTION_MODE, DETECTION_MODE_NONE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=DETECTION_MODES,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key=CONF_DETECTION_MODE,
                )
            )
        }
    )


def _required(key: str, default: Any) -> vol.Marker:
    """Return a required marker, only defaulted when there is a value to offer."""
    if default is None:
        return vol.Required(key)
    return vol.Required(key, default=default)


def _detection_schema(mode: str, defaults: dict[str, Any]) -> vol.Schema:
    """Build the detection settings schema for the selected mode."""
    schema: dict[Any, Any] = {}

    schema[_required(CONF_SOURCE_ENTITY, defaults.get(CONF_SOURCE_ENTITY))] = (
        selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "binary_sensor", "switch"])
        )
    )

    if mode == DETECTION_MODE_THRESHOLD:
        schema[
            vol.Required(
                CONF_POWER_THRESHOLD,
                default=defaults.get(CONF_POWER_THRESHOLD, DEFAULT_POWER_THRESHOLD),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, step=0.1, mode=selector.NumberSelectorMode.BOX
            )
        )
    elif mode == DETECTION_MODE_STATE:
        schema[
            vol.Required(
                CONF_ACTIVE_STATES, default=defaults.get(CONF_ACTIVE_STATES) or ["on"]
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[],
                multiple=True,
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

    schema[
        vol.Required(
            CONF_MIN_ACTIVE_DURATION,
            default=defaults.get(CONF_MIN_ACTIVE_DURATION, DEFAULT_MIN_ACTIVE_DURATION),
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            step=10,
            unit_of_measurement="s",
            mode=selector.NumberSelectorMode.BOX,
        )
    )
    schema[
        vol.Required(
            CONF_IDLE_DEBOUNCE,
            default=defaults.get(CONF_IDLE_DEBOUNCE, DEFAULT_IDLE_DEBOUNCE),
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            step=10,
            unit_of_measurement="s",
            mode=selector.NumberSelectorMode.BOX,
        )
    )

    return vol.Schema(schema)


def _task_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the maintenance task schema, pre-filled with current values."""
    optional_count = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, step=1, mode=selector.NumberSelectorMode.BOX
        )
    )
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): (
                selector.TextSelector()
            ),
            vol.Optional(
                CONF_LIMIT_CYCLES, default=defaults.get(CONF_LIMIT_CYCLES, 0)
            ): optional_count,
            vol.Optional(
                CONF_LIMIT_HOURS, default=defaults.get(CONF_LIMIT_HOURS, 0)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    step=0.5,
                    unit_of_measurement="h",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_LIMIT_DAYS, default=defaults.get(CONF_LIMIT_DAYS, 0)
            ): optional_count,
            vol.Required(
                CONF_WARN_RATIO,
                default=defaults.get(CONF_WARN_RATIO, DEFAULT_WARN_RATIO),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=50,
                    max=100,
                    step=5,
                    unit_of_measurement="%",
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_NOTIFY, default=defaults.get(CONF_NOTIFY, DEFAULT_NOTIFY)
            ): selector.BooleanSelector(),
        }
    )


def _validate_task(user_input: dict[str, Any]) -> dict[str, str]:
    """Reject a task that would never become due."""
    if not any(
        user_input.get(key)
        for key in (CONF_LIMIT_CYCLES, CONF_LIMIT_HOURS, CONF_LIMIT_DAYS)
    ):
        return {"base": "no_limit"}
    return {}


class MaintenanceTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for one appliance."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._appliance: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Name the appliance and pick how its cycles are counted."""
        if user_input is not None:
            self._async_abort_entries_match({CONF_NAME: user_input[CONF_NAME]})
            self._appliance = user_input
            if user_input[CONF_DETECTION_MODE] == DETECTION_MODE_NONE:
                return self._async_create()
            return await self.async_step_detection()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_NAME): selector.TextSelector()}
            ).extend(_mode_schema({}).schema),
        )

    async def async_step_detection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the source entity cycles are detected from."""
        if user_input is not None:
            self._appliance |= user_input
            return self._async_create()

        return self.async_show_form(
            step_id="detection",
            data_schema=_detection_schema(
                self._appliance[CONF_DETECTION_MODE], self._appliance
            ),
        )

    def _async_create(self) -> ConfigFlowResult:
        """Create the appliance entry."""
        return self.async_create_entry(
            title=self._appliance[CONF_NAME], data=self._appliance
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Declare that appliances hold maintenance tasks."""
        return {SUBENTRY_TYPE_TASK: MaintenanceTaskSubentryFlow}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow, used to retune cycle detection."""
        return MaintenanceTrackerOptionsFlow()


class MaintenanceTrackerOptionsFlow(OptionsFlow):
    """Let the user change how cycles are detected, after setup."""

    def __init__(self) -> None:
        """Initialise the flow."""
        self._mode: str = DETECTION_MODE_NONE

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the detection mode."""
        if user_input is not None:
            self._mode = user_input[CONF_DETECTION_MODE]
            if self._mode == DETECTION_MODE_NONE:
                # Drop the now-meaningless detection settings.
                return self.async_create_entry(
                    data={CONF_DETECTION_MODE: DETECTION_MODE_NONE}
                )
            return await self.async_step_detection()

        return self.async_show_form(
            step_id="init", data_schema=_mode_schema(self._current)
        )

    async def async_step_detection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the detection settings."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_DETECTION_MODE: self._mode} | user_input
            )

        return self.async_show_form(
            step_id="detection",
            data_schema=_detection_schema(self._mode, self._current),
        )


class MaintenanceTaskSubentryFlow(ConfigSubentryFlow):
    """Add and reconfigure the maintenance tasks of an appliance."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a maintenance task."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_task(user_input)
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_task_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit an existing maintenance task."""
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_task(user_input)
            if not errors:
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_task_schema(user_input or dict(subentry.data)),
            errors=errors,
        )
