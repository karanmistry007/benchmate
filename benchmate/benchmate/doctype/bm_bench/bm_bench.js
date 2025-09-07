// Copyright (c) 2025, Karan Mistry and contributors
// For license information, please see license.txt

frappe.ui.form.on("BM Bench", {
	refresh: function (frm) {
		// ? Function to add bench actions
		addBenchActions(frm);
	},
});

// ? Function to add bench actions
function addBenchActions(frm) {
	// ? Add "Create Site" button and pair it with handler
	frm.add_custom_button(
		__("Create Site"),
		function () {
			createSite(frm);
		},
		__("Actions")
	);

	// ? Add "Start Bench" button and pair it with handler
	frm.add_custom_button(
		__("Start Bench"),
		function () {
			startBench(frm);
		},
		__("Actions")
	);

	// ? Add "Stop Bench" button and pair it with handler
	frm.add_custom_button(
		__("Stop Bench"),
		function () {
			stopBench(frm);
		},
		__("Actions")
	);
}

function createSite(frm) {
	let d = new frappe.ui.Dialog({
		title: __("Create New Site"),
		fields: [
			{
				fieldtype: "Data",
				label: __("Site Name"),
				fieldname: "site_name",
				reqd: 1,
			},
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			d.hide();
			frappe.call({
				method: "benchmate.api.actions.create_site.execute",
				args: {
					bench_name: frm.doc.name,
					bench_path: frm.doc.path,
					site_name: values.site_name,
				},
				freeze: true,
				freeze_message: `Creating Site ${values.site_name}...`,
				callback: function (r) {
					// ? If success show success message
					if (r.message.success) {
						frappe.show_alert(
							{
								message: __(r.message.message),
								indicator: "green",
							},
							5
						);
					}

					// ? If error show error message
					else {
						frappe.show_alert(
							{
								message: __(r.message.message),
								indicator: "red",
							},
							5
						);
					}
				},
			});
		},
	});
	d.show();
}

// ? Function to handle Start Bench action
function startBench(frm) {
	frappe.call({
		method: "benchmate.api.actions.bench_start.execute",
		args: {
			bench_name: frm.doc.name,
			bench_path: frm.doc.path,
		},
		freeze: true,
		freeze_message: "Starting Bench...",
		callback: function (r) {
			// ? If success show success message
			if (r.message.success) {
				frappe.show_alert(
					{
						message: __(r.message.message),
						indicator: "green",
					},
					5
				);
			}

			// ? If error show error message
			else {
				frappe.show_alert(
					{
						message: __(r.message.message),
						indicator: "red",
					},
					5
				);
			}
		},
	});
}

// ? Function to handle Stop Bench action
function stopBench(frm) {
	frappe.call({
		method: "benchmate.api.actions.bench_stop.execute",
		args: {
			bench_name: frm.doc.name,
			bench_path: frm.doc.path,
		},
		freeze: true,
		freeze_message: "Stopping Bench...",
		callback: function (r) {
			// ? If success show success message
			if (r.message.success) {
				frappe.show_alert(
					{
						message: __(r.message.message),
						indicator: "green",
					},
					5
				);
			}

			// ? If error show error message
			else {
				frappe.show_alert(
					{
						message: __(r.message.message),
						indicator: "red",
					},
					5
				);
			}
		},
	});
}
