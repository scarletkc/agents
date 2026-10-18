from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
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

    def tearDown(self):
        self.temp.cleanup()

    def run_session(self, agent_mode="normal", prompt="hello", *, read_only=False, deny=None, **options):
        run_dir = self.root / f"run-{agent_mode}"
        run_dir.mkdir(exist_ok=True)
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


if __name__ == "__main__":
    unittest.main()
