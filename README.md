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
  draft for the signs of AI authorship and rewrites so it reads as human;
  `portable-markdown`, for generating .md a person will open in a desktop editor; and two for
  understanding what an agent produced, `controlled-writing` and `bespoke-explainers`.

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

The marketplace also lists `reading-vocab`, a plugin hosted in its own repository (see
[*Upstream plugins*](#upstream-plugins)). That repository is private, so installing it needs read
access and git credentials Claude Code can use without a prompt: an SSH key, or `gh auth setup-git`.

```
/plugin install reading-vocab@ai-tradecraft-skills
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

### ChatGPT (the chat app)

ChatGPT takes a skill as an uploaded folder or zip, not from this marketplace. Build the zips:

```
python scripts/package_skills.py
```

That writes `dist/<skill>.zip` for every skill, from the last commit (so it needs a git checkout, and it
replaces `dist/` whole). Each zip holds one top-level folder, named for the skill,
with its `SKILL.md` at the top: the layout OpenAI's skills upload states, with its limits checked (at most
500 files, no file over 25 MB, the zip at most 50 MB). Each release also carries the zips as release assets.
Upload the one you want in the app: **Customize**, then **Skills**, then **Add**, then **Upload from your
computer**. The dialog takes a `.zip`, a `.skill` file or a `SKILL.md`.

Three things to know. **A zip holds one skill.** A link from it to a sibling skill has no target after an
upload; the script lists those links, so upload the sibling too when you need it. **The limits the script
checks are the API's.** The app's dialog states a larger one (780 MiB per file), so a zip that passes the
script passes both. **The upload was tested once**, on 2026-11-25 and 2026-11-26 in the web app, with `ai-writing-audit.zip`
from the v15.13.0 release ([#186](https://github.com/boshuthebuilder/ai-tradecraft-skills/issues/186)). What that
test showed:

1. The zip was accepted as it is, and the skill page listed every bundled file.
2. **The app reviews a skill after the upload.** This one was flagged ("may bypass approval, logging,
   verification, or other safety controls") and switched off until its owner pressed **Approve skill** on the
   skill's page. Another skill may pass; the decision is the account owner's.
3. **A skill's files reach the agent in Work mode**, which "Try in chat" on the skill page opens. A chat in
   Chat mode could not find the skill.
4. In Work mode `tools/audit.py` ran, and the agent could quote the `compatibility` text. The skill page shows
   the name and the description, not that text.

### What a sandboxed agent can run

Cowork and ChatGPT run a skill in a container, not on your own computer. A skill that needs more than
reading says so in its `compatibility` frontmatter, and has a **Without the tools** section that says what
to do when a need is missing.

| | Cowork | ChatGPT (chat app) |
|---|---|---|
| Install | this marketplace, as above (not tested from this repository) | upload a zip from `dist/` (tested 2026-11-25: accepted, then held by the app's review until approved) |
| Where a skill runs | an isolated Linux sandbox | a hosted container |
| Host CLIs (`agy`, `codex`, `claude`, `gh`), macOS helpers | none | none |
| Outbound network | only hosts on an allow-list; SSH to GitHub did not connect | off by default in the hosted container, per the API documentation |
| `python3` | not tested | Python 3.12.14 in Work mode (2026-11-26); 3.13.5 in Chat mode (2026-11-25) |
| Standard-library Python tools | expected to run; not tested | `ai-writing-audit`'s `tools/audit.py` ran in Work mode (2026-11-26); in Chat mode the skill's files were not reachable |
| Shows the `compatibility` text | not tested | not on the skill page; the agent can read it (2026-11-26) |

So in either, the prose-only skills should work as they are, and `ai-writing-audit`'s scan should run. The
skills whose work is done on the operator's own machine (`pre-onboarding`, `folder-curation`,
`adversarial-review`, `private-repo-access`) do not run there. `project-onboarding` and `user-onboarding` run in
part: each has one step that needs that machine (the check of a prepared folder; the editor setup). Each of
these says so and names what is missing.

**Only the cells that carry a date have been checked by a real install from this repository.** The other
cells come from the vendors' documentation and from what this repository has observed in other work. They wait
for a real install ([#186](https://github.com/boshuthebuilder/ai-tradecraft-skills/issues/186)): all of Cowork, and in
ChatGPT the network row.

**claude.ai** is best effort and untested: a skill there gets its `compatibility` text and no other support.

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
layer over a folder of real files. Six skills cover the lifecycle. There are three entry points, by
what is being onboarded: a lived-in folder to make ready (`pre-onboarding`), a folder that is already
tidy or has been prepared (`project-onboarding`), and a person who wants a cross-project view
(`user-onboarding`). The other three are the components they call and the loop that follows:

- **`pre-onboarding`** (entry point): prepare a **lived-in** folder for the system, in an
  interactive session. It audits the folder and tidies it only through plans the owner approves (by
  running `folder-curation`), extracts the full text of every document and writes a summary card for
  each, assesses whether its structure needs re-organising and re-organises only the folders the owner approves,
  builds its wiki (by running `wiki-onboarding` under the core wiki rule), checks the result
  against the **hand-off contract**, and hands it to `project-onboarding`. Ships the tools that do
  the exact parts (`plugins/ai-os/skills/pre-onboarding/tools/`: standard-library Python, with a
  small Swift helper for Apple Vision and local tools (poppler, tesseract, LibreOffice) where
  present; generic and settings-driven), and keeps the folder's settings in machine-readable twins of
  its rulebook and Schema.
- **`project-onboarding`** (entry point): stand up a self-maintaining folder end to end, in **one
  flow for cold and prepared folders**. It tells which by the hand-off contract, validates a prepared
  folder (never rebuilding it) or creates the wiki a tidy cold folder lacks (via `wiki-onboarding`),
  then wires the two standard maintenance jobs (a reactive `ingest` pass and a periodic `reconcile`
  pass) from the **file-ingest archetype**, seeded from the state the folder arrives in. A messy
  cold folder is sent to `pre-onboarding` first. Also home to the job archetypes (file-ingest,
  user-synthesis, code, folder-curation).
- **`user-onboarding`** (entry point): onboard a *person* (an identity) rather than a folder, with the
  storage-ownership handshake (the user owns the folder and shares it into the worker), the
  **type-1 user vault** ("second brain") skeleton, and stamping the **user-synthesis archetype**
  (an incremental `synthesise` + its periodic `reconcile` twin) so the person gets a
  self-maintaining, cross-project view over the wikis they can access. The synthesis is also where
  cross-project migrations are suggested, for the owner to make by hand.
- **`wiki-onboarding`**: bootstrap a wiki for a folder that doesn't have one. Scan the folder
  read-only; a librarian proposes **sections by responsibility**, the routing and the one
  professional best suited to each page; interview the owner on a few key points; agree a page
  contract for every page type; write the **Schema / Index / Log** skeleton (and, in a prepared
  folder, draft every page from the evidence); and accept each page through a model that did not
  write it. One-time and interactive; the wiki stage of `pre-onboarding`; hands off to
  `wiki-maintenance`.
- **`wiki-maintenance`**: keep a wiki current. Process an incoming item end to end (read → file
  by confident match → update the pages it touches → surface what needs a human → log), answer
  queries from the wiki, and run periodic reconcile (lint) passes. The method is portable; each
  wiki's own Schema page is the authority for its exact pages and layout. Home of the **core wiki
  rule** (sections by responsibility, one professional per page, a contract per page type, a
  rationale and an acceptance per page, rich pages drawn from cited data) and of the professional
  catalogue. Includes the provenance
  model, the never-overwrite-a-human-edit guard, full private content and source-supported identifiers
  by default, with explicit owner restrictions.
- **`folder-curation`**: the method for a **lived-in** folder, the one between a drop folder and a
  tidy one, and a component of `pre-onboarding`, which runs it. The audit half is deterministic and
  repeatable: a hash-keyed manifest over the whole library with type classes (an iWork package is
  one item, read directly), duplicate groups that know a submission pack from a redundant copy,
  overlapping homes, files staged for another project, and drift since the last pass. The curate
  half is **propose-only**: an interview on a fixed ladder, then a move-plan the owner
  approves row by row, executed under the shared move guards and proved by a re-audit. Approved
  plans are also how files are staged for another project while a folder is being prepared. The
  curated folder goes back to
  `pre-onboarding` for its extraction, cards and wiki, and the audit keeps running afterwards as the
  project's periodic `audit` job.

A drop folder of files that belong to no project yet is `file-preprocessing`'s: it understands,
renames and files each file into a run parcel, and shares the manifest format the audit uses.

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
behalf, rather than the code or the folder, and the formats that help you understand what it produced.

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

- **`controlled-writing`** — explain in a controlled language so a person can read an agent's
  output fast and check it: one idea per sentence, active voice, one name for each thing. It
  restates the ASD-STE100 (Simplified Technical English) rule families in its own words, with a
  setting dial ("80% of the way" is the default), a claims ledger so simpler words never drop a
  caveat, and the boundary with `ai-writing-audit`, whose rhythm check controlled text fails by
  design.

- **`bespoke-explainers`** — choose the format that gets a person to understanding fastest (prose,
  a diagram, an interactive HTML page or a narrated video) and build it as a throwaway artefact
  for one reader, with its claims checked before anything is rendered. It picks the diagram tool
  by where the diagram will be seen and how big it is, and carries a video recipe (Manim Community
  Edition with a free local voice, timed beat by beat) that was rendered end to end and then
  reproduced by a second agent from the page alone.

- **`private-repo-access`** — get a person with no GitHub account read access to one private
  repository, such as an upstream plugin's, through a read-only deploy key. Run once in Claude Code
  (the Code tab of the Claude desktop app, not Cowork, whose sandbox has no SSH), it makes the key,
  writes the message the person sends to the repository's owner, then tests the key, clones the
  repository and hands over to that repository's own setup guide. Written for a person with no
  coding background: Claude runs and explains every command.

## Upstream plugins

The marketplace may list a plugin that lives in another repository. Its entry in
[`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) is a `github` source pinned to an
upstream release tag and that tag's commit, so nothing upstream reaches a consumer until the pin moves
here. Such a plugin is not a direction: its skills are not copied into this repository, and its own
repository holds their text, licence and versioning.

- **`reading-vocab`** ([chenspc/reading-vocab](https://github.com/chenspc/reading-vocab), private, MIT)
  — two skills for a reader who keeps an Anki deck. `reading-vocab` turns the words jotted while reading
  (Apple Notes, Bear, Obsidian or a text file) plus the book file into dictionary-grounded cards: each
  carries the book's own sentence, one to four authored senses with a short Simplified Chinese gloss each,
  and the macOS dictionary entry. `compare-words` keeps a second deck of near-synonym groups, with a map
  card and a fit card per word. The skills are the procedure; the code they drive (an MCP server, the
  sentence finder, the card composer) runs from the user's own clone of that repository, which its
  `docs/SETUP.md` installs.

**No GitHub account?** Install the `productivity` plugin, which needs no login, then in the Code tab
of the Claude desktop app ask Claude for access to the upstream plugin. Its `private-repo-access`
skill makes a key, writes the request to the repository's owner, and clones the repository once the
owner adds the key.

To take a newer upstream release, change the entry's `ref` and `sha` to the new tag and its commit, in a
PR here. That is a MINOR release of this repository.

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
- **An upstream plugin** — a marketplace entry whose `github` source pins another repository's
  release tag and commit (see [*Upstream plugins*](#upstream-plugins)). Adding one, or moving its pin,
  is a MINOR release.
- **An archetype** — a new job family (its prompt templates, job declarations, and write
  contract) lives under `plugins/ai-os/skills/project-onboarding/archetypes/<name>/`, following
  the shape of `file-ingest`. See
  [`plugins/ai-os/ARCHITECTURE.md`](plugins/ai-os/ARCHITECTURE.md) for what an archetype must
  define.

### Try an unreleased skill

A change to a skill reaches each agent a different way. Before a release, load the working tree directly:

- **Claude Code**: `claude --plugin-dir ./plugins/<direction>` loads that plugin from the folder for one
  session (checked on Claude Code 2.1.294). The installed plugin is not touched.
- **Codex CLI**: add the working tree as a local marketplace, `codex plugin marketplace add <path to this
  checkout>`, then `codex plugin add <direction>@<the name that command reports>` (not tested from this
  repository).
- **ChatGPT (the chat app)**: commit the change, run `python scripts/package_skills.py`, then upload
  `dist/<skill>.zip`. The zips hold the last commit, not uncommitted edits.
- **Cowork**: it installs this marketplace from GitHub. Whether it can be pointed at an unreleased branch has
  not been tested from this repository ([#186](https://github.com/boshuthebuilder/ai-tradecraft-skills/issues/186)).
  Until it has, try a skill in Cowork only after it is merged.
- **A deployment that pins a release** reads skills from a clone at a tag. To try an unreleased skill against
  it, point its skills-path override at this checkout's `plugins/ai-os/skills` (the reference deployment's is
  `FAMILY_AI_SKILLS_DIR`). Check which branch that checkout is on first: a stale one answers without saying so.

### Local checks

CI runs `scripts/lint_skills.py` on every push and PR. To catch the same failures *before* a push
leaves your machine — most usefully a manifest/`CHANGELOG.md` version mismatch, before a release
tag goes out — enable the bundled pre-push hook once per clone:

```
git config core.hooksPath .githooks
```
