import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date = getdate(filters.get("from_date") or frappe.utils.today())
	to_date = getdate(filters.get("to_date") or frappe.utils.today())

	columns = [
		{"label": _("Machine"), "fieldname": "machine", "fieldtype": "Link", "options": "Vending Machine", "width": 150},
		{"label": _("Machine ID"), "fieldname": "machine_id", "fieldtype": "Data", "width": 110},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": _("Slots"), "fieldname": "slots", "fieldtype": "Int", "width": 70},
		{"label": _("Active Slots"), "fieldname": "active_slots", "fieldtype": "Int", "width": 100},
		{"label": _("Items Loaded"), "fieldname": "items_loaded", "fieldtype": "Int", "width": 110},
		{"label": _("Total Capacity"), "fieldname": "total_capacity", "fieldtype": "Float", "width": 120},
		{"label": _("Total Stock"), "fieldname": "total_stock", "fieldtype": "Float", "width": 110},
		{"label": _("Utilization %"), "fieldname": "utilization", "fieldtype": "Percent", "width": 110},
		{"label": _("Sales"), "fieldname": "sales", "fieldtype": "Int", "width": 80},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 130},
		{"label": _("Last Restock"), "fieldname": "last_restock", "fieldtype": "Date", "width": 110},
		{"label": _("Last Sale"), "fieldname": "last_sale", "fieldtype": "Date", "width": 100},
	]

	machine_filters = {}
	if filters.get("machine"):
		machine_filters["name"] = filters.machine

	machines = frappe.get_all(
		"Vending Machine",
		filters=machine_filters,
		fields=["name", "machine_id", "status"],
		order_by="machine_id",
	)

	slots = frappe.get_all(
		"Machine Product Slot",
		filters={"is_active": 1},
		fields=["machine", "maximum_capacity", "current_stock", "item"],
	)
	slot_map = {}
	for slot in slots:
		entry = slot_map.setdefault(
			slot.machine, {"active_slots": 0, "items": set(), "total_capacity": 0, "total_stock": 0}
		)
		entry["active_slots"] += 1
		entry["items"].add(slot.item)
		entry["total_capacity"] += flt(slot.maximum_capacity or 0)
		entry["total_stock"] += flt(slot.current_stock or 0)

	sales_data = frappe.db.sql(
		"""
		SELECT machine, COUNT(name) AS sales, SUM(amount) AS revenue, MAX(posting_date) AS last_sale
		FROM `tabVending Sales Entry`
		WHERE docstatus = 1 AND posting_date BETWEEN %(from_date)s AND %(to_date)s
		GROUP BY machine
		""",
		{"from_date": from_date, "to_date": to_date},
		as_dict=True,
	)
	sales_map = {row.machine: row for row in sales_data}

	restock_data = frappe.db.sql(
		"""
		SELECT custom_vending_machine AS machine, MAX(posting_date) AS last_restock
		FROM `tabStock Entry`
		WHERE docstatus = 1
			AND custom_is_vending_transaction = 1
			AND stock_entry_type IN ('Material Receipt', 'Material Transfer')
			AND custom_vending_machine IS NOT NULL
		GROUP BY custom_vending_machine
		"""
	)
	restock_map = {row.machine: row.last_restock for row in restock_data}

	data = []
	for machine in machines:
		slot_stats = slot_map.get(machine.name, {"active_slots": 0, "items": set(), "total_capacity": 0, "total_stock": 0})
		sales = sales_map.get(machine.name)
		capacity = flt(slot_stats["total_capacity"])
		stock = flt(slot_stats["total_stock"])

		data.append(
			{
				"machine": machine.name,
				"machine_id": machine.machine_id,
				"status": machine.status,
				"slots": frappe.db.count("Machine Product Slot", {"machine": machine.name}),
				"active_slots": slot_stats["active_slots"],
				"items_loaded": len(slot_stats["items"]),
				"total_capacity": capacity,
				"total_stock": stock,
				"utilization": round(stock * 100 / capacity, 2) if capacity else 0,
				"sales": sales.sales if sales else 0,
				"revenue": flt(sales.revenue) if sales else 0,
				"last_restock": restock_map.get(machine.name),
				"last_sale": sales.last_sale if sales else None,
			}
		)

	chart = None
	if data:
		chart = {
			"data": {
				"labels": [d["machine_id"] for d in data],
				"datasets": [{"name": _("Utilization %"), "values": [d["utilization"] for d in data]}],
			},
			"type": "bar",
		}

	return columns, data, None, chart
