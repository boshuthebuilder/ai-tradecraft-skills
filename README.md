# ai-os-skills

The reusable framework — and the [Agent Skills](https://code.claude.com/docs/en/skills) that plug into it — for building a **headless AI assisting system**: one that runs unattended over a person's real folders, notices what changed, reasons over it, and keeps a synthesised layer current without being asked. The conventions live in **one home**, so interactive Claude Code / Cowork sessions and automated pipelines share the same logic.

## The framework

[`ARCHITECTURE.md`](ARCHITECTURE.md) is the core of the repo. It defines the **job** as the unit of work (one pass over a maintained folder: read state, reason once, return a structured result that deterministic guards turn into changes), the three layers of a job (prompt template · skill · deterministic guards), the determinism boundary, the gate that runs a cheap deterministic check before any model call, and reactive vs periodic scheduling. Each job family is an **archetype** with its own write contract — knowledge synthesis is the first, but folder hygiene, drafting, or any other family flows through the same layers and the same gate. The reference deployment is [`family-ai-os`](https://github.com/boshuthebuilder/family-ai-os), which consumes this repo as a pinned dependency.

## The knowledge layer — the skills shipped today

The first archetype implements the **in-folder knowledge wiki**: a synthesised, always-current layer over a folder of real files. Four skills cover the lifecycle:

- **`project-onboarding`** — stand up a self-maintaining folder end to end: create its wiki (via `wiki-onboarding`) and wire the two standard maintenance jobs — a reactive `ingest` pass and a periodic `reconcile` pass — from the **file-ingest archetype**. The whole-project flow; composes the two skills below.
- **`user-onboarding`** — onboard a *person* (an identity) rather than a folder: the storage-ownership handshake (the user owns the folder and shares it into the worker), the **type-1 user vault** ("second brain") skeleton, and stamping the **user-synthesis archetype** (an incremental `synthesise` + its periodic `reconcile` twin) so the person gets a self-maintaining, cross-project view over the wikis they can access.
- **`wiki-onboarding`** — bootstrap a wiki for a folder that doesn't have one: scan the folder read-only, propose a structure that mirrors how the owner already organises it, interview them on a few key points, then write the initial **Schema / Index / Log** skeleton. One-time and interactive; hands off to `wiki-maintenance`.
- **`wiki-maintenance`** — keep a wiki current: process an incoming item end to end (read → file by confident match → update the pages it touches → surface what needs a human → log), answer queries from the wiki, and run periodic reconcile (lint) passes. The method is portable; each wiki's own Schema page is the authority for its exact pages and layout. Includes the provenance model, the never-overwrite-a-human-edit guard, and a sensitive-data rule (identifiers as last-4 only).

## The development process — skills for building the system itself

The runtime skills above keep a deployment's folders current; these four keep the *building* of such systems honest across a mixed pool of coding agents. One theme runs through them: move judgment upstream into artifacts, so cheaper agents become safe to use. They span the lifecycle — **plan** (tier the work), **build** (lock the design, discipline the change), **gate** (review the change):

- **`agent-tiered-planning`** — label every issue with an `agent:standard|senior|frontier` capability tier orthogonal to its effort estimate; publish a playbook cold agents read before picking up work (pickup protocol, tier definitions); enforce the escalation rule — if an issue exceeds your tier: stop, comment, relabel up, leave it (a wrong-but-merged implementation costs more than a delayed one). Tiers double as spend routing: the bulk of a backlog runs on cheaper models, preserving frontier headroom. Includes CONTRIBUTING and label-scheme templates.
- **`design-direction-lock`** — after mockup iteration converges, freeze the direction into a one-page normative artifact (references with anti-goals, visual language, motion rules incl. invariants, product truths, one canonical reference design), then stamp every design-facing issue with the lock revision and only the rules that apply to that surface — so implementing agents match the target instead of re-designing it. Versioned: direction changes are a new revision plus re-stamp, never silent drift. Includes one-pager and stamp templates.
- **`implementation-discipline`** — the conduct any coding agent holds while writing a change: assumptions surfaced before code (competing interpretations presented, then routed to the escalation rule or deviation protocol rather than resolved silently), the minimum that solves the stated problem (no speculative structure — assert loudly rather than handle the impossible), every changed line tracing to the task (unrequested improvements become issues, never diff hunks), and the task restated as verifiable success criteria with a step-then-verify plan. The authoring-side counterpart of the review gate's scope-and-shape lens; binds every tier, and matters most where supervision is thinnest.
- **`adversarial-review`** — the cross-model review gate the reference deployment runs on every complex change: a *different* model from the one that wrote the code reviews the open PR adversarially and posts its findings as PR comments, iterating to convergence. Carries the reviewer fallback chain (Codex → Gemini → independent agent), the auditable PR-comment protocol, a bundled headless-Gemini harness (`tools/agy-review`, typed exits, verify-by-artifact), and the one-time machine setup headless reviewers need. Repo-agnostic and agent-agnostic — the method is markdown any coding agent can follow, and the harness is one dependency-free bash script.

## Install (Claude Code / Cowork)

```
/plugin marketplace add boshuthebuilder/ai-os-skills
/plugin install ai-os-skills@ai-os-skills
```

Then open the folder you want maintained and ask Claude to work on its wiki — `wiki-maintenance` loads automatically when relevant.

### Using it in a Cowork session

1. Run the two commands above in your Cowork session.
2. Point the session at the folder you want maintained (your own, or one shared with you).
3. Ask Claude to drain the inbox / update the wiki — the skill drives the rest.

You don't need any particular system to use these — they're self-contained method prose, no private data.

## Two writers on one folder is safe

If a folder is also maintained by a scheduled automation (an unattended safety net), your inline edits are never clobbered: a well-behaved system hashes every file it writes, so when it sees a page you changed it proposes a `.proposed.md` sibling instead of overwriting. Inline maintenance is first-class; the scheduled pass is the backstop.

## How updates propagate

- **Cowork / interactive** — you get the latest each session (the marketplace tracks this repo).
- **An unattended automation** — should consume a **pinned** clone at a release tag, advanced only through a reviewed deploy, never auto-latest. Releases are semver tags; what counts as a breaking change is defined in [`AGENTS.md`](AGENTS.md), and each release is recorded in [`CHANGELOG.md`](CHANGELOG.md).

Edit a skill here once → interactive sessions pick it up immediately → a pinned automation picks it up on its next deploy.

## Contributing

Two extension points:

- **A skill** — drop a folder under `skills/<name>/` with a `SKILL.md` (YAML frontmatter with at least a `description`). CI (`scripts/lint_skills.py`) lints every skill on push, so a malformed skill never ships. Validate locally with `claude plugin validate .`.
- **An archetype** — a new job family (its prompt templates, job declarations, and write contract) lives under `skills/project-onboarding/archetypes/<name>/`, following the shape of `file-ingest`. See `ARCHITECTURE.md` for what an archetype must define.
