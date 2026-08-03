data = """
SELECT
	DATE_FORMAT(se.posting_date, '%Y-%m') AS "Year-Month",
	DATE_FORMAT(se.posting_date, '%M %Y') AS "Month",
	COUNT(se.name) AS "Transactions:Int",
	SUM(se.quantity_sold) AS "Quantity Sold:Float",
	SUM(se.amount) AS "Revenue:Currency"
FROM `tabVending Sales Entry` se
WHERE se.docstatus = 1
	AND se.posting_date BETWEEN %(from_date)s AND %(to_date)s
	AND (COALESCE(%(machine)s, '') = '' OR se.machine = %(machine)s)
GROUP BY DATE_FORMAT(se.posting_date, '%Y-%m'), DATE_FORMAT(se.posting_date, '%M %Y')
ORDER BY 1 DESC
"""
