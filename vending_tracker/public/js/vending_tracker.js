// Vending Tracker — app-wide desk helpers.
frappe.provide("vending_tracker");

vending_tracker.get_machine_label = function (machine) {
	return machine ? machine : __("Machine");
};

frappe.ui.form.on("Vending Sales Entry", {
	onload(frm) {
		frm.set_query("item", () => ({
			query: "vending_tracker.utils.vending_utils.item_query",
		}));
	},
});
