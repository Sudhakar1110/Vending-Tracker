import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"label": _("Machine"), "fieldname": "machine", "fieldtype": "Link", "options": "Vending Machine", "width": 140},
		{"label": _("Machine ID"), "fieldname": "machine_id", "fieldtype": "Data", "width": 110},
		{"label": _("Slot"), "fieldname": "slot_number", "fieldtype": "Int", "width": 70},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 190},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 170},
		{"label": _("Current Stock"), "fieldname": "current_stock", "fieldtype": "Float", "width": 110},
		{"label": _("Maximum Capacity"), "fieldname": "maximum_capacity", "fieldtype": "Int", "width": 140},
		{"label": _("Reorder Threshold"), "fieldname": "reorder_threshold", "fieldtype": "Float", "width": 140},
		{"label": _("Stock Status"), "fieldname": "stock_status", "fieldtype": "Data", "width": 110},
		{"label": _("Stock Value"), "fieldname": "stock_value", "fieldtype": "Currency", "width": 120},
	]

	conditions = {"is_active": 1}
	if filters.get("machine"):
		conditions["machine"] = filters.machine

	slots = frappe.get_all(
		"Machine Product Slot",
		filters=conditions,
		fields=["machine", "item", "slot_number", "maximum_capacity", "reorder_threshold", "current_stock", "stock_status"],
		order_by="machine, slot_number",
	)

	data = []
	for slot in slots:
		machine_id = frappe.db.get_value("Vending Machine", slot.machine, "machine_id") or slot.machine
		item_name = frappe.db.get_value("Item", slot.item, "item_name") or slot.item
		warehouse = frappe.db.get_value("Vending Machine", slot.machine, "linked_warehouse")
		valuation = flt(
			frappe.db.get_value("Item", slot.item, "valuation_rate")
			or frappe.db.get_value("Item Price", {"item_code": slot.item, "selling": 1}, "price_list_rate")
			or 0
		)

		data.append(
			{
				"machine": slot.machine,
				"machine_id": machine_id,
				"slot_number": slot.slot_number or 0,
				"item": slot.item,
				"item_name": item_name,
				"warehouse": warehouse or "",
				"current_stock": flt(slot.current_stock or 0),
				"maximum_capacity": slot.maximum_capacity or 0,
				"reorder_threshold": flt(slot.reorder_threshold or 0),
				"stock_status": slot.stock_status or "Out of Stock",
				"stock_value": flt(slot.current_stock or 0) * valuation,
			}
		)

	return columns, data
