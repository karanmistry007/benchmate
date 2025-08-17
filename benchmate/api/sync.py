import ast
import configparser
import json
import subprocess
from pathlib import Path

import frappe

from benchmate.api.utils import get_benchmate_settings


# ! benchmate.api.sync.sync_bench_details
@frappe.whitelist()
def sync_bench_details():
	"""
	Sync all benches found under the default path into the 'BM Bench' DocType.

	Workflow:
	- Creates a new Bench record if it does not exist.
	- Updates fields if the Bench already exists.
	- Marks Bench as "Error" if any error was captured during sync.
	- Syncs installed apps into BM App and BM Bench doctypes.

	Returns:
		dict: {
			"success": bool,
			"message": str,
			"data": {
				"updated_benches": list[str],   # names of updated Bench docs
				"updated_apps": list[str],      # names of updated App docs
			} | None
		}
	"""
	try:
		# ? Get default benches path from settings
		settings = get_benchmate_settings()
		default_path = settings.get("default_path", "/home/karan/benches/")

		# ? Gather all benches under the default path
		benches = get_all_benches(default_path)
		updated_benches, updated_apps = [], []

		# ? Process each bench and sync into DocType
		for bench in benches:
			bench_name = bench["bench_name"]

			# ? Create or fetch BM Bench doc
			bench_doc = (
				frappe.get_doc("BM Bench", bench_name)
				if frappe.db.exists("BM Bench", bench_name)
				else frappe.new_doc("BM Bench")
			)

			# ? If error, set status as "Error" and capture details
			if bench.get("is_error", False):
				bench_doc.update(
					{
						"status": "Error",
						"error_message": bench.get("error_message"),
						"last_synced_on": frappe.utils.now(),
						"bench_name": bench_name,
						"path": bench.get("path"),
						"branch": bench.get("branch"),
						"version": bench.get("version"),
					}
				)

			# ? If no error, update valid bench details
			else:
				bench_doc.update(
					{
						"bench_name": bench_name,
						"path": bench.get("path"),
						"branch": bench.get("branch"),
						"version": bench.get("version"),
						"error_message": None,
						"last_synced_on": frappe.utils.now(),
					}
				)

				# ? Manage installed apps
				if bench.get("installed_apps"):
					# Sync installed apps in BM Apps & BM Bench doctypes
					bench_doc, synced_apps = sync_app_details(bench_doc, bench.get("installed_apps"))

					# Track updated apps if any changes were made
					if synced_apps:
						updated_apps.extend(synced_apps)

			# ? Save or update the Bench document
			bench_doc.save(ignore_permissions=True)
			updated_benches.append(bench_doc.name)

			# ? Deduplicate lists
			updated_benches = list(set(updated_benches))
			updated_apps = list(set(updated_apps))

	except Exception as e:
		# ? Rollback in case of failure
		frappe.db.rollback()

		log = json.dumps(
			{
				"success": False,
				"message": f"Bench sync failed: {e!s}",
				"data": {
					"updated_benches": updated_benches if "updated_benches" in locals() else [],
					"updated_apps": updated_apps if "updated_apps" in locals() else [],
				},
			},
			indent=4,
		)

		# ? Log sync failure
		frappe.get_doc(
			{
				"doctype": "BM Sync Log",
				"title": "Error In Bench Sync",
				"log": log,
			}
		).insert()
		frappe.db.commit()

		return {
			"success": False,
			"message": f"Bench sync failed: {e!s}",
			"data": None,
		}

	else:
		# ? Prepare sync success log
		log = json.dumps(
			{
				"success": True,
				"message": "Benches synced successfully.",
				"data": {
					"updated_benches": updated_benches,
					"updated_apps": updated_apps,
				},
			},
			indent=4,
		)

		# ? Log sync success
		frappe.get_doc(
			{
				"doctype": "BM Sync Log",
				"title": "Benches Synced Successfully",
				"log": log,
			}
		).insert()
		frappe.db.commit()

		# ? Show UI message
		frappe.msgprint(
			msg="Benches synced successfully.",
			title="Benches Synced",
			alert=True,
		)

		return {
			"success": True,
			"message": "Benches synced successfully.",
			"data": {
				"updated_benches": updated_benches,
				"updated_apps": updated_apps,
			},
		}


def sync_app_details(bench_doc, installed_apps: dict):
	"""
	Sync installed apps into the 'BM App' and 'BM Bench' DocTypes.

	Workflow:
	- Clears and resets `installed_apps` table in the BM Bench doc.
	- Creates a BM App record if it does not exist.
	- Updates fields if the App already exists.
	- Saves only if there are changes.

	Args:
		bench_doc (Document): The BM Bench document being updated.
		installed_apps (dict): Dictionary of installed apps with details.

	Returns:
		tuple:
			- bench_doc (Document): Updated BM Bench document with installed apps.
			- updated (list[str]): List of updated BM App names.
	"""
	updated = []

	# ? Reset installed_apps table in Bench doc
	bench_doc.installed_apps = []

	# ? Process each installed app
	for app in installed_apps.values():
		is_dirty = False
		app_name = app.get("app_name")

		# ? Create or fetch BM App doc
		app_doc = (
			frappe.get_doc("BM App", app_name)
			if frappe.db.exists("BM App", app_name)
			else frappe.new_doc("BM App")
		)

		# ? Update app_name if changed
		if app_doc.get("app_name") != app_name:
			app_doc.update({"app_name": app_name})
			is_dirty = True

		# ? Update app_title if changed
		if app_doc.get("app_title") != app.get("app_title"):
			app_doc.update({"app_title": app.get("app_title")})
			is_dirty = True

		# ? Update link if changed
		if app_doc.get("link") != app.get("link"):
			app_doc.update({"link": app.get("link")})
			is_dirty = True

		# ? Save BM App only if changes were made
		if is_dirty:
			app_doc.save(ignore_permissions=True)
			updated.append(app_doc.name)

		# ? Add app details to installed_apps table in Bench doc
		bench_doc.append(
			"installed_apps",
			{
				"app_name": app_name,
				"app_title": app.get("app_title"),
				"branch": app.get("branch"),
				"version": app.get("version"),
				"link": app.get("link"),
				"commit": app.get("commit"),
			},
		)

	return bench_doc, updated


# ! benchmate.api.sync.test_sync
@frappe.whitelist()
def test_sync():
	"""
	Sync and return list of all valid benches under the default_path
	configured in BenchMate settings.

	Returns:
		list[dict]: List of bench metadata with sites and installed apps.
	"""
	settings = get_benchmate_settings()
	default_path = settings.get("default_path", "/home/karan/benches/")
	return get_all_benches(default_path)


# ? -------------------------------------------------------------
# ? Utility functions
# ? -------------------------------------------------------------
def run_cmd(cmd: str, cwd: Path | None = None) -> tuple[str | None, str | None]:
	"""
	Execute a shell command.

	Args:
		cmd (str): Command to run.
		cwd (Path | None): Directory to execute in.

	Returns:
		tuple: (stdout, None) if success, else (None, error_message).
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
	Get the Git remote URL for a given app.
	Checks upstream first, then origin.

	Args:
		app_path (Path): Path to app directory.

	Returns:
		str | None: Remote repo URL if found.
	"""
	git_config = app_path / ".git" / "config"
	if not git_config.exists():
		return None

	config = configparser.ConfigParser(strict=False)  # ? allow duplicate keys
	try:
		config.read(git_config)
		if config.has_section('remote "upstream"'):
			return config.get('remote "upstream"', "url", fallback=None)
		if config.has_section('remote "origin"'):
			return config.get('remote "origin"', "url", fallback=None)
	except Exception as e:
		frappe.log_error(f"Failed to parse git remote for {app_path}: {e}", "BenchMate Sync")
	return None


# ? -------------------------------------------------------------
# ? App title extraction
# ? -------------------------------------------------------------
def _parse_hooks_title(hooks_path: Path) -> str | None:
	"""
	Extract app_title from hooks.py using AST.

	Args:
		hooks_path (Path): Path to hooks.py.

	Returns:
		str | None: app_title if found.
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
	Extract project/app name from pyproject.toml.
	Supports [project] and [tool.poetry].

	Args:
		pyproject_path (Path): Path to pyproject.toml.

	Returns:
		str | None: Name if found.
	"""
	if not pyproject_path.exists():
		return None
	try:
		try:
			import tomllib  # type: ignore

			data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
		except Exception:
			# ? Fallback: naive text parsing
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
	Resolve a human-readable app title.

	Order:
	1. hooks.py → app_title
	2. pyproject.toml → name
	3. fallback: prettified app_name

	Args:
		app_path (Path): Path to app folder.
		app_name (str): Name of app.

	Returns:
		str: App title.
	"""
	hooks_title = _parse_hooks_title(app_path / app_name / "hooks.py")
	if hooks_title:
		return hooks_title

	pyproject_name = _parse_pyproject_name(app_path / "pyproject.toml")
	if pyproject_name:
		return pyproject_name.replace("-", " ").replace("_", " ").title()

	return app_name.replace("-", " ").replace("_", " ").title()


# ? -------------------------------------------------------------
# ? Bench & site parsing
# ? -------------------------------------------------------------
def _robust_load_json_array(raw: str):
	"""
	Try to parse output as JSON/array safely.
	Handles garbage before/after JSON.

	Args:
		raw (str): Raw CLI output.

	Returns:
		Any: Parsed JSON object/list.
	"""
	try:
		return json.loads(raw)
	except Exception:
		pass

	# ? Try substring extraction
	start = raw.find("[")
	end = raw.rfind("]")
	if start != -1 and end != -1 and end > start:
		try:
			sub = raw[start : end + 1]
			return json.loads(sub)
		except Exception:
			pass

	# ? Last fallback: literal_eval
	try:
		return ast.literal_eval(raw)
	except Exception:
		raise ValueError("Unable to parse bench version output as JSON/pyliteral")


def parse_installed_apps(entry: Path) -> tuple[dict, str | None, str | None, str | None]:
	"""
	Parse installed apps for a bench.

	Args:
		entry (Path): Path to bench directory.

	Returns:
		tuple: (apps_dict, frappe_version, frappe_branch, error_message)
	"""
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

	# ? Normalize structure
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

	# ? Collect app details
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
				"app_name": app_name,
				"app_title": app_title,
				"branch": app_branch,
				"version": app_version,
				"commit": app_commit,
				"link": app_repo,
			}

			if app_name == "frappe":
				frappe_version, frappe_branch = app_version, app_branch
	except Exception as e:
		frappe.log_error(f"Unexpected error while processing bench apps for {entry}: {e}", "BenchMate Sync")

	return installed_apps, frappe_version, frappe_branch, error_message


def get_site_apps(bench_path: Path, site_name: str, bench_apps: dict) -> tuple[dict, str | None]:
	"""
	Get installed apps for a site within a bench.

	Args:
		bench_path (Path): Path to bench.
		site_name (str): Name of site.
		bench_apps (dict): Available bench apps metadata.

	Returns:
		tuple: (site_apps, error_message)
	"""
	cmd = f"bench --site {site_name} list-apps --format json"
	result, err = run_cmd(cmd, cwd=bench_path)

	if err:
		return {}, f"{bench_path} - {cmd} - {err}"

	if not result:
		return {}, None

	site_apps = {}
	try:
		# ? Use robust parser (handles stray output)
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
	"""
	Scan a given path and return all valid benches with metadata.

	Args:
		default_path (str): Root benches path.

	Returns:
		list[dict]: List of benches with their sites, apps, and status.
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

		# ? Identify valid bench (must have sites/ + Procfile)
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
				"bench_name": entry.name,
				"path": str(entry),
				"branch": frappe_branch,
				"version": frappe_version,
				"sites": sites,
				"installed_apps": bench_apps,
				"is_error": is_error,
				"error_message": error_message,
			}
		)

	return benches
