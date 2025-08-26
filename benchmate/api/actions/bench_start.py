import os
import platform
import subprocess

import frappe


@frappe.whitelist()
def execute(bench_name: str, bench_path: str):
	"""
	Start all services of a given bench in the background.
	This will simulate `bench start` using nohup and run it detached.
	"""
	try:
		if not bench_path:
			frappe.throw("bench_path parameter is required.", frappe.ValidationError)

		bench_path = os.path.abspath(bench_path)

		if not os.path.isdir(bench_path):
			frappe.throw(f"Invalid bench path: {bench_path}", frappe.ValidationError)

		is_linux = "Linux" in platform.system()

		if is_linux:
			# nohup will detach the bench start process so it survives API exit
			log_file = os.path.join(bench_path, "bench_start.log")
			cmd = f"nohup {bench_path}/env/bin/bench start > {log_file} 2>&1 &"

			subprocess.Popen(
				cmd,
				shell=True,
				cwd=bench_path,
				stdout=subprocess.DEVNULL,
				stderr=subprocess.DEVNULL,
				preexec_fn=os.setpgrp,
			)

		else:
			# Windows fallback (though not common for benches)
			cmd = "bench start"
			subprocess.Popen(
				cmd,
				shell=True,
				cwd=bench_path,
				stdout=subprocess.DEVNULL,
				stderr=subprocess.DEVNULL,
			)

		return {
			"success": True,
			"message": f"Bench '{bench_name}' services start command issued successfully.",
			"data": {"bench_path": bench_path},
		}

	except frappe.ValidationError as ve:
		return {"success": False, "message": str(ve), "data": None}

	except Exception as e:
		return {
			"success": False,
			"message": f"Error starting bench: {e}",
			"data": None,
		}
