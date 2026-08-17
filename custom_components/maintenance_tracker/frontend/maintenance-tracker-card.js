/**
 * Maintenance Tracker card.
 *
 * Shipped and registered by the `maintenance_tracker` integration, so there is
 * no Lovelace resource to add by hand. Written as a plain custom element on
 * purpose: no build step, no bundled dependencies, and the file you read is the
 * file Home Assistant serves.
 */

const CARD_TAG = "maintenance-tracker-card";
const EDITOR_TAG = "maintenance-tracker-card-editor";
const VERSION = "0.1.0";

const STATUS_ORDER = { overdue: 0, due_soon: 1, ok: 2 };
const STATUS_LABELS = {
  overdue: "Due",
  due_soon: "Due soon",
  ok: "OK",
};

/** A task sensor is recognised by the attributes the integration attaches. */
const isTaskSensor = (state) =>
  state &&
  state.entity_id.startsWith("sensor.") &&
  state.attributes &&
  typeof state.attributes.task === "string" &&
  typeof state.attributes.progress === "number";

/** Format a "x left" hint from whichever limit is closest to being reached. */
const remainingLabel = (attrs) => {
  const candidates = [
    [attrs.cycles_remaining, attrs.cycles_limit, "cycle", "cycles"],
    [attrs.hours_remaining, attrs.hours_limit, "hour", "hours"],
    [attrs.days_remaining, attrs.days_limit, "day", "days"],
  ].filter(([remaining, limit]) => limit && remaining !== null && remaining !== undefined);

  if (!candidates.length) return "";

  const [remaining, , singular, plural] = candidates.reduce((a, b) =>
    a[0] / a[1] <= b[0] / b[1] ? a : b,
  );
  const rounded = Math.round(Math.abs(remaining) * 10) / 10;
  const unit = rounded === 1 ? singular : plural;
  return remaining < 0
    ? `${rounded} ${unit} over`
    : `${rounded} ${unit} left`;
};

const relativeDate = (iso) => {
  if (!iso) return "never";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.round(days / 30);
  if (months < 12) return `${months} month${months === 1 ? "" : "s"} ago`;
  const years = Math.round(days / 365);
  return `${years} year${years === 1 ? "" : "s"} ago`;
};

class MaintenanceTrackerCard extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._built = false;
    this._rows = new Map();
  }

  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  static getStubConfig(hass) {
    const first = Object.values(hass.states).find(isTaskSensor);
    return { type: `custom:${CARD_TAG}`, device: first ? undefined : null };
  }

  setConfig(config) {
    if (config.entities && !Array.isArray(config.entities)) {
      throw new Error("`entities` must be a list of entity ids");
    }
    this._config = {
      show_counter: true,
      show_progress: true,
      ...config,
    };
    // The layout depends on the config, so rebuild from scratch.
    this._built = false;
    this._rows.clear();
    this.innerHTML = "";
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 1 + Math.max(this._rows.size, 1);
  }

  /* ---------------------------------------------------------------- data */

  /** Resolve which task sensors this card shows, in "most urgent first" order. */
  _tasks() {
    const hass = this._hass;
    let states;

    if (this._config.entities) {
      states = this._config.entities
        .map((entityId) => hass.states[entityId])
        .filter(isTaskSensor);
    } else {
      states = Object.values(hass.states).filter(isTaskSensor);
      if (this._config.device) {
        const registry = hass.entities || {};
        states = states.filter(
          (state) =>
            registry[state.entity_id] &&
            registry[state.entity_id].device_id === this._config.device,
        );
      }
    }

    return states.sort((a, b) => {
      const byStatus = (STATUS_ORDER[a.state] ?? 9) - (STATUS_ORDER[b.state] ?? 9);
      if (byStatus !== 0) return byStatus;
      return (b.attributes.progress ?? 0) - (a.attributes.progress ?? 0);
    });
  }

  /** Find the appliance-level cycle counter sitting on the same device. */
  _counterEntity(tasks) {
    if (this._config.counter_entity) return this._config.counter_entity;

    const registry = this._hass.entities || {};
    const deviceId =
      this._config.device ||
      (tasks.length && registry[tasks[0].entity_id]
        ? registry[tasks[0].entity_id].device_id
        : null);
    if (!deviceId) return null;

    const match = Object.values(this._hass.states).find((state) => {
      const entry = registry[state.entity_id];
      return (
        entry &&
        entry.device_id === deviceId &&
        state.attributes &&
        "cycle_in_progress" in state.attributes
      );
    });
    return match ? match.entity_id : null;
  }

  _title(tasks) {
    if (this._config.title !== undefined) return this._config.title;
    const registry = this._hass.devices || {};
    const entityRegistry = this._hass.entities || {};
    const deviceId =
      this._config.device ||
      (tasks.length && entityRegistry[tasks[0].entity_id]
        ? entityRegistry[tasks[0].entity_id].device_id
        : null);
    if (deviceId && registry[deviceId]) {
      return registry[deviceId].name_by_user || registry[deviceId].name;
    }
    return "Maintenance";
  }

  /* -------------------------------------------------------------- render */

  _render() {
    if (!this._hass) return;
    const tasks = this._tasks();

    if (!this._built) this._build();

    this._titleEl.textContent = this._title(tasks);

    const overdue = tasks.filter((task) => task.state === "overdue").length;
    this._badgeEl.textContent = overdue
      ? `${overdue} due`
      : `${tasks.length} task${tasks.length === 1 ? "" : "s"}`;
    this._badgeEl.className = `mt-badge ${overdue ? "overdue" : "ok"}`;

    this._renderRows(tasks);
    this._renderFooter(tasks);
  }

  _build() {
    const card = document.createElement("ha-card");

    const header = document.createElement("div");
    header.className = "mt-header";
    this._titleEl = document.createElement("div");
    this._titleEl.className = "mt-title";
    this._badgeEl = document.createElement("div");
    header.append(this._titleEl, this._badgeEl);

    this._listEl = document.createElement("div");
    this._listEl.className = "mt-list";

    this._footerEl = document.createElement("div");
    this._footerEl.className = "mt-footer";

    card.append(this._styles(), header, this._listEl, this._footerEl);
    this.append(card);
    this._built = true;
  }

  _renderRows(tasks) {
    const seen = new Set();

    if (!tasks.length) {
      this._listEl.textContent =
        "No maintenance task found. Add one from Settings → Devices & services.";
      this._listEl.className = "mt-list mt-empty";
      return;
    }
    this._listEl.className = "mt-list";

    tasks.forEach((task, index) => {
      seen.add(task.entity_id);
      let row = this._rows.get(task.entity_id);
      if (!row) {
        row = this._buildRow(task.entity_id);
        this._rows.set(task.entity_id, row);
      }
      // Keep the DOM in the urgency order computed above.
      if (this._listEl.children[index] !== row.root) {
        this._listEl.insertBefore(row.root, this._listEl.children[index] || null);
      }
      this._updateRow(row, task);
    });

    for (const [entityId, row] of this._rows) {
      if (!seen.has(entityId)) {
        row.root.remove();
        this._rows.delete(entityId);
      }
    }
  }

  _buildRow(entityId) {
    const root = document.createElement("div");
    root.className = "mt-row";

    const top = document.createElement("div");
    top.className = "mt-row-top";

    const name = document.createElement("button");
    name.className = "mt-name";
    name.type = "button";
    name.addEventListener("click", () => this._showMore(entityId));

    const status = document.createElement("span");
    status.className = "mt-status";

    const action = document.createElement("button");
    action.className = "mt-action";
    action.type = "button";
    action.title = "Mark as serviced";
    action.innerHTML = wrenchIcon();
    action.addEventListener("click", () => this._markServiced(entityId));

    top.append(name, status, action);

    const bar = document.createElement("div");
    bar.className = "mt-bar";
    const fill = document.createElement("div");
    fill.className = "mt-bar-fill";
    bar.append(fill);

    const meta = document.createElement("div");
    meta.className = "mt-meta";

    root.append(top, bar, meta);
    if (!this._config.show_progress) bar.style.display = "none";

    return { root, name, status, fill, bar, meta };
  }

  _updateRow(row, task) {
    const attrs = task.attributes;
    row.name.textContent = attrs.task;
    row.status.textContent = STATUS_LABELS[task.state] || task.state;
    row.status.className = `mt-status ${task.state}`;
    row.root.className = `mt-row ${task.state}`;

    const progress = Math.max(0, Math.min(attrs.progress ?? 0, 100));
    row.fill.style.width = `${progress}%`;
    row.fill.className = `mt-bar-fill ${task.state}`;

    const remaining = remainingLabel(attrs);
    const serviced = `serviced ${relativeDate(attrs.last_service)}`;
    row.meta.textContent = remaining ? `${remaining} · ${serviced}` : serviced;
  }

  _renderFooter(tasks) {
    if (!this._config.show_counter) {
      this._footerEl.style.display = "none";
      return;
    }

    const counterId = this._counterEntity(tasks);
    const counter = counterId ? this._hass.states[counterId] : null;
    if (!counter) {
      this._footerEl.style.display = "none";
      return;
    }
    this._footerEl.style.display = "";

    if (!this._counterLabel) {
      this._counterLabel = document.createElement("div");
      this._counterLabel.className = "mt-counter";
      this._counterButton = document.createElement("button");
      this._counterButton.className = "mt-add";
      this._counterButton.type = "button";
      this._counterButton.textContent = "+1 cycle";
      this._footerEl.append(this._counterLabel, this._counterButton);
    }

    this._counterButton.onclick = () =>
      this._hass.callService(
        "maintenance_tracker",
        "add_cycles",
        { count: 1 },
        { entity_id: counter.entity_id },
      );

    const running = counter.attributes.cycle_in_progress;
    this._counterLabel.textContent = running
      ? `${counter.state} cycles · running`
      : `${counter.state} cycles`;
  }

  /* -------------------------------------------------------------- actions */

  _markServiced(entityId) {
    this._hass.callService("maintenance_tracker", "mark_serviced", {}, {
      entity_id: entityId,
    });
  }

  _showMore(entityId) {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      }),
    );
  }

  _styles() {
    const style = document.createElement("style");
    style.textContent = `
      ha-card { padding: 16px; }
      .mt-header {
        display: flex; align-items: center; justify-content: space-between;
        gap: 12px; margin-bottom: 12px;
      }
      .mt-title {
        font-size: 1.25rem; font-weight: 500; color: var(--primary-text-color);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      }
      .mt-badge {
        flex: none; font-size: .75rem; font-weight: 600; padding: 3px 10px;
        border-radius: 12px; color: var(--text-primary-color, #fff);
      }
      .mt-badge.ok { background: var(--success-color, #43a047); }
      .mt-badge.overdue { background: var(--error-color, #db4437); }

      .mt-list { display: flex; flex-direction: column; gap: 14px; }
      .mt-empty { color: var(--secondary-text-color); font-size: .9rem; }

      .mt-row-top { display: flex; align-items: center; gap: 8px; }
      .mt-name {
        flex: 1; min-width: 0; text-align: left; background: none; border: none;
        padding: 0; font: inherit; font-size: .95rem; cursor: pointer;
        color: var(--primary-text-color);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      }
      .mt-name:hover { color: var(--primary-color); }

      .mt-status {
        flex: none; font-size: .7rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: .04em;
      }
      .mt-status.ok { color: var(--secondary-text-color); }
      .mt-status.due_soon { color: var(--warning-color, #ffa600); }
      .mt-status.overdue { color: var(--error-color, #db4437); }

      .mt-action {
        flex: none; display: grid; place-items: center; width: 32px; height: 32px;
        border: none; border-radius: 50%; cursor: pointer; background: none;
        color: var(--secondary-text-color);
      }
      .mt-action:hover {
        background: var(--divider-color); color: var(--primary-text-color);
      }
      .mt-action svg { width: 20px; height: 20px; fill: currentColor; }

      .mt-bar {
        height: 6px; margin-top: 6px; border-radius: 3px; overflow: hidden;
        background: var(--divider-color);
      }
      .mt-bar-fill {
        height: 100%; border-radius: 3px; transition: width .3s ease;
        background: var(--success-color, #43a047);
      }
      .mt-bar-fill.due_soon { background: var(--warning-color, #ffa600); }
      .mt-bar-fill.overdue { background: var(--error-color, #db4437); }

      .mt-meta {
        margin-top: 4px; font-size: .75rem; color: var(--secondary-text-color);
      }

      .mt-footer {
        display: flex; align-items: center; justify-content: space-between;
        gap: 12px; margin-top: 16px; padding-top: 12px;
        border-top: 1px solid var(--divider-color);
      }
      .mt-counter { font-size: .8rem; color: var(--secondary-text-color); }
      .mt-add {
        font: inherit; font-size: .8rem; font-weight: 500; cursor: pointer;
        padding: 6px 14px; border-radius: 18px; background: none;
        border: 1px solid var(--divider-color); color: var(--primary-color);
      }
      .mt-add:hover { background: var(--divider-color); }
    `;
    return style;
  }
}

function wrenchIcon() {
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/></svg>`;
}

/* ----------------------------------------------------------- config editor */

class MaintenanceTrackerCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;

    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (schema) =>
        ({
          title: "Title",
          device: "Appliance",
          show_progress: "Show progress bars",
          show_counter: "Show the cycle counter",
        })[schema.name] || schema.name;
      this._form.addEventListener("value-changed", (event) => {
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: event.detail.value },
            bubbles: true,
            composed: true,
          }),
        );
      });
      this.append(this._form);
    }

    this._form.hass = this._hass;
    this._form.data = this._config;
    this._form.schema = [
      { name: "title", selector: { text: {} } },
      {
        name: "device",
        selector: { device: { integration: "maintenance_tracker" } },
      },
      { name: "show_progress", selector: { boolean: {} } },
      { name: "show_counter", selector: { boolean: {} } },
    ];
  }
}

if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, MaintenanceTrackerCard);
}
if (!customElements.get(EDITOR_TAG)) {
  customElements.define(EDITOR_TAG, MaintenanceTrackerCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "Maintenance Tracker",
    description: "Maintenance tasks of an appliance, with progress and a reset button.",
    preview: true,
    documentationURL: "https://github.com/rayman223/ha-maintenance-tracker",
  });
}

console.info(
  `%c MAINTENANCE-TRACKER-CARD %c ${VERSION} `,
  "color:#fff;background:#03a9f4;font-weight:700",
  "color:#03a9f4;background:#fff;font-weight:700",
);
