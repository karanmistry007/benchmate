import errno
import glob
import json
import os
import platform
import socket
import time

import frappe


def read_redis_ports(config_dir):
	"""
	Reads all `redis_*.conf` files from the given config directory
	and extracts the 'port' values used by Redis instances.
	"""
	ports = []
	# ? Loop through all redis_*.conf files inside config directory
	for conf_file in glob.glob(os.path.join(config_dir, "redis_*.conf")):
		try:
			with open(conf_file) as f:
				for line in f:
					# ? Extract port number if line starts with 'port'
					if line.strip().startswith("port"):
						port = int(line.strip().split()[1])
						ports.append(port)
						break
		except Exception:
			# ? Ignore faulty/missing config files and continue checking others
			continue
	# ? Return unique ports only
	return list(set(ports))


def read_site_ports(sites_dir):
	"""
	Reads `site_config.json` for each site inside the sites directory
	and extracts `webserver_port` and `socketio_port` values.
	"""
	ports = []
	# ? Ensure that sites folder actually exists
	if not os.path.isdir(sites_dir):
		frappe.throw(
			f"Sites directory not found at {sites_dir}",
			frappe.DoesNotExistError,
		)

	# ? Iterate over all sites present inside the sites directory
	for site_name in os.listdir(sites_dir):
		site_config_path = os.path.join(sites_dir, site_name, "site_config.json")
		if os.path.isfile(site_config_path):
			try:
				with open(site_config_path) as f:
					data = json.load(f)
					# ? Collect webserver_port if present
					if "webserver_port" in data:
						ports.append(int(data["webserver_port"]))
					# ? Collect socketio_port if present
					if "socketio_port" in data:
						ports.append(int(data["socketio_port"]))
			except Exception:
				# ? Continue checking other sites if a site config fails
				continue
	# ? Return unique site ports only
	return list(set(ports))


def stop_port(port, is_linux):
	"""
	Attempts to stop services running on a specific port.

	Args:
	port (int): Port number to stop.
	is_linux (bool): Whether the system is Linux based.

	Returns:
	bool: True if a port was in use and a stop command was attempted.
	False if port was free or no action was needed.
	"""
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	try:
		# ? Try binding to port; if succeeds, port is free (no service running)
		sock.bind(("127.0.0.1", port))
		# ? Port not in use
		return False
	except OSError as e:
		# ? If port is already in use
		if e.errno == errno.EADDRINUSE:
			# ? If port seems to be Redis (within range), attempt graceful shutdown
			if 1100 <= port <= 14000:
				os.system(f"echo 'shutdown' | redis-cli -h 127.0.0.1 -p {port} 2>/dev/null")
				# ? Give Redis process some time to shutdown
				time.sleep(1)

			# ? Force kill remaining process using OS-based commands
			if is_linux:
				os.system(f"fuser {port}/tcp -k")  # Linux command to kill process on a port
			else:
				# ? macOS fallback
				os.system(f"lsof -i tcp:{port} | grep -v PID | awk '{{print $2}}' | xargs kill")
			return True
		else:
			# ? Unexpected socket error
			return False
	finally:
		# ? Ensure socket is closed
		sock.close()


@frappe.whitelist()
def stop_bench(bench_name: str, bench_path: str):
	"""
	API method to stop bench services for the bench located at the given path.

	Args:
	bench_path (str): Absolute or relative path to the bench directory.

	Returns:
	dict: Status message and list of stopped ports enclosed in `data`.
	On error, uses frappe.throw for validation or returns structured error dict.
	"""
	try:
		# ? Validate input parameter
		if not bench_path:
			frappe.throw(
				"bench_path parameter is required.",
				frappe.ValidationError,
			)

		bench_path = os.path.abspath(bench_path)
		config_dir = os.path.join(bench_path, "config")
		sites_dir = os.path.join(bench_path, "sites")

		# ? Validate essential folders and throw if missing
		if not os.path.isdir(config_dir) or not os.path.isdir(sites_dir):
			frappe.throw(
				f"Invalid bench path or missing 'config' or 'sites' folder: {bench_path}",
				frappe.ValidationError,
			)

		is_linux = "Linux" in platform.system()

		# ? Gather all related ports from Redis + Sites configurations
		redis_ports = read_redis_ports(config_dir)
		site_ports = read_site_ports(sites_dir)
		all_ports = list(set(redis_ports + site_ports))

		if not all_ports:
			frappe.throw("No bench service ports found to stop.")

		# ? Stop all detected services running on collected ports
		for port in all_ports:
			stop_port(port, is_linux)

		# ? Return success response with data
		return {
			"success": True,
			"message": f"<b>{bench_name}</b> Bench services are stopped successfully.",
			"data": {"stopped_ports": all_ports},
		}

	except frappe.ValidationError as ve:
		# ? Raised by frappe.throw validation
		return {"success": False, "message": str(ve), "data": None}

	except Exception as e:
		# ? General unexpected error
		return {
			"success": False,
			"message": f"Error stopping bench: {e!s}",
			"data": None,
		}
