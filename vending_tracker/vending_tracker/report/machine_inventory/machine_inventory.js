frappe.query_reports["Machine Inventory"] = {
	filters: [
		{
			fieldname: "machine",
			label: __("Machine"),
			fieldtype: "Link",
			options: "Vending Machine",
		},
	],
};
