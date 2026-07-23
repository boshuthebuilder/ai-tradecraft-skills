---
name: agent-tiered-planning
description: >-
  Plan and dispatch work across a mixed-capability pool of coding agents (humans, frontier models,
  cheaper models) by labeling every issue with an agent-capability tier orthogonal to its effort
  estimate, publishing a playbook cold agents read before picking up work, and enforcing an
  escalation rule when an issue exceeds its tier. Use when a repo's backlog is executed by more than
  one class of agent — at planning time (assign tiers as issues are written) and at pickup time (the
  protocol any cold agent follows). Pairs with design-direction-lock (how standard-tier agents safely
  take design-facing work), implementation-discipline (how any tier conducts itself inside an
  issue), and adversarial-review (the gate the upper tiers mandate).
---

# agent-tiered-planning

A backlog executed by mixed-capability agents fails in a specific way: work is routed by *size*,
but size is the wrong axis. A one-hour task can require deep judgment; a two-day task can be pure
mechanical execution. When a cheap agent picks up a subtle-but-small issue, the failure is not a
delay — it is a **wrong-but-merged implementation** that downstream issues inherit. Tiering makes
capability an explicit, labeled dimension of every issue, so the routing decision is made once, at
planning time, by whoever understands the work best — instead of implicitly, at pickup time, by the
agent least equipped to judge it.

The deep principle (shared with design-direction-lock): **move judgment upstream into artifacts**.
Every hour the planner spends classifying work correctly is repaid by cheaper agents becoming safe
to use at all.

## The tier axis

Two orthogonal label dimensions on every issue:

- `effort:XS|S|M|L|XL` — how *big* (under 1h · 1–3h · half day · full day · 2–3 days, XL a
  candidate to split).
- `agent:standard|senior|frontier` — how much *capability* it needs. A different axis: a small task
  can still be subtle.

Define the tiers by **work character**, with model classes only as illustrations (models change;
the character of work does not):

- **`agent:standard`** — spec-complete and bounded: the issue states exactly what to build and how
  to verify it, and existing patterns in the repo cover the approach. Any competent coding agent
  (e.g. a mid-tier model at medium effort).
- **`agent:senior`** — requires judgment: cross-module integration, numeric calibration, or a
  quality bar that a literal reading of the spec will not reach. A strong agent, or a mid-tier one
  at high reasoning effort; the adversarial-review gate applies to its PRs (see below).
- **`agent:frontier`** — sets patterns other issues will inherit, or contains genuine ambiguity the
  implementer must resolve. The strongest available agent — and the adversarial-review gate is
  mandatory, not optional.

**Assigning tiers at planning time** — ask three questions of each issue, in order:

1. Will other issues inherit this one's choices (an architecture, a schema, a visual pattern)? Or
   must the implementer resolve real ambiguity? → `frontier`.
2. Does it cross modules, set or calibrate numbers, or carry a quality bar beyond the literal
   spec? → `senior`.
3. Otherwise — and only if the spec says exactly what and how to verify — `standard`. An issue that
   *cannot* be written that precisely is not a standard-tier issue no matter how small it is;
   either sharpen the spec or raise the tier.

## The playbook

The rules live in the repo, not in anyone's head: a short `CONTRIBUTING.md` (template bundled) that
every cold agent reads before picking up work. It carries the pickup protocol, the tier
definitions, the escalation rule, the review-gate coupling, and a pointer to the authoring
conduct rules (see implementation-discipline) — so an agent with no conversation history can act
correctly from the issue text alone. This presumes the repo's issues are themselves
written for cold readers (acceptance criteria, explicit dependencies); tiering does not rescue an
underspecified backlog.

**The pickup protocol** (the template's core):

1. Pick an open, non-epic issue whose `Depends on` issues are all closed and whose `agent:*` tier
   matches your capability.
2. Work on a branch named `issue-<n>-<slug>`; never push to the default branch.
3. Open a PR referencing the issue; its acceptance criteria are your definition of done. Attribute
   your agent identity per the repo's convention.
4. If anything user-visible is involved, the design lock is normative (see design-direction-lock):
   implement what it shows, not what you would have designed.

## The escalation rule

> If an issue turns out to be harder than its tier: **stop, comment with what you found, relabel up
> one tier, and leave it** for a stronger agent.

State the economics in the playbook, because they are what make stopping feel legitimate rather
than like failure: **a wrong-but-merged implementation of a high-tier issue costs more than a
delayed one** — it merges confidently, reads plausibly, and poisons everything downstream that
inherits it. Escalation is the system working, exactly like a well-run on-call rotation.

The reverse case needs no ceremony: an issue that turns out easier than its tier is simply done,
and the planner calibrates future labels from it.

## Coupling to the review gate

Tiers and the adversarial-review gate reinforce each other: **every `senior` and `frontier` PR runs
the cross-model adversarial review before merge** (see the adversarial-review skill — reviewer ≠
author by model, findings on the PR, iterate to convergence). `standard` PRs follow the repo's
normal bar. This is the safety net that makes delegating real work to the upper tiers responsible,
and the reason a mis-tiered issue that escalates late still gets caught.

## Tiers as spend routing

Capability tiers are also a **quota device**. Frontier-model subscription windows are the scarce
resource in an agent-heavy workflow; tiering routes the bulk of the backlog to cheaper models (or
separate pools) and preserves frontier headroom for the issues that genuinely need it. The same
logic the adversarial-review skill applies to *reviewer* selection (diversity first, quota second,
separate pools when primary windows run low) applies here to *author* selection — the tier label is
where that decision is recorded.

## Templates

- `templates/CONTRIBUTING.md` — the playbook skeleton: pickup protocol, tier definitions,
  escalation rule, review-gate coupling, conduct pointer. Adapt names and conventions; keep the
  escalation economics sentence.
- `templates/labels.sh` — `gh label create` commands for the `agent:*` scheme (and the `effort:*`
  scheme where the repo lacks one).
