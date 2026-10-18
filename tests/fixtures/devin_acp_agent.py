"""Scripted stand-in for `devin acp` used by tests/test_devin_acp.py.

Usage: devin_acp_agent.py <trace.jsonl> <mode>
Every message the client sends is appended to the trace file.
"""

from __future__ import annotations

import json
import sys
import time

TRACE, MODE = sys.argv[1], sys.argv[2]
# ACP is UTF-8 JSON lines regardless of the console code page.
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
SESSION = "steady-otter"
MODES = {
    "currentModeId": "accept-edits",
    "availableModes": [{"id": m, "name": m} for m in ("accept-edits", "smart", "ask", "plan", "bypass")],
}
CONFIG = [
    {"id": "mode", "currentValue": "accept-edits"},
    {"id": "model", "currentValue": "fake-model"},
    {"id": "thought_level", "currentValue": "high"},
]
OPTIONS = [
    {"optionId": "allow_once", "name": "Allow", "kind": "allow_once"},
    {"optionId": "allow_session", "name": "Allow this session", "kind": "allow_always"},
    {"optionId": "allow_always", "name": "Always allow here", "kind": "allow_always"},
    {"optionId": "allow_always_global", "name": "Always allow everywhere", "kind": "allow_always"},
    {"optionId": "switch_bypass", "name": "Switch to bypass", "kind": "allow_always"},
    {"optionId": "reject_once", "name": "Reject", "kind": "reject_once"},
]


def trace(message: dict) -> None:
    with open(TRACE, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(message, ensure_ascii=False) + "\n")


def send(message: dict) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", **message}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def read() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    message = json.loads(line)
    trace(message)
    return message


def update(payload: dict) -> None:
    send({"method": "session/update", "params": {"sessionId": SESSION, "update": payload}})


def say(text: str) -> None:
    update({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}})


def ask(request_id: int, tool_id: str, kind: str, title: str, locations=None, command=None) -> dict:
    update({"sessionUpdate": "tool_call", "toolCallId": tool_id, "kind": kind, "title": title,
            "status": "pending", "locations": locations or []})
    request = {"toolCallId": tool_id}
    if command:
        request["_meta"] = {"cognition.ai/editableCommand": command}
    send({"id": request_id, "method": "session/request_permission",
          "params": {"sessionId": SESSION, "toolCall": request, "options": OPTIONS}})
    while True:
        message = read()
        if message is None:
            sys.exit(0)
        if message.get("id") == request_id and "method" not in message:
            return message["result"]["outcome"]


def turn(prompt_id: int, text: str, cwd: str) -> None:
    if MODE == "crash":
        sys.exit(3)
    if MODE == "permissions":
        outside = cwd.rsplit("/", 1)[0] + "/outside.txt" if "/" in cwd else cwd + "\\..\\outside.txt"
        results = [
            ask(901, "t1", "execute", "Ran git", command="git status --short"),
            ask(902, "t2", "execute", "Ran git", command="git push origin main"),
            ask(903, "t3", "edit", "Wrote outside", locations=[{"path": outside}]),
            ask(904, "t4", "edit", "Wrote inside", locations=[{"path": cwd + "/inside.txt"}]),
        ]
        say(" ".join(r.get("optionId", r["outcome"]) for r in results))
    elif MODE == "unsupported":
        send({"id": 950, "method": "fs/read_text_file", "params": {"sessionId": SESSION, "path": "x"}})
        while True:
            message = read()
            if message.get("id") == 950:
                say(f"callback error {message['error']['code']}")
                break
    elif MODE in {"hold", "ignore_cancel"}:
        update({"sessionUpdate": "plan", "entries": [{"status": "in_progress", "content": "wait"}]})
        while True:
            message = read()
            if message is None:
                return
            if message.get("method") == "session/cancel" and MODE == "hold":
                send({"id": prompt_id, "result": {"stopReason": "cancelled"}})
                return
    elif MODE == "limit":
        say("partial")
        send({"id": prompt_id, "result": {"stopReason": "max_tokens"}})
        return
    else:
        update({"sessionUpdate": "tool_call", "toolCallId": "r1", "kind": "read", "title": "Read file"})
        update({"sessionUpdate": "tool_call_update", "toolCallId": "r1", "status": "failed"})
        say("echo: ")
        say(text)
    send({"id": prompt_id, "result": {"stopReason": "end_turn", "usage": {"totalTokens": 7}}})


def main() -> None:
    cwd = ""
    while True:
        message = read()
        if message is None:
            return
        method, request_id = message.get("method"), message.get("id")
        params = message.get("params", {})
        if method == "initialize":
            if MODE == "startup_hang":
                time.sleep(30)
            version = 99 if MODE == "bad_version" else 1
            send({"id": request_id, "result": {"protocolVersion": version, "authMethods": []}})
        elif method == "session/new":
            cwd = params["cwd"].replace("\\", "/")
            update({"sessionUpdate": "config_option_update", "configOptions": CONFIG})
            send({"id": request_id, "result": {"sessionId": SESSION, "modes": MODES, "configOptions": CONFIG}})
        elif method == "session/load":
            cwd = params["cwd"].replace("\\", "/")
            say("replayed history that must not appear in the new answer")
            send({"id": request_id, "result": {"modes": MODES, "configOptions": CONFIG}})
        elif method == "session/set_mode":
            send({"id": request_id, "result": {}})
        elif method == "session/prompt":
            turn(request_id, params["prompt"][0]["text"], cwd)


if __name__ == "__main__":
    main()
