import os
import subprocess
import time

import frappe

from benchmate.api.utils import get_benchmate_settings


def update_deletion_log_status(docname, new_text=None, status=None):
	"""
	? Update the BM Log record for a given docname.
	? Appends log text and/or updates the status field, committing immediately.
	"""
	try:
		log_doc = frappe.get_doc("BM Log", docname)

		# ? Append new log text if provided
		if new_text:
			updated_log = (log_doc.log or "") + new_text
			log_doc.db_set("log", updated_log, update_modified=False)

		# ? Update status if provided
		if status:
			log_doc.db_set("status", status, update_modified=False)

		frappe.db.commit()
		log_doc.reload()
	except Exception as e:
		frappe.log_error(f"Error updating BM Log: {e}", "BenchMate SiteDeletionLogs")


def drop_site_background(
	bench_name: str, bench_path: str, site_name: str, sudo_password: str, mysql_root_password: str
):
	"""
	Background task to drop (delete) a Frappe site inside a given bench.
	Captures real-time logs into BM Log doctype,
	and cleans up temporary log files after completion.
	"""
	bench_path = os.path.abspath(bench_path)
	log_file = os.path.join(bench_path, f"bench_drop_site_{site_name}.log")

	# ? Create a unique BM Log record for tracking
	log_timestamp = int(time.time())
	log_name = f"Drop Site-{log_timestamp}"
	if not frappe.db.exists("BM Log", log_name):
		frappe.get_doc(
			{
				"doctype": "BM Log",
				"title": f"Drop Site - {site_name}",
				"log": "",
				"log_timestamp": log_timestamp,
				"status": "In Process",
				"action": "Drop Site",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	# ? Command to drop the site with root DB password, no --verbose
	cmd = [
		"sudo",
		"-S",
		"bench",
		"drop-site",
		site_name,
		"--db-root-password",
		mysql_root_password,
		"--no-backup",
		"--force",
	]

	# ? Launch subprocess and redirect stdout/stderr into a log file
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
			# ? Send sudo password to subprocess
			proc.stdin.write(sudo_password + "\n")
			proc.stdin.flush()
			proc.stdin.close()

			# ? Wait for process completion with timeout (10 mins)
			try:
				proc.wait(timeout=600)
			except subprocess.TimeoutExpired:
				proc.kill()
				update_deletion_log_status(
					log_name,
					new_text="\nTimed out while deleting site!\n",
					status="Error",
				)
				frappe.msgprint(
					msg=f"Timeout expired while deleting site {site_name}.",
					title="Site Deletion Timeout",
					alert=True,
					indicator="red",
				)
				return

		# ? Tail the log file and update BM Log in real-time
		with open(log_file) as f:
			f.seek(0, os.SEEK_SET)
			# ? Stream entire log file content to document
			for line in f:
				update_deletion_log_status(log_name, new_text=line)

		# ? Update status based on exit code
		if proc.returncode == 0:
			update_deletion_log_status(log_name, status="Success")
			remove_bm_site(bench_name=bench_name, bench_path=bench_path, site_name=site_name)
		else:
			update_deletion_log_status(log_name, status="Error")

	except Exception as e:
		frappe.msgprint(
			msg=f"Error While Deleting Site {site_name} in bench {bench_name}",
			title="Site Deletion Error",
			realtime=True,
			alert=True,
			indicator="red",
		)
		frappe.log_error(f"Error running bench drop-site: {e}", "BenchMate SiteDeletionLogs")
		update_deletion_log_status(log_name, status="Error")

	else:
		frappe.msgprint(
			msg=f"Site {site_name} deleted successfully from bench {bench_name}",
			title="Site Deletion Success",
			realtime=True,
			alert=True,
			indicator="green",
		)

	finally:
		# ? Always clean up the temporary log file
		try:
			if os.path.exists(log_file):
				os.remove(log_file)
		except Exception as cleanup_error:
			frappe.log_error(
				f"Failed to remove temp log file {log_file}: {cleanup_error}",
				"BenchMate SiteDeletionLogs",
			)


def remove_bm_site(bench_name: str, bench_path: str, site_name: str):
	"""
	Remove the BM Site record from the system.
	Unlinks the site from its bench and deletes its record.
	"""
	# ? Find and delete the BM Site record matching this site
	site_doc_name = frappe.db.get_value("BM Site", {"bench_name": bench_name, "site_name": site_name})
	if site_doc_name:
		frappe.delete_doc("BM Site", site_doc_name, ignore_permissions=True)
		frappe.db.commit()


@frappe.whitelist()
def execute(bench_name: str, bench_path: str, site_name: str):
	"""
	? Public API method (whitelisted) to enqueue site deletion.
	? Validates input and enqueues the background site deletion task.
	"""
	if not bench_path or not site_name:
		frappe.throw("bench_path and site_name are required", frappe.ValidationError)

	# ? Fetch global BenchMate settings (sudo password, DB password)
	settings = get_benchmate_settings()
	sudo_password = settings.get("sudo_password")
	mysql_root_password = settings.get("db_password")

	# ? Validate required passwords are configured
	if not sudo_password:
		frappe.throw("Sudo password not configured", frappe.ValidationError)
	if not mysql_root_password:
		frappe.throw("MySQL root password not configured", frappe.ValidationError)

	# ? Enqueue background task for long execution
	try:
		frappe.enqueue(
			drop_site_background,
			queue="long",
			timeout=3600,
			bench_name=bench_name,
			bench_path=bench_path,
			site_name=site_name,
			sudo_password=sudo_password,
			mysql_root_password=mysql_root_password,
		)
	except Exception as e:
		frappe.throw(f"Failed to enqueue site deletion: {e!s}")

	return {
		"success": True,
		"message": (
			f"Deleting site <b>{site_name}</b> in the background. "
			f"Check the <b>BM Log</b> for more details."
		),
		"data": None,
	}
