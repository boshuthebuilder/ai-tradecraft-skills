# ai-tradecraft-skills

A method library of [Agent Skills](https://code.claude.com/docs/en/skills) for AI-agent-driven
work, organised by **direction** — each direction a real Claude Code plugin, installable on its
own:

- **`coding`** — development-process discipline for coding agents: plan, build, and gate a change
  across a mixed-capability pool of humans and models. Applies to any repo, whoever wrote it.
- **`ai-os`** — the framework and skills for a **headless AI assisting system**: one that runs
  unattended over a person's real folders, notices what changed, reasons over it, and keeps a
  synthesised layer current without being asked.
- **`productivity`** — skills for individual AI-assisted work: `ai-writing-audit`, which checks a
  draft for the signs of AI authorship and rewrites so it reads as human, and
  `portable-markdown`, for generating .md a person will open in a desktop editor.

The conventions live in **one home**, so interactive Claude Code / Cowork sessions and automated
pipelines share the same logic.

## Install

The skills are self-contained method prose in the open [`SKILL.md`](https://code.claude.com/docs/en/skills)
format, so they work in any agent that reads it — install only the direction you need.

### Claude Code / Cowork

```
/plugin marketplace add boshuthebuilder/ai-tradecraft-skills
/plugin install coding@ai-tradecraft-skills
/plugin install ai-os@ai-tradecraft-skills
/plugin install productivity@ai-tradecraft-skills
```

### ChatGPT (Codex CLI)

Codex CLI reads the Claude Code marketplace format, so the same repo installs as a Codex plugin —
no cloning or symlinking:

```
codex plugin marketplace add boshuthebuilder/ai-tradecraft-skills
codex plugin add coding@ai-tradecraft-skills
codex plugin add ai-os@ai-tradecraft-skills
codex plugin add productivity@ai-tradecraft-skills
```

Start a new Codex session; each plugin's bundled skills load on demand — invoke one with `$<name>`
(e.g. `$adversarial-review`), or let Codex select automatically. Needs a Codex CLI with plugin
support (`codex plugin --help`); verified against `codex-cli 0.144.1`.

Any other agent that reads the open [`SKILL.md`](https://learn.chatgpt.com/docs/build-skills) format
from a skills directory can instead symlink the skill folders it wants —
`plugins/coding/skills/*`, `plugins/ai-os/skills/*`, and `plugins/productivity/skills/*` — into
that agent's skills path.

## The `coding` direction

Six skills for the development process itself, in any repo executed by coding agents. One theme
runs through them: move judgment upstream into artifacts, so cheaper agents become safe to use.
They span the lifecycle — **plan** (tier the work), **build** (lock the design, discipline the
change, iterate to acceptance), **gate** (review the change), **verify** (prove the control ran):

- **`agent-tiered-planning`** — label every issue with an `agent:standard|senior|frontier`
  capability tier orthogonal to its effort estimate; publish a playbook cold agents read before
  picking up work (pickup protocol, tier definitions); enforce the escalation rule — if an issue
  exceeds your tier: stop, comment, relabel up, leave it (a wrong-but-merged implementation costs
  more than a delayed one). Tiers double as spend routing: the bulk of a backlog runs on cheaper
  models, preserving frontier headroom. Includes CONTRIBUTING and label-scheme templates.
- **`design-direction-lock`** — after mockup iteration converges, freeze the direction into a
  one-page normative artifact (references with anti-goals, visual language, motion rules incl.
  invariants, product truths, one canonical reference design), then stamp every design-facing
  issue with the lock revision and only the rules that apply to that surface — so implementing
  agents match the target instead of re-designing it. Versioned: direction changes are a new
  revision plus re-stamp, never silent drift. Includes one-pager and stamp templates.
- **`implementation-discipline`** — the conduct any coding agent holds while writing a change:
  assumptions surfaced before code (competing interpretations presented, then routed to the
  escalation rule or deviation protocol rather than resolved silently), the minimum that solves
  the stated problem (no speculative structure — assert loudly rather than handle the impossible),
  every changed line tracing to the task (unrequested improvements become issues, never diff
  hunks), and the task restated as verifiable success criteria with a step-then-verify plan. The
  authoring-side counterpart of the review gate's scope-and-shape lens; binds every tier, and
  matters most where supervision is thinnest.
- **`iterative-acceptance`** — how to build on a nondeterministic tool (an LLM, OCR, a vision
  model) when the expectations cannot be specified up front and only surface on contact with real
  output. Iterate real runs against a **frozen baseline** whose byte-identity is checked around
  every experiment, with predictions **registered before** each run and scored honestly after it;
  park all state so context comes only from the operator's prompt (the blank-slate protocol); turn
  every miss into a systematic capability rather than a hack for the test data; and keep batch
  knowledge in the prompt channel while fixes live in code. For any pipeline whose core step is a
  model call — document processing, extraction, classification, synthesis.
- **`silent-failure-design`** — design and audit controls so that one which never ran is
  distinguishable from one that ran and passed. The failure class where absence wears the appearance
  of success: CI never scheduled, a watchdog whose exception is swallowed, a guard that cannot start
  and so denies nothing, a test whose seam moved and now passes for the wrong reason, a skipped job
  counted as a pass. One question asked of every control — *if this had never run, what would I
  see?* — plus the four properties that make the answer differ from silence: a liveness signal, an
  artifact-based success test, per-item error isolation, and a vocabulary separating verified from
  unverified. Includes an audit checklist for existing systems.
- **`adversarial-review`** — the cross-model review gate for every complex change: a *different*
  model from the one that wrote the code reviews the open PR adversarially and posts its findings
  as PR comments, iterating to convergence. Carries the author-agnostic reviewer chain
  (Antigravity CLI · Claude · Codex — with eligibility determined by the actual reviewer model,
  diversity-first and same-model disclosed as the last resort), each path's prerequisites, the
  auditable PR-comment protocol, a bundled Antigravity CLI harness
  (`plugins/coding/skills/adversarial-review/tools/agy-review` — typed exits,
  verify-by-artifact), and the one-time machine setup headless reviewers need. Repo-agnostic and
  agent-agnostic — the method is markdown any coding agent can follow, and the harness is one
  dependency-free bash script.

## The `ai-os` direction

[`plugins/ai-os/ARCHITECTURE.md`](plugins/ai-os/ARCHITECTURE.md) is the core of this direction.
It defines the **job** as the unit of work (one pass over a maintained folder: read state, reason
once, return a structured result that deterministic guards turn into changes), the three layers
of a job (prompt template · skill · deterministic guards), the determinism boundary, the gate
that runs a cheap deterministic check before any model call, and reactive vs periodic scheduling.
Each job family is an **archetype** with its own write contract — knowledge synthesis is the
first, and **folder hygiene** is now the fourth (a deterministic audit plus a propose-only curate);
drafting, or any other family, flows through the same layers and the same gate. The reference
deployment is
[`family-ai-os`](https://github.com/boshuthebuilder/family-ai-os), which consumes this repo as a
pinned dependency.

The first archetype implements the **in-folder knowledge wiki**: a synthesised, always-current
layer over a folder of real files. Five skills cover the lifecycle:

- **`project-onboarding`** — stand up a self-maintaining folder end to end: create its wiki (via
  `wiki-onboarding`) and wire the two standard maintenance jobs — a reactive `ingest` pass and a
  periodic `reconcile` pass — from the **file-ingest archetype**. The whole-project flow; composes
  the two skills below. Also home to the job archetypes (file-ingest, user-synthesis, code,
  folder-curation).
- **`user-onboarding`** — onboard a *person* (an identity) rather than a folder: the
  storage-ownership handshake (the user owns the folder and shares it into the worker), the
  **type-1 user vault** ("second brain") skeleton, and stamping the **user-synthesis archetype**
  (an incremental `synthesise` + its periodic `reconcile` twin) so the person gets a
  self-maintaining, cross-project view over the wikis they can access.
- **`wiki-onboarding`** — bootstrap a wiki for a folder that doesn't have one: scan the folder
  read-only, propose a structure that mirrors how the owner already organises it, interview them
  on a few key points, then write the initial **Schema / Index / Log** skeleton. One-time and
  interactive; hands off to `wiki-maintenance`.
- **`wiki-maintenance`** — keep a wiki current: process an incoming item end to end (read → file
  by confident match → update the pages it touches → surface what needs a human → log), answer
  queries from the wiki, and run periodic reconcile (lint) passes. The method is portable; each
  wiki's own Schema page is the authority for its exact pages and layout. Includes the provenance
  model, the never-overwrite-a-human-edit guard, full private content and source-supported identifiers
  by default, with explicit owner restrictions.
- **`folder-curation`** — adopt a **lived-in** folder, the one between a drop folder and a tidy
  one. The audit half is deterministic and repeatable: a hash-keyed manifest over the whole library
  with type classes, duplicate groups that know a submission pack from a redundant copy,
  overlapping homes, and drift since the last pass. The curate half is **propose-only** — an
  interview on a fixed depth ladder, then a move-plan the owner approves row by row, executed under
  the shared move guards and proved by a re-audit. Hands off to `project-onboarding` when the verify
  step is clean, and the audit keeps running afterwards as the project's periodic `audit` job.

### Using it in a Cowork session

1. Install the `ai-os` plugin (see above).
2. Point the session at the folder you want maintained (your own, or one shared with you).
3. Ask Claude to drain the inbox / update the wiki — `wiki-maintenance` loads automatically when
   relevant and drives the rest.

### Two writers on one folder is safe

If a folder is also maintained by a scheduled automation (an unattended safety net), your inline
edits are never clobbered: a well-behaved system hashes every file it writes, so when it sees a
page you changed it proposes a `.proposed.md` sibling instead of overwriting. Inline maintenance
is first-class; the scheduled pass is the backstop.

## The `productivity` direction

Skills for individual AI-assisted knowledge work — the prose and craft an agent produces on your
behalf, rather than the code or the folder.

- **`ai-writing-audit`** — audit a draft for the signs of AI authorship and rewrite to remove them.
  It judges by clusters and structure, not a single banned word: leaked citation markup and low
  sentence-length variance are near-decisive, while vocabulary and em-dashes only contribute to a
  score. Carries the pattern catalogue (`REFERENCE.md`, sourced and era-tagged, verified against the
  2026 landscape) and a triage scanner (`tools/audit.py`) that grades hits into evidence bands. Use
  it on any prose you are about to share so it reads as a person wrote it.

- **`portable-markdown`** — write markdown a person will actually open in Typora, Obsidian or a
  plain viewer, so the links land on the right thing and no raw markup shows. The rule that
  prevents most of the damage is that a link's destination follows from what the link is *for* —
  a name that names a document should open that document, not jump to a section about it. Carries
  the encoding rules both editors' help states, the anchor form that renders invisibly (an empty
  `<a></a>` shows its own source in Typora), table cells that survive model-written text, and a
  probe template for settling behaviour neither vendor documents. `REFERENCE.md` holds the
  clicked-in-the-application matrix.

## How updates propagate

- **Cowork / interactive** — you get the latest each session (the marketplace tracks this repo).
- **An unattended automation** — should consume a **pinned** clone at a release tag, advanced only
  through a reviewed deploy, never auto-latest. Releases are semver tags; what counts as a
  breaking change is defined in [`AGENTS.md`](AGENTS.md), and each release is recorded in
  [`CHANGELOG.md`](CHANGELOG.md).

Edit a skill here once → interactive sessions pick it up immediately → a pinned automation picks
it up on its next deploy.

## Contributing

Three extension points:

- **A skill** — drop a folder under `plugins/<direction>/skills/<name>/` with a `SKILL.md` (YAML
  frontmatter with at least a `description`). CI (`scripts/lint_skills.py`) lints every skill on
  push, so a malformed skill never ships. Validate one plugin locally with
  `claude plugin validate ./plugins/<direction>`, or the whole marketplace with
  `claude plugin validate .`.
- **A direction** — a new plugin under `plugins/<direction>/` (own
  `.claude-plugin/plugin.json` + `skills/`), plus a marketplace entry, created together with its
  first skill. A new direction is a MINOR release.
- **An archetype** — a new job family (its prompt templates, job declarations, and write
  contract) lives under `plugins/ai-os/skills/project-onboarding/archetypes/<name>/`, following
  the shape of `file-ingest`. See
  [`plugins/ai-os/ARCHITECTURE.md`](plugins/ai-os/ARCHITECTURE.md) for what an archetype must
  define.

### Local checks

CI runs `scripts/lint_skills.py` on every push and PR. To catch the same failures *before* a push
leaves your machine — most usefully a manifest/`CHANGELOG.md` version mismatch, before a release
tag goes out — enable the bundled pre-push hook once per clone:

```
git config core.hooksPath .githooks
```
