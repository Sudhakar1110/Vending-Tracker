import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today


VENDING_ITEM_GROUP = "Vending Products"


# ---------------------------------------------------------------------------
# Item group helpers
# ---------------------------------------------------------------------------
def get_vending_item_groups():
	"""Return the 'Vending Products' item group and all its descendants."""
	if not frappe.db.exists("Item Group", VENDING_ITEM_GROUP):
		return []

	groups = [VENDING_ITEM_GROUP]
	try:
		from frappe.utils.nestedset import get_descendants

		groups += frappe.db.get_all(
			"Item Group",
			filters={"name": ["in", get_descendants("Item Group", VENDING_ITEM_GROUP)]},
			pluck="name",
		)
	except Exception:
		pass
	return groups


def is_vending_item(item_code):
	"""Return True if the item belongs (directly or indirectly) to Vending Products."""
	if not item_code:
		return False
	item_group = frappe.db.get_value("Item", item_code, "item_group")
	if not item_group:
		return False

	allowed = set(get_vending_item_groups())
	if item_group in allowed:
		return True

	current = item_group
	while current:
		if current in allowed:
			return True
		parent = frappe.db.get_value("Item Group", current, "parent_item_group")
		if not parent or parent == current:
			break
		current = parent
	return False


def item_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link-field query that only returns items in the Vending Products group."""
	groups = get_vending_item_groups()
	if not groups:
		return []

	return frappe.db.sql(
		"""
		SELECT name, item_name
		FROM `tabItem`
		WHERE item_group IN %(groups)s
			AND disabled = 0
			AND (name LIKE %(txt)s OR item_name LIKE %(txt)s)
		ORDER BY name
		LIMIT %(start)s, %(page_len)s
		""",
		{"groups": groups, "txt": f"%{txt}%", "start": start, "page_len": page_len},
	)


# ---------------------------------------------------------------------------
# Machine / warehouse helpers
# ---------------------------------------------------------------------------
def get_machine_warehouse(machine):
	"""Return the dedicated ERPNext warehouse linked to a vending machine."""
	if not machine:
		return None
	return frappe.db.get_value("Vending Machine", machine, "linked_warehouse")


def generate_iot_token():
	return frappe.generate_hash(20)


def get_selling_rate(item_code, qty=1):
	"""Standard Selling price for an item, falling back to item.standard_rate."""
	rate = frappe.db.get_value(
		"Item Price",
		{"item_code": item_code, "price_list": "Standard Selling", "selling": 1},
		"price_list_rate",
		order_by="valid_from desc",
	)
	if rate is None:
		rate = frappe.db.get_value("Item", item_code, "standard_rate")
	return flt(rate)


def log_machine_health(machine, status=None, is_online=None, source="Manual", error_message=None):
	"""Create a Vending Machine Health Log record (used by heartbeat + schedulers)."""
	if not frappe.db.exists("Vending Machine", machine):
		return None

	doc = frappe.get_doc(
		{
			"doctype": "Vending Machine Health Log",
			"machine": machine,
			"logged_at": frappe.utils.now_datetime(),
			"status": status or frappe.db.get_value("Vending Machine", machine, "status"),
			"is_online": 1 if is_online is None else is_online,
			"source": source,
			"error_message": error_message,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc


# ---------------------------------------------------------------------------
# Slot stock (cached view of the native Stock Ledger via Bin)
# ---------------------------------------------------------------------------
def get_bin_qty(item_code, warehouse):
	"""Actual qty in a warehouse from the native Bin table (source of truth)."""
	if not (item_code and warehouse):
		return 0
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))


def get_stock_status(qty, capacity=None, threshold=None):
	qty = flt(qty)
	if qty <= 0:
		return "Out of Stock"
	if flt(threshold) > 0 and qty <= flt(threshold):
		return "Low Stock"
	if flt(capacity) > 0 and qty >= flt(capacity):
		return "Overstock"
	return "In Stock"


def update_slot_stock(machine=None, item=None):
	"""Recompute cached stock levels for machine slots from Bin.

	Uses db_set on purpose: stock reconciliation must not re-fire the Save-event
	"Low Stock" notification for every slot on every save.
	"""
	filters = {"is_active": 1}
	if machine:
		filters["machine"] = machine
	if item:
		filters["item"] = item

	slots = frappe.get_all(
		"Machine Product Slot",
		filters=filters,
		fields=["name", "machine", "item", "maximum_capacity", "reorder_threshold"],
	)
	for slot in slots:
		warehouse = get_machine_warehouse(slot.machine)
		qty = get_bin_qty(slot.item, warehouse) if warehouse else 0
		status = get_stock_status(qty, slot.maximum_capacity, slot.reorder_threshold)
		frappe.db.set_value(
			"Machine Product Slot",
			slot.name,
			{"current_stock": qty, "stock_status": status},
			update_modified=False,
		)


def sync_all_slot_stock():
	update_slot_stock()


def get_low_stock_slots(machine=None):
	"""Slots currently at or below their reorder threshold (for API / server script)."""
	filters = {"is_active": 1}
	if machine:
		filters["machine"] = machine

	rows = []
	slots = frappe.get_all(
		"Machine Product Slot",
		filters=filters,
		fields=["name", "machine", "item", "current_stock", "reorder_threshold", "maximum_capacity", "stock_status"],
	)
	for slot in slots:
		if flt(slot.reorder_threshold or 0) > 0 and flt(slot.current_stock or 0) <= flt(slot.reorder_threshold):
			rows.append(
				{
					"slot": slot.name,
					"machine": slot.machine,
					"item": slot.item,
					"current_stock": flt(slot.current_stock or 0),
					"reorder_threshold": flt(slot.reorder_threshold or 0),
					"maximum_capacity": slot.maximum_capacity,
					"stock_status": slot.stock_status,
				}
			)
	return rows


# ---------------------------------------------------------------------------
# Stock Entry integration (Restock Entries are native Stock Entries)
# ---------------------------------------------------------------------------
def validate_vending_stock_entry(doc, method=None):
	"""Validate Stock Entries tagged with a vending machine."""
	if not doc.get("custom_vending_machine"):
		return

	doc.custom_is_vending_transaction = 1
	machine_warehouse = get_machine_warehouse(doc.custom_vending_machine)

	if doc.stock_entry_type == "Material Receipt" and doc.to_warehouse and machine_warehouse and doc.to_warehouse != machine_warehouse:
		frappe.throw(
			_("To Warehouse must be the machine's linked warehouse ({0}).").format(machine_warehouse)
		)
	if doc.stock_entry_type == "Material Transfer" and doc.to_warehouse and machine_warehouse and doc.to_warehouse != machine_warehouse:
		frappe.throw(
			_("To Warehouse must be the machine's linked warehouse ({0}).").format(machine_warehouse)
		)
	if doc.stock_entry_type == "Material Issue" and doc.from_warehouse and machine_warehouse and doc.from_warehouse != machine_warehouse:
		frappe.throw(
			_("From Warehouse must be the machine's linked warehouse ({0}).").format(machine_warehouse)
		)

	for row in doc.get("items") or []:
		if row.get("item_code") and not is_vending_item(row.item_code):
			frappe.throw(_("Item {0} is not a vending product.").format(row.item_code))


def on_vending_stock_entry_submit(doc, method=None):
	if doc.get("custom_vending_machine"):
		update_slot_stock(machine=doc.custom_vending_machine)


def on_vending_stock_entry_cancel(doc, method=None):
	if doc.get("custom_vending_machine"):
		update_slot_stock(machine=doc.custom_vending_machine)


# ---------------------------------------------------------------------------
# Notifications (Notification Log + email)
# ---------------------------------------------------------------------------
def get_role_users(role):
	return frappe.get_all(
		"User",
		filters=[["Has Role", "role", "=", role], ["enabled", "=", 1], ["user_type", "=", "System User"]],
		pluck="name",
	)


def create_notification_log(subject, message, reference_doctype=None, reference_name=None, role=None):
	"""Create a Notification Log for each user holding the given role."""
	users = get_role_users(role) if role else []
	if not users:
		return

	for user in users:
		try:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"subject": subject,
					"message": message,
					"type": "Alert",
					"document_type": reference_doctype,
					"document_name": reference_name,
					"for_user": user,
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(message=f"Failed to create notification log for {user}", title="Vending Tracker notify")


def send_email_to_role(subject, message, role, reference_doctype=None, reference_name=None):
	settings = frappe.get_single("Vending Tracker Settings")
	if not settings.notify_via_email:
		return

	users = get_role_users(role)
	recipients = []
	for user in users:
		email = frappe.db.get_value("User", user, "email")
		if email and email not in recipients:
			recipients.append(email)

	override = settings.low_stock_email_to
	if override:
		recipients = [override]

	if not recipients:
		return

	try:
		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			message=message,
			reference_doctype=reference_doctype,
			reference_name=reference_name,
		)
	except Exception:
		frappe.log_error(message="Failed to send vending notification email", title="Vending Tracker email")


def notify_low_stock(slot):
	"""Notify managers that a slot dropped to/below its reorder threshold."""
	machine_name = frappe.db.get_value("Vending Machine", slot.machine, "machine_name") or slot.machine
	item_name = frappe.db.get_value("Item", slot.item, "item_name") or slot.item
	subject = _("Low Stock: {0} in {1}").format(item_name, machine_name)
	message = _(
		"<p>Slot <b>{0}</b> in machine <b>{1}</b> is running low.</p>"
		"<p>Item: {2}<br>Current stock: {3}<br>Reorder threshold: {4}</p>"
	).format(
		slot.name,
		machine_name,
		item_name,
		flt(slot.current_stock or 0),
		flt(slot.reorder_threshold or 0),
	)

	create_notification_log(subject, message, "Machine Product Slot", slot.name, role="Vending Manager")
	send_email_to_role(subject, message, role="Vending Manager", reference_doctype="Machine Product Slot", reference_name=slot.name)


def notify_low_stock_for_item(machine, item):
	"""Check slots of a machine+item after a sale and notify once per cycle."""
	if not frappe.db.get_single_value("Vending Tracker Settings", "low_stock_enabled"):
		return

	slots = frappe.get_all(
		"Machine Product Slot",
		filters={"machine": machine, "item": item, "is_active": 1, "low_stock_notified": 0},
		fields=["name", "current_stock", "reorder_threshold"],
	)
	for slot in slots:
		if flt(slot.reorder_threshold or 0) > 0 and flt(slot.current_stock or 0) <= flt(slot.reorder_threshold):
			notify_low_stock(slot)
			frappe.db.set_value("Machine Product Slot", slot.name, "low_stock_notified", 1)


# ---------------------------------------------------------------------------
# Number card methods (Custom type number cards call these whitelisted methods)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_todays_revenue(filters=None):
	"""Total revenue from submitted vending sales posted today.

	Custom Number Cards call whitelisted methods with a ``filters`` kwarg;
	return a value dict so the card renders with currency formatting.
	"""
	value = flt(
		frappe.db.sql(
			"""SELECT IFNULL(SUM(amount), 0)
			FROM `tabVending Sales Entry`
			WHERE docstatus = 1 AND posting_date = CURDATE()"""
		)[0][0]
	)
	return {"value": value, "fieldtype": "Currency"}


@frappe.whitelist()
def get_monthly_revenue(filters=None):
	"""Total revenue from submitted vending sales posted this month."""
	value = flt(
		frappe.db.sql(
			"""SELECT IFNULL(SUM(amount), 0)
			FROM `tabVending Sales Entry`
			WHERE docstatus = 1
				AND YEAR(posting_date) = YEAR(CURDATE())
				AND MONTH(posting_date) = MONTH(CURDATE())"""
		)[0][0]
	)
	return {"value": value, "fieldtype": "Currency"}


@frappe.whitelist()
def get_low_stock_product_count(filters=None):
	"""Number of active machine slots at or below their reorder threshold."""
	value = cint(
		frappe.db.sql(
			"""SELECT COUNT(*)
			FROM `tabMachine Product Slot`
			WHERE is_active = 1
				AND IFNULL(reorder_threshold, 0) > 0
				AND IFNULL(current_stock, 0) <= reorder_threshold"""
		)[0][0]
	)
	return {"value": value, "fieldtype": "Int"}


# ---------------------------------------------------------------------------
# Email report summaries (scheduler)
# ---------------------------------------------------------------------------
def _sales_rows(from_date, to_date, filters=None):
	conditions = "docstatus = 1 AND posting_date BETWEEN %(from_date)s AND %(to_date)s"
	values = {"from_date": from_date, "to_date": to_date}
	filters = frappe._dict(filters or {})
	if filters.get("machine"):
		conditions += " AND machine = %(machine)s"
		values["machine"] = filters.machine
	if filters.get("item"):
		conditions += " AND item = %(item)s"
		values["item"] = filters.item
	return frappe.db.sql(
		f"""
		SELECT machine, item, quantity_sold, amount, posting_date
		FROM `tabVending Sales Entry`
		WHERE {conditions}
		ORDER BY posting_date DESC
		""",
		values,
		as_dict=True,
	)


def get_daily_sales_summary():
	"""HTML summary of yesterday's sales + low stock for the daily report email."""
	from frappe.utils import add_days

	yesterday = add_days(today(), -1)
	rows = _sales_rows(yesterday, yesterday)
	if not rows:
		return None

	total = sum(flt(r.amount) for r in rows)
	items_html = "".join(
		"<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
			r.machine, r.item, flt(r.quantity_sold), flt(r.amount), r.posting_date
		)
		for r in rows[:50]
	)

	low_stock = get_low_stock_slots()
	low_html = ""
	if low_stock:
		low_html = "<h4>Low Stock</h4><table border='1' cellpadding='6' style='border-collapse:collapse'>" + "".join(
			"<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
				ls["machine"], ls["item"], ls["current_stock"]
			)
			for ls in low_stock[:20]
		) + "</table>"

	return f"""
		<h3>Daily Sales Report - {yesterday}</h3>
		<p>Total revenue: <b>{total:.2f}</b> | Transactions: {len(rows)}</p>
		<table border='1' cellpadding='6' style='border-collapse:collapse'>
			<tr><th>Machine</th><th>Item</th><th>Qty</th><th>Amount</th><th>Date</th></tr>
			{items_html}
		</table>
		{low_html}
	"""


def get_monthly_revenue_summary():
	"""HTML summary of the previous calendar month's revenue."""
	from frappe.utils import add_months, get_first_day, get_last_day

	last_month_first = get_first_day(add_months(today(), -1))
	last_month_last = get_last_day(add_months(today(), -1))
	rows = _sales_rows(last_month_first, last_month_last)

	machines = frappe.db.sql(
		"""
		SELECT machine, COUNT(name) AS transactions, SUM(amount) AS revenue
		FROM `tabVending Sales Entry`
		WHERE docstatus = 1 AND posting_date BETWEEN %s AND %s
		GROUP BY machine
		ORDER BY revenue DESC
		""",
		(last_month_first, last_month_last),
		as_dict=True,
	)
	if not machines:
		return None

	total = sum(flt(r.revenue) for r in machines)
	machine_rows = "".join(
		"<tr><td>{}</td><td>{}</td><td>{:.2f}</td></tr>".format(r.machine, r.transactions, flt(r.revenue))
		for r in machines
	)
	return f"""
		<h3>Vending Revenue Summary - {last_month_first} to {last_month_last}</h3>
		<p>Total revenue: <b>{total:.2f}</b> | Transactions: {len(rows)}</p>
		<table border='1' cellpadding='6' style='border-collapse:collapse'>
			<tr><th>Machine</th><th>Transactions</th><th>Revenue</th></tr>
			{machine_rows}
		</table>
	"""
