# Changelog

Releases are semver tags (`vMAJOR.MINOR.PATCH`); what counts as a breaking change is defined by
the versioned interface in [`AGENTS.md`](AGENTS.md). Consumers pin a tag and advance it
deliberately.

## [Unreleased]

> Draft — not yet tagged. Released once the reference deployment proves the flow end-to-end and the
> pre-release privacy scrub passes (no real names, project ids, or paths in the public diff).

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
  each run" contract** — a breaking change to the archetype's write contract for the next tag.

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
