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


# ! benchmate.api.utils.get_sites
@frappe.whitelist()
def get_sites(bench_name: str):
	try:
		site_list = frappe.get_all(
			"BM Site",
			filters={"bench_name": bench_name},
			fields=["name", "site_name", "status"],
		)

		if not site_list or len(site_list) < 0:
			frappe.throw(
				f"There are no sites in bench {bench_name}",
				frappe.ValidationError,
			)

	except Exception as e:
		frappe.log_error("Error while benchmate.api.utils.get_sites", frappe.get_traceback())
		return {
			"success": True,
			"message": str(e),
			"data": None,
		}

	else:
		return {
			"success": True,
			"message": "Successfully Get The Site List",
			"data": site_list,
		}
