---
name: wiki-maintenance
description: >-
  How to maintain an in-folder knowledge wiki — a synthesised, always-current layer over a folder of
  real files. Process an incoming item end to end (read, file by confident match, update the pages it
  touches, surface what needs a human, log it), answer queries from the wiki, and run periodic
  reconcile (lint) passes. The method is the point; the wiki's own Schema page is the authority for its exact pages and
  layout. If a wiki doesn't exist yet, use wiki-onboarding first to create the Schema/Index/Log skeleton.
---

# wiki-maintenance

A wiki is a **synthesised, always-current knowledge layer** between a folder of raw files and the
questions you ask about them. Instead of scanning hundreds of documents on every query, you read the
relevant wiki page, which already holds the extracted facts and a pointer back to the source. The wiki
is **not a duplicate** of the folder — it holds summaries, key fields, dates, cross-references and
status flags, never the documents themselves. When a page says "see `Property/…/Council Tax 2025-26.pdf`",
that file is the source of truth; the wiki carries the headline facts.

LLMs don't get bored maintaining cross-references, which is exactly what kills hand-kept wikis — so the
wiki is yours to keep coherent. **This skill is the single home for *how*; each wiki's own Schema page
is the single home for *what its pages are*.** Read the Schema first; follow it; this skill is the
method that fills it in.

## The shape of a folder

A maintained folder looks ordinary. The owner's own material sits at the top, organised however they
like, and is **read in place, never reorganised**. Beside it live a few system-owned things, named by
whatever your setup declares:

- the **wiki** — the synthesised layer this skill maintains.
- an **inbox / drop folder** (e.g. `_Inbox/`) — where new items land to be filed and ingested.
- optionally a **config / rulebook** for the folder, and an **outbox** for drafts awaiting review.
- optionally an **audit pair** (`_Audit/manifest.json` + `AUDIT.md`) maintained by the
  folder-curation archetype's `audit` job.

Everything else at the root is the owner's source material. The ingest boundary is an exclusion: read
everything except the system-owned names.

**Anything an AI writes lands in the wiki or an outputs tier, never beside the sources.** A summary, a
dashboard or a session instruction file left next to the documents it describes is a stray; an ingest
that finds one files it into the wiki and logs the move.

## The recommended layout (an example — the Schema is the law)

When a wiki is created from scratch, a **human-readable, numbered-domain** layout works well: one folder
per domain, mirroring the owner's *own* top-level folders, so the wiki reads the way a person thinks
about their affairs rather than as an abstract index. A typical shape:

```
<wiki>/
├── 00 Index        master table of contents + a "what needs attention" dashboard (read first)
├── 01 Deadlines    derived list of forward dates (+ a calendar feed, if there is one)
├── 02 People       overview note + one page per person
├── 03 Property     overview note + one page per property
├── 04 Finance      Recurring Bills, Investments, …
│   …
├── 90 Schema       the wiki's constitution — per-page purpose, fields, and update triggers
└── 91 Log          append-only history
```

Conventions that make it readable: number prefixes drive sidebar ordering (in Obsidian, put each page
in a folder of the same name so the root sorts numerically); each domain folder has an **overview note**
of the same name plus **one detail page per item**; a domain exists only because the owner has files for
it — never invent a taxonomy the material doesn't have. The meta pages sit at high numbers (9x) so
content owns the 00–89 range: a wiki that works will grow domains, and Schema and Log should never need
renaming to stay last.

**This is a recommended default, not a law.** The authority for *this* wiki's exact names and layout is
its **Schema page** — maintain the wiki in the structure the Schema declares, and write into the sections
that already exist rather than imposing a different shape. (No wiki/Schema yet? Use **wiki-onboarding** to
create one.)

## Each page declares its own fields and triggers — the Schema page

A wiki's **Schema page** is its constitution: for every page it records the **purpose**, the **fields to
maintain**, and the **source documents that trigger an update**. That last list is the routing intent —
which page a given kind of source touches. It's the authority when you design or audit the wiki, and you
extend it whenever you add a page or a field.

A page's "fields to maintain" is a small, explicit contract — e.g. for a person page: identity documents
(with dates and **last-4-only** numbers), status, key dates, a pointer to the source folder. Write enough
on the page that the obvious question ("when does this expire?", "what's the latest figure?") is answered
from the wiki without opening the source. When you route an incoming source, match it to the right
existing section/page using the Schema's trigger table; if you can't see the Schema body, route from the
section/page names you do have plus the source itself.

## Contract-driven pages (optional profile)

For a wiki that adopts deterministic rendering, extend its Schema with **one contract per page type**:
who reads it, the questions they need answered in priority order, the professional perspective that
frames the answer, required lookup fields and their evidence sources, derived sections, history rules,
and permitted action kinds. Assign each rendered page a declared type. Keep a machine-readable twin
in the project's audit/config tier, with its Schema revision recorded; jobs consume that twin and
report drift. The Schema remains the authority. Unknown types or missing contracts fail for opted-in
pages, never fall back to generic prose. Legacy pages retain the existing body contract.

The reasoning step returns structured `page_facts` when the deployment advertises this capability;
the deployment validates, stores and renders them. The optional field does not replace `body` for a
consumer that has not adopted it: templates request ordinary `body` in that case. A deployment must
implement the alternate path before enabling it. Durable extraction and cache rules live in
[the architecture](../../ARCHITECTURE.md#durable-extracts-for-rendered-wikis-opt-in).

### Page anatomy and evidence

A useful briefing begins with identity, status and next action in its first five body lines. Then
render required key facts, dated events, records on file, actions, record gaps and coming dates, with
an optional reader-specific assessment. The Schema chooses applicable sections and labels; it need
not impose one generic checklist on every subject. Show missing required rows as **not on file**.
Derive Next from live actions and dates; do not print "nothing outstanding" above an open action.
Warning callouts are for evidenced overdue, lapsed or expired states.

- **Check absence against the page's own sources.** Before asserting "not on file", check its
  source list and the relevant documents; a brief that omits a record is not evidence of absence.
  An unreadable or partial source view leaves absence unverified. This prevents chasing a document
  the page already cites.
- **Sources that disagree stay visible.** State what each document says, explain the disagreement
  and name the one settling step — a letter to request, register to check or confirmation to obtain.
  Do not silently choose one source and present a disputed status as settled; preserve the declared
  precedence of owner assertions while recording the conflicting evidence.
- **History records events**, changes of state or decisions. Repeated statements, payslips or bills
  that only evidence continuity belong in records-on-file with cadence and coverage.
- **Actions are typed** (for example pay, decide, chase, renew, file, book), with owner, evidence,
  amount and due date where known. A missing receipt is a record gap, not a payment action without
  evidence of money due. Keep gaps separate from the owner's to-do list.
- **Lookup rows come from extracts** for identifiers, figures, dates and statuses; owner assertions
  and deterministic calendars take their declared precedence. Narrative cannot override those rows.
- **Owner overlays** are separate dated records: page, asserted fields/status, note, date and speaker.
  They do not add a new page-provenance enum. Render their authority visibly, preserve them across
  rebuilds, and supply them to permitted context. Suppress only actions explicitly settled by the
  assertion. Retire an overlay only when a later source confirms it; record contradictions for the
  owner under the existing manual-provenance rule. Model jobs cannot author owner overlays.

### Identifiers, series and derived views

An owner override chooses a named identifier policy: `last-four` (default), `home-only` (full at the
subject's home), or `stated` (full wherever supported by evidence). Store typed identifiers with
holder, kind, home page, source and document status/dates. Masked source values are unresolved suffixes,
not full identifiers. A structural derivation needs a declared validator and the original source;
never guess from a suffix. Current, superseded and expired documents remain distinct, so an old
passport does not create a new expiry action. Enrichment evidence and guards follow the architecture;
test dates, decimal amounts, year prefixes, chart data and cited filenames as exclusions.

A Schema may declare a **series** field: subject, metric, unit, observation date, value and source.
Keep distinct periods or components from one document distinct; deduplicate the same observation.
Extract stated values faithfully; label computations separately with their input evidence and policy.
Reject impossible readings with a recorded reason rather than allowing them into totals. Every
cross-page row carries its date and freshness status, using Schema thresholds. Never combine dates,
currencies or units without an explicit policy; show a missing policy instead of assuming one. Chart
only series declared live. Assessments may follow the reader's perspective, but parent summaries must
agree with children or identify the conflicting evidence, and are generated after the children.

#### The basis of a money table

A spend table counts the underlying cost once, not every document mentioning money. Apply these
rules to the evidence before aggregating; keep extracted amounts intact for provenance:

1. **One premium per policy year per insurer for the same cover.** A broker's invoice and the
   insurer's schedule count once. A near-equal premium is a restatement; a clearly smaller premium
   represents another policy. Check cover and policy identity to resolve uncertain matches rather
   than silently counting or dropping them.
2. **Prices offered are not spend.** Exclude quotations, estimates, tenders, published tariffs,
   rate cards and fee schedules: they state a price, not an incurred cost or payment.
3. **Acquisition is not running cost.** Keep a property completion balance or vehicle purchase
   price in key facts, outside the asset's running-cost table.
4. **A total and its parts count once.** Where one document states several amounts on one day and
   the smaller amounts could be components of the largest, count only the largest in the total;
   retain the components as evidence, not additional spend.
5. **A receipt does not add to its bill.** Match receipts to already-counted bills by value, including
   half- or quarter-value instalments, over a generous date window declared in the table's basis.
   Use the same obligation's evidence to distinguish a match from an unrelated equal payment.
6. **Pay belongs to the staff subject and the pay period.** Never treat a payslip year-to-date total
   as one month's pay. Attribute pay to the staff page wherever the payslip was filed; a copy held
   as travel or visa evidence does not become travel spend.
7. **An updated document counts once.** Reissued bookings or other updates replace the earlier
   version for the same stay or obligation; do not add both versions.
8. **Historical copies are not this period's spend.** Exclude copies in `old`, `previous`,
   `superseded` or `archive` folders from the current-period total; previous owners' invoices do
   not become the current owner's costs.

Print the basis beneath every rendered money table: period, attribution, what was counted and
excluded, and any matching or currency policy. Label whether it counts incurred costs or evidenced
payments; an invoice alone does not establish payment. A page and its folder note must use the same
basis for the same question. Show unresolved counting matches rather than presenting their total as
settled.

Citation-derived hubs (people, counterparties or another facet) are valid cross-cutting indexes, not
new filing homes. The Schema sets their inclusion threshold. Optional `entities` frontmatter may hold
facets deterministically derived from validated links and parties. Layout below a domain, folder-note
conventions and ordering are Schema choices. Qualify ambiguous links by path; follow portable-markdown
for table escaping and the target editor's link conventions.

Index and deadline roll-ups exclude closed subjects, superseded documents and facts belonging to third
parties unless explicitly in scope. Deduplicate by fact identity, not by the number of pages citing it.

When a restricted row contributes to a roll-up, index or parent summary, generalise the **whole
record**, including evidence, amount and other typed fields, to the source's outward ceiling. Keep
only fields that ceiling permits; scrubbing the display string while metadata passes through is not
enforcement. For `subject-clinical`, even an action's kind or owner is outside the outward ceiling.

### Additional depth: measurements-only

An opted-in contract may permit `measurements-only`: typed metric, value, unit, date and printed
reference range on explicitly authorised subject pages, without diagnoses, treatment, clinical
opinions or imaging findings. Restrict both the extraction/context shape and the rendered fields;
a lexical check is supplementary evidence, never the sole privacy boundary. Unrecognised depth
values must fail validation; the supported vocabulary is the enumeration in *Rules that keep it safe*.
Cross-page contributions obey the architecture's context-crossing rule.

### Additional depth: subject-clinical

`subject-clinical` permits full clinical substance — history, active conditions, treatment, dated
encounters, measured values with units and printed ranges, and the plan — on explicitly authorised
subject pages only, while every other page, including domain notes, hubs, roll-ups and the front page,
carries at most that the subject page exists and the date of its last entry. Declare the authorised
subject-page list in the Schema; never infer authorisation from a folder name. `measurements-only`
remains the narrower choice for values without clinical substance.

Apply [the architecture's context-crossing guard](../../ARCHITECTURE.md#context-crossings-and-evidence-bearing-enrichment)
to cut each restricted page's contribution to that outward ceiling **before** another page's model,
tool context or roll-up receives it, including when the destination is another authorised subject
page. The deployment validates the Schema authorisations and enforces the context and output shapes;
a prose instruction alone cannot implement this depth.

For any restricted depth, a supplementary lexical check excludes citations (including link targets),
link labels and filenames, and declares those exclusions in its report: naming a document held is
not itself disclosing its contents. These are exclusions from the lexical content scan only; they
never exempt those surfaces from identifier policy or the source's outward depth ceiling.

## The Index page — the dashboard

The Index is read first when answering anything. It carries, in order:

- **Most urgent / needs attention** — the few things that genuinely need action now, each one line with
  the figure.
- **Contents** — the table of contents by section, each page with a one-line "covers …".
- **Open questions** — explicit gaps to fill, **struck through (`~~…~~`) when resolved** with a dated
  note of how. The running record of what the wiki still doesn't know.
- **Key facts at a glance** — small tables of the durable headline facts.

## Processing an incoming item — the core loop

This is the spine. For **each** item in the inbox / drop folder:

1. **Read / identify it.** Scans and screenshots usually arrive with their text already extracted (OCR);
   identify them from that, or open the image directly if you can. If you genuinely cannot read it (no
   text, or the file is blocked/unavailable), it has **no content**: flag it **for review** with the
   real reason — never invent a cause, never guess its contents, never file it blind.
2. **File it** into the owner's **existing** folders by confident match, with a **descriptive, renamed
   filename** (rename a meaningless `Scanned Document.pdf` to something like
   `Finance/Bills/<provider> Statement 2026-05-27.pdf`), keeping the extension. **Never create a new
   top-level folder.** Anything you can't place confidently stays put and is flagged for review.
   **On a filename collision, compare content before renaming:** hash the inbox item against the file
   already at the destination (file-preprocessing keys its whole manifest on content hashes for exactly
   this reason). Identical bytes are a duplicate, not a filing problem — don't file it; log it as a
   duplicate and route it to deletion/review. Only different content behind the same natural name earns
   the non-colliding rename.
   **When the destination folder seems missing**, check its siblings for the folder the local convention
   actually predicts (country vs city names, year prefixes) before raising anything — the right folder
   usually exists under a different convention than the source suggests. If a folder genuinely must be
   created, escalate *with the proposed path* as a one-click decision for the owner, never a bare report
   of absence.
3. **Update the pages the source touches.** Use the Schema's trigger table to pick the page(s); update
   their fields; add a provenance link down to the source file. **If the source carries a forward-looking
   date** (renewal, payment, expiry, deadline), record it as `deadline: YYYY-MM-DD` (or a `deadlines:`
   list) in **that page's** frontmatter. If your setup has a deterministic step that rolls those dates
   into a Deadlines page, don't hand-write that page — let the roll-up build it; otherwise update the
   Deadlines list yourself from the page dates. One item typically touches a handful of pages — and the
   Index counts among them whenever the item changes anything the Index carries (the urgent list, a key
   fact, an open question).
4. **Surface what needs a human** — precise and quiet (see *Surfacing*, below).
5. **Log it.** Append one dated line: `## [YYYY-MM-DD] <action> | <short summary>`.

**Authored notes — free text with no source document.** An inbox item that is the owner's own words
(an idea, a brainstorm, a decision) rather than a document to file is an **authored note**: route it
to the domain the Schema declares for authored content (e.g. an *Ideas* domain), mark the page or
block `provenance: manual`, and treat its content as authoritative from then on. Carry the owner's
text **verbatim** as the note body — synthesis may add a title, date and links around it, never
replace it: the wiki page becomes the only copy of the owner's words once the inbox item is drained.
There is nothing to file in step 2 — the note's home *is* the wiki page.

**Fail loud, never silent.** A blocked, locked, unavailable or unreadable source is a *named* state
(flagged for review with its reason) — never dropped, never defaulted to "nothing to do". A genuinely
empty inbox and a blocked read must look different. **And loud once, not loud repeatedly:** raise each
distinct blocker exactly once. When a later run meets the same blocker, increment a counter on the
existing entry ("×8"), never append a new log entry, action or escalation — one line per *state change*.
A frequent tick that re-raises the same block converts one problem into a queue-management workload of
its own.

## Query

When asked something, read the Index first, drill into the relevant pages, and synthesise an answer with
citations down to the source. File a genuinely valuable answer (a comparison, an analysis) back as a wiki
page rather than letting it vanish into chat.

## Reconcile — the periodic health pass (the lint)

Reconcile the wiki **to the files** (the golden source): look for contradictions between pages, stale
claims a newer source supersedes, orphan pages, missing domains and data gaps; refresh the Index
(most-urgent, open-questions, key-facts); record the pass in the log.

Every reconcile starts with the cheap, deterministic checks, and each one reports its count **even when
the count is clean** — "no findings" from a sweep that saw nothing and "no findings" from a healthy wiki
must never look alike:

- **Conformance first.** Count pages missing the required frontmatter keys (`provenance`,
  `last-updated`, `status`) and report N-of-M conforming — "94/94" is a liveness signal; silence is not.
  A page the sweeps cannot read is a finding, never a skip. On a legacy wiki, migrate a bounded batch to
  the canonical keys each run, so the wiki converges instead of staying invisible forever.
- **Paths resolve.** Check that referenced paths exist — frontmatter `source:` keys, body-level
  backticked paths, and claims of the form "file X exists at Y" — and report the dead count.
- **The Schema matches reality.** Diff the Schema's declared layout (the top-level files and folders it
  names) against a directory listing; an undeclared folder or a described-but-missing page is a finding.
- **The Index is the freshest page.** If any page's `last-updated` is newer than the Index's, refresh
  the Index (most-urgent, open questions, key facts) within this pass — the read-first page is the last
  thing allowed to rot. Reconcile the dashboard against the log/queue's open items too: every open
  action either appears under needs-attention/open-questions or is deliberately excluded. (On a wiki
  that predates the Index spec, this duty is also what bootstraps the dashboard into existence.)
- **Fold the log's no-op runs.** Collapse a run of consecutive "nothing changed" entries older than a
  few days into one digest line — the log stays legible, the history stays complete.

Reconcile **never flags or rewrites
`provenance: manual` content** — that is owner-asserted and authoritative. Authored notes (ideas,
brainstorms) may be *merged or cross-linked* during a reconcile where they clearly belong together, but
their content and `provenance: manual` marking are preserved — consolidation never deletes or contradicts
what the owner asserted.

### Render verification for contract-driven pages

For an opted-in wiki, every render and reconcile publishes a dated verification artefact (for example
`_Audit/wiki-verify.json`) with page count, checked scope and counts including zero: missing mandatory
rows or undeclared types, stale/missing extracts, source citations, broken links, malformed tables,
identifier/depth violations and sync conflict copies. Missing or unreadable inputs are findings, not
clean checks; an absent report is **not verified**. Record checks not performed explicitly rather than
reporting zero. Use `productivity:portable-markdown` for table and link mechanics. Visual outputs need
an editor/theme check when introduced or changed; text lint cannot establish chart legibility.

Check an "is not on file" claim against the page's own citations; deployments may enforce this
consistency check deterministically. Lexical depth counts report real content findings after excluding
citations, link targets, link labels and filenames, with those exclusions and the checked scope named
in the artefact. Report identifier and crossing-guard checks separately so a clean lexical count
cannot conceal an unchecked privacy boundary.

Before first hand-off or after changing page anatomy, use the reader-review acceptance step in
`wiki-onboarding`. Keep its findings and the builder's responses beside the verification artefact.

## Cadence — ingest and reconcile

Two passes that differ in **scope**, not just schedule (the file-ingest archetype names them `ingest`
and `reconcile`):

- **Ingest** — incremental and **reactive**: drain the inbox, update the pages each new or changed
  source touches, append to the log. Cheap; run it often.
- **Reconcile** — comprehensive and **periodic**: reckon the whole wiki to the files — dedupe, sweep
  orphans, reconcile stale claims, confirm the structure holds.

**Every regeneration reckons to the live files immediately before rendering.** Diff the live folder
against the source snapshot the pages will use, adopt moves so citations resolve, handle removed
sources as drift, and read new or changed sources onto their pages before rendering. Record the
snapshot and the added, removed, moved and edited sources with the pass, so its log states what the
render was true against. An incomplete or blocked reckoning is a named gap, not a verified render.
This check is part of regeneration, not deferred to the periodic reconcile: stale inputs can produce
confident wrong statements, and the reader cannot tell which rows to distrust.

**A deterministic gate runs before either spends model effort.** A cheap check of folder state — new or
changed sources, items in the inbox, a changed calendar snapshot — decides whether there is anything to
do, so an unchanged folder costs nothing. This is what lets `ingest` run reactively on a frequent tick:
it no-ops for free until something actually moves, and only a real change reaches the model. The gate
applies the project's **class policy** (`folder-curation`): count-only classes cost a count, not a
hash walk, so a folder that is mostly photographs or imaging stays cheap to keep.

A low-volume folder is well served by a frequent reactive ingest and an occasional reconcile; scale to
the folder's traffic. **Who maintains it matters:** when a person (or an interactive session) edits the
wiki inline as they work, any scheduled automation is a *safety net* behind that; for an unattended folder
with no inline maintainer, the scheduled passes are the primary path.

## Rules that keep it safe

- **Never overwrite a human edit.** A maintained wiki keeps a record (e.g. a file-hash log) of every page
  the system wrote. If a human has since edited such a page, propose the change as a `.proposed.md` sibling
  rather than overwriting it.
- **Never shrink a derived page silently.** The human-edit guard doesn't catch system-on-system clobbers,
  so size is its own tripwire: an edit that would remove more than roughly half a page's content, or
  empty sections the Schema declares for that page, diverts to a `.proposed.md` sibling **regardless of
  who last wrote the page**. The Schema already knows what the page should hold — use it as the yardstick.
- **Transient artefacts don't linger.** A `.proposed.md` awaiting review is the only sanctioned sibling,
  and only until the owner accepts or rejects it. Any other parked copy — a `.superseded` page, a `.bak`,
  a backup a rewrite left behind — is finished business: merged or discarded means deleted (or queued for
  owner deletion), never left beside the live page.
- **Provenance always.** Mark each page (or block) by where it came from:
  - **derived** — synthesised from a saved file; the lint reconciles it against the files, and every claim
    links down to its source. A page whose Schema entry says its figures are *computed from an extract*
    is regenerated **from** that extract, never edited around it — a pass that cannot run the
    regeneration must not touch the figures (a hand-restated table looks extract-derived while drifting
    row by row).
  - **manual** — a fact the owner asked to record that is **not** from a saved file. It is authoritative:
    the lint never flags or rewrites it. One upgrade path exists: when a subsequently ingested source
    **confirms** the assertion exactly, ingest may rewrite the fact as `derived`, citing the new source
    (keeping a "first asserted by owner on YYYY-MM-DD" trace where useful) — a confirmed fact rejoins
    reconciliation rather than staying exempt forever. Contradiction is different and unchanged: manual
    wins, the discrepancy is recorded, the owner is asked.
  - **external feed** (e.g. a calendar's "Coming Events") — a read-only view of an external source, kept
    **distinct from file-derived deadlines** and never `.proposed.md`-guarded as if human-authored. In
    the automated job framework it is **rendered deterministically** from the snapshot (a pure function
    of feed + clock, exactly like the Deadlines roll-up) — a scheduled job never rebuilds it; only a
    hand-kept wiki refreshes it manually. Either way an empty, stale or blocked read must **never blank
    it** — leave the prior version and note the gap.
- **Sensitive identifiers, last-4 only — unless the owner decides otherwise.** Record passport / account /
  licence / card numbers as the last 4 digits only, never in full — on every page, in every table. The
  owner may override this: an explicit, dated decision recorded in the Schema (or the wiki's
  data-sensitivity page) is respected by every sweep from then on. A decided exception stops alerting;
  it never becomes a permanently re-raised flag. This rule is stated here because a pass should honour
  it, **and enforced by the deployment's crossing guard** on everything a pass returns — a model
  holding the document quotes the number it was told not to often enough that the instruction cannot
  be the only line of defence (see [`ARCHITECTURE.md`](../../ARCHITECTURE.md)).
- **Sensitivity has a depth as well as a mask.** The Schema may set a per-domain depth: `full`
  (default), `administration-only` (a legal matter: adviser, dates, invoices, next deadline, never
  the substance of advice), `dates-only` (health: appointments and "a report exists at <path>"),
  `measurements-only` or `subject-clinical` (the opt-in subject-page depths defined above). A
  deterministic exclude list (paths and globs the gather never presents) handles credentials and
  anything the owner names; both are recorded decisions and are never re-raised. Identifiers leak
  through filenames as well as bodies: a filename carrying a full account or document number is a
  finding for the next curation round, and the wiki never repeats it.
- **Deadlines are derived, not authored.** Record the date on the page that owns it; build the Deadlines
  list from those, and keep it distinct from any calendar feed. **An empty roll-up must say why:** zero
  rows found while derived pages exist is a likely keying fault, rendered as a loud banner on the
  Deadlines page ("roll-up found no frontmatter deadlines across N pages") — never a bare "None". A
  deployment's deterministic roll-up enforces this in code (prose can't hold it); a hand-kept wiki
  applies it by hand.
- **A wiki is self-contained.** Keep a wiki about *its own folder* — don't name or link another project
  from it. If your setup maintains a separate cross-folder or user-level wiki, that is the only place
  cross-references live, and it only ever reads project wikis — it never writes back into them.

Synced-folder write safety follows
[the architecture's write contract](../../ARCHITECTURE.md#writes-into-synced-folders).

## Renaming a page or folder — the rename protocol

The Schema is the single home for layout, so a layout *change* is a Schema change plus a sweep:

- **Sweep the whole project folder** for the old path — wiki pages, memory files, the folder's
  rulebook/config, anything the deployment keeps beside the wiki. Wiki-internal links, frontmatter
  `source:` keys and config values all move in the same pass.
- **Never rewrite the append-only log.** Historical paths in old entries are records of what was true,
  not dead links to fix.
- **Out-of-folder consumers get a watch item.** Anything that reads the old path but can't be swept from
  here (an engine's prompt templates, an external config) is logged as a watch item and verified against
  that consumer's next run — a rename isn't done until its last consumer has survived it.
- Deployments do well to resolve the Log and Schema **by role** (from the Schema itself, or by layout
  detection) rather than by hardcoded path, so a rename is a one-line change instead of a hunt.

## Canonical frontmatter — the keys the deterministic sweeps read

The deterministic health sweeps (orphans, freshness, the Deadlines roll-up) don't read prose — they key
on frontmatter fields. A page that spells a field differently is **invisible** to them: a fresh page
under a mistyped key looks stale forever; a mis-keyed source path never gets orphan-checked. So the keys
are a contract, not a style choice. The first three are **required on every derived page**; the rest are
**conditional** on the page's content:

| key | required? | value | read by |
|---|---|---|---|
| `provenance` | always | `derived` \| `manual` \| `calendar` | every sweep (skips `manual`/`calendar`) |
| `last-updated` | always | `YYYY-MM-DD` | the freshness sweep |
| `status` | always | `current` \| `superseded` | every sweep (skips `superseded`) |
| `entities` | optional | Schema-defined facet lists | hub/facet index generation |
| `source` *(single)* / `sources` *(list)* | when file-derived | **project-root-relative** path(s) to the source file(s) — never absolute, so a folder rename or machine move is a no-op — or, for a cross-project synthesis, the source **pages** | the orphan sweep |
| `deadline` *(single)* / `deadlines` *(list)* | when a forward date exists | `YYYY-MM-DD` (or `{date, note}`) | the Deadlines roll-up |

(A cross-project user-tier page is `provenance: derived` with `last-updated`/`status` but need carry no
`source:` path and no deadline; a `provenance: manual` note carries no `source:` at all.)

**Write the canonical form; accept the legacy alias.** `source` and `sources` are both canonical — use
the singular for one source, the plural list for several (a reader unions them). The one legacy alias a
reader must still accept is **`updated:` for `last-updated:`** — older wikis carry it, so the freshness
sweep reads either, but **every new or rewritten page uses `last-updated:`**. Don't invent further
spellings (`date:`, `modified:`, `src:`): they are silently invisible to the sweeps. When you touch a
page carrying a legacy alias, migrate it to the canonical key.

**Adoption is explicit, never assumed.** Dropped onto a wiki that predates this contract, the sweeps'
starting state is blindness — every legacy-keyed page is invisible, and "no findings" is
indistinguishable from health. So on first contact, inventory conformance: count the pages that don't
parse under the canonical keys and surface the number on the Index as an error state. Until every
derived page conforms, legacy-keyed pages are findings, never skips — the reconcile duties above make
this the first check of every pass.

## Surfacing what needs a human — precise and quiet

- **State only what the source says, exactly.** Quote the specific figure/status; never round up,
  generalise, or infer beyond the document. If a status page shows *Drive 1 Bad, Drive 2 Good*, say that —
  never "both drives bad". If unsure of a detail, leave it out.
- **An observation is a wiki write, not an alert.** Before surfacing anything, ask the question that
  decides it: **is there a physical act the owner must perform that this system cannot?** Not "is this
  important" — importance is why you write it down, not why you interrupt. If there is such an act,
  name it: one sentence, the exact file or place. If there is not, record it and say nothing; the page
  you just wrote is where it will be read.
  Qualifies: deleting a file the job may not delete, opening something the pipeline cannot read, a
  decision only the household holds. Does not: a discrepancy already recorded on the page, something
  the next pass finishes unaided, anything whose resolution is "wait and see".
  This replaces the older "a true action is rare — when in doubt, inform quietly". Adverbs are
  re-judged every run; "who can act on this" has an answer. A live queue running the old wording
  reached eight open alerts of which five were observations the wiki had already recorded better.
