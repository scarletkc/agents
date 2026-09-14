# Agents

Shared standards and skills for AI coding agents: Claude Code, Codex CLI,
and anything else that reads `AGENTS.md` or the
[SKILL.md](https://agentskills.io) format.

## Featured in

- [Awesome Agent Skills](https://github.com/VoltAgent/awesome-agent-skills/blob/main/README.md#development-and-testing)

## Contents

- [`AGENTS.md`](AGENTS.md): project-agnostic base guidelines. Copy it into a
  repository and prepend the project-specific sections (structure, commands,
  domain notes).
- [`user/AGENTS.md`](user/AGENTS.md): user-level collaboration preferences,
  kept separate from the project-level guidelines.
- [`skills/`](skills/): cross-agent skills; each skill is a directory
  containing a `SKILL.md` plus optional resources.

## Skills

Each summary is generated from the skill's own metadata. Open its `SKILL.md`
for the complete activation description and instructions.

<!-- skills:start -->
| Skill | Summary |
|-------|---------|
| [antigravity-cli](skills/antigravity-cli/SKILL.md) | Delegate work to Antigravity CLI, inspect progress and tool failures, and continue the same conversation across follow-up tasks. |
| [ask-to-plan](skills/ask-to-plan/SKILL.md) | Turn a rough idea into clear goals, requirements, a solution, and an actionable plan through guided questions and native choices. |
| [codex-cli](skills/codex-cli/SKILL.md) | Reach for the Codex CLI when a task is hard enough to earn it: second-model review, bounded hand-offs, sandbox permissions, and a model and effort matched to the difficulty. |
| [grok-cli](skills/grok-cli/SKILL.md) | Delegate work to Grok Build, keep its session for follow-ups, and inspect results while the supervising agent continues working. |
| [marketing-copy](skills/marketing-copy/SKILL.md) | Write outbound promo copy that stays truthful, discloses only what may be public, and earns attention without hype. |
| [product-writing](skills/product-writing/SKILL.md) | Write accurate product copy and useful technical docs. |
| [scoped-change](skills/scoped-change/SKILL.md) | Hold a change to the size the request defines: no unrequested surfaces, no speculative layers, no half-applied edits. |
| [talk-like-scarletkc](skills/talk-like-scarletkc/SKILL.md) | Write and translate in scarletkc's natural voice without generic AI phrasing. |
| [ux-writing](skills/ux-writing/SKILL.md) | Review user-facing copy and documentation for clarity, consistency, facts that do not go stale, and no leftover intermediate state. |
| [worktree-pr](skills/worktree-pr/SKILL.md) | Optionally run a task in its own worktree: branch from the integration branch, compare against the baseline, and prepare it for a PR. |
| [x-content](skills/x-content/SKILL.md) | Find worthwhile X topics and write posts that earn attention and keep readers engaged. |
<!-- skills:end -->

[`product-writing`](skills/product-writing/SKILL.md) is a compact alternative to
[`ux-writing`](skills/ux-writing/SKILL.md) for product copy and technical docs.
Use one of these guides for a task. `ux-writing` retains the original, more
detailed rules; `product-writing` leaves more structural and editorial choices
to the task.

## Install skills

Send this prompt to your coding agent:

> Install skills from https://github.com/scarletkc/agents. Show me the available
> skills and let me choose which ones to install.

You can also use either CLI directly. Both installers let you choose individual
skills. Replace `codex` with another supported agent, such as `claude-code`,
when needed.

### GitHub CLI

Browse the repository and install a skill for the current user:

```sh
gh skill install scarletkc/agents --agent codex --scope user
```

For a non-interactive installation, provide the skill name:

```sh
gh skill install scarletkc/agents <skill> --agent codex --scope user
```

Update installed skills with `gh skill update --all`.

### skills CLI

Browse the repository and choose skills and agents interactively:

```sh
npx skills add scarletkc/agents -g
```

For a non-interactive installation, provide the skill and agent:

```sh
npx skills add scarletkc/agents --skill <skill> --agent codex -g -y
```

Update global skills with `npx skills update -g -y`.

## Package a skill

Create a ZIP for a web app that accepts skill uploads:

```sh
python scripts/package_skill.py <skill>
```

The archive is written to `dist/<skill>.zip`. Its root contains `SKILL.md`
and the skill's supporting files, ready to upload as one file. Root-level
`evals/` and local build artifacts are excluded.

The CLI skills bundle their shared task runtime so each skill can be installed
independently. After editing `scripts/agent_task_runtime.py`, run
`python scripts/sync_agent_runtime.py` to update the bundled copies. The test
suite checks that those copies match the maintained source.

## Feedback and contributions

Report problems or suggest improvements through
[GitHub Issues](https://github.com/scarletkc/agents/issues). Pull requests are
welcome.

## License

[Apache-2.0](LICENSE). Attribution information is provided in
[`NOTICE`](NOTICE).
