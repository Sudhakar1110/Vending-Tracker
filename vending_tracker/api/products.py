import frappe
from frappe import _

from vending_tracker.api.auth import authenticate_machine
from vending_tracker.utils.vending_utils import get_selling_rate


def _product_catalog(machine=None):
	"""Active items in the Vending Products group with pricing and vending fields."""
	items = frappe.db.sql(
		"""
		SELECT
			item.name AS item_code,
			item.item_name,
			item.item_group,
			item.disabled,
			item.custom_vending_category,
			item.custom_default_reorder_threshold,
			item.custom_slot_capacity
		FROM `tabItem` item
		WHERE item.disabled = 0
		ORDER BY item.item_name
		""",
		as_dict=True,
	)
	from vending_tracker.utils.vending_utils import is_vending_item

	catalog = []
	for item in items:
		if not is_vending_item(item["item_code"]):
			continue
		item["price"] = get_selling_rate(item["item_code"])
		catalog.append(item)

	if machine:
		slot_items = frappe.get_all(
			"Machine Product Slot",
			filters={"machine": machine, "is_active": 1},
			pluck="item",
		)
		for item in catalog:
			item["assigned_to_machine"] = item["item_code"] in slot_items

	return catalog


@frappe.whitelist()
def get_products():
	"""Product Sync API (login required) — full vending catalog."""
	return _product_catalog()


@frappe.whitelist(allow_guest=True)
def sync_products(machine_id=None, token=None):
	"""Product Sync API for devices — catalog targeted at one machine."""
	name = authenticate_machine(machine_id, token)
	return {"machine": machine_id, "products": _product_catalog(machine=name)}
