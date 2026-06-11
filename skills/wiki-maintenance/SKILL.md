---
name: wiki-maintenance
description: >-
  How to maintain an in-folder knowledge wiki — a synthesised, always-current layer over a folder of
  real files. Process an incoming item end to end (read, file by confident match, update the pages it
  touches, surface what needs a human, log it), answer queries from the wiki, and run periodic lint
  passes. The method is the point; the wiki's own Schema page is the authority for its exact pages and
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

Everything else at the root is the owner's source material. The ingest boundary is an exclusion: read
everything except the system-owned names.

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
├── 09 Schema       the wiki's constitution — per-page purpose, fields, and update triggers
└── 10 Log          append-only history
```

Conventions that make it readable: number prefixes drive sidebar ordering (in Obsidian, put each page
in a folder of the same name so the root sorts numerically); each domain folder has an **overview note**
of the same name plus **one detail page per item**; a domain exists only because the owner has files for
it — never invent a taxonomy the material doesn't have.

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
3. **Update the pages the source touches.** Use the Schema's trigger table to pick the page(s); update
   their fields; add a provenance link down to the source file. **If the source carries a forward-looking
   date** (renewal, payment, expiry, deadline), record it as `deadline: YYYY-MM-DD` (or a `deadlines:`
   list) in **that page's** frontmatter. If your setup has a deterministic step that rolls those dates
   into a Deadlines page, don't hand-write that page — let the roll-up build it; otherwise update the
   Deadlines list yourself from the page dates. One item typically touches a handful of pages.
4. **Surface what needs a human** — precise and quiet (see *Surfacing*, below).
5. **Log it.** Append one dated line: `## [YYYY-MM-DD] <action> | <short summary>`.

**Fail loud, never silent.** A blocked, locked, unavailable or unreadable source is a *named* state
(flagged for review with its reason) — never dropped, never defaulted to "nothing to do". A genuinely
empty inbox and a blocked read must look different.

## Query

When asked something, read the Index first, drill into the relevant pages, and synthesise an answer with
citations down to the source. File a genuinely valuable answer (a comparison, an analysis) back as a wiki
page rather than letting it vanish into chat.

## Lint — the periodic health pass

Reconcile the wiki **to the files** (the golden source): look for contradictions between pages, stale
claims a newer source supersedes, orphan pages, missing domains and data gaps; refresh the Index
(most-urgent, open-questions, key-facts); record the pass in the log. The lint **never flags or rewrites
`provenance: manual` content** — that is owner-asserted and authoritative.

## Cadence

Two passes that differ in **scope**, not just schedule:

- **Quick ingest** — drain the inbox, update the pages each new source touches, append to the log. Cheap.
- **Comprehensive lint** — reconcile the whole wiki to the files: dedupe, sweep orphans, reconcile stale
  claims, confirm the structure holds.

A low-volume folder is well served by a frequent quick pass and an occasional deep one; scale to the
folder's traffic. **Who maintains it matters:** when a person (or an interactive session) edits the wiki
inline as they work, any scheduled automation is a *safety net* behind that; for an unattended folder with
no inline maintainer, the scheduled pass is the primary path.

## Rules that keep it safe

- **Never overwrite a human edit.** A maintained wiki keeps a record (e.g. a file-hash log) of every page
  the system wrote. If a human has since edited such a page, propose the change as a `.proposed.md` sibling
  rather than overwriting it.
- **Provenance always.** Mark each page (or block) by where it came from:
  - **derived** — synthesised from a saved file; the lint reconciles it against the files, and every claim
    links down to its source.
  - **manual** — a fact the owner asked to record that is **not** from a saved file. It is authoritative:
    the lint never flags or rewrites it.
  - **external feed** (e.g. a calendar's "Coming Events") — a read-only feed rebuilt wholesale each run,
    kept **distinct from file-derived deadlines**, and never `.proposed.md`-guarded as if human-authored.
    An empty, stale or blocked read must **never blank it** — leave the prior version and note the gap.
- **Sensitive identifiers, last-4 only.** Record passport / account / licence / card numbers as the last 4
  digits only, never in full — on every page, in every table.
- **Deadlines are derived, not authored.** Record the date on the page that owns it; build the Deadlines
  list from those, and keep it distinct from any calendar feed.
- **A wiki is self-contained.** Keep a wiki about *its own folder* — don't name or link another project
  from it. If your setup maintains a separate cross-folder or user-level wiki, that is the only place
  cross-references live, and it only ever reads project wikis — it never writes back into them.

## Surfacing what needs a human — precise and quiet

- **State only what the source says, exactly.** Quote the specific figure/status; never round up,
  generalise, or infer beyond the document. If a status page shows *Drive 1 Bad, Drive 2 Good*, say that —
  never "both drives bad". If unsure of a detail, leave it out.
- **A true action is rare.** Treat something as an action only if it genuinely needs the owner to *do*
  something soon **and** is clearly relevant. A filing summary, an FYI, or a figure from a statement is
  informational — it shouldn't interrupt. When in doubt, inform quietly or say nothing.
