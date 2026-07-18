# Changelog

Releases are semver tags (`vMAJOR.MINOR.PATCH`); what counts as a breaking change is defined by
the versioned interface in [`AGENTS.md`](AGENTS.md). Consumers pin a tag and advance it
deliberately.

## v2.4.1 — 2026-07-18

The `adversarial-review` harness now runs the headless reviewer in an **isolated worktree** — a
PATCH hardening (no interface change; same flags, same typed exits). Closes the fifth silent-failure
class surfaced by the second consumer project (issue #19): a review round's `pr-<n>` checkout in the
coordinator's *live* tree not only stranded the branch (the existing after-the-fact restore guard
caught that) but *raced a coordinator editing the same tree* — a mid-round branch switch left a
concurrent `Edit` pointing at a file the checkout had removed.

### Changed
- **`tools/agy-review` isolates the review in a detached worktree at the PR head.** Before launching
  agy the harness fetches `pull/<n>/head`, pins it to a SHA (immune to a concurrent run clobbering
  the shared `FETCH_HEAD`), and `git worktree add --detach`s a throwaway tree; agy runs with its cwd
  there, so its branch-switching is confined to the worktree and the caller's checkout is never
  touched — you can keep editing while a review runs. Falls back (loud `WARN`) to the caller's tree
  plus the existing before/after branch-restore guard only when a worktree cannot be created. The
  worktree is removed on every exit path. SKILL.md documents this as the structural fix for the
  "re-assert your branch" rule.

## v2.4.0 — 2026-07-18

Two new skills complete the **development-process trio** (plan → build → gate) alongside
adversarial-review — practices harvested from a second consumer project (issue #19; a
parametric-furniture build executed by mixed-capability agents), generalised here. A MINOR release.

### Added
- **`agent-tiered-planning`** — plan and dispatch a backlog across mixed-capability agents:
  `agent:standard|senior|frontier` labels as a capability estimate ORTHOGONAL to effort (a small
  task can still be subtle); tier definitions by work character with a three-question assignment
  heuristic; the cold-agent pickup protocol in a repo playbook; the escalation rule ("stop, comment,
  relabel up, leave it" — a wrong-but-merged implementation costs more than a delayed one); coupling
  to the adversarial-review gate (senior/frontier PRs mandate it); tiers as spend routing (bulk work
  on cheaper models, frontier headroom preserved). Templates: CONTRIBUTING skeleton + `labels.sh`.
- **`design-direction-lock`** — freeze a converged design into a one-page normative artifact
  (references with the feeling named and explicit anti-goals; visual language with accent
  discipline; motion rules including the invariants a plausible animation silently breaks; product
  truths; one canonical reference design threaded through every surface), then stamp each
  design-facing issue with the lock revision and ONLY the rules that apply to that surface, plus the
  deviation protocol. Versioned: a direction change is a new revision + re-stamp, never silent
  drift. Templates: one-pager skeleton + issue stamp.

## v2.3.0 — 2026-07-16

The adversarial-review skill gains **quota-aware reviewer selection** and **follow-ups** — a MINOR
release (one new harness flag, two new SKILL.md sections; nothing renamed or removed). Both were
spiked empirically before building (resume incantation, model labels, denial autopsy).

### Added
- **`tools/agy-review --model "<label>"`** — run the review on another Antigravity-pool model
  (Gemini/Claude/GPT families; `agy models` lists the live labels). The pool is a separate
  subscription budget from the primary Claude/ChatGPT plans, so reviews can run without spending
  primary authoring headroom. An unknown label fails loud (rc=1, valid labels listed).
- **Conversation-id surfacing** — every harness result line (success and failure) carries the run's
  `conversation: <id>`; `agy --conversation <id> -p "…"` (flag before `-p`; plain headless works)
  reopens that run with full context. Documented as a *diagnostic*, not the round-to-round
  mechanism: continuity across rounds stays in the PR comment thread, the only session that
  survives switching reviewer legs. The autopsy pattern — asking a dead run what command it was
  proposing — is documented; it revealed a denied reviewer had been mid-way to a genuine defect.
- **SKILL.md: *Quota-aware reviewer selection*** — the chain degrades reactively by typed exits (no
  quota probe rebuilt inside the gate); the pool as a separate budget; diversity still outranks
  quota (same-family-via-pool = preserve-quota choice, disclosed like any weaker gate); older pool
  models are fine for adversarial reading.
- **SKILL.md: *Follow-ups — interrogating a review***.

### Changed
- Machine-setup grant `command(uv run pytest)` widened to **`command(uv run)`**: pytest already
  executes arbitrary repo code via test collection, so the narrow form bought no safety — and it
  killed a reviewer mid-insight reaching for `uv run python -c` to check packaging metadata, a
  check that later proved a real defect.

## v2.2.0 — 2026-07-16

A new skill — a **MINOR** release. This one is about the process that *builds* the system rather
than the system itself: the cross-model review gate the reference deployment runs on every complex
change, packaged so it works for any repo and any coding agent (Claude Code, Codex, or another CLI
agent driving a shell).

### Added
- **`adversarial-review` skill** — reviewer ≠ author by model; the fallback chain (Codex → Gemini →
  independent agent, with "a dead reviewer is a done reviewer"); the auditable PR-comment protocol
  (verdict + file:line findings on the PR, author replies to every finding, iterate to convergence);
  the **headless-reviewer contract** distilled from four production silent-failure classes (verify by
  artifact never exit code; bound + tree-kill; pin commands to permission-matchable forms; name the
  allowed command set; inline `--body` posting; fetch the reviewer's scratch clone); and the one-time
  machine setup for headless Gemini (`~/.gemini/config/config.json` `globalPermissionGrants` — the
  two look-alike settings files are decoys).
- **`adversarial-review/tools/agy-review`** — the bundled harness for the Gemini leg: repo-agnostic
  (repo derived from the caller's checkout), pre-flights the silent killers, bounds the run, verifies
  success by the posted PR comment (count-based, clock-skew-immune), and exits typed
  (`0 ok · 2 auth-needed · 3 permission-denied · 4 timeout · 5 no-comment · 6 bad-args`). Battle-tested
  by reviewing its own source through four converging rounds (11 findings → 3 → posting mechanics →
  APPROVE) in the reference deployment (family-ai-os #559).

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
