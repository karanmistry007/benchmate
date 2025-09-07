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

	// ? Add "Drop Site" button and pair it with handler
	frm.add_custom_button(
		__("Drop Site"),
		function () {
			dropSite(frm);
		},
		__("Actions")
	);

	// ? Add "Backup Site" button and pair it with handler
	frm.add_custom_button(
		__("Backup Site"),
		function () {
			backupSite(frm);
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

// ? Function to handle Cerate Site action
function createSite(frm) {
	let dialog = new frappe.ui.Dialog({
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
			dialog.hide();
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
	dialog.show();
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

// ? Function to handle the Drop Site action from BM Bench form
function dropSite(frm) {
	// ? Create a dialog box for site selection and drop confirmation
	let dialog = new frappe.ui.Dialog({
		title: __("Drop A Site"),

		// ? Fields inside the dialog
		fields: [
			{
				label: __("Site"),
				fieldname: "site",
				fieldtype: "Link",
				options: "BM Site",
				reqd: 1,
				get_query: function () {
					// ? Restrict sites only for the current bench
					return {
						filters: [["bench_name", "=", frm.doc.name]],
					};
				},
				onchange: function () {
					// ? On site selection, fetch the actual site_name
					let site = dialog.get_value("site");
					if (site) {
						frappe.call({
							method: "frappe.client.get_value",
							args: {
								doctype: "BM Site",
								filters: { name: site },
								fieldname: ["site_name"],
							},
							freeze: true,
							freeze_message: __(`Fetching Site Name...`),
							callback: function (response) {
								// ? Auto-populate the readonly Site Name field
								dialog.set_value("site_name", response.message.site_name);
							},
						});
					}
				},
			},
			{
				label: __("Site Name"),
				fieldname: "site_name",
				fieldtype: "Data",
				read_only: 1,
				reqd: 1,
			},
		],

		// ? Primary action button: Drop Site
		primary_action_label: __("Drop"),
		primary_action(values) {
			// ? Hide dialog after confirmation
			dialog.hide();

			// ? Call server-side method to drop the site
			frappe.call({
				method: "benchmate.api.actions.drop_site.execute",
				args: {
					bench_name: frm.doc.name,
					bench_path: frm.doc.path,
					site_name: values.site_name,
				},
				freeze: true,
				freeze_message: __(`Dropping Site ${values.site_name}...`),

				// ? Handle callback after server execution
				callback: function (r) {
					if (r.message.success) {
						// ? Show success message on site drop
						frappe.show_alert(
							{
								message: __(r.message.message),
								indicator: "green",
							},
							5
						);
					} else {
						// ? Show error message if failed
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

	// ? Display the dialog to the user
	dialog.show();
}

// ? Function to handle the Backup Site action from BM Bench form
function backupSite(frm) {
	// ? Create a dialog box for site selection and backup confirmation
	let dialog = new frappe.ui.Dialog({
		title: __("Backup A Site"),

		// ? Fields inside the dialog
		fields: [
			{
				label: __("Site"),
				fieldname: "site",
				fieldtype: "Link",
				options: "BM Site",
				reqd: 1,
				get_query: function () {
					// ? Restrict sites only for the current bench
					return {
						filters: [["bench_name", "=", frm.doc.name]],
					};
				},
				onchange: function () {
					// ? On site selection, fetch the actual site_name
					let site = dialog.get_value("site");
					if (site) {
						frappe.call({
							method: "frappe.client.get_value",
							args: {
								doctype: "BM Site",
								filters: { name: site },
								fieldname: ["site_name"],
							},
							freeze: true,
							freeze_message: __(`Fetching Site Name...`),
							callback: function (response) {
								// ? Auto-populate the readonly Site Name field
								dialog.set_value("site_name", response.message.site_name);
							},
						});
					}
				},
			},
			{
				label: __("Site Name"),
				fieldname: "site_name",
				fieldtype: "Data",
				read_only: 1,
				reqd: 1,
			},
		],

		// ? Primary action button: Backup Site
		primary_action_label: __("Backup"),
		primary_action(values) {
			// ? Hide dialog after confirmation
			dialog.hide();

			// ? Call server-side method to backup the site
			frappe.call({
				method: "benchmate.api.actions.backup_site.execute",
				args: {
					bench_name: frm.doc.name,
					bench_path: frm.doc.path,
					site_name: values.site_name,
				},
				freeze: true,
				freeze_message: __(`Taking Backup Of Site ${values.site_name}...`),

				// ? Handle callback after server execution
				callback: function (r) {
					if (r.message.success) {
						// ? Show success message on site drop
						frappe.show_alert(
							{
								message: __(r.message.message),
								indicator: "green",
							},
							5
						);
					} else {
						// ? Show error message if failed
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

	// ? Display the dialog to the user
	dialog.show();
}
