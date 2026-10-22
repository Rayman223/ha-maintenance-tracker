# Maintenance Tracker for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Validate](https://github.com/rayman223/ha-maintenance-tracker/actions/workflows/validate.yml/badge.svg)](https://github.com/rayman223/ha-maintenance-tracker/actions/workflows/validate.yml)
[![Lint & Tests](https://github.com/rayman223/ha-maintenance-tracker/actions/workflows/tests.yml/badge.svg)](https://github.com/rayman223/ha-maintenance-tracker/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Track when your appliances need servicing — by **usage count**, **runtime hours**
or **calendar interval** — and see it on your dashboard before it becomes a
problem.

> Clean the washing machine drum every 30 cycles, descale it every 6 months,
> replace the filter every 100 cycles. One appliance, three tasks, one card.

## Features

- **One appliance, many maintenance tasks.** Each task has its own limits, its
  own progress and its own reset, all driven by shared appliance counters.
- **Three kinds of limits**, combinable per task: number of cycles, cumulated
  runtime hours, and calendar interval. The task falls due on whichever comes
  first.
- **Manual or automatic counting.** Press a button, call a service, or attach a
  source entity — a smart plug's power, the appliance's own state — and let
  cycles be counted for you.
- **Pre-alert before it is due.** A task turns *due soon* at 90 % of its limit
  (configurable) and *due* past it.
- **Notifications and events** when a task falls due, so automations can react.
- **History**: last service date, number of services, and an optional note.
- **A bundled Lovelace card**, registered automatically — no Lovelace resource
  to add by hand.

## Installation

### HACS (custom repository)

1. HACS → ⋮ → **Custom repositories**
2. Add `https://github.com/rayman223/ha-maintenance-tracker`, category
   **Integration**
3. Install **Maintenance Tracker**, then restart Home Assistant
4. **Settings → Devices & services → Add integration → Maintenance Tracker**

### Manual

Copy `custom_components/maintenance_tracker` into your Home Assistant
`config/custom_components/` directory and restart.

Requires Home Assistant **2025.12** or newer.

## Setting it up

### 1. Add the appliance

Each integration entry is one appliance, and becomes one device. You give it a
name and choose how its cycles are counted:

| Mode | What it does |
| --- | --- |
| **Manual only** | Nothing is watched. You press a button or call a service after each use. |
| **Numeric threshold** | The appliance counts as running while a source entity reads above a value — typically a smart plug's power in watts. |
| **Entity state** | The appliance counts as running while a source entity sits in one of the states you list, for example `run` or `washing`. |

For the automatic modes you also set two guards, which are what make detection
reliable in practice:

- **Minimum cycle duration** (default 5 min) — bursts shorter than this are
  discarded, so standby draw is never mistaken for a wash.
- **Grace period before end of cycle** (default 3 min) — the appliance must stay
  idle this long before the cycle is closed. This absorbs the pauses inside a
  programme, such as a soak between the wash and the spin.

A source entity going `unavailable` is ignored rather than treated as idle, so a
flaky sensor cannot cut a running cycle short.

### 2. Add maintenance tasks

On the appliance's page, **Add maintenance task**. Set at least one limit; leave
the others at `0` to ignore them.

For a washing machine, for example:

| Task | Cycles | Hours | Days |
| --- | --- | --- | --- |
| Clean the drum | 30 | — | — |
| Replace the filter | 100 | — | — |
| Descale | — | — | 180 |

Tasks can be edited or deleted at any time from the same page.

## Entities

For an appliance named *Washing machine* with a task named *Clean the drum*:

| Entity | Description |
| --- | --- |
| `sensor.washing_machine_cycles` | Lifetime cycle count. |
| `sensor.washing_machine_runtime` | Lifetime running time, in hours. |
| `binary_sensor.washing_machine_maintenance_required` | On when **any** task is due. Attributes list which ones. |
| `binary_sensor.washing_machine_cycle_running` | On while a cycle is in progress (automatic modes only). |
| `button.washing_machine_register_a_cycle` | Adds one cycle. |
| `sensor.washing_machine_clean_the_drum` | Task status: `ok`, `due_soon` or `overdue`. Carries every detail as attributes. |
| `sensor.washing_machine_clean_the_drum_progress` | Progress towards the nearest limit, 0–100 %. |
| `sensor.washing_machine_clean_the_drum_last_service` | When it was last serviced. |
| `binary_sensor.washing_machine_clean_the_drum_due` | On when this task is due. |
| `button.washing_machine_clean_the_drum_serviced` | Resets the task and records the service. |

The task status sensor carries everything a dashboard needs in one place:
`progress`, `cycles_since_service`, `cycles_limit`, `cycles_remaining`, the same
three for `hours` and `days`, plus `last_service`, `service_count` and
`last_note`.

## The dashboard card

The integration serves and registers `custom:maintenance-tracker-card` itself,
so it is available as soon as the integration is installed. Add it from the card
picker, or in YAML:

```yaml
type: custom:maintenance-tracker-card
device: 1f2e3d4c5b6a79889900112233445566
```

| Option | Default | Description |
| --- | --- | --- |
| `device` | — | Appliance to show. Omit to show every tracked task. |
| `entities` | — | Explicit list of task status sensors, instead of `device`. |
| `title` | device name | Card heading. |
| `counter_entity` | auto | Cycle counter shown in the footer. |
| `show_progress` | `true` | Show the progress bars. |
| `show_counter` | `true` | Show the footer with the counter and the **+1 cycle** button. |

Tasks are listed most urgent first. The wrench button on a row marks that task
as serviced; clicking the name opens the usual more-info dialog.

## Services

| Service | Target | Description |
| --- | --- | --- |
| `maintenance_tracker.add_cycles` | the appliance's *Cycles* sensor | Adds `count` cycles (negative to correct a miscount). |
| `maintenance_tracker.set_cycles` | the appliance's *Cycles* sensor | Sets the counter to an absolute value. |
| `maintenance_tracker.mark_serviced` | a task status sensor | Records the task as done, with an optional `note` and `serviced_at`. |

```yaml
action: maintenance_tracker.mark_serviced
target:
  entity_id: sensor.washing_machine_replace_the_filter
data:
  note: Filter reference 481248058106
```

## Events

| Event | Fired when |
| --- | --- |
| `maintenance_tracker_cycle_completed` | A cycle finishes. Includes `cycles`, `duration`, `started_at`, `ended_at`. |
| `maintenance_tracker_maintenance_due` | A task reaches a limit. Includes `task` and `ratio`. |
| `maintenance_tracker_maintenance_completed` | A task is marked as serviced. |

Counting a cycle from an appliance that reports its own end-of-programme:

```yaml
triggers:
  - trigger: state
    entity_id: sensor.washer_programme
    to: finished
actions:
  - action: maintenance_tracker.add_cycles
    target:
      entity_id: sensor.washing_machine_cycles
```

Announcing a due task on a speaker:

```yaml
triggers:
  - trigger: event
    event_type: maintenance_tracker_maintenance_due
actions:
  - action: tts.speak
    target:
      entity_id: tts.piper
    data:
      message: "{{ trigger.event.data.appliance }} needs servicing: {{ trigger.event.data.task }}"
```

## How the counters work

Counters are stored **once per appliance**, as lifetime totals. Each task
records the totals it was last serviced at, and its progress is simply
`total − baseline`. Marking a task as serviced moves its baseline rather than
resetting a counter, which means a single writer per counter, no drift between
tasks, and a lifetime history that is never destroyed.

Runtime is credited every minute while a cycle runs, so an unexpected restart
costs at most one minute. If Home Assistant stops mid-cycle, the cycle is
resumed when it comes back — or closed at the last accounted instant if the
appliance finished in the meantime. Downtime itself is never credited as
runtime, since there is no way to know whether the appliance kept running.

## Contributing

Use Python 3.14 for the development checks, as in the GitHub Actions workflow.

```bash
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
python scripts/build_translations.py --check   # keeps translations/en.json in sync
pytest
node --check custom_components/maintenance_tracker/frontend/maintenance-tracker-card.js
```

English wording lives in `strings.json`; `translations/en.json` is generated
from it by `scripts/build_translations.py`. Other languages, such as
`translations/fr.json`, are written by hand.

The brand icon is generated too — `python scripts/build_brand_assets.py`
redraws `custom_components/maintenance_tracker/brand/` at both required sizes.

## License

[MIT](LICENSE)
