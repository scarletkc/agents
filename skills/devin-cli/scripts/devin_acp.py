#!/usr/bin/env python3
"""Run one Devin CLI task over ACP and record it, or summarize a recorded run.

`run` blocks until Devin ends its turn, answering permission requests with a
single-use allow or reject chosen by a local policy. Launch it with your own
background facility when the supervising agent should keep working.
Standard library only; Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = 1
CANCEL_GRACE_SECONDS = 15
EXIT_GRACE_SECONDS = 10

# Commands a delegated worker should leave to the supervisor: history-changing
# git operations, branch and worktree changes, and publishing through gh.
DEFAULT_DENY = (
    r"\bgit\s+(?:push|commit|stash|reset|clean|checkout|switch|restore|rebase|merge|worktree|tag|am|cherry-pick|revert)\b",
    r"\bgit\s+branch\s+(?:-[dDmMcC]|--delete|--move|--copy)\b",
    r"\bgh\s+(?:pr|release|repo|issue|api|workflow|secret|auth|gist)\b",
)
WRITE_KINDS = frozenset({"edit", "delete", "move"})
# Shell commands can write anywhere and cannot be path-checked, so a read-only
# run rejects them along with every write tool.
READ_ONLY_REJECTED_KINDS = WRITE_KINDS | {"execute"}
READ_ONLY_MODES = frozenset({"ask", "plan"})
TEXT_ACTIVITY_INTERVAL = 5.0
SENTINEL_EOF = object()


class DevinError(RuntimeError):
    pass


class DevinTimeout(DevinError):
    pass


def encode(value: Any) -> str:
    # ASCII escapes keep the JSON readable on non-UTF-8 Windows consoles.
    return json.dumps(value, ensure_ascii=True, allow_nan=False)


def positive_seconds(value: str) -> float:
    number = float(value)
    if not (number > 0 and number != float("inf")):
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return number


def non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def default_run_dir() -> Path:
    # mkdtemp creates a unique owner-only directory directly in the temp dir,
    # so no shared parent can be pre-created or replaced by another user.
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(tempfile.mkdtemp(prefix=f"devin-acp-{stamp}-"))


def prepare_run_dir(run_dir: Path) -> None:
    """Create a private directory for one run; refuse one that already holds a run."""
    if (run_dir / "events.jsonl").exists():
        raise DevinError(f"{run_dir} already holds a run; pass a new --run-dir")
    # Briefs and Devin's output can contain project secrets; keep them owner-only.
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(run_dir, 0o700)


class Policy:
    """Decides each permission request. Answers are always single-use."""

    def __init__(
        self,
        workspace: Path,
        deny_patterns: list[str],
        write_roots: list[Path],
        read_only: bool,
    ):
        self.deny = [re.compile(pattern) for pattern in deny_patterns]
        self.write_roots = [workspace, *write_roots]
        self.read_only = read_only

    def decide(self, tool: dict[str, Any]) -> tuple[bool, str]:
        subject = encode(
            {key: tool.get(key) for key in ("title", "kind", "rawInput", "locations", "_meta")}
        )
        # Commands may arrive JSON-escaped; match against the decoded form too.
        decoded = subject.encode().decode("unicode_escape", errors="replace")
        for pattern in self.deny:
            if pattern.search(subject) or pattern.search(decoded):
                return False, f"matches deny rule {pattern.pattern}"
        kind = tool.get("kind")
        if self.read_only and kind in READ_ONLY_REJECTED_KINDS:
            return False, "read-only run"
        if kind in WRITE_KINDS:
            paths = [location.get("path") for location in tool.get("locations") or []]
            if not any(paths):
                return False, "write without a target path"
            for path in paths:
                if not path or not self._writable(path):
                    return False, f"write outside allowed roots: {path}"
        return True, "within policy"

    def _writable(self, path: str) -> bool:
        try:
            target = Path(path).resolve()
        except OSError:
            return False
        return any(target == root or root in target.parents for root in self.write_roots)


class Recorder:
    def __init__(self, run_dir: Path):
        self.started = time.monotonic()
        # "x" refuses to append a second run to an existing event stream.
        self.stream = (run_dir / "events.jsonl").open("x", encoding="utf-8")

    def __call__(self, event_type: str, **fields: Any) -> None:
        record = {"t": round(time.monotonic() - self.started, 3), "type": event_type, **fields}
        self.stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.stream.flush()

    def close(self) -> None:
        self.stream.close()


class DevinSession:
    def __init__(
        self,
        command: list[str],
        cwd: Path,
        run_dir: Path,
        policy: Policy,
        *,
        mode: str | None = None,
        resume: str | None = None,
        timeout: float = 3600,
        startup_timeout: float = 120,
    ):
        self.command = command
        self.cwd = cwd
        self.run_dir = run_dir
        self.policy = policy
        self.mode = mode
        self.resume = resume
        self.timeout = timeout
        self.startup_timeout = startup_timeout
        self.record = Recorder(run_dir)
        self.messages: queue.Queue[Any] = queue.Queue()
        self.next_id = 0
        self.process: subprocess.Popen[str] | None = None
        self.reader: threading.Thread | None = None
        self.write_lock = threading.Lock()
        self.tools: dict[str, dict[str, Any]] = {}
        self.text: list[str] = []
        self.text_chars = 0
        self.recorded_text_chars = 0
        self.last_text_record = 0.0
        self.collect_text = False
        self.session_id: str | None = None
        self.title: str | None = None
        self.current_mode: str | None = None
        self.config: dict[str, Any] = {}
        self.allowed = 0
        self.denied: list[dict[str, Any]] = []
        self.failed_tools = 0
        self.prompt_id: int | None = None

    # transport -----------------------------------------------------------

    def _spawn(self) -> None:
        options: dict[str, Any] = {}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            options["start_new_session"] = True
        stderr = (self.run_dir / "devin.stderr.log").open("ab")
        try:
            self.process = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **options,
            )
        finally:
            stderr.close()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                self.record("non_json_output", line=line[:500])
                continue
            if isinstance(message, dict):
                self.messages.put(message)
        self.messages.put(SENTINEL_EOF)

    def _send(self, message: dict[str, Any]) -> None:
        assert self.process is not None and self.process.stdin is not None
        with self.write_lock:
            try:
                self.process.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
                self.process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                raise DevinError("Devin closed its input; see devin.stderr.log") from exc

    def _request(self, method: str, params: dict[str, Any]) -> int:
        self.next_id += 1
        self._send({"id": self.next_id, "method": method, "params": params})
        return self.next_id

    def _await(self, request_id: int, deadline: float, method: str) -> dict[str, Any]:
        while True:
            message = self._next(deadline)
            if message is None:
                raise DevinTimeout(f"Devin did not answer {method} in time")
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    error = message["error"]
                    detail = error.get("data") or error.get("message") or error
                    raise DevinError(f"{method} failed: {detail}")
                return message.get("result") or {}
            self._dispatch(message)

    def _next(self, deadline: float) -> dict[str, Any] | None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            message = self.messages.get(timeout=min(remaining, 0.5))
        except queue.Empty:
            return {} if time.monotonic() < deadline else None
        if message is SENTINEL_EOF:
            code = self.process.poll() if self.process else None
            raise DevinError(f"Devin exited (code {code}); see devin.stderr.log")
        return message

    def _kill_tree(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            self.process.wait(timeout=EXIT_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            self.process.kill()

    def _shutdown(self) -> None:
        if self.process is None:
            return
        try:
            if self.process.stdin is not None:
                self.process.stdin.close()
        except OSError:
            pass
        try:
            self.process.wait(timeout=EXIT_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            self._kill_tree()
        if self.reader is not None:
            self.reader.join(timeout=2)
        if self.process.stdout is not None:
            self.process.stdout.close()

    # protocol ------------------------------------------------------------

    def _dispatch(self, message: dict[str, Any]) -> None:
        if not message:
            return
        method = message.get("method")
        if method == "session/update":
            self._on_update(message.get("params", {}))
        elif method == "session/request_permission" and "id" in message:
            self._on_permission(message)
        elif method is not None and "id" in message:
            # No filesystem or terminal callbacks are advertised; Devin runs its own tools.
            self.record("unsupported_request", method=method)
            self._send(
                {
                    "id": message["id"],
                    "error": {"code": -32601, "message": f"Client does not implement {method}"},
                }
            )
        elif method is not None:
            self.record("notification", method=method)

    def _on_update(self, params: dict[str, Any]) -> None:
        update = params.get("update", {})
        kind = update.get("sessionUpdate")
        if not self.collect_text:
            self.record("setup_update", kind=kind)
            if kind in {"config_option_update", "current_mode_update"}:
                self._apply_config(update)
            return
        if kind == "agent_message_chunk":
            content = update.get("content", {})
            if content.get("type") == "text":
                chunk = content.get("text", "")
                self.text.append(chunk)
                self.text_chars += len(chunk)
                # Keep the event log moving while Devin streams a long answer.
                now = time.monotonic()
                if now - self.last_text_record >= TEXT_ACTIVITY_INTERVAL:
                    self.last_text_record = now
                    self._record_text_length()
        elif kind in {"tool_call", "tool_call_update"}:
            tool_id = update.get("toolCallId")
            tool = self.tools.setdefault(tool_id, {})
            tool.update({key: value for key, value in update.items() if value is not None})
            if kind == "tool_call":
                self.record("tool", id=tool_id, kind=tool.get("kind"), title=tool.get("title"))
            elif update.get("status") == "failed":
                self.failed_tools += 1
                self.record("tool_failed", id=tool_id, title=tool.get("title"))
        elif kind == "plan":
            entries = [
                {"status": entry.get("status"), "content": entry.get("content")}
                for entry in update.get("entries", [])
            ]
            self.record("plan", entries=entries)
        elif kind == "session_info_update":
            self.title = update.get("title") or self.title
        elif kind in {"config_option_update", "current_mode_update"}:
            self._apply_config(update)
        elif kind == "usage_update":
            self.record("usage", used=update.get("used"), size=update.get("size"))

    def _record_text_length(self) -> None:
        if self.text_chars != self.recorded_text_chars:
            self.recorded_text_chars = self.text_chars
            self.record("text", chars=self.text_chars)

    def _apply_config(self, update: dict[str, Any]) -> None:
        options = update.get("configOptions") or []
        for option in options:
            self.config[option.get("id")] = option.get("currentValue")
        if any(option.get("id") == "mode" for option in options):
            self.current_mode = self.config["mode"]
        if update.get("currentModeId"):
            # A mode update without config options is newer than the cached option.
            self.current_mode = update["currentModeId"]
            if "mode" in self.config:
                self.config["mode"] = self.current_mode

    def _on_permission(self, message: dict[str, Any]) -> None:
        params = message.get("params", {})
        request_tool = params.get("toolCall", {})
        tool = {**self.tools.get(request_tool.get("toolCallId"), {}), **request_tool}
        allowed, reason = self.policy.decide(tool)
        wanted = "allow_once" if allowed else "reject_once"
        option = next(
            (item for item in params.get("options", []) if item.get("kind") == wanted), None
        )
        command = (tool.get("_meta") or {}).get("cognition.ai/editableCommand")
        entry = {"title": tool.get("title"), "kind": tool.get("kind"), "command": command, "reason": reason}
        if option is None:
            # Never fall back to a persistent option such as allow_always.
            outcome = {"outcome": "cancelled"}
            allowed = False
            entry["reason"] = f"{reason}; Devin offered no {wanted} option"
        else:
            outcome = {"outcome": "selected", "optionId": option["optionId"]}
        self.record("permission", decision="allow" if allowed else "deny", **entry)
        if allowed:
            self.allowed += 1
        else:
            self.denied.append(entry)
        self._send({"id": message["id"], "result": {"outcome": outcome}})

    def _cancel(self, prompt_id: int) -> dict[str, Any] | None:
        assert self.session_id is not None
        self._send({"method": "session/cancel", "params": {"sessionId": self.session_id}})
        self.record("cancel_sent")
        deadline = time.monotonic() + CANCEL_GRACE_SECONDS
        try:
            return self._await(prompt_id, deadline, "session/cancel")
        except DevinError:
            self._kill_tree()
            return None

    def run(self, prompt: str) -> dict[str, Any]:
        started = time.monotonic()
        summary: dict[str, Any] = {"status": "failed", "run_dir": str(self.run_dir)}
        self.record("start", command=self.command, cwd=str(self.cwd), resume=self.resume)
        try:
            self._spawn()
            setup_deadline = time.monotonic() + self.startup_timeout
            init = self._await(
                self._request(
                    "initialize",
                    {
                        "protocolVersion": PROTOCOL_VERSION,
                        "clientCapabilities": {},
                        "clientInfo": {"name": "devin-cli-skill", "version": "1"},
                    },
                ),
                setup_deadline,
                "initialize",
            )
            if init.get("protocolVersion") != PROTOCOL_VERSION:
                raise DevinError(f"unsupported ACP protocol version {init.get('protocolVersion')!r}")
            if self.resume:
                result = self._await(
                    self._request(
                        "session/load",
                        {"sessionId": self.resume, "cwd": str(self.cwd), "mcpServers": []},
                    ),
                    setup_deadline,
                    "session/load",
                )
                self.session_id = self.resume
            else:
                result = self._await(
                    self._request("session/new", {"cwd": str(self.cwd), "mcpServers": []}),
                    setup_deadline,
                    "session/new",
                )
                self.session_id = result["sessionId"]
            self._apply_config(
                {
                    "currentModeId": (result.get("modes") or {}).get("currentModeId"),
                    "configOptions": result.get("configOptions"),
                }
            )
            if self.mode:
                available = [m.get("id") for m in (result.get("modes") or {}).get("availableModes", [])]
                if self.mode not in available:
                    raise DevinError(f"mode {self.mode!r} not offered; available: {', '.join(available)}")
                self._await(
                    self._request("session/set_mode", {"sessionId": self.session_id, "modeId": self.mode}),
                    setup_deadline,
                    "session/set_mode",
                )
                self.current_mode = self.mode
            self.record("session", session_id=self.session_id, mode=self.current_mode, config=self.config)
            print(encode({"event": "session", "session_id": self.session_id, "run_dir": str(self.run_dir)}), flush=True)

            self.collect_text = True
            self.record("prompt", text=prompt)
            self.prompt_id = self._request(
                "session/prompt",
                {"sessionId": self.session_id, "prompt": [{"type": "text", "text": prompt}]},
            )
            turn_deadline = time.monotonic() + self.timeout
            try:
                response = self._await(self.prompt_id, turn_deadline, "session/prompt")
                stop_reason = response.get("stopReason")
                summary["status"] = "completed" if stop_reason == "end_turn" else "failed"
                if stop_reason != "end_turn":
                    summary["error"] = f"Devin stopped with {stop_reason!r}; inspect the partial result"
            except DevinTimeout:
                response = self._cancel(self.prompt_id) or {}
                stop_reason = response.get("stopReason", "forced_stop")
                summary.update(status="timed_out", error=f"turn exceeded {self.timeout:g}s and was cancelled")
            summary["stop_reason"] = stop_reason
            summary["usage"] = response.get("usage")
        except KeyboardInterrupt:
            if self.prompt_id is not None:
                try:
                    self._cancel(self.prompt_id)
                except DevinError:
                    self._kill_tree()
            summary.update(status="interrupted", error="interrupted by the supervising process")
        except DevinError as exc:
            summary["error"] = str(exc)
        finally:
            self._shutdown()
            text = "".join(self.text)
            (self.run_dir / "final.md").write_text(text, encoding="utf-8")
            summary.update(
                session_id=self.session_id,
                title=self.title,
                mode=self.current_mode,
                config={k: v for k, v in self.config.items() if k != "mode"},
                elapsed_seconds=round(time.monotonic() - started, 1),
                tool_calls=len(self.tools),
                failed_tools=self.failed_tools,
                permissions_allowed=self.allowed,
                permissions_denied=self.denied,
                final_text_file=str(self.run_dir / "final.md"),
                events_file=str(self.run_dir / "events.jsonl"),
            )
            # Publish the final length even when the last chunks arrived within one interval.
            self._record_text_length()
            summary["text_chars"] = self.text_chars
            self.record("end", **{k: v for k, v in summary.items() if k not in {"run_dir"}})
            self.record.close()
            (self.run_dir / "summary.json").write_text(encode(summary), encoding="utf-8")
        return summary


# progress -----------------------------------------------------------------


def progress(run_dir: Path, tool_count: int) -> dict[str, Any]:
    events_file = run_dir / "events.jsonl"
    if not events_file.exists():
        raise DevinError(f"no events.jsonl in {run_dir}")
    events = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    tools = [e for e in events if e["type"] == "tool"]
    plans = [e for e in events if e["type"] == "plan"]
    result: dict[str, Any] = {
        "run_dir": str(run_dir),
        "finished": any(e["type"] == "end" for e in events),
        "elapsed_seconds": events[-1]["t"] if events else 0,
        "seconds_since_last_event": round(time.time() - events_file.stat().st_mtime, 1),
        "session_id": next((e["session_id"] for e in events if e["type"] == "session"), None),
        "tool_calls": len(tools),
        "recent_tools": [e.get("title") for e in tools[len(tools) - tool_count :]] if tool_count > 0 else [],
        "text_chars": max((e.get("chars", 0) for e in events if e["type"] == "text"), default=0),
        "plan": plans[-1]["entries"] if plans else [],
        "permissions_denied": [
            {key: e.get(key) for key in ("title", "command", "reason")}
            for e in events
            if e["type"] == "permission" and e["decision"] == "deny"
        ],
        "failed_tools": sum(1 for e in events if e["type"] == "tool_failed"),
    }
    summary_file = run_dir / "summary.json"
    if summary_file.exists():
        result["summary"] = json.loads(summary_file.read_text(encoding="utf-8"))
    return result


# cli ----------------------------------------------------------------------


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file is not None:
        text = args.prompt_file.read_text(encoding="utf-8-sig")
    elif args.prompt is not None:
        text = args.prompt
    else:
        text = sys.stdin.buffer.read().decode("utf-8-sig")
    if not text.strip():
        raise DevinError("prompt is empty; pass --prompt, --prompt-file, or UTF-8 stdin")
    return text


def build_command(args: argparse.Namespace) -> list[str]:
    executable = shutil.which(args.devin)
    if executable is None:
        raise DevinError(f"Devin CLI not found ({args.devin!r}); install it or pass --devin <path>")
    command = [executable, "acp"]
    if args.model:
        command += ["--model", args.model]
    if args.agent_type:
        command += ["--agent-type", args.agent_type]
    return command


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = root.add_subparsers(dest="action", required=True)

    run = sub.add_parser("run", help="run one Devin turn and block until it ends")
    run.add_argument("--cwd", type=Path, required=True, help="workspace Devin works in (absolute path)")
    prompts = run.add_mutually_exclusive_group()
    prompts.add_argument("--prompt", help="task text; default reads UTF-8 stdin")
    prompts.add_argument("--prompt-file", type=Path, help="UTF-8 file with the task text")
    run.add_argument("--run-dir", type=Path, help="new or empty directory for this run's events, final text and summary (default: a new private directory under the system temp dir)")
    run.add_argument("--resume", metavar="SESSION_ID", help="continue an earlier Devin session instead of starting a new one")
    run.add_argument("--model", help="model name as accepted by `devin --model` (see `devin models list`)")
    run.add_argument("--mode", help="session mode, e.g. accept-edits, smart, ask, plan (default: Devin's configured mode)")
    run.add_argument("--agent-type", choices=["review", "summarizer"], help="run a specialized Devin agent instead of the default one")
    run.add_argument("--timeout", type=positive_seconds, default=3600, help="seconds before the turn is cancelled (default 3600)")
    run.add_argument("--startup-timeout", type=positive_seconds, default=120, help="seconds allowed for ACP setup (default 120)")
    run.add_argument("--deny", action="append", default=[], metavar="REGEX", help="extra pattern; matching tool calls are rejected (repeatable)")
    run.add_argument("--no-default-deny", action="store_true", help="drop the built-in git/gh deny patterns")
    run.add_argument("--allow-write-root", action="append", default=[], type=Path, metavar="DIR", help="extra directory edits may target (repeatable)")
    run.add_argument("--read-only", action="store_true", help="reject every edit, delete, move and shell-command request; defaults --mode to ask")
    run.add_argument("--devin", default="devin", help="Devin CLI executable name or path")

    prog = sub.add_parser("progress", help="summarize a running or finished run directory")
    prog.add_argument("--run-dir", type=Path, required=True)
    prog.add_argument("--tools", type=non_negative_int, default=8, help="how many recent tool titles to show")
    return root


def _interrupt(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if threading.current_thread() is threading.main_thread():
        # Let a terminated supervisor-side process cancel Devin instead of orphaning it.
        signal.signal(signal.SIGTERM, _interrupt)
    try:
        if args.action == "progress":
            print(encode(progress(args.run_dir.resolve(), args.tools)))
            return 0
        cwd = args.cwd.expanduser().resolve(strict=True)
        if not cwd.is_dir():
            raise DevinError("--cwd must be a directory")
        prompt = read_prompt(args)
        command = build_command(args)
        mode = args.mode
        if args.read_only:
            if mode is None:
                mode = "ask"
            elif mode not in READ_ONLY_MODES:
                raise DevinError(f"--read-only needs --mode ask or plan, not {mode!r}")
        run_dir = (args.run_dir or default_run_dir()).expanduser().resolve()
        prepare_run_dir(run_dir)
        print(encode({"event": "started", "run_dir": str(run_dir)}), flush=True)
        policy = Policy(
            cwd,
            ([] if args.no_default_deny else list(DEFAULT_DENY)) + args.deny,
            [path.expanduser().resolve() for path in args.allow_write_root],
            args.read_only,
        )
        session = DevinSession(
            command,
            cwd,
            run_dir,
            policy,
            mode=mode,
            resume=args.resume,
            timeout=args.timeout,
            startup_timeout=args.startup_timeout,
        )
        summary = session.run(prompt)
        print(encode({"event": "finished", **summary}), flush=True)
        return 0 if summary["status"] == "completed" else 1
    except (DevinError, OSError, ValueError, re.error) as exc:
        print(encode({"event": "error", "error": str(exc)}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
