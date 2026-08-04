import frappe


def execute(filters=None):
	"""Daily sales summary for the selected date range."""
	filters = filters or {}
	from_date = filters.get("from_date") or "1970-01-01"
	to_date = filters.get("to_date") or frappe.utils.today()

	columns = [
		{"label": "Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{"label": "Transactions", "fieldname": "transactions", "fieldtype": "Int", "width": 110},
		{"label": "Quantity Sold", "fieldname": "quantity_sold", "fieldtype": "Float", "width": 120},
		{"label": "Revenue", "fieldname": "revenue", "fieldtype": "Currency", "width": 140},
	]

	data = frappe.db.sql(
		"""
		SELECT
			DATE(se.posting_date) AS posting_date,
			COUNT(se.name) AS transactions,
			SUM(se.quantity_sold) AS quantity_sold,
			SUM(se.amount) AS revenue
		FROM `tabVending Sales Entry` se
		WHERE se.docstatus = 1
			AND se.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND (COALESCE(%(machine)s, '') = '' OR se.machine = %(machine)s)
		GROUP BY DATE(se.posting_date)
		ORDER BY posting_date DESC
		""",
		{
			"from_date": from_date,
			"to_date": to_date,
			"machine": filters.get("machine") or "",
		},
		as_dict=True,
	)

	return columns, data
