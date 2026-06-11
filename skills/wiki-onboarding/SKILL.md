---
name: wiki-onboarding
description: >-
  Bootstrap an in-folder knowledge wiki for a folder that doesn't have one yet (or adopt an existing
  folder): scan the folder read-only, propose a structure that mirrors how the owner already organises
  it, interview the owner on a few key points, then write the initial skeleton — the Schema page (the
  wiki's constitution), the Index (dashboard), a Log, and the domain pages. Hand off to wiki-maintenance,
  which thereafter follows the Schema. Use this when there is no Schema/Index yet; if a wiki already
  exists, use wiki-maintenance instead.
---

# wiki-onboarding

A knowledge wiki is a synthesised, always-current layer over a folder of real files — you read one
page instead of scanning hundreds of documents. **wiki-maintenance** keeps such a wiki current but
assumes it already exists (specifically, that a **Schema page** defines what its pages are). This
skill creates that starting point: it produces the **Schema, Index, and Log** skeleton so maintenance
has something to follow.

It is an **interactive** skill — it proposes and asks before it writes. The output that matters is the
**Schema page**: a small constitution that every later maintenance pass refers to, so the structure
lives in the wiki itself and never has to be re-derived.

## When to use

- A folder of accumulated files has no wiki yet, and the owner wants one.
- You're adopting an existing folder and need to record its conventions as a Schema the system can follow.

If a Schema/Index already exists, don't re-onboard — switch to **wiki-maintenance** and follow it.

## The method

### 1. Scan the folder (read-only)

List the folder's top-level structure — the folders and notable files the owner already keeps. **Never
move or reorganise anything**; you are reading how they think, not imposing a system. Note the natural
domains (e.g. a person has folders like Finance, Property, Health, Travel; a business has Customers,
Contracts, Invoices). The owner's own top-level folders are your draft domain map.

### 2. Propose a structure

Default to a **human-readable, numbered-domain** layout — one folder per domain, mirroring the owner's
own folders, each with a short overview page (a "folder-note") plus per-item detail pages — because it
reads the way a person thinks about their affairs rather than as an abstract index. Always include a
small set of **fixed meta pages**:

```
<wiki>/
├── 00 Index        master table of contents + a "what needs attention" dashboard (read first)
├── 01 Deadlines    derived list of forward dates (+ a calendar feed if there is one)
├── NN <Domain>     one numbered folder per domain, each with an overview note + detail pages
│   …
├── 09 Schema       the wiki's constitution — per-page purpose, fields, and update triggers
└── 10 Log          append-only history of what was ingested/changed
```

Number prefixes drive sidebar ordering (in Obsidian, putting each page in a folder of the same name
sorts the root numerically). This layout is the **recommended default, not a law** — adapt the domains
and names to the material, and record whatever you choose in the Schema (step 4). A small, honest
structure beats an elaborate one the material doesn't justify; only create a domain the owner actually
has files for.

### 3. Interview — a few targeted questions

Confirm the proposal and fill the gaps with **3–5 questions**, not a questionnaire. Aim for:

- **What will you ask this wiki?** The questions they expect to answer from it shape which pages and
  fields matter (e.g. "when does anything expire?", "what do we owe whom?").
- **What's sensitive?** How to handle identifiers and private data (a sound default: record account /
  document / licence numbers as the **last 4 digits only**, never in full).
- **Per domain, what triggers an update?** Which kind of incoming document touches which page — this
  becomes the Schema's routing table.
- **Cadence & conventions** — how often it's maintained, and any existing naming/structure to honour.

Propose, take their answers, and only then write. Never write the skeleton without the owner's nod.

### 4. Write the skeleton

Create the meta pages and the agreed domain pages:

- **Schema** — the constitution. For each page: its **purpose**, the **fields to maintain**, and the
  **source documents that trigger an update**. This is the durable artefact every maintenance pass
  follows; if you choose non-default names or layout, the Schema is where that is recorded and made
  authoritative.
- **Index** — the dashboard: a table of contents by section, a short "most urgent / needs attention"
  list, and an "open questions" list for known gaps.
- **Log** — append-only, one dated line per pass.
- **Domain pages** — an overview note per domain; leave detail pages to be filled as sources arrive
  (don't pre-invent empty pages).

Mark system-written pages so a maintenance pass knows it owns them (and a human edit is respected — see
wiki-maintenance's human-edit guard). Add provenance/freshness frontmatter to each page (`provenance`,
`source`, `last-updated`).

### 5. Hand off

Point the owner at **wiki-maintenance**: from here, each new source is filed and the pages it touches
are updated, all against the Schema you just wrote. Onboarding is one-time; maintenance is the ongoing
loop.

## Principles

- **Propose, then confirm.** This skill is interactive by nature — never bootstrap a structure silently.
- **Read in place, never reorganise.** The owner's files stay exactly where they are; the wiki sits
  beside them and points at them.
- **The Schema is the deliverable.** Everything else (Index, Log, domains) follows from it; get it right
  and small.
- **Start minimal.** Better a tight structure that grows than an elaborate one that's mostly empty.
