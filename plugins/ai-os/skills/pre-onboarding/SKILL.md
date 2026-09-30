---
name: pre-onboarding
description: >-
  Prepare a lived-in folder for onboarding onto an AI-OS deployment, in an interactive session: audit it, tidy it only
  through plans the owner approves, extract the full text of every document and write a summary card for each, build
  its wiki (sections by responsibility; every page written in the voice of the one professional best suited to it,
  against a page contract, with its rationale recorded and accepted by the owner and that professional through a
  model that did not write it), then check the folder meets the hand-off contract and hand it to
  project-onboarding. Ships the tools that do the deterministic work. Use when a person wants a folder they already
  keep made ready for the system; for a folder that is already tidy and has no wiki, project-onboarding alone is
  enough.
---

# pre-onboarding

A lived-in folder should reach the system already understood: every document read, the owner's rules written
down, a wiki the owner can use from day one, and nothing left for the maintenance jobs to guess. This skill is the
person's entry point for that preparation. It runs in an interactive session on the operator's machine, calls the
other skills as components, and uses the tools in [`tools/`](tools/) for everything that must be exact.

The components keep their own rules: [`folder-curation`](../folder-curation/SKILL.md) audits the folder and runs
the approved tidy-up rounds; this skill's own method extracts every document and cards it;
[`wiki-onboarding`](../wiki-onboarding/SKILL.md) builds the wiki under
[the core wiki rule](../wiki-maintenance/SKILL.md#the-core-wiki-rule), whose home is `wiki-maintenance`; and
[`project-onboarding`](../project-onboarding/SKILL.md) takes the prepared folder from there. This skill says in
what order they run, who decides at each point, and which tool does the exact part. Where a rule has a home
elsewhere, it links there rather than restating it.

## When to use

- The owner wants a folder they already keep made ready for the system, and a read-only look shows what years of
  filing leave behind: one subject in two homes, duplicate trees, strays at the root, scans with no text layer,
  working formats such as Pages or Numbers. Start here.
- The owner wants the wiki drafted from every document, read in full, before the system takes the folder over,
  rather than grown by the ingest job as files arrive.

**Go straight to `project-onboarding`** when the folder is already tidy (a read-only scan shows none of the
conditions that make `project-onboarding` stop for curation at its step 1) and the owner is content for the wiki
to start as a skeleton and fill as sources arrive; or when the folder already has a wiki with a Schema and needs
only its jobs.

Not for: a drop folder of files that belong to no project yet (`file-preprocessing`); a git repository (the `code`
archetype); keeping a wiki that already exists (`wiki-maintenance`).

## Before you start

- **The machine.** The operator's own machine, where the bulk engines are logged in ([engine
  isolation](#engine-isolation)). Local reading uses Apple Vision through a small helper you build once in the
  tools folder (`swiftc -O page_ocr.swift -o page-ocr`), poppler for PDFs, and, when installed, tesseract and
  LibreOffice. A tool that is missing is named in the records it would have read, never skipped silently. Ask the
  operator which engine and model each model lane uses (with `agy`, the effort is part of the model id).
- **The tools.** Run each as `python3 <tools>/<tool>.py`, where `<tools>` is this skill's `tools/` folder
  (standard-library Python 3.9 or later). Every tool takes `--root "<folder>"`; working state lives outside the
  folder, in the work directory, `<work>` below (`--work`, default `~/.ai-os-pre-onboarding/<folder name>`). The
  common flags, every command and every output are in the [tool reference](references/tools.md).
- **The isolation terms file.** The operator's list of names from other projects and people that must never reach
  this folder's cards: kept outside the folder, never committed, never shown to a model. Ask the operator for its
  path; its format is in [the card contract](references/cards.md#the-terms-file).
- **The owner is in the session.** Nothing in the owner's material changes without an approved plan row, and every
  structural choice in the wiki is the owner's to agree. Plan the session around the owner's decisions.

## The shape of a prepared folder

```
<Folder>/
  CLAUDE.md, AGENTS.md       the rulebook and its byte-identical copy
  .familyai/
    rulebook.json            the rulebook's machine-readable twin
    wiki-schema.json         compiled from the wiki's Schema page
  _Audit/
    manifest.json, AUDIT.md, summary.json
    plans/<YYYY-MM-DD>/      one folder per curation round (folder-curation's shape)
    extract/<id>.json        the full text of each document, page by page
    cards/<id>.json          one summary card per document
    wiki-rationale.md        one rationale block per wiki page
    wiki-acceptance.json     the acceptance verdicts
  _Inbox/                    the drop point the rulebook names
  _Migrations/<Project>/     files approved for another project, only while a migration is open
  <folder name> Wiki/        00 Index, 01 Deadlines, the numbered sections, 90 Schema, 91 Log
  <the owner's folders>      unchanged except by approved rows
```

Outside the folder, the work directory holds logs, caches, batches, queues, bundles and briefs; it is not part of
the hand-off.

## The method

Every step but the owner's decisions and the model reading is a tool, and every tool reports a count, zero
included, or a named not-verified state.

### 1. Audit

    python3 <tools>/audit.py --root "<folder>"

The hash-keyed manifest (`family-ai-preprocess-manifest/2`), `AUDIT.md` and `summary.json` in `_Audit/`, merged
with the manifest already there so history is kept. What the audit finds and why is
[`folder-curation` step 1](../folder-curation/SKILL.md#1-audit-deterministic-never-moves-anything). A file kept
only in the cloud stops the audit with a list: download it, or pass `--dataless read` to let the audit download it.
Show the owner `AUDIT.md` before asking anything.

### 2. Interview the owner; write the rulebook and its twin

Ask [`folder-curation`'s interview](../folder-curation/SKILL.md#2-interview-the-owner-a-fixed-ladder-one-pass), in
its order, and record every answer in the folder's rulebook, `CLAUDE.md`, with `AGENTS.md` a byte-identical copy.
In the same change, write `.familyai/rulebook.json` from the same answers and pin it: record the rulebook's
sha256 as `rulebook_sha256`, which says the twin was reviewed against it
([the format and pinning](references/settings.md#rulebookjson)). Two things the
[hand-off contract](#the-hand-off-contract) checks belong in the rulebook from the start:

- every name the system reserves at the top of the folder, `GEMINI.md` included, and every pack
  ([the list](references/settings.md#rulebookjson));
- new files are filed within this folder by the wiki's routing, never routed to the migrations folder: a file that
  seems to belong to another project is filed or flagged here, and moving it is the owner's user-tier synthesis to
  propose ([a project files within itself](../wiki-maintenance/SKILL.md#rules-that-keep-it-safe)).

Then run `settings.py check --root "<folder>"`. Until the wiki exists it reports `wiki-schema.json` as missing;
fix every other finding now.

### 3. Curation rounds, each approved by the owner

A round is [`folder-curation` steps 3 to 6](../folder-curation/SKILL.md#3-propose-the-only-model-step), carried
out by `plan.py` in a plan folder, `<folder>/_Audit/plans/<YYYY-MM-DD>/` (below `<plan folder>`, and `<plan>` its
`move-plan.csv`). Finish curating before step 4: an extract record carries the path it was read at.

1. **Propose.** `plan.py light --root "<folder>" --out "<plan folder>"` proposes the light-depth rows: root strays
   (their destination left for the owner), file and folder names with a space at either end or before the
   extension, and redundant copies outside any pack. Rows for a deeper depth the owner chose follow
   folder-curation's step 3, written in the same [plan format](../folder-curation/references/move-plan-schema.md);
   the executor runs `create`, `move`, `rename`, `rmdir` and `delete` rows, and fails an approved `convert` row
   (with the rest of its domain), so a conversion stays the owner's. To stage files for another project, list
   their paths in a file and run
   `plan.py migrate --root "<folder>" --project <Project> --paths-file <file> --out "<plan folder>"`;
   `plan.py return` brings staged files back.
2. **Show the owner the actual files.** Confirm a cross-project boundary with the files it moves, never with a
   description of them ([folder-curation step 2](../folder-curation/SKILL.md#2-interview-the-owner-a-fixed-ladder-one-pass)):
   the owner reads `review.tsv`, which lists every staged path with its copy kind and the copies that stay behind,
   and a `MISSING` line for each listed path the manifest does not know. Correct the paths file and propose the
   round again until the list is what the owner means.
3. **Approve.** The owner reads the plan domain by domain and chooses a destination for each stray; write it into
   that row's `to` column. Record each decision as it is made:
   `plan.py approve --plan <plan> --rows 1-5,7 --note "<what the owner said>"`, with `--decline` for a no. Then
   `plan.py rmdirs --root "<folder>" --plan <plan>` proposes an `rmdir` row for each top-most folder the approved
   moves empty; the owner approves or declines those too (the rulebook's `keep_empty_folders`).
4. **Dry run.** `plan.py check --root "<folder>" --plan <plan>`; fix or decline every row that fails.
5. **Execute.** Keep a copy of the manifest the round starts from (for example in
   `<work>/plans/<YYYY-MM-DD>/manifest.before.json`), then run `plan.py execute --root "<folder>" --plan <plan>`
   to print what would happen, and again with `--apply`. Nothing is unlinked: removed items go to the Bin, with an
   undo entry each ([`rmdir` and the Bin](../folder-curation/references/move-plan-schema.md#rmdir-and-the-bin)).
6. **Prove.** Re-audit (step 1), then
   `plan.py prove --plan <plan> --before <the copy> --after "<folder>/_Audit/manifest.json"`; it must print
   `"ok": true`. Once another project has collected the files staged for it, add
   `--allow-departed-under "_Migrations/<Project>/"`, so those departures are expected by name and nothing else
   is excused.
7. **Delete last.** Only after a clean proof:
   `plan.py execute --root "<folder>" --plan <plan> --phase deletes --apply`, then re-audit once more and check the
   deletes against the fresh manifest ([folder-curation step 6](../folder-curation/SKILL.md#6-verify-by-re-audit)).
8. **Expect another round.** Deleting redundant copies can make new ones: once copies leave, a folder shares a
   different proportion with its canonical home, and a working copy can become redundant
   ([folder-curation step 5](../folder-curation/SKILL.md#5-execute-deterministic-guards-not-judgement)). Propose
   what the re-audit shows as a new round, never folded into the one just run. Curation is done when a round's
   proof and delete check are clean and the owner wants nothing more at the depth they chose.

### 4. Extract the text

    python3 <tools>/extract.py --root "<folder>" --lane main --worker 0/4    (and 1/4, 2/4, 3/4 alongside)
    python3 <tools>/extract.py --root "<folder>" --lane apps

Each live document gets a record in `_Audit/extract/<id>.json` holding the text of every page and the tier that
read it: a PDF's text layer first, then local OCR, and last the model vision lane (step 6) for pages local OCR
could not read cleanly. Office files and plain text are parsed directly. The tiers, statuses and fields are in
[the tool reference](references/tools.md#extractpy). Run again with `--retry-failed` once the cause of a failed
record is fixed; to re-read a record after a later move, remove it and run `extract.py` again. Two lessons from
real folders:

- **iWork is read without the apps.** Pages, Numbers and Keynote documents are read by parsing the package itself
  (`iwa.py`), with its preview image as the fallback (the record is then `partial`). Never open an app or export a
  file to read it: an export is the owner's choice
  ([the class policy](../folder-curation/SKILL.md#class-policy-defaults-the-rulebook-may-override-per-folder)).
- **A text layer can be broken.** Some PDFs carry a text layer whose spaces decode as `)` or `!`, which reads as
  text but is not. The extractor detects it, discards the layer and OCRs the page, so trust the tier recorded per
  page, not the file type.

### 5. Open the gate to the engines

<!-- provisional: #92 -->

Before any model reads this folder:

    python3 <tools>/isolation.py scan   --terms <terms file> --path <tools> --path "<folder>/.familyai"
    python3 <tools>/isolation.py canary --terms <terms file> --engine agy --model <model> \
        --out <work>/state/canary-agy.json

`scan` checks every file a model will be shown (the tools' prompts and templates, and the settings the card
instructions are filled from) for the terms, and exits 1 on any hit; scan the wiki briefs the same way before
drafting (step 7). `canary` asks the engine to list every name in its context and fails on any term. Run it for
each engine you will use, and keep the result: it is the record that the gate ran. No tool reads it for you, so
never start a lane without a passing one. A failure means the engine's context carries another project: fix its
setup ([engine isolation](#engine-isolation)) and run the canary again.

### 6. The vision lane and the cards

<!-- provisional: #92 -->

    python3 <tools>/vision.py --root "<folder>" --model <vision model> \
        --lanes extract_main0,extract_main1,extract_main2,extract_main3,extract_apps0
    python3 <tools>/cards.py build --root "<folder>"
    python3 <tools>/cards.py work  --root "<folder>" --engine agy --model <model> --terms <terms file> [--worker 0/3]

The vision lane reads the page images queued in step 4 and exits once every extraction lane named in `--lanes`
has finished and its queue is empty. Then `cards.py build` plans batches from the finished records (run it again if
it reports records still waiting), and `cards.py work` has the engine write one card per document. What a card
holds, how the answers are joined to their documents and how each card is checked against the terms are
[the card contract](references/cards.md). A card that names a term its own document does not carry writes
`<work>/state/ALERT` and stops every worker: find where the term came from before you remove the file. A document
that could not be carded is listed as `<work>/state/card_err_<id>.txt`; list those ids in a file and run
`cards.py work` with `--redo <file>` once the cause is fixed.

**Prefer a deterministic repair to re-running a model.** When a card is wrong in a way its own source settles,
repair it with a tool: a re-run costs quota, and can break what was right. `refs.py --root "<folder>"` counts the
reference numbers cards cut short and how many it can restore; `--apply` restores each from the one number in the
document's own text that ends the same way, and writes the cards it could not settle to
`<work>/state/redo_refs.txt`, the only ones to send back:
`cards.py work ... --redo <work>/state/redo_refs.txt`. It runs only under the identifier policy `stated`
([identifiers](#identifiers)).

### 7. Build the wiki

The method is [`wiki-onboarding`](../wiki-onboarding/SKILL.md) under the core wiki rule; this is who holds the pen
at each stage, and the tool or brief for it. Each role is a model briefed as that role; the agent running the
session coordinates, and the owner decides.

<!-- provisional: #93 -->

| Stage | Who holds the pen | Brief or tool | Method |
| --- | --- | --- | --- |
| Readers: who reads the wiki, and what for | the owner, answering; the agent asks and records the answers in the owner's words | `readers-interview.md`, with `wiki.py profile` | [step 3](../wiki-onboarding/SKILL.md#3-interview--a-few-targeted-questions) |
| Sections and routing | the librarian proposes; the owner agrees | `structure-brief.md`, with `wiki.py profile` | [step 2](../wiki-onboarding/SKILL.md#2-propose-a-structure-the-librarians-sections-and-each-pages-professional) |
| Each page's professional | the librarian proposes; the owner agrees | `structure-brief.md` | step 2 |
| Each section's page contract | the section's professional drafts it; the owner agrees | `contract-brief.md` | [step 3a](../wiki-onboarding/SKILL.md#3a-page-contracts-for-every-page-type-drafted-by-its-professionals) |
| Each page | that professional writes it, as their deliverable to the owner, their client, in their own voice | `page-brief.md`, rendered by `wiki.py brief`; `wiki.py chart`; `wiki.py check` | [step 4a](../wiki-onboarding/SKILL.md#4a-draft-the-pages-when-every-document-has-been-read) |
| Acceptance | the owner's lens and the professional's, each played by a model that did not write the page | `review-owner.md`, `review-professional.md` | [step 6](../wiki-onboarding/SKILL.md#6-reader-acceptance-the-owners-lens-and-the-professionals) |

The briefs are templates in `tools/templates/`: to brief a role, fill the template's fields and give it to a model
in a fresh context (a subagent), then take the JSON it returns to the owner. The librarian picks each page's
professional from [the professional catalogue](../wiki-maintenance/references/professionals.md), as its note on
choosing says. The coordinator alone writes what sections share: the fixed pages (the Index, the Log, a People
alias table), the Deadlines roll-up from the pages' own frontmatter, and the rationale file from the blocks the
drafters return.

<!-- provisional: #93 -->
<!-- provisional: #94 -->

In order:

1. `wiki.py profile --root "<folder>" --out <work>/profile.json`: the folder's shape, per folder, for the readers
   interview and the librarian.
2. Hold the readers interview; brief the librarian with the readers' answers; agree the sections, routing and
   each page's professional with the owner. Create the wiki folder, `<folder name> Wiki/`, and its Schema page,
   `90 Schema/90 Schema.md`, as [wiki-onboarding step 4](../wiki-onboarding/SKILL.md#4-write-the-skeleton)
   describes it, with the agreed tables in the format
   [the settings reference](references/settings.md#the-schema-pages-tables) fixes. Then run
   `settings.py compile --root "<folder>"` and `settings.py check --root "<folder>"`.
3. `wiki.py bundles --root "<folder>"` routes every live document to its section's evidence bundle in the work
   directory. It lists what it cannot route and what has no card: fix the routing (edit the Schema, compile again)
   or card the document (step 6), until both lists are empty.
4. Brief each section's professional; agree each contract with the owner; add it to the Schema's Page contracts
   table; compile and check again (the check names any section, other than a `fixed` one, still without a
   contract).
5. Settle the page map: every page the wiki will hold, from the agreed layout and Page professionals table (`brief`
   lists it); no drafting agent adds, renames or merges a page. Then render a brief per group of pages:
   `wiki.py brief --root "<folder>" --page "<NN Section>/<Page>.md" [--page ...] --out <work>/briefs/<NN>.md`.
   Scan the briefs for the terms (step 5). Give each section to its own drafting agent, in a fresh context with
   only its brief; it writes its pages, draws charts with `wiki.py chart`, runs the checker command its brief
   names, and returns JSON.
6. Write the fixed pages, the Deadlines roll-up (`wiki.py check` lists every page's `deadlines:` as
   `[date, page]`) and `_Audit/wiki-rationale.md` from the returns (`wiki.py rationale` assembles the file). Then
   run `wiki.py check --root "<folder>"` over the whole wiki until it reports zero problems.
7. Accept every page in both lenses through a model that did not write it (another model or engine than the one
   that drafted it, named in the record), recording each verdict in
   `_Audit/wiki-acceptance.json` (`wiki.py review-prompts` and `wiki.py accept`); rebuild what the findings touch
   and review it again, children before parents and the Index last.

<!-- provisional: #93 -->

**Card bundles go stale after any migration.** A bundle records the manifest it was built from, and every
curation round ends in a re-audit that rewrites the manifest. After any round, rebuild the bundles, and run
`wiki.py drift --root "<folder>"` to list every page line that cites a path that has left or is leaving, before
drafting again; `brief` refuses stale bundles. To move a page, use `wiki.py move --root "<folder>" --map <file>`,
which rewrites every link to and from it.

### 8. Check readiness

    python3 <tools>/readiness.py --root "<folder>" --terms <terms file> --out <work>/readiness.json

The [hand-off contract](#the-hand-off-contract), checked. Fix what it names, in the step that owns it, and run it
again. Every item is a count or a named not-verified state, and some are reported without failing the run, so read
the whole report, not only the exit code.

### 9. Hand off

Tell the owner what was prepared (the rounds run, the documents read and carded, the pages accepted, anything
left open), then run [`project-onboarding`](../project-onboarding/SKILL.md) on the folder from its step 1. It finds
a wiki with a Schema, so it does not onboard one again, and an audit pair and rulebook, so it stamps the
folder-curation archetype's `audit` job beside the file-ingest pair. The wiki was built during preparation, and no
job runs on it until then ([wiki-onboarding step 5](../wiki-onboarding/SKILL.md#5-hand-off)).

## Engine isolation

<!-- provisional: #92 -->

- **One login per machine per engine**, shared by every project on the machine. Never copy a login or token file
  into a project's state: a copied token goes stale when the engine rotates it, and can log the main install out.
- **Context isolated per call.** Every call starts in a fresh, empty working directory, with the prompt on
  standard input, no tools (a tool use fails the call and its reply is discarded), no API keys in its environment,
  and its own process group, killed on timeout. The engine sees nothing from another project: no history,
  memories, sessions or instructions. A per-project state folder, where one is used, holds no credential file: it
  is scanned before and after every call, and one found there fails the call.
- **Named outcomes, never guesses.** A quota message whatever the exit code (with the reset time, where the
  message gives one, which the workers sleep until), an empty answer (`degenerate`), a tool use and an engine
  error are each named, and none is taken for an answer.
- **The gate before, the guard after.** The canary (step 5) before the first call, and the contamination check on
  every card.

<!-- provisional: #91 -->

The exact command-line flags each engine runs with are in `tools/engines.py`, and are set by the isolation spike
on the operator's machine; read them there rather than from this page.

## Identifiers

The identifier policy is `wiki-maintenance`'s
([identifiers](../wiki-maintenance/SKILL.md#identifiers-series-and-derived-views)); the owner's choice is recorded
as `identifiers` in `rulebook.json`. The preparation carries it wherever a model writes: the card instructions and
the page briefs state it, and `refs.py` refuses to restore numbers in full under any policy but `stated`.
Passwords and activation codes are never written, under any policy.

## The settings twins

The folder carries its rules in two human-written sources, the rulebook and the wiki's Schema page, and each has a
machine-readable twin in `.familyai/` that the tools and the deployment read: `rulebook.json`, written with the
rulebook, and `wiki-schema.json`, compiled from the Schema by `settings.py compile`. Each records its source's
hash, so an edited source makes its twin stale rather than silently wrong, and every tool refuses a stale twin.
Formats, the stale states and their remedies: [the settings reference](references/settings.md).

## The hand-off contract

<!-- provisional: #97 -->

What a deployment relies on when it onboards a prepared folder, and what `readiness.py` checks:

- **The manifest is current**, with its counts reported: live, departed and migrating entries, root strays,
  redundant copies, hygiene defects, unconverted iWork files.
- **Every live document has an extract record and a card**; each card's category is one the rulebook allows,
  each record's path agrees with the manifest, and no card names an isolation term its document does not carry.
- **The wiki** is at `<folder name> Wiki/`, with numbered sections and the fixed pages `00 Index`, `01 Deadlines`,
  `90 Schema` and `91 Log`, and `wiki.py check` reports zero problems (frontmatter, `sources:` lists and
  folder-relative backticked paths that exist, links, em dashes, coverage, charts, rationale blocks), with
  acceptance reported as its own state.
- **Derived pages hold nothing hand-written**: `01 Deadlines` and any open-questions list are built from the pages,
  and a date that recurs lives in its own page's frontmatter (`recurring:`), never in a table kept by hand
  ([deadlines are derived](../wiki-maintenance/SKILL.md#rules-that-keep-it-safe)).
- **The rulebook**: `CLAUDE.md` and `AGENTS.md` identical; naming the wiki folder; reserving the deployment's
  rulebook filenames, `GEMINI.md` included; filing new files within the folder and leaving migrations to the
  owner's user-tier synthesis.
- **The settings twins** present and fresh.
- **No scratch folders** left in `_Audit/`.

Which of these `readiness.py` reports today, and how, is in [the tool reference](references/tools.md#readinesspy).

## The tools

<!-- provisional: #93 -->
<!-- provisional: #94 -->

| Tool | Step | What it does |
| --- | --- | --- |
| `audit.py` | 1, 3 | the manifest, `AUDIT.md` and `summary.json` |
| `settings.py` | 2, 7 | compiles `wiki-schema.json`; checks both twins and the rulebook's facts |
| `plan.py` | 3 | curation rounds: `light`, `migrate`, `return`, `approve`, `rmdirs`, `check`, `execute`, `prove` |
| `extract.py` | 4 | full text per page, local tools only (with `iwa.py` and the `page-ocr` helper) |
| `isolation.py` | 5 | the terms scan and the per-engine canary |
| `vision.py` | 6 | the model vision lane for pages local OCR could not read |
| `cards.py` | 6 | one card per document; the whole-chunk join; the contamination guard |
| `refs.py` | 6 | restores truncated reference numbers from each card's own source |
| `wiki.py` | 7 | `profile`, `bundles`, `brief`, `chart`, `check`, `rationale`, `review-prompts`, `accept`, `move`, `drift` |
| `readiness.py` | 8 | the hand-off contract |
| `engines.py` | 5, 6 | the engine adapters every model call goes through |

Every flag, output and exit code: [the tool reference](references/tools.md).

## Principles

- **The owner decides; the tools carry it out.** Nothing in the owner's material moves without an approved row,
  and no section, routing, professional or contract is written into the Schema until the owner agrees it.
- **The folder carries its own settings.** The rulebook and its twins travel with the folder; the tools read the
  twins and refuse a stale one.
- **Guards in the tools, not in prompts.** Every write goes through one guarded writer; `--read-only-root` proves
  a tool against a real folder without changing it. A skill describes; code enforces
  ([the three layers](../../ARCHITECTURE.md#the-three-layers-of-a-job)).
- **Only understanding is a model call.** Hashing, routing, joining answers to documents, repairing what a source
  settles, rendering charts and checking are deterministic
  ([the determinism boundary](../../ARCHITECTURE.md#the-determinism-boundary)).
- **Counts, never silence.** Every check reports a count, zero included, or a named not-verified state; an alert
  stops every worker until someone reads it.
- **Working files stay outside the folder.** The work directory holds what the tools need along the way; the
  folder holds only what the deployment will read.
- **Nothing is permanently deleted.** Removed copies and emptied folders go to the Bin, each with its undo entry.
- **One writer per file.** A drafting agent writes only its own pages; what sections share is the coordinator's.
