import frappe
from frappe import _

from vending_tracker.api.auth import authenticate_machine
from vending_tracker.utils.vending_utils import (
	generate_iot_token,
	# Aliased so the whitelisted API endpoint below (same name) does not shadow
	# this helper — otherwise the endpoint would recurse into itself.
	get_machine_warehouse as get_machine_linked_warehouse,
	log_machine_health,
)


def _require_vending_admin():
	roles = frappe.get_roles()
	if not ({"Vending Administrator", "System Manager", "Administrator"} & set(roles)):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def register(
	machine_id=None,
	machine_name=None,
	machine_type="Snack",
	status="Active",
	company=None,
	location=None,
	iot_enabled=0,
	api_endpoint=None,
):
	"""Machine Registration API.

	Creates (or updates) a Vending Machine and returns its IoT token. Requires a
	logged-in user with the Vending Administrator / System Manager role.
	"""
	_require_vending_admin()
	if not machine_id:
		frappe.throw(_("machine_id is required"))

	existing = frappe.db.get_value("Vending Machine", {"machine_id": machine_id}, "name")
	if existing:
		doc = frappe.get_doc("Vending Machine", existing)
	else:
		doc = frappe.new_doc("Vending Machine")
		doc.machine_id = machine_id

	doc.machine_name = machine_name or doc.machine_name or machine_id
	doc.machine_type = machine_type or doc.machine_type or "Snack"
	doc.status = status or doc.status or "Active"
	doc.company = company or doc.company
	doc.location = location or doc.location
	doc.iot_enabled = 1 if iot_enabled in (1, "1", True) else doc.iot_enabled
	doc.api_endpoint = api_endpoint or doc.api_endpoint

	if doc.iot_enabled and not doc.iot_token:
		doc.iot_token = generate_iot_token()

	doc.flags.ignore_permissions = True
	doc.save()

	return {
		"name": doc.name,
		"machine_id": doc.machine_id,
		"machine_name": doc.machine_name,
		"status": doc.status,
		"iot_token": doc.iot_token,
		"linked_warehouse": doc.linked_warehouse,
	}


@frappe.whitelist(allow_guest=True)
def heartbeat(machine_id=None, token=None, battery_level=None, temperature=None, error_message=None):
	"""Machine Heartbeat API.

	Device-authenticated. Updates the machine's online status and monitoring
	fields, and records a health log. Bringing a machine back online clears the
	Offline status.
	"""
	name = authenticate_machine(machine_id, token)

	doc = frappe.get_doc("Vending Machine", name)
	was_online = doc.is_online

	doc.is_online = 1
	doc.last_heartbeat = frappe.utils.now_datetime()
	if battery_level is not None:
		doc.battery_level = battery_level
	if temperature is not None:
		doc.temperature = temperature
	if doc.status == "Offline":
		doc.status = "Active"
	doc.flags.ignore_permissions = True
	doc.save()

	log_machine_health(
		name,
		status="Online" if doc.is_online else doc.status,
		is_online=1,
		source="Heartbeat",
		error_message=error_message,
	)

	return {
		"status": "ok",
		"machine": doc.machine_id,
		"is_online": doc.is_online,
		"last_heartbeat": doc.last_heartbeat,
		"state_change": bool(not was_online and doc.is_online),
	}


@frappe.whitelist(allow_guest=True)
def get_status(machine_id=None, token=None):
	"""IoT Machine Status API — snapshot for a vending machine UI.

	Returns machine state plus per-slot inventory (item, stock, capacity,
	threshold, selling price).
	"""
	name = authenticate_machine(machine_id, token)
	doc = frappe.get_doc("Vending Machine", name)

	slots = frappe.get_all(
		"Machine Product Slot",
		filters={"machine": name, "is_active": 1},
		fields=["name", "item", "slot_number", "current_stock", "maximum_capacity", "reorder_threshold", "stock_status"],
		order_by="slot_number",
	)
	from vending_tracker.utils.vending_utils import get_selling_rate

	for slot in slots:
		slot["price"] = get_selling_rate(slot["item"])

	return {
		"machine_id": doc.machine_id,
		"machine_name": doc.machine_name,
		"status": doc.status,
		"is_online": doc.is_online,
		"warehouse": doc.linked_warehouse,
		"last_heartbeat": doc.last_heartbeat,
		"battery_level": doc.battery_level,
		"temperature": doc.temperature,
		"slots": slots,
	}


@frappe.whitelist()
def list_machines():
	"""List machines and their online/stock state (requires login)."""
	_require_vending_admin()
	machines = frappe.get_all(
		"Vending Machine",
		fields=["name", "machine_id", "machine_name", "status", "is_online", "linked_warehouse", "iot_enabled"],
		order_by="machine_id",
	)
	for machine in machines:
		machine["low_stock_count"] = frappe.db.count(
			"Machine Product Slot",
			{"machine": machine.name, "is_active": 1, "stock_status": ["in", ["Low Stock", "Out of Stock"]]},
		)
	return machines


@frappe.whitelist()
def regenerate_token(machine):
	"""Rotate a machine's IoT token (Vending Administrator / System Manager)."""
	_require_vending_admin()
	doc = frappe.get_doc("Vending Machine", machine)
	doc.iot_token = generate_iot_token()
	doc.flags.ignore_permissions = True
	doc.save()
	return doc.iot_token


@frappe.whitelist()
def get_machine_warehouse(machine):
	"""Return the linked warehouse of a machine (used by client scripts)."""
	return get_machine_linked_warehouse(machine)


@frappe.whitelist()
def get_machine_summary(machine):
	"""Small status summary for a machine (used by client scripts)."""
	if not frappe.db.exists("Vending Machine", machine):
		frappe.throw(_("Vending Machine not found"))
	doc = frappe.get_doc("Vending Machine", machine)
	return {
		"is_online": doc.is_online,
		"status": doc.status,
		"last_heartbeat": doc.last_heartbeat,
		"low_stock_count": frappe.db.count(
			"Machine Product Slot",
			{
				"machine": machine,
				"is_active": 1,
				"stock_status": ["in", ["Low Stock", "Out of Stock"]],
			},
		),
	}


@frappe.whitelist()
def test_connection(machine):
	"""Try reaching the machine's configured API endpoint (requires login)."""
	doc = frappe.get_doc("Vending Machine", machine)
	if not doc.api_endpoint:
		frappe.throw(_("No API endpoint configured for this machine."))

	from requests import get as requests_get

	url = doc.api_endpoint
	sep = "&" if "?" in url else "?"
	url = f"{url}{sep}machine_id={doc.machine_id}&token={doc.iot_token}"
	try:
		response = requests_get(url, timeout=10)
		response.raise_for_status()
		return _("Connection successful. Response: {0}").format(response.text[:200])
	except Exception as exc:
		frappe.throw(_("Connection failed: {0}").format(exc))
