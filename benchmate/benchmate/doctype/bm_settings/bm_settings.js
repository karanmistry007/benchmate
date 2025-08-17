// Copyright (c) 2025, Karan Mistry and contributors
// For license information, please see license.txt

frappe.ui.form.on("BM Settings", {
	refresh(frm) {
		// ? Add the "Sync Bench Details" button when the form is refreshed
		addSyncBenchDetailsButton(frm);
	},
});

function addSyncBenchDetailsButton(frm) {
	// ? Check if the BM Settings document has syncing enabled
	if (frm.doc.enable) {
		// ? Add custom button to trigger bench details sync
		frm.add_custom_button("Sync Bench Details", () => {
			enqueueSyncBenchDetailsButton();
		});
	}
}

function enqueueSyncBenchDetailsButton() {
	// ? Call Frappe backend method to enqueue sync
	frappe.call({
		method: "benchmate.api.sync.enqueue_sync_bench_details",
		args: {},

		// ? Freeze the UI with message while processing
		freeze: true,
		freeze_message: "Enqueuing Sync Bench Details...",

		// ? Callback when backend call is complete
		callback: function (res) {
			// ? If enqueue was successful, show a success alert
			if (res.message.success) {
				frappe.show_alert(
					{
						message: __("Successfully Enqueued Sync Bench Details!"),
						indicator: "green",
					},
					5
				);
			}
		},
	});
}
