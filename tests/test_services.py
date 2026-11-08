"""Offline service tests: temporary installations and injected process results only."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


class TemporaryInstallation(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.workspace = self.root / "work"
        self.workspace.mkdir()
        self.env = {"CODEX_HOME": str(self.home / ".codex"), "PATH": ""}
        self.binaries = {}

    def touch(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return path

    def skill(self, name, agent=False):
        directory = "home/.agents/skills" if agent else "home/.codex/skills"
        return self.touch(f"{directory}/{name}/SKILL.md").parent

    def tool(self, name):
        path = self.touch(f"bin/{name}.exe")
        self.binaries[name] = str(path)
        return path

    def bundle(self):
        return self.touch("home/AppData/Roaming/npm/node_modules/@fly-ai/flyai-cli/dist/flyai-bundle.cjs")

    def doctor(self, **kwargs):
        return self.dependencies.doctor(home=self.home, workspace=self.workspace,
                                        env=self.env, which=self.binaries.get,
                                        user_environment={}, **kwargs)

    def complete_installation(self):
        for name in ("flyai", "amap-lbs-skill", "video-report", "ego-browser"):
            self.skill(name)
        self.tool("node")
        self.tool("ego-browser")
        self.bundle()
        self.touch("home/.codex/skills/amap-lbs-skill/node_modules/axios/package.json")
        self.touch("work/.tools/bin/ffmpeg.exe")
        self.touch("work/.tools/bin/ffprobe.exe")
        self.touch("work/.venv/Scripts/python.exe")


class DependencyTests(TemporaryInstallation):
    def setUp(self):
        super().setUp()
        try:
            self.dependencies = importlib.import_module("dependencies")
        except ModuleNotFoundError:
            self.fail("dependencies.py must implement the offline dependency doctor")

    def test_doctor_discovers_both_skill_roots_and_reports_missing_tools(self):
        self.skill("flyai")
        amap = self.skill("amap-lbs-skill", agent=True)
        report = self.doctor()
        self.assertTrue(report["read_only"])
        self.assertTrue(report["skills"]["flyai"]["installed"])
        self.assertEqual(report["skills"]["amap-lbs-skill"]["resolved_path"], str(amap.resolve()))
        self.assertFalse(report["skills"]["video-report"]["installed"])
        self.assertFalse(report["tools"]["node"]["available"])

    def test_doctor_finds_report_repository_tools_using_resolved_junction_target(self):
        report_skill = self.root / "report-repo/skills/video-report"
        report_skill.mkdir(parents=True)
        (report_skill / "SKILL.md").write_text("report", encoding="utf-8")
        linked = self.home / ".codex/skills/video-report"
        ffmpeg = self.touch("report-repo/.tools/bin/ffmpeg.exe")
        ffprobe = self.touch("report-repo/.tools/bin/ffprobe.exe")
        python = self.touch("report-repo/.venv/Scripts/python.exe")
        # Inject only the filesystem's junction resolution result. Windows junction
        # creation requires privileges; repository discovery itself stays real.
        original = self.dependencies.find_skill
        def resolved_skill(name, **kwargs):
            if name == "video-report":
                return {"installed": True, "path": str(linked),
                        "resolved_path": str(report_skill.resolve())}
            return original(name, **kwargs)
        with patch.object(self.dependencies, "find_skill", side_effect=resolved_skill):
            report = self.doctor()
        self.assertEqual(report["skills"]["video-report"]["resolved_path"], str(report_skill.resolve()))
        for name, path in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe), ("video-report-python", python)):
            self.assertEqual(report["tools"][name]["path"], str(path.resolve()))

    def test_doctor_never_runs_processes_or_changes_private_configuration(self):
        private = self.home / ".flyai/config.json"
        private.parent.mkdir(parents=True)
        private.write_text('{"FLYAI_API_KEY":"private-key-sentinel"}', encoding="utf-8")
        before = private.read_bytes()
        with patch("subprocess.run", side_effect=AssertionError("doctor must be read-only")):
            report = self.doctor()
        self.assertTrue(report["credentials"]["flyai"]["config_exists"])
        self.assertTrue(report["credentials"]["flyai"]["key_configured"])
        self.assertNotIn("private-key-sentinel", json.dumps(report))
        self.assertEqual(private.read_bytes(), before)

    def test_doctor_reports_environment_key_booleans_without_values(self):
        self.env.update(FLYAI_API_KEY="fly-secret", AMAP_WEBSERVICE_KEY="amap-secret")
        report = self.doctor()
        self.assertTrue(report["credentials"]["flyai"]["environment_configured"])
        self.assertTrue(report["credentials"]["amap"]["process_environment"])
        self.assertNotIn("fly-secret", json.dumps(report))
        self.assertNotIn("amap-secret", json.dumps(report))

    def test_doctor_detects_windows_user_key_without_copying_it(self):
        report = self.dependencies.doctor(home=self.home, env=self.env,
            workspace=self.workspace, which=self.binaries.get,
            user_environment={"AMAP_WEBSERVICE_KEY": "registry-secret"})
        self.assertTrue(report["credentials"]["amap"]["user_environment"])
        self.assertTrue(report["credentials"]["amap"]["key_configured"])
        self.assertNotIn("registry-secret", json.dumps(report))

    def test_invalid_private_json_is_not_echoed_or_considered_configured(self):
        config = self.touch("home/.flyai/config.json")
        config.write_text('{"FLYAI_API_KEY":"do-not-echo"', encoding="utf-8")
        report = self.doctor()
        self.assertTrue(report["credentials"]["flyai"]["config_exists"])
        self.assertFalse(report["credentials"]["flyai"]["key_configured"])
        self.assertNotIn("do-not-echo", json.dumps(report))

    def test_install_missing_is_noop_when_dependencies_exist(self):
        self.complete_installation()
        calls = []
        report = self.dependencies.install_missing(home=self.home, env=self.env,
            workspace=self.workspace, which=self.binaries.get, user_environment={},
            runner=lambda *args, **kwargs: calls.append(args))
        self.assertEqual(calls, [])
        self.assertEqual(report["actions"], [])
        self.assertTrue(report["ok"])

    def test_install_missing_uses_official_sources_and_installs_only_absent_parts(self):
        self.tool("node")
        npm = self.tool("npm")
        npx = self.tool("npx")
        installer = self.touch("home/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py")
        calls = []

        def run(argv, **kwargs):
            self.assertIsInstance(argv, list)
            self.assertFalse(kwargs.get("shell", False))
            calls.append(argv)
            if str(installer) in argv:
                self.skill("flyai")
            elif str(npx) in argv:
                self.skill("amap-lbs-skill", agent=True)
            elif "@fly-ai/flyai-cli" in argv:
                self.bundle()
            elif "axios" in argv:
                self.touch("home/.agents/skills/amap-lbs-skill/node_modules/axios/package.json")
            return subprocess.CompletedProcess(argv, 0, "installed", "")

        report = self.dependencies.install_missing(home=self.home, env=self.env,
            workspace=self.workspace, which=self.binaries.get, user_environment={}, runner=run)
        self.assertTrue(report["ok"], report)
        self.assertEqual(len(calls), 4)
        self.assertIn("alibaba-flyai/flyai-skill", calls[0])
        self.assertIn("skills/flyai", calls[0])
        self.assertIn("@fly-ai/flyai-cli", calls[1])
        self.assertIn("skills@1.7.6", calls[2])
        self.assertIn("https://clawhub.ai/lbs-amap/skills/amap-lbs-skill", calls[2])
        self.assertIn("axios", calls[3])
        self.assertTrue(any(str(npm) == value for value in calls[3]))
        self.assertNotIn("ego-browser", " ".join(value for call in calls for value in call))
        # Browser/video dependencies remain explicit manual requirements, not installs.
        self.assertFalse(report["after"]["tools"]["ego-browser"]["available"])

    def test_install_failure_is_sanitized_and_does_not_claim_success(self):
        self.complete_installation()
        (self.home / "AppData/Roaming/npm/node_modules/@fly-ai/flyai-cli/dist/flyai-bundle.cjs").unlink()
        self.tool("npm")
        report = self.dependencies.install_missing(home=self.home, env=self.env,
            workspace=self.workspace, which=self.binaries.get, user_environment={},
            runner=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, "secret", "private stacktrace"))
        self.assertFalse(report["ok"])
        self.assertEqual(report["actions"][0]["status"], "failed")
        self.assertNotIn("secret", json.dumps(report))
        self.assertNotIn("stacktrace", json.dumps(report))

    def test_existing_skills_are_reused_when_only_axios_is_missing(self):
        self.complete_installation()
        (self.home / ".codex/skills/amap-lbs-skill/node_modules/axios/package.json").unlink()
        self.tool("npm")
        calls = []
        def runner(argv, **kwargs):
            calls.append(argv)
            self.touch("home/.codex/skills/amap-lbs-skill/node_modules/axios/package.json")
            return subprocess.CompletedProcess(argv, 0, "", "")
        report = self.dependencies.install_missing(home=self.home, env=self.env,
            workspace=self.workspace, which=self.binaries.get, user_environment={}, runner=runner)
        self.assertTrue(report["ok"])
        self.assertEqual(len(calls), 1)
        self.assertIn("axios", calls[0])
        self.assertIn("--ignore-scripts", calls[0])
        self.assertIn("--omit=dev", calls[0])
        self.assertNotIn("--global", calls[0])

    def test_windows_cmd_fallback_quotes_paths_and_rejects_expansion(self):
        argv = self.dependencies.prepare_command([r"C:\Program Files\nodejs\npm.cmd", "install", "--global", "@fly-ai/flyai-cli"], windows=True)
        self.assertEqual(argv[1:5], ["/d", "/v:off", "/s", "/c"])
        self.assertIn(r"C:\Program Files\nodejs\npm.cmd", argv)
        self.assertEqual(argv[5], "call")
        with self.assertRaises(ValueError):
            self.dependencies.prepare_command([r"C:\npm.cmd", "install", "%PRIVATE_KEY%"], windows=True)
        with self.assertRaises(ValueError):
            self.dependencies.prepare_command([r"C:\npm.cmd", "install", "path&command"], windows=True)


class FlyAIQueryTests(TemporaryInstallation):
    def setUp(self):
        super().setUp()
        try:
            self.flyai = importlib.import_module("flyai_query")
        except ModuleNotFoundError:
            self.fail("flyai_query.py must preserve successful JSON across Node exit failures")
        self.node = self.tool("node")
        self.cli_bundle = self.bundle()
        self.output = self.workspace / "queries/result.json"

    def query(self, arguments, result):
        calls = []
        def runner(argv, **kwargs):
            calls.append(argv)
            self.assertFalse(kwargs.get("shell", False))
            return result
        envelope = self.flyai.run_query(arguments, self.output, home=self.home,
            workspace=self.workspace, env=self.env, which=self.binaries.get,
            user_environment={}, runner=runner)
        return envelope, calls

    def test_success_json_survives_windows_node_assertion_exit(self):
        response = {"status": 0, "data": {"items": [{"name": "西湖"}]}}
        process = subprocess.CompletedProcess([], 3221226505, json.dumps(response), "Assertion failed\nprivate stacktrace")
        envelope, calls = self.query(["keyword-search", "--query", "杭州亲子游"], process)
        self.assertEqual(calls, [[str(self.node), str(self.cli_bundle), "keyword-search", "--query", "杭州亲子游"]])
        self.assertEqual(envelope["response"], response)
        self.assertEqual(envelope["process_exit"], 3221226505)
        self.assertTrue(envelope["transport_warning"])
        self.assertEqual(envelope["query"], ["keyword-search", "--query", "杭州亲子游"])
        self.assertTrue(envelope["checked_at"])
        saved = self.output.read_text(encoding="utf-8")
        self.assertEqual(json.loads(saved), envelope)
        self.assertNotIn("stacktrace", saved)

    def test_normal_service_success_has_no_transport_warning(self):
        envelope, _ = self.query(["ai-search", "--query", "杭州酒店"],
                                subprocess.CompletedProcess([], 0, '{"status":0,"data":[]}', ""))
        self.assertIsNone(envelope["transport_warning"])

    def test_service_failure_is_saved_and_rejected_even_when_exit_zero(self):
        with self.assertRaises(self.flyai.QueryError):
            self.query(["search-poi", "--city-name", "杭州"],
                       subprocess.CompletedProcess([], 0, '{"status":401,"message":"not allowed"}', ""))
        self.assertEqual(json.loads(self.output.read_text(encoding="utf-8"))["response"]["status"], 401)

    def test_no_json_fails_without_echoing_stdout_or_stderr(self):
        with self.assertRaises(self.flyai.QueryError) as raised:
            self.query(["keyword-search", "--query", "杭州"],
                       subprocess.CompletedProcess([], 1, "secret-content", "sensitive-stacktrace"))
        self.assertNotIn("secret-content", str(raised.exception))
        self.assertNotIn("sensitive-stacktrace", str(raised.exception))
        self.assertFalse(self.output.exists())

    def test_response_parser_ignores_logs_but_last_service_status_wins(self):
        result = self.flyai.extract_response('Starting query\n{"status":0,"data":[]}\n{"status":9,"data":[]}\n')
        self.assertEqual(result["status"], 9)
        with self.assertRaises(self.flyai.QueryError):
            self.flyai.extract_response('{"tool":"keyword_search","arguments":{}}')

    def test_parser_does_not_accept_nested_success_in_a_failure(self):
        result = self.flyai.extract_response('{"status":3,"data":{"status":0}}')
        self.assertEqual(result["status"], 3)

    def test_parser_accepts_pretty_json_after_a_notice(self):
        try:
            result = self.flyai.extract_response('Starting query\n{\n  "status": 0,\n  "data": []\n}\n')
        except self.flyai.QueryError:
            self.fail("A complete pretty-printed service response must be accepted after a notice")
        self.assertEqual(result, {"status": 0, "data": []})

    def test_parser_rejects_nested_success_in_a_truncated_response(self):
        with self.assertRaises(self.flyai.QueryError):
            self.flyai.extract_response('{"status":3,"data":\n{"status":0}\n')

    def test_start_failure_is_sanitized(self):
        def cannot_start(argv, **kwargs):
            raise OSError("private environment and stacktrace")
        with self.assertRaises(self.flyai.QueryError) as raised:
            self.flyai.run_query(["keyword-search", "--query", "杭州"], self.output,
                home=self.home, env=self.env, workspace=self.workspace, which=self.binaries.get,
                user_environment={}, runner=cannot_start)
        self.assertNotIn("private environment", str(raised.exception))
        self.assertFalse(self.output.exists())

    def test_read_only_allowlist_rejects_config_and_credentials(self):
        for args in (["config", "set", "FLYAI_API_KEY", "secret"],
                     ["keyword-search", "--api-key", "secret", "--query", "杭州"],
                     ["keyword-search", "--query", "杭州", "--token=secret"]):
            with self.subTest(args=args), self.assertRaises(self.flyai.QueryError):
                self.flyai.validate_query(args)

    def test_all_documented_read_only_commands_are_allowed(self):
        for name in ("keyword-search", "search-flight", "search-hotel", "search-poi", "search-train",
                     "search-marriott-hotel", "search-marriott-package", "ai-search"):
            self.assertEqual(self.flyai.validate_query([name]), [name])

    def test_marriott_hotel_allows_brand_and_hotel_name_from_reference(self):
        arguments = ["search-marriott-hotel", "--dest-name", "上海",
                     "--hotel-brands", "万豪酒店,喜来登", "--hotel-name", "JW万豪"]
        try:
            result = self.flyai.validate_query(arguments)
        except self.flyai.QueryError:
            self.fail("The official hotel reference includes brand and hotel-name filters")
        self.assertEqual(result, arguments)

    def test_marriott_package_rejects_flags_missing_from_reference(self):
        for option in ("--hotel-name", "--province-or-city"):
            with self.subTest(option=option), self.assertRaises(self.flyai.QueryError):
                self.flyai.validate_query(["search-marriott-package", "--keyword", "上海", option, "上海"])

    def test_query_uses_array_so_shell_metacharacters_are_plain_query_text(self):
        text = '杭州 & $(echo forbidden) "quote"'
        _, calls = self.query(["keyword-search", "--query", text],
                              subprocess.CompletedProcess([], 0, '{"status":0,"data":[]}', ""))
        self.assertEqual(calls[0][-1], text)

    def test_missing_bundle_is_clear_and_never_uses_launcher(self):
        self.cli_bundle.unlink()
        with self.assertRaises(self.flyai.QueryError) as raised:
            self.query(["keyword-search", "--query", "杭州"],
                       subprocess.CompletedProcess([], 0, '{"status":0}', ""))
        self.assertIn("bundle", str(raised.exception).lower())

    def test_cli_requires_separator_before_query(self):
        with patch("sys.stderr"):
            self.assertNotEqual(self.flyai.main(["--output", str(self.output), "config", "set", "KEY", "secret"]), 0)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
