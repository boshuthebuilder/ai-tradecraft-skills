---
name: implementation-discipline
description: >-
  How a coding agent conducts itself while implementing a change — the four disciplines that stop
  plausible-but-wrong work before it is written: surface assumptions and competing interpretations
  before coding (present them and stop rather than pick one silently); build the minimum that
  solves the stated problem (no speculative abstraction, configurability, or handling for
  scenarios that cannot occur — fail loud instead); change only what the task requires (every
  changed line traces to the request; unrequested improvements become issues, not diff hunks); and
  restate the task as verifiable success criteria with a step-then-verify plan before starting.
  Use at pickup time on any issue, before the first line of any change, in any repo executed by
  coding agents — and as the standard a reviewer holds a diff to. Pairs with agent-tiered-planning
  (the escalation rule is where a surfaced tier mismatch goes), design-direction-lock (the
  deviation protocol is the design-side channel for the same stop-and-ask), and adversarial-review
  (the gate that catches what conduct fails to prevent).
---

# implementation-discipline

An agent that codes first fails *confidently*. It resolves ambiguity silently instead of naming
it, invents scope the task never asked for, wraps the result in structure nothing needs — and the
diff it produces reads plausibly and merges wrong. None of these are failures of capability; they
are failures of conduct, and they occur at every capability level. The other development-process
skills move judgment upstream into artifacts — tiers, the design lock, the review gate. This
skill moves it upstream *within the change itself*: the judgment happens before the first line is
written, not after the review finds its absence.

Conduct is also what makes review possible. A disciplined diff — every hunk tracing to a stated
intent — is one a reviewer, human or the adversarial gate, can actually hold to account. An
undisciplined one hides its real defects among its unrequested ones.

## Assumptions before code

**Do not resolve ambiguity silently.** Choosing one reading of an ambiguous task and running with
it converts an open question into a confident wrong answer — the most expensive kind, because it
merges. Before implementing:

- State your assumptions where the work is recorded — the issue or the PR, not your own context.
  An assumption nobody can read is an assumption nobody can correct.
- If the task supports more than one interpretation, present the interpretations and stop —
  unless resolving that ambiguity is explicitly the task's remit, as it is for a frontier-tier
  issue (see agent-tiered-planning). Then the rule becomes: resolve it **on the record** — state
  the reading you chose and why, where a reviewer will see it. What is never yours is the silent
  resolution, buried in an implementation.
- Push back when the request itself looks wrong. A cold reader disagreeing with the spec is
  signal, not insubordination — say what looks wrong and why, then wait.

Each kind of surfaced problem already has a channel; route it there rather than inventing one:

- The task needs more capability or judgment than its tier implies → the **escalation rule**
  (agent-tiered-planning): stop, comment with what you found, relabel up, leave it.
- The better idea is design-facing → the **deviation protocol** (design-direction-lock): propose
  it on the issue and pause that part of the work until the owner answers.
- The issue is underspecified → the playbook's standing rule: comment describing what is
  underspecified instead of guessing.

This skill owns the general rule — surface, then route; those artifacts own their channels.

## The minimum that solves it

**Build exactly what the stated problem needs, and nothing on speculation.** No feature beyond
what was asked. No abstraction serving a second caller that does not exist. No configurability
nobody requested. Speculative structure is a bet the backlog has not placed — it costs review
attention now and carrying weight forever, against a payoff nobody has scheduled.

No error handling for scenarios that cannot occur, either — and this is not licence to swallow
errors. For a state that genuinely cannot happen, an assertion that fails loudly beats a
defensive branch that handles-and-continues: the assertion surfaces the impossible state, the
branch hides it. That is the conduct-level echo of this repo's fail-loud rule: a failure is a
named, visible state, never a benign default. The overbuild is the recovery path,
not the check.

The self-test, before pushing: would a senior engineer reading this diff call it overcomplicated?
If a 200-line change could be 50, the 50 is the deliverable.

## Every line traces to the task

**Touch only what the task requires.** Do not improve adjacent code, reformat lines that were
passing, or rename things you merely dislike — match the existing style even where you disagree
with it. The test is mechanical: every changed line in the diff traces to the request. A hunk
that does not is scope drift *even when it is an improvement*, because nobody asked for it,
nobody reviewed the decision to make it, and it widens the blast radius of a revert.

The distinction that keeps this workable:

- **Orphans your change created** — an import, variable, or function *your* edit made unused —
  are yours to remove. That is completing the change, not expanding it.
- **Pre-existing mess** — dead code, odd naming, a missing refactor — is not. Raise it as an
  **issue**, where the planner can tier and schedule it; never fold it into the current diff.
  The improvement is welcome; the unrequested hunk is not.

For anything user-visible this is the same rule the design lock states from the other side:
implement what the approved direction shows, not what you would have designed.

## Criteria before execution

**Restate the task as verifiable success criteria before starting it.** "Fix the bug" becomes
"write the test that reproduces it, then make it pass". "Add validation" becomes "write the tests
for the invalid inputs, then make them pass". A task with strong criteria lets you loop
independently — implement, verify, adjust — in small validated steps; a task held as "make it
work" needs a human check on every step, which is the opposite of delegation.

For multi-step work, state the plan as step-then-verify pairs, so each step has a check that
passes or fails rather than an impression of progress.

Half of this discipline lives upstream: a standard-tier issue is *defined* by stating exactly
what to build and how to verify it, and the pickup protocol already makes the issue's acceptance
criteria the definition of done (see agent-tiered-planning). This section is the implementer-side
mirror — when the criteria are given, they are the contract; when a task arrives without them (an
interactive request, a vague ask), deriving and stating them is the first act of the work, not an
optional preamble.

## Applies at every tier

These disciplines bind `standard`, `senior`, and `frontier` alike. They matter most where
supervision is thinnest — a standard-tier agent working alone from issue text has no reviewer in
the loop until the diff exists — and the upper tiers are additionally held to them by the review
gate, where an untraceable hunk or an unneeded abstraction is a finding, not a taste difference
(see adversarial-review). Discipline is not a substitute for the gate, nor the gate for
discipline: conduct prevents what review would otherwise have to catch, and review catches what
conduct failed to prevent.
