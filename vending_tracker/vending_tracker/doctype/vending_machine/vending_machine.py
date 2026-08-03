import frappe
from frappe import _
from frappe.model.document import Document

from vending_tracker.utils.vending_utils import generate_iot_token


class VendingMachine(Document):
	def validate(self):
		self.set_iot_token()
		self.create_linked_warehouse()

	def set_iot_token(self):
		if self.iot_enabled and not self.iot_token:
			self.iot_token = generate_iot_token()

	def create_linked_warehouse(self):
		"""Ensure the machine is mapped to a dedicated ERPNext warehouse.

		The warehouse is auto-created (once) when none is linked and the
		setting is enabled. All stock movement for this machine flows through
		this warehouse in the native Stock Ledger.
		"""
		if self.linked_warehouse:
			return

		if not frappe.db.get_single_value("Vending Tracker Settings", "auto_create_warehouse"):
			return

		company = self.company or frappe.defaults.get_global_default("company")
		if not company:
			return

		warehouse_name = f"VM - {self.machine_id}"
		if not frappe.db.exists("Warehouse", warehouse_name):
			wh = frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": f"{self.machine_id} - {self.machine_name}",
					"company": company,
					"is_group": 0,
					"disabled": 0,
				}
			)
			wh.flags.ignore_permissions = True
			wh.insert()
			self.linked_warehouse = wh.name
		else:
			self.linked_warehouse = warehouse_name
