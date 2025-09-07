import os
import subprocess
import time

import frappe

from benchmate.api.utils import get_benchmate_settings


def update_log_status(docname, new_text=None, status=None):
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

		# ? Update status if provided (e.g., "In Process", "Success", "Error")
		if status:
			log_doc.db_set("status", status, update_modified=False)

		frappe.db.commit()
		log_doc.reload()
	except Exception as e:
		frappe.log_error(f"Error updating BM Log: {e}", "BenchMate SiteCreationLogs")


def create_site_background(
	bench_name: str, bench_path: str, site_name: str, sudo_password: str, mysql_root_password: str
):
	"""
	Background task to create a new Frappe site inside a given bench.
	Captures real-time logs into BM Log doctype,
	and cleans up temporary log files after completion.
	"""
	bench_path = os.path.abspath(bench_path)
	log_file = os.path.join(bench_path, f"bench_new_site_{site_name}.log")

	# ? Create a unique BM Log record for tracking
	log_timestamp = int(time.time())
	log_name = f"Create Site-{log_timestamp}"
	if not frappe.db.exists("BM Log", log_name):
		frappe.get_doc(
			{
				"doctype": "BM Log",
				"title": f"Create Site - {site_name}",
				"log": "",
				"log_timestamp": log_timestamp,
				"status": "In Process",
				"action": "Create Site",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	# ? Command to create a new site with root DB password and default admin password
	cmd = [
		"sudo",
		"-S",
		"bench",
		"new-site",
		site_name,
		"--db-root-password",
		mysql_root_password,
		"--admin-password",
		"root",
		"--verbose",
	]

	# ? Launch subprocess and redirect stdout/stderr into a log file
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

	# ? Tail the log file and update BM Log in real-time
	try:
		with open(log_file) as f:
			f.seek(0, os.SEEK_END)  # ? Move to end for live tailing
			while proc.poll() is None:
				where = f.tell()
				line = f.readline()
				if not line:
					time.sleep(1)
					f.seek(where)
				else:
					update_log_status(log_name, new_text=line)

			# ? Capture any remaining output after process finishes
			remaining = f.read()
			if remaining:
				update_log_status(log_name, new_text=remaining)

		# ? Update status based on exit code
		if proc.returncode == 0:
			update_log_status(log_name, status="Success")
			create_bm_site(bench_name=bench_name, bench_path=bench_path, site_name=site_name)

		else:
			update_log_status(log_name, status="Error")

	except Exception as e:
		frappe.msgprint(
			msg=f"Error While Creating Site {site_name} in bench {bench_name}",
			title="Site Creation Error",
			realtime=True,
			alert=True,
			indicator="red",
		)
		frappe.log_error(f"Error tailing bench new-site log: {e}", "BenchMate SiteCreationLogs")
		update_log_status(log_name, status="Error")

	else:
		frappe.msgprint(
			msg=f"Site {site_name} created successfully. in bench {bench_name}",
			title="Site Creation Success",
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
				"BenchMate SiteCreationLogs",
			)


def create_bm_site(bench_name: str, bench_path: str, site_name: str):
	"""
	Create a new BM Site record in the system.
	Links the site to its bench, sets its status as Active,
	adds metadata (path, sync time), and attaches default apps.
	"""

	# ? Initialize a new BM Site document
	bm_site_doc = frappe.new_doc("BM Site")

	# ? Populate the BM Site document with essential details
	bm_site_doc.update(
		{
			"bench_name": bench_name,
			"bench_path": bench_path,
			"site_name": site_name,
			"status": "Active",
			"last_synced_on": frappe.utils.now_datetime(),
			"path": os.path.join(bench_path, "sites", site_name),
		}
	)

	# ? Fetch default frappe app metadata from BM Installed Apps for this bench
	bm_bench_default_apps = (
		frappe.db.get_value(
			"BM Installed Apps",
			{
				"parent": bench_name,
				"app_name": "frappe",
			},
			[
				"app_name",
				"app_title",
				"branch",
				"version",
				"link",
				"commit",
			],
			as_dict=1,
		)
		or {}
	)

	# ? Attach frappe app metadata into the site's installed apps child table
	bm_site_doc.append("installed_apps", bm_bench_default_apps)

	# ? Save the BM Site record into the database
	bm_site_doc.insert()

	# ? Commit immediately to make sure the new site is persisted
	frappe.db.commit()


@frappe.whitelist()
def execute(bench_name: str, bench_path: str, site_name: str):
	"""
	? Public API method (whitelisted) to enqueue site creation.
	? Validates input and enqueues the background site creation task.
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
			create_site_background,
			queue="long",
			timeout=3600,
			bench_name=bench_name,
			bench_path=bench_path,
			site_name=site_name,
			sudo_password=sudo_password,
			mysql_root_password=mysql_root_password,
		)
	except Exception as e:
		frappe.throw(f"Failed to enqueue site creation: {e!s}")

	return {
		"success": True,
		"message": f"Creating <b>{site_name}</b> in background Check <b>BM Log</b> for more details.",
		"data": {"bench_path": bench_path},
	}
