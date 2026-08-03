import frappe


def get_context(context):
	"""Simple site health page for monitoring endpoints."""
	context.no_cache = 1
	context.app_version = frappe.get_hooks("app_version") or frappe.__version__
	context.site = frappe.local.site
	context.machine_count = frappe.db.count("Vending Machine") if frappe.db.table_exists("Vending Machine") else 0
	return context
