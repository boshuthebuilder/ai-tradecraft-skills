---
name: wiki-maintenance
description: >-
  How to maintain a project's in-folder wiki — process an inbox item end to end (read, file,
  update the pages it touches, surface actions, log the run), keep a synthesised always-current
  knowledge layer over the human's own files, answer queries, and run periodic lint passes. The
  standard layout is the human-readable numbered-domain structure (worked example below); each
  project's own Schema page is authoritative for its own wiki. Every file-ingest project declares
  this skill so the conventions live in one place rather than being redefined per project.
---

# wiki-maintenance

The wiki is a **synthesised, always-current knowledge layer** between the raw source files and the
questions asked in conversation. Instead of scanning hundreds of documents on every query, you read
the relevant wiki page, which already holds the extracted facts and a pointer back to the source. The
wiki is **not a duplicate** of the folder — it holds summaries, key fields, dates, cross-references
and status flags, never the documents themselves. When a page says "see `Properties/…/Council Tax
2025-26.pdf`", that file is the source of truth; the wiki carries the headline facts.

LLMs don't get bored maintaining cross-references, which is exactly what kills hand-kept wikis — so
the wiki is yours to keep coherent. This skill is the single home for **how**; a project's own Schema
page (below) is the single home for **what its pages are**.

## The shape of a project

A project root looks like an ordinary folder. The human's own material sits at the top, organised
however they like, and is **read in place, never reorganised**. The system owns only a small set of
reserved names, declared in `.familyai/metadata.yaml`:

- the **wiki directory** (`ingest.wiki_dir`, e.g. `Family Wiki/` or `Personal-Boshu Wiki/`) — the
  wiki you maintain (this skill's domain).
- `Outbox/` — drafts and statements awaiting human review.
- `AGENTS.md` + `CLAUDE.md` (symlink) + `GEMINI.md` (symlink) — the project schema, one rulebook
  under three filenames.
- `_Inbox/` — the project's drop folder (the staging queue the daily job drains); its `README.md`
  is ignored.
- `.familyai/` — hidden system folder (`metadata.yaml`, `memory/`).

Everything else at the root is the human's source material. The ingest boundary is an exclusion: read
everything except the reserved names.

## The standard wiki structure — numbered domains, with folder-notes

A wiki the system creates from scratch uses a **numbered, domain-based** layout that mirrors the
human's *own* top-level folders, so the wiki reads the way a person thinks about their affairs
(People, Property, Finance, Health…) rather than as an abstract index. The worked example is the
Family wiki:

```
<wiki_dir>/
├── 00 Index/      00 Index.md       master table of contents + health dashboard (read first)
├── 01 Deadlines/  01 Deadlines.md   derived roll-up of forward dates (do NOT hand-write — see below)
│               └── Coming Events.md  the calendar feed (provenance: calendar)
├── 02 People/     02 People.md       folder-note (household overview) + 01 Boshu.md, 02 Jiayu.md
├── 03 Properties/ …                  one folder per domain, mirroring the human's own folders
├── 04 Finance/    01 Recurring Bills.md, 02 Investments.md, …
│   …
├── 09 Schema/     09 Schema.md       the wiki's constitution — per-page purpose, fields, triggers
└── 10 Log/        10 Log.md          append-only ingest history
```

Conventions that make this layout readable:

- **Number prefixes** (`NN`) drive ordering in Obsidian's sidebar; ignore them when reading a page's
  name. Every page lives **inside a folder of the same name** (Obsidian sorts folders before files),
  so the root sorts in pure numeric order.
- **Folder-note pattern.** Each domain folder has an **overview page named after the folder** (e.g.
  `02 People/02 People.md`) holding folder-level facts, plus **one detail page per item** beneath it
  (`01 Boshu.md`, `02 Jiayu.md`). Shared facts go on the overview; item-specific facts go on the
  detail page.
- **Domains mirror the human's folders.** A new domain page appears because the human has a folder
  for it — never invent a taxonomy the source material doesn't have.

**This is the standard for a *new* wiki only.** An existing wiki is maintained in **its own declared
structure** — its Schema page (or `CONVENTIONS.md`) is authoritative, and you write into the existing
sections rather than imposing this layout over a wiki that is already shaped differently. Standardise
on the numbered-domain shape when starting fresh; follow what is there when it already exists.

## Each page declares its own fields and triggers — the Schema page

The wiki's `Schema` page (`09 Schema/09 Schema.md` in the example) is its **constitution**: for every
page it records **purpose**, the **fields to maintain**, and the **source documents that trigger an
update**. That last list is the routing intent — which page a given kind of source touches. It is the
authority when you (a human, or an agentic pass that can open the page) design or audit the wiki, and
you extend it whenever you add a page or a field. In a **single-shot ingest you do not have the page
bodies open** — you route from the **section and page names you are given** plus the source itself
(next section); the Schema page is where that mapping is recorded and kept authoritative.

A page's "fields to maintain" is a small, explicit contract — e.g. for a person page: identity
documents (with dates and **last-4-only** numbers), immigration status, employment, a health summary
pointer, cross-references. Write enough on the page that the obvious question ("when does the passport
expire?", "what was the latest reading?") is answered from the wiki without opening the source.

## The `00 Index` page — the operator's dashboard

`00 Index` is read first when answering anything. It carries, in order:

- **Most urgent** — the few things that genuinely need attention now, each one line with the figure.
- **Wiki pages** — the table of contents by section, each page with a one-line "covers …".
- **Open questions** — explicit gaps to fill, **struck through (`~~…~~`) when resolved** with a dated
  note of how. This is the running record of what the wiki still doesn't know.
- **Key facts at a glance** — small tables (people, property, vehicle…) of the durable headline facts.

## Processing an inbox item — the core loop

This is the spine of the daily job. For **each** item in `_Inbox/`:

1. **Read / identify it.** Scanned PDFs and screenshots arrive with their OCR'd text in the gather
   excerpt — identify them from that. If the job was routed to a vision model and the item is an
   image present in your workspace, open and read it directly. If you genuinely cannot read it
   (no vision, OCR found no text, or the file is `evicted_unavailable` from iCloud), it has **no
   content**: send it to `needs_a_look` with the given reason **verbatim** — never invent a cause,
   never claim a directory / permission / "read scope" problem, never guess its contents, never file
   it blind.
2. **File it** into the human's **existing** folders by confident match. Give the destination a
   **full path with a descriptive, renamed filename** (rename a meaningless `Scanned Document.pdf` to
   e.g. `Family Finance/Bills/Amex/Amex Cancellation - Boshu 2026-05-27 (ending 1001).pdf`), keeping
   the original extension. **Never create a new top-level folder.** Never let a confident match cross
   an identity-tag boundary. Anything you cannot place confidently stays in `_Inbox/` and is marked
   `needs_a_look` for the dashboard's "Needs a look" panel.
3. **Update the pages the source touches.** Match the source to the right **existing** section/page
   from the structure you are given (the Schema page's source-trigger table is the authority for that
   mapping; when you cannot open it, route from the section/page names plus the source). Update their
   fields; add a provenance link down to the source
   file. **If the source carries a concrete forward-looking date** (renewal, payment, expiry,
   deadline), record it as `deadline: YYYY-MM-DD` (or a `deadlines:` list) in **that page's**
   frontmatter — and **do not hand-write the Deadlines page**: a deterministic step rolls those
   frontmatter dates into it after you run. One ingest typically touches a handful of pages.
4. **Surface what needs a human** — precise and quiet (see *Notifications* below). Most items are
   informational; a true action is rare.
5. **Log the run.** Append one dated line to the log: `## [YYYY-MM-DD] <action> | <short summary>`
   (the recent timeline is `grep "^## \[" log.md | tail`). The audit row the system appends records
   counts: `filed N, wiki M (P proposed), needs K`.

**Fail loud, never silent.** A blocked, locked, evicted or unreadable source is a *named* state
(`needs_a_look` with its reason) — never dropped, never defaulted to "nothing to do". A genuinely
empty inbox and a blocked read must look different.

## Query

A human asks something. Read `00 Index` first, drill into the relevant pages, synthesise an answer
with citations down to the source. File a genuinely valuable answer (a comparison, an analysis) back
as a wiki page rather than letting it vanish into chat.

## Lint — the periodic health pass

Reconcile the wiki **to the files** (the golden source): look for contradictions between pages, stale
claims a newer source supersedes, orphan pages, missing domains and data gaps; refresh `00 Index`
(most-urgent, open-questions, key-facts); record the pass in the log. The lint **never flags or
rewrites `provenance: manual` content** — that is owner-asserted and authoritative.

## Maintenance cadence

Two passes that differ in **scope**, not just schedule:

- **Daily (quick ingest)** — drain `_Inbox/`, update the pages each new source touches, append to the
  log. Cheap; no full-wiki work.
- **Weekly (comprehensive lint)** — reconcile the whole wiki to the files: dedupe, sweep orphans,
  reconcile stale claims, confirm the structure holds.

This pair is the default for a low-volume document folder; a higher-traffic project scales the
frequency, and a `code-autonomous` / research project with no wiki doesn't use it at all — cadence is
a property of the project, declared in its `.familyai/metadata.yaml` jobs.

**Inline vs scheduled depends on who maintains it.** For an **owner-maintained / Cowork** project
(humans and a Cowork session edit the wiki inline as they work), the scheduled jobs are a *safety net*
behind that inline maintenance (`family-ingest.md`). For a **headless** project on the mini with no
inline operator, the scheduled ingest **is** the primary update path (`base-ingest.md`).

## Rules that keep it safe

- **Never overwrite a human edit.** Every file the system writes is hashed in `file-hashes.sqlite`.
  If a human has edited a page the system wrote, propose the change as a `.proposed.md` sibling rather
  than overwriting it.
- **Provenance always — three classes.** Every page (or block) is one of:
  - `provenance: derived` — synthesised from a saved file; the lint reconciles it against the files,
    and every claim links down to its source.
  - `provenance: manual` — a fact the human asked to record that is **not** from a saved file. It is
    authoritative: the lint never flags or rewrites it, and a calendar event never supersedes it.
  - `provenance: calendar` — an external read-only feed (the `Coming Events` page). It is **rebuilt
    wholesale each run** from a fresh snapshot, kept **distinct from the file-derived Deadlines page**
    (calendar events are not file deadlines), and **never `.proposed.md`-guarded** as if human-authored.
    Only update it when the calendar read is fresh (`status: ok`); an empty, stale, missing or blocked
    read must **never blank it** — leave the prior version and note the gap in the log.
- **Sensitive identifiers, last-4 only.** Record passport / account / licence / card numbers as the
  last 4 digits only, never the full number — on every page, in every table.
- **Deadlines are derived, not authored.** The Deadlines page is rolled up deterministically from page
  `deadline:`/`deadlines:` frontmatter; record the date on the page that owns it and let the roll-up
  build the list. Keep it distinct from the calendar's `Coming Events`.
- **One direction only.** The per-user `Wiki-<Identity>/` vault is a synthesis *across* the project
  wikis a user can access; it never writes back into a project wiki, and `gather` excludes user wikis
  from project ingest exactly as it excludes the project wiki, so the synthesis can never loop back as
  a source.
- **A project wiki is self-contained.** Keep each project's wiki about *that project only* — never
  name, reference or link another project from it. Cross-project connections live solely in the
  user-tier wiki.
- **Light entity resolution across projects.** A person or company appearing in two of a user's
  projects becomes one entity page in *their user wiki* (not in either project wiki), with the
  project-level detail linked beneath.

## Notifications — precise and quiet by default

The owner does not want noise or false urgency:

- **State only what the source says, exactly.** Quote the specific figure/status; never round up,
  generalise, or infer beyond the document. If a status page shows *Drive 1 Bad, Drive 2 Good*, say
  that — never "both drives bad". If unsure of a detail, leave it out.
- **A true action is rare.** Flag `action` only for something that genuinely needs the owner to *do*
  something soon **and** is clearly relevant to them. A filing summary, an FYI, a figure from a
  statement, or anything already handled is `info` — quiet activity feed, no interruption. When in
  doubt, use `info` or send nothing.
