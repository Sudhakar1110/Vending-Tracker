frappe.ui.form.on("Machine Product Slot", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Refresh Stock"), () => {
				frappe.call({
					method: "vending_tracker.api.stock.get_slot_stock",
					args: { slot: frm.doc.name },
					callback(r) {
						frm.set_value("current_stock", r.message.current_stock);
						frm.set_value("stock_status", r.message.stock_status);
						frm.refresh_field("current_stock");
						frm.refresh_field("stock_status");
						frappe.show_alert({ message: __("Stock refreshed"), indicator: "green" });
					},
				});
			});
		}
	},
});
