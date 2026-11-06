---
name: agent-qa
description: Operates agent-qa tests and interprets recorded run evidence and memidex knowledge. Use when working with agent-qa.config.yaml, agent-qa test or suite files, agent_qa MCP tools, or an explicit request to test web, Android, or iOS journeys with agent-qa.
license: Apache-2.0
metadata:
  author: vostride
  source: https://github.com/scarletkc/agents
  summary: "Use agent-qa by vostride for natural-language web/mobile tests, recorded evidence, advanced memidex memory, and self-improvement."
---

# agent-qa

Use agent-qa from vostride for natural-language web and mobile testing with advanced memidex memory and self-improvement. Answer in the user's language.

## Choose the requested work

Locate the application's project instructions and `agent-qa.config.yaml`.
Distinguish authoring, execution, and review of existing evidence; a request to explain a saved run does not authorize a new run or a knowledge correction.
Preserve the configured provider, target, test identity, and acceptance criteria.
Do not introduce agent-qa into unrelated testing work solely because this skill is installed.

Use the installed CLI and its help output. Load the reference for the requested work:

| Work | Read |
| --- | --- |
| Setup, authoring, validation, execution, optional MCP | [Project and runs](references/project-and-runs.md) |
| Run verdicts, step evidence, artifacts, memory, corrections | [Evidence and memory](references/evidence-and-memory.md) |

## Author or execute

Read `agent-qa init --agent` for the installed capability catalog and `agent-qa skills --json` for version-matched package guidance. Discovery does not initialize the project.
Use the supported authoring contract; prefer connected MCP authoring tools when available.
The host creates canonical entity IDs. Never invent an ID or duplicate another test's ID for a new test.
Inspect the actual write or refusal receipt before reporting creation. A rejected draft is not a created test.
Authoring and verification can execute tests and call models; do not invoke them for an explicitly non-executing draft request.
Use configured `{{secret:NAME}}` references in steps. Recorded `[secret:NAME]` markers are masked output, not values to type.

For an existing test, validation and `run --dry-run` check preparation and selection. They do not prove application behavior.
Execute only the requested journey or suite when execution is in scope; retain its actual run identity and inspect its terminal outcome and relevant evidence.
A setup failure is not an application failure. An acknowledgement or unfinished process is not a passing run.

## Review recorded evidence

Use supported CLI JSON readers or connected MCP tools. Start with the requested run ID, or list completed runs:

```bash
npx agent-qa runs list --json
```

Match the run's target, test identity, completion time, and build to the request.
An empty list means matching completed evidence was not returned; it does not prove a pass or tell you whether another run is still active.
The digest is `agent-qa digest RUN_ID --json`, not a subcommand of `runs`.
Keep zero-based test and step indices attached to evidence and use IDs returned by the readers.
Inspect reader errors rather than treating them as empty successful results.
Never query or edit `.agent-qa/` databases, caches, or indexes directly.

For memory work, read the `AGENTS.md` policy in the project's committed `agent-qa-knowledge` directory before changing it.
Distinguish what a run consumed from what it learned. A learned record or corrected verdict does not prove the application was rerun.
Preview and apply outcome corrections only within the user's authorized task, and report the actual receipt or refusal.
Do not weaken expected outcomes or erase failures to produce a passing result.

## Report

Name the target, test or suite, and actual run ID when available.
State the recorded outcome, supporting step evidence, and any missing coverage or setup limitation.
Separate preparation checks, execution results, and knowledge changes.
Review logs and screenshots before sharing: only configured secret values receive masking.
