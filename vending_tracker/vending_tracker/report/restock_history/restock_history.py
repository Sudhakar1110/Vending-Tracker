data = """
SELECT
	se.name AS "Stock Entry",
	se.posting_date AS "Date:Date",
	se.stock_entry_type AS "Stock Entry Type",
	se.custom_vending_machine AS "Machine",
	se.from_warehouse AS "Source Warehouse",
	se.to_warehouse AS "Target Warehouse",
	(SELECT IFNULL(SUM(i.qty), 0) FROM `tabStock Entry Detail` i WHERE i.parent = se.name) AS "Total Quantity:Float",
	(SELECT COUNT(*) FROM `tabStock Entry Detail` i WHERE i.parent = se.name) AS "Items:Int",
	se.remarks AS "Remarks",
	CASE se.docstatus WHEN 0 THEN 'Draft' WHEN 1 THEN 'Submitted' ELSE 'Cancelled' END AS "Status"
FROM `tabStock Entry` se
WHERE se.custom_is_vending_transaction = 1
	AND se.stock_entry_type IN ('Material Receipt', 'Material Transfer')
	AND se.posting_date BETWEEN COALESCE(%(from_date)s, '1970-01-01') AND COALESCE(%(to_date)s, CURDATE())
	AND (COALESCE(%(machine)s, '') = '' OR se.custom_vending_machine = %(machine)s)
ORDER BY se.posting_date DESC, se.name DESC
"""
