import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime, today

from vending_tracker.utils.vending_utils import (
	get_machine_warehouse,
	get_selling_rate,
	is_vending_item,
	notify_high_sales,
	notify_low_stock_for_item,
	update_slot_stock,
)


class VendingSalesEntry(Document):
	def validate(self):
		self.validate_vending_item()
		self.set_rate()
		self.calculate_amount()

	def on_submit(self):
		# Reduce machine stock exclusively through the native Stock Ledger.
		self.create_material_issue()
		update_slot_stock(machine=self.machine, item=self.item)
		notify_low_stock_for_item(self.machine, self.item)
		notify_high_sales(self)

	def on_cancel(self):
		self.cancel_stock_entry()
		update_slot_stock(machine=self.machine, item=self.item)

	def validate_vending_item(self):
		if self.item and not is_vending_item(self.item):
			frappe.throw(_("Item {0} is not a vending product.").format(self.item))

	def set_rate(self):
		if not self.rate and self.item:
			self.rate = get_selling_rate(self.item)

	def calculate_amount(self):
		self.amount = flt(self.quantity_sold) * flt(self.rate)

	def create_material_issue(self):
		"""Create and submit a native Material Issue Stock Entry.

		Stock is consumed from the machine's dedicated warehouse so the Stock
		Ledger remains the single source of truth for machine inventory.
		"""
		if self.stock_entry:
			return

		warehouse = get_machine_warehouse(self.machine)
		if not warehouse:
			frappe.throw(_("Machine {0} has no linked warehouse. Please set it first.").format(self.machine))

		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Issue"
		se.company = (
			frappe.db.get_value("Vending Machine", self.machine, "company")
			or frappe.defaults.get_global_default("company")
		)
		se.posting_date = self.posting_date or today()
		se.posting_time = self.posting_time or now_datetime().strftime("%H:%M:%S")
		se.remarks = _("Vending sale {0}: {1} x {2} from machine {3}").format(
			self.name, self.quantity_sold, self.item, self.machine
		)
		se.custom_vending_machine = self.machine
		se.custom_is_vending_transaction = 1
		se.custom_vending_source_document = self.name
		se.append(
			"items",
			{
				"item_code": self.item,
				"qty": self.quantity_sold,
				"uom": frappe.db.get_value("Item", self.item, "stock_uom"),
				"s_warehouse": warehouse,
				"allow_zero_valuation_rate": 1,
			},
		)
		se.flags.ignore_permissions = True
		se.insert()
		se.submit()
		self.db_set("stock_entry", se.name)

	def cancel_stock_entry(self):
		if not self.stock_entry:
			return
		se = frappe.get_doc("Stock Entry", self.stock_entry)
		if se.docstatus == 1:
			se.flags.ignore_permissions = True
			se.cancel()
