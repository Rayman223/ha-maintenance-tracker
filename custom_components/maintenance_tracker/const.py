"""Constants for the Maintenance Tracker integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "maintenance_tracker"

# --- Config entry (one entry == one appliance) -------------------------------

CONF_APPLIANCE_NAME: Final = "appliance_name"

# Automatic cycle detection (optional).
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
DEFAULT_MIN_ACTIVE_DURATION: Final = 120  # seconds
DEFAULT_IDLE_DEBOUNCE: Final = 300  # seconds

# --- Maintenance tasks (N per appliance) -------------------------------------

CONF_TASKS: Final = "tasks"
CONF_TASK_ID: Final = "task_id"
CONF_TASK_NAME: Final = "task_name"
CONF_LIMIT_CYCLES: Final = "limit_cycles"
CONF_LIMIT_HOURS: Final = "limit_hours"
CONF_LIMIT_DAYS: Final = "limit_days"
CONF_WARN_RATIO: Final = "warn_ratio"

DEFAULT_WARN_RATIO: Final = 0.9  # pre-alert at 90 % of the limit

# --- Task status -------------------------------------------------------------

STATUS_OK: Final = "ok"
STATUS_DUE_SOON: Final = "due_soon"
STATUS_OVERDUE: Final = "overdue"

# --- Services ----------------------------------------------------------------

SERVICE_INCREMENT: Final = "increment"
SERVICE_SET_COUNTER: Final = "set_counter"
SERVICE_COMPLETE_TASK: Final = "complete_task"
SERVICE_RESET_TASK: Final = "reset_task"

ATTR_COUNT: Final = "count"
ATTR_TASK_ID: Final = "task_id"
ATTR_NOTE: Final = "note"

# --- Events ------------------------------------------------------------------

EVENT_CYCLE_COMPLETED: Final = f"{DOMAIN}_cycle_completed"
EVENT_MAINTENANCE_DUE: Final = f"{DOMAIN}_maintenance_due"
EVENT_MAINTENANCE_COMPLETED: Final = f"{DOMAIN}_maintenance_completed"

# --- Storage -----------------------------------------------------------------

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.data"

# --- Frontend ----------------------------------------------------------------

FRONTEND_SCRIPT_URL: Final = f"/{DOMAIN}/maintenance-tracker-card.js"
FRONTEND_DIR_NAME: Final = "frontend"
