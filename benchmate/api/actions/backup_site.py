import os
import subprocess
import time

import frappe

from benchmate.api.utils import get_benchmate_settings


def update_backup_log_status(docname, new_text=None, status=None):
	"""
	Update the BM Log record for a given docname.
	Appends log text and/or updates the status field, committing immediately.
	"""
	try:
		log_doc = frappe.get_doc("BM Log", docname)

		# Append new log text if provided
		if new_text:
			updated_log = (log_doc.log or "") + new_text
			log_doc.db_set("log", updated_log, update_modified=False)

		# Update status if provided
		if status:
			log_doc.db_set("status", status, update_modified=False)

		frappe.db.commit()
		log_doc.reload()
	except Exception as e:
		frappe.log_error(f"Error updating BM Log: {e}", "BenchMate SiteBackupLogs")


def backup_site_background(bench_name: str, bench_path: str, site_name: str, sudo_password: str):
	"""
	Background task to take a backup of a Frappe site inside a given bench.
	Captures real-time logs into BM Log doctype,
	and cleans up temporary log files after completion.
	"""
	bench_path = os.path.abspath(bench_path)
	log_file = os.path.join(bench_path, f"bench_backup_site_{site_name}.log")

	# Create a unique BM Log record for tracking
	log_timestamp = int(time.time())
	log_name = f"Backup Site-{log_timestamp}"
	if not frappe.db.exists("BM Log", log_name):
		frappe.get_doc(
			{
				"doctype": "BM Log",
				"title": f"Backup Site - {site_name}",
				"log": "",
				"log_timestamp": log_timestamp,
				"status": "In Process",
				"action": "Backup Site",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	# Command to run backup with files
	cmd = [
		"sudo",
		"-S",
		"bench",
		"--site",
		site_name,
		"backup",
		"--with-files",
	]

	try:
		# Launch subprocess and redirect stdout/stderr into a log file
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

			# Wait for process completion with timeout (15 mins)
			try:
				proc.wait(timeout=900)
			except subprocess.TimeoutExpired:
				proc.kill()
				update_backup_log_status(
					log_name,
					new_text="\nTimed out while taking backup!\n",
					status="Error",
				)
				frappe.msgprint(
					msg=f"Timeout expired while backing up site {site_name}.",
					title="Site Backup Timeout",
					alert=True,
					indicator="red",
				)
				return

		# Tail the log file and update BM Log in real-time
		with open(log_file) as f:
			f.seek(0, os.SEEK_SET)
			for line in f:
				update_backup_log_status(log_name, new_text=line)

		# Update status based on exit code
		if proc.returncode == 0:
			update_backup_log_status(log_name, status="Success")
		else:
			update_backup_log_status(log_name, status="Error")

	except Exception as e:
		frappe.msgprint(
			msg=f"Error while taking backup of site {site_name} in bench {bench_name}",
			title="Site Backup Error",
			realtime=True,
			alert=True,
			indicator="red",
		)
		frappe.log_error(f"Error running bench backup: {e}", "BenchMate SiteBackupLogs")
		update_backup_log_status(log_name, status="Error")

	else:
		frappe.msgprint(
			msg=f"Backup for site {site_name} completed successfully in bench {bench_name}",
			title="Site Backup Success",
			realtime=True,
			alert=True,
			indicator="green",
		)

	finally:
		# Always clean up the temporary log file
		try:
			if os.path.exists(log_file):
				os.remove(log_file)
		except Exception as cleanup_error:
			frappe.log_error(
				f"Failed to remove temp log file {log_file}: {cleanup_error}",
				"BenchMate SiteBackupLogs",
			)


@frappe.whitelist()
def execute(bench_name: str, bench_path: str, site_name: str):
	"""
	Public API method (whitelisted) to enqueue site backup.
	Validates input and enqueues the background site backup task.
	"""
	if not bench_path or not site_name:
		frappe.throw("bench_path and site_name are required", frappe.ValidationError)

	# Fetch global BenchMate settings (sudo password)
	settings = get_benchmate_settings()
	sudo_password = settings.get("sudo_password")

	if not sudo_password:
		frappe.throw("Sudo password not configured", frappe.ValidationError)

	try:
		frappe.enqueue(
			backup_site_background,
			queue="long",
			timeout=3600,
			bench_name=bench_name,
			bench_path=bench_path,
			site_name=site_name,
			sudo_password=sudo_password,
		)
	except Exception as e:
		frappe.throw(f"Failed to enqueue site backup: {e!s}")

	return {
		"success": True,
		"message": (
			f"Backing up site <b>{site_name}</b> in the background. Check the <b>BM Log</b> for more details."
		),
		"data": None,
	}
