---
name: ux-writing
description: "Judgment for text read by someone who wasn't there when it was written: user-facing output, error and help text, docs, comments, and generated deliverables. Use when that text is the substance of the work or under review."
license: Apache-2.0
metadata:
  author: scarletkc
  source: https://github.com/scarletkc/agents
  summary: "Review user-facing copy and documentation for clarity, consistency, facts that do not go stale, and no leftover intermediate state."
---

# UX Writing & Docs

User-visible text is product behavior and carries the same quality bar as
code. Every rule below is distilled from a real defect caught in review, and
keeps its counter-example because the reasoning is the point. When in doubt,
re-read the output as the user who just hit the problem.

## Status output & diagnostics

- **Report effective values, not stored ones.** A status display answers
  "what will happen when I run this", so resolve values exactly the way the
  runtime does, including environment variables and layered config.
  *Counter-example: a config viewer printed "API key set: no" while an env
  var held the key the next run would actually use.*
- **Diagnostics must stay truthful under failure.** When one config layer
  fails to load, fall back to the most complete state that still loads,
  never to blank defaults. A diagnostic that misreports is worse than one
  that aborts. *Counter-example: a broken project-level config made a doctor
  command check blank defaults and report a missing API key that was in fact
  configured; the fake failure buried the real one.*
- **Show deltas, not dumps.** A health/diagnostic command lists what
  deviates and who set it; the exhaustive listing belongs to the dedicated
  inspect command. Don't make one command duplicate another's job.
  *Counter-example: a doctor check printed fifteen "field: origin" lines,
  most of them saying "global". One line naming the two real overrides
  replaced the block.*
- **Annotate at the granularity of the claim.** If one sub-part of a
  composite value has a different source or state, say it on the sub-part;
  don't relabel the whole. *Counter-example: an env-injected API key
  relabeled an entire endpoint block "(environment)" although its URL and
  model came from a file. The fix was "key from env", with the block label
  unchanged.*
- **Re-read neighboring labels after adding metadata.** New suffixes collide
  with existing value labels. *Counter-example: "Embedding dimensions:
  default (default)", fixed by renaming the value "auto".*
- **Machine-readable output is a contract.** Porcelain/TSV/JSON output never
  gains decoration, notices, or annotations; informational text goes to
  stderr or the human-format path. Absence is part of the contract, so write
  the negative test (`"(project)" not in stdout`).
- **Never truncate the payload.** Paths, IDs, and URLs in diagnostics must
  survive narrow terminals un-ellipsized (disable auto-wrap/crop for those
  lines); a truncated path cannot be copied into the next command.

## Error messages

Every error answers three questions: what happened, where, and what to do
now. The strongest pattern: name the offending file or input, list the
rejected fields, list the allowed fields, and say where the rejected setting
belongs instead. Fail loudly rather than degrade silently; when catching an
exception purely to suppress a traceback, keep the message intact.

## Documentation

- **Each document has one responsibility, and it decides what belongs.** A
  page is a durable contract, a proposal, an investigation, a TODO, a dated
  work order, or a runbook — one of them, not several. Naming that first is
  what makes a canonical home decidable: a fact lives on the page whose job
  it is, and every other surface reaches it through a single specific link
  instead of a partial retelling on each page that happens to touch it. When
  two pages both claim to be the detailed spec, the broader responsibility
  keeps the shared rules and the narrower keeps only what its own surface
  adds. *Counter-example: an implementation plan stayed the de-facto spec
  after shipping, so the rules lived half there and half in the architecture
  doc; folding the stable rules into the contract and leaving the sequence in
  git history left one page to trust.*
- **Rationale is a genre of its own.** A how-to answers what to run, a
  reference answers what exists, and why-it-was-built-this-way belongs to a
  design record, an ADR, or the pull request that decided it. Answering the
  design question inside a usage page pushes the steps the reader came for
  below the fold, and the argument is also the part that rots first: the
  implementation moves on and only the guide still defends the old choice.
  An explanation produced because someone asked once belongs in that
  answer, not in a permanent page. *Counter-example: a setup guide spent
  its second paragraph on why this queue was chosen over two others; the
  queue was replaced a release later and the paragraph outlived it.*
- **One canonical home per fact.** Details that change together (field
  lists, precedence chains, supported values) live in exactly one document;
  every other mention links to it. Legitimate copies: artifacts distributed
  standalone (a bundled skill file that ships without the repo), and
  genuinely surface-specific nuance. *Counter-example: a seven-field
  allowlist pasted into five docs.*
- **Restating and linking is a bug, not thoroughness.** If a section
  duplicates the canonical content and then ends with "see X for the full
  contract", it already is the full contract. Delete the restatement; keep
  the link and whatever is specific to this surface.
- **Prefer the smallest sufficient edit.** When revising existing text,
  preserve unaffected wording, structure, and rationale. Remove genuine
  duplication, but do not rewrite neighboring prose or compress away useful
  distinctions without a reason. *Counter-example: changing one mandatory
  workflow into an optional one rewrote several surrounding sections, then
  over-corrected by removing useful context; a few local edits were enough.*
- **Insertion respects adjacency.** Before adding a section, check what the
  surrounding paragraphs attach to. *Counter-example: a new section landed
  between a flags table and its output-format footnote, orphaning the
  footnote in the wrong chapter.*
- **Adjectives need evidence.** "Recommended", "faster", "better" come from
  your own benchmarks, not optimism. *Counter-example: a feature was about
  to ship commented "# recommended" while the project's own eval showed it
  losing to the default on strong models. It shipped as "optional".*
- **Every README section has one job.** Positioning sections ("Why X?")
  don't accumulate feature bullets; quick-starts don't explain architecture.
  A README stays lean and links into the docs; detail accumulating there
  usually means it left its canonical home.
- **Order a page by what the reader needs first, and split when it stops
  being one task.** Open with scope and the authoritative entry points, then
  the common rules and the main path, and only then exceptions, recovery,
  and change checks. An overview layer summarizes stable semantics and links
  down; it does not carry field tables, full payloads, or current numbers to
  buy self-containment. When a page starts demanding that the reader
  understand several unrelated tasks, or whole chapters serve only two
  maintainers, that is the signal to split it — and the split leaves behind
  one line of purpose plus the link, never a second copy of the fact.
  *Counter-example: a getting-started page opened with the full option
  reference, so the three commands a first-time reader needed sat two
  screens below it.*
- **Reminders name the most-forgotten item only.** A guideline that
  enumerates every artifact reads as noise and gets skipped whole. "Update
  whichever docs the change affects; the bundled skill is the easiest to
  forget" beats a list of six file types.

## Facts that go stale

Docs are edited on a human cadence, while some facts change on every commit,
deploy, or restart. Writing one of those into a long-lived page is not a
maintenance burden, it is a defect on a delay: the page turns wrong on its
own, and nothing fails when it does. Record where the current answer is
read, not the answer. This is "report effective values, not stored ones"
applied to prose.

- **Never snapshot a value that moves faster than the doc.** Long-lived
  pages (README, architecture notes, runbooks, domain docs) carry the stable
  material: intent, invariants, boundaries, procedures, failure handling.
  Version and protocol numbers, image tags, build IDs, deployed commit
  hashes, object and migration counts, expiry dates, and "currently live /
  not yet shipped" claims all change without anyone re-reading the page that
  repeats them. Those belong in a changelog, in git history, or on the
  release ticket, where carrying a date is the point. The rule forbids the
  hand-maintained second copy, not the table: when a page genuinely has to
  show current values, generate it from the authoritative source at build
  time so it cannot drift silently. *Counter-example: a
  runbook opened with "production currently runs 2.3.1"; four releases later
  an on-call engineer trusted the line and worked through the wrong
  version's changelog.*
- **A pointer names a symbol, not a repository.** The canonical home for a
  fact is often code rather than a doc, and then the doc's job is to say
  where to read it instead of copying the value or the whole field table.
  Make the pointer land: a specific file plus a searchable symbol, function,
  data key, or heading. "See the source", a repo-root link, or a directory
  leaves the reader to re-derive what the sentence promised. If no single
  symbol owns the fact, that is a code problem surfacing as a doc problem;
  fix the boundary instead of papering over it with a copied table. A
  directory is a fair target in two cases only: the fact emerges from an
  ordered set with no single-file truth (migrations replayed in sequence),
  or the directory is a catalog some loader enumerates (locales, plugins,
  maps). Both still owe a searchable selection key — the naming convention,
  the loader function, the object name.
  *Counter-example: "protocol versions are defined in the networking layer"
  sent every reader grepping six files, and became a link to
  `PROTOCOL_VERSION` in `net/constants.py`.*
- **A doc cannot observe the runtime.** The repository answers how a commit
  is meant to behave; only the running system knows which commit is live,
  what is healthy, and which artifact is being served. Docs record the
  command or console that answers those questions, never the answer, and
  never promote merged code to "deployed". A successful deploy report is
  evidence on that release's ticket; copying it into a doc converts a
  one-time result into a standing hand-sync obligation. *Counter-example: a
  "current environment" table listing service versions was updated by hand
  after every deploy, until the deploy where it wasn't, and nothing in CI
  could notice.*

## The final state, not the path to it

A deliverable is read by someone who was not in the room while it was made.
Anything that only holds against the conversation behind it — an option
that was considered and dropped, a scope that was corrected, an instruction
the requester gave ten minutes ago — reads as noise at best, and at worst
as a claim about the product. Session context expires faster than the
artifact carrying it, so this is "facts that go stale" applied to the
conversation rather than to time. The test for any line: does it hold for a
reader who has never seen that conversation? "Without the bulk-download
panel" does not, because nobody expected one. "Not `json.dumps` here, the
payload has to keep key order for the signature check" does.

- **State what the code does, not what it nearly did.** Titles, summaries,
  and comments describe the shipped behavior; intermediate attempts,
  abandoned options, and negative scope belong to the discussion that
  produced them, which git history and the review thread already keep.
  *Counter-example: a requested cut left the pull request titled "Add
  export button (without the bulk-download panel)", so every reader had to
  understand a panel that never existed before reading the one that did.*
- **A comment carries the non-obvious reason only.** What earns the lines
  is a constraint the next reader cannot recover from the code: an ordering
  requirement, an upstream bug, a platform quirk. A "why not X" line
  qualifies when X is what that reader would reach for anyway, not when X
  is merely what this conversation happened to try and discard. Restating
  what the code plainly says, or defending it against an alternative nobody
  would propose, spends attention now and becomes a lie when the code
  around it moves. *Counter-example: a helper kept eight lines on why it
  held no cache, written the moment a reviewer asked for the cache to go;
  two rewrites later the paragraph was the only trace of either.*
- **Evidence serves the reader's decision, not the author's doubt.** A
  claim the reader has to act on — this one is faster, this default is
  safe, use this over that — owes its basis, and "adjectives need evidence"
  above says where the basis comes from. A statement of what the code does
  owes nothing, because nobody is being asked to believe anything: a cited
  standard, a benchmark number, or an appeal to consensus attached to it is
  answering a challenge that was never made. The test is whether removing
  the line changes what the reader can decide. Cited figures also age
  faster than the sentence carrying them, and nobody comes back to
  re-measure. *Counter-example: a config page defended its default with
  "benchmarks show a 40% improvement", measured two majors earlier against
  a code path that no longer existed; support was still quoting the
  number.*
- **A deliverable does not narrate its own production.** Generated reports,
  decks, exports, and screens are product content: they carry findings,
  values, and instructions, never the implementation notes, method
  rationale, or next steps of whoever produced them. "This page
  demonstrates", "we could also", and "implemented as" are the producer's
  voice leaking into the product, and the exceptions are narrow — copy that
  genuinely is help text or an empty state, and documents explicitly asked
  to record their own methodology. Reasoning has its own homes: the reply
  to the requester, the commit message, the pull request body, a planning
  file. *Counter-example: a generated status deck opened on a slide titled
  "Approach and next steps for this report", ahead of the numbers it had
  been asked for.*

## Sync sweep for behavior changes

A behavior change is unfinished until its copy sites agree. Grep for the old
wording across, in rough order of forgettability:

1. `--help` option strings, the most-missed site: a flag's help kept saying
   "show current configuration" after the command learned origin labels,
2. centralized message/string modules and command docstrings,
3. README and docs pages,
4. bundled skill files, plugin metadata, MCP tool descriptions (these are UX
   for agents, and the same rules apply),
5. roadmap or status notes describing the old behavior.

Then re-resolve the links involved: a renamed heading breaks every anchor
aimed at it, a moved file breaks the relative paths pointing at it, and
neither announces itself in a normal test run.

## Testing copy

- Assert flattened text or behavior, not console formatting: consoles wrap
  (~80 columns under test runners), so multi-word substrings split across
  lines. Flatten with `" ".join(output.split())` before substring
  assertions.
- Color env leakage: `FORCE_COLOR` / `COLORTERM` in the invoking shell make
  rich consoles emit ANSI into captured output; clear them for test runs.
- For machine formats, assert what must be absent, not only what must be
  present.
