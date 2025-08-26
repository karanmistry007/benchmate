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

// ? Function to handle Create Site action
function createSite(frm) {
	frappe.call({
		method: "benchmate.api.create_site",
		args: { bench_path: frm.doc.bench_path },
		callback: function (r) {
			// ? Show response message from backend
			frappe.msgprint(r.message);
		},
	});
}

// ? Function to handle Start Bench action
function startBench(frm) {
	frappe.call({
		method: "benchmate.api.start_bench",
		args: { bench_path: frm.doc.bench_path },
		callback: function (r) {
			// ? Show response message from backend
			frappe.msgprint(r.message);
		},
	});
}

// ? Function to handle Stop Bench action
function stopBench(frm) {
	frappe.call({
		method: "benchmate.api.actions.bench_stop.stop_bench",
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
