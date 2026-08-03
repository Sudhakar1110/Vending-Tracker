frappe.listview_settings["Vending Machine"] = {
	get_indicator(doc) {
		const status_colors = {
			Active: "green",
			Maintenance: "orange",
			Offline: "red",
			Disabled: "gray",
		};
		return [__(doc.status), status_colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
