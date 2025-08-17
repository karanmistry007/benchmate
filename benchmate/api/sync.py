import ast
import configparser
import json
import subprocess
from pathlib import Path

import frappe

from benchmate.api.utils import get_benchmate_settings


@frappe.whitelist()
def sync():
	"""
	Sync and return list of all valid benches under default_path
	as configured in BenchMate settings.
	"""
	settings = get_benchmate_settings()
	default_path = settings.get("default_path", "/home/karan/benches/")
	return get_all_benches(default_path)


# -------------------------------------------------------------
# ? Utility functions
# -------------------------------------------------------------
def run_cmd(cmd: str, cwd: Path | None = None) -> str | None:
	"""
	Execute a shell command and return stdout as string.
	Returns None if the command fails.
	"""
	try:
		return subprocess.check_output(cmd, cwd=cwd, shell=True, text=True, stderr=subprocess.STDOUT).strip()
	except subprocess.CalledProcessError as e:
		frappe.log_error(f"Command failed: {cmd}\n{e.output}", "BenchMate run_cmd")
		return None


def get_git_remote(app_path: Path) -> str | None:
	"""
	Extract repo URL from .git/config (prefer upstream → origin).
	"""
	git_config = app_path / ".git" / "config"
	if not git_config.exists():
		return None

	config = configparser.ConfigParser()
	try:
		config.read(git_config)
		if config.has_section('remote "upstream"'):
			return config.get('remote "upstream"', "url", fallback=None)
		if config.has_section('remote "origin"'):
			return config.get('remote "origin"', "url", fallback=None)
	except Exception as e:
		frappe.log_error(f"Failed to parse git remote for {app_path}: {e}", "BenchMate Sync")
	return None


# -------------------------------------------------------------
# ? App title extraction
# -------------------------------------------------------------
def _parse_hooks_title(hooks_path: Path) -> str | None:
	"""
	Parse hooks.py safely using AST to extract app_title.
	"""
	if not hooks_path.exists():
		return None
	try:
		tree = ast.parse(hooks_path.read_text(encoding="utf-8"))
		for node in ast.walk(tree):
			if isinstance(node, ast.Assign):
				for target in node.targets:
					if isinstance(target, ast.Name) and target.id == "app_title":
						if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
							return node.value.value.strip()
		return None
	except Exception as e:
		frappe.log_error(f"Failed reading hooks.py for title: {hooks_path}\n{e}", "BenchMate Title")
		return None


def _parse_pyproject_name(pyproject_path: Path) -> str | None:
	"""
	Read project/app name from pyproject.toml ([project] or [tool.poetry]).
	"""
	if not pyproject_path.exists():
		return None
	try:
		# ? Python 3.11+ has tomllib in stdlib
		try:
			import tomllib  # type: ignore

			data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
		except Exception:
			# ? Fallback: very naive parsing for "name ="
			raw = pyproject_path.read_text(encoding="utf-8")
			for line in raw.splitlines():
				if line.strip().startswith("name"):
					val = line.split("=", 1)[1].strip().strip("\"'")
					if val:
						return val
			return None

		# ? PEP 621 & poetry fallback
		if "project" in data and isinstance(data["project"], dict):
			return data["project"].get("name")
		if "tool" in data and isinstance(data["tool"], dict):
			poetry = data["tool"].get("poetry")
			if isinstance(poetry, dict):
				return poetry.get("name")
		return None
	except Exception as e:
		frappe.log_error(f"Failed reading pyproject.toml: {pyproject_path}\n{e}", "BenchMate Title")
		return None


def get_app_title(app_path: Path, app_name: str) -> str:
	"""
	Best-effort app title resolution:
	1. hooks.py (app_title)
	2. pyproject.toml (project.name / poetry.name)
	3. Fallback: prettified app_name
	"""
	# ? hooks.py
	hooks_title = _parse_hooks_title(app_path / app_name / "hooks.py")
	if hooks_title:
		return hooks_title

	# ? pyproject.toml
	pyproject_name = _parse_pyproject_name(app_path / "pyproject.toml")
	if pyproject_name:
		return pyproject_name.replace("-", " ").replace("_", " ").title()

	# ? fallback: format folder name
	return app_name.replace("-", " ").replace("_", " ").title()


# -------------------------------------------------------------
# ? Bench & site parsing
# -------------------------------------------------------------
def parse_installed_apps(entry: Path) -> tuple[dict, str | None, str | None]:
	"""
	Parse bench-wide installed apps via `bench version --format json`.
	Returns:
	- installed_apps dict
	- frappe_version
	- frappe_branch
	"""
	installed_apps = {}
	frappe_version, frappe_branch = None, None

	version_json = run_cmd("bench version --format json", cwd=entry)
	if not version_json:
		return installed_apps, None, None

	try:
		apps_data = json.loads(version_json)
		if isinstance(apps_data, list):
			for app in apps_data:
				app_name = app.get("app")
				app_branch = app.get("branch")
				app_version = app.get("version")
				app_commit = app.get("commit")

				app_path = entry / "apps" / app_name
				app_repo = get_git_remote(app_path)
				app_title = get_app_title(app_path, app_name)

				installed_apps[app_name] = {
					"title": app_title,
					"branch": app_branch,
					"version": app_version,
					"commit": app_commit,
					"repo": app_repo,
				}

				# ? store frappe version/branch separately
				if app_name == "frappe":
					frappe_version, frappe_branch = app_version, app_branch
	except Exception as e:
		frappe.log_error(f"Failed to parse bench version json: {e}", "BenchMate Sync")

	return installed_apps, frappe_version, frappe_branch


def get_site_apps(bench_path: Path, site_name: str, bench_apps: dict) -> dict:
	"""
	Get installed apps for a specific site using:
	`bench --site <site> list-apps --format json`
	Filter against bench-wide apps metadata.
	"""
	cmd = f"bench --site {site_name} list-apps --format json"
	result = run_cmd(cmd, cwd=bench_path)
	if not result:
		return {}

	site_apps = {}
	try:
		data = json.loads(result)
		for app_name in data.get(site_name, []):
			if app_name in bench_apps:
				site_apps[app_name] = bench_apps[app_name]
	except Exception as e:
		frappe.log_error(f"Failed to parse site apps for {site_name}: {e}", "BenchMate Sync")

	return site_apps


def get_all_benches(default_path: str):
	"""
	Return list of all valid benches under default_path.
	Each bench includes:
	- frappe version & branch
	- installed apps metadata
	- detailed sites with site-specific installed apps
	"""
	benches: list[dict] = []
	root = Path(default_path).expanduser().resolve()

	if not root.exists():
		frappe.log_error(f"Path does not exist: {root}", "BenchMate Sync")
		return benches

	for entry in root.iterdir():
		if not entry.is_dir():
			continue

		sites_path = entry / "sites"
		procfile_path = entry / "Procfile"

		# ? validate bench structure
		if not (sites_path.is_dir() and procfile_path.is_file()):
			continue

		# ? Bench apps & frappe version/branch
		bench_apps, frappe_version, frappe_branch = parse_installed_apps(entry)

		# ? Sites metadata
		sites = []
		for s in sites_path.iterdir():
			if s.is_dir() and s.name != "assets":
				site_apps = get_site_apps(entry, s.name, bench_apps)
				sites.append(
					{
						"site_name": s.name,
						"bench_name": entry.name,
						"path": str(s),
						"installed_apps": site_apps,
					}
				)

		# ? final bench info
		benches.append(
			{
				"name": entry.name,
				"path": str(entry),
				"version": frappe_version,
				"branch": frappe_branch,
				"sites": sites,
				"installed_apps": bench_apps,
			}
		)

	return benches
