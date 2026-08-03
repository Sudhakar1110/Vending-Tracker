import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class VendingMachineHealthLog(Document):
	def validate(self):
		if not self.logged_at:
			self.logged_at = now_datetime()
