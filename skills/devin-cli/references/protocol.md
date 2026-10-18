# Devin ACP details

How `devin acp` behaves on the wire, as the helper relies on it. Run
`devin acp --help` for the current flags; when the CLI's behavior differs
from this page, trust the CLI and update the page.

## Process

`devin acp [--model <name>] [--agent-type review|summarizer]` reads and
writes newline-delimited JSON-RPC 2.0 on stdio, UTF-8. Stderr carries
verbose tracing, which the helper saves to `devin.stderr.log`. `--model`
accepts the same fuzzy names as `devin --model` and sets the session's
`model` and `thought_level` options; `DEVIN_MODEL` in the environment sets
the same default. `--cloud` relays to Devin Cloud; the helper does not use it.

## Setup

1. `initialize` with `protocolVersion: 1`. The result advertises
   `loadSession: true` and an interactive `authMethods` entry (browser
   login). Stored CLI credentials are used automatically, so the helper sends
   no `authenticate` request.
2. `session/new` with `cwd` and `mcpServers: []` returns a `sessionId`. The
   ID is a readable name such as `steady-otter`, and Devin persists the
   session.
   - `modes` lists `accept-edits` (Code), `smart`, `ask`, `plan`, and
     `bypass`, plus the current mode.
   - `configOptions` reports `mode`, `model`, `thought_level`, and `speed`
     with their current values.
3. `session/set_mode` with `modeId` switches the mode; the helper only sends
   modes the session listed.
4. `session/set_config_option` rejects values outside the offered list with
   error -32602. The `model` option's values are not the same set as the
   names `devin models list` prints (a name `--model` accepts can be
   rejected here), so the helper sets the model through the `--model` flag.
5. `session/load` with an existing `sessionId`, `cwd`, and `mcpServers`
   resumes a session. Before answering, Devin replays the history as
   `session/update` notifications (user and agent message chunks, tool
   calls). The helper ignores replayed text.

## A turn

`session/prompt` returns `stopReason` (`end_turn` for a normal finish) and
`usage` token counts when the turn ends. Meanwhile `session/update` carries:

| `sessionUpdate` | Meaning |
| --- | --- |
| `agent_message_chunk` | Answer text, streamed |
| `agent_thought_chunk` | Reasoning text; the helper does not keep it |
| `tool_call`, `tool_call_update` | Tool start, then status (`pending`, `in_progress`, `completed`, `failed`) with `kind`, `title`, and `locations` |
| `plan` | Devin's task list with per-entry status |
| `usage_update` | Context use (`used` and `size`) |
| `session_info_update` | Session title |
| `config_option_update`, `current_mode_update` | Effective options and mode |
| `available_commands_update` | Slash commands; ignored |

`session/cancel` (a notification) asks Devin to stop; the pending
`session/prompt` then answers with `stopReason: "cancelled"`.

## Permission requests

`session/request_permission` arrives after the matching `tool_call` update.
Its `toolCall` carries only `toolCallId` and, for shell commands,
`_meta["cognition.ai/editableCommand"]`. Take `kind`, `title`, and
`locations` from the earlier update. The options offered for a command are:

| `optionId` | `kind` | Effect |
| --- | --- | --- |
| `allow_once` | `allow_once` | Run this call only |
| `allow_session` | `allow_always` | Allow the command for the rest of the session |
| `allow_always` | `allow_always` | Persist an allow rule for this project |
| `allow_always_global` | `allow_always` | Persist an allow rule for all projects |
| `switch_bypass` | `allow_always` | Switch the session to bypass mode |
| `reject_once` | `reject_once` | Refuse this call |

Answer with `{"outcome": {"outcome": "selected", "optionId": ...}}`, or with
`{"outcome": {"outcome": "cancelled"}}`. The helper advertises no filesystem
or terminal client capabilities and answers any other client request with
-32601, so Devin runs its own tools.

Protocol reference: [ACP prompt turn](https://agentclientprotocol.com/protocol/v1/prompt-turn).
