from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/devin-cli/scripts/devin_acp.py"
FIXTURE = ROOT / "tests/fixtures/devin_acp_agent.py"
spec = importlib.util.spec_from_file_location("devin_acp", SCRIPT)
devin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(devin)


class DevinRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.trace_file = self.root / "trace.jsonl"
        self.runs = 0

    def tearDown(self):
        self.temp.cleanup()

    def run_session(self, agent_mode="normal", prompt="hello", *, read_only=False, deny=None, **options):
        self.runs += 1
        run_dir = self.root / f"run-{self.runs}-{agent_mode}"
        devin.prepare_run_dir(run_dir)
        policy = devin.Policy(
            self.workspace, list(devin.DEFAULT_DENY) + (deny or []), [], read_only
        )
        session = devin.DevinSession(
            [sys.executable, str(FIXTURE), str(self.trace_file), agent_mode],
            self.workspace,
            run_dir,
            policy,
            **{"startup_timeout": 5, "timeout": 20, **options},
        )
        with contextlib.redirect_stdout(io.StringIO()):
            summary = session.run(prompt)
        return summary, run_dir

    def trace(self):
        return [
            json.loads(line)
            for line in self.trace_file.read_text(encoding="utf-8").splitlines()
        ]

    def outcomes(self):
        return {
            m["id"]: m["result"]["outcome"]
            for m in self.trace()
            if m.get("id", 0) >= 900 and "result" in m
        }

    def test_turn_records_text_config_and_files(self):
        summary, run_dir = self.run_session(prompt="你好 `quoted` $()")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["stop_reason"], "end_turn")
        self.assertEqual(summary["session_id"], "steady-otter")
        self.assertEqual(summary["config"], {"model": "fake-model", "thought_level": "high"})
        self.assertEqual(summary["failed_tools"], 1)
        self.assertEqual(
            (run_dir / "final.md").read_text(encoding="utf-8"), "echo: 你好 `quoted` $()"
        )
        self.assertEqual(json.loads((run_dir / "summary.json").read_text())["status"], "completed")
        init = next(m for m in self.trace() if m.get("method") == "initialize")
        self.assertEqual(init["params"]["clientCapabilities"], {})

    def test_permissions_are_single_use_and_follow_policy(self):
        summary, _ = self.run_session("permissions")
        self.assertEqual(
            self.outcomes(),
            {
                901: {"outcome": "selected", "optionId": "allow_once"},
                902: {"outcome": "selected", "optionId": "reject_once"},
                903: {"outcome": "selected", "optionId": "reject_once"},
                904: {"outcome": "selected", "optionId": "allow_once"},
            },
        )
        self.assertEqual(summary["permissions_allowed"], 2)
        reasons = [entry["reason"] for entry in summary["permissions_denied"]]
        self.assertIn("deny rule", reasons[0])
        self.assertEqual(summary["permissions_denied"][0]["command"], "git push origin main")
        self.assertIn("outside allowed roots", reasons[1])

    def test_read_only_rejects_workspace_edits(self):
        self.run_session("permissions", read_only=True)
        self.assertEqual(self.outcomes()[904], {"outcome": "selected", "optionId": "reject_once"})

    def test_extra_deny_pattern_rejects_matching_command(self):
        self.run_session("permissions", deny=[r"git\s+status"])
        self.assertEqual(self.outcomes()[901]["optionId"], "reject_once")

    def test_writes_without_a_path_and_read_only_shell_commands_are_rejected(self):
        policy = devin.Policy(self.workspace, [], [], read_only=False)
        self.assertEqual(policy.decide({"kind": "edit"}), (False, "write without a target path"))
        self.assertTrue(policy.decide({"kind": "execute", "title": "Ran ls"})[0])
        read_only = devin.Policy(self.workspace, [], [], read_only=True)
        self.assertEqual(read_only.decide({"kind": "execute"}), (False, "read-only run"))
        self.assertTrue(read_only.decide({"kind": "read"})[0])

    def test_read_only_cli_defaults_to_ask_and_rejects_editing_modes(self):
        command = [sys.executable, str(FIXTURE), str(self.trace_file), "normal"]
        base = ["run", "--cwd", str(self.workspace), "--prompt", "x", "--read-only"]
        with patch.object(devin, "build_command", return_value=command):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = devin.main([*base, "--run-dir", str(self.root / "ro-1")])
            self.assertEqual(code, 0)
            finished = json.loads(output.getvalue().splitlines()[-1])
            self.assertEqual(finished["mode"], "ask")
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = devin.main([*base, "--mode", "accept-edits", "--run-dir", str(self.root / "ro-2")])
            self.assertEqual(code, 1)
            self.assertIn("--read-only needs", json.loads(output.getvalue())["error"])

    def test_run_directory_holds_one_private_run(self):
        _, run_dir = self.run_session()
        with self.assertRaises(devin.DevinError):
            devin.prepare_run_dir(run_dir)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(run_dir.stat().st_mode), 0o700)

    def test_mode_update_without_options_replaces_cached_mode(self):
        run_dir = self.root / "config"
        devin.prepare_run_dir(run_dir)
        policy = devin.Policy(self.workspace, [], [], False)
        session = devin.DevinSession([sys.executable], self.workspace, run_dir, policy)
        session._apply_config({"configOptions": [{"id": "mode", "currentValue": "accept-edits"}]})
        session._apply_config({"currentModeId": "plan"})
        session.record.close()
        self.assertEqual(session.current_mode, "plan")
        self.assertEqual(session.config["mode"], "plan")

    def test_final_text_length_is_recorded_when_chunks_arrive_quickly(self):
        _, run_dir = self.run_session(prompt="hello")
        report = devin.progress(run_dir, tool_count=8)
        self.assertEqual(report["text_chars"], len("echo: hello"))
        self.assertEqual(report["summary"]["text_chars"], len("echo: hello"))

    def test_default_run_directories_are_unique_and_private(self):
        first, second = devin.default_run_dir(), devin.default_run_dir()
        try:
            self.assertNotEqual(first, second)
            self.assertEqual(first.resolve().parent, Path(tempfile.gettempdir()).resolve())
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o700)
            devin.prepare_run_dir(first)
        finally:
            first.rmdir()
            second.rmdir()

    def test_streamed_text_is_logged_as_activity(self):
        with patch.object(devin, "TEXT_ACTIVITY_INTERVAL", 0):
            _, run_dir = self.run_session(prompt="streamed")
        report = devin.progress(run_dir, tool_count=0)
        self.assertEqual(report["recent_tools"], [])
        self.assertEqual(report["text_chars"], len("echo: streamed"))

    def test_resume_loads_session_and_excludes_replayed_text(self):
        summary, run_dir = self.run_session(resume="steady-otter", prompt="follow-up")
        methods = [m.get("method") for m in self.trace()]
        self.assertIn("session/load", methods)
        self.assertNotIn("session/new", methods)
        self.assertEqual(summary["session_id"], "steady-otter")
        self.assertEqual((run_dir / "final.md").read_text(encoding="utf-8"), "echo: follow-up")

    def test_mode_is_set_and_unknown_mode_never_sends_prompt(self):
        summary, _ = self.run_session(mode="ask")
        set_mode = next(m for m in self.trace() if m.get("method") == "session/set_mode")
        self.assertEqual(set_mode["params"]["modeId"], "ask")
        self.assertEqual(summary["mode"], "ask")
        self.trace_file.unlink()
        failed, _ = self.run_session(mode="nonsense")
        self.assertEqual(failed["status"], "failed")
        self.assertIn("available: accept-edits", failed["error"])
        self.assertFalse(any(m.get("method") == "session/prompt" for m in self.trace()))

    def test_timeout_cancels_and_reports_timed_out(self):
        summary, _ = self.run_session("hold", timeout=0.5)
        self.assertEqual(summary["status"], "timed_out")
        self.assertEqual(summary["stop_reason"], "cancelled")
        self.assertTrue(any(m.get("method") == "session/cancel" for m in self.trace()))

    def test_unacknowledged_cancel_stops_the_process(self):
        with patch.object(devin, "CANCEL_GRACE_SECONDS", 0.5):
            summary, _ = self.run_session("ignore_cancel", timeout=0.5)
        self.assertEqual(summary["status"], "timed_out")
        self.assertEqual(summary["stop_reason"], "forced_stop")

    def test_incomplete_stop_reason_keeps_partial_text(self):
        summary, run_dir = self.run_session("limit")
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["stop_reason"], "max_tokens")
        self.assertEqual((run_dir / "final.md").read_text(encoding="utf-8"), "partial")

    def test_setup_and_process_failures_are_reported(self):
        for mode in ("crash", "bad_version", "startup_hang"):
            with self.subTest(mode=mode):
                summary, _ = self.run_session(mode, startup_timeout=0.5)
                self.assertEqual(summary["status"], "failed")
                self.assertTrue(summary["error"])

    def test_unsupported_client_request_gets_method_not_found(self):
        _, run_dir = self.run_session("unsupported")
        self.assertEqual((run_dir / "final.md").read_text(encoding="utf-8"), "callback error -32601")

    def test_progress_summarizes_run_directory(self):
        _, run_dir = self.run_session("permissions")
        report = devin.progress(run_dir, tool_count=2)
        self.assertTrue(report["finished"])
        self.assertEqual(report["session_id"], "steady-otter")
        self.assertEqual(report["recent_tools"], ["Wrote outside", "Wrote inside"])
        self.assertEqual(len(report["permissions_denied"]), 2)
        self.assertEqual(report["summary"]["status"], "completed")


class DevinCliTests(unittest.TestCase):
    def test_command_passes_model_and_agent_type(self):
        args = devin.parser().parse_args(
            ["run", "--cwd", ".", "--prompt", "x", "--model", "m-high", "--agent-type", "review"]
        )
        with patch.object(devin.shutil, "which", return_value="/bin/devin"):
            self.assertEqual(
                devin.build_command(args),
                ["/bin/devin", "acp", "--model", "m-high", "--agent-type", "review"],
            )

    def test_missing_executable_and_empty_prompt_are_errors(self):
        args = devin.parser().parse_args(["run", "--cwd", ".", "--prompt", " ", "--devin", "no-such-devin"])
        with self.assertRaises(devin.DevinError):
            devin.build_command(args)
        with self.assertRaises(devin.DevinError):
            devin.read_prompt(args)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = devin.main(["run", "--cwd", ".", "--prompt", "x", "--devin", "no-such-devin"])
        self.assertEqual(code, 1)
        self.assertIn("not found", json.loads(output.getvalue())["error"])

    def test_timeouts_must_be_positive_and_finite(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.assertRaises(argparse.ArgumentTypeError):
                devin.positive_seconds(value)
        with self.assertRaises(argparse.ArgumentTypeError):
            devin.non_negative_int("-1")


if __name__ == "__main__":
    unittest.main()
