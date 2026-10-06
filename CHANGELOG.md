# Changelog

Releases are semver tags (`vMAJOR.MINOR.PATCH`); what counts as a breaking change is defined by
the versioned interface in [`AGENTS.md`](AGENTS.md). Consumers pin a tag and advance it
deliberately.

## v12.2.0 (2026-10-06)

A **MINOR**, from a second cold-reader test of `pre-onboarding`. The isolation terms file kept a term out of a
card, but a document whose own text or path carried a term was still sent whole to the engine, its images to the
vision model, and its text and path to the wiki's drafting and reviewing subagents. The tools now shield every call,
and the prose is completed for the gaps the reader found. Tool command lines are not part of the versioned interface
([`AGENTS.md`](AGENTS.md)), and nothing a consumer depends on breaks: no skill name, frontmatter, archetype layout or
prompt placeholder changed.

### Added (MINOR)

- **The shield** (`isolation.shield`, `shield_value`, `shield_digest`, `carries`). Every term and marker of the terms
  file is replaced by `[withheld name]` in every path and text a tool sends or writes: `cards.py` (items, section
  prompts, opening text and notes; the notes' cache basis folds in the sha256 of the terms' forms, and a cached note is
  shielded again when read; a card records `card_meta.shielded`, a count, and `card_meta.shield_sha256`), and `wiki.py`
  `profile`, `bundles`, `brief` and `review-prompts` (a page's sha256 in a review prompt is left as it was). Text is
  shielded whole and then cut, never the other way. `bundles.json` records the shield, never the terms (nor the terms
  file's path), and `brief` and `bundles --reuse` refuse and remove bundles built under another one.
- **One matcher** (`isolation.alternation`) for the shield, the scan (`hits`), `carries` and `masked`: case-insensitive,
  in Unicode NFC, with a space in a term matching any run of Unicode whitespace, so a name wrapped at a line end, set
  with a no-break space or stored decomposed is still the name. A name split by a hyphen at a line end, or by a
  zero-width character, is not matched: a settled residual. The shield is idempotent. The matcher takes the placeholder
  out of a text (`isolation.without_placeholder`: case-insensitive, tolerant of the spacing inside the brackets) before
  `hits` and `carries` look for a form, so no form is ever found inside it, whatever the caller (a card, a section note,
  the scan), and a surname such as Held, or a marker such as Nam, stays listable.
- **A subagent is told never to open a shielded source.** One rule (`wiki.shielded_document`) decides it for `bundles`,
  `brief` and `review-prompts` alike: the document's path, any copy's path, its extract text or any field of its card
  carries a term, or its card records that it was shielded; a card or extract record that is missing or unreadable counts
  as shielded (fail closed), except an entry the manifest records as never read (`hashed` false: an image over the cap),
  which is judged by its paths alone, so such an image, or a folder holding one, is not marked for that. A bundle line for such a document has `"shielded": true`; the page brief and both review
  templates say never to open such a source; `review-prompts` (which takes `--extract`) lists it as "do not open", and a
  cited folder with a shielded document under it likewise (how many, never which), and samples none of its facts; `brief`
  says how many of the sources an existing page cites are shielded. The tools cannot restrict a subagent's file access:
  the guard is the instruction and the shielded text the bundle already holds.
- **A section note that names a term is contamination:** it writes the ALERT, stops every worker and is never cached.
- **`vision.py` holds back a document that carries a term.** An image cannot be shielded, so a document whose manifest
  path or extract text (`text` or `local_text`) carries a term has no image sent: its queued pages are marked `unread`,
  the local text kept, and the log counts such documents. The residual, a term visible only on a page local OCR could
  not read, is stated.
- **`readiness.py`: `paths_naming_terms`** finds a live or staged manifest entry whose path, a copy's path or migration
  label carries a term (a migration label is a folder name under the migrations folder): paths a later run can still
  send. `history_paths_naming_terms` counts, as information and never a finding, the names the manifest keeps as history
  (departed entries, `original_name`, `rename_history`). It also requires **a canary for every model the cards ran
  on**: given `--terms`, each engine and exact model in `card_meta` needs a passing `<work>/state/canary-*.json`, for
  codex at the exact effort (the light model's `light_model_effort` is now recorded beside `light_model`), made against
  the same terms file, or it is a finding. Codex cards with no recorded effort read `not verified`, never a pass.
  `cards_shield` counts, as not verified, the cards made with no recorded shield or under another terms file.
- **`isolation.py canary --effort`** (codex; agy's effort is in its model id), and the result names the effort used and
  records the digest of the terms file it ran against (`terms_sha256`), which readiness must find equal.
- **`audit.py` reports what it skips** (`summary.json` `not_audited`, the `Not audited` section of `AUDIT.md`) and counts
  excluded items apart from count-only images (`summary.json` `excluded`). A skipped folder the owner also excluded is
  named, with that reason, and counts as excluded (naming it is intended: it is a top-level name, as the top-level
  table already shows for any folder the walk enters, and its items are counted, never listed); a link at the top is
  one item and is never walked.
- **`settings.py check` reads `ocr_languages`** against the codes `extract.py` reads, from one list in `common.py`.

### Changed

- **`cards.py work`, `vision.py` and `wiki.py` `profile`, `bundles`, `brief` and `review-prompts` need `--terms F` or
  `--no-isolation-terms`** (and refuse both). A command line that omitted both on `vision.py` or the wiki commands now
  stops at its start (exit 2) and says what to add.
- **The contamination check has no excuse.** A card is compared with its document as the engine was sent it, shielded,
  so a card that names any term is a finding in `cards.py` and in `readiness.py`, including a card made before this
  release under the old rule that a term its own source carried was not an alert.
- **`audit.py` drops, rather than carries as `departed`, an entry whose own path the owner has since excluded**, which
  would have kept the file's name and real content hash for ever. A departed entry whose own path is not excluded keeps
  its history, with only a copy's path under an excluded folder taken out. An excluded item no longer appears in any
  path-listing section of `AUDIT.md`, and takes no part in the iWork pairing.
- **`readiness.py` keys `isolation.canary` by `"<engine> <model>"`** (for codex, `"<engine> <model> effort <E>"`), one
  entry per result file, instead of one per engine. The fixture's prepared cards now record the engine and model they stand for (`agy`, `gemini-fake-high`).
- **The prose** closes the gaps the second reader found: the order of exclusions and terms before the first audit; the
  reserved and skipped names (`Outbox`, `Wiki`, the leading `_`); neutral migration labels; the shield and its
  residual; one canary per model; who the operator and the owner are; recording each model by its exact id; the session
  context a file scan cannot see; asking `ocr_languages`; a copy left behind being a live document; when
  `prove --allow-departed-under` is needed; the hand-made rationale return file; a header-only Page contracts table;
  one build location for the OCR helper; the empty roll-up banner as the tool renders it; and the drafting agents'
  exception to opening the Schema page.

### Migrating a deployment

Nothing is required to advance the pin. A deployment that runs the preparation tools should add `--terms` or
`--no-isolation-terms` to `vision.py` and the four wiki commands, audit once more, rebuild its bundles, and run one
canary per model its cards ran on (`canary-<engine>-<model>.json`) before `readiness.py --terms`.

### Placeholders

No placeholder was added, removed or made required: each of the eight prompt templates under
`project-onboarding/archetypes/` uses the same set as at v12.1.0.

## v12.1.0 (2026-10-06)

A **MINOR**, from a cold-reader test: a fresh agent given only `pre-onboarding` planned the preparation of a
fictional company folder and found where the skill left it guessing. The tools now keep every file staged for
another project, and every path the owner excludes, away from every model-facing artefact, and the skill's
prose is completed for a cold reader and for a company folder.

### Added (MINOR)

- **Withheld means purged** (`common.withheld`, `common.purge_withheld`, #128, #131). A document staged in the
  migrations folder, or under a path the owner excluded, is never read, carded, sent to an engine, put in a
  bundle, brief, profile, review prompt, drift report or chart, or opened or hashed by `plan.py`. Every tool's
  start, and every worker batch, discards what an earlier run derived from such a document: extract records,
  cards, cached section notes, queued page images, hash-cache lines, and every bundle, brief, prompt and report
  written under another withheld set. It prints counts, never paths, and a removal that fails stops the tool.
- **`wiki.py deadlines`** renders the derived Deadlines page from the pages' `deadline`, `deadlines` and
  `recurring` frontmatter, in exactly the form `readiness.py` accepts (#128).
- **`check` finds citations of withheld documents** (`cites_withheld`), in any spelling of the path, and
  `review-prompts` refuses to render a page that has one. `brief` marks such a page (#128).
- **`plan.py` takes `--work`** like every other tool, and purges only the work folder it resolved (#132).
- **The rulebook skeleton** (`tools/templates/rulebook.md`), whose migrations wording passes readiness (#129).

### Changed

- **`exclude` is enforced.** Every tool honours it and refuses an entry that names no path or lies inside an
  iWork package; matching ignores case and Unicode form; `audit.py` records an excluded file without opening,
  hashing or downloading it.
- **The rulebook routing check** reads the whole rulebook statement by statement, names the migrations folder in
  any case with or without its slash, and still flags a sentence that negates the routing, with advice on how
  to word it.
- **`audit.py` records a document's first placement** in `rename_history`, as the manifest schema describes;
  an older manifest is read as before and gains it on the document's next move.
- **Fail loud:** `extract.py` refuses a missing `--ocr-bin` and names a missing OCR tier on an image record,
  and `--retry-failed` recovers it; `plan.py check` refuses a row with no destination; `light`, `migrate` and
  `return` refuse to overwrite a plan that holds the owner's decisions; `--out` is refused inside the folder,
  compared ignoring case.
- **`isolation.py scan`** refuses only an expansion left undone (`~user`, an unset `$NAME`), so a path through
  iCloud Drive (`com~apple~CloudDocs`) is accepted (#132).
- **The prose** closes the 47 gaps the cold reader found (#129, #130): the order of the audit and the
  interview, the card categories, third-party personal data, the terms file, the engines' canaries, how the
  wiki subagents are isolated (the coordinating session's own instruction and memory files are scanned, and a
  hit stops the stage), who writes the fixed pages, acceptance order, the Bin, iWork figures, and company
  folders (a bookkeeper, a compliance officer and a marketing manager in the catalogue, VAT in the money rules).

### Migrating a deployment

Nothing is required to advance the pin. A deployment that runs the preparation tools should audit once more
(first placements), and check that each `exclude` entry still names a path.

### Placeholders

No placeholder was added, removed or made required: each of the eight prompt templates under
`project-onboarding/archetypes/` uses the same set as at v12.0.0.

## v12.0.0 (2026-10-05)

A **MAJOR**: a semantic change to a documented rule (#126), with a new hand-off check and a roll-up reader
that follow it. The reference deployment's owner decided that no job moves a file between projects. A
deployment may propose or suggest a move, and the owner makes it by hand. Staging files in the migrations
folder still happens during preparation, through plan rows the owner approves, and a folder is onboarded only
once that folder is empty. Its generated pages also stopped using em dashes, which `readiness.py` had to learn
to read.

### Breaking (MAJOR)

- **No job moves a file between projects** (`wiki-maintenance`'s rule that a project files within itself,
  `folder-curation`, `user-onboarding`, `pre-onboarding`, `project-onboarding`, the user-synthesis archetype
  and `ARCHITECTURE.md`, #126). Before, once a folder was maintained, the user-tier synthesis proposed a
  migration and, the owner approving it, the holding project's approved curation plan carried it out, staged
  in `<migrations folder>/<Project>/`. Now a file that belongs to another project is filed in the folder like
  any other, the synthesis still proposes the move with its evidence, and the owner makes it by hand. A
  deployment surfaces the proposal as a suggestion, and executes no guarded cross-project move and stages no
  plan from an approval. What stays: during preparation a curation round stages files in the migrations
  folder through plan rows the owner approves (`plan.py migrate` and `return`).
- **A folder is onboarded only once its migrations folder is empty** (`project-onboarding` step 1,
  `pre-onboarding`'s hand-off contract). Onboarding stops while the folder holds any file, an evicted iCloud
  placeholder included, names the count per target project, and never moves files between projects to clear
  it. Before, nothing required the folder to be cleared.
- **The user-synthesis templates say who makes the move** (`synthesise.md` and `reconcile.md`, #126): the
  owner makes any move by hand, and a template only suggests it. The reply may still carry `migration`, and its
  shape is unchanged.
- **Skill descriptions** (frontmatter, #126): `folder-curation` now says approved plans stage files for another
  project while a folder is being prepared, and `user-onboarding` says the synthesis suggests migrations for the
  owner to make by hand. No skill is renamed.

### Added (MINOR)

- **`migrations_folder_cleared`, a hand-off contract item**
  ([`pre-onboarding`](plugins/ai-os/skills/pre-onboarding/SKILL.md#the-hand-off-contract),
  [`readiness.py`](plugins/ai-os/skills/pre-onboarding/references/tools.md#readinesspy), #126). The folder's
  migrations folder (`migrations_dir`, `_Migrations` by default) must hold no file. `readiness.py` lists names
  and never opens a file; `.DS_Store` and empty folders do not count, and an evicted iCloud placeholder does.
  The finding names the count per first-level subfolder, one for each target project. A folder it cannot list
  is reported as not verified, never as cleared.
- **The roll-up reader follows the dashless form** (`readiness.py`, #126). The reference roll-up now writes
  `- **<when>**: <titles>. <note> (<links>)`, or `- **<when>**: <titles> (<links>)` with no note, a colon where
  it had a spaced em dash in the intro, the entries and the empty-roll-up banner. `parse_entry` and the banner
  check read it, still read the em-dash form a deployment that has not re-rendered writes, and still read the
  note-only colon form of the fixture. A colon line that fits both colon forms is read as titled; the rule and
  its one misreading are in the tool reference. Each form is pinned in `tests/test_readiness.py`.

### Changed

- **The fixture's report carries the new finding.** The fixture stages a file in its migrations folder for the
  audit, plan and wiki tools, so `tests/expected/readiness.json` now reports exactly that one finding and
  `regen_expected.py` fails on any other. The readiness tests start from the fixture with that file, its
  extract record and its card removed.

### Migrating a deployment

Advance the pin as [*Consuming a pinned release*](plugins/ai-os/ARCHITECTURE.md#consuming-a-pinned-release)
sets out, after these steps:

1. **Stop carrying out cross-project migrations.** Surface a user-synthesis item that carries `migration` to
   the owner as a suggestion, with its two projects, its files and its evidence, and let the owner make the
   move by hand. Remove any step that turns an approval into a staging plan, or into a guarded move, in the
   holding project once the folder is maintained.
2. **Refuse to onboard a folder whose migrations folder holds any file.** Name the count per target project
   and wait for the owner to clear it by hand; never move files between projects to clear it. A deployment's
   own check of the hand-off contract refuses such a folder the same way, and `readiness.py` reports it as
   `migrations_folder_cleared`. A prepared folder that still has files staged there goes back to the owner.
3. **Re-read the two user-synthesis templates** and re-stamp any copy a project made of them
   ([`archetypes/user-synthesis/`](plugins/ai-os/skills/project-onboarding/archetypes/user-synthesis/)): the
   wording changed, the reply shape did not.

Nothing is needed for the roll-up reader: a deployment that has not re-rendered its roll-ups still passes, and
one that has passes too.

### Placeholders

No placeholder was added, removed or made required: each of the eight prompt templates under
`project-onboarding/archetypes/` uses the same set as at v11.0.0.

## v11.0.0 (2026-10-04)

A **MAJOR**: page contracts, until now an opt-in profile, become mandatory for every page type, and
several documented rules and archetype outputs change with them. Preparing a lived-in folder for
the system had been done with one-off scripts written for one folder; it is now a method any agent
can follow, in a new entry skill, `pre-onboarding`, which bundles the tools that do the exact parts
and runs the existing skills as its components. The rule it builds a wiki under (how the wiki is
divided, who writes each page, how a page is accepted) is single-homed in `wiki-maintenance` as
**the core wiki rule**, and it binds every wiki, prepared or not. That rule, the move plan's new
action and its Bin, and the changed outputs of the folder-curation jobs are semantic changes to
documented rules and archetype outputs, so a deployment advancing its pin has work to do, set out
under *Migrating a deployment* below.

### Breaking (MAJOR)

- **The core wiki rule** ([`wiki-maintenance`](plugins/ai-os/skills/wiki-maintenance/SKILL.md#the-core-wiki-rule),
  #99): one new section holds how a wiki is divided, written and accepted, the same whether the wiki
  is being prepared, onboarded or maintained. `wiki-onboarding` and `pre-onboarding` apply it and
  every maintenance pass keeps it. Its parts follow.
- **Sections by responsibility.** A wiki is divided as the office running the owner's affairs would
  divide the work, one section per area of responsibility, proposed with its routing by a librarian
  and agreed by the owner. The owner's folders are mirrored only where that does not break the
  division (the Schema's routing maps each folder onto its section), and a matter filed in two
  places has one home page. The recommended layout's "domains" become "sections".
- **One professional per page.** Every page is given the one professional best suited to it, from a
  new catalogue, who sets its voice and its first questions: tone only, with facts, sources,
  identifiers and format rules unchanged. A section may have several professionals; a page has
  exactly one. Maintenance keeps it: ingest writes as the page's professional, and a page it would
  create in a section that names several, or that needs a new section, it proposes for the owner to
  agree rather than writing it. Changing a page's professional is a Schema change the owner agrees.
- **A page contract for every section the layout does not mark `fixed`**: its reader, its questions
  most important first and the fields every page carries, in the Schema before the section's first
  page is written; a required field with no evidence shows as **not on file**. Before, contracts
  belonged to an opt-in profile. That profile, formerly *contract-driven pages*, is now
  *deterministic rendering*: still optional, it governs only how the pages it names are produced,
  and those pages declare a render type finer than their section. Its old anchors still resolve. The
  Schema page records, per section, its purpose, contract and update triggers, and per page its
  professional, in tables with fixed headers that compile into a machine-readable twin.
- **A rationale block per page.** Every page has exactly one five-line block in
  `_Audit/wiki-rationale.md` (reader and use; professional lens; shape; changed from the previous
  page; left out or flagged), written by whoever writes the page and rewritten when its shape,
  contract or professional changes. A page with no block is a finding; reconcile counts the
  sections with no contract, the pages with no single professional and the pages with no block.
- **Acceptance by a model that did not write the page.** Before a page is first handed to the owner
  it is accepted in two lenses, the owner's and its professional's, both played by a model other
  than its author. Each verdict is recorded with the models that wrote and reviewed the page; one
  whose reviewer is its author is refused, a guard held in code rather than prose. Acceptance is
  reported as its own state (accepted, not recorded or refused), never folded into a passing check,
  and a page is accepted again after a change to its anatomy, contract or professional. Before, an
  independent reader review applied only to contract-driven pages.
- **Recurring dates live in page frontmatter.** A new canonical key, `recurring: [{date, note}]`,
  holds a date that comes round every year, and the Deadlines roll-up reads
  it; such a date is never kept by hand in a table on the Deadlines page. The date is `MM-DD`, month
  first, or a day and a month name (`5 April`, `April 5th`, `5 Sept`); any other numeric form is
  refused, and the roll-up shows the month in words, so a date written the wrong way round is
  visible. A page the Schema marks `derived` (the Deadlines roll-up, an open-questions list built
  from the pages) holds nothing written by hand: readiness reads the Deadlines page against the
  roll-up's own output and reports every line it does not render from the pages' frontmatter.
- **A project files new items within itself**, replacing "a wiki is self-contained". Every new item
  is filed inside its project by the project's own routing, and one that seems to belong to another
  project is filed or flagged where it arrived, like any other: no project routes an item to
  another. Moving files between projects is a **migration**: proposed by the owner's user-tier
  synthesis once a folder is maintained (or by a curation round while it is prepared), approved by
  the owner, and carried out by the holding folder's approved curation plan. No ingest or reconcile
  moves a file out of its project.
- **Outside knowledge, dated rules, rich pages and history pages.** A professional's general
  knowledge is labelled as such and never fills a row that cites a document. A dated rule (a rate,
  threshold, fee or deadline) is checked against the issuing authority's own publication, which the
  page names with the date of the check, or flagged as unchecked. Records go in tables, series and
  shares in charts, histories and validity periods in timelines, every visual drawn from the page's
  own cited table beside it and rendered by a tool, never by hand. A page in a section marked
  `history` closes with a coverage table, one row per source folder.
- **The file-ingest templates write to the contract and the voice** (`ingest.md` and
  `reconcile.md`, #101): both now say that every page, rendered or not, is written to its Schema
  contract and in its professional's voice, and the block that carries `{page_contracts}` is
  retitled *Optional deterministic rendering*. The placeholder and the output shape are unchanged.
- **The move plan**
  ([`move-plan-schema.md`](plugins/ai-os/skills/folder-curation/references/move-plan-schema.md),
  #100). A new action, `rmdir`, removes a folder that holds nothing but `.DS_Store`; it carries no
  evidence hash, and a folder `rename` now carries none either (it was the id of the folder's
  manifest listing). `status` gains `proposed`, which a proposer may seed: the owner's approval sets
  `pending` and a decline `skipped`. A path ending in `/` names a folder. A `move` the proposer
  cannot place (a root stray) is proposed with `to` empty, filled with the owner's choice before
  approval, and a `move` that stages a file for another project records its copy kind in `kind`.
- **The executor** (`folder-curation`
  [step 5](plugins/ai-os/skills/folder-curation/SKILL.md#5-execute-deterministic-guards-not-judgement),
  #100). Every row is dry-run before anything moves. Rows run in `seq` order: renames, moves and
  `create` rows, then conversions, then `rmdir` rows, and deletes last, in a phase of their own. A
  file or package must hash to its row's evidence before it moves (a package hashed exactly as the
  audit hashes it), and nothing is overwritten. Nothing is unlinked: a deleted copy and a removed
  folder go to the Bin, each with an undo entry saying where. The delete phase is refused until
  every other approved row is done and the folder has been re-audited since, and each delete row is
  re-verified against that fresh manifest (the path still `redundant`, a separate canonical copy
  still there, both still hashing to the evidence). The executor still takes its rows only from the
  approved plan, but now reads that fresh manifest too, where it used to read nothing but the plan.
- **The re-audit proof is a (path, hash) diff, and it covers deletes** (`folder-curation`
  [step 6](plugins/ai-os/skills/folder-curation/SKILL.md#6-verify-by-re-audit), #100). The pairs
  that disappeared and appeared must be exactly the executed rows'; departures from
  `_Migrations/<Project>/` after another project collects its files pass only as an explicit
  allowance for that path. After the delete phase the same proof runs again from the same baseline,
  so each deleted copy's pair must go too, and nothing else.
- **iWork is read directly** (`folder-curation`'s
  [class policy](plugins/ai-os/skills/folder-curation/SKILL.md#class-policy-defaults-the-rulebook-may-override-per-folder),
  #100; the folder-curation archetype's `jobs.yaml`, #101). The `iwork` class becomes
  `{hash: full, ingest: read}` (it was `ingest: after_convert`), a package counting as one item, and
  a new `other` class keeps `after_convert` for the other proprietary formats. A deployment whose
  own ingest cannot read iWork overrides `iwork`, back to `after_convert` for example: a job never
  depends on a skill's bundled tools.
- **The audit job's output** (folder-curation archetype `audit.md`, #101). An iWork package is one
  entry, never walked into, its id given by the manifest's package hash rule and its entry carrying
  `package`. The walk covers `_Migrations/<Project>/`: each live path there sets the entry's
  `migrating` flag, with the project in `migration_target`, and stays counted until the other
  project collects it. `AUDIT.md` gains section 11, *Migrating out*, and *Needs a look* moves from
  11 to 12.
- **The curate job's output** (folder-curation archetype `curate.md`, #101). `curate` never emits
  an `rmdir` row: one is proposed only once the owner has approved the moves that empty its folder,
  so no folder is removed on the strength of a move the owner declined, and a return round's `rmdir`
  for `_Migrations/<Project>/` likewise comes only after its moves are approved. A folder `rename`
  row returns an empty `evidence`, and `create` rows sit with renames and moves at the head of the
  order.
- **Skill descriptions** (frontmatter, #99 to #101). No skill is renamed, but the descriptions of
  `wiki-maintenance`, `wiki-onboarding`, `folder-curation`, `project-onboarding`, `user-onboarding`
  and `file-preprocessing` change with their roles: a person preparing a lived-in folder starts at
  `pre-onboarding`, which runs `folder-curation` and `wiki-onboarding` as its components, where
  before `project-onboarding` sent a messy folder to `folder-curation` first.

### Added (MINOR)

- **`pre-onboarding`, a new entry skill**
  ([`SKILL.md`](plugins/ai-os/skills/pre-onboarding/SKILL.md), #98). It prepares a lived-in
  folder in an interactive session on the operator's machine, in nine steps: audit; interview the
  owner and write the rulebook and its twin; curation rounds, each approved by the owner (through
  `folder-curation`); extract the full text of every document; open the gate to the engines (a scan
  for the operator's isolation terms and a canary per engine); the vision lane and a summary card
  per document; build the wiki (through `wiki-onboarding`, with a table of who holds the pen at each
  stage); check readiness; hand off to `project-onboarding`. It states the engine isolation, the
  identifier policy (passwords and activation codes never written) and the lessons of real folders:
  iWork read without the apps, broken PDF text layers detected and read again by OCR, a
  deterministic repair preferred to re-running a model, bundles rebuilt after any migration.
- **Its bundled tools** (`pre-onboarding/tools/`, #87 to #90, #92 to #95 and #97): standard-library
  Python 3.9 or later plus one Swift helper for Apple Vision OCR, generic and settings-driven.
  `audit.py`, `settings.py`, `plan.py`, `extract.py` (with `iwa.py`, which reads iWork packages, and
  `page_ocr.swift`), `isolation.py`, `vision.py`, `cards.py`, `refs.py`, `wiki.py`, `readiness.py`,
  `engines.py` and the shared `common.py`, with the role briefs and card instructions in
  `tools/templates/` and JSON schemas for cards and OCR. The tools share common flags: `--root`,
  `--settings-dir`, `--work` (working state, kept outside the folder), `--out` and
  `--read-only-root`, which refuses any write under the root. They are tested against a fictional
  fixture folder with frozen expected outputs (`tests/regen_expected.py --check`).
- **agy's prompt limit, measured**: on agy 1.2.16 with `gemini-3.1-pro-high`, agy cuts a user message at about
  192,000 UTF-8 bytes of prompt text, silently (exit 0, a successful result), for ASCII and CJK alike, so a
  card could be written from part of a document. `engines.py` now refuses a prompt over 180,000 bytes of its
  text before the call (`AGY_MAX_PROMPT_BYTES`; the earlier check counted the serialised message against
  200,000, which let ASCII through above the cut), and raises `PromptCut` when the stream shows the model
  reading agy's stored copy and being refused a command. `cards.py`'s agy defaults for `--small-chars`,
  `--batch-chars`, `--section-chars` and `--single-max` fall from 60,000 to 50,000 characters, which is 150,000
  bytes of CJK text beside the largest card prompt's overhead. A real agy 1.2.16 capture also settles the
  stream events: its tool steps (`step_update` with `step_type: "tool"`) were not seen as tool events by the
  earlier check, which had guessed their shape, so a tool step now discards the reply in every lane (any step
  other than a user input, an agent response or agy's own system message counts, whatever its keys), and the
  vision lane accepts only the steps that open its images (`view_file`, `list_dir`, `find_by_name`) and only for
  paths inside the call's own folder, whatever key or spelling names them (a `file:` URL is parsed, and any
  value that names something in the folder, a link included, is judged by where it leads). agy is also no longer given `--json-schema`, which in plan mode sent
  the model through plan mode's workflow (a written plan, `finish` steps, a reply asking for approval before
  the JSON): the schema's text goes in the prompt, counted by the size limit, and `cards.py` still checks every
  card. Only the environment-variable lists remain provisional (#125).
- **Engine isolation, settled on the operator's machine** (#91): both engines run with the machine's own home
  and its one login. Each keeps its login as a file there, and a per-project state folder would need that file
  copied, so none is used; isolation comes from what each call is given and denied. codex runs ephemeral, with
  the user's config and rules ignored, memories and tools off and an empty folder, but its global
  `~/.codex/AGENTS.md` still reaches the model, so the isolation scan reads it for the operator's terms. agy
  gives the model no memories, conversation summaries or instruction files. The canary is a positive control:
  each run plants a fresh invented name in the engine's context and passes only a reply that repeats it and
  does not read as a refusal. The old "list your context" canary passed on a refusal while proving nothing.
- **The settings twins** (#89). A folder's rulebook and its wiki's Schema page each get a
  machine-readable twin in `.familyai/`: `rulebook.json`, written with the rulebook, and
  `wiki-schema.json`, compiled by `settings.py compile` from the Schema's fixed-header tables
  (Layout, Routing, Page contracts and an optional Page professionals). Each records its source's
  sha256, so an edited source makes its twin stale, never silently wrong, and every tool refuses a
  stale twin.
- **The skill's references** (#98): `references/cards.md` (the card contract: what a card holds,
  the whole-chunk join, the isolation checks, repair from the card's own source),
  `references/settings.md` (both twins and their stale states) and `references/tools.md` (every
  command, flag, output and exit code).
- **The hand-off contract** (#97 and #98): what a deployment relies on when it onboards a prepared
  folder, checked by `readiness.py`. A current manifest; an extract record and a card for every live
  document `extract.py` reads, no card naming an isolation term its own document lacks; each
  engine's canary passed, or reported as not verified; the wiki at `<folder name> Wiki/` with
  `00 Index`, `01 Deadlines`, `90 Schema` and `91 Log` and a clean `wiki.py check`; every page
  accepted; derived pages holding nothing hand-written; the rulebook identical in `CLAUDE.md` and
  `AGENTS.md`, naming the wiki folder, reserving the deployment's rulebook filenames (`GEMINI.md`
  included) and routing no new file to the migrations folder; fresh twins; no scratch left in
  `_Audit/`. Each item reports a count or a named not-verified state.
- **The professional catalogue**
  ([`professionals.md`](plugins/ai-os/skills/wiki-maintenance/references/professionals.md), #99): a
  flat menu, for personal and company pages alike, of professionals with the pages they suit, their
  deliverable and tone, their first questions and their usual visuals, and a note on choosing.
- **`wiki-onboarding`'s stages** (#100). Step 2 is the librarian's proposal of sections, routing and
  each page's professional; step 3a has each section's contract drafted by its professional and
  agreed by the owner; a new step 4a drafts every page when every document has already been read (a
  fixed page map, fresh bundles, a persona brief per page, parallel agents, a checker each agent
  runs, and JSON returns from which only the coordinator writes the shared pages); step 6 runs the
  two-lens acceptance. The wiki folder's name is the deployment's `{wiki_dir}`, set once in
  configuration; in preparation the wiki is built in the session, and no job runs on it until the
  folder is onboarded.
- **`folder-curation` as a component of `pre-onboarding`** (#100): still the method the preparation
  tools implement and the archetype's jobs keep running. New in it: files bound for another project
  are staged in `_Migrations/<Project>/` at their original relative paths, with a `review.tsv`
  listing each staged path's copies left behind, and a return migration brings them back; a
  boundary is confirmed with the actual files from the manifest, never with a description; and a
  re-audit after each round is expected to reveal a second round of redundancy.
- **The manifest schema's additions**
  ([`manifest-schema.md`](plugins/ai-os/skills/file-preprocessing/references/manifest-schema.md),
  #100): an extension rule (within a version an optional field may be added, and a consumer ignores
  what it does not know), under which `/2` gains `package`, the `migrating` flag and
  `migration_target`; and the package hash rule, one definition for every producer, executor and
  consumer. The schema string stays `family-ai-preprocess-manifest/2`, and every earlier `/2` file
  stays valid.
- **Proposed migrations in the user-synthesis archetype**
  ([README](plugins/ai-os/skills/project-onboarding/archetypes/user-synthesis/README.md#proposed-migrations),
  #101). `synthesise` and its `reconcile` twin may raise a cross-project migration as an ordinary
  `needs_a_look` item carrying an optional `migration` object (`from_project`, `to_project`,
  `paths`, `pages`) for the owner to approve or decline; most runs propose none, and no placeholder
  is added. The synthesis never moves a file: an approved migration is staged by `folder-curation`
  in the holding project.
- **`project-onboarding`, one flow for cold and prepared folders** (#101). Step 1 tells the starting
  state from what is on disk: a folder carrying `.familyai/rulebook.json` is prepared when it meets
  the hand-off contract (checked with `readiness.py` or the deployment's own check), and a messy
  cold folder is sent to `pre-onboarding`. A prepared folder is validated, never rebuilt, and its
  config is written from the twins. A new step 4 seeds the jobs from the state the folder arrives in
  (the ingest gate, the human-edit guard, the audit's previous pass), so the first tick is quiet;
  the later steps are renumbered 5 to 7.
- **`ARCHITECTURE.md`** (#101): a reviewer is never the author, held by the code that records a
  verdict; a new section, *Preparing a folder before onboarding*, on the sequence and where
  preparation ends; one login per machine, each call's context isolated and no project copying a
  login or token file; and cross-project migrations proposed by the user-tier synthesis and approved
  by the owner. `user-onboarding` follows suit: an identity needs no model login of its own.
- **Repo docs** (#101). `AGENTS.md`'s "skills are conventions, not code" gains an exception for
  operator tools a skill bundles for an interactive session (`adversarial-review`'s `agy-review`,
  `ai-writing-audit`'s tools and `pre-onboarding`'s), and the versioned interface now names every
  skill's frontmatter contract. The README lists the three ai-os entry points: `pre-onboarding`,
  `project-onboarding` and `user-onboarding`.
- **CI** ([`lint.yml`](.github/workflows/lint.yml), #103): a `pre-onboarding-tools` job runs the
  tools' unit tests on Python 3.9 and the latest 3.x with the standard library alone, each skipped
  tier named in its skip reason, then checks the frozen outputs on the fixture.

### Migrating a deployment

Advance the pin as [*Consuming a pinned release*](plugins/ai-os/ARCHITECTURE.md#consuming-a-pinned-release)
sets out, after these steps:

1. **Give every section that is not `fixed` a page contract** in its wiki's Schema
   ([a page contract for every page type](plugins/ai-os/skills/wiki-maintenance/SKILL.md#a-page-contract-for-every-page-type));
   where the Schema is compiled, use the
   [fixed-header tables](plugins/ai-os/skills/pre-onboarding/references/settings.md#the-schema-pages-tables).
2. **Name one professional for every page** in the Schema
   ([one professional per page](plugins/ai-os/skills/wiki-maintenance/SKILL.md#one-professional-per-page),
   from [the catalogue](plugins/ai-os/skills/wiki-maintenance/references/professionals.md)).
3. **Write a rationale block for every page** in `_Audit/wiki-rationale.md`
   ([the rationale block](plugins/ai-os/skills/wiki-maintenance/SKILL.md#the-rationale-block)).
4. **Record acceptance for every page**
   ([acceptance](plugins/ai-os/skills/wiki-maintenance/SKILL.md#acceptance), run as
   [`wiki-onboarding` step 6](plugins/ai-os/skills/wiki-onboarding/SKILL.md#6-reader-acceptance-the-owners-lens-and-the-professionals)
   sets out), and hold the reviewer-is-not-author check in the code that records a verdict
   ([the three layers](plugins/ai-os/ARCHITECTURE.md#the-three-layers-of-a-job)).
5. **Move hand-kept recurring tables into page frontmatter** as `recurring:` entries, and teach the
   deterministic Deadlines roll-up to read the key
   ([canonical frontmatter](plugins/ai-os/skills/wiki-maintenance/SKILL.md#canonical-frontmatter--the-keys-the-deterministic-sweeps-read)).
6. **Make every rulebook stop routing new files to another project**
   ([rules that keep it safe](plugins/ai-os/skills/wiki-maintenance/SKILL.md#rules-that-keep-it-safe));
   migrations come from the user-tier synthesis instead
   ([proposed migrations](plugins/ai-os/skills/project-onboarding/archetypes/user-synthesis/README.md#proposed-migrations)).
7. **Override `iwork` if your ingest cannot read iWork**, and classify the other proprietary
   formats as `other`, in each project's
   [`jobs.yaml`](plugins/ai-os/skills/project-onboarding/archetypes/folder-curation/jobs.yaml).
8. **Accept `rmdir` in plan executors**, and the plan's other changes listed above
   ([`rmdir` and the Bin](plugins/ai-os/skills/folder-curation/references/move-plan-schema.md#rmdir-and-the-bin)),
   and hash a package by the
   [package hash rule](plugins/ai-os/skills/file-preprocessing/references/manifest-schema.md#entry-fields).
9. **Re-read the archetype outputs that changed**, and re-stamp any copy a project made of them: the
   folder-curation `audit.md` and `curate.md`
   ([`archetypes/folder-curation/`](plugins/ai-os/skills/project-onboarding/archetypes/folder-curation/)),
   the file-ingest `ingest.md` and `reconcile.md`
   ([`archetypes/file-ingest/`](plugins/ai-os/skills/project-onboarding/archetypes/file-ingest/)),
   and the user-synthesis templates, whose reply a strict validator must let carry `migration`
   ([`archetypes/user-synthesis/`](plugins/ai-os/skills/project-onboarding/archetypes/user-synthesis/)).

### Placeholders

No placeholder was added, removed or made required: each of the eight prompt templates under
`project-onboarding/archetypes/` uses the same set as at v10.0.0.

### Still open

The engines' environment-variable lists stay provisional until #125 records which variables each engine reads;
the skill marks them where they are used. Everything else the milestone left open is settled: the isolation
spike (#91) in the skill's engine isolation section and `engines.py`, the chart rendering matrix (#102) in
`portable-markdown`, and the proof on a real prepared folder (#104), which found the tool fixes listed above.

## v10.0.0 — 2026-09-28

A **MAJOR** (reference implementation family-ai-os v2.7.4): a semantic change to a documented rule.
"Update the pages the source touches, writing into the existing sections" left the *shape* of the
update open, and a bulk drop into the reference implementation answered it with a dated batch section
at the foot of each existing page — facts stranded below the tables and summaries that should have
learned them. The rule now says what an update is, and the periodic pass gains a duty to undo the old
shape.

- **Integrate, never accrete** (`wiki-maintenance` core loop step 3, `file-ingest/ingest.md` step 3):
  synthesise into the existing page first; put each fact in the section that already tracks its kind
  (the table row, the list, the line it supersedes — correcting that line rather than stacking a newer
  one beside it); create a page only when no existing page covers the topic, placed where it fits.
  **Never open a heading named for the run, its date or the batch.** An event-dated heading is
  structure; the Log stays the one run-dated page.
- **The page must be in view — a stated precondition.** An edit made without reading a page can add
  to it but never correct it. For every existing page ingest may write (the Index included), a
  deployment gives it the whole page (in the gather report, or through a Read tool) or a section-level
  addition that lands a fact in a named section and can set the page's frontmatter (the reference
  implementation's `append` under a heading listed verbatim in `{wiki_structure}`). The addition places
  a fact; the next pass that sees the page whole corrects any line it contradicts. The template's
  shipped output shape is still `create | update`, so a template consumed unchanged must show every
  page it may write in full. A deployment that cannot meet this for a page withholds that page's
  sources, and reports why, until it can. If one reaches the model anyway, it leaves the source
  unhandled (no filing, no page write) and names the missing precondition in `log_entry` — it never
  rewrites a page it has not seen.
- **Reconcile folds accretion back** (`wiki-maintenance` reconcile, `file-ingest/reconcile.md` step 1),
  on affirmative evidence only: a section whose heading names the ingest itself (the job's own name,
  usually with the run's date), every fact under which is of a kind one of the page's other sections
  already tracks. Any other heading, dated or not, is structure and stays. On a page seen whole, the
  facts move into their topical sections, contradicted derived lines are corrected (a
  `provenance: manual` line never is), duplicate sections merge and the emptied container is dropped,
  citations and manual content carried verbatim and the shrink tripwire still applying. A page seen
  only in part is left alone and raises nothing.

Migration: re-reconcile any twin derived from `file-ingest/ingest.md` or `file-ingest/reconcile.md`.
No placeholder, output shape or layout changed, but check the ingest precondition: if your ingest is
shown some existing pages only in part, add a section-level addition that can also set frontmatter,
or hold those pages' sources back until it can see them whole.

## v9.0.0 — 2026-09-24

### Breaking

- Private wikis use `subject-clinical` as their sole, default content depth. Full clinical and other
  personal content may appear on relevant authorised pages; remove the other depth modes and the
  former subject-page-only ceiling. Migrate existing Schema settings before enabling the new method.
- Full source-supported identifiers (`stated`) are now the default. Explicit owner restrictions,
  project/identity access and excluded source paths still apply. Onboarding and archetype prompts
  follow the same policy; the identifier evidence requirements are unchanged.

## v8.0.0 — 2026-09-21

### Changed

- **Breaking:** evidence-bearing identifier completion now requires matching
  kind **and** holder-or-issuer, replacing the previous kind-or-institution rule (#77).
- Wiki maintenance defines the money-table counting basis, source checks before absence claims,
  explicit source disagreements, whole-record roll-up restrictions and lexical-check exclusions;
  regeneration now reckons to live files immediately before rendering (#78–#81).

### Added

- Opt-in `subject-clinical` depth with Schema-authorised subject pages and an existence/last-entry
  outward ceiling; `measurements-only` remains available (#76).

## v7.0.0 — 2026-09-16

A **MAJOR** correction to `adversarial-review`: remove the MiniMax reviewer leg because the method no
longer assumes that subscription is available. The remaining paths are Antigravity CLI, Claude and
Codex. Antigravity is named as the multi-model execution path it is, and reviewer eligibility follows
the model it actually serves rather than treating the CLI itself as the Gemini model family.

## v6.7.1 — 2026-09-15

A **PATCH** correcting the contract-driven wiki guidance after independent review.

- Name hub/facet index generation as the consumer of `entities` frontmatter, make the reader-acceptance
  hand-off sequence explicit and repair two awkward prose wraps.

## v6.7.0 — 2026-09-15

A **MINOR** introducing an opt-in contract-driven document-wiki profile. Existing body-based wikis,
provenance values and incremental user-synthesis behaviour remain valid.

- Schema-owned per-type contracts, optional `{page_contracts}` context and advertised `page_facts`
  output, deterministic briefing anatomy, dated owner overlays and project-owned renderer wiring.
- Durable extracts keyed by source, purpose and version; model provenance, gap-directed rereads,
  validated restart joins and named degenerate backend outcomes.
- Typed identifier policies, dated series, citation-derived facets/hubs and measurements-only depth;
  context-crossing restrictions, evidence-bearing enrichment and sync-safe publication guidance.
- Scoped render verification, independent reader acceptance, event/action versus record-gap rules,
  rulebook-copy checks and case-aware curation. Case-specific personas and thresholds stay in Schema.

## v6.6.0 — 2026-09-03

A **MINOR** for `ai-os`, from a real preprocessing run over a family backlog. Six findings, each
about the seam between a model's answer and what the system does with it — none about the reasoning
itself.

- **A redaction guard where the answers cross into the deterministic side** (`ARCHITECTURE.md`,
  new section; `file-preprocessing` step 8): the last-4 rule and the sensitivity depths were only
  ever *prompt instructions*, and a model holding the document quotes the number it was told not to.
  They are now a deterministic guard with four stated properties — at the crossing rather than
  inside a model call *or* at each write (a filename built from an unguarded field puts the number
  on the filesystem before any write-time guard sees it), typed targets rather than a digit hunt
  (`reference_numbers` is a field the schema wants populated), every redaction counted and reported,
  and outright exclusion enforced by the gate rather than the guard. The guarded set is *named*
  rather than gestured at — `parties` and each `connections[].relation` included, being the two a
  guard written from memory omits and the two a model most naturally qualifies with the number it
  just read, alongside the text of anything the run *raises* — `owner_action` above all, since
  naming which account to go and find is exactly what it is for, and the ledger it lands in is read
  by people and by later runs. The chain from the curation interview's answer to the enforcement point
  is stated end to end; the four prompt templates that carried the rule now point at it instead of only asserting
  it.
- **A chunked reasoning step's answers are reconciled before any is applied** (`ARCHITECTURE.md`,
  `file-preprocessing`): near-identical inputs are where a model returns one answer for two files or
  a path it tidied on the way out. A missing answer is visible and retryable; an answer attached to
  the *wrong* file is a confident, well-formed, undetectable error. Answers are matched by an
  engine-issued id, the returned set must equal the requested set exactly, and a chunk that fails is
  **retried halved, never applied in part**.
- **An escalation's key is the subject, not the file it was found in** (`ARCHITECTURE.md`): keyed by
  path, one concern about an entity mints one item per file that mentions it — eighty documents,
  eighty items, one answer between them. The lifecycle now names the per-*file* version of the
  re-raise defect it already closed for the per-*run* one, and requires a batch pass to answer from
  its own batch before raising the residue. `file-preprocessing`'s reduce step and `curate` both
  collapse repeated questions this way.
- **A closed `look` vocabulary** (manifest schema `look` field, both producers): the class is a
  value the engine routes on, the reason stays free text a person reads. A class recovered by
  keyword from a model's sentence makes "the same defect" a function of phrasing. Computed classes
  are never model-selected, and never duplicated into `look` either — `file-preprocessing` leaves
  the model only `flagged` (its other three classes are the engine's verdicts, and a file lands in
  exactly one look folder), while `folder-curation` keeps `look` for its three judgements —
  `misfiled`, `credentials`, `flagged` — classifying the escalations `curate` returns (the ones
  that feed the raised-item ledger), not `move-plan.csv` rows and not manifest entries, since only
  its deterministic `audit` writes the manifest. Curation's computed findings co-occur on one file
  and stay on the flags and fields the walk already sets.
- **The read ladder is a cost ladder, and a rung is checked against the material's languages**
  (`file-preprocessing`): descend only as far as a file needs, record the tier each file was read
  at, and treat an empty extraction from a file that should have text as a **capability gap to
  report** rather than a verdict about the document — a recogniser without the folder's script
  installed silently produces "unrecognisable" documents a person reads at a glance. The two model
  stages have opposite economics (per-file and high-volume vs whole-batch and strongest), so routing
  is declared per stage where a deployment can.
- **`unconverted` matches across the whole folder, not the same-folder sibling** (`folder-curation`,
  schema `convert_candidate`): exports live one folder over and under modified names, and a false
  `unconverted` becomes a `convert` row that makes a second export. Match *strength* now decides the
  flag — an identical normalised stem clears it, a stem that agrees only after a modifier is folded
  out leaves it set with the candidate named so a `convert` row points at what it doubts, and no
  match leaves it set with no candidate. A *confident* pairing is recorded and re-confirmed by the
  export's **content id**, so it survives the first descriptive rename — including the ones
  medium-depth curation itself performs; a *weak* one stays provisional and re-searches every pass,
  so the export the owner makes in answer to the flag is actually found. Candidates rank by same
  folder → nearest common ancestor → closest mtime, and an export is claimed once, so a single
  recent export cannot clear the flag across every year of an archive that shares its stem. The
  match stays deterministic: a content-level comparison would mean opening the format the class
  policy says cannot be opened.

`extraction` gains an optional `tier`, naming the rung of the read ladder that produced the text so
a run's spend can be attributed — `none` when no rung produced any, which is an outcome to count
rather than an absence. `file-preprocessing` also stops claiming Understand is its only
non-deterministic step: the whole-batch planning call and reduce are model calls too, and the guard
step is written against all three.

Additive throughout: no skill renamed or removed, no placeholder introduced or made required. The
new `look` and `convert_candidate` fields are optional, and the `look` vocabulary is extensible the
way flags are — a consumer ignores a value it does not know.

## v6.5.0 — 2026-09-01

A **MINOR** for `ai-os`: a new skill and archetype for the folder that sits between
`file-preprocessing` and `project-onboarding`, the lived-in one.

The onboarding flow went from "scan read-only" straight to "write the wiki", under a rule that the
owner's files are never reorganised. Adopting a real folder showed the gap: overlapping homes for
one subject, duplicate trees built by copying, strays at the root, AI outputs left beside the
documents they described, and formats the system cannot read. Onboarding that as-is writes the
ambiguity into the Schema; preprocessing it runs a conveyor over files the owner already filed.

- **New skill `folder-curation`**: audit (deterministic, repeatable, a hash-keyed manifest over the
  whole library with type classes, duplicate kinds, overlapping homes and drift) then curate
  (interview on a fixed ladder, a move-plan the owner approves row by row, execution under the
  shared move guards, verify by re-audit). Propose-only by default; a depth ladder
  (light / medium / full) the owner chooses and the plan never exceeds.
- **New archetype `folder-curation`**: a periodic `audit` that sits entirely below the determinism
  boundary, and an on-demand, propose-only `curate`. First archetype whose job may touch the owner's
  material, and only by proposing.
- **Manifest schema `/2`** (strict superset): `class`, `size`, `mtime`, `hashed`, `copies`,
  `overlap`, `generic_name`, `plan_ref`; flags `root_stray`, `unconverted`, `hygiene`. Duplicates
  keep the `/1` rule that a copy mints no entry of its own — copies of the same bytes share one
  hash, so a duplicate group *is* an entry, and `copies` carries its several live paths with the
  kind (`canonical`, `redundant`, `working_copy`, `pack`) that decides what may be done to each.
  The scan contract and the move guards move into the reference as the single home both skills
  cite.
- **`file-preprocessing` gains an in-place mode**: understand and rename listed files where they
  are, for curation's medium depth.
- **`project-onboarding`** gains the pre-onboarding branch (assess, curate if needed);
  **`wiki-onboarding`** gains four interview questions, the time-vs-topic routing rule and the
  People alias table; **`wiki-maintenance`** gains the outputs-placement rule (AI artefacts land in
  the wiki, never beside sources), sensitivity depth per domain, and the class policy in the gate.

No skill was renamed or removed; no placeholder became required (`curate.md` uses only the required
core). `manifest-schema.md` keeps its path; `/1` files remain valid.

Two documentation fixes ride along, unrelated to `folder-curation` and changing no contract. The
`coding` direction's README section claimed "Four skills" above five bullets, and
`iterative-acceptance` — shipped in v4.2.0 — had no bullet at all and was named in neither
`plugins/coding/.claude-plugin/plugin.json` nor `.claude-plugin/marketplace.json`; all three now
list the six skills that are actually there. And the `file-preprocessing` naming example now uses
an invented party name, per this repo's own generic-always rule.

## v6.4.0 — 2026-09-01

A **MINOR** for `productivity`'s `portable-markdown` skill: the vault-boundary section stops
recommending one fix and presents the decision it actually is.

v5.x told a generator to report an out-of-vault link as "a configuration finding, not a defect to
repair", and named a single resolution — root the Obsidian vault at the parent folder so the
documents fall inside it. That is sound where the parent is small. Driven on a real deployment it
was not: rooting the vault there would have taken it from 28 notes to 42 while pulling **1,585
PDFs** and every household folder into the file tree, so the owner rejected it and chose the other
resolution instead — keep the vault, state out-of-vault paths as text, and link only to other notes
in the vault. The skill had nothing to say about that choice, and its "do not repair" advice was
actively wrong once it was made.

What changed in `SKILL.md`:

- **Two resolutions, in a table with what each costs** — root at the parent, or name rather than
  link — with the deciding question named (how much lives beside the vault) and the measured
  numbers from the case behind it.
- **`outside_vault` becomes repairable *after* the decision, and must not be before it.** The old
  advice (report it apart from the repairable kinds) is now correct only for the pre-decision state,
  which is what it always meant; folding it in early still invites a mass rewrite of working links
  to satisfy a setting nobody has chosen.
- **Two reasons the conversion is cheaper than it looks**: these links usually carry the path as
  their own link text already, so backticking it loses nothing; and it retires most encoding defects
  by construction — every `%26` failure in that wiki was on a link that escaped the vault.
- **A new subsection on the escapes that do not work.** The Obsidian community plugin that reads
  outside the vault does it through code-block processors, not markdown links, so Typora renders the
  block literally and its manifest is desktop-only; and symlinking fails wherever a generator's own
  sweeps resolve a page's real path and skip what escapes the vault root — a visible problem traded
  for a silent one.

`REFERENCE.md` gains the matching *Escapes that do not work* table. No skill name, frontmatter
contract, archetype layout or placeholder changed.

## v6.3.0 — 2026-08-15

A **MINOR** for `productivity`'s `ai-writing-audit` skill: the catalogue is re-synced against the
August 2026 revision of Wikipedia's *Signs of AI writing* essay, and the sync itself becomes
deterministic — a machine-readable coverage map plus a checker that fails loudly when the essay
moves on.

The skill shipped in v3.1.0 (2026-07) and had not been touched since, while the essay kept
growing; the only guard was a prose "Last verified 2026-07" stamp, which is exactly the
silent-staleness shape `silent-failure-design` warns about — nothing distinguished "still
current" from "nobody looked". A section-by-section audit against the live essay (revision
1369390317) found roughly a dozen catalogued signs with no home in the skill, a drifted
vocabulary layer, four leaked-markup tokens the scanner did not know, and one internal bug:
REFERENCE.md's band map ended at §14 while a §15 sat outside every band, unscored.

What changed:

- **REFERENCE.md is renumbered §1–§20** (the §-numbers are internal, not part of the versioned
  interface) and absorbs the missing signs, each with a rewrite move: chat-mode leakage as a new
  near-decisive §3 (knowledge-cutoff *and* the newer source-availability disclaimers, direct
  address, refusal residue, unfilled placeholders); document mechanics (§6: Title Case headings,
  skipped levels, multiple top-level headings, `---` breaks, hollow tables); the "X rather than
  Y" third parallelism form; outline-like "Despite these challenges… Future Outlook" closers
  (§8); copulative avoidance promoted from an aside to §12; weasel attribution (§13);
  significance inflation and canned notability (§14, dissolving the old unbanded §15); elegant
  variation (§15, prose-only). The era-vocabulary tiers are rebuilt from the essay's current
  lists (the GPT-4-era tier grows from 6 to 19 words; a Grok tier is new), and a *Calibration*
  section carries the essay's ineffective indicators and signs of human writing — what not to
  flag.
- **`tools/audit.py`** gains a Band-1 chat-mode-leakage table, the new artifact tokens
  (`oai_citation`, `attributableIndex`, DeepSeek `【…†…】`, `:::writing` — all found *by doing
  this sync*), count-gated Band-2 patterns so ordinary English ("rather than", "serves as")
  cannot fire on a single innocent use (with length-scaled gates for the two commonest), and an
  aggregated Markdown document-mechanics check that strips YAML frontmatter before counting
  `---` breaks. Same invocation, same output shape, verdict thresholds unchanged.
- **`tools/coverage.json` + `tools/sync_check.py` (new).** Every essay section maps to a
  REFERENCE.md section or to a recorded exclusion (wikitext, citation forensics and
  Wikipedia-process signs are out of scope for general prose — excluded is a visible state, not
  an omission). Keys are the essay's rename-stable `{{shortcut|WP:…}}` anchors with
  path-qualified fallbacks; the synced revid lives in the map as the single machine-checkable
  home of "last verified". The checker makes one MediaWiki API request (parsed section tree +
  wikitext + revid — the tree is the ground truth, so headings inside the essay's quoted
  AI-output examples cannot pollute the inventory), diffs live keys against the map, and exits
  typed: 0 in sync, 1 coverage drift, 2 map error, 3 fetch failure (offline is loud, never
  "assume in sync"), 4 vocabulary-digest drift (soft — re-verify the era tiers). Stdlib-only,
  with `certifi` as an optional fallback for Pythons that ship without a CA store.

Interface: additive only — no skill rename, no layout change, `audit.py`'s invocation is
untouched, and the two new tool files are new surface. Hence MINOR.

## v6.2.0 — 2026-08-15

A **MINOR** for `coding`'s `adversarial-review` skill: `tools/agy-review`'s relay salvage
(introduced in v6.1.0) now also fires on exit 5, not just exit 3.

An audit of family-ai-os prompted by the v6.1.0 fix found the posting-step trap had hit at least
9 PRs since 2026-07-22, not just the two 2026-08-14 incidents that motivated the original fix —
and one of them ([#574](https://github.com/boshuthebuilder/family-ai-os/pull/574)) landed on a
bare **exit 5 (no-comment)** instead of exit 3: the composed-but-unposted verdict is the same
shape, but the harness's final log line didn't match the exit-3 `auto-denied` grep, so v6.1.0's
salvage — gated on that classification — never ran. The salvage attempt is refactored into a
shared `attempt_relay_salvage` function and is now gated only on whether a conversation id was
captured at all, called from both the exit-3 and exit-5 branches before either concedes. It is
safe to call when nothing was actually composed (an invented-command death, a window-burn): the
resumed run is told to run no tools, and the existing verdict-line gate refuses to relay a resume
with no `APPROVE`/`CHANGES-REQUESTED`, so a doomed attempt costs a few wasted seconds rather than
a false relay. No contract change — same invocation, same typed exits, same artifact-based
verification.

## v6.1.0 — 2026-08-15

A **MINOR** for `coding`'s `adversarial-review` skill: `tools/agy-review` now self-recovers from
the known exit-3 posting-step trap instead of just diagnosing it.

The trap: a headless soft-deny can land *after* the reviewer has composed its verdict — it reaches
for a command at the final (posting) step, gets auto-denied, and dies without ever printing the
marked review, leaving the verdict stranded inside the kept conversation. This fired twice on
2026-08-14 (family-ai-os PRs #854 and #856); the documented manual recovery (resume the
conversation, ask it to print the review verbatim, relay it via `gh pr comment`) worked both
times. The harness now performs that exact procedure itself on the exit-3, posting-step shape:
it resumes the run's conversation with a no-tools prompt, and — when a verdict comes back —
posts it under an explicit relay-provenance preamble and exits 0, with the result line saying the
comment was relayed. Exit 3 is unchanged for the case where the self-salvage also fails (or the
grants were genuinely missing at pre-flight); the manual procedure in the skill's *Follow-ups*
section remains the documented fallback. No contract change — same invocation, same typed exits,
same artifact-based verification.

## v6.0.0 — 2026-08-14

A **MAJOR** for `wiki-maintenance` (plus the layout guidance it shares with `wiki-onboarding`),
driven by two independent field reports from live deployments (2026-08-13 and 2026-08-14 — fifteen
distinct findings between them, every one observed in production). Both reports led with the same
finding: legacy frontmatter had made most of a wiki invisible to the sweeps, and nothing ever said
so — the exact silent-failure class the `coding` plugin's `silent-failure-design` skill names,
which the wiki machinery did not apply to itself.

Two documented rules change meaning — the MAJOR:

- **`provenance: manual` gains its one exit.** When a subsequently ingested source *confirms* a
  manual assertion exactly, ingest may upgrade the fact to `derived`, citing the new source
  (keeping a "first asserted by owner on DATE" trace where useful). Previously manual was never
  rewritten, full stop — which left confirmed facts permanently exempt from reconciliation despite
  a source of truth on file. Contradiction is unchanged: manual wins, discrepancy recorded, owner
  asked.
- **Last-4-only gains an owner override valve.** An explicit, dated owner decision recorded in the
  Schema (or the wiki's data-sensitivity page) is respected by the sweeps — a decided exception
  stops alerting. Previously the rule guaranteed a permanently re-raised flag the owner had
  already declined.

The additive bulk, by theme (`wiki-maintenance` unless noted):

- **Liveness over silence.** Adoption of the frontmatter contract is explicit: conformance is
  counted first in every reconcile and reported even when clean ("94/94 conforming" is a liveness
  signal); a page the sweeps cannot read is a finding, never a skip; a legacy wiki converges via a
  bounded migration batch per run. Referenced paths are resolved (frontmatter `source:`, body-level
  backticked paths, "file X exists at Y" claims) with the dead count reported, and `source:` paths
  are now mandated **project-root-relative**. The Schema is diffed against the directory it claims
  to describe. The Index must be the freshest page and reconcile against the queue's open items.
  An empty Deadlines roll-up renders a loud banner when derived pages exist, never a bare "None".
- **Filing.** On filename collision, hash-compare before renaming — identical bytes are a
  duplicate routed to deletion/review, never filed twice (the machinery `file-preprocessing`
  already keys on). The no-new-folders guard gains its escape hatch: check what the local
  convention predicts, and a genuinely-needed folder escalates *with the proposed path* as a
  one-click owner decision.
- **Provenance lifecycle.** A shrink guard on derived pages: an edit removing more than roughly
  half a page, or emptying Schema-declared sections, diverts to `.proposed.md` regardless of who
  last wrote the page. Extract-provenance pages are regenerated from the extract, never hand-edited.
  The transient-artefact rule extends beyond `.proposed.md` to `.superseded`/backup siblings.
- **Noise.** One raise per distinct blocker — a repeat increments a counter on the existing entry,
  never appends. Reconcile folds runs of no-op log entries into digest lines.
- **Layout.** The example trees here and in `wiki-onboarding` move the meta pages to `90 Schema` /
  `91 Log` so content owns 00–89 and the meta pages never need renaming as domains grow. (The
  Second Brain vault layout in `user-onboarding`/`user-synthesis` keeps `09/10`: its top-level
  areas are a closed set, so the headroom argument doesn't apply.) A new rename protocol covers
  the project-wide sweep, the never-rewritten append-only log, and watch items for out-of-folder
  consumers. `wiki-onboarding`'s Schema step now requires enumerating what actually exists before
  writing the constitution when retrofitting.

Enforcement-layer counterparts (the deterministic roll-up zero-guard, resolving Log/Schema by
role) are tracked in the reference deployment, per the three-layer model.

## v5.2.0 — 2026-08-06

A **MINOR** correcting a rule `portable-markdown` shipped wrong yesterday: it told you to
percent-encode the ampersand.

Neither Typora 1.14.9 nor Obsidian 1.12.7 decodes `%26` when opening a local file — though both decode
`%20` and CJK **in the same destination**, which is what makes it invisible. The link looks correctly
encoded by Obsidian's own documented rule, and is, and opens nothing. In Obsidian the click is worse
than a failure: it **creates** a stray note and a `Health %26 Medical` folder in the vault rather than
reporting anything.

True for a markdown link and an HTML `<a href>` alike, so no form rescues it. Filenames carrying `&`
are ordinary — "Brand Concept & Development Plan", "Health & Medical" — so this is a whole class of
link silently dead, not an edge case. In the deployment this came from, 86 wiki links were affected.

- `quote(path, safe="/&")` — the `&` stays literal.
- Inside an HTML attribute the href must then be entity-escaped too, so the `&` reads `&amp;` — the
  form verified to open. Three escapings in one element, none substituting for another.
- `REFERENCE.md` gains the clicked matrix, and the note that no existence check can catch this:
  `unquote("%26")` gives the real path, so the link is valid on disk and dead in the hand.

## v5.1.0 — 2026-08-06

A **MINOR**: a new `productivity` skill, `portable-markdown`, and no change to any existing rule.

Generated markdown has two audiences — a renderer and a person — and "the renderer" is not one
renderer. The same file is opened in Typora, in Obsidian, and in whatever previews it elsewhere, and
they diverge in exactly the places a generated document leans on: links, anchors, tables, inline HTML.

The skill came out of a real defect in the reference implementation (family-ai-os v1.51.0–v1.52.1).
A folder audit was rebuilt to open with a map of what happened to each dropped file. It rendered
correctly and every link resolved, and the operator still reported that the file links did not work.
Two distinct causes, neither of them the markdown and neither of them the editor's settings:

- an **empty `<a id="x"></a>`** renders as literal visible text in Typora, so all 177 headings read
  `<a id="doc-4b1671ff4451"></a>ALWAYSFLOW - Price List …`. An `<a>` *with content* renders only its
  content, which is why the id and the href belong on one element rather than two.
- of 834 links, **657 were in-document anchors** and only 177 opened a file. Every name the reader
  clicked in the summary tables did exactly what it was told, and what it was told was wrong: a table
  whose purpose is to hand over a document should link to the document.

Hence the skill's central rule — a link's destination follows from what the link is *for* — plus the
encoding both vendors' help does state (URL-encode the destination; keep the file extension; escape
pipes in table cells), the two separate escapings needed when text sits inside an inline element, and
the observation that **no in-document link form is documented by both** editors, so the file link is
the portable choice and the anchor is a verified extra.

`REFERENCE.md` carries the matrix, driven in Typora 1.14.9 rather than reasoned about, because most of
this behaviour is undocumented — including a probe template for settling the next such question, and a
short list of things that look like defects and are not.

## v5.0.0 — 2026-08-03

A **MAJOR** (reference implementation family-ai-os v1.50.7): a semantic change to a documented rule.
"A true action is rare" is replaced by a test with an answer, in every template and skill that carried
it. The reference implementation ran the old wording for months and still arrived at a queue of eight
open alerts of which **five were observations its own wiki had already recorded** — more currently,
and better hedged, than the alert did. Its owner reviewed them one by one and wanted no decision from
himself on seven.

- **An observation is a wiki write, not an alert.** An item is raised only when there is a physical
  act the owner must perform that the system cannot, named in a new **`owner_action`**. Otherwise
  `owner_action` is null, the item is *recorded* rather than queued, and the page the run wrote is
  where the observation is read. "Rare", "soon" and "clearly relevant" are judgements a model re-makes
  differently every run; "is there an act only the owner can do" has an answer.
- **`owner_action` and `what_would_resolve` are not duplicates**, and the difference is the mechanism.
  `what_would_resolve` is what makes the item stop being true — a later run or the clock may satisfy
  it. `owner_action` is the part of that only a person can do. It is always a subset, and its **null**
  is the load-bearing value: the one thing `what_would_resolve` cannot express, because "the page is
  updated after the appointment" is a real resolution that asks nothing of anybody today.
- **If you cite an open item, supersede it or say why both stand.** Citing an open item and leaving it
  open is a duplicate, not a citation. A live pair sat eleven days with the stale, narrower item at a
  *higher* priority than the one that subsumed it — so a replacement must inherit at least the
  priority it retires, and nothing sinks by being replaced.
- **A default cannot fail, so a default is never a decision** (`coding` / silent-failure-design). The
  quieter twin of a control that never ran: one that ran on a value nobody chose. A notification lane
  defaulted to `household`, one call site omitted it, and an operator alert sat in a family queue for
  eleven days with no error, no log and no diff. Ask it of the parameter — *if the caller had never
  thought about this, what would I see?* — and make omission loud with a structural test over the call
  sites rather than a runtime exception.

**Consumers must re-reconcile their twins.** Unlike every release since v3.0.0, the archetypes are
*not* byte-identical: `file-ingest/{ingest,reconcile}.md`, `user-synthesis/{synthesise,reconcile}.md`,
`wiki-maintenance/SKILL.md` and `ARCHITECTURE.md` all change. A deployment advancing its pin will see
its prompt-derivation check go red until the twins are re-derived and restamped — correctly, this
time: it is real content drift, not the provenance-lag false signal of v3.0.0–v4.3.2.

## v4.3.2 — 2026-08-01

A **PATCH** (reference implementation family-ai-os v1.49.4): v4.3.1 named the two drifts but
prescribed a reconciliation that is itself unsafe. Adversarial review of the implementation showed
the fix could destroy the provenance it exists to protect, so the guidance is sharpened where it
was wrong.

- **"One truth test for existence" was the wrong lesson.** Judge records against what the walk
  already OBSERVED — it has hashed the tree the records point into, so its digests answer *still
  there* and *still this content* at once. A bare existence probe cannot see a path whose bytes
  were replaced, and the record then claims for ever that a file is a copy of something it no
  longer contains.
- **Only a proven absence may retire a record.** `Path.exists()`-style helpers answer *false* for a
  file that merely cannot be stat-ed, collapsing "gone" and "cannot tell" — so a transient
  permission or I/O blip erases the user's provenance permanently. Keep the record on any other
  error and say so.
- **A path read out of a file is untrusted, even one you wrote.** Run records through the same
  containment and symlink guards every other file-sourced path passes, and refuse an escaping one
  *without* probing it.
- **Count work where its record commits, not where the work is minted** — otherwise the
  unaccountable count simply moves to the failure path.

## v4.3.1 — 2026-08-01

A **PATCH** (reference implementation family-ai-os v1.49.4): two ways a record drifts from the
folder it describes, both found in practice.

- **A transformation consumed by a later step still needs recording** — a scan straightened before
  a merge has its upright copy eaten by that merge, so the run counts work the audit cannot show
  unless the straightening is written onto the archived original. Reconcile reported counts against
  recorded ones in a test.
- **Reconcile location records against the folder every run.** A record written once and never
  re-checked drifts as soon as a human moves or deletes the file; walkers cannot see an absence, so
  prune at the source rather than making each reader re-check. One truth test for existence, not two.

## v4.3.0 — 2026-08-01

A **MINOR** (reference implementation family-ai-os v1.49.0): the skill now says how a run should
REPORT itself, not only how it should process files.

- **Duplicate drops are set aside, not left unmentioned** — into the run's `_Duplicates/`, with the
  three constraints spelled out (hash-keyed identity means no second entry; the runs walker means
  the copy must be recorded or it is rediscovered for ever; a crash-recovery pass that repairs
  committed moves means the move must declare it claims no placement).
- **Report in the terms the counts mean**: files in vs documents out, provenance counted apart, and
  the run's audit named by path — never a path that was not written.
- **The audit pair splits by scope**: full detail per run folder, an index of runs at the root.
- **A live run is visible as such**: liveness from the lock rather than the newest row, stage
  published into the run's own row, and the final write replacing it.

## v4.2.2 — 2026-07-31

A **PATCH** (reference implementation family-ai-os v1.48.2, same release as v4.2.1's sweeper).

- **`file-preprocessing` — the look queue re-opens on fresh context.** A run carrying a pasted
  operator note re-admits every look-flagged file for a fresh judgement without the force flag;
  a resolved file moves into the current run's parcel, entry advancing in place, prior verdict
  excluded from the prompt index. A bare run re-judges nothing.
- **Operator-declared complete files.** A half-marker-named scan the context declares COMPLETE
  (declared `complete:` front-matter, or extracted from prose through the same validators) is
  exempted from pair detection — no merge hold, no lonely-half flag; the stated fact beats the
  filename pattern.
- **Audit lineage.** AUDIT.md records per-entry Merged from/into, Split from/into and
  Straightened from/into, derived purely from manifest lineage fields.

## v4.2.1 — 2026-07-31

A **PATCH** (reference implementation family-ai-os v1.48.2).

- **`file-preprocessing` — unanswered files get one in-run sweeper retry.** A file the
  understanding step failed to answer for (omitted from a reply, or in a chunk that died on a
  timeout/exhausted backend) is re-asked once in its own small chunk(s) with routing run fresh —
  a dead backend's files retry on the next eligible backend inside the same run. Still
  unanswered, it defers to `Incoming/` exactly as before: deferral stays the floor, retry is the
  first response. A first-round failure the sweeper fully recovers from reports a healed `ok`,
  with the failed chunk row visible beside its retry row; only a failure that leaves files behind
  colours the run status.

## v4.2.0 — 2026-07-31

A **MINOR** with one called-out behaviour change (reference implementation family-ai-os v1.48.0).

- **`file-preprocessing` — bundles split into their component documents** (new step 5): the
  understanding step may propose page ranges + per-part fields only when boundaries are certain;
  the engine validates a strict partition of every page and executes it whole or rejects it whole
  (a rejected proposal files the bundle flagged, never a partial split). Lineage mirrors the merge
  contract: `split_from`/`split_into` + the new `archived_bundle` flag, bundle archived only once
  EVERY part's move lands.
- **Themes segregate the run folder above categories** when the operator declares them:
  `Runs/<ts>/<Theme>/<Category>/…`, files assigned against the declared list with unknowns in the
  declared catch-all; the look surface and `_Archive/` stay at the run root. Entries carry an
  optional `theme`.
- **The pasted run note and the standing file are one context capability** behind one parser
  (front-matter and all; malformed refuses naming its source; the note wins on collision) — and
  the operator normally writes neither: the whole-batch planning call extracts merge geometry and
  theme declarations from PLAIN PROSE through exactly the front-matter validators (declared wins
  over extracted; misfires dropped with recorded reasons).
- **BEHAVIOUR CHANGE — twinless split-scan halves file visibly** to `Needs a look/` under their
  understood names with an engine-derived "(odd pages only)" note (entry keeps `original_name`,
  marker intact, for a manual pair-up). Supersedes v4.0–4.1's invisible wait state, which
  misled: "waiting" on a finished run implies the run will act later, and it never does.
- **NEW dev-process skill `iterative-acceptance`** (coding plugin): the loop for building on
  nondeterministic tools when expectations are discovered, not specified — frozen baseline with a
  byte-identity invariant, predictions registered before each run and scored honestly, the
  blank-slate protocol, misses-become-capabilities (never hacks for the test data), context in
  the prompt vs fixes in code, iterate until the attention surface is near-empty.

Schema additions are additive; consumers ignore unknown fields and flags by contract.

## v4.1.0 — 2026-07-31

A **MINOR**: `file-preprocessing` grows four additive capabilities (reference implementation
family-ai-os v1.47.0); the folder contract, hash contract and every v4.0.0 behaviour are
unchanged, so a v4.0.0 deployment keeps working untouched.

- **The whole-batch reduce** (the second half of the fuller two-pass): after every group's
  answers validate and before anything applies, one pass over each accepted entry's compact row
  plus the prior-run index settles a batch-consistent category per file and records connections
  **on BOTH entries** — bidirectional, including reverse links onto prior-run entries. Advisory:
  a failed reduce leaves the groups' own judgements standing.
- **Operator merge directives**: `INSTRUCTIONS.md` may open with a `---`-fenced YAML front-matter
  declaring split-scan merge geometry (`even_first` for a pair whose first odd page is missing,
  `reverse_odd`/`reverse_even` for a half scanned backwards). Stripped from the model-facing
  body; validated strictly — a malformed or typo'd block refuses the run rather than being
  silently ignored; the page gate is evaluated for the declared geometry.
- **Sideways scans are straightened** (before pairing, so merges consume upright halves):
  orientation decided from the reading DIRECTION of recognised lines — never recognition scores,
  which are rotation-invariant on modern recognisers — and acted on only at a clear win. The
  upright copy files; the sideways original rests in the run's `_Archive/` with
  `rotated_from`/`rotated_into` lineage and the new `archived_original` flag, mirroring the merge
  pair's contract.
- **The date retry**: a `date_unreadable` verdict from a text-only read earns one bounded second
  look with the actual file open before `No date/` ever sees it; only an answer with a real date
  and no attention request replaces the original judgement.

Schema additions (`manifest-schema.md`): entry fields `rotated_from`/`rotated_into`, flag
`archived_original`, and the bidirectional-connections wording. All additive — consumers ignore
unknown fields and flags by contract.

## v4.0.0 — 2026-07-30

A **MAJOR**: `file-preprocessing`'s folder contract changes. The drop zone renames `_Inbox/` →
`Incoming/`, and processed files land in dated `Runs/<YYYY-MM-DD HHMM>/` parcels instead of
category folders at the root — a v3.4 deployment that keeps dropping into `_Inbox/` would sit
unprocessed, which is exactly the breaking-change bar AGENTS.md sets. **Migration:** rename
`_Inbox` → `Incoming` (on the machine that owns the folder); existing root-level category folders
need no move — the scan adopts files wherever their recorded paths still resolve, and anything
relocated by hand is adopted as a human move on the next run.

The rest of the release, with the reference implementation (family-ai-os v1.46.0):

- **Conveyor, not a library**: the drop zone is `Incoming/`; a run produces its own dated folder
  under `Runs/`, carrying a manifest+audit *slice* with rebased paths, so a collected parcel
  explains itself wherever it goes; the root pair is the long memory.
- **"Needs a look" is a reasoned surface, never a dumping ground**: one per-run `Needs a look/`
  folder whose SUBFOLDER is the reason (`Unrecognisable/` original name kept · `No date/` ·
  `Too large/` terminal · `Flagged/` with the model's required `look`+`look_reason`); an
  unexplained low confidence files normally; a file the model failed to answer for stays in
  `Incoming/` and retries. `NEEDS A LOOK.md` is written only when the folder is non-empty.
- **Split scans are re-joined**: marker-named odd/even halves (单数/双数, 奇数页/偶数页, "odd
  pages" — never bare "odd"/"even") pair by stem, gate on interleavable page counts, merge into
  one document; originals archive to the run's `_Archive/`. The merged entry's id remains the
  merged FILE's own SHA-256 (the hash contract and move guards are unchanged); **re-merge
  deduplication** works through the halves' own entries (`merged_from`/`merged_into` linkage) —
  needed because PDF writers embed creation metadata, so the same halves never merge to
  identical bytes twice.
- **No arbitrary page caps**: probe first (page count + text-layer presence), tier the read, hand
  a too-long scan to a vision-capable model whole, and end the ladder in a terminal visible stop.
- **UK English naming by default**; hard-to-translate proper nouns keep both forms side by side.
- **Fresh re-judging**: a re-processed file's own prior entry is excluded from any index shown to
  the model — a stale verdict is never inherited.
- Schema additions (`family-ai-preprocess-manifest/1`, backwards-compatible): `look_reason`,
  `merged_from`, `merged_into`; flags `too_large` and `archived_half`; `partial_read` is legacy —
  recognised, no longer produced.

## v3.4.0 — 2026-07-28

A **MINOR**: a new `ai-os` skill, **`file-preprocessing`** — staging-folder triage for batches of
files that belong to no project yet (scans are the motivating case; any type is accepted).

The method: an `_Inbox/` drop zone in a staging folder; understand each new file (read/OCR however
the environment allows); build a **party-first** name deterministically from model-proposed fields
(`<Party> - <DocType> <YYYY-MM-DD> <Detail>.<ext>`, fixed fallbacks, never a fabricated date); move
it into a category subfolder under guards (containment, no symlink traversal, never-overwrite with
deterministic suffixes, content-hash-verified moves); and maintain the **portable audit pair inside
the folder** — `manifest.json`, the hash-keyed machine source of truth (schema
`family-ai-preprocess-manifest/1`, authoritative definition in
`plugins/ai-os/skills/file-preprocessing/references/manifest-schema.md`), and `AUDIT.md`, its
derived human/cold-AI rendering. Entries are keyed by content hash, so identity survives renames,
runs are incremental, removed files are flagged `departed` (never deleted from the audit), returned
bytes are re-placed without model spend, and unreadable files land in `Needs Review/` unguessed.
Hash-keyed idempotency is the interop property: an automated engine, a human hand-moving files, and
any other agent following this skill can all work the same folder without stepping on each other.
family-ai-os's `preprocess` engine (v1.42.0) is the reference implementation; this skill is the
portable spec.

## v3.3.0 — 2026-07-27

A **MINOR**: a new `coding` skill, **`silent-failure-design`**, and three additions to
`adversarial-review`'s rules — both drawn from one week on a real deployment in which six separate
controls were found to have silently stopped running.

**New skill `silent-failure-design`.** The failure class where absence wears the appearance of
success: a control that never ran produces the same observable output as one that ran and found
nothing wrong. The six instances behind it are concrete — CI never scheduled because a conflicting PR
has no merge ref (`gh pr checks` says "no checks reported", which reads as *not yet*); a watchdog that
crashed on its first row inside a blanket `except: pass` with output to `DEVNULL`, printing
`0 red row(s) pushed` exactly as a healthy system does; a fail-closed guard that could not start and
therefore denied every read for weeks; a test whose monkeypatch seam moved during a refactor so it
passed against the operator's *real production data*; a wholly-skipped workflow counted as a pass by a
merge gate; and an adversarial review that posted a verdict on the wrong PR. Every one was found by
accident. The skill is one question asked of any control — *if this had never run, what would I see?*
— plus the four properties that make the answer differ from silence (a liveness signal separate from
the finding, verification by artifact rather than exit code, per-item error isolation, and a status
vocabulary that separates *verified* from *unverified* and *nothing failed* from *nothing ran*), an
audit checklist for existing systems, and the instruction to fix the class rather than the instance.

**`adversarial-review` rules 5, 6 and 7 are new**, and rule 4 is rewritten. Rule 4 previously measured
convergence by a shrinking finding count; one gate ran 5 → 2 → 2 → 4 → 0, so the count carried no
signal — what did was that the converging round's fix **deleted** 83 lines rather than adding another
guard. Rule 5 is the mirror of "an APPROVE is not a pass": **a CHANGES-REQUESTED is not automatically
right**, so verify a finding's *premise* before acting on it, especially when the remedy adds
complexity — in that gate a finding asserted a function ran on a 60-second poll when one `grep` for
callers showed it ran weekly, and the optimisation added to satisfy it caused three real defects in
the next round. Rule 6 names **fix-induced findings** (three of thirteen there existed only because of
earlier fixes) and says to stop patching and find the shared root once a second appears. Rule 7 says
to point the harness at the PR you think you are reviewing — deriving an invocation by copying a
previous one and substituting the number is how a reviewer audits a different, already-merged PR while
its instructions describe yours. Later rules renumber accordingly, with cross-references updated.

All three plugin manifests bump to 3.3.0 per the single-version-stream rule.

## v3.2.0 — 2026-07-23

A **MINOR** to `adversarial-review`: a fourth reviewer leg, **MiniMax** (`mmx`). The fallback chain is now
four legs — Gemini, Claude, Codex, MiniMax — each eligible when it is not the author's model. MiniMax is a
fourth-vendor model on its own **subscription** budget (independent of the Claude, ChatGPT and Antigravity
plans), so it is the most diverse reviewer on the bench and the one to reach for when the other three are
near their walls; a Claude-authored change now runs Gemini → MiniMax → Codex (the two idle separate budgets
before the days-walling Codex bucket). Like the Claude and Codex legs it has **no bundled harness**, and the
leg documents its one wrinkle: `mmx text chat` is a pure chat completion with **no repo/`gh`/tool access**,
so the driver pastes the `gh pr diff` + PR intent INTO the prompt (the reviewer can fetch nothing itself)
and relays findings with `gh pr comment`. It also carries a prerequisites row, a place in quota-aware
selection, and the silent-default-substitution trap (mmx swaps its default for an unknown `--model`, so pin
a confirmed one). Reviewer-selection rule 1 lists MiniMax among the eligible reviewers. All three plugin
manifests bump to 3.2.0 per the single-version-stream rule.

## v3.1.1 — 2026-07-23

A **PATCH** to `adversarial-review`: no contract change, one gap closed in the exit-3 triage. The
exit-code table and the prose beneath it now split the *intact-grants* permission-denied case by its
**narration tail** — a tail that died mid-read reaching for a command routes to the invented-command
autopsy (as before), while a tail showing a *finished verdict whose only denial was the posting step*
(the print-mode soft-deny) routes first to **the relay salvage**, not the command hunt. "The relay
salvage" is generalised to match: its cause was stated narrowly as backticks in the `--body`, and now
covers any command the config denies at the posting step, cross-linked to the fallback chain. Harvested
from the v3.0.0 release review (#42). All three plugin manifests bump to 3.1.1 per the single-version-
stream rule.

## v3.1.0 — 2026-07-23

A **third direction, `productivity`** (displayName "AI Productivity"), created together with its first
skill — the standing rule that a direction never ships as an empty placeholder. A MINOR release: a new
plugin plus a new skill, both additive; nothing renamed, removed, or semantically changed. Per the
single-version-stream rule the version lint enforces, all three plugin manifests bump to 3.1.0.

The skill is **`ai-writing-audit`** — audit a draft for the signs of AI authorship and rewrite to remove
them. It is dissolved in from a loose, unversioned copy and rebuilt on this repo's conventions (generic
prose, UK English, skill-relative tool paths, `SKILL.md` + `REFERENCE.md` + `tools/`), then brought up to
date against the 2026 landscape before shipping. The 2024-era version was a flat word-list anchored on
"delve" and the em-dash; both have since been trained or instructed away (frontier models dialled back
"delve" through 2025; OpenAI shipped an em-dash-suppression setting in November 2025), so a word-list is
now weak and perishable evidence. The rebuild reframes the method around **evidence bands and cluster
density**, matching the move Wikipedia's own "Signs of AI writing" essay made:

- **Band 1 (near-decisive):** a new top category for **leaked citation/tool markup** (`oaicite`,
  `[cite: 1]`, `turn0search0`, `grok_card`, `ppl-ai-file-upload`), and **sentence-length variance**
  (burstiness) as the primary structural metric, quantified from a 2025 stylometry study.
- **Band 2 (fires in clusters):** negative parallelism (now the most common single tell), formatting
  overkill, the rule of three, compulsive summaries, trailing "-ing" analysis, false ranges, and a new
  **sycophancy-opener** item ("Great question", "Let's break this down").
- **Band 3 (contributory only):** vocabulary is **era-tagged** by model generation (with "delve" marked
  as fading and the annotator-dialect origin story flagged as unverified folklore), alongside hedging
  clichés, stock transitions, flattery, and em-dash *density* (not presence).

Also adds a **model-fingerprint** note (Grok, ChatGPT, Gemini, Claude tendencies) and a provenance stamp
("last verified 2026-07") declaring the vocabulary layer the most perishable part. The bundled
`tools/audit.py` scanner is rewritten to grade hits into the three bands, detect the artifact tokens and
the double-hyphen dash, compute burstiness, and print a cluster verdict rather than a raw tally.

### Added
- **`productivity` direction** (`plugins/productivity/`): `.claude-plugin/plugin.json` +
  `skills/ai-writing-audit/{SKILL.md, REFERENCE.md, tools/audit.py}`, and its `marketplace.json` entry.
- `README.md` — a `productivity` direction section; install lines for both Claude Code and Codex; the
  bullet flipped from *(planned)* to shipped.

### Changed
- `plugins/coding/.claude-plugin/plugin.json`, `plugins/ai-os/.claude-plugin/plugin.json`: `version`
  bumped to 3.1.0 (single-version-stream).
- `.claude-plugin/marketplace.json`: `productivity` entry added; `metadata.description` names the third
  direction.
- `AGENTS.md` (+ `CLAUDE.md` symlink): the "Today" direction list and the versioned-interface skill-name
  examples include `productivity` / `ai-writing-audit`.

## v3.0.3 — 2026-07-23

Adds a **`displayName`** to each plugin so the `/plugin` picker reads `Coding Discipline` and
`Headless AI OS` instead of the auto-title-cased `Coding` / `Ai Os` (the latter mis-cased). The `name`
identifiers stay `coding` / `ai-os`, so install commands (`coding@ai-tradecraft-skills`) and skill
invocation prefixes (`coding:adversarial-review`) are unchanged — `displayName` is UI-only, "not used
for namespacing or lookup" (Claude Code ≥ v2.1.143; older clients fall back to `name`). Set in both the
plugin manifests and the marketplace entries so the browse and installed views agree. A PATCH: no skill,
archetype, placeholder, or documented-method change — nothing in the versioned interface moves; the
manifests bump to 3.0.3 for the version lint.

### Changed
- `plugins/coding/.claude-plugin/plugin.json`, `plugins/ai-os/.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`: add `displayName` (`Coding Discipline` / `Headless AI OS`).

## v3.0.2 — 2026-07-23

Docs only. Corrects the **ChatGPT (Codex CLI)** install to the real, cleaner path: Codex CLI reads
the Claude Code marketplace format, so the repo installs as a first-class Codex plugin —
`codex plugin marketplace add boshuthebuilder/ai-tradecraft-skills` then `codex plugin add
coding@ai-tradecraft-skills` / `ai-os@ai-tradecraft-skills` — rather than the clone-and-symlink v3.0.1
documented. Verified end to end against `codex-cli 0.144.1`: both plugins install `enabled` at 3.0.1
with all eight skills materialised in the plugin cache. The manual skills-directory symlink is kept as
a one-line note for other `SKILL.md`-reading agents (Cursor, Gemini CLI). A PATCH; manifests bump to
3.0.2 for the version lint.

### Changed
- `README.md`: `ChatGPT (Codex CLI)` install switched from clone-and-symlink to
  `codex plugin marketplace add` + `codex plugin add`.

## v3.0.1 — 2026-07-23

Docs only. The README `Install` section gains a **ChatGPT (Codex CLI)** subsection alongside the
Claude Code / Cowork one: Codex reads the same open `SKILL.md` format but has no marketplace, so the
instructions clone the repo and symlink each direction's skill folders into the user-level
`~/.agents/skills` directory (with `$<name>` invocation and the note that the same folders work in
any `.agents/skills`-reading agent). No skill, archetype, placeholder, or manifest-contract change —
a PATCH; the plugin manifests bump to 3.0.1 only to satisfy the single-version-stream lint.

### Changed
- `README.md`: `Install` restructured into `Claude Code / Cowork` and `ChatGPT (Codex CLI)`
  subsections.

## v3.0.0 — 2026-07-23

**Breaking** — the repo repurposes from "the headless-AI-OS method" into a **method library of
Agent Skills for AI-agent-driven work, organised by direction**, and restructures from a single
flat plugin into a multi-plugin marketplace: one real Claude Code plugin per direction. The two
families the flat layout already kept strictly separate — zero cross-references between them,
skill by skill — become two independently installable plugins: **`coding`**
(agent-tiered-planning, design-direction-lock, implementation-discipline, adversarial-review) and
**`ai-os`** (project-onboarding, user-onboarding, wiki-onboarding, wiki-maintenance, plus
`ARCHITECTURE.md`, which is that direction's own design doc and never mentioned the coding
family). A third direction, `productivity`, follows in a later MINOR together with its first
skill — never as an empty placeholder. The marketplace is named **`ai-tradecraft-skills`** (the
`agent-skills` candidate is a reserved Anthropic marketplace name, re-checked on every load), and
the GitHub repository is renamed `ai-os-skills` → `ai-tradecraft-skills` to match. A MAJOR
release: the versioned interface's own layout changes — every `skills/<name>/SKILL.md` and
archetype path a consumer resolves moves under `plugins/<direction>/`. Prompt-template
placeholders are unchanged.

### Changed
- **Repository layout**: `skills/<name>/` → `plugins/coding/skills/<name>/` (four skills) or
  `plugins/ai-os/skills/<name>/` (four skills); `ARCHITECTURE.md` → `plugins/ai-os/ARCHITECTURE.md`.
  Full map under *Migration* below.
- **`.claude-plugin/plugin.json`** (root) removed — the repo root is no longer itself a plugin.
  Each direction carries its own manifest at `plugins/<direction>/.claude-plugin/plugin.json`,
  version synced to this release per the single-version-stream rule.
- **`.claude-plugin/marketplace.json`**: renamed to `ai-tradecraft-skills`; two plugin entries
  (`coding`, `ai-os`) with relative sources; `renames` retires the old `ai-os-skills` plugin name
  to `null` — its content maps to *two* successors, and a single-successor mapping would silently
  migrate half the skills and drop the other half, which *Fail loud, never silent* forbids.
- **`scripts/lint_skills.py`**: discovery moves to `plugins/*/skills/*/SKILL.md`; per-plugin
  manifest validation (name matches directory, marketplace entry exists, entry version — when
  declared — agrees); every plugin's version must equal every other's and the newest CHANGELOG
  heading; loud failures on a plugin with zero skills and on any `SKILL.md` outside
  `plugins/*/skills/*/` (the partial-move signature the old glob would have linted past).
- **`README.md`**: rewritten around the directions, with per-plugin install commands.
- **`AGENTS.md`**: intro reframed to the direction library; versioned-interface layout strings
  updated; the `ARCHITECTURE.md` link points at its new home, and that path is called out as part
  of the documented interface.
- **`implementation-discipline`** (now under `plugins/coding/`): the fail-loud citation no longer
  names `ARCHITECTURE.md` by file, since that document ships in a different, independently
  installable plugin — the rule is restated inline, unchanged in substance.

### Migration (for the pinned consumer)

| Old path (≤ v2.9.1) | New path (v3.0.0) |
|---|---|
| `skills/adversarial-review/` | `plugins/coding/skills/adversarial-review/` |
| `skills/agent-tiered-planning/` | `plugins/coding/skills/agent-tiered-planning/` |
| `skills/design-direction-lock/` | `plugins/coding/skills/design-direction-lock/` |
| `skills/implementation-discipline/` | `plugins/coding/skills/implementation-discipline/` |
| `skills/project-onboarding/` (+ `archetypes/`) | `plugins/ai-os/skills/project-onboarding/` (+ `archetypes/`) |
| `skills/user-onboarding/` | `plugins/ai-os/skills/user-onboarding/` |
| `skills/wiki-maintenance/` | `plugins/ai-os/skills/wiki-maintenance/` |
| `skills/wiki-onboarding/` | `plugins/ai-os/skills/wiki-onboarding/` |
| `ARCHITECTURE.md` | `plugins/ai-os/ARCHITECTURE.md` |
| `github.com/boshuthebuilder/ai-os-skills` | `github.com/boshuthebuilder/ai-tradecraft-skills` |

A pinned consumer updates every resolved path above and its remote URL in the same deploy that
advances the pin — see *Consuming a pinned release* in
[`plugins/ai-os/ARCHITECTURE.md`](plugins/ai-os/ARCHITECTURE.md). A marketplace-installed
consumer gets no automatic migration (`renames` → `null` is a removal notice, not a redirect):
remove the old marketplace, re-add `boshuthebuilder/ai-tradecraft-skills`, and install `coding`
and `ai-os` explicitly.

## v2.9.1 — 2026-07-23

`adversarial-review`'s headless-reviewer contract gains one bullet, sibling to *verify by artifact,
never by exit code*: a reviewer's read of the code cannot see a validator and its reader disagreeing
at run time, and neither can a test that mocks the load path. Harvested from a production incident in
a consumer deployment — a config flag's reader was written and tested, every test mocked the config
loader, the real validator silently rejected the new key, and the feature was inert until someone
actually armed it on the real host. A PATCH — wording under an existing bullet, no section added, no
rule renamed or changed.

## v2.9.0 — 2026-07-23

`adversarial-review`: the fallback chain becomes **author-agnostic**, and **Claude joins as a first-class
reviewer leg**. Rule 1 already said "if Codex wrote it, Gemini or Claude reviews it" and the skill's own
scope claims "any coding agent," but the concrete chain didn't deliver it: Gemini was "primary when Claude
authored," Codex was the fallback, and Claude appeared only as the same-vendor *last resort* — so a Codex-
or Gemini-authored change had no documented way to run its most diverse reviewer (Claude), and mislabelled
it as the weak floor. Now the three legs (Gemini · Claude · Codex) are each eligible whenever the author is
a different model, ordered diversity-first then window-economics; same-**model** review is the disclosed
last resort. The Claude leg is documented, not scripted — `claude -p` headless or a fresh no-context
subagent, relayed via `gh pr comment`, driven like the Codex leg — because Claude lacks the silent-failure
modes that forced the Gemini harness (print mode exits non-zero on hard failure), and a speculative
`tools/claude-review` would be the very structure rule 7 forbids until a real driver feels the pain.

Also adds a **Prerequisites** section: the CLI + auth each leg needs and a one-line check, stating plainly
that the `agy-review` harness self-enforces its prerequisites (typed exits) while the Codex and Claude legs
have no wrapper and must be checked by hand. A MINOR release: a new reviewer leg + a new doc section; no
grant, exit-code, or harness-behaviour change, and the numeric-contract forwarding block gains a Claude
line.

### Changed
- `skills/adversarial-review/SKILL.md`: author-agnostic chain intro; Claude leg added, Codex renumbered,
  same-model last resort generalised; `Prerequisites` section; Claude added to the numeric-contract
  forwarding bullets.
- `README.md`: chain description updated to the author-agnostic three-leg form.

## v2.8.0 — 2026-07-22

`adversarial-review`: the fallback chain flips to **Gemini-first** (harness leg 1, Codex leg 2) for
Claude-authored code. A policy change on window economics, not review quality: the Antigravity
subscription is a budget separate from both the author's Claude plan and Codex's single shared
ChatGPT-Plus bucket, which rate-walls for *days* at a time and is the capability fit for coding
work — the reference deployment's routing now reserves it the same way (its 2026-07-22 rebalance,
family-ai-os v1.31.0). Decided the day Codex hard-walled to the 28th mid-review while the
Antigravity pools sat at 2–6% weekly. Every harness rule, typed exit, and grant is unchanged; the
Codex leg keeps its full instructions as the fallback (its review record — including a
data-loss-class catch the author's tests missed — is called out so nobody reads "fallback" as
"worse"). The numeric-contract forwarding note is rephrased for the new order: `codex review` still
cannot carry the contract, so the warning against reaching for it out of habit stays load-bearing.
A MINOR release: reviewer-selection *policy* changed; no interface, grant, or exit-code change.

### Changed
- `skills/adversarial-review/SKILL.md`: chain legs 1↔2 with the window-economics rationale inline;
  Codex leg annotated as fallback with its wall behaviour; numeric-contract forwarding note updated.

## v2.7.0 — 2026-07-22

`ARCHITECTURE.md` gains **Consuming a pinned release** — the consumer-side half of the pin contract.
The repo already told a deployment to pin a tag and advance it deliberately; it never said what
enforcing that requires, and the reference deployment proved the gap the expensive way. A MINOR
release (a new section; nothing renamed, removed, or semantically changed).

### Added
- **`ARCHITECTURE.md` → *Consuming a pinned release***, harvested from a production regression in the
  reference deployment: its deploy hook once checked the pinned ref out, the step was dropped by an
  unrelated rewrite, and for weeks advancing the pin changed a file that nothing read — the pinned
  tier still *resolved* from a stale clone, so unattended jobs ran an old method with nothing failing,
  and the health row's own remediation ("redeploy") was exactly what did not help. The section states
  what a consumer owes the pin: **enforce it as a deploy gate** (a release that cannot obtain its
  skills must not activate; fetch tags without `--force` so a moved tag fails loudly rather than
  substituting unreviewed code); **verify before the switch** (materialise the candidate in a
  throwaway worktree — checking out first and verifying second leaves a window in which a scheduled
  job reads an unverified tree); **verify against what the deployment actually consumes** — declared
  skills, the archetype paths its templates derive from, and above all the **placeholders** those
  templates use, since substitution leaves unknown tokens verbatim and an archetype that grows a field
  the deployment does not supply ships `{like_this}` into a live prompt with no error anywhere;
  **judge drift on content, not the tag**; and **keep the fallback visible**, since a bundled-copy
  fallback is a method version nothing verified.
- **`AGENTS.md`** — the consumer-contract paragraph now points at that section for what
  "deliberately" requires, rather than leaving it to each deployment to discover.

## v2.6.2 — 2026-07-22

The `adversarial-review` shell-diff label now **pre-answers the semantics a reviewer would otherwise
execute to check**, and the exit-3 guidance separates an invented command from a missing grant. A
PATCH hardening in the shape of v2.5.1 — no interface change: same grants (`bash -c` stays
un-granted), same typed exits, one sharpened label rule.

### Fixed
- **Reviewing shell makes the reviewer reach for shell *execution*.** Eighth silent-failure class,
  observed reviewing a deployment-critical bash hook (family-ai-os #592): the Gemini leg died typed
  exit 3 (permission-denied) having posted nothing, with the grants block *fully intact* — all
  sixteen documented rules present — so the existing "restore the grants block" remediation was the
  wrong lead. A conversation autopsy (the technique the skill already documents) showed the reviewer
  had proposed `bash -c 'set -e; ( false; echo "still ran" ) || true'` to empirically verify `set
  -e` semantics inside a subshell while auditing the hook's error handling. `command(bash -n)` is
  granted; `bash -c` is not, and prefix matching does not cover it. This is **distinct** from the
  two documented execution-reach deaths (an un-granted command invented mid-run; a granted
  long-running command burning the window): here the reviewer reaches for execution *because the
  artefact under review is shell*, so reviewing bash code makes this death likely rather than
  incidental. `command(bash -c)` is deliberately **not** granted — it is arbitrary code execution,
  refused for the same reason the set already refuses `command(echo)` and `write_file(*)`. The fix
  is in the **label**: when the diff is shell it must forbid executing shell snippets (and `bash -c`
  by name) *and* pre-answer the semantic question the reviewer would otherwise test — e.g. that bash
  suppresses `set -e` inside a compound command used as the left operand of `||`, so the code gives
  every fallible command an explicit `|| { …; exit 1; }` instead of relying on it. Pre-answering is
  what stops the reviewer needing the command at all; a bare prohibition only moves the wall.
  Documented in the *Steer review labels to static reading* bullet.
- **Exit 3 with an intact grants block points at the autopsy, not `config.json`.** The typed-exit
  table and a note beneath it now split exit 3: a grants block *missing a rule* → restore it
  (*Machine setup*); an *intact* block → the reviewer invented an un-granted command, so go straight
  to the conversation autopsy to recover it rather than editing config.

## v2.6.1 — 2026-07-22

The `adversarial-review` bounding example now **closes stdin explicitly**, and the section names
the death it prevents. A PATCH hardening in the shape of v2.5.1 — no interface change: same
watchdog, same treat-a-hang-as-done rule, one redirection added to the example invocation.

### Fixed
- **A backgrounded `codex exec` can spend its whole round waiting on stdin.** Seventh
  silent-failure class, this time observed first-hand (codex-cli 0.144.1, during the round-1
  review of this repo's own PR #30): launched in the background with stdin left as an open
  non-TTY pipe, `codex exec` prints "Reading additional input from stdin..." and waits for that
  pipe to close — which a coordinator holding it open never does. The watchdog then kills the
  child tree with nothing reviewed, and because the skill rightly treats a hang as that reviewer
  being done, the round is indistinguishable from a subscription rate wall: the chain advances
  and an omitted redirection silently costs the leg. The *Bounding a review CLI* example now
  redirects `< /dev/null`, and a sentence beside it names the failure so an operator seeing the
  tell knows to suspect the launcher's stdin, not the reviewer's quota.

## v2.6.0 — 2026-07-22

A fourth development-process skill: **`implementation-discipline`** — how a coding agent conducts
itself while writing a change. The trio becomes a quartet, spanning plan (tier the work), build
(lock the design, discipline the change), gate (review the change). A MINOR release: a new skill
plus cross-references in existing skills; nothing renamed, removed, or semantically changed.

### Added
- **`implementation-discipline`** — the authoring-conduct convention, distilled from
  widely-observed LLM coding failure modes ([Karpathy's January 2026
  post](https://x.com/karpathy/status/2015883857489522876) and [the community skill that grew from
  it](https://github.com/multica-ai/andrej-karpathy-skills)) and rehomed in this repo's method.
  Four disciplines: **assumptions before code** (competing interpretations are presented, not
  silently resolved — and each kind of surfaced problem routes to its existing channel: the
  escalation rule, the deviation protocol, or a comment on the underspecified issue); **the
  minimum that solves it** (no speculative abstraction or configurability, no handling for
  scenarios that cannot occur — an assertion that fails loudly, echoing the method's fail-loud
  rule, beats a defensive branch); **every
  line traces to the task** (no drive-by improvements — an unrequested improvement becomes an
  issue the planner can tier, never a diff hunk; orphans your own change created are yours to
  remove); **criteria before execution** ("fix the bug" becomes "write the failing test, then make
  it pass" — the implementer-side mirror of the standard-tier spec-completeness rule). The skill
  is the single home of the conduct rules; existing skills reference it rather than restate it.

### Changed
- **`adversarial-review`** — a seventh rule: **scope and shape are findings**. A hunk that does
  not trace to the PR's stated intent, and structure the change does not need, are defects to
  name — with a forwardable lens phrase for delegated reviewers, who never read the skill page.
- **`agent-tiered-planning`** — the playbook template gains a short *Conduct while building*
  section, so cold agents meet the conduct rules at pickup; the SKILL.md's template enumeration
  and frontmatter pairing note updated to match.
- **README + plugin manifests** — the development-process trio is now a quartet; descriptions
  updated accordingly.

## v2.5.1 — 2026-07-21

The `adversarial-review` review prompt now **bans the project's test suite**, and the harness names
the death it caused. A PATCH hardening in the shape of v2.4.1 — no interface change: same flags, same
typed exits, one new rule in the headless-reviewer contract.

### Fixed
- **A reviewer can lose its whole round to a *granted* command.** Sixth silent-failure class from
  consumer telemetry: a review leg decided to run `uv run pytest` (~7 minutes in that repo) and then
  spent every remaining turn polling it — "I am waiting for pytest … checking back in 60 seconds",
  five times over — exiting cleanly having posted nothing, so the leg was lost and the chain had to
  advance. This is **not** the documented un-granted-command death: `command(uv run)` is deliberately
  *granted* (Machine setup explains why it is not narrowed) and nothing was denied, so no grant
  change fixes it. The fix is in the prompt, which now states plainly that the reviewer does not run
  the suite, and why — running it is CI's job and the author's, a full run can outlast the entire
  review window, and the gate's value is careful reading, not re-running CI. Two details the review
  of this very change forced: the operative rule is **never poll** rather than a wall-clock budget (a
  reviewer cannot predict a command's duration before running it, and a flat "30 seconds" would have
  disarmed the `uv run` arithmetic check v2.5.0 shipped a day earlier — a cold dependency sync blows
  any budget), and the short checks that stay welcome are **named individually** rather than as a
  category, since "a quick single-file check" invites `shellcheck`/`py_compile`/`node --check`, none
  granted — trading this death for the un-granted-command one. The prompt also no longer justifies
  the ban by asserting the author already ran the suite: it cannot know that, and telling an
  adversarial reviewer to trust an author's claim suppresses the finding the gate exists to catch.
- **A window-burn no longer reports as a generic silence.** The harness flags the shape (repeated
  "waiting…" narration in the tail, nothing posted) and says *this looks like the reviewer spending
  its round waiting on a long-running command* — on exit 4 and exit 5 alike, since either can fire
  first. The typed exit is unchanged (the leg is done either way); the operator now sees an
  actionable failure instead of an opaque one, and is pointed at the `--label` when a focus phrase
  steered the reviewer into it. Deliberately worded as a hypothesis, not a ruling — it is a
  heuristic, and a *wrong* diagnosis is worse than none, so the note hedges and points at the debug
  log and the conversation autopsy that actually confirm a death. Same principle the harness already
  applies elsewhere: verify by artifact, keep a debug log, make failures diagnosable.

## v2.5.0 — 2026-07-21

`adversarial-review` learns how to review a **numeric or engineering contract**. A MINOR release
(one new SKILL.md section, frontmatter description extended; nothing renamed or removed).

### Added
- **Reviewing a numeric or engineering contract** — the second harvest from the same consumer-project
  telemetry that produced the worktree hardening (issue #19). When the artefact carries numbers with
  real-world consequences (a physical model, a sizing or capacity calculation, a pricing or rate
  formula, a tolerance table), truth conditions are crisp and the gate performs unusually well — one
  run returned thirteen findings, all real. That hit rate comes from holding *both* sides to
  executable evidence, so the section states the rules that produce it: a **finding must carry a
  counterexample** (concrete inputs, the produced value and the correct one — two numbers of the
  *same quantity*, since a unit alone proves nothing: `3.2 kN·m` and `3200 kN·mm` are equal); where
  the spec is **under-specified**, the evidence is instead a **divergence** (two defensible readings
  and their two different numbers — the defect is that the contract does not choose, so demanding a
  single right answer would suppress the finding); a **fix must carry a recomputation** (the commit
  ships the script/derivation and the reply shows before → after — the granted `uv run` means the
  reviewer can execute the check rather than trust it); and **the counterexample becomes a test
  vector** (folded into the artefact's permanent checks, turning a one-off exchange into a regression
  guard). Because a delegated reviewer reads only the harness prompt plus `--label` and never this
  page, the section ships a **ready-made label** carrying both the evidence contract and the defect
  classes — units and scale, unstated sign/direction conventions, cases that fail to superpose,
  assumed boundary/support conditions, missing limits, and the domain of validity.

## v2.4.2 — 2026-07-21

The published **plugin manifest** catches up with the repo, and a lint guard stops it drifting again.
A PATCH release: no skill content changes.

### Fixed
- **`.claude-plugin/plugin.json` was frozen at `1.0.0`** while the repo shipped through v2.4.1 — four
  releases. Claude Code compares that `version` to decide whether an update exists, so every plugin
  consumer stayed pinned to the June knowledge-layer snapshot: three skills, no `user-onboarding`, no
  `adversarial-review`, none of the development-process trio. Bumped to the real release version.
- **Both manifest descriptions were stale**, still advertising "currently the knowledge layer:
  project-onboarding, wiki-onboarding, wiki-maintenance". They now name all seven skills across the
  two layers that actually ship.

### Added
- **`scripts/lint_skills.py` now lints the plugin manifest** (CI already runs it): `plugin.json`'s
  `version` must equal the newest `## vX.Y.Z` heading in `CHANGELOG.md`, and `marketplace.json` must
  list the plugin — the same pair `claude plugin tag` refuses to tag when they disagree. Version
  drift is now a loud CI failure at PR time instead of a silent stale install.

## v2.4.1 — 2026-07-21

The `adversarial-review` harness now runs the headless reviewer in an **isolated worktree** — a
PATCH hardening (no interface change; same flags, same typed exits). Closes the fifth silent-failure
class surfaced by the second consumer project (issue #19): a review round's `pr-<n>` checkout in the
coordinator's *live* tree not only stranded the branch (the existing after-the-fact restore guard
caught that) but *raced a coordinator editing the same tree* — a mid-round branch switch left a
concurrent `Edit` pointing at a file the checkout had removed.

### Changed
- **`tools/agy-review` isolates the review in a detached worktree at the PR head.** Before launching
  agy the harness fetches `pull/<n>/head` into a **per-run ref** (`refs/agy-review/pr-<n>-<pid>`,
  never the shared `FETCH_HEAD` a concurrent run could clobber between fetch and resolve), then
  `git worktree add --detach`s a throwaway tree inside a **private 0700 parent dir** (so the
  checked-out PR source is not world-readable on a shared host, and the not-yet-existing child path
  is accepted by every git version). agy runs with its cwd there, so its branch-switching is
  confined to the worktree and the caller's checkout is never touched — you can keep editing while a
  review runs. Falls back (loud `WARN`) to the caller's tree plus the existing before/after
  branch-restore guard only when a worktree cannot be created; the "your files are the PR version"
  hint given to the reviewer is **conditional** on the worktree existing, so the fallback never
  misleads it into reviewing the caller's current branch. Worktree, parent dir, and ref are all
  removed on every exit path. SKILL.md documents this as the structural fix for the "re-assert your
  branch" rule.

## v2.4.0 — 2026-07-18

Two new skills complete the **development-process trio** (plan → build → gate) alongside
adversarial-review — practices harvested from a second consumer project (issue #19; a
parametric-furniture build executed by mixed-capability agents), generalised here. A MINOR release.

### Added
- **`agent-tiered-planning`** — plan and dispatch a backlog across mixed-capability agents:
  `agent:standard|senior|frontier` labels as a capability estimate ORTHOGONAL to effort (a small
  task can still be subtle); tier definitions by work character with a three-question assignment
  heuristic; the cold-agent pickup protocol in a repo playbook; the escalation rule ("stop, comment,
  relabel up, leave it" — a wrong-but-merged implementation costs more than a delayed one); coupling
  to the adversarial-review gate (senior/frontier PRs mandate it); tiers as spend routing (bulk work
  on cheaper models, frontier headroom preserved). Templates: CONTRIBUTING skeleton + `labels.sh`.
- **`design-direction-lock`** — freeze a converged design into a one-page normative artifact
  (references with the feeling named and explicit anti-goals; visual language with accent
  discipline; motion rules including the invariants a plausible animation silently breaks; product
  truths; one canonical reference design threaded through every surface), then stamp each
  design-facing issue with the lock revision and ONLY the rules that apply to that surface, plus the
  deviation protocol. Versioned: a direction change is a new revision + re-stamp, never silent
  drift. Templates: one-pager skeleton + issue stamp.

## v2.3.0 — 2026-07-16

The adversarial-review skill gains **quota-aware reviewer selection** and **follow-ups** — a MINOR
release (one new harness flag, two new SKILL.md sections; nothing renamed or removed). Both were
spiked empirically before building (resume incantation, model labels, denial autopsy).

### Added
- **`tools/agy-review --model "<label>"`** — run the review on another Antigravity-pool model
  (Gemini/Claude/GPT families; `agy models` lists the live labels). The pool is a separate
  subscription budget from the primary Claude/ChatGPT plans, so reviews can run without spending
  primary authoring headroom. An unknown label fails loud (rc=1, valid labels listed).
- **Conversation-id surfacing** — every harness result line (success and failure) carries the run's
  `conversation: <id>`; `agy --conversation <id> -p "…"` (flag before `-p`; plain headless works)
  reopens that run with full context. Documented as a *diagnostic*, not the round-to-round
  mechanism: continuity across rounds stays in the PR comment thread, the only session that
  survives switching reviewer legs. The autopsy pattern — asking a dead run what command it was
  proposing — is documented; it revealed a denied reviewer had been mid-way to a genuine defect.
- **SKILL.md: *Quota-aware reviewer selection*** — the chain degrades reactively by typed exits (no
  quota probe rebuilt inside the gate); the pool as a separate budget; diversity still outranks
  quota (same-family-via-pool = preserve-quota choice, disclosed like any weaker gate); older pool
  models are fine for adversarial reading.
- **SKILL.md: *Follow-ups — interrogating a review***.

### Changed
- Machine-setup grant `command(uv run pytest)` widened to **`command(uv run)`**: pytest already
  executes arbitrary repo code via test collection, so the narrow form bought no safety — and it
  killed a reviewer mid-insight reaching for `uv run python -c` to check packaging metadata, a
  check that later proved a real defect.

## v2.2.0 — 2026-07-16

A new skill — a **MINOR** release. This one is about the process that *builds* the system rather
than the system itself: the cross-model review gate the reference deployment runs on every complex
change, packaged so it works for any repo and any coding agent (Claude Code, Codex, or another CLI
agent driving a shell).

### Added
- **`adversarial-review` skill** — reviewer ≠ author by model; the fallback chain (Codex → Gemini →
  independent agent, with "a dead reviewer is a done reviewer"); the auditable PR-comment protocol
  (verdict + file:line findings on the PR, author replies to every finding, iterate to convergence);
  the **headless-reviewer contract** distilled from four production silent-failure classes (verify by
  artifact never exit code; bound + tree-kill; pin commands to permission-matchable forms; name the
  allowed command set; inline `--body` posting; fetch the reviewer's scratch clone); and the one-time
  machine setup for headless Gemini (`~/.gemini/config/config.json` `globalPermissionGrants` — the
  two look-alike settings files are decoys).
- **`adversarial-review/tools/agy-review`** — the bundled harness for the Gemini leg: repo-agnostic
  (repo derived from the caller's checkout), pre-flights the silent killers, bounds the run, verifies
  success by the posted PR comment (count-based, clock-skew-immune), and exits typed
  (`0 ok · 2 auth-needed · 3 permission-denied · 4 timeout · 5 no-comment · 6 bad-args`). Battle-tested
  by reviewing its own source through four converging rounds (11 findings → 3 → posting mechanics →
  APPROVE) in the reference deployment (family-ai-os #559).

## v2.1.1 — 2026-07-15

Wording only, no contract change — a **PATCH**. Closes the last gap the reference deployment's
notification-hygiene work surfaced: the reason model was *duplicating the deterministic health surface*.
The reference deployment made its wiki-health needs-a-look self-clearing (a standing, per-project alert
that resolves when the condition clears), but the model still ALSO flagged the same machine-detectable
conditions in free text — un-keyed, so those escalations pile up run after run and never clear (a real
cluster of three near-duplicate "resolve this `.proposed.md`" alerts for one file).

### Changed
- **Archetype prompts** (`file-ingest/{ingest,reconcile}`): the model now **defers machine-detectable
  conditions to the deterministic health sweep** — pending `.proposed.md` siblings awaiting review,
  orphaned pages (citing a vanished source), and unreadable pages are surfaced (and self-cleared) by the
  deployment's reconcile-health sweep, so the model must not also record them in `needs_a_look`.
  `needs_a_look` is reserved for judgement calls the harness cannot detect (an ambiguous filing, a
  real-world inconsistency, an owner-only decision). The reconcile prompt's *deterministic-findings
  worklist* rule (v2.1.0) is tightened accordingly: fix what you can, but do not re-escalate the residual.

## v2.1.0 — 2026-07-12

Aligns the archetypes with the reference deployment's 2026-07 **System Jobs Review** (a 25-PR
implementation on family-ai-os). Additive only — new optional fields, new prose, no rename or removal —
so a **MINOR** release. The archetype prompts here are the templates stamped for every future
onboarding; this carries the review's corrections to source, so the next project is not born with the
defects the review fixed.

### Changed
- **Archetype prompts** (`file-ingest/{ingest,reconcile}`, `user-synthesis/{synthesise,reconcile}`)
  carry the six review rules: *partial-view honesty* (a capped/truncated listing never reads as
  "missing/orphaned"); *escalation quality* (`needs_a_look` gains `what_would_resolve` + optional
  `proposed_action`); *re-raise discipline* (reference a `previously_raised` open/dismissed item, never
  repeat it; reopen a recently-resolved one only on changed evidence); *deterministic-findings worklist*
  (reconcile works the pre-computed `{reconcile_findings}` block); *no-change silence* (a run that
  changed nothing omits `notify`); *figure fidelity* (quoted source values copied character-for-character).
  The `code/{digest,code-review}` archetypes already embodied these and are unchanged.
- **Coming Events is deterministic.** Like the Deadlines roll-up, `Coming Events` is now rendered
  deterministically by the deployment from the calendar snapshot — the prompts never build it. Wired as
  a project-wide `rollups.coming_events` capability.
- **`ARCHITECTURE.md`**: adds the **raised-item lifecycle** to the job contract (stable key on source
  path/identity · `open|resolved|dismissed` persistence · the ledger injected into every gather ·
  `what_would_resolve`); states **partial-view honesty** as a gather-contract requirement; acknowledges
  a bounded read-only **agentic** execution mode returning the same contract; adds Coming Events to the
  determinism boundary.
- **`wiki-maintenance/SKILL.md`**: pins the **canonical frontmatter keys** the deterministic sweeps read
  (mandatory `provenance`/`last-updated`/`status`; conditional `source`/`sources`, `deadline`/`deadlines`)
  and the one legacy alias readers accept (`updated:` → `last-updated:`).

### Added
- Archetype `jobs.yaml` templates carry the **full job contract**: explicit `execution_mode` (+ a
  commented agentic option and its read-only constraint), commented `max_budget_usd` guidance (a hit cap
  is an explicit `budget_exceeded` outcome, never a silent truncation), explicit `capabilities.skills`,
  and the file-ingest project-wide `rollups` block (`deadlines` / `open_questions` / `coming_events`).
- `AGENTS.md` documents `{reconcile_findings}` as an **optional** template placeholder (empty default)
  and `{current_knowledge}` as a **required** user-synthesis placeholder.

## v2.0.0 — 2026-06-23

**Breaking** — the `user-synthesis` archetype's write contract changes (see *Changed*). The reference
deployment ran the flow end-to-end before release; the public diff is placeholder-only (no real names,
project ids, or paths).

### Added
- **`user-onboarding` skill** (`skills/user-onboarding/`): onboard a *person* (an identity) — the
  storage-ownership handshake (the user owns the folder and shares it into the worker), the **type-1
  user vault** skeleton it scaffolds, and stamping the user-synthesis archetype. The identity-level
  sibling of `project-onboarding`.
- `ARCHITECTURE.md`: the **Storage ownership** prerequisite and **The type-1 user vault** section (the
  folder-IS-vault skeleton — `00 Index` / `01 Knowledge` / `02 Ideas` / `03 Reports` / `09 Schema` /
  `10 Log`, folder-notes, the three determinism stories, Knowledge ⊥ Ideas).

### Changed
- **`user-synthesis` archetype is now a `synthesise`/`reconcile` pair, not a lone job.** Its Knowledge
  area is **incrementally evolved** (read the current tree, make minimal stable changes, preserve
  paths) rather than regenerated wholesale — so, per the twin rule, it re-earns a periodic `reconcile`
  full-vault pass. Updated `jobs.yaml` (adds `reconcile`), `README.md`, `synthesise.md` (incremental),
  `scheduler.md` (the periodic clock), and added `reconcile.md`. `ARCHITECTURE.md`'s twin rule now uses
  this archetype as its worked example. **Supersedes the v1.0.0 "no reconcile twin / full re-synthesis
  each run" contract** — a breaking change to the archetype's write contract.

## v1.1.0 — 2026-06-23

### Added
- **`code` archetype** (`skills/project-onboarding/archetypes/code/`): the job pair for a git-backed
  project the system reads read-only and reports on — a periodic `digest` (plain-language summary of
  what changed) and a `code-review` (correctness/risk review). A third kind of source — a git clone,
  not the owner's documents or other wikis — read **deterministically** (`git` history is a pure
  function of clone state); the only writes are dated report pages through the deployment's guards,
  never to the code. No `ingest` (a clone has no inbox). README + `jobs.yaml` + the two prompt
  templates + `scheduler.md`.
- `ARCHITECTURE.md`: the `code` archetype as the third shipped family, reaffirming the determinism
  boundary for a repository source.

## v1.0.0 — 2026-06-12

### Added
- **`user-synthesis` archetype** (`skills/project-onboarding/archetypes/user-synthesis/`): a single,
  gated, LLM-reasoned job that synthesises a per-identity, cross-project (user-tier) wiki from the
  project wikis that identity may access. Deterministic gate + access-scoping; reasoning does the
  weaving; no `reconcile` twin (full re-synthesis each run).
- `ARCHITECTURE.md`: the **tiers and identities** model (project-tier wikis self-contained; the
  user-tier wiki as the one home of cross-project links; an *identity* as an access principal), the
  **twin rule** (a periodic `reconcile` exists only for incrementally-built artefacts that can
  drift), the user-synthesis gate inputs, and that an archetype's sources may be other wikis.
- `wiki-maintenance`: the **authored-note pattern** — a free-text inbox item with no source document
  routes to a Schema-declared authored domain as `provenance: manual`; reconcile may merge/link
  authored notes but never deletes or contradicts them.
- `project-onboarding`: pointer to when to stamp user-synthesis instead of file-ingest.
- `AGENTS.md` (+ `CLAUDE.md` symlink): working constraints — the genericness rule, the versioned
  interface, and this release protocol.
- This changelog.

## v0.x — pre-versioning history (summary)

Everything before the first tag, in brief: the wiki skill family (`wiki-onboarding`,
`wiki-maintenance`), the `project-onboarding` flow with the **file-ingest** archetype
(`ingest` + `reconcile`, `id == mode`, reactive gate + periodic pass), and `ARCHITECTURE.md`
reframing the repo as a general job framework for a headless assisting system (wiki as the
first layer, not the boundary). Consumers pinned bare commit SHAs during this period.
