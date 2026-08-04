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

// ---------------------------------------------------------------------------
// Workflow guide — list views
// ---------------------------------------------------------------------------
// Adds a "Workflow" button to the header of the Vending Sales Entry and Stock
// Entry list views. Clicking it opens a dialog with a visual state diagram and
// the states / transitions tables, rendered live from the active workflow
// config (frappe.workflow.workflows[doctype]).

vending_tracker.add_workflow_button = function (page, doctype) {
	if (!page || page.__vt_workflow_button) {
		return;
	}
	page.add_inner_button(__("Workflow"), () => vending_tracker.show_workflow_dialog(doctype));
	// add_inner_button also dedupes by label, so double-adding is impossible;
	// the flag only guards the extra mobile menu item it appends.
	page.__vt_workflow_button = true;
};

// Mirrored on the public /health portal page (vending_tracker/www/health.py
// -> _workflow renders the same guide server-side); both read the live
// workflow config so they stay consistent.
vending_tracker.show_workflow_dialog = function (doctype) {
	// Ensure the workflow is loaded client-side (the list view itself also
	// loads it via set_stats -> frappe.workflow.get_state_fieldname).
	frappe.workflow.get_state_fieldname(doctype);
	const wf = frappe.workflow.workflows[doctype];

	const dialog = new frappe.ui.Dialog({
		title: __("Workflow") + ": " + doctype,
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "workflow_body" }],
		primary_action_label: __("Close"),
		primary_action() {
			dialog.hide();
		},
	});
	dialog.fields_dict.workflow_body.$wrapper.html(
		vending_tracker.workflow_guide_html(wf, doctype)
	);
	dialog.show();
};

vending_tracker.workflow_guide_html = function (wf, doctype) {
	const esc = frappe.utils.escape_html;
	const doc_status_labels = { 0: __("Draft"), 1: __("Submitted"), 2: __("Cancelled") };
	const doc_status_colors = { 0: "gray", 1: "green", 2: "red" };

	if (!wf || !Array.isArray(wf.states) || !wf.states.length) {
		return `<div class="text-muted">${__("No active workflow is configured for {0}.", [doctype])}</div>`;
	}

	const states = wf.states.slice().sort((a, b) => cint(a.doc_status) - cint(b.doc_status));
	const transitions = Array.isArray(wf.transitions) ? wf.transitions : [];

	const role_list = (value) => {
		return (value || "")
			.split(",")
			.map((r) => r.trim())
			.filter(Boolean)
			.join(", ");
	};

	// --- state flow diagram -------------------------------------------------
	let flow_html = "";
	states.forEach((state, i) => {
		const status = cint(state.doc_status);
		const roles = role_list(state.allow_edit);
		flow_html += `
			<div class="vt-wf-card vt-wf-${doc_status_colors[status] || "gray"}">
				<div class="vt-wf-state">${esc(state.state)}</div>
				<div class="vt-wf-sub">${esc(doc_status_labels[status] || __("DocStatus {0}", [status]))}</div>
				<div class="vt-wf-roles">${esc(roles || __("No role"))}</div>
			</div>`;
		if (i < states.length - 1) {
			const next = states[i + 1];
			const actions = frappe.utils.unique(
				transitions
					.filter((t) => t.state === state.state && t.next_state === next.state)
					.map((t) => t.action)
			);
			flow_html += `
				<div class="vt-wf-arrow">
					<span class="vt-wf-arrow-glyph">&rarr;</span>
					${actions.length ? `<span class="vt-wf-arrow-action">${esc(actions.join(" / "))}</span>` : ""}
				</div>`;
		}
	});

	// --- states table -------------------------------------------------------
	const states_rows = states
		.map((state) => {
			const status = cint(state.doc_status);
			const update = state.update_field
				? `${esc(state.update_field)} = ${esc(state.update_value ?? "")}`
				: "—";
			return `
				<tr>
					<td><span class="indicator ${doc_status_colors[status] || "gray"}">${esc(state.state)}</span></td>
					<td>${esc(doc_status_labels[status] || status)}</td>
					<td>${esc(role_list(state.allow_edit) || "—")}</td>
					<td>${update}</td>
				</tr>`;
		})
		.join("");

	// --- transitions table --------------------------------------------------
	const transitions_rows = transitions
		.map((t) => {
			return `
				<tr>
					<td>${esc(t.state)}</td>
					<td><span class="label label-default">${esc(t.action)}</span></td>
					<td>${esc(t.next_state)}</td>
					<td>${esc(role_list(t.allowed) || "—")}</td>
				</tr>`;
		})
		.join("");

	return `
		<div class="vt-wf-dialog">
			<div class="vt-wf-flow">${flow_html}</div>
			<h6 class="vt-wf-section">${__("Workflow States")}</h6>
			<table class="table table-bordered vt-wf-table">
				<thead>
					<tr>
						<th>${__("State")}</th>
						<th>${__("DocStatus")}</th>
						<th>${__("Editable By")}</th>
						<th>${__("On Entry Updates")}</th>
					</tr>
				</thead>
				<tbody>${states_rows}</tbody>
			</table>
			<h6 class="vt-wf-section">${__("Transitions")}</h6>
			<table class="table table-bordered vt-wf-table">
				<thead>
					<tr>
						<th>${__("From")}</th>
						<th>${__("Action")}</th>
						<th>${__("To")}</th>
						<th>${__("Allowed Roles")}</th>
					</tr>
				</thead>
				<tbody>${transitions_rows}</tbody>
			</table>
		</div>`;
};

// The Restock Workflow lives on the ERPNext-owned Stock Entry doctype, so its
// list view cannot be extended from an app module file. Hook the router and add
// the Workflow button whenever the Stock Entry list view is shown.
if (frappe.router && frappe.router.on) {
	frappe.router.on("change", () => {
		const route = frappe.get_route() || [];
		if (route[0] !== "List" || route[1] !== "Stock Entry") {
			return;
		}
		if (route[2] && route[2] !== "List") {
			return; // only the plain list view
		}
		if (cur_list && cur_list.doctype === "Stock Entry" && cur_list.page) {
			vending_tracker.add_workflow_button(cur_list.page, "Stock Entry");
		}
	});
}
