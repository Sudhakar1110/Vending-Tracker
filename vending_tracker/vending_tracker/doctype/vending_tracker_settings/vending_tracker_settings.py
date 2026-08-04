import frappe
from frappe.model.document import Document


class VendingTrackerSettings(Document):
	pass


@frappe.whitelist()
def seed_demo_data():
	"""UI-triggered demo data seeding (button on Vending Tracker Settings).

	Adds demo machines, warehouse stock and submitted sales entries so the
	dashboard charts and reports have data — no bench console needed. The
	seeding itself is idempotent and guarded by vending_tracker.install.
	"""
	from vending_tracker.install import create_sample_data

	create_sample_data()
	frappe.db.commit()
	return True
