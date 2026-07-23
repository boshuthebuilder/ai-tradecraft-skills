# Working on <project>

This repo is built by a mix of humans and AI coding agents of different capability levels. Every
issue is written for a cold reader: if you cannot execute an issue without asking questions,
comment on the issue describing what is underspecified instead of guessing.

## Picking up work

1. Pick an open, non-epic issue whose `Depends on` issues are all closed and whose `agent:*` tier
   matches your capability (see below).
2. Work on a branch named `issue-<n>-<slug>`. Never push to `<default-branch>`.
3. Open a PR that references the issue, using the acceptance criteria as your definition of done.
   Attribute your agent identity per this repo's convention (label + PR-footer).
4. <If the repo has a design lock:> Match the design direction: `docs/design-direction.md` and the
   normative mockups are authoritative for anything user-visible — implement what they show.

## Conduct while building

While implementing, the `implementation-discipline` skill is the rulebook: assumptions surfaced
before coding, the minimum the issue asks for, every changed line traceable to the issue,
acceptance criteria as your step-then-verify plan.

## Agent tiers

Effort labels (`effort:XS` … `effort:XL`) estimate size. `agent:*` labels estimate the capability
needed, which is a different axis: a small task can still be subtle.

- `agent:standard` — spec-complete and bounded; the issue states exactly what to build and how to
  verify it; existing patterns cover it. Suitable for any competent coding agent.
- `agent:senior` — requires judgment: cross-module integration, numeric calibration, or a quality
  bar that a literal reading of the spec will not reach. The review gate below applies to its PRs.
- `agent:frontier` — sets patterns other issues inherit, or contains genuine ambiguity. Strongest
  available agent, and the adversarial review gate below is mandatory, not optional.

If an issue turns out to be harder than its tier: stop, comment with what you found, swap the label
up one tier, and leave it for a stronger agent. A wrong-but-merged implementation of a high-tier
issue costs more than a delayed one.

## Review gate

Every PR that touches more than one layer, introduces a new pattern, or is labeled `agent:senior`
or `agent:frontier` must pass the cross-model adversarial review before merge (the
`adversarial-review` skill: a different model reviews the open PR, findings land as PR comments,
iterate to convergence). Re-check your working branch after any review tool runs.

## Non-negotiable product truths

<List the handful of facts agents most often get wrong — the invariants a plausible-looking PR can
silently violate. If the repo has a design lock, point at it here.>
