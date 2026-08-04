frappe.listview_settings["Vending Sales Entry"] = {
	onload(list_view) {
		vending_tracker.add_workflow_button(list_view.page, "Vending Sales Entry");
	},
};
