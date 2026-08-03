import frappe
from frappe import _
from frappe.utils import flt, getdate


def _location_label(address):
	if not address:
		return _("Not Set")
	title = frappe.db.get_value("Address", address, "address_title") or ""
	city = frappe.db.get_value("Address", address, "city") or ""
	parts = [p for p in (title, city) if p]
	return parts[0] if len(parts) == 1 else f"{parts[0]} ({parts[1]})" if parts else address


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date = getdate(filters.get("from_date") or frappe.utils.today())
	to_date = getdate(filters.get("to_date") or frappe.utils.today())

	columns = [
		{"label": _("Location"), "fieldname": "location", "fieldtype": "Data", "width": 200},
		{"label": _("Machines"), "fieldname": "machines", "fieldtype": "Int", "width": 100},
		{"label": _("Transactions"), "fieldname": "transactions", "fieldtype": "Int", "width": 120},
		{"label": _("Quantity Sold"), "fieldname": "quantity", "fieldtype": "Float", "width": 120},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 140},
	]

	conditions = "docstatus = 1 AND posting_date BETWEEN %(from_date)s AND %(to_date)s"
	values = {"from_date": from_date, "to_date": to_date}
	if filters.get("machine"):
		conditions += " AND machine = %(machine)s"
		values["machine"] = filters.machine

	rows = frappe.db.sql(
		f"""
		SELECT
			se.machine,
			COUNT(se.name) AS transactions,
			SUM(se.quantity_sold) AS quantity,
			SUM(se.amount) AS revenue
		FROM `tabVending Sales Entry` se
		WHERE {conditions}
		GROUP BY se.machine
		""",
		values,
		as_dict=True,
	)

	by_location = {}
	for row in rows:
		location = frappe.db.get_value("Vending Machine", row.machine, "location")
		key = _location_label(location)
		entry = by_location.setdefault(
			key,
			{"location": key, "machines": set(), "transactions": 0, "quantity": 0, "revenue": 0},
		)
		entry["machines"].add(row.machine)
		entry["transactions"] += row.transactions
		entry["quantity"] += flt(row.quantity)
		entry["revenue"] += flt(row.revenue)

	data = []
	for entry in by_location.values():
		entry["machines"] = len(entry["machines"])
		data.append(entry)

	data.sort(key=lambda d: d["revenue"], reverse=True)

	chart = None
	if data:
		chart = {
			"data": {
				"labels": [d["location"] for d in data],
				"datasets": [{"name": _("Revenue"), "values": [d["revenue"] for d in data]}],
			},
			"type": "bar",
		}

	return columns, data, None, chart
