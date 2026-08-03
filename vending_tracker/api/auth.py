import frappe
from frappe import _


def authenticate_machine(machine_id, token):
	"""Device-level authentication for IoT endpoints.

	Validates a machine against its stored IoT token. Raises an authentication
	error when the machine or token is invalid, or when the machine is disabled.
	"""
	if not machine_id or not token:
		frappe.throw(_("machine_id and token are required"), frappe.AuthenticationError)

	machine = frappe.db.get_value(
		"Vending Machine",
		{"machine_id": machine_id, "iot_token": token},
		["name", "status"],
		as_dict=True,
	)
	if not machine:
		frappe.throw(_("Invalid machine credentials"), frappe.AuthenticationError)
	if machine.status == "Disabled":
		frappe.throw(_("Machine is disabled"), frappe.ValidationError)
	return machine.name


@frappe.whitelist(allow_guest=True)
def ping():
	"""Connectivity check for IoT devices and monitoring."""
	return {"status": "ok", "app": "vending_tracker", "server_time": frappe.utils.now_datetime()}
