import frappe
from frappe.utils import flt, format_datetime, nowdate


def get_context(context):
	"""Site health / status page for monitoring endpoints.

	Kept cheap and defensive: every stat is guarded, so a missing table or a
	renamed field can never take the page down.
	"""
	context.no_cache = 1
	context.site = frappe.local.site
	context.app_version = _app_version("frappe")
	context.erpnext_version = _app_version("erpnext")
	context.tracker_version = _app_version("vending_tracker")
	context.installed_apps = ", ".join(frappe.get_installed_apps())

	context.machines = _machines()
	context.machine_count = len(context.machines)
	# Operational status, not IoT heartbeat: a machine without IoT integration
	# (iot_enabled = 0) is perfectly functional and should not read as offline.
	context.active_count = _safe_count("Vending Machine", {"status": "Active"})
	context.slot_count = _safe_count("Machine Product Slot")
	context.low_stock_count = _low_stock_count()
	context.sales_count = _safe_count("Vending Sales Entry", {"docstatus": 1})
	context.todays_revenue_label = _money(_revenue(from_date=nowdate()))
	context.total_revenue_label = _money(_revenue())
	context.pending_restocks = _pending_restocks()
	context.scheduler_disabled = _scheduler_disabled()
	context.generated = format_datetime(frappe.utils.now_datetime())
	return context


def _app_version(app):
	"""Best-effort version string for an installed app.

	``frappe.get_hooks()`` returns hook values as a *list* (e.g. ``['15.100.1']``),
	so the first element is used; apps without an ``app_version`` hook fall back
	to their module ``__version__``.
	"""
	try:
		values = frappe.get_hooks("app_version", app_name=app) or []
		if values:
			return values[0]
		return getattr(frappe.get_module(app), "__version__", None) or None
	except Exception:
		return None


def _safe_count(doctype, filters=None):
	try:
		if not frappe.db.table_exists(doctype):
			return 0
		return frappe.db.count(doctype, filters or {})
	except Exception:
		return 0


def _low_stock_count():
	"""Slots whose known stock is at or below their reorder threshold."""
	try:
		if not frappe.db.table_exists("Machine Product Slot"):
			return 0
		return (
			frappe.db.sql(
				"""select count(*) from `tabMachine Product Slot`
				where ifnull(reorder_threshold, 0) > 0
					and current_stock is not null
					and current_stock <= reorder_threshold"""
			)[0][0]
			or 0
		)
	except Exception:
		return 0


def _revenue(from_date=None):
	try:
		if not frappe.db.table_exists("Vending Sales Entry"):
			return 0.0
		if from_date:
			value = frappe.db.sql(
				"""select ifnull(sum(amount), 0) from `tabVending Sales Entry`
				where docstatus = 1 and posting_date = %s""",
				from_date,
			)[0][0]
		else:
			value = frappe.db.sql(
				"""select ifnull(sum(amount), 0) from `tabVending Sales Entry`
				where docstatus = 1"""
			)[0][0]
		return flt(value)
	except Exception:
		return 0.0


def _money(value):
	try:
		from frappe.utils import fmt_money

		return fmt_money(flt(value))
	except Exception:
		return f"{flt(value):,.2f}"


def _pending_restocks():
	"""Draft Stock Entries tagged with a vending machine."""
	try:
		if not frappe.db.table_exists("Stock Entry"):
			return 0
		if not frappe.db.field_exists("Stock Entry", "custom_vending_machine"):
			return 0
		return frappe.db.count(
			"Stock Entry", {"docstatus": 0, "custom_vending_machine": ["!=", ""]}
		)
	except Exception:
		return 0


def _scheduler_disabled():
	try:
		from frappe.utils.scheduler import is_scheduler_disabled

		return is_scheduler_disabled()
	except Exception:
		return None


def _machines():
	try:
		if not frappe.db.table_exists("Vending Machine"):
			return []
		rows = frappe.db.get_all(
			"Vending Machine",
			fields=[
				"machine_id",
				"machine_name",
				"machine_type",
				"status",
				"is_online",
				"iot_enabled",
				"battery_level",
				"temperature",
				"last_api_status",
				"location",
				"linked_warehouse",
				"last_heartbeat",
			],
			order_by="machine_id",
		)
		status_class = {
			"Active": "on",
			"Offline": "off",
			"Maintenance": "warn",
			"Disabled": "gray",
		}
		for row in rows:
			row["last_heartbeat_label"] = (
				format_datetime(row.get("last_heartbeat"))
				if row.get("last_heartbeat")
				else "—"
			)
			# Operational status (the primary health signal) drives the pill color.
			row["status_class"] = status_class.get(row.get("status"), "gray")
			# IoT connectivity is only meaningful for IoT-enabled machines.
			if row.get("iot_enabled"):
				row["iot_label"] = "Online" if row.get("is_online") else "Offline"
				row["iot_class"] = "on" if row.get("is_online") else "off"
			else:
				row["iot_label"] = "Disabled"
				row["iot_class"] = "gray"
			# Battery (Percent) — color-coded for monitoring at a glance:
			# green >= 50%, amber 20–49%, red < 20%.
			if row.get("battery_level") is not None:
				battery = flt(row.get("battery_level"))
				row["battery_pct"] = battery
				row["battery_label"] = f"{battery:.0f}%"
				row["battery_class"] = "on" if battery >= 50 else ("warn" if battery >= 20 else "off")
			else:
				row["battery_pct"] = None
				row["battery_label"] = "—"
				row["battery_class"] = "gray"
			temperature = row.get("temperature")
			row["temperature_label"] = (
				f"{flt(temperature):.1f} °C" if temperature is not None else "—"
			)
			api_status = row.get("last_api_status")
			row["api_status_label"] = api_status or "—"
			row["api_status_class"] = {"Success": "on", "Failed": "off"}.get(api_status, "gray")
		return rows
	except Exception:
		return []
