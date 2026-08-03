frappe.ui.form.on("Vending Sales Entry", {
	item(frm) {
		if (!frm.doc.item) return;
		frappe.call({
			method: "vending_tracker.api.sales.get_item_rate",
			args: { item_code: frm.doc.item },
			callback(r) {
				if (r.message) {
					frm.set_value("rate", r.message);
					frm.set_value("amount", flt(frm.doc.quantity_sold) * flt(r.message));
				}
			},
		});
	},
	quantity_sold(frm) {
		frm.set_value("amount", flt(frm.doc.quantity_sold) * flt(frm.doc.rate));
	},
	rate(frm) {
		frm.set_value("amount", flt(frm.doc.quantity_sold) * flt(frm.doc.rate));
	},
});
