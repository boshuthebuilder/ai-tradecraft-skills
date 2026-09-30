---
name: wiki-onboarding
description: >-
  Bootstrap an in-folder knowledge wiki for a folder that doesn't have one yet (or adopt an existing
  folder): sections by responsibility, a professional per page and a contract per page type, the
  Schema, Index and Log skeleton, and pages accepted by a model that did not write them; then hand off
  to wiki-maintenance. Use this when there is no Schema/Index yet; if a wiki already exists, use
  wiki-maintenance instead. To prepare a lived-in folder for the system, start at pre-onboarding.
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

In outline: scan the folder read-only; a librarian proposes sections by responsibility and the one
professional best suited to each page; interview the owner on a few key points; agree a page contract
for every page type, drafted by its professionals; write the skeleton (the Schema page, the Index
dashboard, a Log and the section pages) and, where every document has already been read, draft the
pages; accept each page in the owner's lens and its professional's, through a model that did not write
it; then hand off to **wiki-maintenance**, which thereafter follows the Schema.

How a wiki is divided, who writes each page and how a page is accepted is the **core wiki rule**, whose
one home is [`wiki-maintenance`](../wiki-maintenance/SKILL.md#the-core-wiki-rule). This skill applies it
to a new wiki: the steps below say when each part of the rule is decided and by whom, not what the rule
is.

## When to use

- A folder of accumulated files has no wiki yet, and the owner wants one.
- You're adopting an existing folder and need to record its conventions as a Schema the system can follow.
- As the wiki stage of **pre-onboarding**. A person preparing a lived-in folder for the system starts at
  [`pre-onboarding`](../pre-onboarding/SKILL.md), which runs this skill once the folder is curated and
  every document has been read and given a summary card. The wiki is then built during preparation, in
  the interactive session, and its pages are drafted from that evidence (step 4a).

If a Schema/Index already exists, don't re-onboard — switch to **wiki-maintenance** and follow it.

## The method

### 1. Scan the folder (read-only)

List the folder's top-level structure: the folders and notable files the owner already keeps. **Never
move or reorganise anything**; you are reading how they think, not imposing a system. Note the areas of
responsibility the material covers (e.g. a person's identity papers, money, tax, home, health, study; a
business's customers, contracts, invoices). The owner's own top-level folders are the first evidence of
those areas, not yet the section list. If the scan shows overlapping homes, duplicate trees or root
strays, the folder needs curation before a Schema can route it; propose that first, through
`pre-onboarding`, whose curation rounds follow **folder-curation**.

### 2. Propose a structure: the librarian's sections and each page's professional

A **librarian**, the professional whose trade is arranging a collection, reads the scan (and, in a
prepared folder, the audit and the document cards) and proposes three things together:

- **The sections**, one per area of responsibility, under the core rule's
  [sections by responsibility](../wiki-maintenance/SKILL.md#sections-by-responsibility).
- **The routing**: which of the owner's folders feed which section and page, so every folder the
  material uses maps onto a section. It becomes the Schema's routing table.
- **Each page's professional**: for every page, the one professional best suited to it, chosen from
  [the professional catalogue](../wiki-maintenance/references/professionals.md) under
  [one professional per page](../wiki-maintenance/SKILL.md#one-professional-per-page), or named for the
  matter where no row fits. Where a section has several professionals, name each page's own.

The owner agrees the sections, the routing and every page's professional before any page is written.

Default to a **human-readable, numbered-section** layout: one folder per section, each with a short
overview page (a "folder-note") plus per-item detail pages, because it reads the way a person thinks
about their affairs rather than as an abstract index. Always include a small set of **fixed meta pages**:

```
<wiki>/
├── 00 Index        master table of contents + a "what needs attention" dashboard (read first)
├── 01 Deadlines    derived list of forward dates (+ a calendar feed if there is one)
├── NN <Section>    one numbered folder per area of responsibility, each with an overview note + detail pages
│   …
├── 90 Schema       the wiki's constitution: layout, routing, page contracts and page professionals
└── 91 Log          append-only history of what was ingested/changed
```

Number prefixes drive sidebar ordering (in Obsidian, putting each page in a folder of the same name
sorts the root numerically). The meta pages sit at high numbers (9x) so content owns the 00–89 range:
a wiki that works will grow sections, and Schema and Log should never need renaming to stay last.
This layout is the **recommended default, not a law**: adapt the sections and names to the material,
and record whatever you choose in the Schema (step 4). A small, honest structure beats an elaborate one
the material doesn't justify; only create a section the owner actually has files for.

**The wiki folder's name is the deployment's `{wiki_dir}`**, the name every job template is given. Set
it once in the folder's configuration (in a prepared folder, `wiki_dir` in the rulebook's twin, whose
format is in [the settings reference](../pre-onboarding/references/settings.md)), list it among the
rulebook's reserved names, and let the checks confirm it: in a prepared folder the settings check and
the hand-off readiness check among the preparation tools in
[`pre-onboarding/tools/`](../pre-onboarding/tools/) both report a wiki folder that is not named
`<folder name> Wiki`. Never write the wiki under a name the configuration does not carry.

**Time folders and topic folders.** Owners keep two shapes side by side: time-based folders (school
years, tax years, policy years) and topic folders that span years (a hobby, an adviser, an exam).
Documents get filed under both and duplicated across them. Route both into their sections, and write
the rule for a document filed under both down: dated documents route with their time folder; a topic
folder is the home only for matters that span several years. Record the rule in the Schema's routing so
every later pass files the same way.

### 3. Interview — a few targeted questions

Confirm the proposal and fill the gaps with **3–5 questions**, not a questionnaire. Aim for:

- **What will you ask this wiki?** The questions they expect to answer from it shape which pages and
  fields matter (e.g. "when does anything expire?", "what do we owe whom?").
- **Any explicit exclusions?** Private content and full source-supported identifiers are included
  by default, following `wiki-maintenance`. Record any owner-requested identifier restriction or
  excluded source path in the Schema and compiled job config, where the deployment can enforce it.
- **Per section, what triggers an update?** Which kind of incoming document touches which page: the
  answers confirm or correct the librarian's routing table.
- **Cadence & conventions** — how often it's maintained, and any existing naming/structure to honour.

Four more the scan cannot guess, so they replace guesses rather than lengthening the questionnaire:

- **How do new files arrive today?** A scanner to the root, attachments saved into subfolders,
  batches from a desktop — this decides where the inbox goes.
- **Which folders are closed matters?** Ingested once as history and marked superseded, rather than
  watched for change.
- **Which formats are working formats**, and will they be converted?
- **Does anyone else write to the folder, and where have AI outputs already been written?** Those
  move to the wiki tier — see `wiki-maintenance`.

In a prepared folder the curation interview has already recorded several of these answers in the
folder's rulebook (how files arrive, closed matters, working formats, exclusions, where AI outputs sit).
Read them there and ask only what is still open.

Propose, take their answers, and only then write. Never write the skeleton without the owner's nod.

### 3a. Page contracts for every page type, drafted by its professionals

Every page type (a section: its pages share one contract) has its **page contract** in the Schema
before its first page is written. This is mandatory, following the core wiki rule in `wiki-maintenance`
([a page contract for every page type](../wiki-maintenance/SKILL.md#a-page-contract-for-every-page-type)).
Ask who will read the wiki and what they need to decide. Then, for each section the material
justifies, **its professional drafts the contract**: the model briefed as that professional starts
from the first questions of their catalogue row and proposes the reader, the questions in priority
order and the fields every page of the section carries, and the owner agrees or corrects it. Where a
section names several professionals, they draft its contract together, each owning the questions for
the pages they voice. Sections the layout marks `fixed` take the shapes the method gives them. Record
the identifier-policy rung and any policy for combining currencies, dates or units; record an absent
policy explicitly.

Put the layout, routing, page contracts and page professionals in the Schema's tables before writing
those pages, and compile the machine-readable twin through the deployment's tooling (the tables and the
twin are in [the settings reference](../pre-onboarding/references/settings.md); in a prepared folder
the settings check reports any section that is not `fixed` and has no contract). A contract says what a
page must answer, not how it is produced: do not silently opt an existing wiki into
[deterministic rendering](../wiki-maintenance/SKILL.md#deterministic-rendering-optional-profile), which
stays an optional profile, and do not impose case-specific fields.

### 4. Write the skeleton

Create the meta pages and the agreed section pages:

- **Schema**: the constitution. For each section: its **purpose**, its **contract** and the **source
  documents that trigger an update**; for each page, its **professional**. The layout, routing,
  contracts and page professionals go in the tables with fixed headers that the settings reference
  defines. This is the durable artefact every maintenance pass follows; if you choose non-default
  names or layout, the Schema is where that is recorded and made authoritative. When retrofitting a
  Schema onto a wiki that already exists, enumerate what is actually
  there first — top-level files and folders, page counts, frontmatter conformance — and write the
  constitution to describe the country as found, not as remembered: a Schema that omits the bulk of the
  wiki is worse than none, because nothing ever notices.
- **Index**, the dashboard: a table of contents by section, a short "most urgent / needs attention"
  list, and an "open questions" list for known gaps.
- **Log**: append-only, one dated line per pass.
- **Section pages**: an overview note per section. Leave detail pages to be filled as sources arrive
  (don't pre-invent empty pages), unless every document has already been read, when step 4a drafts
  them. A People section carries an **alias table**: every name, script and nickname a person appears
  under, so routing recognises the same person across languages and documents. Record it as a Schema
  field the trigger table consults.

Mark system-written pages so a maintenance pass knows it owns them (and a human edit is respected: see
wiki-maintenance's human-edit guard). Give each page `wiki-maintenance`'s canonical frontmatter
(`provenance`, `last-updated`, `status`, and `sources` on a page drawn from files), and give every page,
the meta pages included, its [rationale block](../wiki-maintenance/SKILL.md#the-rationale-block),
written by whoever writes the page.

### 4a. Draft the pages, when every document has been read

In a prepared folder every document already has its full text and a summary card, so the pages are
drafted now rather than left for sources to arrive. One coordinator, the agent running the session,
runs the drafting:

- **A fixed page map.** Before drafting starts, the coordinator fixes every page path the wiki will
  hold, from the agreed layout and page professionals. A drafting agent writes only its own pages on the
  map and links only to paths on it; none invents, renames or merges a page. A page the evidence shows
  is missing goes back to the coordinator as a proposal, and the map changes through the Schema.
- **Fresh bundles.** Each section's evidence is a bundle built from the cards by the Schema's compiled
  routing. The preparation tools list every document the routing cannot place or that has no card,
  and record the hash of the manifest the bundles were built from. Fix the routing, and card what has
  no card, until that list is empty; rebuild the bundles after any change to the manifest (a migration
  or a curation round above all), and draft only from bundles built from the current manifest: a stale
  bundle cites paths that have moved and misses files that arrived.
- **A persona brief per page.** Brief each page, not each section: its professional, deliverable and
  tone (resolved as
  [the settings reference](../pre-onboarding/references/settings.md#a-pages-professional) sets out),
  its contract (reader, questions in order, fields), the Schema's writing rules, the page map and its
  share of the bundle. The page is written as that professional's deliverable to the owner, under the
  core rule's [rich pages](../wiki-maintenance/SKILL.md#rich-pages) and
  [outside knowledge](../wiki-maintenance/SKILL.md#outside-knowledge-and-dated-rules).
- **Parallel agents.** Draft sections in parallel, one agent per section (or per group of pages in a
  large one), each in a fresh context holding only its briefs, its bundle and the map, so no agent
  carries another section's evidence or voice.
- **A checker every drafting agent runs.** Before it returns, each agent runs the deterministic wiki
  check among the preparation tools (frontmatter keys, source paths that exist, page links that
  resolve, em dashes, documents in scope that no page covers) and fixes every finding on its own pages.
  The coordinator runs the same check once every agent is back, when links between sections can
  resolve.
- **JSON returns; the coordinator writes the fixed pages.** An agent returns JSON, not prose: the pages
  it wrote, each page's rationale block, its Index entry, its open questions and its check result. Only
  the coordinator writes what sections share: the pages the layout marks `fixed` (the Index, the Log,
  a People alias table) from those returns, the derived Deadlines roll-up from the pages' own
  frontmatter rather than from any return's prose, and the rationale file from the returned blocks.

### 5. Hand off

Point the owner at **wiki-maintenance**: from here, each new source is filed and the pages it touches
are updated, all against the Schema you just wrote. Onboarding is one-time; maintenance is the ongoing
loop. Complete step 6 for every page before handing the pages to the owner.

**Built during preparation; jobs wait for onboarding.** As the wiki stage of `pre-onboarding`, the wiki
is built in the interactive session and handed over with the prepared folder, and no job runs on it
yet. The maintenance jobs are stamped when `project-onboarding` onboards the folder; until then only
the preparing session writes the wiki.

### 6. Reader acceptance: the owner's lens and the professional's

When a page is accepted, in which lenses and what a verdict records are the core rule's
[acceptance](../wiki-maintenance/SKILL.md#acceptance); this step is how to run it.

Commission the review from **a model that did not write the page**. Brief it with the agreed reader,
the page's contract and professional, the page and its sources, and have it answer in both lenses.
Write the verdict, with the models that wrote and reviewed the page, to the acceptance record beside
the audit pair (in a prepared folder, `_Audit/wiki-acceptance.json`, which the wiki check reports as
recorded or not), with each finding and the response to it. Rebuild what the findings touch and review
it again, children before parents and the Index last. This is the acceptance loop of
`coding:iterative-acceptance`; a passing check never stands in for it.

## Principles

- **Propose, then confirm.** This skill is interactive by nature: never bootstrap a structure silently.
- **Read in place, never reorganise.** The owner's files stay exactly where they are; the wiki sits
  beside them and points at them.
- **The Schema is the deliverable.** Everything else (Index, Log, sections) follows from it; get it
  right and small.
- **Start minimal.** Better a tight structure that grows than an elaborate one that's mostly empty.
- **One writer per file.** A drafting agent writes only its own pages; whatever sections share is the
  coordinator's to write.
