frappe.ui.form.on("Vending Tracker Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Open Vending Overview"), () => {
			frappe.set_route("workspace", "Vending Tracker");
		});
		frm.add_custom_button(__("Seed Demo Data"), () => {
			frappe.confirm(
				__("This will add demo machines, warehouse stock and submitted sales entries so the dashboard charts and reports have data. Continue?"),
				() => {
					frm.call({
						method:
							"vending_tracker.vending_tracker.doctype.vending_tracker_settings.vending_tracker_settings.seed_demo_data",
						callback(r) {
							if (!r.exc) {
								frappe.msgprint(
									__("Demo data seeded. Open the Vending Overview workspace to see the dashboard.")
								);
							}
						},
					});
				}
			);
		});
	},
});
