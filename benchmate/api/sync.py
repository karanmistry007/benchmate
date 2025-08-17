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
def run_cmd(cmd: str, cwd: Path | None = None) -> tuple[str | None, str | None]:
	"""
	Execute a shell command and return stdout as string.
	Returns (stdout, None) if success.
	Returns (None, "command: error_message") if the command fails.
	"""
	try:
		out = subprocess.check_output(cmd, cwd=cwd, shell=True, text=True, stderr=subprocess.STDOUT).strip()
		return out, None
	except subprocess.CalledProcessError as e:
		error_message = e.output.strip() if e.output else str(e)
		frappe.log_error(f"Command failed: {cmd}\n{e.output}", "BenchMate run_cmd")
		return None, error_message


def get_git_remote(app_path: Path) -> str | None:
	"""
	Extract repo URL from .git/config (prefer upstream → origin).
	"""
	git_config = app_path / ".git" / "config"
	if not git_config.exists():
		return None

	config = configparser.ConfigParser(strict=False)  # allow duplicate options
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
		try:
			import tomllib  # type: ignore

			data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
		except Exception:
			raw = pyproject_path.read_text(encoding="utf-8")
			for line in raw.splitlines():
				if line.strip().startswith("name"):
					val = line.split("=", 1)[1].strip().strip("\"'")
					if val:
						return val
			return None

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
	hooks_title = _parse_hooks_title(app_path / app_name / "hooks.py")
	if hooks_title:
		return hooks_title

	pyproject_name = _parse_pyproject_name(app_path / "pyproject.toml")
	if pyproject_name:
		return pyproject_name.replace("-", " ").replace("_", " ").title()

	return app_name.replace("-", " ").replace("_", " ").title()


# -------------------------------------------------------------
# ? Bench & site parsing
# -------------------------------------------------------------
def _robust_load_json_array(raw: str):
	try:
		return json.loads(raw)
	except Exception:
		pass

	start = raw.find("[")
	end = raw.rfind("]")
	if start != -1 and end != -1 and end > start:
		try:
			sub = raw[start : end + 1]
			return json.loads(sub)
		except Exception:
			pass

	try:
		return ast.literal_eval(raw)
	except Exception:
		raise ValueError("Unable to parse bench version output as JSON/pyliteral")


def parse_installed_apps(entry: Path) -> tuple[dict, str | None, str | None, str | None]:
	installed_apps = {}
	frappe_version, frappe_branch, error_message = None, None, None

	version_json, err = run_cmd("bench version --format json", cwd=entry)
	if err:
		return installed_apps, None, None, f"{entry} - bench version --format json - {err}"

	if not version_json:
		return installed_apps, None, None, None

	try:
		apps_data = _robust_load_json_array(version_json)
	except Exception as e:
		frappe.log_error(f"bench version returned non-JSON output for {entry}: {e}", "BenchMate Sync")
		return installed_apps, None, None, None

	try:
		if isinstance(apps_data, dict):
			found_list = None
			for v in apps_data.values():
				if isinstance(v, list):
					found_list = v
					break
			apps = found_list or []
		elif isinstance(apps_data, list | tuple):
			apps = list(apps_data)
		else:
			apps = []
	except Exception:
		apps = []

	try:
		for app in apps:
			if not isinstance(app, dict):
				continue
			app_name = app.get("app")
			if not app_name:
				continue
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

			if app_name == "frappe":
				frappe_version, frappe_branch = app_version, app_branch
	except Exception as e:
		frappe.log_error(f"Unexpected error while processing bench apps for {entry}: {e}", "BenchMate Sync")

	return installed_apps, frappe_version, frappe_branch, error_message


def get_site_apps(bench_path: Path, site_name: str, bench_apps: dict) -> tuple[dict, str | None]:
	cmd = f"bench --site {site_name} list-apps --format json"
	result, err = run_cmd(cmd, cwd=bench_path)

	if err:
		return {}, f"{bench_path} - {cmd} - {err}"

	if not result:
		return {}, None

	site_apps = {}
	try:
		# try robust parser (handles garbage around JSON)
		data = _robust_load_json_array(result)

		if isinstance(data, dict):
			app_list = data.get(site_name) or next((v for v in data.values() if isinstance(v, list)), [])
		elif isinstance(data, list):
			app_list = data
		else:
			app_list = []

		for app_name in app_list or []:
			if app_name in bench_apps:
				site_apps[app_name] = bench_apps[app_name]

	except Exception as e:
		frappe.log_error(
			f"{cmd} returned invalid JSON for site {site_name}: {e}\nRaw Output:\n{result}", "BenchMate Sync"
		)

	return site_apps, None


def get_all_benches(default_path: str):
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

		if not (sites_path.is_dir() and procfile_path.is_file()):
			continue

		is_error = False
		error_message = None

		bench_apps, frappe_version, frappe_branch, err = parse_installed_apps(entry)
		if err:
			is_error, error_message = True, err

		sites = []
		for s in sites_path.iterdir():
			if s.is_dir() and s.name != "assets":
				site_apps, site_err = get_site_apps(entry, s.name, bench_apps)
				if site_err and not error_message:
					is_error, error_message = True, site_err
				sites.append(
					{
						"site_name": s.name,
						"bench_name": entry.name,
						"path": str(s),
						"installed_apps": site_apps,
					}
				)

		benches.append(
			{
				"name": entry.name,
				"path": str(entry),
				"version": frappe_version,
				"branch": frappe_branch,
				"sites": sites,
				"installed_apps": bench_apps,
				"is_error": is_error,
				"error_message": error_message,
			}
		)

	return benches
