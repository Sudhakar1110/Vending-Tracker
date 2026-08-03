import frappe
from frappe import _
from frappe.model.document import Document

from vending_tracker.utils.vending_utils import is_vending_item, update_slot_stock


class MachineProductSlot(Document):
	def validate(self):
		self.validate_item()
		self.validate_unique_slot_number()

	def on_update(self):
		# Recompute cached stock from the native Stock Ledger (Bin).
		update_slot_stock(machine=self.machine, item=self.item)

	def validate_item(self):
		if self.item and not is_vending_item(self.item):
			frappe.throw(
				_("Item {0} does not belong to the 'Vending Products' item group.").format(self.item)
			)

	def validate_unique_slot_number(self):
		if not (self.machine and self.slot_number):
			return
		existing = frappe.db.get_value(
			"Machine Product Slot",
			{"machine": self.machine, "slot_number": self.slot_number, "name": ["!=", self.name]},
			"name",
		)
		if existing:
			frappe.throw(_("Slot number {0} already exists for machine {1}.").format(self.slot_number, self.machine))
