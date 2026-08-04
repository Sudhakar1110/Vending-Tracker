import frappe

VENDING_ITEM_GROUP = "Vending Products"

# Workflow states referenced by the app's workflows (fixtures/workflow.json).
# The Workflow Document State rows are mandatory Link fields to the "Workflow
# State" master doctype, which Frappe does NOT create automatically. If these
# records are missing, clicking any workflow state (badge, table link) opens
# /app/workflow-state/{state} and 404s with "Workflow State X not found".
WORKFLOW_STATES = ["Draft", "Submitted", "Cancelled"]


def after_install():
	"""Runs after `bench --site <site> install-app vending_tracker`.

	Creates the workflow states the app's workflows depend on, the Vending
	Products item group, configures role permissions on the reused ERPNext
	masters, and seeds optional sample data.
	"""
	create_workflow_states()
	create_vending_item_group()
	setup_role_permissions()
	create_sample_data()


def after_migrate():
	"""Runs on every `bench migrate`.

	Re-ensures the workflow states exist so sites that installed the app before
	they were created (or had them removed) self-heal on the next migrate.
	"""
	create_workflow_states()


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
