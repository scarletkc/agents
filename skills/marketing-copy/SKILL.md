---
name: marketing-copy
description: "Write outbound promotional copy for a product or project: launch and update posts for community platforms and social media, store page descriptions and short blurbs, landing page headlines and calls to action, press-style announcements, and the naming of a product for another language or market. Covers what may be disclosed publicly, keeping claims traceable to shipped changes, and writing a headline that carries information instead of hype. Use when drafting or revising anything aimed at people who do not use the product yet, and when deciding whether a link, key, price, or unreleased detail can appear in public copy."
license: Apache-2.0
metadata:
  author: scarletkc
  source: https://github.com/scarletkc/agents
  summary: "Write outbound promo copy that stays truthful, discloses only what may be public, and earns attention without hype."
---

# Marketing Copy

Outbound copy reaches people who have no product context and no reason to
finish reading. It is also the surface where a disclosure mistake is
permanent: a post can be deleted, a screenshot of it cannot. Both facts push
the same way, toward concrete claims a reader can check.

This covers copy aimed outward. Product-internal strings and documentation
follow
[`ux-writing`](https://github.com/scarletkc/agents/blob/main/skills/ux-writing/SKILL.md).

## Disclosure comes first

Decide what may be public before writing, because the draft is where a leak
gets normalized.

- **Keys, invite codes, and credentials are not copy.** Anything that grants
  access belongs in the channel that distributes it under its own terms,
  never inline in a public post, and never pasted into a draft "to be removed
  later".
- **An unreleased or unlisted URL stays unlisted.** A link that has not been
  announced is not published just because it resolves. The same applies to
  endpoints, staging hosts, and pages reachable only by those already told.
- **Platform rules bind the copy, not just the account.** Each destination
  has its own limits on what may be promoted, linked, priced, or given
  away, and they differ between platforms carrying the same post. When a
  rule makes a detail unpostable, drop the detail; hinting at it obliquely
  to stay within the letter of the rule is the same violation with worse
  writing.
- **Unshipped work is not a feature.** Roadmap items, planned platforms, and
  anything gated behind review get described as what they are, or left out.
  Announcing a date creates an obligation the copy cannot see.

When a constraint blocks a detail the requester wanted to include, say which
detail and why, and let them decide, rather than quietly dropping it or
quietly keeping it.

## Claims stay traceable

Take substance from what actually shipped: the changelog, the commit range,
the release notes. Every concrete claim traces to one of those, and an
adjective that carries a claim owes what "adjectives need evidence" in
`ux-writing` asks of it. What outbound adds is the exchange rate: specifics
beat adjectives at the same length, because a number, a mechanism, or a
before-and-after carries conviction that "greatly improved" cannot, and it
survives a reader who checks.

Never invent a metric, a benchmark, a user count, a review quote, or a
comparison against a named competitor. When the honest version is thin, that
is information about the release, not a prompt to inflate it.

## Writing for someone who has never seen it

Say what the thing is before saying why it got better. A reader who cannot
tell what the product does has no way to care that it improved, and an
update post aimed at existing users reads as noise to everyone else. When a
post has to serve both audiences, the identifying sentence costs one line
and buys the rest.

Revolutionary, seamless, game-changing, and unleash have stopped carrying
meaning in this genre: they appear in every launch post regardless of what
shipped, so a reader skips them to look for the specifics underneath. Write
the specifics instead. Manufactured urgency and invented scarcity fail the
same way, and cost more when the deadline turns out to be arbitrary.

A post may legitimately carry several asks, since a launch often wants the
wishlist, the community, and the download at once. Order them by what this
particular reader can act on now, and let each one be findable rather than
competing for the same sentence.

## Naming across languages

A product name rendered for another market is a naming decision, not a
translation. Check that the candidate is pronounceable and memorable for
that audience, carries no unintended meaning, and does not collide with an
existing product in the same category. Prefer a name the audience can
search, and once a rendering has shipped anywhere public, keep it stable. A
second name for the same product splits every search result and every
conversation about it.
