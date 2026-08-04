import json
import os

import frappe

VENDING_ITEM_GROUP = "Vending Products"

# Workflow states referenced by the app's workflows (fixtures/workflow.json).
# The Workflow Document State rows are mandatory Link fields to the "Workflow
# State" master doctype, which Frappe does NOT create automatically. If these
# records are missing, clicking any workflow state (badge, table link) opens
# /app/workflow-state/{state} and 404s with "Workflow State X not found".
WORKFLOW_STATES = ["Draft", "Submitted", "Cancelled"]

# Dashboard widgets shipped by this app. A malformed `filters_json` on any of
# these makes the workspace fail with "Invalid filter: =" when the chart widget
# tries to apply it, and a missing/invalid config field leaves a chart stuck on
# "No Data". The repair below restores the values from the shipped module files.
DASHBOARD_CHART_NAMES = [
	"Revenue Trend",
	"Sales Trend",
	"Machine Performance",
	"Product Performance",
	"Stock Level Trend",
]
NUMBER_CARD_NAMES = [
	"Total Revenue",
	"Today's Revenue",
	"Monthly Revenue",
	"Active Machines",
	"Low Stock Products",
	"Pending Restocks",
]

# Canonical filters for the app's document-type charts.
#
# IMPORTANT: rows MUST include the doctype ([doctype, fieldname, condition,
# value]). Frappe v15's chart widget feeds chart filters straight into the
# workspace FilterGroup, which treats the first element as the doctype and the
# second as the fieldname. The shorthand [fieldname, condition, value] form
# therefore lands "docstatus" in the doctype slot and "=" in the fieldname
# slot, popping "Invalid filter: =" once per chart. With the full 4-element
# form the filters validate cleanly on both the frontend and the server.
DASHBOARD_CHART_FILTERS = {
	"Revenue Trend": [["Vending Sales Entry", "docstatus", "=", 1]],
	"Sales Trend": [["Vending Sales Entry", "docstatus", "=", 1]],
	"Machine Performance": [["Vending Sales Entry", "docstatus", "=", 1]],
	"Product Performance": [["Vending Sales Entry", "docstatus", "=", 1]],
	"Stock Level Trend": [["Vending Sales Entry", "docstatus", "=", 1]],
}

# Operators accepted by Frappe's filter parser.
VALID_FILTER_CONDITIONS = {
	"=", "!=", "<", ">", "<=", ">=",
	"like", "not like", "in", "not in",
	"between", "is", "is not",
	"timespan", "previous", "select", "exists",
}

# System fields that always exist on a doctype even when absent from its fields.
STANDARD_FILTER_FIELDS = {
	"name", "owner", "creation", "modified", "modified_by",
	"docstatus", "idx", "_assign", "_comments", "_liked_by",
	"_user_tags", "_seen", "_inbox",
}

# Chart config fields restored from the module files when blank, so a corrupted
# DB record (e.g. an empty group_by_based_on) can never leave a chart rendering
# "No Data".
CHART_CONFIG_FIELDS = [
	"document_type", "chart_type", "based_on", "value_based_on",
	"group_by_based_on", "group_by_type", "aggregate_function_based_on",
	"time_interval", "timespan", "number_of_groups", "type",
]


def after_install():
	"""Runs after `bench --site <site> install-app vending_tracker`.

	Creates the workflow states the app's workflows depend on, the Vending
	Products item group, configures role permissions on the reused ERPNext
	masters, and seeds optional sample data.
	"""
	create_workflow_states()
	repair_dashboard_widgets()
	create_vending_item_group()
	setup_role_permissions()
	create_sample_data()


def after_migrate():
	"""Runs on every `bench migrate`.

	Re-ensures the workflow states exist and repairs any corrupted dashboard
	chart / number card filters, so sites that installed the app before these
	records were created (or had them removed) self-heal on the next migrate.
	"""
	create_workflow_states()
	repair_dashboard_widgets()


def create_workflow_states():
	"""Create the Workflow State master records used by the app's workflows.

	Idempotent: existing records are left untouched. The records are shared
	with any other workflow on the site that uses the same state names, so they
	are never deleted on uninstall.
	"""
	for state in WORKFLOW_STATES:
		if frappe.db.exists("Workflow State", state):
			continue
		frappe.get_doc(
			{"doctype": "Workflow State", "workflow_state_name": state}
		).insert(ignore_permissions=True)


def repair_dashboard_widgets():
	"""Repair corrupted filters / config on the app's standard charts and number cards.

	Malformed ``filters_json`` (e.g. ``["="]`` or 3-element shorthand rows on
	charts) makes the workspace fail with "Invalid filter: =" popups, and a
	blank config field (e.g. ``group_by_based_on``) leaves a chart stuck on
	"No Data". Stored values are restored from the shipped module files
	whenever they are invalid or missing, and malformed per-user chart filter
	overrides are dropped from ``Dashboard Settings`` so the workspace renders
	cleanly. Idempotent and safe to run on every migrate, every widget save
	(doc_events) and every daily scheduler run.
	"""
	_repair_widget_filters("Dashboard Chart", DASHBOARD_CHART_NAMES, "dashboard_chart", is_chart=True)
	_repair_widget_filters("Number Card", NUMBER_CARD_NAMES, "number_card")
	_repair_dashboard_settings()


def _repair_widget_filters(doctype, names, folder, is_chart=False):
	"""Restore ``filters_json`` / ``dynamic_filters_json`` / config fields when corrupted."""
	for name in names:
		if not frappe.db.exists(doctype, name):
			continue
		module_doc = _module_widget_doc(folder, name)
		if module_doc is None:
			continue
		expected_filters = module_doc.get("filters_json", "[]")
		expected_dynamic = module_doc.get("dynamic_filters_json", "[]")
		document_type = frappe.db.get_value(doctype, name, "document_type")

		current_filters = frappe.db.get_value(doctype, name, "filters_json")
		if is_chart:
			# Charts need the full [doctype, fieldname, condition, value] rows
			# (see DASHBOARD_CHART_FILTERS); replace anything else.
			if not _is_valid_filter_list(current_filters, doctype=document_type, require_doctype=True):
				frappe.db.set_value(
					doctype,
					name,
					"filters_json",
					frappe.as_json(DASHBOARD_CHART_FILTERS.get(name, [])),
				)
				print(f"Vending Tracker: repaired {doctype} '{name}' filters_json")
			_restore_missing_chart_fields(name, module_doc)
		else:
			if not _is_valid_filter_list(current_filters, doctype=document_type):
				frappe.db.set_value(doctype, name, "filters_json", expected_filters)
				print(f"Vending Tracker: repaired {doctype} '{name}' filters_json")

		current_dynamic = frappe.db.get_value(doctype, name, "dynamic_filters_json")
		if current_dynamic and not _is_valid_json(current_dynamic):
			frappe.db.set_value(doctype, name, "dynamic_filters_json", expected_dynamic or "[]")
			print(f"Vending Tracker: repaired {doctype} '{name}' dynamic_filters_json")


def _restore_missing_chart_fields(name, module_doc):
	"""Fill blank chart config fields from the shipped module file."""
	for field in CHART_CONFIG_FIELDS:
		expected = module_doc.get(field)
		if expected in (None, ""):
			continue
		current = frappe.db.get_value("Dashboard Chart", name, field)
		if current in (None, ""):
			frappe.db.set_value("Dashboard Chart", name, field, expected)
			print(f"Vending Tracker: restored {field} on Dashboard Chart '{name}'")


def repair_dashboard_settings():
	"""doc_events entry point for ``Dashboard Settings`` saves."""
	_repair_dashboard_settings()


def _repair_dashboard_settings():
	"""Drop malformed per-user chart filter overrides from Dashboard Settings.

	Per-user filters are saved by the workspace FilterGroup in the full
	[doctype, fieldname, condition, value] form, so anything else (corrupted
	values, 3-element shorthand, unknown fieldnames) is dropped. Only this app's
	own charts are inspected: ``chart_config`` is shared across the whole site,
	and Report-type charts (including ones from other apps) legitimately store
	``filters`` as an object rather than a filter list.
	"""
	for name in frappe.get_all("Dashboard Settings", pluck="name"):
		value = frappe.db.get_value("Dashboard Settings", name, "chart_config")
		if not value:
			continue
		try:
			chart_config = frappe.parse_json(value)
		except Exception:
			continue
		if not isinstance(chart_config, dict):
			continue
		changed = False
		for chart_name, config in list(chart_config.items()):
			if chart_name not in DASHBOARD_CHART_NAMES:
				continue
			if not isinstance(config, dict) or "filters" not in config:
				continue
			document_type = frappe.db.get_value("Dashboard Chart", chart_name, "document_type")
			if not _is_valid_filter_list(
				config["filters"], doctype=document_type, require_doctype=True
			):
				del config["filters"]
				changed = True
		if changed:
			frappe.db.set_value(
				"Dashboard Settings", name, "chart_config", frappe.as_json(chart_config)
			)
			print(f"Vending Tracker: repaired Dashboard Settings '{name}' chart_config")


def _module_widget_doc(folder, name):
	"""Read the shipped module JSON for a dashboard widget."""
	try:
		from frappe.modules import get_module_path
	except ImportError:
		return None
	scrub = frappe.scrub(name)
	path = os.path.join(get_module_path("Vending Tracker"), folder, scrub, f"{scrub}.json")
	if not os.path.exists(path):
		return None
	with open(path) as f:
		return json.load(f)


def _is_valid_filter_list(value, doctype=None, require_doctype=False):
	"""A valid Frappe filter list for the chart widget.

	``require_doctype`` demands the full [doctype, fieldname, condition, value]
	rows the workspace FilterGroup produces (per-user chart filters and the
	app's chart ``filters_json``); otherwise the 3-element
	[fieldname, condition, value] shorthand used by number cards is accepted.
	"""
	if value is None:
		return True
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except Exception:
			return False
	if not isinstance(value, list):
		return False
	if not value:
		return True
	for row in value:
		if not _is_valid_filter_row(row, doctype=doctype, require_doctype=require_doctype):
			return False
	return True


def _is_valid_filter_row(row, doctype=None, require_doctype=False):
	"""A single filter row with a real fieldname and a known condition."""
	if not isinstance(row, (list, tuple)):
		return False
	if require_doctype:
		if len(row) < 4:
			return False
		row_doctype, fieldname, condition = row[0], row[1], row[2]
		if not isinstance(row_doctype, str) or not row_doctype:
			return False
		if doctype and row_doctype != doctype:
			return False
	else:
		if len(row) < 3:
			return False
		fieldname, condition = row[0], row[1]
	if not isinstance(fieldname, str) or not fieldname:
		return False
	if not isinstance(condition, str) or condition not in VALID_FILTER_CONDITIONS:
		return False
	if fieldname in STANDARD_FILTER_FIELDS:
		return True
	if doctype:
		try:
			if not frappe.get_meta(doctype).has_field(fieldname):
				return False
		except Exception:
			return False
	return True


def _is_valid_json(value):
	try:
		frappe.parse_json(value or "[]")
		return True
	except Exception:
		return False


def create_vending_item_group():
	"""Create the 'Vending Products' item group under 'All Item Groups'."""
	if frappe.db.exists("Item Group", VENDING_ITEM_GROUP):
		return

	root = "All Item Groups"
	if not frappe.db.exists("Item Group", root):
		# Fresh sites that haven't completed the ERPNext setup wizard may lack
		# the standard root item group; create it so the link target exists.
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": root,
				"parent_item_group": None,
				"is_group": 1,
			}
		).insert(ignore_permissions=True, ignore_mandatory=True)

	frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": VENDING_ITEM_GROUP,
			"parent_item_group": root,
			"is_group": 0,
		}
	).insert(ignore_permissions=True, ignore_mandatory=True)


def setup_role_permissions():
	"""Grant Vending roles read/write access on the ERPNext masters they reuse.

	Uses the same APIs as the Role Permission Manager (DocPerm records), so the
	permissions are visible and editable in ERPNext's UI.
	"""
	doc_perms = {
		"Vending Staff": {
			"Item": ["read"],
			"Item Price": ["read"],
			"Warehouse": ["read"],
			"Bin": ["read"],
			"Stock Entry": ["read"],
			"UOM": ["read"],
			"Address": ["read"],
			"Contact": ["read"],
		},
		"Vending Manager": {
			"Item": ["read", "write", "create"],
			"Item Price": ["read", "write", "create"],
			"Warehouse": ["read", "write"],
			"Bin": ["read"],
			"Stock Entry": ["read", "write", "create", "submit"],
			"UOM": ["read"],
			"Address": ["read"],
			"Contact": ["read"],
		},
		"Vending Administrator": {
			"Item": ["read", "write", "create", "delete"],
			"Item Price": ["read", "write", "create", "delete"],
			"Warehouse": ["read", "write", "create", "delete"],
			"Bin": ["read"],
			"Stock Entry": ["read", "write", "create", "submit", "cancel"],
			"UOM": ["read"],
			"Address": ["read", "write", "create"],
			"Contact": ["read", "write", "create"],
		},
	}

	import frappe.permissions

	for role, doc_types in doc_perms.items():
		if not frappe.db.exists("Role", role):
			continue
		for dt, perms in doc_types.items():
			if not frappe.db.exists(dt):
				continue
			if not frappe.db.exists("DocPerm", {"parent": dt, "role": role}):
				frappe.permissions.add_permission(dt, role)
			for ptype in perms:
				frappe.permissions.update_permission_property(dt, role, 0, ptype, 1)


def create_sample_data():
	"""Seed a small set of vending products, prices, one machine and its slots.

	All lookups are existence-guarded so the function is safe to re-run.
	Custom fields on Item are applied via fixtures (which may or may not have
	been synced yet when after_install runs), so they are set only when present.
	"""
	company = frappe.defaults.get_global_default("company")
	if not company:
		return

	items = [
		{"item_code": "VND-CHIPS-001", "item_name": "Classic Potato Chips", "vending_category": "Snacks", "rate": 25.0},
		{"item_code": "VND-COLA-002", "item_name": "Cola 330ml Can", "vending_category": "Beverages", "rate": 40.0},
		{"item_code": "VND-ENERGY-003", "item_name": "Energy Drink 250ml", "vending_category": "Beverages", "rate": 90.0},
		{"item_code": "VND-BAR-004", "item_name": "Chocolate Bar 50g", "vending_category": "Confectionery", "rate": 35.0},
		{"item_code": "VND-WATER-005", "item_name": "Bottled Water 500ml", "vending_category": "Beverages", "rate": 20.0},
		{"item_code": "VND-TRAIL-006", "item_name": "Trail Mix 100g", "vending_category": "Ready-to-Eat", "rate": 60.0},
	]

	has_category_field = frappe.db.exists("Custom Field", "Item-custom_vending_category")
	has_threshold_field = frappe.db.exists("Custom Field", "Item-custom_default_reorder_threshold")
	has_capacity_field = frappe.db.exists("Custom Field", "Item-custom_slot_capacity")

	created_items = []
	for it in items:
		if frappe.db.exists("Item", it["item_code"]):
			created_items.append(it["item_code"])
			continue

		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": it["item_code"],
				"item_name": it["item_name"],
				"item_group": VENDING_ITEM_GROUP,
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"is_sales_item": 1,
				"is_purchase_item": 1,
				"standard_rate": it["rate"],
			}
		)
		if has_category_field:
			item.custom_vending_category = it["vending_category"]
		if has_threshold_field:
			item.custom_default_reorder_threshold = 5
		if has_capacity_field:
			item.custom_slot_capacity = 15
		item.insert(ignore_permissions=True, ignore_mandatory=True)

		if not frappe.db.exists(
			"Item Price",
			{"item_code": item.name, "price_list": "Standard Selling", "selling": 1},
		):
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": item.name,
					"price_list": "Standard Selling",
					"price_list_rate": it["rate"],
					"selling": 1,
				}
			).insert(ignore_permissions=True)

		created_items.append(item.name)

	if frappe.db.exists("Vending Machine", "VM-00001"):
		return

	from vending_tracker.utils.vending_utils import generate_iot_token

	machine = frappe.get_doc(
		{
			"doctype": "Vending Machine",
			"machine_id": "VM-00001",
			"machine_name": "Lobby Vending Machine",
			"machine_type": "Snack",
			"status": "Active",
			"iot_enabled": 1,
			"company": company,
			"iot_token": generate_iot_token(),
		}
	)
	machine.insert(ignore_permissions=True)

	for idx, item_code in enumerate(created_items[:6], start=1):
		if frappe.db.exists(
			"Machine Product Slot",
			{"machine": machine.name, "slot_number": idx},
		):
			continue
		frappe.get_doc(
			{
				"doctype": "Machine Product Slot",
				"machine": machine.name,
				"item": item_code,
				"slot_number": idx,
				"maximum_capacity": 15,
				"reorder_threshold": 5,
			}
		).insert(ignore_permissions=True)
