---
name: devin-cli
description: "Delegate bounded coding tasks to the local Devin CLI over ACP from a supervising agent such as Claude Code or Codex. Use when the user asks to hand work to Devin, when an independent implementation, port, review, or investigation can run in parallel with your own work, or when an earlier Devin session needs a follow-up. Includes a blocking run helper with single-use permission answers, a deny policy, progress summaries, and session resume."
license: Apache-2.0
metadata:
  author: scarletkc
  source: https://github.com/scarletkc/agents
  summary: "Hand bounded tasks to Devin CLI over ACP, keep its permissions single-use, watch progress, and resume the same session for follow-ups."
---

# Devin CLI

Devin CLI is a separate coding agent on the same machine. `devin acp` speaks
the Agent Client Protocol over stdio; the bundled helper
[scripts/devin_acp.py](scripts/devin_acp.py) drives one turn, answers
permission requests from a local policy, and records everything in a run
directory. It uses only the Python standard library (3.10+). Resolve the
script relative to this installed skill, not the project being worked on.

Devin must already be installed and signed in. Signing in opens a browser,
so the user does it with `devin auth login`; the helper never authenticates
and never changes Devin's configuration. If `devin` is missing, signed out,
or out of quota, report that and the work that remains instead of quietly
doing the task yourself.

## Run a task

```sh
python <script> run --cwd <absolute-workspace> --prompt-file <brief.md> [--run-dir <dir>]
python <script> progress --run-dir <dir>
python <script> run --cwd <absolute-workspace> --resume <session_id> --prompt-file <follow-up.md>
```

`run` blocks until Devin ends its turn, so start it with your own background
facility (a background shell command, `nohup ... &`, `Start-Process`) when
you have other work. It prints JSON lines: `started` with the run directory,
`session` with Devin's session ID, and `finished` with the summary. It exits
0 only when the turn ended normally. Each run gets its own owner-only run
directory holding `final.md` (Devin's final message), `summary.json`,
`events.jsonl`, and `devin.stderr.log`; `run` refuses a directory that
already holds a run. The files contain the brief and Devin's output, so keep
them out of shared or tracked locations. `--help` lists every flag;
[references/protocol.md](references/protocol.md) covers the ACP details.

## Write the brief

Devin sees none of your conversation. A brief that works on the first try
states, in this order:

1. The goal and why it matters, in a paragraph.
2. The current state: what already exists, what is committed, where.
3. Files to read first, including the project's conventions.
4. The environment: absolute paths to interpreters and tools, environment
   variables, and the exact commands that build, test, and validate.
5. Scope: the files or modules this task owns, and what other workers own.
6. Rules: leave changes uncommitted; no branch, stash, reset, or push; the
   directories it must not touch.
7. Done means: commands that must pass and numbers that must hold (for
   example, the test count must not drop).
8. What the final message must contain: files changed, counts, every
   intentional deviation, and anything left unfinished.

Use a UTF-8 prompt file rather than shell-quoted text. Size each task so its
"done" can be checked in one pass; split a large port into steps whose
acceptance does not depend on work still in flight.

## Isolate and integrate

- Give every writing task its own git worktree, created from a commit that
  contains what Devin needs. If the base has uncommitted work, copy it in
  (`git ls-files -m -o --exclude-standard` lists it; in Git Bash on Windows
  pass `--force-local` to `tar` so `C:` paths are not read as remote hosts).
- Never let two writers edit the same files. Parallel tasks get explicit
  ownership lists in their briefs, and a module both need is ported first,
  on its own.
- Devin leaves its changes uncommitted. Review them, copy them into the
  integration tree, and commit there. Files changed on both sides need a
  manual merge.
- Restore or discard only named paths. `git checkout -- .` or
  `git reset --hard` in a tree with other uncommitted work destroys it.
- Remove the worktree and its branch after integrating.

## Permissions

The helper answers each request with a single-use option: `allow_once` or
`reject_once`. It never selects `allow_session`, `allow_always`,
`allow_always_global`, or `switch_bypass`, because those persist in Devin's
configuration or change the session's mode. By default it rejects git
operations that rewrite history or switch branches and worktrees, publishing
through `gh`, and edit, delete, or move requests whose target is outside
`--cwd` or missing. Adjust with `--deny <regex>`, `--no-default-deny`, and
`--allow-write-root <dir>`.

Shell commands are matched only against the deny patterns; a command can
write anywhere, so no path check applies to it. For a task that must not
change anything, pass `--read-only`: it rejects every edit, delete, move, and
shell-command request and starts the session in `ask` mode (`plan` is also
accepted).

The policy only sees what Devin asks about. In `accept-edits`, Devin's usual
default, it applies workspace edits and runs read-only tools without asking. Pick
the mode for the job with `--mode`: `ask` answers without editing, `plan`
plans first, `smart` auto-approves more, and `bypass` approves everything.
Use `bypass` only when the user explicitly authorizes it. None of this is an
OS sandbox; isolation comes from the worktree.

`permissions_denied` in the summary lists what Devin tried outside the
policy. Read it: a denial usually means the brief left a gap.

## Model and effort

`--model` takes the names `devin models list` shows; many include the effort
as a suffix (for example `-high`). Without it, Devin's configured default
applies. The summary's `config` reports the effective `model`,
`thought_level`, and `speed`; confirm them after the run. Use
`--agent-type review` for Devin's code-review agent, which reads and runs
shell commands but does not edit.

## Monitor

`progress` reports the tool-call count, recent tool titles, the latest plan,
denials, failed tools, the length of the answer streamed so far,
`seconds_since_last_event`, and the summary once finished. Large tasks routinely run for an hour or more; judge a stall by
`seconds_since_last_event`, not by elapsed time. `--timeout` (default 3600
seconds) cancels the turn; if Devin does not acknowledge, the helper stops
its process tree. Cancelling does not undo edits already made.

## Follow-ups

`run --resume <session_id>` continues the same conversation: Devin reloads
its history and `final.md` contains only the new turn. Prefer it for
corrections and the next step of the same task; it is cheaper and more
accurate than a new brief. The user can also open the session in Devin's
own interface with `devin --resume <session_id>`. `devin list` is an
interactive picker; do not call it from automation.

## Verify before accepting

`completed` means Devin ended its turn, not that the work is right. Run the
"done" checks yourself in the worktree, read the diff, look for files outside
the task's scope, and compare the final message's claims (counts, files)
with what is there. When a test suite is claimed to catch regressions,
break one input on purpose, confirm the suite fails, and restore it.
Report what Devin produced and what you verified.
