# Vending Tracker — Automations

Verified inventory of every automation shipped by this app. All items were
cross-checked end-to-end (hooks → function definitions, notification
conditions/fields → doctype schemas, doc events → methods, server scripts →
whitelisted methods) and pass `node validate_app.cjs`.

**Summary: 23 named automations** — 6 scheduled jobs, 8 notifications
(7 enabled + 1 intentionally replaced), 5 document-event hooks, 4 doctype
controller actions — plus supporting IoT APIs, server scripts, workflows and
install-time automation.

---

## 1. Scheduled background jobs (6) — Frappe Scheduler

Wired in `hooks.py` (`scheduler_events`) → `scheduler_events.py`.

### Hourly
1. **Machine Health Check** — marks IoT machines **Offline** when no heartbeat
   is received for N minutes (`offline_after_minutes` setting, default 30),
   logs a `Vending Machine Health Log` record → fires the **Machine Offline**
   alert.
2. **IoT Synchronization** — server-initiated poll of each online IoT machine's
   `api_endpoint` (passing `machine_id` + `iot_token`). Success/failure is
   recorded on `last_api_status` / `last_sync_status` → fires the **API
   Failure** / **IoT Sync Failure** alerts.

### Daily
3. **Dashboard Refresh** — reconciles every slot's cached stock from the
   native Stock Ledger (Bin) and self-heals corrupted dashboard chart filters
   / config.
4. **Low Stock Detection** — finds active slots at or below their reorder
   threshold and notifies Vending Managers — **once per depletion cycle**
   (tracked by the `low_stock_notified` flag, so no spam).
5. **Revenue Summary** — on the 1st of each month, emails the previous
   month's revenue summary to **Vending Administrators**.
6. **Daily Reports** — emails yesterday's sales + low stock summary to
   **Vending Managers**.

---

## 2. Email / system notifications (8) — Notification records

| # | Notification | Document Type | Event | Status |
| --- | --- | --- | --- | --- |
| 7 | **Low Stock** | Machine Product Slot | Save | ✅ Enabled |
| 8 | **Maintenance Due** (≤ 7 days) | Vending Machine | Save | ✅ Enabled |
| 9 | **Machine Offline** (`is_online` → 0) | Vending Machine | Value Change | ✅ Enabled |
| 10 | **Machine Disabled** (`status` → Disabled) | Vending Machine | Value Change | ✅ Enabled |
| 11 | **API Failure** (`last_api_status` → Failed) | Vending Machine | Value Change | ✅ Enabled |
| 12 | **IoT Sync Failure** (`last_sync_status` → Failed) | Vending Machine | Value Change | ✅ Enabled |
| 13 | **Restock Completed** (vending Stock Entry) | Stock Entry | Submit | ✅ Enabled |
| 14 | **High Sales** (submitted sale) | Vending Sales Entry | Submit | ⚠️ Disabled by design |

> **High Sales** is disabled because Notification conditions run in a sandbox
> without `frappe.db`, so the threshold couldn't be read at eval time. It is
> replaced by the Python `notify_high_sales()` method wired into the Sales
> Entry `on_submit`, which reads the threshold from Vending Tracker Settings.

---

## 3. Document events (5) — hooks `doc_events`

15. **Stock Entry `validate`** → `validate_vending_stock_entry` — validates the
    machine-linked warehouse and that items belong to Vending Products.
16. **Stock Entry `on_submit`** → `on_vending_stock_entry_submit` — reconciles
    slot stock from the Stock Ledger.
17. **Stock Entry `on_cancel`** → `on_vending_stock_entry_cancel` — reconciles
    slot stock from the Stock Ledger.
18. **Dashboard Chart `on_update`** → `repair_dashboard_widgets` — self-heals
    corrupted chart filters / config on every save.
19. **Dashboard Settings `on_update`** → `repair_dashboard_settings` — drops
    malformed per-user chart filter overrides.

---

## 4. Doctype controller automation (4)

20. **Vending Sales Entry `on_submit`** — auto-creates and submits a native
    **Material Issue** Stock Entry (stock consumed via the Stock Ledger),
    recomputes slot stock, and fires the **Low Stock** + **High Sales** alerts.
21. **Vending Sales Entry `on_cancel`** — auto-cancels the linked Stock Entry
    and restores stock.
22. **Vending Machine `validate`** — auto-generates the IoT token and
    **auto-creates the linked Warehouse** (`VM - <machine_id>`) when the
    setting is enabled.
23. **Machine Product Slot `on_update`** — recomputes cached `current_stock` /
    `stock_status` from the Stock Ledger.

---

## 5. IoT device-driven automation (REST APIs)

Guest APIs authenticated by `machine_id` + `iot_token`:

- **`heartbeat`** — auto-brings the machine back **Online**, updates telemetry
  (battery / temperature), clears the Offline status and logs a health record.
- **`sync_sales`** — bulk-pushes device sales; each entry is submitted and
  triggers the full sales chain (auto Material Issue + alerts).
- **`sync_stock`** — reconciles device-reported counts against the machine
  warehouse by **auto-creating Material Receipt / Material Issue** Stock
  Entries.
- Supporting endpoints: `register`, `get_status`, `get_inventory`,
  `sync_products`, `test_connection` (admin), `list_machines`, `ping`.

## 6. Server scripts (2) — REST API

- **`Vending_Machine_Status`** — `GET /api/method/Vending_Machine_Status`.
- **`Vending_Low_Stock_Check`** — `GET /api/method/Vending_Low_Stock_Check`.

## 7. Workflows (2) — role-gated state machines

- **Vending Sales Entry Workflow** — Draft → Submitted → Cancelled.
- **Vending Restock Workflow** (on Stock Entry) — Draft → Submitted →
  Cancelled.

Workflow State master records (`Draft` / `Submitted` / `Cancelled`) are
auto-created on install and migrate by `install.py create_workflow_states()`.

## 8. Install-time automation

- **`after_install` / `after_migrate`** (`install.py`) — creates workflow
  states, repairs dashboard widgets and notifications, creates the Vending
  Products item group, grants role permissions, and seeds idempotent demo data
  (items, machines, warehouses, stock, submitted sales) when no real sales
  exist yet.
- **`before_uninstall`** (`uninstall.py`) — cleanly removes app artifacts.
