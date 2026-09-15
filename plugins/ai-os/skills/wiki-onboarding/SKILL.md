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
Contracts, Invoices). The owner's own top-level folders are your draft domain map. If the scan shows
overlapping homes, duplicate trees or root strays, the folder needs **folder-curation** before a
Schema can route it; propose that first.

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
├── 90 Schema       the wiki's constitution — per-page purpose, fields, and update triggers
└── 91 Log          append-only history of what was ingested/changed
```

Number prefixes drive sidebar ordering (in Obsidian, putting each page in a folder of the same name
sorts the root numerically). The meta pages sit at high numbers (9x) so content owns the 00–89 range:
a wiki that works will grow domains, and Schema and Log should never need renaming to stay last.
This layout is the **recommended default, not a law** — adapt the domains
and names to the material, and record whatever you choose in the Schema (step 4). A small, honest
structure beats an elaborate one the material doesn't justify; only create a domain the owner actually
has files for.

**Time folders and topic folders.** Owners keep two shapes side by side: time-based folders (school
years, tax years, policy years) and topic folders that span years (a hobby, an adviser, an exam).
Documents get filed under both and duplicated across them. Mirror both in the wiki, but write the
routing rule down: dated documents route to the time folder; a topic folder is the home only for
matters that span several years. Record the rule in the Schema so every later pass files the same way.

### 3. Interview — a few targeted questions

Confirm the proposal and fill the gaps with **3–5 questions**, not a questionnaire. Aim for:

- **What will you ask this wiki?** The questions they expect to answer from it shape which pages and
  fields matter (e.g. "when does anything expire?", "what do we owe whom?").
- **What's sensitive?** How to handle identifiers and private data (a sound default: record account /
  document / licence numbers as the **last 4 digits only**, never in full). Record the answer where
  the deployment can *compile* it — paths excluded outright become the gate's exclude list, per-domain
  depths become the redaction guard's settings. An answer that lives only in prose is a preference a
  model is asked to honour, not a control.
- **Per domain, what triggers an update?** Which kind of incoming document touches which page — this
  becomes the Schema's routing table.
- **Cadence & conventions** — how often it's maintained, and any existing naming/structure to honour.

Four more the scan cannot guess, so they replace guesses rather than lengthening the questionnaire:

- **How do new files arrive today?** A scanner to the root, attachments saved into subfolders,
  batches from a desktop — this decides where the inbox goes.
- **Which folders are closed matters?** Ingested once as history and marked superseded, rather than
  watched for change.
- **Which formats are working formats**, and will they be converted?
- **Does anyone else write to the folder, and where have AI outputs already been written?** Those
  move to the wiki tier — see `wiki-maintenance`.

Propose, take their answers, and only then write. Never write the skeleton without the owner's nod.

### 3a. Page contracts, when adopting structured rendering

Ask who will read the wiki and what they need to decide. Record the identifier-policy rung and any
policy for combining currencies, dates or units; record an absent policy explicitly. For each page
type justified by the material, agree the reader's questions, professional perspective and evidence
fields with the owner, following `wiki-maintenance`'s contract profile. Put the contracts in the Schema
before writing those pages, and compile the machine-readable twin through the deployment's tooling.
Do not silently opt an existing wiki into a new renderer or impose case-specific fields.

### 4. Write the skeleton

Create the meta pages and the agreed domain pages:

- **Schema** — the constitution. For each page: its **purpose**, the **fields to maintain**, and the
  **source documents that trigger an update**. This is the durable artefact every maintenance pass
  follows; if you choose non-default names or layout, the Schema is where that is recorded and made
  authoritative. When retrofitting a Schema onto a wiki that already exists, enumerate what is actually
  there first — top-level files and folders, page counts, frontmatter conformance — and write the
  constitution to describe the country as found, not as remembered: a Schema that omits the bulk of the
  wiki is worse than none, because nothing ever notices.
- **Index** — the dashboard: a table of contents by section, a short "most urgent / needs attention"
  list, and an "open questions" list for known gaps.
- **Log** — append-only, one dated line per pass.
- **Domain pages** — an overview note per domain; leave detail pages to be filled as sources arrive
  (don't pre-invent empty pages). A People domain carries an **alias table**: every name, script and
  nickname a person appears under, so routing recognises the same person across languages and
  documents. Record it as a Schema field the trigger table consults.

Mark system-written pages so a maintenance pass knows it owns them (and a human edit is respected — see
wiki-maintenance's human-edit guard). Add provenance/freshness frontmatter to each page (`provenance`,
`source`, `last-updated`).

### 5. Hand off

Point the owner at **wiki-maintenance**: from here, each new source is filed and the pages it touches
are updated, all against the Schema you just wrote. Onboarding is one-time; maintenance is the ongoing
loop. For contract-driven pages, complete step 6 before handing the pages to the owner.

### 6. Reader acceptance

Before first hand-off of contract-driven pages, and after a regeneration changes their anatomy,
commission an independent reader review by a model that did not write them. Brief it with the agreed
reader and page contracts: what can the reader still not answer or do? Keep findings and a response to
each beside the render verification artefact, rebuild affected pages and recheck. Review parent and
Index pages last against their children. This is the acceptance loop described in
`coding:iterative-acceptance`; automated lint and reader judgement answer different questions.

## Principles

- **Propose, then confirm.** This skill is interactive by nature — never bootstrap a structure silently.
- **Read in place, never reorganise.** The owner's files stay exactly where they are; the wiki sits
  beside them and points at them.
- **The Schema is the deliverable.** Everything else (Index, Log, domains) follows from it; get it right
  and small.
- **Start minimal.** Better a tight structure that grows than an elaborate one that's mostly empty.
