---
name: codex-cli
description: "When handing work to the Codex CLI earns its cost, and how to size the run: second-model review, bounded implementation hand-offs, sandbox permissions, model and reasoning effort. Use when the user asks for Codex or `codex exec`, when a change is complex or high-stakes enough that an independent reviewer would change the outcome, or when a delegated run needs its model, effort, or permissions chosen. For agents other than Codex itself."
license: Apache-2.0
metadata:
  author: scarletkc
  source: https://github.com/scarletkc/agents
  summary: "Reach for the Codex CLI when a task is hard enough to earn it: second-model review, bounded hand-offs, sandbox permissions, and a model and effort matched to the difficulty."
---

# Codex CLI

Codex is a second agent on the same machine, with its own model behind it.
That is the entire reason to reach for it: a model that did not write the code
has no memory of intending it to work. Everything below follows from that one
asymmetry — who wrote it, who reads it, and how much thinking each step is
worth paying for.

This skill is for the supervising agent, not for Codex. If you *are* Codex,
this does not apply — calling yourself buys nothing but a second opinion from
the same mind. Claude Code is the intended caller.

It also assumes the machine is already set up: `codex` on `PATH`, the user
logged in, and whatever MCP servers and tools they want available configured
in `~/.codex/config.toml`. If the binary is missing, auth has expired, or a
run dies on permissions, report that plainly and stop — quietly falling back
to doing it yourself hides the fact that the review the user asked for never
happened.

Concrete flags belong to `codex --help`, which is authoritative and moves
faster than this file. What follows is the judgment.

## When to reach for it

Every invocation is a second model spending the user's money and your
wall-clock time. It earns that when the problem is hard enough that another
model changes the outcome — not as a reflex after every edit. Doing the work
yourself and checking it with the project's own tests remains the normal path.

- **When the user asks for it.** They have already made the call; don't
  re-litigate it. Match the model and effort to the task and go.
- **After writing something complex or expensive to get wrong.** Your own
  review of your own diff is the weakest review available, because you are
  checking the code against the intent you already have in your head rather
  than against what it says. That weakness only matters when the defect would
  be costly — concurrency, migrations, security-adjacent paths, platform
  assumptions, anything on a compatibility surface. A routine edit that the
  suite already covers is not worth a review pass. *Counter-example: an agent
  changed one side of a path comparison to a normalized form and left the
  other side platform-native; every test it wrote passed, because it wrote
  them against the same wrong mental model.*
- **When a demanding change is bounded well enough to describe in a prompt.**
  A hand-off is worth it when you can state the goal, the files, and the
  acceptance check in a paragraph. That paragraph is also the honest test of
  whether *you* understand the change — if you cannot write it, delegating it
  just moves the confusion downstream. The boundary binds Codex exactly as it
  binds you: pass it along in the prompt, because Codex cannot infer where the
  user drew it.
- **When the work is long, mechanical, and verifiable.** Wide renames,
  repetitive migrations, and mass edits with a green suite proving them buy
  throughput rather than insight, and they are cheap to check.
- **When you are stuck.** After two failed attempts on the same defect, a
  third attempt from the same context tends to repeat the second. A fresh
  agent with the symptom and the reproduction, and none of your accumulated
  theory, is a better use of the next few minutes.

## When to keep it

- **Ordinary work you can verify yourself.** Most changes are this. Writing
  the prompt, waiting for the run, and reading the diff costs more than the
  edit, and a delegated pass over a small change mostly returns items you
  already knew. Absent a reason above, just do it.
- **Judgment about words.** User-facing copy, documentation, naming, and
  release notes need the taste and the context of the session that has been
  talking to the user, and they survive delegation badly. See
  [`ux-writing`](https://github.com/scarletkc/agents/blob/main/skills/ux-writing/SKILL.md).
- **Anything you cannot check afterwards.** Delegating work you have no way
  to verify converts an unknown into a confident-sounding report, which is
  worse than the unknown. Establish the check first.
- **Decisions the user reserved.** Choosing the approach, committing,
  pushing, opening or merging a PR — those stay where the user put them. A
  permissive sandbox makes it *possible* for a delegated run to do all of
  them, which is a reason to scope the prompt tightly, not a licence to let
  it decide.

## Choosing the model

Pick from the task's difficulty, not from habit. Reaching for the strongest
model every time wastes the user's money on renames; reaching for the cheapest
on a subtle bug wastes the user's afternoon.

- **`gpt-5.6-sol`** — the frontier model. Worth it for reviews that must not
  miss anything, root-cause hunts, concurrency and lock-ordering questions,
  cross-platform semantics, and any change whose failure mode is silent.
- **`gpt-5.6-terra`** — balanced, and the sane default for ordinary feature
  work inside a boundary you have already defined.
- **`gpt-5.6-luna`** — fast and cheap with a lower ceiling. Right when a test
  suite or a compiler, not the model, is what actually decides whether the
  result is correct.

## Choosing the effort

Reasoning effort buys deliberation, not knowledge, and it multiplies both
latency and cost. Scale it with how subtle the failure would be:

- **`medium`** — mechanical work with an immediate, objective check.
- **`high`** — real implementation work and routine reviews. The usual pick.
- **`xhigh`** — subtle bugs, unfamiliar subsystems, anything one attempt has
  already failed at.
- **`max`** — the hardest problems, when a wrong answer costs far more than
  the extra minutes. Deliberate, not habitual.

The pairing that matters most: **review the code at least as high as you wrote
it.** A cheap review of an expensive change finds the typos and misses the
reason you delegated it.

## Running it

Drive the non-interactive surface — `codex exec` for work, `codex exec review`
for review. Model and effort are per invocation: `-m <model>` and
`-c model_reasoning_effort=<level>`, both overriding the user's `config.toml`
defaults for that run only. Prefer `codex exec review` over the top-level
`codex review`, which is equally non-interactive but takes the model through
`-c model="..."` rather than `-m`. Review scope is `--base <branch>` for
a branch, `--uncommitted` for the working tree, `--commit <sha>` for one
commit. Everything else — `--json`, output files, resuming a session — is in
`codex --help`.

### Give it the permissions the task needs

This is the step that most often turns a delegated run into a wasted one.
`codex exec` is sandboxed, and its own default — before the user's config is
applied — is **read-only**: the model reads the repository, plans the change,
and every write is refused. Failures inside the sandbox are handed back to the
model rather than raised to you, so what returns is a fluent description of a
change that never reached disk.

- **Let the user's configuration apply, and reach for `-s` mainly to
  narrow.** Their `config.toml` already encodes the permission level they are
  willing to run at, and on many machines it is the setting that actually
  works. `-s read-only` is a sound narrowing for a review or an
  investigation, since nothing should be written anyway.
  `--ignore-user-config` discards their settings wholesale and is rarely what
  you want.
- **Raising the mode is a request, not a guarantee.** `-s workspace-write`
  asks for a writable workspace; whether it is granted depends on the
  platform's sandbox backend and on any `.rules` policy in effect, and on a
  host without a working backend the writes are refused anyway. So confirm
  with `git status` on the target tree rather than with the run's summary.
  When the answer is "nothing changed", the fix lives in the user's
  configuration or their host setup — say so, rather than rerunning the same
  command or escalating the flag yourself.
- **Widen the reach deliberately, not by default.** `--add-dir` makes another
  directory writable, which matters when the work spans a worktree and its
  main checkout; `-C` sets the working root; `--skip-git-repo-check` allows
  running outside a repository. `workspace-write` does not imply network
  access — that is a separate setting
  (`sandbox_workspace_write.network_access`), so dependency installs inside
  it fail until it is enabled.
- **Treat full access as the user's call.** `-s danger-full-access` and
  `--dangerously-bypass-approvals-and-sandbox` remove the boundary that keeps
  a delegated agent inside the task. Some users configure exactly that
  globally and are happy with it; inheriting their setting is different from
  escalating to it yourself on a task they scoped narrowly.

### Write the prompt like a brief

- **Put the acceptance check in it.** State the goal, the files in scope, the
  test or command that proves it, and the boundary it must not cross. Codex
  cannot see your conversation with the user, so anything the user said that
  constrains the change has to be restated.
- **Ask review prompts for specifics.** "Review this" returns prose. Naming
  what you are unsure of — the migration path, the error handling, the
  platform assumption — returns findings you can act on.

## Reading the result back

A Codex run is a proposal, not a merge. You asked for a second model precisely
because a single model's confidence is not evidence, and that cuts both ways.

- **Read the diff, not the summary.** The report describes what Codex meant
  to do. Only the diff says what it did, and the gap between the two is where
  the surprises live — the unrelated file it touched, the test it relaxed to
  make something pass, the fallback it added to keep an error from surfacing.
- **Run the suite yourself.** "Tests pass" from the agent that changed the
  tests is a claim about the same run that produced them.
- **Findings are input, not a verdict.** A review from a strong model still
  produces items that are wrong about this codebase or out of scope for this
  change. Judge each one, fix what is real, and say plainly which ones you
  dismissed and why — an unexplained dismissal reads as an oversight later.
- **Report the division of labour.** When the user reads the result, they
  should know which parts another agent wrote and what you verified. That is
  what makes the supervision worth anything.
