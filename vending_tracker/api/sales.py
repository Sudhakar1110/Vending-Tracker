import frappe
from frappe import _
from frappe.utils import flt

from vending_tracker.api.auth import authenticate_machine
from vending_tracker.utils.vending_utils import get_selling_rate, is_vending_item


@frappe.whitelist()
def get_item_rate(item_code):
	"""Return the current selling rate for an item (used by client scripts)."""
	return get_selling_rate(item_code)


@frappe.whitelist(allow_guest=True)
def sync_sales(machine_id=None, token=None, sales=None, submit=True):
	"""Sales Sync API.

	Bulk-pushes sales from an IoT device into Vending Sales Entry documents.
	Each entry is submitted by default, which automatically creates the native
	ERPNext Material Issue Stock Entry and reduces machine stock via the Stock
	Ledger only.

	``sales`` is a list of dicts:
	{"item": "VND-COLA-002", "quantity_sold": 1, "rate": 40, "sold_at": "2026-01-01 10:00:00", "source": "IoT"}
	"""
	name = authenticate_machine(machine_id, token)

	if not isinstance(sales, list) or not sales:
		frappe.throw(_("sales must be a non-empty list"))

	created = []
	failed = []

	for idx, sale in enumerate(sales, start=1):
		if not isinstance(sale, dict):
			failed.append({"row": idx, "error": "not a dict"})
			continue
		item = sale.get("item") or sale.get("item_code")
		qty = flt(sale.get("quantity_sold") or sale.get("qty") or 1)
		rate = flt(sale.get("rate") or 0)
		source = sale.get("source") or "IoT"

		if not item or not is_vending_item(item):
			failed.append({"row": idx, "item": item, "error": "item is not a vending product"})
			continue

		try:
			doc = frappe.new_doc("Vending Sales Entry")
			doc.machine = name
			doc.item = item
			doc.quantity_sold = qty
			doc.rate = rate or get_selling_rate(item)
			doc.source = source
			doc.posting_date = (sale.get("sold_at") or frappe.utils.today())[:10]
			if sale.get("sold_at"):
				doc.posting_time = sale["sold_at"][11:19] or "12:00:00"
			doc.flags.ignore_permissions = True
			doc.insert()
			if submit:
				doc.submit()
			created.append({"name": doc.name, "row": idx, "amount": doc.amount})
		except Exception as exc:
			failed.append({"row": idx, "item": item, "error": str(exc)})

	return {"machine": machine_id, "created": created, "failed": failed}
