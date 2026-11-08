"""Read-only dependency discovery and explicit, missing-only service installation.

``doctor`` never launches a process. Credential fields contain presence booleans;
private configuration, registry values and subprocess output are never returned.
Only ``install-missing`` may download or change a service installation.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


SKILLS = ("flyai", "amap-lbs-skill", "video-report", "ego-browser")
FLYAI_PACKAGE = Path("node_modules/@fly-ai/flyai-cli/dist/flyai-bundle.cjs")
AMAP_SOURCE = "https://clawhub.ai/lbs-amap/skills/amap-lbs-skill"


def checked_at():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _windows_user_environment():
    """Read only the two registry entries needed for presence and executable lookup."""
    if os.name != "nt":
        return {}
    import winreg
    result = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            for name in ("AMAP_WEBSERVICE_KEY", "Path"):
                try:
                    value = winreg.QueryValueEx(key, name)[0]
                    result[name] = value if isinstance(value, str) else ""
                except OSError:
                    pass
    except OSError:
        pass
    return result


def _context(home=None, env=None, workspace=None, user_environment=None):
    home = Path(home) if home is not None else Path.home()
    env = dict(os.environ if env is None else env)
    workspace = Path(workspace) if workspace is not None else Path.cwd()
    user_environment = (_windows_user_environment() if user_environment is None
                        else dict(user_environment))
    return home, env, workspace, user_environment


def _first_file(paths):
    for path in paths:
        if path.is_file():
            return str(path.resolve())
    return None


def _which(name, env, which=None, user_environment=None):
    if which is not None:
        return which(name)
    search_path = env.get("PATH", "")
    user_path = (user_environment or {}).get("Path", "")
    if user_path:
        search_path += os.pathsep + os.path.expandvars(user_path)
    return shutil.which(name, path=search_path)


def find_skill(name, *, home, env):
    roots = (Path(env.get("CODEX_HOME") or home / ".codex") / "skills",
             home / ".agents/skills")
    for root in roots:
        candidate = root / name
        if (candidate / "SKILL.md").is_file():
            return {"installed": True, "path": str(candidate.absolute()),
                    "resolved_path": str(candidate.resolve())}
    return {"installed": False, "path": None, "resolved_path": None}


def find_flyai_bundle(*, home, env, launcher=None, node=None, workspace=None):
    """Locate the real npm bundle without executing an npm/PowerShell launcher."""
    prefixes = [Path(env.get("APPDATA") or home / "AppData/Roaming") / "npm"]
    for key in ("npm_config_prefix", "NPM_CONFIG_PREFIX"):
        if env.get(key):
            prefixes.append(Path(env[key]))
    for executable in (launcher, node):
        if executable:
            path = Path(executable)
            if path.is_file() and path.name == "flyai-bundle.cjs":
                return str(path.resolve())
            prefixes.extend((path.parent, path.resolve().parent,
                             path.resolve().parent.parent))
    if workspace is not None:
        prefixes.append(Path(workspace))
    if os.name != "nt":
        prefixes.extend((Path("/usr/local"), Path("/usr")))
    return _first_file(candidate for prefix in prefixes
                       for candidate in (prefix / FLYAI_PACKAGE,
                                         prefix / "lib" / FLYAI_PACKAGE))


def _runtime_roots(workspace, report_skill):
    roots = [workspace.resolve()]
    if report_skill["installed"]:
        resolved = Path(report_skill["resolved_path"])
        roots.extend((resolved, *resolved.parents))
    return tuple(dict.fromkeys(roots))


def _axios_path(skill):
    if not skill["installed"]:
        return None
    resolved = Path(skill["resolved_path"])
    return _first_file(root / "node_modules/axios/package.json"
                       for root in (resolved, *resolved.parents))


def doctor(*, home=None, env=None, workspace=None, which=None, user_environment=None):
    """Return JSON-safe skills/tools/packages/credentials/ready fields, offline.

    ``home``, ``env``, ``which`` and ``user_environment`` can be supplied for
    isolated tests; no actual account configuration needs to be read in tests.
    ``tools.flyai.bundle`` identifies the node entry point used by flyai_query.
    """
    home, env, workspace, user_environment = _context(home, env, workspace, user_environment)
    skills = {name: find_skill(name, home=home, env=env) for name in SKILLS}
    lookup = lambda name: _which(name, env, which, user_environment)
    node = lookup("node")
    if not node:
        node = _first_file([
            Path(env.get("ProgramFiles") or "C:/Program Files") / "nodejs/node.exe",
            home / "AppData/Local/Programs/nodejs/node.exe",
        ]) if which is None else None
    launcher = lookup("flyai")
    bundle = find_flyai_bundle(home=home, env=env, launcher=launcher, node=node,
                               workspace=workspace)
    roots = _runtime_roots(workspace, skills["video-report"])
    tool_paths = {"node": node, "ego-browser": lookup("ego-browser")}
    for name in ("ffmpeg", "ffprobe"):
        override = env.get("VIDEO_REPORT_" + name.upper())
        candidates = [Path(override).expanduser()] if override else []
        candidates.extend(root / sub / filename
                          for root in roots
                          for sub in (".tools/bin", ".tools/ffmpeg/bin")
                          for filename in (name + ".exe", name))
        tool_paths[name] = _first_file(candidates[:1]) if override else None
        tool_paths[name] = tool_paths[name] or lookup(name) or _first_file(candidates)
    python_override = env.get("VIDEO_REPORT_PYTHON")
    python_candidates = [Path(python_override).expanduser()] if python_override else []
    python_candidates.extend(root / sub for root in roots
                             for sub in (".venv/Scripts/python.exe", ".venv/bin/python"))
    tool_paths["video-report-python"] = _first_file(python_candidates)
    tools = {name: {"available": bool(path), "path": str(path) if path else None}
             for name, path in tool_paths.items()}
    tools["flyai"] = {"available": bool(bundle), "path": launcher or bundle,
                       "bundle": bundle, "launcher_path": launcher}
    config_path = home / ".flyai/config.json"
    private_key = False
    if config_path.is_file():
        try:
            # Presence inspection is bounded; malformed content is never echoed.
            if config_path.stat().st_size <= 1024 * 1024:
                config = json.loads(config_path.read_text(encoding="utf-8-sig"))
                private_key = (isinstance(config, dict)
                               and isinstance(config.get("FLYAI_API_KEY"), str)
                               and bool(config["FLYAI_API_KEY"].strip()))
        except (OSError, ValueError):
            pass
    flyai_env = bool(str(env.get("FLYAI_API_KEY", "")).strip())
    amap_process = bool(str(env.get("AMAP_WEBSERVICE_KEY", "")).strip())
    amap_user = bool(str(user_environment.get("AMAP_WEBSERVICE_KEY", "")).strip())
    credentials = {
        "flyai": {"config_exists": config_path.is_file(),
                  "key_configured": bool(private_key or flyai_env),
                  "environment_configured": flyai_env},
        "amap": {"key_configured": amap_process or amap_user,
                 "process_environment": amap_process, "user_environment": amap_user},
    }
    axios = _axios_path(skills["amap-lbs-skill"])
    return {"schema_version": 1, "checked_at": checked_at(), "read_only": True,
            "skills": skills, "tools": tools,
            "packages": {"amap-axios": {"available": bool(axios), "path": axios}},
            "credentials": credentials,
            "ready": {
                "flyai_query": bool(skills["flyai"]["installed"] and node and bundle),
                "amap_query": bool(skills["amap-lbs-skill"]["installed"] and node
                                   and axios and credentials["amap"]["key_configured"]),
                "browser": bool(skills["ego-browser"]["installed"] and tools["ego-browser"]["available"]),
                "video": bool(skills["video-report"]["installed"] and all(
                    tools[name]["available"] for name in ("ffmpeg", "ffprobe", "video-report-python"))),
            }}


def prepare_command(argv, *, windows=None):
    """Keep subprocess arguments separate, including trusted Windows .cmd calls.

    No user-supplied command text is accepted by installation commands. Shell
    expansion characters are additionally rejected for the .cmd fallback.
    Native node/npm entry points are preferred by ``_package_manager``.
    """
    argv = [str(value) for value in argv]
    windows = os.name == "nt" if windows is None else windows
    if not windows or Path(argv[0]).suffix.lower() not in (".cmd", ".bat"):
        return argv
    if any(any(character in value for character in '"%!&|<>^()\r\n\x00') for value in argv):
        raise ValueError("Unsafe expansion character in Windows installation arguments")
    # ``call`` keeps the /c command from beginning with a quoted executable.
    # Python quotes paths containing spaces when serializing this argument array.
    return ["cmd.exe", "/d", "/v:off", "/s", "/c", "call", *argv]


def _package_manager(name, *, home, env, which, user_environment, node):
    executable = _which(name, env, which, user_environment)
    if not executable:
        return None
    if Path(executable).suffix.lower() in (".cmd", ".bat", ".ps1") and node:
        entries = [Path(node).parent / f"node_modules/npm/bin/{name}-cli.js",
                   Path(executable).parent / f"node_modules/npm/bin/{name}-cli.js"]
        entry = _first_file(entries)
        if entry:
            return [node, entry]
    if Path(executable).suffix.lower() == ".ps1":
        cmd = Path(executable).with_suffix(".cmd")
        return [str(cmd)] if cmd.is_file() else None
    return [str(executable)]


def install_missing(*, home=None, env=None, workspace=None, which=None,
                    user_environment=None, runner=None):
    """Install absent FlyAI/amap pieces only; never install a browser or set keys.

    ``ok`` describes these four requested install targets. Missing Node, video
    tools or browser remain visible in ``after``; they are not auto-installed.
    Each action reports a fixed name/status/process_exit, never raw tool output.
    """
    home, env, workspace, user_environment = _context(home, env, workspace, user_environment)
    runner = subprocess.run if runner is None else runner
    options = dict(home=home, env=env, workspace=workspace, which=which,
                   user_environment=user_environment)
    before = doctor(**options)
    state = before
    actions = []
    codex_home = Path(env.get("CODEX_HOME") or home / ".codex")

    def execute(name, command, present):
        nonlocal state
        if command is None:
            actions.append({"name": name, "status": "blocked", "process_exit": None,
                            "message": "Required local installer or Node package manager is unavailable."})
            return
        try:
            result = runner(prepare_command(command), shell=False, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=300,
                            env=env, cwd=str(workspace))
            state = doctor(**options)
            success = result.returncode == 0 and present(state)
            actions.append({"name": name, "status": "installed" if success else "failed",
                            "process_exit": result.returncode})
        except (OSError, ValueError, subprocess.SubprocessError):
            actions.append({"name": name, "status": "failed", "process_exit": None,
                            "message": "Installation could not complete; subprocess diagnostics were suppressed."})

    if not state["skills"]["flyai"]["installed"]:
        installer = codex_home / "skills/.system/skill-installer/scripts/install-skill-from-github.py"
        command = ([sys.executable, str(installer), "--repo", "alibaba-flyai/flyai-skill",
                    "--path", "skills/flyai", "--dest", str(codex_home / "skills")]
                   if installer.is_file() else None)
        execute("flyai-skill", command, lambda report: report["skills"]["flyai"]["installed"])
    node = state["tools"]["node"]["path"]
    npm = (_package_manager("npm", home=home, env=env, which=which,
                            user_environment=user_environment, node=node) if node else None)
    if not state["tools"]["flyai"]["available"]:
        execute("flyai-cli", npm + ["install", "--global", "@fly-ai/flyai-cli"] if npm else None,
                lambda report: report["tools"]["flyai"]["available"])
    if not state["skills"]["amap-lbs-skill"]["installed"]:
        npx = (_package_manager("npx", home=home, env=env, which=which,
                                user_environment=user_environment, node=node) if node else None)
        command = npx + ["--yes", "skills@1.7.6", "add", AMAP_SOURCE,
                         "--global", "--yes", "--agent", "codex"] if npx else None
        execute("amap-skill", command, lambda report: report["skills"]["amap-lbs-skill"]["installed"])
    if state["skills"]["amap-lbs-skill"]["installed"] and not state["packages"]["amap-axios"]["available"]:
        directory = state["skills"]["amap-lbs-skill"]["resolved_path"]
        command = npm + ["install", "--prefix", directory, "--no-save", "--ignore-scripts",
                         "--omit=dev", "--no-audit", "--no-fund", "axios"] if npm else None
        execute("amap-axios", command, lambda report: report["packages"]["amap-axios"]["available"])
    after = doctor(**options)
    return {"schema_version": 1, "checked_at": checked_at(),
            "ok": (all(action["status"] == "installed" for action in actions)
                   and after["skills"]["flyai"]["installed"]
                   and after["skills"]["amap-lbs-skill"]["installed"]
                   and after["tools"]["flyai"]["available"]
                   and after["packages"]["amap-axios"]["available"]),
            "actions": actions, "before": before, "after": after}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("doctor", "install-missing"), nargs="?", default="doctor")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(),
                        help="Task directory for portable video tools and virtualenv discovery")
    args = parser.parse_args(argv)
    try:
        result = doctor(workspace=args.workspace) if args.command == "doctor" else install_missing(workspace=args.workspace)
    except (OSError, ValueError):
        print(json.dumps({"error": "Dependency inspection could not complete; no private diagnostics were emitted."}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if args.command == "doctor" or result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
