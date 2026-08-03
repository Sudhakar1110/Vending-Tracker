import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date = getdate(filters.get("from_date") or frappe.utils.today())
	to_date = getdate(filters.get("to_date") or frappe.utils.today())

	columns = [
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Vending Category"), "fieldname": "vending_category", "fieldtype": "Data", "width": 140},
		{"label": _("Transactions"), "fieldname": "transactions", "fieldtype": "Int", "width": 110},
		{"label": _("Quantity Sold"), "fieldname": "quantity", "fieldtype": "Float", "width": 120},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 140},
		{"label": _("Avg Rate"), "fieldname": "avg_rate", "fieldtype": "Currency", "width": 110},
		{"label": _("Machines"), "fieldname": "machines", "fieldtype": "Int", "width": 100},
		{"label": _("Revenue Share"), "fieldname": "revenue_share", "fieldtype": "Percent", "width": 120},
	]

	conditions = "docstatus = 1 AND posting_date BETWEEN %(from_date)s AND %(to_date)s"
	values = {"from_date": from_date, "to_date": to_date}
	if filters.get("machine"):
		conditions += " AND machine = %(machine)s"
		values["machine"] = filters.machine

	rows = frappe.db.sql(
		f"""
		SELECT
			item,
			COUNT(name) AS transactions,
			SUM(quantity_sold) AS quantity,
			SUM(amount) AS revenue,
			AVG(rate) AS avg_rate,
			COUNT(DISTINCT machine) AS machines
		FROM `tabVending Sales Entry`
		WHERE {conditions}
		GROUP BY item
		ORDER BY revenue DESC
		""",
		values,
		as_dict=True,
	)

	total_revenue = flt(sum(r.revenue for r in rows))
	data = []
	for row in rows:
		row["item_name"] = frappe.db.get_value("Item", row.item, "item_name") or ""
		row["vending_category"] = frappe.db.get_value("Item", row.item, "custom_vending_category") or ""
		row["revenue_share"] = flt(row.revenue) * 100 / total_revenue if total_revenue else 0
		data.append(row)

	chart = None
	if data:
		chart = {
			"data": {
				"labels": [d.item for d in data[:10]],
				"datasets": [{"name": _("Revenue"), "values": [d.revenue for d in data[:10]]}],
			},
			"type": "bar",
		}

	return columns, data, None, chart
