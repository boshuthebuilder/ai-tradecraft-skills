# Changelog

Releases are semver tags (`vMAJOR.MINOR.PATCH`); what counts as a breaking change is defined by
the versioned interface in [`AGENTS.md`](AGENTS.md). Consumers pin a tag and advance it
deliberately.

## v2.1.1 — 2026-07-15

Wording only, no contract change — a **PATCH**. Closes the last gap the reference deployment's
notification-hygiene work surfaced: the reason model was *duplicating the deterministic health surface*.
The reference deployment made its wiki-health needs-a-look self-clearing (a standing, per-project alert
that resolves when the condition clears), but the model still ALSO flagged the same machine-detectable
conditions in free text — un-keyed, so those escalations pile up run after run and never clear (a real
cluster of three near-duplicate "resolve this `.proposed.md`" alerts for one file).

### Changed
- **Archetype prompts** (`file-ingest/{ingest,reconcile}`): the model now **defers machine-detectable
  conditions to the deterministic health sweep** — pending `.proposed.md` siblings awaiting review,
  orphaned pages (citing a vanished source), and unreadable pages are surfaced (and self-cleared) by the
  deployment's reconcile-health sweep, so the model must not also record them in `needs_a_look`.
  `needs_a_look` is reserved for judgement calls the harness cannot detect (an ambiguous filing, a
  real-world inconsistency, an owner-only decision). The reconcile prompt's *deterministic-findings
  worklist* rule (v2.1.0) is tightened accordingly: fix what you can, but do not re-escalate the residual.

## v2.1.0 — 2026-07-12

Aligns the archetypes with the reference deployment's 2026-07 **System Jobs Review** (a 25-PR
implementation on family-ai-os). Additive only — new optional fields, new prose, no rename or removal —
so a **MINOR** release. The archetype prompts here are the templates stamped for every future
onboarding; this carries the review's corrections to source, so the next project is not born with the
defects the review fixed.

### Changed
- **Archetype prompts** (`file-ingest/{ingest,reconcile}`, `user-synthesis/{synthesise,reconcile}`)
  carry the six review rules: *partial-view honesty* (a capped/truncated listing never reads as
  "missing/orphaned"); *escalation quality* (`needs_a_look` gains `what_would_resolve` + optional
  `proposed_action`); *re-raise discipline* (reference a `previously_raised` open/dismissed item, never
  repeat it; reopen a recently-resolved one only on changed evidence); *deterministic-findings worklist*
  (reconcile works the pre-computed `{reconcile_findings}` block); *no-change silence* (a run that
  changed nothing omits `notify`); *figure fidelity* (quoted source values copied character-for-character).
  The `code/{digest,code-review}` archetypes already embodied these and are unchanged.
- **Coming Events is deterministic.** Like the Deadlines roll-up, `Coming Events` is now rendered
  deterministically by the deployment from the calendar snapshot — the prompts never build it. Wired as
  a project-wide `rollups.coming_events` capability.
- **`ARCHITECTURE.md`**: adds the **raised-item lifecycle** to the job contract (stable key on source
  path/identity · `open|resolved|dismissed` persistence · the ledger injected into every gather ·
  `what_would_resolve`); states **partial-view honesty** as a gather-contract requirement; acknowledges
  a bounded read-only **agentic** execution mode returning the same contract; adds Coming Events to the
  determinism boundary.
- **`wiki-maintenance/SKILL.md`**: pins the **canonical frontmatter keys** the deterministic sweeps read
  (mandatory `provenance`/`last-updated`/`status`; conditional `source`/`sources`, `deadline`/`deadlines`)
  and the one legacy alias readers accept (`updated:` → `last-updated:`).

### Added
- Archetype `jobs.yaml` templates carry the **full job contract**: explicit `execution_mode` (+ a
  commented agentic option and its read-only constraint), commented `max_budget_usd` guidance (a hit cap
  is an explicit `budget_exceeded` outcome, never a silent truncation), explicit `capabilities.skills`,
  and the file-ingest project-wide `rollups` block (`deadlines` / `open_questions` / `coming_events`).
- `AGENTS.md` documents `{reconcile_findings}` as an **optional** template placeholder (empty default)
  and `{current_knowledge}` as a **required** user-synthesis placeholder.

## v2.0.0 — 2026-06-23

**Breaking** — the `user-synthesis` archetype's write contract changes (see *Changed*). The reference
deployment ran the flow end-to-end before release; the public diff is placeholder-only (no real names,
project ids, or paths).

### Added
- **`user-onboarding` skill** (`skills/user-onboarding/`): onboard a *person* (an identity) — the
  storage-ownership handshake (the user owns the folder and shares it into the worker), the **type-1
  user vault** skeleton it scaffolds, and stamping the user-synthesis archetype. The identity-level
  sibling of `project-onboarding`.
- `ARCHITECTURE.md`: the **Storage ownership** prerequisite and **The type-1 user vault** section (the
  folder-IS-vault skeleton — `00 Index` / `01 Knowledge` / `02 Ideas` / `03 Reports` / `09 Schema` /
  `10 Log`, folder-notes, the three determinism stories, Knowledge ⊥ Ideas).

### Changed
- **`user-synthesis` archetype is now a `synthesise`/`reconcile` pair, not a lone job.** Its Knowledge
  area is **incrementally evolved** (read the current tree, make minimal stable changes, preserve
  paths) rather than regenerated wholesale — so, per the twin rule, it re-earns a periodic `reconcile`
  full-vault pass. Updated `jobs.yaml` (adds `reconcile`), `README.md`, `synthesise.md` (incremental),
  `scheduler.md` (the periodic clock), and added `reconcile.md`. `ARCHITECTURE.md`'s twin rule now uses
  this archetype as its worked example. **Supersedes the v1.0.0 "no reconcile twin / full re-synthesis
  each run" contract** — a breaking change to the archetype's write contract.

## v1.1.0 — 2026-06-23

### Added
- **`code` archetype** (`skills/project-onboarding/archetypes/code/`): the job pair for a git-backed
  project the system reads read-only and reports on — a periodic `digest` (plain-language summary of
  what changed) and a `code-review` (correctness/risk review). A third kind of source — a git clone,
  not the owner's documents or other wikis — read **deterministically** (`git` history is a pure
  function of clone state); the only writes are dated report pages through the deployment's guards,
  never to the code. No `ingest` (a clone has no inbox). README + `jobs.yaml` + the two prompt
  templates + `scheduler.md`.
- `ARCHITECTURE.md`: the `code` archetype as the third shipped family, reaffirming the determinism
  boundary for a repository source.

## v1.0.0 — 2026-06-12

### Added
- **`user-synthesis` archetype** (`skills/project-onboarding/archetypes/user-synthesis/`): a single,
  gated, LLM-reasoned job that synthesises a per-identity, cross-project (user-tier) wiki from the
  project wikis that identity may access. Deterministic gate + access-scoping; reasoning does the
  weaving; no `reconcile` twin (full re-synthesis each run).
- `ARCHITECTURE.md`: the **tiers and identities** model (project-tier wikis self-contained; the
  user-tier wiki as the one home of cross-project links; an *identity* as an access principal), the
  **twin rule** (a periodic `reconcile` exists only for incrementally-built artefacts that can
  drift), the user-synthesis gate inputs, and that an archetype's sources may be other wikis.
- `wiki-maintenance`: the **authored-note pattern** — a free-text inbox item with no source document
  routes to a Schema-declared authored domain as `provenance: manual`; reconcile may merge/link
  authored notes but never deletes or contradicts them.
- `project-onboarding`: pointer to when to stamp user-synthesis instead of file-ingest.
- `AGENTS.md` (+ `CLAUDE.md` symlink): working constraints — the genericness rule, the versioned
  interface, and this release protocol.
- This changelog.

## v0.x — pre-versioning history (summary)

Everything before the first tag, in brief: the wiki skill family (`wiki-onboarding`,
`wiki-maintenance`), the `project-onboarding` flow with the **file-ingest** archetype
(`ingest` + `reconcile`, `id == mode`, reactive gate + periodic pass), and `ARCHITECTURE.md`
reframing the repo as a general job framework for a headless assisting system (wiki as the
first layer, not the boundary). Consumers pinned bare commit SHAs during this period.
