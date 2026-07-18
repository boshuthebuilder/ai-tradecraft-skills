---
name: design-direction-lock
description: >-
  After a design direction has converged through mockup iteration, freeze it into a short normative
  artifact (docs/design-direction.md) carrying the references, visual language, motion rules, and
  product truths — then stamp every design-facing issue with the lock revision and only the rules
  that apply to that issue's surface, so implementing agents (especially cheaper ones) implement the
  approved direction instead of re-designing it. Use at the moment design review rounds converge on
  an approved direction, and again whenever the direction deliberately changes (a new lock revision,
  never silent drift). Pairs with agent-tiered-planning (the stamp is what makes design-facing work
  safe for standard-tier agents).
---

# design-direction-lock

Design converges in one place — a mockup review thread, a pair of eyes, a run of iterations — and
then dozens of issues implement it in many places, often executed by agents that never saw the
iteration. Without a lock, every one of those agents quietly re-designs: each PR drifts a little
toward what its model *would have* designed, review rounds burn on re-litigating settled choices,
and the product's visual identity dissolves into plausible-but-wrong. The lock converts taste into
a **normative artifact**: decided once, referenced everywhere, versioned when it changes.

This is the same principle as agent-tiered-planning — **move judgment upstream into artifacts** —
applied to design: the lock plus the per-issue stamp is what turns a design-facing issue from
senior-tier work ("exercise taste") into standard-tier work ("match the target").

## When to lock

Lock **at convergence, not before**: the mockup/design iteration has run its review rounds, the
owner has approved a specific revision, and the remaining work is implementation. A premature lock
freezes the wrong thing and then either blocks iteration or gets ignored — both worse than no lock.
Until convergence, mockups are proposals; after the lock, they are **normative**: implement what
they show, not what you would have designed.

## The lock artifact — `docs/design-direction.md`

One page, versioned in the repo next to the code it governs (template bundled). Head it with the
revision and what approved it ("locked at rev N, approved through <the review rounds/PR>"). Then:

- **References, with the feeling named** — the real-world designs the direction draws from, each
  with *why* (what quality it contributes), plus the feeling in a few words. Include the
  **anti-goals** ("explicitly not: …"): agents drift toward defaults, and naming the rejected
  directions is the cheapest way to block them.
- **Visual language** — ground and accent colours with their discipline ("one accent, for CTAs and
  active states only; <colour> reserved for warnings"), type roles, the rendering style for any
  product imagery. Point at the token file as the single machine home; the prose states the *rules*,
  the tokens state the *values*.
- **Motion rules** — the motion character (easing, sequencing, what motion is *for*), and above all
  any **invariants an animation must never violate** — physical or product constraints that a
  plausible animation can silently break. State reduced-motion behaviour.
- **Product truths** — the handful of facts implementing agents most often get wrong: structural
  realities, pricing presentation, localisation, what is simulated. These earn their place by
  having been gotten wrong (or nearly) at least once.
- **The normative surfaces** — link each approved mockup/screen, and thread **one canonical
  reference design** (one concrete configuration with real numbers) through all of them, so every
  surface is verifiable against the same example.

Keep it to a page: the lock is the *court of appeal*, not the spec of every screen — the mockups
carry the pixels.

## The issue stamp

The lock only works if implementers actually meet it, and cold agents read the issue, not the docs
tree. So **stamp every design-facing issue** with a dated block (template bundled):

- the lock revision and a link to the artifact and normative mockups;
- **only the rules that apply to this issue's surface** — three to six lines, selected, not the
  whole lock (an agent told everything is told nothing);
- the deviation protocol: propose the deviation in a comment on the issue and **pause that part of
  the work until the owner answers** — never implement it meanwhile. The escape valve that keeps the
  lock from blocking genuinely better ideas while making deviation a decision, not drift; waiting is
  what makes it a decision.

Stamp at lock time (sweep the open design-facing issues once) and at issue-creation time
thereafter. The stamp is additive — append it dated rather than rewriting the issue body, so the
issue's history stays legible.

## Versioning the lock

Direction changes are allowed; drift is not. A deliberate change = **a new revision**: bump the rev
in the artifact's heading, note what changed, and re-stamp the affected open issues. An implementer
who finds the lock contradicting a newer decision has found a process bug — say so on the issue;
never silently follow the newer decision and leave the lock stale.

## Templates

- `templates/design-direction.md` — the one-pager skeleton.
- `templates/issue-stamp.md` — the per-issue reference block.
