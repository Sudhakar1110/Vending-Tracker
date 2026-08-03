frappe.ui.form.on("Vending Machine", {
	refresh(frm) {
		if (frm.doc.last_heartbeat) {
			const last = frappe.datetime.str_to_user(frm.doc.last_heartbeat);
			const mins = frappe.datetime.get_diff(new Date(), last) * 24 * 60;
			const state = frm.doc.is_online ? __("Online") : __("Offline");
			const ago = mins < 1 ? __("just now") : __("{0} min ago", [Math.round(mins)]);
			frm.set_headline(
				__("{0} - last heartbeat {1}", [state, ago])
			);
		}

		if (frm.doc.iot_enabled) {
			frm.add_custom_button(__("Regenerate IoT Token"), () => {
				frappe.confirm(
					__("Regenerate the IoT token? Connected devices will need the new token."),
					() => {
						frappe.call({
							method: "vending_tracker.api.machine.regenerate_token",
							args: { machine: frm.doc.name },
							callback(r) {
								frm.set_value("iot_token", r.message);
								frm.refresh_field("iot_token");
								frappe.show_alert({ message: __("Token regenerated"), indicator: "green" });
							},
						});
					}
				);
			});
		}

		if (frm.doc.iot_enabled && frm.doc.api_endpoint && frm.doc.is_online) {
			frm.add_custom_button(__("Check Connection"), () => {
				frappe.call({
					method: "vending_tracker.api.machine.test_connection",
					args: { machine: frm.doc.name },
					freeze: true,
					callback(r) {
						frappe.msgprint(r.message);
					},
				});
			});
		}
	},
});
