frappe.query_reports["Low Stock Alert"] = {
	filters: [
		{
			fieldname: "machine",
			label: __("Machine"),
			fieldtype: "Link",
			options: "Vending Machine",
		},
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "only_low_stock",
			label: __("Only Low Stock"),
			fieldtype: "Check",
			default: 1,
		},
	],
};
