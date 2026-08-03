# Vending Tracker

Enterprise vending machine management for **Frappe v15 / ERPNext v15+**.

The application manages and monitors multiple vending machines across multiple
locations while reusing ERPNext's native inventory, warehouse, stock, pricing
and reporting engine — no duplicate stock tables or movement logic.

## Installation

```bash
bench get-app https://github.com/your-org/vending_tracker
bench --site [site_name] install-app vending_tracker
bench --site [site_name] migrate
```

ERPNext v15+ must be installed on the site first (`required_apps = ["erpnext"]`).

## What gets installed

- **Doctypes**: `Vending Machine`, `Machine Product Slot`, `Vending Sales Entry`,
  `Vending Machine Health Log`, `Vending Tracker Settings` (Single).
- **Stock Entry integration**: Custom Fields (`custom_vending_machine`,
  `custom_is_vending_transaction`, `custom_vending_source_document`) + the
  **Vending Restock Workflow** (Draft → Submitted → Cancelled) on `Stock Entry`.
  Restocks are native ERPNext Stock Entries (`Material Transfer` /
  `Material Receipt`) into the machine's dedicated warehouse. All stock movement
  flows through the native Stock Ledger only.
- **Sales**: `Vending Sales Entry` with its own workflow. On submission it
  automatically creates a native `Material Issue` Stock Entry, reducing machine
  stock exclusively through the Stock Ledger.
- **Master data**: Reuses ERPNext `Item`, `Item Group`, `Item Price`, `Warehouse`,
  `Bin`, `Stock Entry`, `Stock Ledger Entry`, `Address`, `Contact`, `Company`,
  `UOM`, `Notification`, `User`, `Role`, `Dashboard`. Only items in the
  **Vending Products** item group are eligible. Item custom fields
  (`Vending Category`, `Default Reorder Threshold`, `Slot Capacity`) are added
  via fixtures.
- **10 reports** (Script + Query), **6 number cards**, **5 dashboard charts**,
  a **Vending Overview workspace**, **8 notifications**, **3 roles**, **2
  workflows**, **4 print formats**, **client & server scripts**.
- **REST APIs** for IoT machine registration, heartbeat, status, sales sync,
  stock sync, product sync and inventory lookup (token authenticated).
- **Scheduler jobs** for low stock detection, dashboard refresh, IoT
  synchronisation, daily reports, revenue summary and machine health checks.

## Fixtures & module files

Version-controlled configuration is delivered two ways, both auto-installed on
`migrate`:

- `fixtures/` — Custom Field, Property Setter, Client Script, Server Script,
  Role, Notification, Workflow, Print Format.
- module folders — `doctype/`, `report/`, `workspace/`, `dashboard_chart/`,
  `number_card/`, `templates/`.

Both are auto-installed on `bench migrate` (reports, workspaces, charts and
cards sync as module files; the rest through the fixture import). You can
regenerate fixture snapshots anytime with `bench --site [site] export-fixtures`.

## Dashboard vs Workspace

In Frappe v14+ the legacy `Dashboard` doctype was replaced by **Workspaces**
(ERPNext v15 itself ships no `{module}_dashboard` folders). The requested
"Vending Overview" dashboard is therefore delivered as the **Vending Tracker**
workspace, which contains all the requested blocks: revenue / today's / monthly
revenue number cards, revenue-by-machine and monthly revenue charts, best
selling products (Product Performance chart), stock level trend chart, low
stock alert, restock history and machine status links.

## REST APIs (token-authenticated)

IoT devices authenticate with `machine_id` + `iot_token`:

- `POST /api/method/vending_tracker.api.machine.register` (admin)
- `GET /api/method/vending_tracker.api.machine.heartbeat`
- `GET /api/method/vending_tracker.api.machine.get_status`
- `POST /api/method/vending_tracker.api.sales.sync_sales`
- `POST /api/method/vending_tracker.api.stock.sync_stock`
- `GET /api/method/vending_tracker.api.stock.get_inventory`
- `GET /api/method/vending_tracker.api.products.sync_products`

Server Scripts also expose `GET /api/method/Vending_Machine_Status` and
`GET /api/method/Vending_Low_Stock_Check` (login required).

## Notes

- **Workflow blast radius**: the `Vending Restock Workflow` is intentionally
  applied to `Stock Entry` (per project decision). Because workflows apply to a
  whole doctype, every Stock Entry on the instance gets the `workflow_state`
  field and workflow action bar. Programmatic submission from ERPNext (e.g.
  purchase receipts) is unaffected — workflow states are set automatically on
  submit/cancel — and Stock User / Stock Manager / System Manager are all in
  the transitions, so standard ERPNext users are not locked out. If you prefer
  zero impact on non-vending stock entries, deactivate the workflow and rely
  on the built-in docstatus instead.
- **Install hooks**: install/uninstall logic lives in `install.py` /
  `uninstall.py` (hooks `after_install` / `before_uninstall`), the standard
  Frappe v15 convention.
- **Sample data** (6 products, one machine + slots) is created on install, but
  only when the site has a default company configured (fresh sites usually set
  one via the setup wizard). It is existence-guarded and safe to re-run; delete
  it in production if not needed.
- The `Vending Sales Entry` and `Stock Entry` workflows both mirror the native
  docstatus flow (Draft → Submitted → Cancelled).
