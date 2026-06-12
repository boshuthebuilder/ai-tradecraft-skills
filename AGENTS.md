# AGENTS.md — ai-os-skills

This repo is the **method**: skills and job archetypes for building a headless AI assisting
system over a person's real folders. Deployments consume it as a **pinned dependency** — they
resolve skills from a clone checked out at a release tag and advance that pin deliberately. The
design is [`ARCHITECTURE.md`](ARCHITECTURE.md); the reference deployment is
[`family-ai-os`](https://github.com/boshuthebuilder/family-ai-os). `CLAUDE.md` is a symlink to
this file — one source of truth, two filenames.

## Binding rules for working here

- **Generic, always.** No real owner, host, machine, or platform names in skills, archetypes,
  or prompt templates — the consumed method must read as method ("the owner", "the deployment",
  "an always-on machine"), never as one household's configuration. If an example needs a name,
  invent an obviously fictional one. The one deliberate exception: top-level docs (this file,
  `README.md`, `ARCHITECTURE.md`) may link the reference deployment by name, as they already do.
- **Skills are conventions, not code.** Enforcement (write guards, path checks, locks) belongs
  in a deployment's code; a skill *describes* intent. Don't write a rule into a skill that only
  code can hold — point to the three-layer model in `ARCHITECTURE.md` instead.
- **One home per convention.** `wiki-maintenance` owns how a wiki is kept; archetypes own job
  shapes; `ARCHITECTURE.md` owns the system design. Don't restate a convention in a second
  place — reference it.
- UK English in prose. Prefer editing existing files to adding new ones.

## Versioning — the consumer contract

Releases are **semver tags** `vMAJOR.MINOR.PATCH`, recorded in [`CHANGELOG.md`](CHANGELOG.md).
The versioned *interface* is everything a consumer may depend on:

- **skill names and their frontmatter contracts** (`wiki-onboarding`, `wiki-maintenance`,
  `project-onboarding`) and the `skills/<name>/SKILL.md` layout;
- **archetype directory layout** under `skills/project-onboarding/archetypes/<archetype>/`
  (the file set: `README.md`, `jobs.yaml`, prompt templates, `scheduler.md`) and the
  `id == mode` rule;
- **prompt-template placeholders** (currently `{date}`, `{gather_report}`, `{project_name}`,
  `{project_rulebook}`, `{wiki_dir}`, `{wiki_structure}`) — a deployment substitutes these at
  run time;
- **the documented method** in `ARCHITECTURE.md` (the gate, the determinism boundary, the
  three layers, fail-loud).

**MAJOR** — any breaking change to the above: a rename, a removal, a placeholder a template now
requires, a semantic change to a documented rule. **MINOR** — additive: a new skill, a new
archetype, a new *optional* placeholder, a new section. **PATCH** — wording and fixes with no
contract change.

## Release protocol

1. Land the change on `main` via PR.
2. Move the `CHANGELOG.md` *Unreleased* entries under a new `vX.Y.Z` heading (date it), in the
   same PR or a follow-up commit.
3. Tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.

Consumers pin a **tag**, never track `main`. A deployment advances its pin deliberately (in its
own config, with its own review), so `main` here may move freely between releases — breaking
changes cost a MAJOR bump, not a coordinated migration.
