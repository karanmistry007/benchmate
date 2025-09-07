import os
import subprocess
import time

import frappe

from benchmate.api.utils import get_benchmate_settings


def update_restore_log_status(docname, new_text=None, status=None):
	"""
	Update the BM Log record for a given docname.
	Appends log text and/or updates the status field, committing immediately.
	"""
	try:
		log_doc = frappe.get_doc("BM Log", docname)

		if new_text:
			updated_log = (log_doc.log or "") + new_text
			log_doc.db_set("log", updated_log, update_modified=False)

		if status:
			log_doc.db_set("status", status, update_modified=False)

		frappe.db.commit()
		log_doc.reload()
	except Exception as e:
		frappe.log_error(f"Error updating BM Log: {e}", "BenchMate SiteRestoreLogs")


def restore_site_background(
	bench_name: str,
	bench_path: str,
	site_name: str,
	db_files_path: str,
	public_files_path: str,
	private_files_path: str,
	sudo_password: str,
	mysql_root_password: str,
):
	"""
	Background task to restore a Frappe site from backup files.
	Captures real-time logs into BM Log doctype,
	and cleans up temporary log files after completion.
	"""
	bench_path = os.path.abspath(bench_path)
	log_file = os.path.join(bench_path, f"bench_restore_site_{site_name}.log")

	# Create BM Log record
	log_timestamp = int(time.time())
	log_name = f"Restore Site-{log_timestamp}"
	if not frappe.db.exists("BM Log", log_name):
		frappe.get_doc(
			{
				"doctype": "BM Log",
				"title": f"Restore Site - {site_name}",
				"log": "",
				"log_timestamp": log_timestamp,
				"status": "In Process",
				"action": "Restore Site",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	# Build restore command with MySQL root password
	cmd = [
		"sudo",
		"-S",
		"bench",
		"--site",
		site_name,
		"--force",
		"restore",
		db_files_path,
		"--with-public-files",
		public_files_path,
		"--with-private-files",
		private_files_path,
		"--mariadb-root-password",
		mysql_root_password,  # ✅ Pass MySQL root password
	]

	try:
		with open(log_file, "w") as f:
			proc = subprocess.Popen(
				cmd,
				cwd=bench_path,
				stdin=subprocess.PIPE,
				stdout=f,
				stderr=subprocess.STDOUT,
				text=True,
			)

			# Send sudo password
			proc.stdin.write(sudo_password + "\n")
			proc.stdin.flush()
			proc.stdin.close()

			# Wait with timeout (20 mins)
			try:
				proc.wait(timeout=1200)
			except subprocess.TimeoutExpired:
				proc.kill()
				update_restore_log_status(
					log_name,
					new_text="\nTimed out while restoring site!\n",
					status="Error",
				)
				frappe.msgprint(
					msg=f"Timeout expired while restoring site {site_name}.",
					title="Site Restore Timeout",
					alert=True,
					indicator="red",
				)
				return

		# Stream logs into BM Log
		with open(log_file) as f:
			f.seek(0, os.SEEK_SET)
			for line in f:
				update_restore_log_status(log_name, new_text=line)

		# Success or error status
		if proc.returncode == 0:
			update_restore_log_status(log_name, status="Success")
		else:
			update_restore_log_status(log_name, status="Error")

	except Exception as e:
		frappe.msgprint(
			msg=f"Error while restoring site {site_name} in bench {bench_name}",
			title="Site Restore Error",
			realtime=True,
			alert=True,
			indicator="red",
		)
		frappe.log_error(f"Error running bench restore: {e}", "BenchMate SiteRestoreLogs")
		update_restore_log_status(log_name, status="Error")

	else:
		frappe.msgprint(
			msg=f"Site {site_name} restored successfully in bench {bench_name}",
			title="Site Restore Success",
			realtime=True,
			alert=True,
			indicator="green",
		)

	finally:
		try:
			if os.path.exists(log_file):
				os.remove(log_file)
		except Exception as cleanup_error:
			frappe.log_error(
				f"Failed to remove temp log file {log_file}: {cleanup_error}",
				"BenchMate SiteRestoreLogs",
			)


@frappe.whitelist()
def execute(
	bench_name: str,
	bench_path: str,
	site_name: str,
	db_files_path: str,
	public_files_path: str,
	private_files_path: str,
):
	"""
	Public API method (whitelisted) to enqueue site restore.
	Validates input and enqueues the background site restore task.
	"""
	if not bench_path or not site_name or not db_files_path:
		frappe.throw("bench_path, site_name and db_files_path are required", frappe.ValidationError)

	# ? Update the paths with full paths as per the current bench and site
	absolute_site_path = os.path.abspath(frappe.get_site_path())
	db_files_path = os.path.join(absolute_site_path, db_files_path.lstrip("/"))
	public_files_path = os.path.join(absolute_site_path, public_files_path.lstrip("/"))
	private_files_path = os.path.join(absolute_site_path, private_files_path.lstrip("/"))

	settings = get_benchmate_settings()
	sudo_password = settings.get("sudo_password")
	mysql_root_password = settings.get("db_password")

	if not sudo_password:
		frappe.throw("Sudo password not configured", frappe.ValidationError)

	if not mysql_root_password:
		frappe.throw("MySQL root password not configured", frappe.ValidationError)

	try:
		frappe.enqueue(
			restore_site_background,
			queue="long",
			timeout=7200,
			bench_name=bench_name,
			bench_path=bench_path,
			site_name=site_name,
			db_files_path=db_files_path,
			public_files_path=public_files_path,
			private_files_path=private_files_path,
			sudo_password=sudo_password,
			mysql_root_password=mysql_root_password,
		)

	except Exception as e:
		frappe.throw(f"Failed to enqueue site restore: {e!s}")

	return {
		"success": True,
		"message": (
			f"Restoring site <b>{site_name}</b> in the background. Check the <b>BM Log</b> for more details."
		),
		"data": None,
	}
