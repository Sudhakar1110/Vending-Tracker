from frappe import _

app_name = "vending_tracker"
app_title = "Vending Tracker"
app_publisher = "Vending Tracker Contributors"
app_description = (
    "Enterprise vending machine management for Frappe v15 / ERPNext v15+ — "
    "machines, slots, sales, restocks, IoT APIs, dashboards and reports, "
    "powered by the native ERPNext inventory engine."
)
app_email = "support@vendingtracker.example"
app_license = "MIT"

# ERPNext must be installed before this app.
required_apps = ["erpnext"]

# Includes in <head>
# ------------------
app_include_js = "/assets/vending_tracker/js/vending_tracker.js"
app_include_css = "/assets/vending_tracker/css/vending_tracker.css"

# Fixtures
# --------
# Files are expected in the `fixtures/` directory:
#   fixtures/custom_field.json, fixtures/property_setter.json,
#   fixtures/client_script.json, fixtures/server_script.json,
#   fixtures/role.json, fixtures/workflow.json,
#   fixtures/print_format.json
#
# Reports, Workspaces, Dashboard Charts, Number Cards and Notifications are
# delivered as version-controlled module files (report/, workspace/,
# dashboard_chart/, number_card/, notification/ folders) and are auto-synced
# during migrate — the standard ERPNext v15 approach. They are intentionally
# NOT listed here: module imports skip doctype validation (import_doc sets
# ignore_validate), while fixture imports run full doctype validation, which
# rejects standard Notifications and standard charts.
fixtures = [
    "Custom Field",
    "Property Setter",
    "Client Script",
    "Server Script",
    "Role",
    "Workflow",
    "Print Format",
]

# Scheduler Events
# ----------------
# Scheduler jobs are defined in `scheduler_events.py`
scheduler_events = {
    "hourly": [
        "vending_tracker.scheduler_events.machine_health_check",
        "vending_tracker.scheduler_events.iot_synchronization",
    ],
    "daily": [
        "vending_tracker.scheduler_events.dashboard_refresh",
        "vending_tracker.scheduler_events.low_stock_detection",
        "vending_tracker.scheduler_events.revenue_summary",
        "vending_tracker.scheduler_events.daily_reports",
    ],
}

# Installation
# ------------
after_install = "vending_tracker.install.after_install"
after_migrate = "vending_tracker.install.after_migrate"
before_uninstall = "vending_tracker.uninstall.before_uninstall"

# Document Events
# ---------------
# Keep machine slot stock levels in sync with the native Stock Ledger and
# validate vending-tagged stock entries.
#
# Dashboard Chart / Dashboard Settings on_update re-run the widget repair so
# corrupted chart filters (which pop "Invalid filter: =") or a blank chart
# config ("No Data") self-heal on every save — including the module-file import
# that runs during bench migrate.
doc_events = {
    "Stock Entry": {
        "validate": "vending_tracker.utils.vending_utils.validate_vending_stock_entry",
        "on_submit": "vending_tracker.utils.vending_utils.on_vending_stock_entry_submit",
        "on_cancel": "vending_tracker.utils.vending_utils.on_vending_stock_entry_cancel",
    },
    "Dashboard Chart": {
        "on_update": "vending_tracker.install.repair_dashboard_widgets",
    },
    "Dashboard Settings": {
        "on_update": "vending_tracker.install.repair_dashboard_settings",
    },
}
