import frappe
from collections import Counter
from frappe.utils import add_days, flt, format_date, format_datetime, nowdate

# docstatus -> (label, diagram color); pill classes map green/red to on/off.
DOC_STATUS = {
	0: ("Draft", "gray"),
	1: ("Submitted", "green"),
	2: ("Cancelled", "red"),
}
PILL_CLASS = {"green": "on", "red": "off", "gray": "gray"}

# Plain-language state names/hints for the portal's workflow guide, so a shop
# owner does not need to know docstatus numbers or role names.
FRIENDLY_STATES = {
	0: {"name": "New", "hint": "Being prepared — nothing is changed yet."},
	1: {"name": "Confirmed", "hint": "Done — stock is updated automatically."},
	2: {"name": "Cancelled", "hint": "Undone — stock goes back to how it was."},
}
FRIENDLY_TAGLINES = {
	"Vending Sales Entry": "How a sale is recorded",
	"Stock Entry": "How restocking a machine works",
}


def _roles(value):
	"""Normalize a Workflow role field to a list of role names.

	This app's fixtures store ``allowed`` / ``allow_edit`` as comma-separated
	strings, but Frappe v15 defines those fields as Table MultiSelect (a list
	of ``{"role": ...}`` rows), so accept both shapes.
	"""
	if not value:
		return []
	if isinstance(value, (list, tuple)):
		parts = [
			(r.get("role") or "") if isinstance(r, dict) else str(r)
			for r in value
		]
		value = ",".join(parts)
	return [r.strip() for r in str(value).split(",") if r.strip()]


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

	slot_map = _slot_summary()
	context.slot_summary = slot_map
	context.machines = _machines(slot_map=slot_map)
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

	# Detailed portal panels (all guarded; empty when there is no data yet).
	context.alerts = _alerts()
	context.restock_queue = _restock_queue(slot_map=slot_map)
	context.top_items = _top_items()
	context.machine_revenue = _revenue_by_machine()
	context.generated = format_datetime(frappe.utils.now_datetime())

	# Desk routes the portal cards / rows link to (Vending Machine is autonamed
	# by machine_id, so form URLs are /app/vending-machine/<machine_id>).
	context.links = {
		"machines": "/app/vending-machine",
		"active": "/app/vending-machine?status=Active",
		"slots": "/app/machine-product-slot",
		"low_stock": "/app/query-report/Low Stock Alert",
		"sales": "/app/vending-sales-entry",
		"pending_restocks": "/app/stock-entry",
	}
	context.desk_workspace_url = "/app/vending-tracker"

	# Workflow guide snapshots for the portal modal (mirrors the desk dialog).
	context.workflows = [w for w in (_workflow("Vending Sales Entry"), _workflow("Stock Entry")) if w]

	# Portal charts: 14-day revenue trend and machine status distribution.
	context.revenue_days = _revenue_trend()
	# Portal degrades when the scheduler is off or any machine is Offline/Disabled.
	context.degraded = bool(
		context.scheduler_disabled
		or any(m.get("status") in ("Offline", "Disabled") for m in context.machines)
	)
	status_counts = Counter(m.get("status") or "—" for m in context.machines)
	context.status_dist = [
		{
			"status": status,
			"count": count,
			"pill_class": {"Active": "on", "Offline": "off", "Maintenance": "warn"}.get(status, "gray"),
		}
		for status, count in status_counts.most_common()
	]
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


def _revenue_trend(days=14):
	"""Daily submitted-sales revenue for the last N days (portal chart)."""
	try:
		if not frappe.db.table_exists("Vending Sales Entry"):
			return []
		today = nowdate()
		rows = frappe.db.sql(
			"""select posting_date, ifnull(sum(amount), 0) as total
			from `tabVending Sales Entry`
			where docstatus = 1 and posting_date >= %s
			group by posting_date""",
			add_days(today, -(days - 1)),
			as_dict=True,
		)
		by_date = {str(r.posting_date): flt(r.total) for r in rows}
		peak = max(by_date.values()) if by_date else 0.0
		out = []
		for offset in range(days - 1, -1, -1):
			day = add_days(today, -offset)
			value = by_date.get(str(day), 0.0)
			out.append(
				{
					"label": format_date(day, "dd MMM"),
					"amount_label": _money(value),
					"pct": int(round(value / peak * 100)) if peak else 0,
				}
			)
		return out
	except Exception:
		return []


def _workflow(doctype):
	"""Snapshot of an active workflow for the portal's Workflow guide modal.

	Mirrors the desk dialog (vending_tracker/public/js/vending_tracker.js
	-> show_workflow_dialog); both render the live workflow config, so the two
	views stay consistent by construction.
	"""
	try:
		if not frappe.db.table_exists("Workflow"):
			return None
		name = frappe.db.get_value(
			"Workflow", {"document_type": doctype, "is_active": 1}, "name", cache=True
		)
		if not name:
			return None
		doc = frappe.get_cached_doc("Workflow", name)
		states = []
		for idx, s in enumerate(
			sorted(doc.states, key=lambda x: int(x.doc_status or 0)), start=1
		):
			status = int(s.doc_status or 0)
			label, color = DOC_STATUS.get(status, (f"DocStatus {status}", "gray"))
			friendly = FRIENDLY_STATES.get(status, {"name": s.state, "hint": ""})
			states.append(
				{
					"state": s.state,
					"doc_status": status,
					"status_label": label,
					"status_class": color,
					"pill_class": PILL_CLASS.get(color, "gray"),
					"allow_edit": ", ".join(_roles(s.allow_edit)) or "—",
					"update": f"{s.update_field} = {s.update_value}" if s.update_field else "—",
					"step": idx,
					"friendly_name": friendly["name"],
					"friendly_hint": friendly["hint"],
				}
			)
		transitions = [
			{
				"state": t.state,
				"action": t.action,
				"next_state": t.next_state,
				"roles": ", ".join(_roles(t.allowed)) or "—",
			}
			for t in doc.transitions
		]
		allowed_roles = set()
		for t in doc.transitions:
			allowed_roles.update(_roles(t.allowed))
		return {
			"workflow_name": doc.workflow_name or name,
			"document_type": doctype,
			"tagline": FRIENDLY_TAGLINES.get(doctype, ""),
			"states": states,
			"transitions": transitions,
			"allowed_roles": sorted(allowed_roles),
		}
	except Exception:
		return None


def _slot_summary():
	"""Per-machine slot counts: total (active), in stock, and low stock."""
	try:
		if not frappe.db.table_exists("Machine Product Slot"):
			return {}
		rows = frappe.db.sql(
			"""select machine,
				count(*) as total,
				sum(case when is_active = 1 then 1 else 0 end) as active,
				sum(case when is_active = 1 and ifnull(reorder_threshold, 0) > 0
					and current_stock is not null
					and current_stock <= reorder_threshold then 1 else 0 end) as low
			from `tabMachine Product Slot`
			group by machine""",
			as_dict=True,
		)
		out = {}
		for r in rows:
			active = int(r.active or 0)
			low = int(r.low or 0)
			out[r.machine] = {
				"total": int(r.total or 0),
				"active": active,
				"in_stock": max(active - low, 0),
				"low": low,
			}
		return out
	except Exception:
		return {}


def _alerts(limit=8):
	"""Most recent notification log entries for the portal alert feed."""
	try:
		if not frappe.db.table_exists("Notification Log"):
			return []
		rows = frappe.db.get_all(
			"Notification Log",
			fields=["name", "subject", "message", "type", "creation", "document_type", "document_name"],
			order_by="creation desc",
			limit=limit,
		)
		out = []
		for r in rows:
			subject = (r.subject or "").strip()
			message = (r.message or "").strip() or subject
			if len(message) > 140:
				message = message[:140].rsplit(" ", 1)[0] + "…"
			log_type = (r.type or "Alert").strip()
			out.append(
				{
					"subject": subject,
					"message": message,
					"type": log_type,
					"pill_class": "off" if log_type == "Alert" else "gray",
					"creation_label": format_datetime(r.creation) if r.creation else "—",
					"document": f"{r.document_type} {r.document_name}".strip(),
				}
			)
		return out
	except Exception:
		return []


def _restock_queue(slot_map=None, limit=6):
	"""Pending (draft) restock Stock Entries with the machine's low-slot count."""
	try:
		if not frappe.db.table_exists("Stock Entry"):
			return []
		if not frappe.db.field_exists("Stock Entry", "custom_vending_machine"):
			return []
		rows = frappe.db.get_all(
			"Stock Entry",
			filters={"docstatus": 0, "custom_vending_machine": ["!=", ""]},
			fields=["name", "posting_date", "custom_vending_machine"],
			order_by="creation desc",
			limit=limit,
		)
		slot_map = slot_map if slot_map is not None else _slot_summary()
		out = []
		for r in rows:
			machine = r.custom_vending_machine
			out.append(
				{
					"stock_entry": r.name,
					"machine": machine,
					"posting_date_label": str(r.posting_date) if r.posting_date else "—",
					"low_slots": (slot_map.get(machine) or {}).get("low", 0),
				}
			)
		return out
	except Exception:
		return []


def _top_items(limit=5):
	"""Best-selling items over the last 30 days (revenue ranked)."""
	try:
		if not frappe.db.table_exists("Vending Sales Entry"):
			return []
		rows = frappe.db.sql(
			"""select se.item, sum(se.quantity_sold) as qty, sum(se.amount) as revenue
			from `tabVending Sales Entry` se
			where se.docstatus = 1 and se.posting_date >= %s
			group by se.item order by revenue desc limit %s""",
			(add_days(nowdate(), -29), int(limit)),
			as_dict=True,
		)
		peak = max((flt(r.revenue) for r in rows), default=0.0)
		# Single batched lookup for display names (avoids N+1 queries).
		names = {}
		items = [r.item for r in rows if r.item]
		if items:
			names = {
				i.name: i.item_name
				for i in frappe.db.get_all("Item", filters={"name": ["in", items]}, fields=["name", "item_name"])
			}
		out = []
		for r in rows:
			out.append(
				{
					"item": r.item,
					"item_name": names.get(r.item) or r.item or "—",
					"qty": flt(r.qty),
					"revenue_label": _money(r.revenue),
					"pct": int(round(flt(r.revenue) / peak * 100)) if peak else 0,
				}
			)
		return out
	except Exception:
		return []


def _revenue_by_machine(limit=5):
	"""Top machines by revenue over the last 30 days."""
	try:
		if not frappe.db.table_exists("Vending Sales Entry"):
			return []
		rows = frappe.db.sql(
			"""select se.machine, sum(se.amount) as revenue
			from `tabVending Sales Entry` se
			where se.docstatus = 1 and se.posting_date >= %s
			group by se.machine order by revenue desc limit %s""",
			(add_days(nowdate(), -29), int(limit)),
			as_dict=True,
		)
		peak = max((flt(r.revenue) for r in rows), default=0.0)
		out = []
		for r in rows:
			out.append(
				{
					"machine": r.machine,
					"revenue_label": _money(r.revenue),
					"pct": int(round(flt(r.revenue) / peak * 100)) if peak else 0,
				}
			)
		return out
	except Exception:
		return []


def _machines(slot_map=None):
	try:
		if not frappe.db.table_exists("Vending Machine"):
			return []
		rows = frappe.db.get_all(
			"Vending Machine",
			fields=[
				"name",
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
			row["desk_url"] = f"/app/vending-machine/{row.get('name') or row.get('machine_id')}"
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
			# Battery / temperature are only written by the IoT heartbeat API, so
			# they mean nothing until a machine has actually reported. Machines
			# without a heartbeat still carry the DB default of 0 — treat that as
			# "not reported" (—) instead of a real 0% / 0.0 °C reading.
			reported = bool(row.get("last_heartbeat"))
			# Battery (Percent) — color-coded for monitoring at a glance:
			# green >= 50%, amber 20–49%, red < 20%.
			if reported and row.get("battery_level") is not None:
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
				f"{flt(temperature):.1f} °C" if reported and temperature is not None else "—"
			)
			api_status = row.get("last_api_status")
			row["api_status_label"] = api_status or "—"
			row["api_status_class"] = {"Success": "on", "Failed": "off"}.get(api_status, "gray")
			# Slot inventory summary for this machine (total / in stock / low).
			slots = (slot_map or {}).get(row.get("name")) or {}
			row["slot_total"] = slots.get("active", 0)
			row["slot_in_stock"] = slots.get("in_stock", 0)
			row["slot_low"] = slots.get("low", 0)
			# Heartbeat staleness: show "5 min ago" / "2 days ago", and flag a
			# machine as stale when it last reported more than a day ago.
			if row.get("last_heartbeat"):
				try:
					# Imported locally so an odd Frappe build can never take the
					# public page down with an ImportError at module load.
					from frappe.utils import time_ago

					row["heartbeat_ago"] = time_ago(row["last_heartbeat"])
					stale = (frappe.utils.now_datetime() - row["last_heartbeat"]).days >= 1
				except Exception:
					row["heartbeat_ago"] = row.get("last_heartbeat_label")
					stale = False
				row["heartbeat_class"] = "warn" if stale else "on"
			else:
				row["heartbeat_ago"] = None
				row["heartbeat_class"] = "off"
		return rows
	except Exception:
		return []
