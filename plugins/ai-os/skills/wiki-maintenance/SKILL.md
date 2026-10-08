---
name: wiki-maintenance
description: >-
  How to maintain an in-folder knowledge wiki — a synthesised, always-current layer over a folder of
  real files. Process an incoming item end to end (read, file by confident match, update the pages it
  touches, surface what needs a human, log it), answer queries from the wiki, and run periodic
  reconcile (lint) passes. The method is the point; the wiki's own Schema page is the authority for its exact pages and
  layout. If a wiki doesn't exist yet, use wiki-onboarding first to create the Schema/Index/Log skeleton.
  Home of the core wiki rule: sections by responsibility, one professional per page, a page contract for every page
  type, a rationale and an acceptance for every page, and rich pages drawn from cited data.
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
- the wiki's **rationale** (`_Audit/wiki-rationale.md`) and its **acceptance record**
  (`_Audit/wiki-acceptance.json`, or as the deployment names it), beside the audit pair (see
  [the core wiki rule](#the-core-wiki-rule)).

Everything else at the root is the owner's source material. The ingest boundary is an exclusion: read
everything except the system-owned names.

**Anything an AI writes lands in the wiki or an outputs tier, never beside the sources.** A summary, a
dashboard or a session instruction file left next to the documents it describes is a stray; an ingest
that finds one files it into the wiki and logs the move.

**The one exception is an owner confirmation record, because it is not an AI artefact.** Some facts
exist only because the owner said so: "the deposit came back in cash; no letter is coming". When the
owner states such a fact about a matter whose documents sit in the folder, the deployment's capture
surface writes it **into that matter's folder**, beside the documents it settles. It is a dated,
attributed Markdown file that carries the owner's words verbatim and is named so the deployment can
recognise it by its name alone (for example `2026-03-14 Owner confirmation - Deposit returned.md`).
The words are the owner's, so the record is a **source**: read and cited like any document in the
folder. No job writes, edits, renames, moves, files or sweeps one, and an ingest never treats one as a
stray. Only the capture surface writes them, on the owner's explicit statement. The deployment's code
holds those rules ([the three layers](../../ARCHITECTURE.md#the-three-layers-of-a-job)). This is what
keeps the folder the golden source when the owner settles something by saying it: a fact kept only in
the wiki is a fact the folder does not know, so the next job that reads the folder asks again. When no
folder fits the statement, it stays a wiki-only `manual` note (see *Provenance always*). A user vault's
synthesis reads the records of every project its identity may access
([`user-synthesis`](../project-onboarding/archetypes/user-synthesis/README.md#owner-confirmation-records)),
so a fact settled in a project folder also settles it in the second brain.

## The recommended layout (an example — the Schema is the law)

When a wiki is created from scratch, a **human-readable, numbered-section** layout works well: one
folder per section, each section an area of responsibility as the office running these affairs would
divide them ([sections by responsibility](#sections-by-responsibility)), following the owner's *own*
top-level folders wherever they already divide things that way, so the wiki reads the way a person
thinks about their affairs rather than as an abstract index. A typical shape:

```
<wiki>/
├── 00 Index        master table of contents + a "what needs attention" dashboard (read first)
├── 01 Deadlines    derived list of forward dates (+ a calendar feed, if there is one)
├── 02 People       overview note + one page per person
├── 03 Property     overview note + one page per property
├── 04 Finance      Recurring Bills, Investments, …
│   …
├── 90 Schema       the wiki's constitution: layout, routing, page contracts and professionals
└── 91 Log          append-only history
```

Conventions that make it readable: number prefixes drive sidebar ordering (in Obsidian, put each page
in a folder of the same name so the root sorts numerically); each section folder has an **overview note**
of the same name plus **one detail page per item**; a section exists only because the owner has files for
it — never invent a taxonomy the material doesn't have. The meta pages sit at high numbers (9x) so
content owns the 00–89 range: a wiki that works will grow sections, and Schema and Log should never need
renaming to stay last.

**This is a recommended default, not a law.** The authority for *this* wiki's exact names and layout is
its **Schema page** — maintain the wiki in the structure the Schema declares, and write into the sections
that already exist rather than imposing a different shape. (No wiki/Schema yet? Use **wiki-onboarding** to
create one.)

## Each page declares its own fields and triggers — the Schema page

A wiki's **Schema page** is its constitution: for every section it records the **purpose**, the
**page contract** (its reader, the questions it answers in priority order, and the fields it carries)
and the **source documents that trigger an update**, and for every page its **professional**. The
trigger list is the routing: which page a given kind of source touches. It's the authority when you design or audit the
wiki, and you extend it whenever you add a page or a field.

A page's contract is small and explicit. For a person page, its fields might be identity documents
(with dates and **full, source-supported** numbers), status, key dates and a pointer to the source
folder. Write enough on the page that the obvious question ("when does this expire?", "what's the
latest figure?") is answered from the wiki without opening the source. When you route an incoming
source, match it to the right existing section/page using the Schema's trigger table; if you can't see
the Schema body, route from the section/page names you do have plus the source itself.

The Schema's layout, routing, page contracts and page professionals are tables with fixed headers,
compiled into a machine-readable twin; the format, the twin and its staleness rule are
[`pre-onboarding`'s settings reference](../pre-onboarding/references/settings.md). The Schema is the
authority; the twin is what code reads.

## The core wiki rule

How a wiki is divided, written and accepted is one rule, the same whether the wiki is being prepared,
onboarded or maintained. This section is its home: `wiki-onboarding` and `pre-onboarding` apply it, and
every maintenance pass keeps it.

### Sections by responsibility

Divide the wiki the way the office running these affairs would divide the work: one section per area
of responsibility (identity and residence, money, tax, the home, health, study), each the natural desk
of one or more professionals and each justified by files the owner actually has. A librarian, the
professional whose trade is arranging a collection, proposes the sections and the routing; the owner
agrees them before any page is written.

- **Mirror the owner's folders only where that does not break the division.** Where a top-level folder
  already is one responsibility, its section follows it. Where one folder mixes several
  responsibilities, or several folders serve one, the sections follow the responsibility and the
  Schema's routing maps each folder onto its section. The folders stay where they are: the wiki adapts
  to them, never the reverse.
- **A matter in two places has one home.** When the same matter is filed under two folders (a payslip
  kept with the tax papers and again with the job papers, a passport scan inside a travel pack), one
  page owns it, and the routing sends the other folder's copy to that page. A fact lives on one page;
  every other page that needs it links there.

### One professional per page

Every page is given **the one professional best suited to it**, chosen from
[the professional catalogue](references/professionals.md), or named for the matter where no row fits.
The librarian proposes each page's professional and the owner agrees. That professional:

- **sets the page's voice**: the page reads as the deliverable they would hand the owner (a tax
  adviser's position letter, a private banker's accounts schedule), in their tone;
- **sets its first questions**: the page answers first what they would answer first, and those
  questions become its contract's questions.

The voice is **tone only**. Facts, sources, identifiers, provenance, frontmatter and the format rules
are the same whoever the page speaks as, and a professional adds no fact the sources do not hold except
as labelled outside knowledge (below). A section may have several professionals, but a page has exactly
one: where a section names several, each of its pages names its own in the Schema, and no page gets a
blend of voices.

### A page contract for every page type

Every section (a page type: the pages of a section share its contract) has a **page contract** in the
Schema before its first page is written, drafted by its professional with the owner: **who reads it**, the **questions
they need answered, most important first**, and the **fields every page of the type carries**. The
page answers its questions in that order, the first in its opening lines
([page anatomy](#page-anatomy-and-evidence)), and a required field with no evidence shows as **not on
file**. Sections the Schema's layout marks `fixed` (the meta pages,
and a People section kept as the alias table) take the shapes this skill and `wiki-onboarding` give
them, so their contract is the method's; every other section has its own in the Schema.

Contracts are the rule for every wiki; **deterministic rendering stays an optional profile**. A contract
says what a page must answer, not how the page is produced: a page the reasoning step writes as ordinary
body text and a page rendered from structured facts both meet their contract. The rendering profile
adds its own declarations on top ([below](#deterministic-rendering-optional-profile)).

### Outside knowledge and dated rules

A professional knows more than the folder holds: the usual filing date, what an allowance is, when a
document must be renewed. That is **outside knowledge**, and the page labels it as such (for example a
line opening *General rule, not from the folder's documents:*), keeps it apart from what the documents
say, and never lets it fill a row that cites a document or stand in for a missing record.

A **dated rule** (a rate, threshold, allowance, fee or deadline that changes by year or by law) is
checked against the official source, the issuing authority's own publication, before it is written.
The page names that source and the date of the check; a rule that could not be checked is flagged as
unchecked, never stated as fact. Recheck a dated rule once the period it was checked for has passed.

### Rich pages

A page shows its data in the form its professional would use:

- **tables for records**: one row per document, account, policy, person or event, with its source;
- **charts for series and shares**: a line or bar chart for a value across dates or periods, a pie for
  how a whole divides;
- **timelines for histories and validity periods**: a timeline for a matter's dated events, a gantt bar
  for how long a document, lease, policy or contract runs.

Every visual is drawn from **the page's own cited data**: the table it comes from sits beside it on
the page, each row with its source, and the visual shows nothing the table does not. It is **rendered by
a tool, never written by hand**: a deterministic renderer turns the table into the chart block (in a
prepared folder, `pre-onboarding`'s `wiki.py chart`), so the same data always gives the same block. Where
the data cannot support a visual (a series of fewer than three points, units or currencies mixed with no
policy, events without dates), or no renderer is at hand, the page keeps the table or a sentence and
draws nothing. Which chart kinds and callout types render in which editor, and any editor setting they
need, is recorded once in `productivity:portable-markdown` ("Charts and callouts"); a page uses only what
it lists, and the table beside every chart is what keeps the page whole where a chart does not draw.

### History pages

A section the Schema's layout marks `history` holds closed matters, ingested once as history rather
than watched for change. A history page opens with what the matter was, its dates and how it ended;
then the records that mattered, as a table, and a timeline where the events are dated. It closes with a
**coverage table**, one row per source folder the matter used: the folder's path in backticks, its file
count and what it holds. Coverage is how a history page accounts for every document without naming
each: a run of readings, slides or copies is covered by its folder's row, while a document that decided
something is named by its own path.

### The rationale block

Every page has one **rationale block** in `_Audit/wiki-rationale.md`, in the audit tier rather than on
the page, so the page stays its professional's deliverable. The file opens with `# Wiki rationale`; each
block is headed `### <page path>`, relative to the wiki folder, and has exactly five lines:

```markdown
### 20 Finance/Tax.md
- Reader and use: Alex, checking what is due and what was filed.
- Professional lens: chartered tax adviser; questions answered in order: 1. is anything due 2. what is the tax position
- Shape: a one-line position, then one row per tax year with its source
- Changed from the previous page: first version
- Left out or flagged: nothing
```

1. **Reader and use**: who reads the page, and what for.
2. **Professional lens**: the page's one professional, then the contract's questions, numbered in the
   order the page answers them.
3. **Shape**: the page's structure and visuals and why, or "as the Schema sets out".
4. **Changed from the previous page**: what this version changed, or "first version".
5. **Left out or flagged**: what was left out and why, and what was flagged for the owner, or "nothing".

Whoever writes a page writes its block. A pass that changes a page's shape, contract or professional
rewrites the block, line 4 saying what changed; an ingest that only integrates a fact into the page's
existing structure leaves it as it is. A page with no block is a finding.

### Acceptance

Before a page is first handed to the owner, it is accepted in two lenses: **the owner's** (can the
owner answer their real questions from it, in the order they ask them, and act on what it says?) and
**its professional's** (does it meet its contract, do a sample of its facts match their sources, does
it stay in scope?). Both are played by **a model that did not write the page**, so no page is marked by
its author. Record each verdict with the models that wrote and reviewed the page; a verdict whose
reviewer is its author is refused, a guard the recording tool or the deployment holds rather than this
prose. Keep each finding with a response to it, rebuild the affected pages and review them again, and
review parent and Index pages last, against their children. Acceptance is reported as its own state
(accepted, not recorded or refused), never folded into a passing check. A page is accepted again after
a change to its anatomy, contract or professional. The procedure is `wiki-onboarding`'s reader
acceptance step.

### Maintenance keeps each page's professional

Every later pass writes a page as its professional and to its contract: an ingest puts a new fact where
that professional would put it, in their words, and a reconcile that folds or corrects keeps the voice.
A page created during maintenance gets its professional, and a contract if it opens a new section, in
the Schema before it is written; a pass that cannot take them from the Schema proposes the page rather
than inventing either. Changing a page's professional or contract is a Schema change the owner
agrees; the page's rationale block records it and the page is accepted again. No pass blends two voices
on one page or lets a page slide back into generic prose.

### The rule in a user vault

A type-1 user vault ([`ARCHITECTURE.md`](../../ARCHITECTURE.md#the-type-1-user-vault)) keeps the rule
**per page kind**, not per page: its pages are born in unattended synthesis runs, so no owner can agree
each page's professional before it is written. The vault's `09 Schema` names its page kinds, each with
one contract, and for each kind either fixes the professional or delegates the choice to the page; a
page the synthesis writes declares its kind in frontmatter (`kind:`), and a page of a delegating kind
its professional too (`professional:`), and is written as that professional, to its kind's contract.
The rule, its keys and its counts are over the pages the synthesis writes (`00 Index/`, `01
Knowledge/`); the owner-authored Ideas and the Reports carry no kind. Sections by responsibility does not apply: the
vault's areas are fixed, and its Knowledge tree emerges by theme and entity from the project wikis it
reads. The rationale file and the acceptance record live in `_Audit/` at the vault root, written by the
deployment from what the synthesis returns. Which kinds there are, who proposes them and when a page is
accepted are [`user-onboarding`'s](../user-onboarding/SKILL.md#3-scaffold-the-type-1-skeleton).

## Page anatomy and evidence

Every page is a briefing that answers its contract. A useful briefing begins with identity, status
and next action in its first five body lines. Then set out required key facts, dated events, records
on file, actions, record gaps and coming dates, with an optional reader-specific assessment. The
Schema chooses applicable sections and labels; it need not impose one generic checklist on every
subject. Show missing required rows as **not on file**.
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

### Identifiers, series and derived views

The default identifier policy is `stated`: full wherever supported by evidence. An explicit owner
restriction may choose `last-four` or `home-only` (full at the subject's home). Under the rendering
profile, store typed identifiers with holder, kind, home page, source and document status/dates.
Masked source values are unresolved suffixes, not full identifiers. A structural derivation needs a declared validator and the original source;
never guess from a suffix. Current, superseded and expired documents remain distinct, so an old
passport does not create a new expiry action. Enrichment evidence and guards follow the architecture;
test dates, decimal amounts, year prefixes, chart data and cited filenames as exclusions.

A Schema may declare a **series** field: subject, metric, unit, observation date, value and source.
Keep distinct periods or components from one document distinct; deduplicate the same observation.
Extract stated values faithfully; label computations separately with their input evidence and policy.
Reject impossible readings with a recorded reason rather than allowing them into totals. Every
cross-page row carries its date and freshness status, using Schema thresholds. Never combine dates,
currencies or units without an explicit policy; show a missing policy instead of assuming one. A declared
series is charted only while it is declared live; other cited tables follow [rich pages](#rich-pages). Assessments
may follow the reader's perspective, but parent summaries must agree with children or identify the
conflicting evidence, and are generated after the children.

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
   retain the components as evidence, not additional spend. If the component relationship is only
   possible, label the resulting total provisional until checked; explicitly separate purchases
   remain distinct costs.
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
9. **VAT is net, gross or shown apart, never mixed.** Where documents carry VAT, state whether a table is
   net or gross of it and show the VAT as a column of its own rather than folded into either; a table does not
   mix net and gross rows. A credit note is a negative against the invoice it credits, never added as spend or
   counted as income. A net or gross figure a document does not state is a computation, labelled as one.

Name the **period convention** the table uses: the financial year, the VAT period or the tax year, with its
start and end dates, and never put two conventions in one total. Print the basis beneath every rendered
money table: period (and its convention), attribution, what was counted and excluded, whether amounts are net
or gross of VAT, and any matching or currency policy. Label whether it counts incurred costs or evidenced
payments; an invoice alone does not establish payment. A page and its folder note must use the same
basis for the same question. Show unresolved counting matches rather than presenting their total as
settled.

Citation-derived hubs (people, counterparties or another facet) are valid cross-cutting indexes, not
new filing homes. The Schema sets their inclusion threshold. Optional `entities` frontmatter may hold
facets deterministically derived from validated links and parties. Layout below a section, folder-note
conventions and ordering are Schema choices. Qualify ambiguous links by path; follow portable-markdown
for table escaping and the target editor's link conventions.

Index and deadline roll-ups exclude closed subjects, superseded documents and facts belonging to third
parties unless explicitly in scope. Deduplicate by fact identity, not by the number of pages citing it.

### Full content: subject-clinical

`subject-clinical` is the sole content-depth mode and the default for private wikis. Health pages
carry history, active conditions, treatment, dated encounters, measured values with units and printed
reference ranges, and the documented plan. Other subjects carry their complete relevant evidence.
The Schema declares each page's purpose and sources; clinical content and personal information may
also appear in relevant section notes, indexes, family summaries, roll-ups and other authorised pages.
There is no subject-page-only or existence/date ceiling. Summaries remain selective for relevance,
not because clinical substance is automatically suppressed. Do not invent diagnoses or care plans.

Remove the former `full`, `administration-only`, `dates-only` and `measurements-only` depth values
when migrating a Schema; use `subject-clinical` or omit the depth to take the default. Existing
`subject-clinical` contracts also change: their old outward ceiling no longer applies. Validate
unknown values rather than silently treating them as another mode. Re-read source records where
older pages contain only dates or measurements; a policy change cannot recover omitted facts.

This is a private-content policy, not an access grant. Keep identity/project access scoping and
explicit source exclusions at [context crossings](../../ARCHITECTURE.md#context-crossings-and-evidence-bearing-enrichment).
An owner-requested identifier restriction applies to entire records and their typed fields as well
as display text; the default `stated` policy preserves full identifiers throughout.

<a id="contract-driven-pages-optional-profile"></a>

## Deterministic rendering (optional profile)

Every page has a contract ([the core wiki rule](#a-page-contract-for-every-page-type)). A wiki may also
adopt **deterministic rendering** for some of its pages, which are then produced by the deployment's
renderer from structured facts rather than written as body text. (Before every page had a contract,
this profile was called *contract-driven pages*.) For those pages the Schema adds to the contract:
the evidence sources of each required lookup field, derived sections, history rules and permitted
action kinds. Assign each rendered page a declared render type, finer than its section. Jobs consume
the compiled twin of the contracts and report drift; the Schema remains the authority. Unknown types or missing contracts fail
for rendered pages, never fall back to generic prose. Pages outside the profile keep the ordinary body
output, still written to their contract and in their professional's voice.

The reasoning step returns structured `page_facts` when the deployment advertises this capability;
the deployment validates, stores and renders them. The optional field does not replace `body` for a
consumer that has not adopted it: templates request ordinary `body` in that case. A deployment must
implement the alternate path before enabling it. Durable extraction and cache rules live in
[the architecture](../../ARCHITECTURE.md#durable-extracts-for-rendered-wikis-opt-in).

- **Lookup rows come from extracts** for identifiers, figures, dates and statuses; owner assertions
  and deterministic calendars take their declared precedence. Narrative cannot override those rows.
- **Owner overlays** are separate dated records: page, asserted fields/status, note, date and speaker.
  They do not add a new page-provenance enum. Render their authority visibly, preserve them across
  rebuilds, and supply them to permitted context. Suppress only actions explicitly settled by the
  assertion. Retire an overlay only when a later source confirms it; record contradictions for the
  owner under the existing manual-provenance rule. Model jobs cannot author owner overlays.

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
2. **File it** into the owner's folders by confident match, under an **existing** top-level folder and
   into a folder that already exists wherever one fits, with a **descriptive, renamed filename** (rename a meaningless `Scanned Document.pdf` to something like
   `Finance/Bills/<provider> Statement 2026-05-27.pdf`), keeping the extension. **Never create a new
   top-level folder.** Anything you can't place confidently stays put and is flagged for review.
   An item that seems to belong to another project is still filed or flagged here (see *Rules that
   keep it safe*).
   **On a filename collision, compare content before renaming:** hash the inbox item against the file
   already at the destination (file-preprocessing keys its whole manifest on content hashes for exactly
   this reason). Identical bytes are a duplicate, not a filing problem — don't file it; log it as a
   duplicate and route it to deletion/review. Only different content behind the same natural name earns
   the non-colliding rename.
   **When the destination folder seems missing**, check its siblings for the folder the local convention
   actually predicts (country vs city names, year prefixes) before deciding it is missing — the right
   folder usually exists under a different convention than the source suggests. If a folder genuinely
   must be created below an existing top-level folder, the deployment's write contract decides who
   creates it ([the three layers](../../ARCHITECTURE.md#the-three-layers-of-a-job)), and the deployment
   says which in the instructions it gives the agent. Where they say it creates folders itself under its
   own deterministic guards (a bounded depth, every new name checked, a half-built path undone), name the
   full destination and file into it: the deployment creates the folder, and asking the owner to make one
   the system can make is a chore with no reason. Where they say nothing, assume no such guard: escalate
   *with the proposed path* as a one-click decision for the owner, never a bare report of absence. Either
   way, never a new top-level folder.
3. **Update the pages the source touches — by integrating, never accreting.** Use the Schema's trigger
   table to pick the page(s), then the section on each page the fact belongs to, and put it where the
   page already tracks it: the row in the table that holds its kind, the list it extends, the field or
   line it supersedes — correcting that line, not stacking the newer statement beside it. A source does
   not earn a page, or a section, of its own: **synthesise into the existing page first**, and create a
   page only when no existing page covers the topic, placed where it fits in the layout. Where its
   section has a contract and names one professional, the page takes them; otherwise (a section naming
   several professionals, or a page needing a new section) the pass proposes the page for review, naming
   its professional, and writes it only once the owner agrees the Schema entry. Write as the page's professional,
   to its contract ([the core wiki rule](#the-core-wiki-rule)). **Never open a
   heading named for the run, its date or the batch** (`## <date> ingest`, `## Documents added`): it
   strands the facts below the sections they belong to, where the page's own tables and summaries never
   learn them. Date the fact, not the section — a heading that dates an *event* is structure, and the
   Log is the one page whose entries are run-dated. Integration needs the page in view, since an edit
   made without reading a page can add to it but never correct it. So for every existing page its
   ingest step may write, a deployment gives it either the **whole page** (or a way to read it) or a
   **section-level addition** — a fact landing at the end of a named section, with each page's
   headings listed verbatim, able to set the page's frontmatter too — which places the fact and leaves
   the correction of any line it contradicts to the next pass that sees the page whole. The model can
   only decline to rewrite a page it has not seen, never repair a missing capability, so a page the
   deployment can neither show nor extend keeps its sources back until it can. An edit that can only
   land at a page's end is accretion by construction. Add a provenance link down to the source file. **If the source carries a forward-looking
   date** (renewal, payment, expiry, deadline), record it as `deadline: YYYY-MM-DD` (or a `deadlines:`
   list) in **that page's** frontmatter, and a date that comes round every year (a renewal day, a
   filing date) in its `recurring:` list. If your setup has a deterministic step that rolls those dates
   into a Deadlines page, don't hand-write that page — let the roll-up build it; otherwise update the
   Deadlines list yourself from the page dates. One item typically touches a handful of pages — and the
   Index counts among them whenever the item changes anything the Index carries (the urgent list, a key
   fact, an open question).
4. **Surface what needs a human** — precise and quiet (see *Surfacing*, below).
5. **Log it.** Append one dated line: `## [YYYY-MM-DD] <action> | <short summary>`.

**Authored notes — free text with no source document.** An inbox item that is the owner's own words
(an idea, a brainstorm, a decision) rather than a document to file is an **authored note**: route it
to the section the Schema declares for authored content (e.g. an *Ideas* section), mark the page or
block `provenance: manual`, and treat its content as authoritative from then on. Carry the owner's
text **verbatim** as the note body — synthesis may add a title, date and links around it, never
replace it: the wiki page becomes the only copy of the owner's words once the inbox item is drained.
There is nothing to file in step 2 — the note's home *is* the wiki page. A statement of **fact** about a
matter whose documents sit in the folder is not an authored note: it is an owner confirmation record
(see [the shape of a folder](#the-shape-of-a-folder)), a source rather than a page.

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
claims a newer source supersedes, orphan pages, missing sections, data gaps, and pages that have
drifted from their contract or their professional's voice; refresh the Index (most-urgent,
open-questions, key-facts); record the pass in the log.

**Fold back what an ingest accreted.** On a page seen **whole**, a section is an ingest run's container
— facts that missed their sections (step 3 of the core loop) — only on affirmative evidence: its
heading names the ingest itself (the job's own name, usually with the run's date), **and** every fact
under it is of a kind one of the page's other sections already tracks. Any other heading, dated or
not, is the page's own structure and stays. Fold a container by moving each fact into its topical
section — the row into the table that tracks it, the bullet into its list — correcting any earlier
derived line it contradicts (never a `provenance: manual` one, nor a line an owner confirmation record
backs: owner assertions keep their precedence, and the disagreement stays visible), merging sections that
describe the same thing, and dropping the emptied container. Every citation and all manual content survive verbatim, and the fold is subject to
the shrink tripwire below like any other edit. A page seen only in part is never rewritten for this,
and is no finding: it waits for a pass that sees it whole.

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
- **Every page carries the core rule.** Count the sections with no page contract (`fixed` sections
  aside), the pages with no single professional, and the pages with no block in
  `_Audit/wiki-rationale.md`; report acceptance as its own state. A missing contract or professional
  is the owner's to agree, never invented by a pass to make the count zero.

Reconcile **never flags or rewrites
`provenance: manual` content** — that is owner-asserted and authoritative. Authored notes (ideas,
brainstorms) may be *merged or cross-linked* during a reconcile where they clearly belong together, but
their content and `provenance: manual` marking are preserved — consolidation never deletes or contradicts
what the owner asserted.

<a id="render-verification-for-contract-driven-pages"></a>

### Render verification (optional profile)

For a wiki that has adopted deterministic rendering, every render and reconcile publishes a dated
verification artefact (for example `_Audit/wiki-verify.json`) with page count, checked scope and counts
including zero: missing mandatory rows or undeclared types, stale/missing extracts, source citations,
broken links, malformed tables, identifier-policy violations and sync conflict copies. Missing or
unreadable inputs are findings, not clean checks; an absent report is **not verified**. Record checks
not performed explicitly rather than reporting zero. Use `productivity:portable-markdown` for table and
link mechanics. Visual outputs need an editor/theme check when introduced or changed; text lint cannot
establish chart legibility.

Check an "is not on file" claim against the page's own citations; deployments may enforce this
consistency check deterministically. Verification must not flag clinical substance or full,
evidence-supported identifiers merely because they occur outside a subject page. Report checks of
explicit owner restrictions separately from source-evidence and access checks.

Rendered pages are accepted like any other ([acceptance](#acceptance)); keep the review's findings
and the builder's responses beside the verification artefact.

## Cadence — ingest and reconcile

Two passes that differ in **scope**, not just schedule (the file-ingest archetype names them `ingest`
and `reconcile`):

- **Ingest** — incremental and **reactive**: drain the inbox, update the pages each new or changed
  source touches, append to the log. Cheap; run it often.
- **Reconcile** — comprehensive and **periodic**: reckon the whole wiki to the files — dedupe, sweep
  orphans, reconcile stale claims, fold accreted sections back, confirm the structure holds.

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
with no inline maintainer, the scheduled passes are the primary path. One thing an inline maintainer never
does is edit the wiki to match a fact the owner has only said. That fact goes to the deployment's
capture surface as an owner confirmation record, and ingest folds it in from there, so the wiki never
carries a fact the folder lacks.

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
  - **from an owner confirmation record** — `derived`, because the record is a file in the folder:
    the page cites it in `source:` like any document, and the lint reconciles the page against it. A
    record outranks the **absence** of a document. The matter it names is settled, so do not raise
    a missing document or chase evidence the record says will not come. A document that contradicts
    a record follows *Sources that disagree stay visible*: state both, keep the owner's precedence and
    ask the owner. Never silently prefer either. Where the fact belongs with a folder's documents,
    prefer a record to a `manual` note. A manual note lives only in the wiki, so the folder, which is
    the golden source, never learns the fact.
  - **external feed** (e.g. a calendar's "Coming Events") — a read-only view of an external source, kept
    **distinct from file-derived deadlines** and never `.proposed.md`-guarded as if human-authored. In
    the automated job framework it is **rendered deterministically** from the snapshot (a pure function
    of feed + clock, exactly like the Deadlines roll-up) — a scheduled job never rebuilds it; only a
    hand-kept wiki refreshes it manually. Either way an empty, stale or blocked read must **never blank
    it** — leave the prior version and note the gap.
- **Full identifiers by default.** Preserve passport, account, licence and card numbers exactly as
  supported by their sources, including in relevant summaries. Never reconstruct a full number from
  a masked suffix without the evidence required by the enrichment contract. An explicit owner
  restriction is recorded in the Schema and enforced by the deployment's crossing guard.
- **Private content is useful content.** Apply the `subject-clinical` policy above across relevant
  pages. Do not automatically suppress medical, legal or other personal substance. Explicit path
  exclusions, including credentials the owner excludes, still prevent those sources entering a job.
- **Deadlines are derived, not authored.** Record the date on the page that owns it; build the Deadlines
  list from those, and keep it distinct from any calendar feed. Recurring dates too: a date that comes
  round every year lives in its own page's `recurring:` list, never in a table kept by hand on the
  Deadlines page. A page the Schema marks `derived` (the Deadlines roll-up, an open-questions list built
  from the pages) holds nothing written by hand. **An empty roll-up must say why:** zero
  rows found while derived pages exist is a likely keying fault, rendered as a loud one-line banner on the
  Deadlines page (a quoted line in bold, `> **Roll-up found no frontmatter deadlines across N readable pages:
  likely a keying fault, not a deadline-free wiki.**`, then the sentence that says to record each date as a
  frontmatter key on the page that owns it), never a bare "None". A
  deployment's deterministic roll-up enforces this in code (prose can't hold it); a hand-kept wiki
  applies it by hand.
- **A project files within itself; the owner's synthesis proposes migrations.** Keep a wiki about *its
  own folder*: don't name or link another project from it. Every new item is filed inside this project
  by its own routing, and one that seems to belong elsewhere is filed or flagged here like any other;
  a project never routes an item to another project. Moving files between projects is a
  **migration**. While a folder is being prepared, a curation round (`folder-curation`) may stage one in
  the migrations folder through plan rows the owner approves, and the folder is onboarded only once that
  folder is empty. Once it is maintained, a file that belongs to another project stays filed here like
  any other, and the move is only suggested, by the owner's **user-tier synthesis**, the one place
  cross-references live (it reads project wikis and never writes back into them); the owner makes it by
  hand. No ingest or reconcile ever moves a file out of its project.

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
| `kind` | in a user vault, on every page the synthesis writes (`00 Index/`, `01 Knowledge/`) | a page kind the vault's `09 Schema` names ([the rule in a user vault](#the-rule-in-a-user-vault)) | the reconcile count of pages with no kind or no rationale block |
| `professional` | in a user vault, on a page whose kind delegates the choice | a catalogue row, or a professional named for the matter | the reconcile's voice check, which keeps it |
| `recurring` *(list)* | when a date comes round every year | `{date, note}`, the date as `MM-DD`, month first (`04-05` is 5 April), or a day and a month name (`5 April`, `April 5th`, `5 Sept`: the name in full, its first three letters or `sept`, in any case); never another numeric form (`6/4` reads either way round). Prefer the day and month name, which a reader who writes the day first (a UK reader) reads as written | the Deadlines roll-up, which shows it as a day and a month name, so a date written the wrong way round is visible |

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
