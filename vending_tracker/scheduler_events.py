import frappe
from frappe import _
from frappe.utils import add_to_date, flt, now_datetime, today


def machine_health_check():
	"""Mark IoT machines offline when their heartbeat is stale.

	Persists via a normal save so the "Machine Offline" value-change
	notification fires automatically, and logs a health record.
	"""
	settings = frappe.get_single("Vending Tracker Settings")
	minutes = flt(settings.offline_after_minutes or 30) or 30
	cutoff = add_to_date(now_datetime(), minutes=-minutes)

	machines = frappe.get_all(
		"Vending Machine", filters={"iot_enabled": 1, "is_online": 1}, pluck="name"
	)
	for name in machines:
		last_heartbeat = frappe.db.get_value("Vending Machine", name, "last_heartbeat")
		if last_heartbeat and last_heartbeat >= cutoff:
			continue

		doc = frappe.get_doc("Vending Machine", name)
		doc.is_online = 0
		if doc.status == "Active":
			doc.status = "Offline"
		doc.save(ignore_permissions=True)

		from vending_tracker.utils.vending_utils import log_machine_health

		log_machine_health(
			doc.name,
			status="Offline",
			is_online=0,
			source="Health Check",
			error_message=_("No heartbeat received in the last {0} minutes.").format(minutes),
		)
		frappe.db.commit()


def iot_synchronization():
	"""Server-initiated IoT poll.

	For every online IoT machine with an API endpoint configured, this job calls
	the endpoint (passing the machine token) to pull status / sync inventory and
	records the outcome. Failures flip ``last_api_status`` so the "API Failure"
	notification fires, and log a health record.
	"""
	settings = frappe.get_single("Vending Tracker Settings")
	if not settings.iot_sync_enabled:
		return

	machines = frappe.get_all(
		"Vending Machine",
		filters={
			"iot_enabled": 1,
			"is_online": 1,
			"api_endpoint": ["!=", ""],
		},
		pluck="name",
	)
	for name in machines:
		doc = frappe.get_doc("Vending Machine", name)
		url = doc.api_endpoint
		sep = "&" if "?" in url else "?"
		url = f"{url}{sep}machine_id={doc.machine_id}&token={doc.iot_token}"

		try:
			import requests

			response = requests.get(url, timeout=15)
			response.raise_for_status()
			try:
				payload = response.json()
			except ValueError:
				payload = response.text

			doc.last_api_status = "Success"
			doc.last_sync_status = "Success" if isinstance(payload, dict) else doc.last_sync_status
			doc.save(ignore_permissions=True)

			from vending_tracker.utils.vending_utils import log_machine_health

			log_machine_health(doc.name, status=doc.status, source="API")
		except Exception as exc:
			doc.last_api_status = "Failed"
			doc.save(ignore_permissions=True)

			from vending_tracker.utils.vending_utils import log_machine_health

			log_machine_health(
				doc.name,
				status=doc.status,
				source="API",
				error_message=f"{type(exc).__name__}: {exc}",
			)
		frappe.db.commit()


def low_stock_detection():
	"""Reconcile slot stock and notify managers of slots below reorder level.

	Each slot is notified at most once per depletion cycle (tracked by the
	``low_stock_notified`` flag), so managers are not spammed on every run.
	"""
	settings = frappe.get_single("Vending Tracker Settings")
	if not settings.low_stock_enabled:
		return

	from vending_tracker.utils.vending_utils import notify_low_stock

	slots = frappe.get_all(
		"Machine Product Slot",
		filters={"is_active": 1},
		fields=["name", "machine", "item", "current_stock", "reorder_threshold", "low_stock_notified"],
	)
	for slot in slots:
		current = flt(slot.current_stock or 0)
		threshold = flt(slot.reorder_threshold or 0)
		if threshold > 0 and current <= threshold and not slot.low_stock_notified:
			notify_low_stock(slot)
			frappe.db.set_value("Machine Product Slot", slot.name, "low_stock_notified", 1)
		elif current > threshold and slot.low_stock_notified:
			frappe.db.set_value("Machine Product Slot", slot.name, "low_stock_notified", 0)

	frappe.db.commit()


def dashboard_refresh():
	"""Reconcile every slot's cached stock level from the Stock Ledger (Bin).

	Also re-runs the dashboard widget repair, so corrupted chart filters (which
	pop "Invalid filter: =") or a blank chart config ("No Data") self-heal
	every day even if a migrate was never run.
	"""
	from vending_tracker.install import repair_dashboard_widgets
	from vending_tracker.utils.vending_utils import sync_all_slot_stock

	repair_dashboard_widgets()
	sync_all_slot_stock()
	frappe.db.commit()


def revenue_summary():
	"""Email a monthly revenue summary to Vending Administrators on the 1st."""
	if not today().endswith("-01"):
		return

	from vending_tracker.utils.vending_utils import get_monthly_revenue_summary, send_email_to_role

	message = get_monthly_revenue_summary()
	if message:
		send_email_to_role(
			subject=_("Vending Revenue Summary - {0}").format(today()),
			message=message,
			role="Vending Administrator",
		)


def daily_reports():
	"""Email yesterday's Daily Sales and Low Stock summary to Vending Managers."""
	from vending_tracker.utils.vending_utils import get_daily_sales_summary, send_email_to_role

	message = get_daily_sales_summary()
	if message:
		send_email_to_role(
			subject=_("Vending Daily Sales Report - {0}").format(today()),
			message=message,
			role="Vending Manager",
		)
