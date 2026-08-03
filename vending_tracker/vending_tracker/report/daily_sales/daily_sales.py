data = """
SELECT
	DATE(se.posting_date) AS "Date:Date",
	COUNT(se.name) AS "Transactions:Int",
	SUM(se.quantity_sold) AS "Quantity Sold:Float",
	SUM(se.amount) AS "Revenue:Currency"
FROM `tabVending Sales Entry` se
WHERE se.docstatus = 1
	AND se.posting_date BETWEEN %(from_date)s AND %(to_date)s
	AND (COALESCE(%(machine)s, '') = '' OR se.machine = %(machine)s)
GROUP BY DATE(se.posting_date)
ORDER BY DATE(se.posting_date) DESC
"""
