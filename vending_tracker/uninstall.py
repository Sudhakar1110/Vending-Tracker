import frappe


def before_uninstall():
	"""Remove app-created customizations on the reused ERPNext doctypes.

	Custom doctypes, reports, workspaces, charts and number cards belonging to
	the app module are removed automatically by `bench uninstall-app`; this
	function cleans up the fixtures attached to standard ERPNext doctypes.
	"""
	delete_custom_fields()
	delete_property_setters()
	delete_client_scripts()
	delete_server_scripts()
	delete_notifications()
	delete_workflows()
	delete_print_formats()
	delete_roles()


def _delete_docs(doctype, names, label):
	for name in names:
		try:
			frappe.delete_doc(doctype, name, force=True)
		except Exception:
			frappe.log_error(
				message=f"Failed to delete {doctype} {name}",
				title=f"Vending Tracker uninstall ({label})",
			)


def delete_custom_fields():
	# The fixture custom fields do not carry a module, so match by the
	# {doctype}-custom_* name pattern the fixtures use.
	names = frappe.get_all(
		"Custom Field",
		filters=[
			["name", "like", "Item-custom_%"],
			["name", "like", "Stock Entry-custom_%"],
		],
		pluck="name",
	)
	_delete_docs("Custom Field", names, "custom fields")


def delete_property_setters():
	names = [
		"Item-custom_vending_category-in_list_view",
		"Item-custom_default_reorder_threshold-in_list_view",
	]
	_delete_docs("Property Setter", names, "property setters")


def delete_client_scripts():
	names = ["Stock Entry - Vending Restock", "Vending Machine - IoT Monitor"]
	_delete_docs("Client Script", names, "client scripts")


def delete_server_scripts():
	names = ["Vending_Machine_Status", "Vending_Low_Stock_Check"]
	_delete_docs("Server Script", names, "server scripts")


def delete_notifications():
	names = [
		"Low Stock",
		"Machine Offline",
		"Maintenance Due",
		"Restock Completed",
		"High Sales",
		"Machine Disabled",
		"API Failure",
		"IoT Sync Failure",
	]
	_delete_docs("Notification", names, "notifications")


def delete_workflows():
	names = ["Vending Sales Entry Workflow", "Vending Restock Workflow"]
	_delete_docs("Workflow", names, "workflows")


def delete_print_formats():
	names = [
		"Vending Sales Entry",
		"Vending Restock Entry",
		"Vending Machine Inventory",
		"Vending Daily Sales Report",
	]
	_delete_docs("Print Format", names, "print formats")


def delete_roles():
	for role in ["Vending Staff", "Vending Manager", "Vending Administrator"]:
		assigned = frappe.db.count("Has Role", {"role": role})
		if assigned:
			continue
		try:
			frappe.delete_doc("Role", role, force=True)
		except Exception:
			frappe.log_error(
				message=f"Failed to delete Role {role}",
				title="Vending Tracker uninstall (roles)",
			)
