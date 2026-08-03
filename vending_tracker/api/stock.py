import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from vending_tracker.api.auth import authenticate_machine
from vending_tracker.utils.vending_utils import (
	get_bin_qty,
	get_machine_warehouse,
	get_stock_status,
	update_slot_stock,
)


@frappe.whitelist(allow_guest=True)
def sync_stock(machine_id=None, token=None, stock=None):
	"""Stock Sync API.

	Reconciles device-reported actual stock counts against the machine
	warehouse. Any difference is applied through a native ERPNext Stock Entry
	(Material Receipt for surplus, Material Issue for shortage) so the Stock
	Ledger stays the single source of truth.

	``stock`` is a list of dicts: {"item": "VND-COLA-002", "quantity": 12}
	"""
	name = authenticate_machine(machine_id, token)
	warehouse = get_machine_warehouse(name)
	if not warehouse:
		frappe.throw(_("Machine has no linked warehouse."))

	if not isinstance(stock, list):
		frappe.throw(_("stock must be a list"))

	applied = []
	skipped = []
	for idx, entry in enumerate(stock, start=1):
		if not isinstance(entry, dict):
			skipped.append({"row": idx, "error": "not a dict"})
			continue
		item = entry.get("item") or entry.get("item_code")
		reported = flt(entry.get("quantity") or 0)
		if not item:
			skipped.append({"row": idx, "error": "item missing"})
			continue

		current = get_bin_qty(item, warehouse)
		delta = flt(reported - current)
		if abs(delta) < 0.0001:
			skipped.append({"row": idx, "item": item, "delta": 0})
			continue

		try:
			se = frappe.new_doc("Stock Entry")
			se.stock_entry_type = "Material Receipt" if delta > 0 else "Material Issue"
			se.company = frappe.db.get_value("Vending Machine", name, "company") or frappe.defaults.get_global_default("company")
			se.posting_date = frappe.utils.today()
			se.posting_time = now_datetime().strftime("%H:%M:%S")
			se.remarks = _("IoT stock sync for machine {0} ({1} {2} units)").format(
				machine_id, item, delta
			)
			se.custom_vending_machine = name
			se.custom_is_vending_transaction = 1
			se.custom_vending_source_document = "IoT"

			item_row = {
				"item_code": item,
				"qty": abs(delta),
				"uom": frappe.db.get_value("Item", item, "stock_uom"),
				"allow_zero_valuation_rate": 1,
			}
			if delta > 0:
				item_row["t_warehouse"] = warehouse
			else:
				item_row["s_warehouse"] = warehouse
			se.append("items", item_row)

			se.flags.ignore_permissions = True
			se.insert()
			se.submit()
			applied.append({"item": item, "delta": delta, "stock_entry": se.name})
		except Exception as exc:
			skipped.append({"row": idx, "item": item, "error": str(exc)})

	update_slot_stock(machine=name)

	return {
		"machine": machine_id,
		"warehouse": warehouse,
		"applied": applied,
		"skipped": skipped,
	}


@frappe.whitelist(allow_guest=True)
def get_inventory(machine_id=None, token=None):
	"""Inventory Lookup API — slot-wise stock snapshot for the machine."""
	name = authenticate_machine(machine_id, token)
	warehouse = get_machine_warehouse(name)

	slots = frappe.get_all(
		"Machine Product Slot",
		filters={"machine": name, "is_active": 1},
		fields=["name", "item", "slot_number", "current_stock", "maximum_capacity", "reorder_threshold", "stock_status"],
		order_by="slot_number",
	)
	for slot in slots:
		slot["warehouse"] = warehouse
		slot["bin_actual_qty"] = get_bin_qty(slot["item"], warehouse) if warehouse else 0
		slot["item_name"] = frappe.db.get_value("Item", slot["item"], "item_name") or ""

	return {"machine": machine_id, "warehouse": warehouse, "slots": slots}


@frappe.whitelist()
def get_slot_stock(slot):
	"""Refresh a single slot's cached stock from Bin (used by client scripts)."""
	doc = frappe.get_doc("Machine Product Slot", slot)
	warehouse = get_machine_warehouse(doc.machine)
	qty = get_bin_qty(doc.item, warehouse) if warehouse else 0
	status = get_stock_status(qty, doc.maximum_capacity, doc.reorder_threshold)
	frappe.db.set_value(
		"Machine Product Slot",
		slot,
		{"current_stock": qty, "stock_status": status},
		update_modified=False,
	)
	return {"current_stock": qty, "stock_status": status, "warehouse": warehouse}
