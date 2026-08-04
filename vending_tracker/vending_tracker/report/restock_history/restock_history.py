import frappe


def execute(filters=None):
	"""Restock Stock Entries for the selected date range."""
	filters = filters or {}
	from_date = filters.get("from_date") or "1970-01-01"
	to_date = filters.get("to_date") or frappe.utils.today()

	columns = [
		{"label": "Stock Entry", "fieldname": "name", "fieldtype": "Link", "options": "Stock Entry", "width": 170},
		{"label": "Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{"label": "Stock Entry Type", "fieldname": "stock_entry_type", "fieldtype": "Data", "width": 160},
		{"label": "Machine", "fieldname": "machine", "fieldtype": "Link", "options": "Vending Machine", "width": 170},
		{"label": "Source Warehouse", "fieldname": "from_warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 180},
		{"label": "Target Warehouse", "fieldname": "to_warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 180},
		{"label": "Total Quantity", "fieldname": "total_quantity", "fieldtype": "Float", "width": 110},
		{"label": "Items", "fieldname": "items", "fieldtype": "Int", "width": 80},
		{"label": "Remarks", "fieldname": "remarks", "fieldtype": "Data", "width": 200},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 110},
	]

	data = frappe.db.sql(
		"""
		SELECT
			se.name,
			se.posting_date,
			se.stock_entry_type,
			se.custom_vending_machine AS machine,
			se.from_warehouse,
			se.to_warehouse,
			(SELECT IFNULL(SUM(i.qty), 0) FROM `tabStock Entry Detail` i WHERE i.parent = se.name) AS total_quantity,
			(SELECT COUNT(*) FROM `tabStock Entry Detail` i WHERE i.parent = se.name) AS items,
			se.remarks,
			CASE se.docstatus WHEN 0 THEN 'Draft' WHEN 1 THEN 'Submitted' ELSE 'Cancelled' END AS status
		FROM `tabStock Entry` se
		WHERE se.custom_is_vending_transaction = 1
			AND se.stock_entry_type IN ('Material Receipt', 'Material Transfer')
			AND se.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND (COALESCE(%(machine)s, '') = '' OR se.custom_vending_machine = %(machine)s)
		ORDER BY se.posting_date DESC, se.name DESC
		""",
		{
			"from_date": from_date,
			"to_date": to_date,
			"machine": filters.get("machine") or "",
		},
		as_dict=True,
	)

	return columns, data
