import frappe


def get_benchmate_settings():
	"""Get Benchmate settings if enabled, else raise ValidationError."""

	# ? Check if settings are enabled
	if frappe.db.get_single_value("BM Settings", "enable"):
		# ? Fetch settings document
		benchmate_settings_doc = frappe.get_single("BM Settings")

		# ? Collect and return required settings
		benchmate_settings = {
			"default_path": benchmate_settings_doc.get("default_path"),
			"sudo_password": benchmate_settings_doc.get_password("sudo_password"),
			"db_password": benchmate_settings_doc.get_password("db_password"),
		}
		return benchmate_settings

	# ? Raise error if settings are disabled
	else:
		frappe.throw(
			"Benchmate Settings are not enabled. Please enable them to proceed.",
			frappe.ValidationError,
		)
