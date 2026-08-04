data = """
SELECT
	se.machine AS "Machine",
	COUNT(se.name) AS "Transactions:Int",
	SUM(se.quantity_sold) AS "Quantity Sold:Float",
	SUM(se.amount) AS "Revenue:Currency"
FROM `tabVending Sales Entry` se
WHERE se.docstatus = 1
	AND se.posting_date BETWEEN COALESCE(%(from_date)s, '1970-01-01') AND COALESCE(%(to_date)s, CURDATE())
	AND (COALESCE(%(machine)s, '') = '' OR se.machine = %(machine)s)
GROUP BY se.machine
ORDER BY SUM(se.amount) DESC
"""
