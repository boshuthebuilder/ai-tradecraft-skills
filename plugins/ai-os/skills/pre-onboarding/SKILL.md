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
  isolation](#engine-isolation)). Local reading uses Apple Vision through a small helper (the OCR helper, below),
  poppler for PDFs, and, when installed, tesseract and LibreOffice. A tool that is missing is named in the records it
  would have read, never skipped silently (the helper is the one exception, below). Ask the operator which engine and
  model the vision lane (`agy` only, a model that reads page images) and the cards use, and which two different
  models draft and review the wiki's pages (those are subagents of the session, not engine calls:
  [step 7](#7-build-the-wiki)). Name each model by the id its engine accepts: `agy models` lists agy's, and with
  `agy` the effort is part of the id.
- **The tools.** Run each as `python3 <tools>/<tool>.py` (standard-library Python 3.9 or later), where `<tools>` is
  this skill's `tools/` folder, beside this `SKILL.md`: `plugins/ai-os/skills/pre-onboarding/tools/` in a checkout of
  the repository, and the same `skills/pre-onboarding/tools/` under the plugin's own folder in an installed plugin
  (the folder this skill was loaded from). Work out its absolute path once and use that path in every command. Every
  tool takes `--root "<folder>"`; working state lives outside the folder, in the work directory, `<work>` below
  (`--work`, default `~/.ai-os-pre-onboarding/<folder name>`). The common flags, every command and every output are
  in the [tool reference](references/tools.md#common-flags).
- **The OCR helper.** Build it once, into the work directory and not the tools folder, since a plugin update may
  replace the tools folder and a helper built there with it: `mkdir -p "<work>"`, then
  `swiftc -O "<tools>/page_ocr.swift" -o "<work>/page-ocr"` (macOS 13 or later; a few seconds), and pass
  `--ocr-bin "<work>/page-ocr"` to every `extract.py` run. Prove it before the long run: copy one scan whose text you
  can read, as an image, into a scratch folder outside the folder being prepared, run `audit.py` and
  `extract.py --lane main --ocr-bin ...` over it with a scratch `--work` of its own, and open its record in the
  scratch `_Audit/extract/`. A page of tier `local_ocr` and engine `vision`, holding the scan's text, proves the
  helper. Without it a page image is recorded as a `photo`, with no note saying why. Build your own even when a
  binary is already in the tools folder: it may come from another machine.
- **The isolation terms file.** Every name that must never reach a model working on this folder: the people,
  organisations and places of the operator's other projects, and the operator's own identifiers from any other use
  of the engines. It is kept outside the folder, never committed and never shown to a model, so the operator writes
  it in their own editor and gives the session its path alone; the names never enter the conversation. List only
  names distinct to the other projects: never the owner's own name, this folder's own organisation, or an
  identifier it shares with the operator's other affairs (a home address, a tax reference), since the folder's own
  settings name its people and every scan of them would fail. Ask the operator for the path; the format is in
  [the card contract](references/cards.md#the-terms-file). Where there is genuinely nothing to list, step 5 says
  what runs instead.
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
    plans/<YYYY-MM-DD>/      one folder for each round's proposal (folder-curation's shape)
    extract/<id>.json        the full text of each document, page by page
    cards/<id>.json          one summary card per document
    wiki-rationale.md        one rationale block per wiki page
    wiki-acceptance.json     the acceptance verdicts
    wiki-acceptance.json.lock  the lock `wiki.py accept` takes, left beside the record; harmless
  _Inbox/                    the drop point the rulebook names; onboarding sets it up, so preparation need not
  _Migrations/<Project>/     files approved for another project, only while a migration is open; empty at hand-off
  <folder name> Wiki/        00 Index, 01 Deadlines, the numbered sections, 90 Schema, 91 Log (each fixed page a
                             folder note: 00 Index/00 Index.md, and so on)
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
only in the cloud stops the audit with a list: download it, or, with the owner's say-so, pass `--dataless read`,
which makes the audit download every cloud-only file under the folder (on a large folder, most of what the owner keeps
in the cloud). Show the owner `AUDIT.md` before asking anything. This first audit is a look: it runs again once the
interview has settled the packs ([step 2](#2-interview-the-owner-write-the-rulebook-and-its-twin)).

### 2. Interview the owner; write the rulebook and its twin

Ask [`folder-curation`'s interview](../folder-curation/SKILL.md#2-interview-the-owner-a-fixed-ladder-one-pass), in
its order, and record every answer in the folder's rulebook, `CLAUDE.md`, with `AGENTS.md` a byte-identical copy;
[`tools/templates/rulebook.md`](tools/templates/rulebook.md) is the skeleton to start from. In the same change, write
`.familyai/rulebook.json` from the same answers and pin it: record the rulebook's sha256 as `rulebook_sha256`, which
says the twin was reviewed against it ([the format and pinning](references/settings.md#rulebookjson)). The same
interview settles what this preparation adds to the ladder, each a key of the twin:

- **The categories and the description.** `card_categories`, the list a card's category must come from, and
  `folder_description`, the one line the card engine is told about the folder. Propose both from the audit and let
  the owner agree them: the default categories are a personal set ([the list](references/settings.md#rulebookjson)),
  and a company wants its own. List `Other` if it is to be allowed: a card the engine places outside the list becomes
  `Other`, and `readiness.py` reports it as a `bad_category` unless the list holds it.
- **Packs.** The folders that keep deliberate copies of documents held elsewhere: `packs`, and the words that mark
  them in `pack_keywords`. The default keywords are a personal set, so a company's own packs, such as a year-end
  accounts pack or a payroll year, are unprotected until listed ([examples](references/settings.md#rulebookjson)).
- **Other people's personal data.** If the folder holds staff, customer or supplier papers (contracts, payslips, tax
  and bank details, contact lists), ask what may go to the cloud engines: the vision lane sends page images and the
  cards send each document's whole text to `agy` or `codex`, under the identifier policy. Record the answer in the
  rulebook. `boundaries` is free text that no tool enforces, and `exclude` is the setting a deployment enforces once
  the folder is onboarded: no preparation tool reads it. Until then the one hard control is a top-level folder named
  in `reserved`, which the audit never walks, so nothing in it is extracted, carded or sent. Anything else the tools
  find is read, and the owner should be told so.

Two things the [hand-off contract](#the-hand-off-contract) checks belong in the rulebook from the start:

- every name the system reserves at the top of the folder, `GEMINI.md` included, and every pack
  ([the list](references/settings.md#rulebookjson)); a pack listed in `rulebook.json` must be an existing folder,
  named exactly, or the audit and plan tools refuse to run;
- new files are filed within this folder by the wiki's routing, never routed to the migrations folder: a file that
  seems to belong to another project is filed here like any other, and the move is only suggested, by the owner's
  user-tier synthesis; the owner makes it by hand
  ([a project files within itself](../wiki-maintenance/SKILL.md#rules-that-keep-it-safe)). Keep the other project's
  name out of the rulebook. `readiness.py` reads this part by keyword, line by line, so keep the migrations folder
  and the words about new files on different lines, as the skeleton does; its wording passes.

Then run `settings.py check --root "<folder>"`. Until the wiki exists it reports `wiki-schema.json` as missing;
fix every other finding now. **Audit again** once the twin is pinned and before any plan is proposed: step 1 worked
out the manifest's copy kinds, which decide what a plan may propose to delete, with the default pack keywords and no
`reserved` names, and a name the twin now reserves leaves the manifest as a departure.

### 3. Curation rounds, each approved by the owner

A round is [`folder-curation` steps 3 to 6](../folder-curation/SKILL.md#3-propose-the-only-model-step), carried
out by `plan.py` in a plan folder, `<folder>/_Audit/plans/<YYYY-MM-DD>/` (below `<plan folder>`, and `<plan>` its
`move-plan.csv`). Every proposal gets a plan folder of its own: `plan.py light`, `migrate` and `return` write
`move-plan.csv` over any plan already in the folder they are given, approvals included. A second proposal on the same
day (a round that deletes copies often needs one) takes a suffix, `<YYYY-MM-DD>-2`, or a word for what it does,
`<YYYY-MM-DD>-migrate`; nothing reads the folder's name. Finish curating before step 4 where you can: extract
records and bundles carry the paths they were built from. A round after that is repaired, never read again (*A round
after extraction*, below).

1. **Propose.** `plan.py light --root "<folder>" --out "<plan folder>"` proposes the light-depth rows: root strays
   (their destination left for the owner), file and folder names with a space at either end or before the
   extension, and redundant copies outside any pack. Rows for a deeper depth the owner chose follow
   folder-curation's step 3, written in the same [plan format](../folder-curation/references/move-plan-schema.md);
   the executor runs `create`, `move`, `rename`, `rmdir` and `delete` rows, and names an approved `convert` row
   and leaves it pending, since a conversion stays the owner's. To stage files for another project, list their
   paths in a file and run
   `plan.py migrate --root "<folder>" --project <Project> --paths-file <file> --out "<plan folder>"`, where
   `<Project>` is only the name of the folder the files are staged in, any label the owner will recognise;
   `plan.py return` brings staged files back (`rmdirs`, below, proposes removing the folder it empties).
2. **Show the owner the actual files**
   ([a boundary is confirmed with its files](../folder-curation/SKILL.md#2-interview-the-owner-a-fixed-ladder-one-pass)).
   The owner reads `review.tsv`, which lists every staged path with its copy kind and the copies that stay behind,
   and a `MISSING` line for each listed path the manifest does not know. Correct the paths file and propose the
   round again until the list is what the owner means.
3. **Approve.** The owner reads the plan domain by domain and chooses a destination for each stray; write it into
   that row's `to` column ([the plan schema](../folder-curation/references/move-plan-schema.md)) before approving
   the row. No `plan.py` command does it: edit `move-plan.csv` with a tool that reads and writes CSV (its paths hold
   commas and quotes), change no other cell and keep the row order. `check` (item 4) does not flag a stray left
   without a destination; the dry run in item 5 refuses it by name. Record each decision as it is made:
   `plan.py approve --plan <plan> --rows 1-5,7 --note "<what the owner said>"`, with `--decline` for a no and
   `--defer` for not this round. Then
   `plan.py rmdirs --root "<folder>" --plan <plan>` proposes an `rmdir` row for each top-most folder the approved
   moves empty; the owner approves or declines those too (the rulebook's `keep_empty_folders`).
4. **Dry run.** `plan.py check --root "<folder>" --plan <plan>`; fix or decline every row that fails.
5. **Execute.** Keep a copy of the manifest the round starts from (for example in
   `<work>/plans/<YYYY-MM-DD>/manifest.before.json`), then run `plan.py execute --root "<folder>" --plan <plan>`
   to print what would happen, and again with `--apply`. Nothing is unlinked: removed items go to the Bin, with an
   undo entry each ([`rmdir` and the Bin](../folder-curation/references/move-plan-schema.md#rmdir-and-the-bin)). Keep
   the Bin (the operator's `~/.Trash`, unless `--bin` names another folder) unemptied until the folder is onboarded,
   and tell the owner why: for a folder in iCloud Drive a removal reaches every device it syncs to, while the undo log
   and the Bin's copy are on this machine only.
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

**The migrations folder is cleared by hand before hand-off.** Staging is for this preparation only:
`project-onboarding` stops while the migrations folder holds any file. The owner empties it, each staged file
collected by its own project (a departure `prove` expects by name, item 6) or brought back by an approved `return`
round, until nothing is left but `.DS_Store` and empty folders. An empty `<Project>/` folder left behind is fine:
`rmdirs` proposes removing only a folder that approved moves emptied, not one emptied by hand. `extract.py`,
`vision.py` and `cards.py` skip every entry under the migrations folder, whatever its flags, and count it as held for
another project, so a staged file's text, pages and path never reach an engine; clear the folder before step 4 where
you can, so nothing waits on it. A departed entry stays in the manifest for ever, with its old path and its target
project: the tools build their prompts from live documents, and no brief hands the manifest to a model. After
onboarding the system stages nothing: a file that belongs to another project is filed in the folder like any other,
and the move is only suggested, for the owner to make.

**A round after extraction.** When a round has to run after step 4 (a migration found while the wiki is drafted,
say), repair what it moved rather than read anything again. Once the round's re-audit is proved,
`extract.py repath --root "<folder>"` lists each extract record whose path it would rewrite to its document's
current path, matched by content hash, with nothing read again; run it again with `--apply` to write them. It
refuses a move to a path that is not in the folder, so it runs only on a manifest the re-audit has made current
([`repath`](references/tools.md#repath)). Then rebuild the bundles and run `wiki.py drift` (step 7). Cards hold no
path, only their document's id, so they need nothing.

### 4. Extract the text

    python3 <tools>/extract.py --root "<folder>" --lane main --worker 0/4 --ocr-bin "<work>/page-ocr"
        (and 1/4, 2/4, 3/4 alongside)
    python3 <tools>/extract.py --root "<folder>" --lane apps --ocr-bin "<work>/page-ocr"

Each live document gets a record in `_Audit/extract/<id>.json` holding the text of every page and the tier that read
it: a PDF's text layer first, then local OCR, and last the model vision lane (step 6) for pages local OCR could not
read cleanly. Local OCR reads in the rulebook's `ocr_languages` (default `en-GB`): set them, at the interview, to the
languages the documents are written in, most likely first. tesseract reads with every one of them at once, so check
before the run that `tesseract --list-langs` lists each (`eng`, `fra`, `deu`, `spa`, `chi_sim` or `chi_tra`, for the
codes the rulebook accepts): a language whose data is not installed makes it read nothing and say nothing, and the
page goes on to the vision lane or reads as blank. Office files and plain text are parsed directly. The tiers,
statuses and fields are in [the tool reference](references/tools.md#extractpy). Run again with `--retry-failed` once
the cause of a failed record is fixed; a record is never read again to follow a move ([a round after
extraction](#3-curation-rounds-each-approved-by-the-owner)). Two lessons from real folders:

- **iWork is read without the apps.** Pages, Numbers and Keynote documents are read by parsing the package itself
  (`iwa.py`), with its preview image as the fallback (the record is then `partial`). Never open an app or export a
  file to read it: an export is the owner's choice
  ([the class policy](../folder-curation/SKILL.md#class-policy-defaults-the-rulebook-may-override-per-folder)).
  `iwa.py` keeps the fields that are human text, so a Numbers sheet's numbers and grid may not reach the record:
  open the record of one sheet of each kind before relying on it. Where a page needs the figures (a price list, a
  ledger), ask the owner for an `.xlsx` or `.csv` export of the sheet, which is read directly.
- **A text layer can be broken.** Some PDFs carry a text layer whose spaces decode as `)` or `!`, which reads as
  text but is not. The extractor detects it, discards the layer and OCRs the page, so trust the tier recorded per
  page, not the file type.

### 5. Open the gate to the engines

Before any model reads this folder:

    python3 <tools>/isolation.py scan   --terms <terms file> --path <tools> --path "<folder>/.familyai" \
        --if-present ~/.codex/AGENTS.md --if-present ~/.codex/AGENTS.override.md --if-present ~/.codex/skills \
        --if-present ~/.gemini/GEMINI.md --out <work>/state/scan.json
    python3 <tools>/isolation.py canary --terms <terms file> --engine <engine> --model <model> \
        --out <work>/state/canary-<engine>.json

`scan` checks every file a model will be shown (the tools' prompts and templates, and the settings the card
instructions are filled from) for the terms, and exits 1 on any hit or when it found nothing to check; scan the wiki
briefs and review prompts the same way before a model reads them (step 7). The `--if-present` lines are the global
files each engine reads whatever the folder: codex's under `~/.codex` (add `~/.agents/skills` where that folder
exists) and agy's `~/.gemini/GEMINI.md`. They assume each engine's default home: a codex installed under another
`CODEX_HOME` needs the files in that folder given instead. Drop the lines of an engine this machine lacks, since a
missing `~/.codex` or `~/.gemini` is an error, as a typo would be. A file missing from a folder the machine has is
skipped and listed in the result's `absent` and on stderr, so read `absent` and check it holds only files the machine
really lacks. `scan` expands `~` and variables itself, follows links into folders (skills are often links; a broken
one is an error, never a skip), and stops with an error on a path that still holds `~` or `$`, or whose folder does
not exist: that is a typo, and a typo must never read as a clean scan.

`canary` checks a cooperating engine: it plants an invented name in the engine's context and asks the engine for
every name it holds, as exactly one line, `NAMES:` and the names separated by commas, starting with that one. It
passes only a reply of that one shape, with no term in it: after surrounding whitespace a single line, `NAMES:` and a
comma-separated list, the first item the invented name (recorded as `marker`), every item name-like (one to six
words, none of `. ! ? ; :` inside, no pronoun or negation from a small closed set, not wrapped in brackets). A second
line, a fence, bold, a bullet or an item that fails the name-like test fails as unanswered: an honest reply in another shape costs a
rerun and never gives a false pass. It cannot prove that a model withholding names deliberately holds nothing back (a
well-formed line holding only the invented name passes); no reply can prove an absence. The scan above, and the
contamination check on every card, cover that. Run the canary for each engine you
will use, with the `--model` the cards will use: models of one engine answer differently, and some refuse the
question outright, which fails the canary. In one measured run a Flash-tier Gemini model refused it where a Pro-tier
one answered, so canary the exact model and effort a lane will use, never a sibling of it. The same model can decline on one run and answer on the next: a decline
proves nothing either way, so run the canary again. A model that declines three runs in a row cannot be cleared for
this folder, so card with one that answers. The result records the `model` and `effort` that were cleared, and `readiness.py` names them: compare
them with the model the cards ran on (`card_meta.model`). A codex `--light-model` is not covered by the engine's
one result, and neither is the vision model when it differs from the card model on `agy`: canary it as well, to a
result file of its own, `<work>/state/canary-agy-vision.json`. `readiness.py` reads one file per engine and names
the model that file cleared, so leave `canary-agy.json` to the card model's result (one result covers both when they
are the same model; with the cards on `codex`, it is the vision model's) and say in the hand-off which file cleared
the vision lane. Each command clears its `--out` file before it even reads its command line, so a
run that stops early (or is refused) leaves no earlier pass behind. Keep both results: they are the record
that the gate ran, and `readiness.py` reads each engine's canary from `<work>/state/canary-<engine>.json` (step 8).
No lane reads them (`vision.py` included), so never start one without passing ones. A failure means the engine's
context carries another project: fix its setup ([engine isolation](#engine-isolation)) and run the canary again.

**When no agy model passes.** The vision lane cannot run. The pages local OCR could not read stay `pending_vision` in
records whose status is `needs_vision`: `cards.py build` counts their documents as waiting for ever, and readiness
reports their cards as missing, so they never reach the hand-off unread by themselves. Do not leave them queued. Name
them to the owner (every record whose `status` is `needs_vision`, with its pages), and either find an agy model that
passes the canary or let the owner decide what becomes of those documents, such as taking them out of the folder, which
the next audit records as a departure. No tool marks a page unread without the lane.

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
`<work>/state/ALERT` and stops every worker (the worker that found it exits 2, as any refusal does; every other
worker, and the vision lane, exits 3 at its next batch while the file exists): find where the term came from before
you remove the file. A document
that could not be carded is listed as `<work>/state/card_err_<id>.txt` (for a long one, naming each section that could
not be read: no card is written from the rest); list those ids in a file and run `cards.py work` with `--redo <file>`
once the cause is fixed. A redo sends a document as a first run would, a long one in sections, and reuses the notes
already cached, so only the section that failed is read again; the `card_err_` file goes when the card is written.

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

**The roles are subagents of this session, not engine calls.** The librarian, the contract drafters, the page
drafters and the reviewers are tool-using subagents of the operator's own session, each in a fresh context, on the
models the operator named (a page's reviewer on a different model from its drafter). They do not go through
`engines.py`, so [the engine rules](#engine-isolation), agy's prompt limit and the no-tools rule among them, bind the
vision lane and the cards alone. The readers interview is the coordinator's own: it asks the owner and writes the
answers down, and gives the template to no one. What holds a subagent is what it is shown and told: its brief, the
Schema page, the bundles and the source files they name, and the core wiki rule, and nothing else in the folder or on
the machine. It does not read the terms file, `<work>/state`, or anything under `_Audit/` its brief does not name (the
manifest and `AUDIT.md` name the project a staged file is bound for, and a departed entry keeps it); every brief says
so. The coordinating session is the operator's own and is not behind this gate, and it needs no name from the terms
file. Scan what a subagent is given before it reads it, the briefs and review prompts as files:

    python3 <tools>/isolation.py scan --terms <terms file> --path <work>/briefs --path <work>/reviews \
        --path "<folder>/CLAUDE.md" --path "<folder>/.familyai" --path "<folder>/<folder name> Wiki/90 Schema" \
        --out <work>/state/scan-wiki.json

`.familyai` has changed since step 5 (the compiled Schema), and a subagent working in the folder loads the rulebook and
is sent to the Schema page, so they are scanned again with the briefs. `scan` refuses a path that does not exist: leave
out the Schema page before it is written, and `<work>/reviews` before the first review prompt. It creates `--out`'s
folder. Save every brief you fill by hand under `<work>/briefs/` (`structure.md`, `contract-<NN>.md`), beside the
ones `wiki.py brief --out` writes, so that each is a file to scan.

| Stage | Who holds the pen | Brief or tool | Method |
| --- | --- | --- | --- |
| Readers: who reads the wiki, and what for | the owner, answering; the agent asks and records the answers in the owner's words | `readers-interview.md`, with `wiki.py profile` | [step 3](../wiki-onboarding/SKILL.md#3-interview--a-few-targeted-questions) |
| Sections and routing | the librarian proposes; the owner agrees | `structure-brief.md`, with `wiki.py profile` | [step 2](../wiki-onboarding/SKILL.md#2-propose-a-structure-the-librarians-sections-and-each-pages-professional) |
| Each page's professional | the librarian proposes; the owner agrees | `structure-brief.md` | step 2 |
| Each section's page contract | the section's professional drafts it, or its professionals together where it has several; the owner agrees | `contract-brief.md` | [step 3a](../wiki-onboarding/SKILL.md#3a-page-contracts-for-every-page-type-drafted-by-its-professionals) |
| Each page | that professional writes it, as their deliverable to the owner, their client, in their own voice; the fixed pages are the coordinator's (item 6) | `page-brief.md`, rendered by `wiki.py brief`; `wiki.py chart`; `wiki.py check` | [step 4a](../wiki-onboarding/SKILL.md#4a-draft-the-pages-when-every-document-has-been-read) |
| Acceptance | the owner's lens and the professional's, each played by a model that did not write the page | `review-owner.md`, `review-professional.md` | [step 6](../wiki-onboarding/SKILL.md#6-reader-acceptance-the-owners-lens-and-the-professionals) |

The briefs are templates in [`tools/templates/`](tools/templates/): to brief a role, fill the template's fields (its
opening comment says how each is made) and give it to a subagent, then take the JSON it returns to the owner. The
librarian picks each page's professional from
[the professional catalogue](../wiki-maintenance/references/professionals.md), as its note on choosing says. What the sections share is the coordinator's to write
([step 4a](../wiki-onboarding/SKILL.md#4a-draft-the-pages-when-every-document-has-been-read), *JSON returns*).

In order:

1. `wiki.py profile --root "<folder>" --out <work>/profile.json`: the folder's shape, per folder, for the readers
   interview and the librarian.
2. Hold the readers interview; brief the librarian with the readers' answers; confirm the proposal with
   wiki-onboarding step 3's questions, asking only what the rulebook does not already answer; agree the sections,
   routing and each page's professional with the owner. Create the wiki folder, `<folder name> Wiki/`, and its
   Schema page, `90 Schema/90 Schema.md`, as
   [wiki-onboarding step 4](../wiki-onboarding/SKILL.md#4-write-the-skeleton) describes it, with the agreed tables
   in the format [the settings reference](references/settings.md#the-schema-pages-tables) fixes. The Layout lists all
   four fixed pages as `fixed` sections, each a folder note (`00 Index/00 Index.md`, `01 Deadlines/01 Deadlines.md`,
   `90 Schema/90 Schema.md`, `91 Log/91 Log.md`), and Page professionals gives every page of a section that names
   several professionals its own row, folder notes included: the checks refuse a page whose professional cannot be
   told, and a page with no row has no deliverable or tone recorded. Beside the tables the Schema records, as ordinary
   sections, who reads the wiki and for what, each section's purpose and trigger documents, and the identifier,
   currency, date and unit policy, an absent one stated as absent. Then run `settings.py compile --root "<folder>"`
   and `settings.py check --root "<folder>"`.
3. `wiki.py bundles --root "<folder>"` routes every live document to its section's evidence bundle, in
   `<work>/bundles` by default. It lists what it cannot route and what has no card: fix the routing (edit the
   Schema, compile again) or card the document (step 6), until both lists are empty.
4. Brief each section's professional, or all of a section's professionals together where it has several, to draft
   its contract; agree each contract with the owner; add it to the Schema's Page contracts table; compile and
   check again (the check names any section, other than a `fixed` one, still without a contract).
5. Fix the page map before drafting starts
   ([step 4a](../wiki-onboarding/SKILL.md#4a-draft-the-pages-when-every-document-has-been-read)). It is every page in
   Page professionals, each Layout section's folder note and the pages on disk, with the pages being briefed added:
   list every page the wiki will hold in Page professionals first, and each brief's map (`brief` prints it) is
   complete. Then render a brief per group of pages:
   `wiki.py brief --root "<folder>" --page "<NN Section>/<Page>.md" [--page ...] --out <work>/briefs/<NN>.md`.
   Scan the briefs (above), then draft as step 4a sets out. A section whose bundle is very large (check
   `wc -c` on its `bundle_<NN>.jsonl`) is split across agents by page, or by year where it holds a page a year, and
   each agent is told which lines of the bundle are its own (a folder prefix or a year in the path), so that it reads
   those and not the whole file. As a working limit, not a measured one, give an agent no more than about 200,000
   characters of bundle: the sources it opens and the pages it writes need the rest of its context. Each drafting
   agent draws its charts with `wiki.py chart`, runs the checker command its brief names, and returns the JSON its
   brief shows: each page's text, rationale block and Index entry, its open questions and its check result. Keep each
   return as a file in `<work>/returns/`.
6. The coordinator writes what the sections share, from the returns. It writes `00 Index` in the chief of staff's
   voice, from the drafters' Index entries and open questions, and the other fixed pages (the Log, a People alias
   table). It renders `01 Deadlines` with `wiki.py deadlines --root "<folder>"`, from the pages' `deadline`,
   `deadlines` and `recurring` frontmatter (a dry run; `--write` writes the page), never by hand. For every page it
   writes, the Schema and the folder notes included, it makes a return file by hand in `<work>/returns/`: an object
   with a `pages` list, each entry the page's `path` and its `rationale` block (the heading and five lines), so that
   `wiki.py rationale --root "<folder>" --returns <work>/returns` writes `_Audit/wiki-rationale.md` with a block for
   every page. Then run `wiki.py check --root "<folder>"` over the whole wiki until it reports zero problems.
7. Accept every page as [wiki-onboarding step 6](../wiki-onboarding/SKILL.md#6-reader-acceptance-the-owners-lens-and-the-professionals)
   runs it and [the core rule's acceptance](../wiki-maintenance/SKILL.md#acceptance) sets it out, through a model
   other than the one that drafted it (below, `<A>` drafted the page and `<B>` reviews it). Finish every edit first,
   the last `91 Log` line included, since any later edit to a page voids its acceptance; then accept the section
   pages, then `01 Deadlines`, `90 Schema` and `91 Log`, and the Index last, against its children (that step also says
   what a reviewer judges on a fixed page).
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
left open). If they read the wiki in Typora, tell them to turn on Preferences, Markdown, Syntax Support,
Diagrams, then restart Typora, or its charts show as code ([portable-markdown](../../../productivity/skills/portable-markdown/SKILL.md#charts-and-callouts)).
Then run [`project-onboarding`](../project-onboarding/SKILL.md) on the folder from its step 1. It finds
a wiki with a Schema, so it does not onboard one again, and an audit pair and rulebook, so it stamps the
folder-curation archetype's `audit` job beside the file-ingest pair. The wiki was built during preparation, and no
job runs on it until then ([wiki-onboarding step 5](../wiki-onboarding/SKILL.md#5-hand-off)). Nothing in the work
directory is part of the hand-off: onboarding reads the folder, whether it continues in this session or on the
deployment, and runs `readiness.py` itself (its step 1). Keep `<work>/readiness.json` and the canary results to show
the owner what was verified and what was not.

## Engine isolation

<!-- provisional: the engines' environment-variable lists (#125) -->

The rule is the framework's: one login per machine, the context isolated per call
([the architecture](../../ARCHITECTURE.md#execution-context-constraints-why-the-indirection-exists)). The
preparation holds it in `tools/engines.py`, which every engine call goes through, the vision lane's and the cards'
(the wiki's subagents are not engine calls: [step 7](#7-build-the-wiki)); how, and with which flags, is in
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
  sandbox on, from an empty working folder, and its output shape is asked for in the prompt, never with
  `--json-schema` (in plan mode that flag makes the model write a plan and ask to be approved, which the rule below
  discards). Probed on the operator's machine, the model is given no saved
  memories, no summaries of earlier conversations and no instruction file, but it is offered tools: any tool step
  in its stream discards the reply, allowed or not. agy 1.2.16 streams one as a `step_update` event with
  `step_type: "tool"`, a `tool_name` and a `tool_info`, as real captures show, and the rule does not rest on that:
  any step other than a `user_input`, an `agent_response` or agy's own `system_message` counts, whatever its keys.
  The vision lane alone accepts the steps that open its images, `view_file`, `list_dir` or `find_by_name`, and only
  when every path they name, however it is spelled (a file URL included), is inside the call's own folder; any other
  tool, or a read elsewhere or one that cannot be judged, fails there too.
  agy also cuts a long message short, silently (exit 0, a successful result, no event), and asks the model to read the rest from a
  stored copy, which a call with no tools cannot do. Measured on agy 1.2.16 with
  `gemini-3.1-pro-high`: the cut falls at about 192,000 UTF-8 bytes of prompt text, plus or minus 150, for ASCII
  and CJK alike. The limit is on the bytes of the text, not characters, tokens or the size of the serialised
  message. The tools refuse a prompt over 180,000 bytes of text (6% under the cut) before the call, and the card
  budgets keep every call under it. That refusal is the guard: a call whose task can be answered from the start of
  its prompt reads as ok on part of its input. The stream's one trace of a cut, a step that names agy's stored copy
  beside a refused command, is caught too, but its absence proves nothing. Re-probe on an agy upgrade (about six
  calls).

The canary checks the isolation before the first call (step 5), and the contamination guard after, on every card.
Three layers hold the rule, and each covers what the others cannot:

- **The canary** checks a cooperating engine: that it answers the question in the required form (one `NAMES:` line,
  an invented name first, short comma-separated names), and that its answer names no banned term. It cannot prove that a model withholding names
  deliberately holds nothing back: no reply can prove an absence, and the invented name is in the message, not in an
  instruction file.
- **The scan** reads every file a model is shown, including the global files each engine reads.
- **The contamination check** reads every card, against its own source.

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
  aside; it shows every deadline of the pages the roll-up reads that is not before that stamp; a date that recurs is
  a `recurring:` entry, `{date, note}` with the date as `MM-DD` (month first) or a day and a month name
  (`5 April`), in its page's frontmatter, and the roll-up shows it by its day and month name; the page holds only
  what the roll-up renders from the pages' frontmatter (each entry's date, note and page link), and every other
  line is reported; and a roll-up with nothing to show says why (`wiki.py deadlines` renders the page in exactly
  this form). Any other derived page, such as an open-questions list, is reported as not verified.
- **The rulebook**: `CLAUDE.md` present, valid UTF-8 and identical to `AGENTS.md`; naming the wiki folder; reserving
  the deployment's rulebook filenames, `GEMINI.md` included; routing no new file to the migrations folder, which
  leaves a migration to the owner: the user-tier synthesis only suggests it.
- **The migrations folder is cleared**: the folder's migrations folder (`migrations_dir` in `rulebook.json`,
  `_Migrations` by default) holds no file, since a deployment onboards a folder only once it is empty. Names are
  listed and no file is opened; `.DS_Store` and empty folders do not count, an evicted iCloud placeholder does, and
  the finding names the count per first-level subfolder. The owner clears it by hand before hand-off.
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
| [`wiki.py`](references/tools.md#wikipy) | 7 | `profile`, `bundles`, `brief`, `chart`, `check`, `rationale`, `deadlines`, `review-prompts`, `accept`, `move`, `drift` |
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
