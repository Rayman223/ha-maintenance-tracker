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

- **One appliance, many maintenance tasks.** Each task has its own limits,
  its own progress and its own reset.
- **Three kinds of limits**, combinable per task: number of cycles, cumulated
  runtime hours, and calendar interval (every N days).
- **Manual or automatic counting.** Press a button, call a service, or attach a
  source entity (smart plug power, appliance state) and let cycles be detected
  automatically.
- **Pre-alert before it is due** — a task turns `due_soon` at 90 % of its limit
  (configurable) and `overdue` past it.
- **Notifications** on due tasks, plus events you can hook automations onto.
- **History** — last service date and total number of services per task.
- **Bundled Lovelace card**, registered automatically. No manual resource to add.

## Installation

### HACS (custom repository)

1. HACS → ⋮ → **Custom repositories**
2. Add `https://github.com/rayman223/ha-maintenance-tracker`, category
   **Integration**
3. Install **Maintenance Tracker**, then restart Home Assistant
4. **Settings → Devices & Services → Add integration → Maintenance Tracker**

### Manual

Copy `custom_components/maintenance_tracker` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

Everything is configured from the UI. Adding an integration entry creates one
**appliance**; its options let you add, edit and remove **maintenance tasks**,
and optionally set up automatic cycle detection.

<!-- TODO: entity table, services, card options, automation examples -->

## Contributing

Issues and pull requests are welcome. Run `ruff check .` and `pytest` before
submitting; the card lives in `frontend/` and is built with `npm run build`.

## License

[MIT](LICENSE)
