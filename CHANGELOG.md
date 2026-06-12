# Changelog

Releases are semver tags (`vMAJOR.MINOR.PATCH`); what counts as a breaking change is defined by
the versioned interface in [`AGENTS.md`](AGENTS.md). Consumers pin a tag and advance it
deliberately.

## Unreleased

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
