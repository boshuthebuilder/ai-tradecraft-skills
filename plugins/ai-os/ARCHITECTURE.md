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

A maintained folder runs **jobs**. A job is one pass over the folder: it reads folder state, reasons,
and returns a structured result that deterministic guards turn into changes. The reasoning is usually a
**single model call** (`single_shot`); a job may instead run a **bounded, read-only agentic loop** that
investigates before it answers — but it returns the *same* structured contract, is given *read-only*
tools only, and every write still flows through the deterministic guards (a write tool inside the loop
would bypass them and is not allowed). One call or a bounded loop, the reasoning stage is the only
non-deterministic part; the execution mode is a per-job config choice, not a different contract. Updating the wiki
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
`plugins/ai-os/skills/project-onboarding/archetypes/file-ingest/`), whose two standard jobs are:

- **`ingest`** — incremental and **reactive**. Drain the inbox, update the pages each new or changed
  source touches, append to the log. Cheap; runs often.
- **`reconcile`** — comprehensive and **periodic**. Reconcile the whole wiki against the files
  (dedupe, sweep orphans, fix stale claims, confirm the structure holds). Expensive; runs on a clock.

The second is **user-synthesis** (`plugins/ai-os/skills/project-onboarding/archetypes/user-synthesis/`): a gated
synthesis of a per-person, cross-project view (see *Tiers and identities*, below). It also shows that
an archetype's *source* need not be the owner's files at all — its sources are other wikis. Whatever
the source, the same shape holds: gather presents the model a deterministic, access-scoped view of
it, and only the reasoning step is a model call. Its user-tier vault is **incrementally evolved**, not
regenerated, so — like file-ingest — it is a **pair**: an incremental, reactive `synthesise` and a
periodic `reconcile` twin (see *The type-1 user vault*, below, and the twin rule under *Scheduling*).

The third is **code** (`plugins/ai-os/skills/project-onboarding/archetypes/code/`): a periodic `digest` + a
`code-review` over a **git clone** the system reads read-only — a third kind of source (a repository,
not the owner's documents or other wikis). It reaffirms the boundary: gather reads the clone's history
*deterministically* (`git` is a pure function of clone state), the reasoning summarises or reviews, and
the only writes are report pages through the deployment's guards — never to the code. A code project
offers no `ingest`, since its source is a clone, not an inbox of documents.

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
frontmatter dates into a Deadlines page, **rendering a calendar snapshot into a `Coming Events` view**,
writing the audit log — all deterministic. A calendar feed is an external read, not file-derived, and
its forward view is a pure function of the snapshot; rebuilding it through the model each run is both
waste and a source of churn, so it is rolled up deterministically exactly like Deadlines and the
prompt templates are told not to build it. Only the *understanding* (what does this document mean,
which page does it touch, what should the summary say) is a model call. This is what makes the system testable, reproducible, and cheap: the same folder
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

For the user-synthesis archetype, the same rule over different inputs: the content of every wiki the
identity may access, plus the accessible-project set itself. The more expensive the reasoning step,
the more the gate matters — a full cross-project synthesis is the costliest pass in the system, and
the gate is what makes running its check every few minutes free.

A change is only **consumed** (recorded as seen) once the run has actually absorbed it — i.e. on a
successful write, not merely on observing it. A failed or skipped run leaves the change pending, so
the next gate re-detects it. This is the fail-loud rule applied to the gate itself.

## Fail loud, never silent

A blocked, denied, stale, or missing read is a **named state**, never a benign empty default. An
empty inbox, a denied calendar grant, and a stale snapshot are three different things and must look
different. A read that can fail returns a status (`ok | empty | stale | missing | error`), and only
`ok` participates in the gate — a stale snapshot must never masquerade as "nothing changed" and
suppress a real change, nor blank a page it can no longer see.

The same principle governs any **capped or truncated view** the gather stage hands to a model. A
listing that was trimmed to fit a context budget is a *partial view*, and it must be **marked as such**
in the context — a sentinel `omitted: N` **count** on a capped section (and, where the deployment can,
the `omitted_paths` themselves, kept distinct from the count), a `truncated` flag when a listing didn't
fit at all, an `excerpt_truncated` marker on a page shown only in part, and a *distinct* list of
sources known to be deleted/moved (as opposed to merely not-shown). This is a gather-contract
requirement, not prompt etiquette: without it a prompt cannot tell "this page is gone" from "this page
wasn't shown this run", and the review found that ambiguity is what makes a model report false
orphans, false missing-pages, and rewrite pages whose unseen tail it then drops. Mark the partiality
deterministically at the boundary; the prompt templates are written to trust those markers.

## Consuming a pinned release

A deployment resolves its skills from a **clone of this repo checked out at a release tag**, named in
its own config. That pin is the deployment's promise to itself: unattended jobs run a reviewed version
of the method rather than whatever is newest. Two failures make the promise hollow, and both are
silent — which is why the consumer side needs its own rules rather than trusting the tag.

**A pin nothing enforces is documentation.** If the deploy does not check the named ref out, advancing
the pin edits a file and changes nothing: the clone stays where it last was, the pinned tier still
*resolves*, and jobs keep running an old method with nothing failing. Only a deep health probe notices,
and its natural advice ("redeploy") is exactly what does not help. So the deploy must materialise the
pin **as a hard gate** — a release that cannot obtain its skills does not activate, because activating
it runs new code against old method with nothing saying so. Fetch the tag without `--force`: a released
tag that moved upstream must fail loudly rather than substitute a commit nobody reviewed.

**Verify before the switch, not after.** The directory jobs read is live: on an always-on machine a
scheduled job can start at any moment, so checking the candidate out and *then* verifying leaves a
window in which production runs an unverified tree. Materialise the candidate somewhere throwaway
(a detached worktree), verify it there, and only then move what jobs read. A first-ever clone is the
same hazard — populate it only with a verified commit.

**Verify against what the deployment actually consumes**, which is narrower and more specific than
"the release looks fine": the skills its jobs declare, the archetype paths its prompt templates derive
from, and — the one that matters most — the **placeholders those templates use**. Placeholder
substitution typically replaces the fields it is given and leaves unknown tokens verbatim, so an
archetype that grows a field the deployment does not supply ships `{like_this}` into a live prompt with
no exception and no log line. A deployment that renders an upstream field under a different local name
should *declare* that translation, so a genuinely new upstream field is a finding rather than silent
corruption. Run the check where a bad pin can still be stopped — on the change that advances it, and
again on the machine, since the first can be bypassed and a tag can move between them.

**Judge drift on content, not the tag.** A release whose changes never touch the archetypes a
deployment mirrors is not drift for that deployment, and flagging it trains an operator to re-stamp
without looking; a real upstream edit must not be able to hide behind a mechanical tag bump.

**Keep the fallback visible.** A deployment that falls back to a bundled copy when the pinned clone is
unavailable is running a method version nothing verified. That may be the right trade for availability,
but per *Fail loud, never silent* it is a named state, never a green one — and a host that genuinely
expects the pinned tier is entitled to refuse to run at all rather than substitute silently.

## Surfacing: the raised-item lifecycle

A job that finds something it cannot safely resolve **escalates** it — a `needs_a_look` item. The
review of the reference deployment found the sharpest, most persistent failure here: a job re-raised
the *same* items week after week, because nothing it raised ever re-entered the next run. A dashboard
"Resolve" only marked a notification seen; the job had no memory of what was already open, so it
rediscovered and re-surfaced it every pass. This is a **framework-level contract**, not a deployment
detail — any AI-OS deployment reproduces the defect unless the spec requires the lifecycle:

- **Every escalation has a stable key** — a normalised function of the item + its reason class + the
  source **path/identity** (not its content hash, which changes whenever the evidence does, and would
  mint a new identity instead of matching the existing concern) — so "the same concern" is recognisable
  across runs even as wording drifts. The evidence hash is stored *alongside* the key, for
  change-detection, not folded *into* it.
- **The deployment persists raised items** with a status (`open | resolved | dismissed`); the human's
  resolution actions (a dashboard button, a reply) write that state. Escalations are durable records,
  not fire-and-forget notifications.
- **The ledger of open, recently-resolved, and dismissed items is injected into every gather context**
  (as a `previously_raised` list, or whatever the deployment names it), each entry carrying its status
  and evidence hash. The prompt templates are written against it: **never re-raise an item that is open
  or dismissed** — reference it — and reopen a *resolved* one only when its evidence hash shows the
  underlying facts have changed (then say what changed). Dismissed means the human judged it a non-issue;
  it stays suppressed like an open one.
- **Escalations are decidable in one step.** Each carries a `what_would_resolve` — one sentence naming
  the single decision or action that closes it — and, where the job can name it, an optional
  `proposed_action`. A bare "please check this" is not an escalation; it is noise.

This closes the loop the gate opened: the gate decides whether to spend a model call; the ledger
decides whether a *finding* is new. Together they are why a healthy folder is both cheap and quiet —
nothing runs when nothing changed, and nothing is surfaced twice.

## Tiers and identities

Two concepts the archetypes above rest on:

- A **project** is a maintained folder. An **identity** is an access principal — a person — that may
  own projects and receive a synthesis. Access is **one rule** (do the requester's tags intersect the
  target's?) applied at every boundary: which jobs an identity may trigger, which accounts a service
  reads, and which wikis a synthesis may see. One rule, single-homed in the deployment, so it can
  never drift between surfaces.
- Wikis come in two **tiers**. A **project-tier** wiki is strictly self-contained: it never names or
  links another project (the `wiki-maintenance` rule). A **user-tier** wiki — one per identity — is
  the only place cross-project links live: it is *synthesised over* the project wikis that identity
  may access, reads them, and never writes back into them. Isolation is by construction: the
  synthesis job's gather only ever presents the wikis the access rule allows, so a cross-tier leak
  cannot happen downstream of it.

Onboarding an *identity* (as opposed to a project) is its own skill — **`user-onboarding`** — because
a user vault is a different shape from a project wiki: its storage is owned differently (see *Storage
ownership*, below), it is a single self-contained vault rather than a wiki subfolder, and it carries
distinct content areas. See `plugins/ai-os/skills/user-onboarding` for the flow and *The type-1 user vault* for the
shape it stamps.

### Storage ownership

A binding prerequisite, because it shapes step one of identity onboarding. **User-tier and project
folders are created in the *user's own* cloud account and *shared into* the worker** — never created
on the worker's account. The handshake: the user creates the folder under their own identity, shares
it to the worker (`<worker-account>`), and the worker accepts the invite; the deployment then maps the
shared-in path in its per-host path config. This keeps the storage on the user's own plan and the
ownership with the user (they can revoke access, and their data never sits on the worker's quota). A
deployment that materialises folders on the worker has inverted the model.

### The type-1 user vault

The user-synthesis archetype writes into a **single self-contained vault** — the *user vault* (a
"second brain"), one per identity, named distinctly (`<Identity> Second Brain`). Unlike a project,
**the folder itself is the vault** (no wiki subfolder), and it is organised into a fixed skeleton of
**numbered areas**, each carrying a same-name *folder-note* (a high-level summary + how-to-read; the
[Obsidian Folder Notes](https://github.com/LostPaul/obsidian-folder-notes) convention). The skeleton:

```
<Identity> Second Brain/
├── <Identity> Second Brain.md   root folder-note: what this is + how to read
├── 00 Index/                    the map into the areas below (system-maintained)
├── 01 Knowledge/                DERIVED — synthesise owns it; an emergent, multi-layer, INCREMENTALLY
│                                evolved cross-project hierarchy (never regenerated wholesale)
├── 02 Ideas/                    AUTHORED — flat, comprehensive, atomic idea pages captured via the
│                                interactive surfaces (never hand-edited in the vault, never archived)
├── 03 Reports/                  AI-generated point-in-time documents, date-binned (03 Reports/YYYY/MM/)
├── 09 Schema/                   the vault's constitution: organising principles + stability rules
└── 10 Log/                      append-only run history
```

Three areas, three determinism stories: **Knowledge** is model-derived but **incrementally evolved**
(the synthesis reads the current tree and makes minimal stable changes, preserving page paths so links
survive — it must never rebuild the vault wholesale); **Ideas** are owner-authored, captured through
the interactive layer as atomic one-idea-per-file pages; **Reports** are AI documents the synthesis
never touches. The asymmetric-linking rule: Ideas may link Knowledge, but **Knowledge never links
Ideas** (it stitches consolidated cross-project understanding, not un-incubated ideas). A matured idea
is **promoted to a project**, which the synthesis then stitches into Knowledge — Ideas are never folded
directly into Knowledge (Knowledge is derived-only).

Because Knowledge is incrementally evolved, the user vault can **drift** from its sources — so the
archetype is a `synthesise`/`reconcile` **pair**, not a lone job (the twin rule below).

## Scheduling: reactive vs periodic

- **`ingest` is reactive** — a short-interval poll (or an event wake) that runs the gate; idle ticks
  no-op for free. The deployment supplies the timer.
- **`reconcile` is periodic** — a fixed cadence (e.g. weekly). It is a whole-wiki pass that isn't
  triggered by a single change, so it stays on a clock.
- **`synthesise` is reactive; `reconcile` is its periodic twin.** The twin rule: a `reconcile`-style
  periodic pass exists **only** when the maintained artefact is built *incrementally* and can therefore
  drift from its source. A full-rebuild job regenerates everything from current sources on every run,
  so there is nothing to drift and one gated job suffices; an archetype that later turns incremental
  (usually for cost) re-earns its periodic full pass at that moment. **The user-synthesis archetype is
  the worked example of that rule:** its user vault began as a full rebuild (no twin), then turned
  incremental so its Knowledge tree would survive across runs (paths stable, links intact) — and at
  that moment it re-earned its twin. So today it is a pair: a reactive `synthesise` that evolves the
  Knowledge slice a source change touches, and a periodic `reconcile` that reckons the *whole* vault
  against *all* accessible sources (prune cruft, repair broken cross-refs, confirm the `09 Schema`
  stability rules still hold) — the same incremental-write contract, differing only in breadth and
  cadence. Reconcile runs on a clock, not on the reactive gate.

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
`plugins/ai-os/skills/project-onboarding`.
