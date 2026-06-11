---
name: project-onboarding
description: >-
  Stand up a self-maintaining knowledge folder end to end: create its wiki (via wiki-onboarding) and
  set up the two standard maintenance jobs that keep it current — a reactive `ingest` pass that drains
  the inbox and a periodic `reconcile` pass that reckons the whole wiki against the files. Use when
  onboarding a new folder/project into an AI-OS-style setup, or adding scheduled ingest + reconcile to
  a folder that only has a wiki. This is the whole-project flow; for just the wiki skeleton use
  wiki-onboarding, and for the ongoing loop use wiki-maintenance.
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

## When to use

- A folder is being adopted into an AI-OS-style setup and needs both a wiki and its maintenance jobs.
- A folder already has a wiki but no scheduled ingest/reconcile, and you want to add the standard pair.

For just the wiki skeleton, use **wiki-onboarding**. For running an existing wired project, use
**wiki-maintenance**.

## The shape of an onboarded project

When onboarding is done, the folder has:

- the owner's own material, **read in place, never reorganised**;
- a **wiki** with a Schema (its constitution), Index, Log, and domain pages;
- an **inbox / drop folder** where new items land;
- two jobs declared in the project's config:
  - **`ingest`** — `mode: ingest`, reactive (runs after an inbox or calendar change), drains the inbox;
  - **`reconcile`** — `mode: reconcile`, periodic (e.g. weekly), reckons the whole wiki to the files;
- the **`wiki-maintenance`** skill declared as the project's capability, so both jobs share one home
  for the conventions.

## The method

### 1. Scope the folder (read-only)

List the folder's top-level structure and natural domains — exactly the read-only scan
**wiki-onboarding** opens with. Never move or reorganise anything. Confirm this folder *should* be a
file-ingest project at all: the archetype fits a folder of accumulating documents that benefits from a
synthesised, queryable wiki. A folder that is pure code, or has no documents to summarise, doesn't
need it — don't impose the archetype where the material doesn't justify it.

### 2. Create the wiki — hand to wiki-onboarding

Run **wiki-onboarding**: scan, propose a structure that mirrors the owner's own folders, interview on
a few key points (what they'll ask the wiki, what's sensitive, per-domain update triggers, cadence),
and write the **Schema / Index / Log** skeleton. The Schema it produces is the durable artefact every
later pass follows. Do not proceed to wire jobs until there is a Schema to maintain.

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

### 4. Register and declare

- Register the project in your deployment's index so the orchestrator iterates it.
- Declare `wiki-maintenance` as the project's skill capability — this is what makes both jobs share
  the one home for conventions.
- If the project has a calendar feed, wire its snapshot producer so the gate can detect calendar
  changes (a producer with the grant writes a snapshot; the job reads it deterministically).

### 5. Verify the wiring before trusting it

- **Reactive ingest fires and is cheap when idle.** Drop a test item in the inbox; confirm the next
  gate tick ingests it and files it. With nothing changed, confirm a tick no-ops with no model call.
- **Reconcile runs on its cadence** and reckons the wiki to the files without touching
  `provenance: manual` content.
- **Fail-loud holds.** A blocked/unreadable source is surfaced for review with its reason, never
  dropped; a stale calendar snapshot does not blank the upcoming view.

### 6. Hand off

From here the project runs itself: **wiki-maintenance** is the loop both jobs follow. Onboarding is
one-time; maintenance is ongoing.

## Principles

- **Wiki first, then jobs.** There is nothing to maintain until a Schema exists — `wiki-onboarding`
  is a hard prerequisite of wiring the jobs.
- **Stamp, don't reinvent.** The archetype is the single home for the standard job pair; copy it and
  specialise only where a project genuinely differs, so every project stays recognisable.
- **The gate makes reactive safe.** Run the cheap deterministic check often; spend a model call only
  when folder state moved. Never reach for a fragile watcher when an idle no-op poll is reliable.
- **Guidelines here, guarantees in code.** This skill says what an onboarded project looks like; the
  deployment's deterministic guards (write-guard, in-folder path check) are what enforce it at run
  time — keep those in code, not prose.
- **Read in place, never reorganise.** The owner's files stay where they are; onboarding adds a wiki
  and jobs beside them, nothing more.
