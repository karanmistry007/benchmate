import subprocess
from pathlib import Path

import frappe

from benchmate.api.utils import get_benchmate_settings


@frappe.whitelist()
def sync():
	"""Sync and return list of valid benches under default_path"""
	settings = get_benchmate_settings()
	default_path = settings.get("default_path", "/home/karan/benches/")
	return get_all_benches(default_path)


def run_cmd(cmd: str, cwd: Path | None = None) -> str | None:
	"""Run a shell command and return stdout text (or None on failure)."""
	try:
		return subprocess.check_output(cmd, cwd=cwd, shell=True, text=True, stderr=subprocess.STDOUT).strip()
	except subprocess.CalledProcessError as e:
		frappe.log_error(f"Command failed: {cmd}\n{e.output}", "BenchMate run_cmd")
		return None


def get_all_benches(default_path: str):
	"""
	Return list of all valid bench directories under default_path.
	A valid bench must contain both `sites/` dir and `Procfile`.
	"""
	benches: list[dict] = []
	root = Path(default_path).expanduser().resolve()

	if not root.exists():
		frappe.log_error(f"Path does not exist: {root}", "BenchMate Sync")
		return benches

	for entry in root.iterdir():
		if not entry.is_dir():
			continue

		# Precompute paths
		sites_path = entry / "sites"
		procfile_path = entry / "Procfile"

		# Validate bench structure
		if not (sites_path.is_dir() and procfile_path.is_file()):
			continue

		# Collect site names (skip special folders like assets)
		site_names = [s.name for s in sites_path.iterdir() if s.is_dir() and s.name != "assets"]

		benches.append(
			{
				"name": entry.name,
				"path": str(entry),
				"frappe_version": None,  # placeholder for future extension
				"sites": site_names,
				"installed_apps": {},  # placeholder for future extension
			}
		)

	return benches
