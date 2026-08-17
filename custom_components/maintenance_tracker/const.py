"""Constants for the Maintenance Tracker integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "maintenance_tracker"

PLATFORMS: Final = ["binary_sensor", "button", "sensor"]

# --- Config entry: one entry == one appliance --------------------------------

CONF_SOURCE_ENTITY: Final = "source_entity"
CONF_DETECTION_MODE: Final = "detection_mode"
CONF_POWER_THRESHOLD: Final = "power_threshold"
CONF_ACTIVE_STATES: Final = "active_states"
CONF_MIN_ACTIVE_DURATION: Final = "min_active_duration"
CONF_IDLE_DEBOUNCE: Final = "idle_debounce"

DETECTION_MODE_NONE: Final = "none"
DETECTION_MODE_THRESHOLD: Final = "threshold"
DETECTION_MODE_STATE: Final = "state"
DETECTION_MODES: Final = [
    DETECTION_MODE_NONE,
    DETECTION_MODE_THRESHOLD,
    DETECTION_MODE_STATE,
]

DEFAULT_POWER_THRESHOLD: Final = 10.0  # watts
DEFAULT_MIN_ACTIVE_DURATION: Final = 300  # seconds
DEFAULT_IDLE_DEBOUNCE: Final = 180  # seconds

# --- Subentries: N maintenance tasks per appliance ---------------------------

SUBENTRY_TYPE_TASK: Final = "task"

CONF_LIMIT_CYCLES: Final = "limit_cycles"
CONF_LIMIT_HOURS: Final = "limit_hours"
CONF_LIMIT_DAYS: Final = "limit_days"
CONF_WARN_RATIO: Final = "warn_ratio"
CONF_NOTIFY: Final = "notify"

DEFAULT_WARN_RATIO: Final = 90  # percent of the limit
DEFAULT_NOTIFY: Final = True

# --- Task status -------------------------------------------------------------

STATUS_OK: Final = "ok"
STATUS_DUE_SOON: Final = "due_soon"
STATUS_OVERDUE: Final = "overdue"
STATUSES: Final = [STATUS_OK, STATUS_DUE_SOON, STATUS_OVERDUE]

# --- Services ----------------------------------------------------------------

SERVICE_ADD_CYCLES: Final = "add_cycles"
SERVICE_SET_CYCLES: Final = "set_cycles"
SERVICE_MARK_SERVICED: Final = "mark_serviced"

ATTR_COUNT: Final = "count"
ATTR_NOTE: Final = "note"
ATTR_SERVICED_AT: Final = "serviced_at"

# --- Events ------------------------------------------------------------------

EVENT_CYCLE_COMPLETED: Final = f"{DOMAIN}_cycle_completed"
EVENT_MAINTENANCE_DUE: Final = f"{DOMAIN}_maintenance_due"
EVENT_MAINTENANCE_COMPLETED: Final = f"{DOMAIN}_maintenance_completed"

# --- Internals ---------------------------------------------------------------

STORAGE_VERSION: Final = 1

#: How often accumulated runtime is flushed while a cycle is running.
RUNTIME_TICK_SECONDS: Final = 60

#: Periodic recompute, so that calendar-based tasks become due without any
#: source entity having to change state.
RECOMPUTE_INTERVAL_MINUTES: Final = 5

SECONDS_PER_HOUR: Final = 3600
