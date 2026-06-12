# The AI-OS job framework

The skills in this repo describe *what* to do to a maintained folder (onboard a wiki, ingest an
item, reconcile the wiki). This document describes the *shape of the system around them* — how a
headless assisting system is built over a person's real folders so it stays robust, cheap, and
reproducible. The knowledge wiki is the first job family this repo ships, not the boundary of the
design.

It is deliberately generic. A concrete deployment (an unattended pipeline on an always-on machine, a
cron job, a Cowork session a person drives by hand) supplies the timer, the storage, and the model
runner; this framework is the design those deployments share. The reference deployment is
[`family-ai-os`](https://github.com/boshuthebuilder/family-ai-os), which consumes this repo as a
pinned dependency.

## The unit of work: a job

A maintained folder runs **jobs**. A job is one pass over the folder: it reads folder state, reasons
once, and returns a structured result that deterministic guards turn into changes. Updating the wiki
is the most common thing a job does — but it is one job family, not the definition. A job can
equally propose a folder re-organisation, clean duplicates, suggest structure improvements, or
improve the wiki's own Schema. Each such family is its own **archetype** with its own write
contract, flowing through the same three layers and the same gate described below.

What a job family may *touch* is part of its archetype's contract. File-ingest reads the owner's
files in place and writes only the wiki (plus filing inbox items into existing folders); a
folder-hygiene archetype would *propose* moves and deletions for the owner to approve, not execute
them. Whatever the family: every write goes through the deployment's deterministic guards, and
anything that touches the owner's own material defaults to propose-only.

The first archetype this repo ships is **file-ingest** (see
`skills/project-onboarding/archetypes/file-ingest/`), whose two standard jobs are:

- **`ingest`** — incremental and **reactive**. Drain the inbox, update the pages each new or changed
  source touches, append to the log. Cheap; runs often.
- **`reconcile`** — comprehensive and **periodic**. Reconcile the whole wiki against the files
  (dedupe, sweep orphans, fix stale claims, confirm the structure holds). Expensive; runs on a clock.

The names are the same as the modes: a job's `id` equals its `mode`, so there is no third vocabulary.

## The three layers of a job

A job is **not** a monolith. It is three layers, each with a single home, composed at run time:

1. **The prompt template** — the per-job *procedure*. It knows this job's specifics: where the inbox
   is, how to name a filed document, what to check, and the exact structured output to return. It
   **references the skill** for the conventions rather than restating them. (`ingest.md`,
   `reconcile.md` in the archetype.)
2. **The skill** — the shared *conventions*. `wiki-maintenance` is the single home for *how* a wiki
   is kept: the page model, provenance, the never-overwrite-a-human-edit rule, surfacing. One home,
   reused by every job and every interactive session.
3. **The deterministic guards** — the *enforcement*, in the deployment's code, not the prompt. The
   inbox path, the "file only into an existing folder" rule, the `.proposed.md` write-guard, the
   in-root path check: these are enforced deterministically so the model **cannot** violate them even
   if it tries. The prompt *describes* the intent; the code *guarantees* it.

The split matters: guidance the model reads (layers 1–2) is prose it can be persuaded against;
guarantees (layer 3) are code it cannot. Put a rule in the layer that can actually hold it.

## The determinism boundary

> Everything except the reasoning step is a deterministic function of folder state, config, files,
> and the clock. Put non-determinism **only** in the reasoning step.

Gathering what changed, hashing files, reading a snapshot, filing under an existing folder, rolling
frontmatter dates into a Deadlines page, writing the audit log — all deterministic. Only the
*understanding* (what does this document mean, which page does it touch, what should the summary say)
is a model call. This is what makes the system testable, reproducible, and cheap: the same folder
state yields the same gather and the same writes; only one stage is a fresh sample from a model.

## The gate before the model

The single most important cost-and-robustness property:

> A deterministic change-detector decides whether there is anything worth a model call **before** one
> is made. When folder state hasn't moved, the job does nothing — no model call, no spend.

So "reactive" does **not** require a fragile file-watcher. It means **running the cheap deterministic
gate often** — on a short interval, or woken by an event — and letting the gate fall through to a
no-op almost every time. A burst of changes between two ticks coalesces into one run. The expensive
reasoning step is reached only when the gate finds new or changed inputs.

What the gate counts as "something changed", for the file-ingest archetype:

- an item is in the inbox;
- a source file is new, or its content hash differs from the last time it was ingested;
- the calendar feed's event set has changed since the last successfully-ingested snapshot
  (hash the events, ignoring churn like a regenerated-at timestamp).

A change is only **consumed** (recorded as seen) once the run has actually absorbed it — i.e. on a
successful write, not merely on observing it. A failed or skipped run leaves the change pending, so
the next gate re-detects it. This is the fail-loud rule applied to the gate itself.

## Fail loud, never silent

A blocked, denied, stale, or missing read is a **named state**, never a benign empty default. An
empty inbox, a denied calendar grant, and a stale snapshot are three different things and must look
different. A read that can fail returns a status (`ok | empty | stale | missing | error`), and only
`ok` participates in the gate — a stale snapshot must never masquerade as "nothing changed" and
suppress a real change, nor blank a page it can no longer see.

## Scheduling: reactive vs periodic

- **`ingest` is reactive** — a short-interval poll (or an event wake) that runs the gate; idle ticks
  no-op for free. The deployment supplies the timer.
- **`reconcile` is periodic** — a fixed cadence (e.g. weekly). It is a whole-wiki pass that isn't
  triggered by a single change, so it stays on a clock.

## Execution context constraints (why the indirection exists)

These shape any real deployment and are worth stating once, generically:

- **An unattended scheduler often cannot do what an interactive session can.** Writing a synced
  cloud folder, or reading calendar/contacts behind an OS privacy grant, may require a logged-in
  session that a background daemon doesn't have. The pattern: the scheduler **hops into a session
  that holds the capability** to do the write, and capability-bound reads (e.g. the calendar) are
  **decoupled via a deterministic snapshot** — a producer with the grant writes a snapshot file; the
  job reads the snapshot as a pure function of file + clock. The snapshot's freshness is modelled, so
  a missed producer run shows up as `stale`, not as silent emptiness.
- **Least privilege.** A job sees only what its config declares. Read-only stays read-only by
  construction where possible (no write path to misuse), not by a flag.

## What this gives you

A folder that maintains itself: drop a document in, and within one gate interval its wiki absorbs it;
change nothing and nothing runs. The conventions live in one public home (the skills); the design
lives here; a deployment is just an instance that supplies a timer, storage, and a model runner and
follows this shape. Onboard a new folder by stamping the file-ingest archetype — see
`skills/project-onboarding`.
