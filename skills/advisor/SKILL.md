---
name: advisor
description: "Seek an independent diagnosis when materially different attempts stop producing evidence, observations contradict the current theory, or uncertainty makes the next experiment costly. Use for stalled debugging and difficult engineering decisions; skip routine first failures, cases answered by existing docs or tests, and requests for reassurance."
license: Apache-2.0
metadata:
  author: Zhong-fan
  source: https://github.com/scarletkc/agents
  summary: "Get a bounded second opinion when progress stalls, then keep ownership of implementation and validation."
---

# Advisor

An advisor helps the worker choose what to test next. The worker still owns the
task, the changes, and proof that they work.

Keep routine execution with the worker and spend stronger-model reasoning on
the specific bottleneck, through a short diagnosis request.

## Decide whether advice would help

First inspect the error, relevant code, docs, and tests. Continue directly when
they identify a clear next step or when each attempt is producing useful new
evidence. A first failure alone does not justify consultation.

Consult when different plausible approaches have failed without narrowing the
cause, the observations contradict the working theory, or choosing between
remaining explanations requires an expensive or risky experiment. Concurrency,
architecture, and platform interactions can justify earlier advice when a small
local check cannot resolve the uncertainty. Repeating one command without
learning is a reason to change the investigation, not to count retries toward a
fixed threshold. Do not consult merely to reassure yourself about a settled choice.

## Prepare a bounded brief

Give the advisor enough evidence to challenge the theory, including inconvenient
results. Separate observations from assumptions. Include:

- **Goal:** the behavior to achieve and the scope of the task.
- **Observed facts:** exact errors, environment, relevant code, and a minimal
  reproduction. Label untested claims and keep secrets out of the brief.
- **Attempts and results:** materially different checks or changes, what each
  established, and what it ruled out. Include failed results.
- **Current theory:** the suspected cause and evidence for and against it.
- **Constraints:** relevant compatibility, permissions, cost, and acceptance
  requirements; identify actions needing the user's approval.
- **Specific question:** the assumption to challenge or experiment to choose.

Ask for likely causes, missing assumptions, and the smallest test that separates
the remaining explanations, with expected outcomes. For example: "Both writes
succeed alone but one sidecar disappears when they overlap. Which transaction
boundary could permit deletion, and what two-process test would distinguish it
from a failed rename?" Do not ask the advisor to take over or fix the entire task.

## Choose an available advisor

Prefer an available advisor with stronger reasoning capability relevant to the
bottleneck, within the user's permissions and cost constraints. Use the host's
consultation tool or a separate agent; leave the permitted model choice to the
matching provider integration. A fresh context can also expose assumptions the
worker has stopped questioning. If invoking an external CLI, use the matching
provider skill already available in the environment for invocation, sessions,
authentication, and permissions. This skill does not prescribe a provider,
model, command, or flag. Do not install tools or expand access just to consult.

If no suitable advisor is available or invocation fails, report that limitation
and continue with an explicitly identified local test when one is useful. If
progress depends on missing evidence or permission, report the blocker to the
user. Never imply an independent consultation happened when it did not.

## Act on the diagnosis

Evaluate the advice against the observed facts. Prefer a discriminating test to
an unexplained patch. Run the selected test, compare its result with the predicted
outcomes, then implement and validate the solution within the original scope.
Advice is a hypothesis, not evidence that the fix works.

Consult again only after new evidence creates a specific unanswered question.
Do not resend the same brief for more agreement, keep retrying a failed advisor,
or ask the advisor to recursively consult another advisor. If advice repeats
without adding a useful test, stop the consultation loop and state which fact
or decision is still missing.
