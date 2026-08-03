frappe.ui.form.on("Vending Machine Health Log", {
	refresh(frm) {
		if (frm.doc.is_online) {
			frm.set_df_property("status", "read_only", 0);
		}
	},
});
