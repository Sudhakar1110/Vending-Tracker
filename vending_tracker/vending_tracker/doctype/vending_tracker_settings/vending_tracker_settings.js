frappe.ui.form.on("Vending Tracker Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Open Vending Overview"), () => {
			frappe.set_route("workspace", "Vending Tracker");
		});
	},
});
