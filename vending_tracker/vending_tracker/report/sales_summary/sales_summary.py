import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date = getdate(filters.get("from_date") or frappe.utils.today())
	to_date = getdate(filters.get("to_date") or frappe.utils.today())

	columns = [
		{"label": _("Machine"), "fieldname": "machine", "fieldtype": "Link", "options": "Vending Machine", "width": 150},
		{"label": _("Transactions"), "fieldname": "transactions", "fieldtype": "Int", "width": 120},
		{"label": _("Quantity Sold"), "fieldname": "quantity", "fieldtype": "Float", "width": 120},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 140},
		{"label": _("Avg Sale Value"), "fieldname": "avg_sale_value", "fieldtype": "Currency", "width": 140},
	]

	conditions = "docstatus = 1 AND posting_date BETWEEN %(from_date)s AND %(to_date)s"
	values = {"from_date": from_date, "to_date": to_date}
	if filters.get("machine"):
		conditions += " AND machine = %(machine)s"
		values["machine"] = filters.machine
	if filters.get("item"):
		conditions += " AND item = %(item)s"
		values["item"] = filters.item

	rows = frappe.db.sql(
		f"""
		SELECT machine, COUNT(name) AS transactions, SUM(quantity_sold) AS quantity, SUM(amount) AS revenue
		FROM `tabVending Sales Entry`
		WHERE {conditions}
		GROUP BY machine
		ORDER BY revenue DESC
		""",
		values,
		as_dict=True,
	)

	data = []
	for row in rows:
		row["avg_sale_value"] = flt(row.revenue) / row.transactions if row.transactions else 0
		data.append(row)

	if data:
		total = {
			"machine": _("Total"),
			"transactions": sum(d.transactions for d in data),
			"quantity": flt(sum(d.quantity for d in data)),
			"revenue": flt(sum(d.revenue for d in data)),
			"avg_sale_value": flt(sum(d.revenue for d in data)) / sum(d.transactions for d in data) if sum(d.transactions for d in data) else 0,
		}
		data.append(total)

	return columns, data
