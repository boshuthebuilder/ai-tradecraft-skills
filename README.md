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
