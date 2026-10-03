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
  filing leave behind: one subject in two homes, duplicate trees, strays at the root, scans with no text layer.
  Start here.
- The owner wants the wiki drafted from every document, read in full, before the system takes the folder over,
  rather than grown by the ingest job as files arrive.

**Go straight to `project-onboarding`** when the folder is already tidy (a read-only scan shows none of the
conditions that make `project-onboarding` stop for curation at its step 1) and the owner is content for the wiki
to start as a skeleton and fill as sources arrive; or when the folder already has a wiki with a Schema and needs
only its jobs.

Not for: a drop folder of files that belong to no project yet (`file-preprocessing`, which owns such files and
moves them into parcels, where this skill reads a kept folder in place); a git repository (the `code`
archetype); keeping a wiki that already exists (`wiki-maintenance`).

## Before you start

- **The machine.** The operator's own machine, where the bulk engines are logged in ([engine
  isolation](#engine-isolation)). Local reading uses Apple Vision through a small helper you build once in the
  tools folder (`swiftc -O page_ocr.swift -o page-ocr`), poppler for PDFs, and, when installed, tesseract and
  LibreOffice. A tool that is missing is named in the records it would have read, never skipped silently. Ask the
  operator which engine and model each of the three model lanes uses: the vision lane (`agy` only), the cards, and
  the wiki's drafting and review subagents (with `agy`, the effort is part of the model id).
- **The tools.** Run each as `python3 <tools>/<tool>.py`, where `<tools>` is this skill's `tools/` folder
  (standard-library Python 3.9 or later). Every tool takes `--root "<folder>"`; working state lives outside the
  folder, in the work directory, `<work>` below (`--work`, default `~/.ai-os-pre-onboarding/<folder name>`). The
  common flags, every command and every output are in the [tool reference](references/tools.md#common-flags).
- **The isolation terms file.** Every name that must never reach a model working on this folder: the people,
  organisations and places of the operator's other projects, and the operator's own identifiers from any other use
  of the engines. It is kept outside the folder, never committed and never shown to a model. Ask the operator for
  its path; its format is in [the card contract](references/cards.md#the-terms-file). Where there is genuinely
  nothing to list, step 5 says what runs instead.
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
  ([the list](references/settings.md#rulebookjson)); a pack listed in `rulebook.json` must be an existing folder,
  named exactly, or the audit and plan tools refuse to run;
- new files are filed within this folder by the wiki's routing, never routed to the migrations folder: a file that
  seems to belong to another project is filed or flagged here, and moving it is the owner's user-tier synthesis to
  propose ([a project files within itself](../wiki-maintenance/SKILL.md#rules-that-keep-it-safe)).

Then run `settings.py check --root "<folder>"`. Until the wiki exists it reports `wiki-schema.json` as missing;
fix every other finding now.

### 3. Curation rounds, each approved by the owner

A round is [`folder-curation` steps 3 to 6](../folder-curation/SKILL.md#3-propose-the-only-model-step), carried
out by `plan.py` in a plan folder, `<folder>/_Audit/plans/<YYYY-MM-DD>/` (below `<plan folder>`, and `<plan>` its
`move-plan.csv`). Finish curating before step 4 where you can: extract records and bundles carry the paths they
were built from. A round after that is repaired, never read again (*A round after extraction*, below).

1. **Propose.** `plan.py light --root "<folder>" --out "<plan folder>"` proposes the light-depth rows: root strays
   (their destination left for the owner), file and folder names with a space at either end or before the
   extension, and redundant copies outside any pack. Rows for a deeper depth the owner chose follow
   folder-curation's step 3, written in the same [plan format](../folder-curation/references/move-plan-schema.md);
   the executor runs `create`, `move`, `rename`, `rmdir` and `delete` rows, and names an approved `convert` row
   and leaves it pending, since a conversion stays the owner's. To stage files for another project, list their
   paths in a file and run
   `plan.py migrate --root "<folder>" --project <Project> --paths-file <file> --out "<plan folder>"`;
   `plan.py return` brings staged files back (`rmdirs`, below, proposes removing the folder it empties).
2. **Show the owner the actual files**
   ([a boundary is confirmed with its files](../folder-curation/SKILL.md#2-interview-the-owner-a-fixed-ladder-one-pass)).
   The owner reads `review.tsv`, which lists every staged path with its copy kind and the copies that stay behind,
   and a `MISSING` line for each listed path the manifest does not know. Correct the paths file and propose the
   round again until the list is what the owner means.
3. **Approve.** The owner reads the plan domain by domain and chooses a destination for each stray; write it into
   that row's `to` column ([the plan schema](../folder-curation/references/move-plan-schema.md)). Record each
   decision as it is made:
   `plan.py approve --plan <plan> --rows 1-5,7 --note "<what the owner said>"`, with `--decline` for a no and
   `--defer` for not this round. Then
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
   `plan.py execute --root "<folder>" --plan <plan> --phase deletes --apply`, then re-audit once more and run
   `prove` again on the same before-copy: it now takes each deleted copy's pair away too, and must still print
   `"ok": true`.
8. **Deleting redundant copies can make new ones**
   ([folder-curation step 5, *Expect a second round of redundancy*](../folder-curation/SKILL.md#5-execute-deterministic-guards-not-judgement)):
   propose what the re-audit shows as a new round. Curation is done when a round's proof and delete check are
   clean and the owner wants nothing more at the depth they chose.

**A round after extraction.** When a round has to run after step 4 (a migration found while the wiki is drafted,
say), repair what it moved rather than read anything again. Once the round's re-audit is proved,
`extract.py repath --root "<folder>"` lists each extract record whose path it would rewrite to its document's
current path, matched by content hash, with nothing read again; run it again with `--apply` to write them. It
refuses a move to a path that is not in the folder, so it runs only on a manifest the re-audit has made current
([`repath`](references/tools.md#repath)). Then rebuild the bundles and run `wiki.py drift` (step 7). Cards hold no
path, only their document's id, so they need nothing.

### 4. Extract the text

    python3 <tools>/extract.py --root "<folder>" --lane main --worker 0/4    (and 1/4, 2/4, 3/4 alongside)
    python3 <tools>/extract.py --root "<folder>" --lane apps

Each live document gets a record in `_Audit/extract/<id>.json` holding the text of every page and the tier that read
it: a PDF's text layer first, then local OCR, and last the model vision lane (step 6) for pages local OCR could not
read cleanly. Local OCR reads in the rulebook's `ocr_languages` (default `en-GB`): set them, at the interview, to the
languages the documents are written in, most likely first. Office files and plain text are parsed directly. The tiers,
statuses and fields are in [the tool reference](references/tools.md#extractpy). Run again with `--retry-failed` once
the cause of a failed record is fixed; a record is never read again to follow a move ([a round after
extraction](#3-curation-rounds-each-approved-by-the-owner)). Two lessons from real folders:

- **iWork is read without the apps.** Pages, Numbers and Keynote documents are read by parsing the package itself
  (`iwa.py`), with its preview image as the fallback (the record is then `partial`). Never open an app or export a
  file to read it: an export is the owner's choice
  ([the class policy](../folder-curation/SKILL.md#class-policy-defaults-the-rulebook-may-override-per-folder)).
- **A text layer can be broken.** Some PDFs carry a text layer whose spaces decode as `)` or `!`, which reads as
  text but is not. The extractor detects it, discards the layer and OCRs the page, so trust the tier recorded per
  page, not the file type.

### 5. Open the gate to the engines

Before any model reads this folder:

    python3 <tools>/isolation.py scan   --terms <terms file> --path <tools> --path "<folder>/.familyai" \
        --if-present ~/.codex/AGENTS.md --if-present ~/.codex/AGENTS.override.md --out <work>/state/scan.json
    python3 <tools>/isolation.py canary --terms <terms file> --engine <engine> --model <model> \
        --out <work>/state/canary-<engine>.json

`scan` checks every file a model will be shown (the tools' prompts and templates, and the settings the card
instructions are filled from) for the terms, and exits 1 on any hit or when it found nothing to check; scan the wiki
briefs and review prompts the same way before a model reads them (step 7). `canary` asks the engine to list every name
in its context and fails on any term. Run it for each engine you will use, and keep both results: they are the record
that the gate ran, and `readiness.py` reads each engine's canary from `<work>/state/canary-<engine>.json` (step 8).
No lane reads them, so never start one without passing ones. A failure means the engine's context carries another
project: fix its setup ([engine isolation](#engine-isolation)) and run the canary again.

**When there is nothing to list.** The gate needs a terms file, and an empty one is refused. Where the operator
genuinely has no name to keep out (no other project, and no other use of the engines), there is no file, and the
canary is not run: readiness reports each engine's canary as `not run`, a named not-verified state and never a
pass. Run the cards with `--no-isolation-terms`, which their log records, and readiness without `--terms`, which
reports the contamination check as not verified too. Tell the owner why.

### 6. The vision lane and the cards

    python3 <tools>/vision.py --root "<folder>" --model <vision model> \
        --lanes extract_main0,extract_main1,extract_main2,extract_main3,extract_apps0
    python3 <tools>/cards.py build --root "<folder>"
    python3 <tools>/cards.py work  --root "<folder>" --engine <engine> --model <model> --terms <terms file> \
        [--worker 0/3]

The vision lane, which runs on `agy` only, reads the page images queued in step 4 and exits once every extraction
lane named in `--lanes` has finished and its queue is empty. Then `cards.py build` plans batches from the finished
records (run it again if it reports records still waiting), and `cards.py work` has the engine write one card per
document. What a card holds, how the answers are joined to their documents and how each card is checked against
the terms are [the card contract](references/cards.md). A card that names a term its own document does not carry writes
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
session coordinates, and the owner decides. In a prepared folder the readers come first, before the librarian's
proposal that [wiki-onboarding step 2](../wiki-onboarding/SKILL.md#2-propose-a-structure-the-librarians-sections-and-each-pages-professional)
puts ahead of its interview: the cards and the profile already give the librarian the material, and the readers'
questions should shape the sections rather than confirm them. The questions of
[its step 3](../wiki-onboarding/SKILL.md#3-interview--a-few-targeted-questions) then confirm the proposal.

| Stage | Who holds the pen | Brief or tool | Method |
| --- | --- | --- | --- |
| Readers: who reads the wiki, and what for | the owner, answering; the agent asks and records the answers in the owner's words | `readers-interview.md`, with `wiki.py profile` | [step 3](../wiki-onboarding/SKILL.md#3-interview--a-few-targeted-questions) |
| Sections and routing | the librarian proposes; the owner agrees | `structure-brief.md`, with `wiki.py profile` | [step 2](../wiki-onboarding/SKILL.md#2-propose-a-structure-the-librarians-sections-and-each-pages-professional) |
| Each page's professional | the librarian proposes; the owner agrees | `structure-brief.md` | step 2 |
| Each section's page contract | the section's professional drafts it, or its professionals together where it has several; the owner agrees | `contract-brief.md` | [step 3a](../wiki-onboarding/SKILL.md#3a-page-contracts-for-every-page-type-drafted-by-its-professionals) |
| Each page | that professional writes it, as their deliverable to the owner, their client, in their own voice | `page-brief.md`, rendered by `wiki.py brief`; `wiki.py chart`; `wiki.py check` | [step 4a](../wiki-onboarding/SKILL.md#4a-draft-the-pages-when-every-document-has-been-read) |
| Acceptance | the owner's lens and the professional's, each played by a model that did not write the page | `review-owner.md`, `review-professional.md` | [step 6](../wiki-onboarding/SKILL.md#6-reader-acceptance-the-owners-lens-and-the-professionals) |

The briefs are templates in [`tools/templates/`](tools/templates/): to brief a role, fill the template's fields and
give it to a model in a fresh context (a subagent), then take the JSON it returns to the owner. The librarian picks
each page's professional from [the professional catalogue](../wiki-maintenance/references/professionals.md), as its
note on choosing says. What the sections share is the coordinator's to write
([step 4a](../wiki-onboarding/SKILL.md#4a-draft-the-pages-when-every-document-has-been-read), *JSON returns*).

In order:

1. `wiki.py profile --root "<folder>" --out <work>/profile.json`: the folder's shape, per folder, for the readers
   interview and the librarian.
2. Hold the readers interview; brief the librarian with the readers' answers; confirm the proposal with
   wiki-onboarding step 3's questions, asking only what the rulebook does not already answer; agree the sections,
   routing and each page's professional with the owner. Create the wiki folder, `<folder name> Wiki/`, and its
   Schema page, `90 Schema/90 Schema.md`, as
   [wiki-onboarding step 4](../wiki-onboarding/SKILL.md#4-write-the-skeleton) describes it, with the agreed tables
   in the format [the settings reference](references/settings.md#the-schema-pages-tables) fixes. Then run
   `settings.py compile --root "<folder>"` and `settings.py check --root "<folder>"`.
3. `wiki.py bundles --root "<folder>"` routes every live document to its section's evidence bundle, in
   `<work>/bundles` by default. It lists what it cannot route and what has no card: fix the routing (edit the
   Schema, compile again) or card the document (step 6), until both lists are empty.
4. Brief each section's professional, or all of a section's professionals together where it has several, to draft
   its contract; agree each contract with the owner; add it to the Schema's Page contracts table; compile and
   check again (the check names any section, other than a `fixed` one, still without a contract).
5. Render a brief per group of pages on the page map, which
   [step 4a](../wiki-onboarding/SKILL.md#4a-draft-the-pages-when-every-document-has-been-read) fixes before
   drafting starts (`brief` lists it):
   `wiki.py brief --root "<folder>" --page "<NN Section>/<Page>.md" [--page ...] --out <work>/briefs/<NN>.md`.
   Scan the briefs for the terms (step 5), then draft as step 4a sets out. Each drafting agent draws its charts
   with `wiki.py chart`, runs the checker command its brief names, and returns the JSON its brief shows: each
   page's text, rationale block and Index entry, its open questions and its check result. Keep each return as a
   file in `<work>/returns/`.
6. From the returns, write the fixed pages and the Deadlines roll-up (`wiki.py check` lists every page's
   `deadlines:` as `[date, page]`), and `wiki.py rationale --root "<folder>" --returns <work>/returns` writes
   `_Audit/wiki-rationale.md`. Then run `wiki.py check --root "<folder>"` over the whole wiki until it reports zero
   problems.
7. Accept every page as [wiki-onboarding step 6](../wiki-onboarding/SKILL.md#6-reader-acceptance-the-owners-lens-and-the-professionals)
   runs it and [the core rule's acceptance](../wiki-maintenance/SKILL.md#acceptance) sets it out, through a model
   other than the one that drafted it (below, `<A>` drafted the page and `<B>` reviews it).
   `wiki.py review-prompts --root "<folder>" --page "<page>" [--page ...] --author-model <A> --reviewer-model <B>`
   renders each page's owner and professional prompts in `<work>/reviews/`; scan them, give each to `<B>`, add a
   `response` to each finding in its reply, and record the reply with
   `wiki.py accept --root "<folder>" --reply <file> --author-model <A> --reviewer-model <B>`. `wiki.py check` then
   reports each page as `accepted`, `not recorded` or `refused`, apart from its problems.

**Bundles go stale after any migration**
([step 4a, *Fresh bundles*](../wiki-onboarding/SKILL.md#4a-draft-the-pages-when-every-document-has-been-read)):
`brief` and `bundles --reuse` refuse bundles built from another manifest or routing, so rebuild them after any
round ([a round after extraction](#3-curation-rounds-each-approved-by-the-owner)). To move a page,
`wiki.py move --root "<folder>" --map <file>` rewrites every link to and from it.

### 8. Check readiness

    python3 <tools>/readiness.py --root "<folder>" --terms <terms file> --out <work>/readiness.json

The [hand-off contract](#the-hand-off-contract), checked ([`readiness.py`](references/tools.md#readinesspy)). It
exits 0 when nothing is found, 1 on any finding, each listed in `findings` with the report key that holds it, and 2
on a tool error. Fix each finding in the step that owns it, and run it again. Named not-verified states, such as an
engine whose canary was not run, are listed in `not_verified`: they do not change the exit code, and are not a pass
either, so read them and tell the owner.

### 9. Hand off

Tell the owner what was prepared (the rounds run, the documents read and carded, the pages accepted, anything
left open), then run [`project-onboarding`](../project-onboarding/SKILL.md) on the folder from its step 1. It finds
a wiki with a Schema, so it does not onboard one again, and an audit pair and rulebook, so it stamps the
folder-curation archetype's `audit` job beside the file-ingest pair. The wiki was built during preparation, and no
job runs on it until then ([wiki-onboarding step 5](../wiki-onboarding/SKILL.md#5-hand-off)).

## Engine isolation

The rule is the framework's: one login per machine, the context isolated per call
([the architecture](../../ARCHITECTURE.md#execution-context-constraints-why-the-indirection-exists)). The
preparation holds it in `tools/engines.py`, which every model call goes through; how, and with which flags, is in
[the tool reference](references/tools.md#enginespy). Both engines run with the machine's own home and its one
login: neither can reach that login from another folder without its token file being copied or linked there, and
a copy that a token refresh rotates logs the main install out. So no per-project state folder is used, and
isolation comes from what each call is given and what it is denied:

- **codex** runs `exec --ephemeral` (no session file written), `--ignore-user-config` and `--ignore-rules`, with
  memories and every tool feature disabled, in an empty working folder. What still reaches the model is the
  machine's global instruction file, `~/.codex/AGENTS.md` (and `AGENTS.override.md` when present): no setting
  drops it without a separate codex home. Treat it as model-facing: the gate's `scan` reads it (step 5), and it
  must hold nothing from any project.
- **agy** keeps its login in a token file in its own state folder (not the macOS keychain), so it too runs with
  the machine's home. Each call goes in on standard input as one stream-json message, in plan mode with the
  sandbox on, from an empty working folder. Probed on the operator's machine, the model is given no saved
  memories, no summaries of earlier conversations and no instruction file, but it is offered tools: any tool event
  in its stream discards the reply (the vision lane alone may open its images). agy also cuts a very long
  message short and asks the model to read the rest from a stored copy (seen at about 300 KB), which a call with
  no tools cannot do: keep every prompt to it well under that, as the card budgets do.

The canary checks the isolation before the first call (step 5), and the contamination guard after, on every card.
A canary reply must take one of its two forms, `NONE` or a `NAMES:` line: a model that refuses to list its context
holds no term either, so a refusal fails as unanswered rather than passing.

## Identifiers

The identifier policy is `wiki-maintenance`'s
([identifiers](../wiki-maintenance/SKILL.md#identifiers-series-and-derived-views)); the owner's choice is recorded
as `identifiers` in `rulebook.json`. The preparation carries it wherever a model writes: the card instructions and
the page briefs state it, and `refs.py` refuses to restore numbers in full under any policy but `stated`, and
never restores a tail the source itself shows masked.
Passwords and activation codes are never written, under any policy.

## The settings twins

The folder carries its rules in two human-written sources, the rulebook and the wiki's Schema page, and each has a
machine-readable twin in `.familyai/` that the tools and the deployment read: `rulebook.json`, written with the
rulebook, and `wiki-schema.json`, compiled from the Schema by `settings.py compile`. Each records its source's
hash, so an edited source makes its twin stale rather than silently wrong, and every tool refuses a stale twin.
Formats, the stale states and their remedies: [the settings reference](references/settings.md).

## The hand-off contract

What a deployment relies on when it onboards a prepared folder, and what `readiness.py` checks:

- **The manifest is current**: its counts are reported (live, departed and migrating entries, root strays,
  redundant copies, hygiene defects, unconverted iWork files), and no live entry's current path is gone.
- **Every live document `extract.py` reads has an extract record and a card**; each card's category is one the
  rulebook allows, each record's path agrees with the manifest (`extract.py repath` repairs one that does not), and
  no card names an isolation term its own document does not carry.
- **The gate ran**: each engine's canary passed, or was not run, which is reported as not verified.
- **The wiki** is at `<folder name> Wiki/`, with the fixed pages `00 Index`, `01 Deadlines`, `90 Schema` and
  `91 Log`, and `wiki.py check` reports zero problems (numbered sections, frontmatter, `sources:` lists and
  folder-relative backticked paths that exist, links, em dashes, coverage, charts, rationale blocks).
- **The wiki is accepted**: the rationale file exists, and every page is `accepted`. A page whose acceptance cannot
  be verified (its professional or contract cannot be read) is reported as not verified, and what keeps it
  unreadable is a finding of its own.
- **Derived pages hold nothing hand-written**
  ([deadlines are derived](../wiki-maintenance/SKILL.md#rules-that-keep-it-safe)). Every date on `01 Deadlines` comes
  from a page's frontmatter, superseded pages left out, its own `last-updated` (a build stamp, never after today)
  aside; it shows every deadline of the pages the sweeps read that is not before that stamp; a date that recurs is
  a `recurring:` entry, `{date: MM-DD, note}`, in its page's frontmatter, shown by its own `MM-DD`; and a roll-up
  with nothing to show says why. Any other derived page, such as an open-questions list, is reported as not
  verified.
- **The rulebook**: `CLAUDE.md` present, valid UTF-8 and identical to `AGENTS.md`; naming the wiki folder; reserving
  the deployment's rulebook filenames, `GEMINI.md` included; routing no new file to the migrations folder, which
  leaves migrations to the owner's user-tier synthesis.
- **The settings twins** present and fresh.
- **No scratch**: `_Audit/` holds no folder but `plans`, `extract` and `cards`.

How `readiness.py` reports each is in [the tool reference](references/tools.md#readinesspy).

## The tools

| Tool | Step | What it does |
| --- | --- | --- |
| [`audit.py`](references/tools.md#auditpy) | 1, 3 | the manifest, `AUDIT.md` and `summary.json` |
| [`settings.py`](references/tools.md#settingspy) | 2, 7 | compiles `wiki-schema.json`; checks both twins and the rulebook's facts |
| [`plan.py`](references/tools.md#planpy) | 3 | curation rounds: `light`, `migrate`, `return`, `approve`, `rmdirs`, `check`, `execute`, `prove` |
| [`extract.py`](references/tools.md#extractpy) | 4, 3 | full text per page, local tools only (with `iwa.py` and the `page-ocr` helper); `repath` after a later round |
| [`isolation.py`](references/tools.md#isolationpy) | 5 | the terms scan and the per-engine canary |
| [`vision.py`](references/tools.md#visionpy) | 6 | the model vision lane for pages local OCR could not read |
| [`cards.py`](references/tools.md#cardspy) | 6 | one card per document; the whole-chunk join; the contamination guard |
| [`refs.py`](references/tools.md#refspy) | 6 | restores truncated reference numbers from each card's own source |
| [`wiki.py`](references/tools.md#wikipy) | 7 | `profile`, `bundles`, `brief`, `chart`, `check`, `rationale`, `review-prompts`, `accept`, `move`, `drift` |
| [`readiness.py`](references/tools.md#readinesspy) | 8 | the hand-off contract |
| [`engines.py`](references/tools.md#enginespy) | 5, 6 | the engine adapters every model call goes through |

The flags every tool shares, its exit codes and the files it keeps outside the folder:
[the tool reference](references/tools.md#common-flags) and [its working files](references/tools.md#working-files).

## Principles

- **The owner decides; the tools carry it out.** Nothing in the owner's material moves without an approved row,
  and no section, routing, professional or contract is written into the Schema until the owner agrees it.
- **The folder carries its own settings.** The rulebook and its twins travel with the folder; the tools read the
  twins and refuse a stale one.
- **Working files stay outside the folder.** The work directory holds what the tools need along the way; the
  folder holds only what the deployment will read.
- **Guards live in the tools, not in prompts.** Every write goes through one guarded writer; `--read-only-root`
  proves a tool against a real folder without changing it. A skill describes; code enforces
  ([the three layers](../../ARCHITECTURE.md#the-three-layers-of-a-job)).
