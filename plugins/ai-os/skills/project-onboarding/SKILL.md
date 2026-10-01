---
name: project-onboarding
description: >-
  Stand up a self-maintaining knowledge folder end to end, in one flow whether the folder arrives cold
  or prepared by pre-onboarding: tell which by pre-onboarding's hand-off contract, validate a prepared
  folder and never rebuild it, or create the wiki a cold folder lacks (via wiki-onboarding); then set up
  the two standard maintenance jobs that keep it current (a reactive `ingest` pass that drains the inbox
  and a periodic `reconcile` pass that reckons the whole wiki against the files), seeded from the state
  the folder arrives in. Use when onboarding a new folder/project into an AI-OS-style setup, when
  pre-onboarding hands over a prepared folder, or when adding scheduled ingest + reconcile to a folder
  that only has a wiki. Also home to the job archetypes: file-ingest (the pair above), user-synthesis
  (use this when onboarding a person/identity who wants a synthesised cross-project view, a user-tier
  wiki or second brain, over the project wikis they can access), code (a git-backed project the system
  reads read-only and reports on: a periodic `digest` + a `code-review`, no `ingest`) and
  folder-curation (a deterministic periodic audit plus a propose-only curate over a curated folder).
  For a lived-in folder that needs tidying before a wiki can route it, start at pre-onboarding, which
  runs folder-curation. For just the wiki skeleton use wiki-onboarding, and for the ongoing loop use
  wiki-maintenance.
---

# project-onboarding

Onboarding a folder into a self-maintaining setup is two things, not one: **a wiki** (the synthesised
layer) and the **jobs** that keep it current. `wiki-onboarding` produces the wiki skeleton;
`wiki-maintenance` runs the ongoing loop. This skill is the flow that ties them together and stamps
out the standard **file-ingest archetype** — the `ingest` + `reconcile` job pair — so a new folder
arrives fully wired rather than as a bare wiki someone still has to schedule.

It is the **guideline** for that flow. The concrete act of writing config and scheduling a timer is
deployment-specific (an unattended pipeline registers a project and installs a scheduler entry; a
person driving a Cowork session may just run the passes by hand) — so this skill describes *what a
correctly-onboarded project looks like* and the order to build it, and points at the archetype
templates to copy. See [`ARCHITECTURE.md`](../../ARCHITECTURE.md) for the why.

**One flow, cold or prepared.** A folder arrives **cold**, with no preparation (a tidy folder, with or
without a wiki), or **prepared** by [`pre-onboarding`](../pre-onboarding/SKILL.md): curated, every
document read and carded, its wiki built and accepted, and its settings written into machine-readable
twins. The steps below are the same for both. Step 1 tells which by the hand-off contract, never by a
guess, and each later step says what differs. What preparation built is validated here, never rebuilt,
and becomes the jobs' starting point.

## When to use

- A folder is being adopted into an AI-OS-style setup and needs both a wiki and its maintenance jobs.
- `pre-onboarding` hands over a prepared folder (its last step): validate it and wire its jobs.
- A folder already has a wiki but no scheduled ingest/reconcile, and you want to add the standard pair.
- A lived-in folder whose read-only scan shows overlapping homes, duplicate trees or root strays is not
  ready for this skill: start it at **pre-onboarding**, which runs **folder-curation** for the tidy-up
  and hands the folder back here prepared.

For just the wiki skeleton, use **wiki-onboarding**. For running an existing wired project, use
**wiki-maintenance**.

This skill's flow below is for the **file-ingest** archetype (a folder of documents). For giving a
*person* a cross-project view over the project wikis they can access, use the **`user-onboarding`**
skill, which stamps the **user-synthesis** archetype (`archetypes/user-synthesis/`) — an incremental
`synthesise` plus its periodic `reconcile` twin, over a type-1 user vault (no wiki-onboarding pass).

## The shape of an onboarded project

When onboarding is done, the folder has:

- the owner's own material, **read in place, never reorganised**;
- a **wiki** with a Schema (its constitution), Index, Log, and section pages: one section per area of
  responsibility, each page with its professional and each page type with its contract
  ([the core wiki rule](../wiki-maintenance/SKILL.md#the-core-wiki-rule));
- an **inbox / drop folder** where new items land;
- optionally an **audit pair** (`_Audit/manifest.json` + `AUDIT.md`) and a **rulebook** at the root
  recording the curation depth, class policy, naming rules and exclusions, when the folder went
  through folder-curation (in preparation, or on its own);
- on a prepared folder, also the **settings twins** in the settings folder (`.familyai/` by default;
  [the settings reference](../pre-onboarding/references/settings.md)) and, in `_Audit/`, an extract
  record and a card per document and the wiki's rationale and acceptance record;
- two jobs declared in the project's config:
  - **`ingest`** — `mode: ingest`, reactive (runs after an inbox or calendar change), drains the inbox;
  - **`reconcile`** — `mode: reconcile`, periodic (e.g. weekly), reckons the whole wiki to the files;
  - and, on a curated folder, the folder-curation archetype's periodic **`audit`**;
- the **`wiki-maintenance`** skill declared as the project's capability, so both jobs share one home
  for the conventions.

## The method

### 1. Scope the folder and tell its starting state (read-only)

List the folder's top-level structure: exactly the read-only scan **wiki-onboarding** opens with
([its step 1](../wiki-onboarding/SKILL.md#1-scan-the-folder-read-only)). Never move or reorganise
anything. Confirm this folder *should* be a file-ingest project at all: the archetype fits a folder
of accumulating documents that benefits from a synthesised, queryable wiki. A folder that is pure
code, or has no documents to summarise, doesn't
need it — don't impose the archetype where the material doesn't justify it.

**Tell the starting state** from what is on disk, never from a description of the folder:

- **Prepared.** A folder carrying `rulebook.json` in the settings folder (`.familyai/` by default)
  claims to be prepared, and it is prepared when it meets
  [`pre-onboarding`'s hand-off contract](../pre-onboarding/SKILL.md#the-hand-off-contract). Check it
  with that skill's `readiness.py` ([the tool reference](../pre-onboarding/references/tools.md#readinesspy)),
  which is read-only on the folder, or with the deployment's own check of the same contract.
  `readiness.py` exits 1 on any finding, each listed in its report's `findings`, and lists each named
  not-verified state (an engine whose canary was not run, say) in `not_verified` without changing the
  exit code, so read the report, not only the exit code. A deployment's own check treats the same
  items as findings, and decides for itself whether to accept a not-verified state or to require it
  verified. A finding sends the folder back to `pre-onboarding`, to the step that owns it; it is never
  repaired here. A not-verified state the deployment accepts goes on only when the owner accepts it
  too, and that acceptance is recorded with the onboarding.
- **Cold and tidy.** No twins, and the scan finds none of the conditions below: go on. A folder with
  an audit pair and a rulebook but no twins (curated by `folder-curation` on its own) is cold; the scan
  decides whether it is tidy.
- **Cold and messy.** The scan finds any of: one subject with more than one home, a duplicate tree,
  strays at the root, AI artefacts beside sources, or a format the system cannot read. Stop, and start
  the folder at **pre-onboarding**, which runs **folder-curation** for the tidy-up and hands the folder
  back prepared. Its hand-off check, not this skill, decides when the folder is ready; onboarding a
  folder that still has two homes for one subject writes that ambiguity into the Schema's routing
  table, where it stays.

### 2. Ensure a wiki exists: validate it, or onboard one only if there is none

The jobs need a Schema to maintain, so this step guarantees one exists, **without rebuilding a wiki
that is already there** (adding jobs to a folder that already has a wiki is one of this skill's uses,
and a prepared folder's wiki was drafted from every document and accepted):

- **A prepared folder** → **validate, never rebuild.** Its Schema, pages, rationale and acceptance
  record, and both settings twins, fresh, stand as the hand-off check found them in step 1: do not run
  wiki-onboarding again, redraft or re-accept a page, or extract or card a document again. Read the
  Schema. A twin found stale later is a repair for `pre-onboarding`
  ([stale twins](../pre-onboarding/references/settings.md#stale-twins)), never a reason to re-onboard.
- **A cold folder with no wiki / Schema** → run **wiki-onboarding**
  ([its steps 2 to 4](../wiki-onboarding/SKILL.md#2-propose-a-structure-the-librarians-sections-and-each-pages-professional)),
  under [the core wiki rule](../wiki-maintenance/SKILL.md#the-core-wiki-rule), to write the
  **Schema / Index / Log** skeleton.
- **A cold folder with a wiki / Schema** → **do not re-onboard.** Read and validate the existing
  Schema, then go straight to stamping the jobs (step 3).

Either way, do not proceed to wire jobs until there is a Schema to maintain — it is the durable
artefact every later pass follows.

### 3. Stamp the file-ingest archetype — the two jobs

Copy the archetype from `archetypes/file-ingest/` and fill in the project's specifics:

- **The jobs block** (`jobs.yaml`) — declare `ingest` and `reconcile` with their modes, prompt
  templates, and whatever model/timeout fields your deployment's config uses.
- **The prompt templates** (`ingest.md`, `reconcile.md`) — start from the archetype's generic
  versions; specialise **only** where the generic shape falls short for this project (the default is
  to use them unchanged and let the project's Schema + the `wiki-maintenance` skill carry the
  specifics). Each template already references `wiki-maintenance` rather than restating it.
- **The scheduler** (`scheduler.md`) — wire `ingest` to run **reactively** (a short poll, or an
  event wake, that runs the deterministic gate and no-ops when nothing changed) and `reconcile` to
  run on a **periodic** cadence. The concrete timer is your deployment's (a launch agent, a cron
  entry, a person). Confirm the reactive ingest runs in a context that can actually write the wiki
  (see the execution-context note in `ARCHITECTURE.md`).

**On a prepared folder, write the config from the settings twins.** `rulebook.json` and
`wiki-schema.json` in the settings folder (`.familyai/` by default) are the folder's settings in the
form code reads
([the settings reference](../pre-onboarding/references/settings.md)): take the inbox, the wiki folder
(the templates' `{wiki_dir}`), the migrations folder, the exclusions and the identifier policy from the
rulebook's twin, and the layout, routing, page contracts and page professionals from the Schema's,
rather than reading them again from prose. The rulebook and the Schema page stay the authorities, and
a twin is read only while it is fresh (step 2).

On a curated folder (a prepared one included) also stamp the folder-curation archetype's `audit`
(deterministic, periodic) so drift stays visible; see `archetypes/folder-curation/`.

For a project adopting deterministic rendering
([the optional profile](../wiki-maintenance/SKILL.md#deterministic-rendering-optional-profile)), version
its compiled render declarations and renderer configuration beside its stamped templates. The
project's renderer is maintained code, not a script left in one session. Templates carry the optional
`{page_contracts}` context described by the file-ingest archetype; deployments without the profile
supply an empty block and retain `body` output. Either way every page follows
[the core wiki rule](../wiki-maintenance/SKILL.md#the-core-wiki-rule).

### 4. Seed the starting point

A job's first run starts where the folder is, not from nothing.

- **A prepared folder.** Preparation read every document and built the wiki from them, so seed the
  jobs with that state before the first tick, however the deployment records each: the ingest gate
  holds every live entry of the manifest the hand-off check passed as already ingested, at its
  manifest id (a file's SHA-256; a package's by the manifest's package hash rule,
  [`manifest-schema.md`](../file-preprocessing/references/manifest-schema.md#added-in-2)); the
  human-edit guard holds each wiki page as preparation wrote it, so a later owner edit is detected
  and proposed around rather than overwritten; and the prepared `_Audit/manifest.json` is the `audit`
  job's previous pass. A file added or edited since the check has an id the seed does not hold, so
  the first tick takes it as new. Unseeded, the first ingest takes every document as new and rewrites
  an accepted wiki from its sources.
- **A cold folder with a wiki already filled** (kept by hand, say, or prepared but with its settings
  folder lost). Seed the human-edit guard with every page as found, and the ingest gate with every
  source as it stands, so that ingest takes only what arrives after onboarding; then let the first
  `reconcile`, not `ingest`, reckon the wiki against the files. Unseeded, the first ingest takes every
  document as new and rewrites the wiki.
- **A cold folder with a new skeleton.** Nothing to seed beyond it: the first passes fill the wiki
  from the sources, as the Schema routes them.

### 5. Register and declare

- Register the project in your deployment's index so the orchestrator iterates it.
- Declare `wiki-maintenance` as the project's skill capability — this is what makes both jobs share
  the one home for conventions.
- If the project has a calendar feed, wire its snapshot producer so the gate can detect calendar
  changes (a producer with the grant writes a snapshot; the job reads it deterministically).

### 6. Verify the wiring before trusting it

- **Reactive ingest fires and is cheap when idle.** Drop a test item in the inbox; confirm the next
  gate tick ingests it and files it. With nothing changed, confirm a tick no-ops with no model call.
- **A seeded folder starts quiet.** With nothing dropped since onboarding, the first tick
  re-ingests nothing and rewrites no page, and on a prepared folder the first `audit` reports no
  drift. A tick that takes the whole folder as new means the seed (step 4) did not take.
- **Reconcile runs on its cadence** and reckons the wiki to the files without touching
  `provenance: manual` content.
- **Fail-loud holds.** A blocked/unreadable source is surfaced for review with its reason, never
  dropped; a stale calendar snapshot does not blank the upcoming view.

For a project adopting deterministic rendering, the wiring check also verifies a synthetic item through ingest and reconcile:
the touched page is rendered under its declared contract, its evidence is retained, and the next job
uses the same configuration. Test unknown types and malformed contracts fail visibly. A synthetic
fixture can verify the runtime without migrating a live wiki.

### 7. Hand off

From here the project runs itself: **wiki-maintenance** is the loop both jobs follow. Onboarding is
one-time; maintenance is ongoing.

## Principles

- **Wiki first, then jobs.** There is nothing to maintain until a Schema exists: a cold folder gets
  one from `wiki-onboarding` before any job is wired, and a prepared folder arrives with one.
- **One flow; validate, never rebuild.** Cold and prepared folders take the same steps. What
  preparation built (the curated folder, the extract records and cards, the accepted wiki, the twins)
  is checked against the hand-off contract and kept; a finding goes back to `pre-onboarding`, and the
  jobs start from the prepared state.
- **Stamp, don't reinvent.** The archetype is the single home for the standard job pair; copy it and
  specialise only where a project genuinely differs, so every project stays recognisable.
- **The gate makes reactive safe.** Run the cheap deterministic check often; spend a model call only
  when folder state moved. Never reach for a fragile watcher when an idle no-op poll is reliable.
- **Guidelines here, guarantees in code.** This skill says what an onboarded project looks like; the
  deployment's deterministic guards (write-guard, in-folder path check) are what enforce it at run
  time — keep those in code, not prose.
- **Read in place, never reorganise.** The owner's files stay where they are; onboarding adds a wiki
  and jobs beside them, nothing more. Reorganisation is a separate, owner-approved act that precedes
  onboarding (folder-curation, run by pre-onboarding) or comes later as an approved curation round,
  never something a maintenance job does.
