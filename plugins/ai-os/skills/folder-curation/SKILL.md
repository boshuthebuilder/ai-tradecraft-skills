---
name: folder-curation
description: >-
  Adopt a lived-in folder before it is onboarded: audit it thoroughly (a hash-keyed manifest.json +
  AUDIT.md over the whole library: type classes, duplicate groups with pack semantics, overlapping
  homes, generic names, unreadable formats, hygiene defects, live vs closed), then reorganise it only
  under the owner's approval, from a reviewed move-plan executed under guards and verified by
  re-audit, and hand it to project-onboarding. Propose-only by default; nothing moves without a yes.
  The audit half keeps running afterwards as the project's periodic `audit` job (the folder-curation
  archetype), and while a folder is being prepared approved plans are also how files are staged for
  another project, for the owner to move by hand. A component of
  pre-onboarding: a person preparing a lived-in folder for the system starts there, and it runs this
  skill's audit and curation rounds with its bundled tools. Use directly when the owner wants a
  one-time scan and a live drift record without moving anything, or to stage an approved migration
  while a folder is being prepared. For a drop folder of files that belong to no project yet use
  file-preprocessing; for a folder that is already tidy use project-onboarding directly.
---

# folder-curation

Two skills already handle files at the ends of their life: `file-preprocessing` takes a **drop folder**
of files that belong to no project yet and owns them outright (understand, rename, move, hand back a
parcel), and `project-onboarding` takes a **ready folder** and puts a wiki and jobs beside it, reading
the owner's files in place and never reorganising them. Between the two sits the common case: a
**lived-in folder**, organised by its owner over years, with the overlaps, duplicates, strays and
opaque formats that years produce. Onboarding it as-is means the wiki inherits every ambiguity;
preprocessing it means running a conveyor over material the owner already filed. Neither fits.

This skill is that middle step. It has **two halves with one contract**:

- **Audit**: deterministic, read-only, repeatable. Produces the same hash-keyed manifest and
  `AUDIT.md` pair `file-preprocessing` produces (schema
  [`manifest-schema.md`](../file-preprocessing/references/manifest-schema.md), `/2`), extended
  with what a library needs: a type class per file, duplicate groups that know a deliberate copy from
  a redundant one, overlapping homes, and drift since the last pass.
- **Curate**: interactive, propose-only. Interviews the owner on a fixed ladder, turns the audit into
  a **move-plan** the owner approves row by row, executes only what was approved (under the same
  guards `file-preprocessing` moves under), and proves the result by re-auditing.

They are one skill because the second half is only safe **because of** the first (every move is
reversible by content hash, and the verify step has a baseline to diff against), and because the
first half is what the project keeps running after curation is done. Their **defaults are opposite**
to `file-preprocessing`'s, which is why this is not a mode of that skill: preprocessing is built to
act on files nobody has organised; curation is built to refuse to act on files somebody has.

**A component of `pre-onboarding`.** A person preparing a lived-in folder for the system starts at
[`pre-onboarding`](../pre-onboarding/SKILL.md), which runs this skill's audit and curation rounds in an
interactive session with the preparation tools in [`pre-onboarding/tools/`](../pre-onboarding/tools/),
then reads, summarises and builds the wiki over the curated result. This skill stays the method those
tools implement, and the method the folder-curation archetype's jobs keep running after onboarding.

## When to use

- A folder the owner already works in is being prepared for an AI-OS-style setup, and a read-only scan
  shows overlapping homes for one subject, duplicate trees, strays at the root, or formats the system
  cannot read. Start at `pre-onboarding`, which runs this skill first; the folder goes on to
  `project-onboarding` when the verify step is clean and the rest of the preparation is done.
- The owner wants a thorough one-time audit and a **live drift record** of a folder without anything
  moving. Run the audit half only; the `audit` job then keeps it current.
- A project that was onboarded without curation keeps raising filing ambiguities. Run curation
  retroactively; the wiki's existing citations are swept by the rename protocol.
- Files are to **migrate** between projects while a folder is being prepared. A curation round may
  propose one, and an approved plan of this skill stages the files in `_Migrations/<Project>/`
  (step 3); the folder is onboarded only once that folder is empty. Once a folder is maintained, no
  plan of this skill moves a file between projects: the owner's user-tier synthesis may suggest a
  migration (`wiki-maintenance`'s rule that a project files within itself), and the owner makes it
  by hand.

Not for: a drop folder of new files (`file-preprocessing`); a folder that is already tidy
(`project-onboarding`); a git repository (the `code` archetype); writing the wiki (`wiki-onboarding`).

## The shape of a curated folder

Beside the owner's material, named by whatever the deployment declares:

```
<Folder>/
  _Audit/
    manifest.json          hash-keyed, schema family-ai-preprocess-manifest/2
    AUDIT.md               the manifest rendered for people and cold AI readers; regenerated every pass
    plans/<YYYY-MM-DD>/    one folder per curation round; a second round the same day takes a suffix
                           (`<YYYY-MM-DD>-2`), never the same folder
      move-plan.csv        the proposal, then the approvals, then the execution record (one file, three columns filled in turn)
      undo.log             every executed row's reverse, appended as it happens
      review.tsv           for a migration round, each staged path with its copy kind and the copies
                           left behind; for a migration or return round, a MISSING row for each
                           listed path the manifest does not know
  _Migrations/<Project>/   files the owner approved for another project, at their original relative
                           paths, until that project collects them (only while a migration is open;
                           empty before the folder is onboarded)
  <rulebook>               the folder's standing instructions for any AI session (e.g. CLAUDE.md):
                           the depth the owner chose, the class policy, naming rules, exclusions,
                           where AI outputs land
  <the owner's folders>    unchanged except by approved rows
```

Reserved names (`_Audit`, the rulebook, the inbox, migrations and wiki names the deployment declares,
dotfiles, and any `_`-prefixed system folder) are never content. Anything else at the root that is not
a declared name is a **root stray** and appears in the audit as one. The migrations folder is the one
reserved name the audit still walks: a staged file is this folder's until another project collects it,
so it stays counted and carries the manifest's `migrating` flag.

## The method

Every step except **Propose** is deterministic. Steps 1 and 6 are the same pass.

### 1. Audit (deterministic; never moves anything)

Walk the whole folder under the scan contract the manifest reference defines (hash, adopt human
moves, spot edited files and strays, flag departed entries), then compute what a library needs:

- **A type class per file**, from the class policy below. Classes decide what is hashed in full,
  what is counted only, and what the later ingest may read.
- **A package is one item.** An iWork document saved as a package (a folder of member files) is
  audited as one item and never walked into: its id is computed by the manifest's package hash rule,
  and its entry carries `package`.
- **Files staged for another project**: every path under `_Migrations/<Project>/` sets the entry's
  `migrating` flag, with the project in `migration_target`, and the audit lists them in a section of
  their own. They leave the audit only when the other project collects them, and the entry is then
  `departed` (or, if a copy stays behind, simply loses the flag).
- **Duplicate groups** by content hash, across the whole tree. Copies of the same bytes share one
  manifest entry (the key *is* the hash), so a group is one entry with several `copies`, each path
  tagged by kind:
  - *redundant*: the same bytes filed twice by accident (`x.pdf` and `x (1).pdf`; a parallel
    tree built by copying);
  - *working copy*: a folder assembled by copying sources from their canonical home (a tax-year
    folder that copies bank statements in);
  - *pack*: a folder the owner declared, or the audit recognises by shape, as a **submission
    record** (an application pack that copies identity documents). Copies inside a pack are
    reference copies, never redundancy.
  Only *redundant* copies are ever candidates for deletion, and only after approval.
- **Overlapping homes**: one subject with more than one folder where its documents land (the same
  property under a transactions folder and an operations folder; identity documents under a person
  and under an ID folder). Detected by name and by duplicate groups that span two trees; listed as a
  pair with the count of files on each side.
- **Generic names**: files whose stem is a device or scanner default (`IMG_`, `Scanned Document`,
  `Screenshot`, `document`, chat-export prefixes), counted per folder.
- **Unreadable-by-design formats**: proprietary office formats the system cannot open, medical
  imaging, bundled software, camera originals, message files, counted per class and per folder; never
  flagged per run. iWork is read directly (the class policy below), yet the audit still pairs each
  iWork file with its export, because the owner shares and files the export, and a `convert` row that
  makes a second one is waste. A proprietary file is `unconverted` only when **no export of it can
  be confidently matched**, and the search is wider than the obvious one: people export to a sibling
  folder, to an outputs folder,
  and under a modified name ("… final", "… signed", a date appended). Matching only `X.pages`
  against `X.pdf` in the same folder therefore reports as unconverted a document that was converted
  years ago — and the plan's answer to that is a `convert` row that makes a *second* export. So
  match on the **normalised stem across the whole folder** (case, punctuation, whitespace and a
  short modifier list folded out), and let the strength of the match decide the flag. Two
  constraints keep "the whole folder" from over-reaching, and an archive of yearly folders is what
  needs them — `2022/Statement.numbers`, `2023/Statement.numbers` and one `2024/Statement.pdf` all
  share a stem:
  - **Nearest wins, and the order is fixed**: same folder, then the nearest common ancestor
    (fewest directory hops), then — only among candidates equally near — the one whose modification
    time is closest to the proprietary file's. A rule that says merely "break ties by mtime" leaves
    the direction to the implementer, and two conforming engines then disagree.
  - **An export is claimed once.** One export cannot convert three files; it pairs with the nearest
    claimant and the rest keep their `unconverted` flag. Without this, a single 2024 export clears
    the flag on every year in the archive and silently suppresses the rows that were right.

  With those, the flag falls out of the match:
  - a **confident** match (the normalised stems are identical) means the file *is* converted:
    **no `unconverted` flag**, and the pairing recorded on the entry (`convert_candidate`,
    `match: stem`). Record it by the export's **content id**, not its path, and re-confirm it by
    that id on every later pass — a shortcut past the search, not a replacement for it: if that
    content has left the folder (the ordinary re-export, where the owner edits the document and
    exports again, giving the export new bytes and a new id) the search simply runs again. The
    shortcut earns its place because the audit recomputes from disk
    each run, so a pairing held by name is undone by the first descriptive rename — including the
    ones this skill's own medium depth performs through `file-preprocessing` — and the file is
    re-flagged `unconverted` for ever after, proposing an export that already exists;
  - a **weak** match (the stems agree only after a modifier is folded out) stays `unconverted`, but
    with the candidate named — a `convert` row must point at the file it believes is not the export,
    so the owner declines in one look instead of re-deriving the question. A weak pairing is
    **provisional, never sticky**: the search runs again every pass, because the owner's usual
    answer to the flag is to make the real export, and a rule that stops searching while the old
    near-miss survives would leave the flag up for ever;
  - **no** match at all is `unconverted` with no `convert_candidate`: the plain case the flag was
    always for.

  **Stay deterministic**: this pass makes no model call, and comparing a proprietary bundle's
  *contents* to a PDF would mean reading documents, which the audit never does: it hashes and names.
  If a content-level comparison is ever wanted, it belongs in `curate`, which already reads.
- **Hygiene defects**: trailing or leading whitespace in a name, hidden system files, names that
  differ only by case, path components over the filesystem's byte limit, obvious misspellings the
  owner may confirm.
- **Live vs closed** per top-level folder, from the newest modification and the density of recent
  changes, so the later ingest can order its work and mark closed matters superseded.
- **Drift since the last pass** (from the second run on): added, removed, moved (same hash, new
  path: adopted, not flagged), edited (same path, new hash), new duplicate groups, new root strays,
  new files landing in an overlapping home.

**Every finding is a class, never a phrase**, and the free-text reason explains rather than
classifies. The audit's sections, the review lists and the plan's grouping are all derived from the
class, so it has to be a value: recovered by keyword from a sentence, "the same defect" is whatever
the wording happened to be that pass, and two identical files land in different sections. The
audit's own findings are **computed, never chosen by a model**, and they are carried by the flags
and fields the walk already sets — `root_stray`, `generic_name`, `unconverted`, `hygiene`,
`overlap`, `copies[].kind` — which is also why a file can hold several at once without anything
having to choose between them. The `look` classes are `curate`'s three *judgements* — `misfiled`,
`credentials`, `flagged` — and they classify the **escalations** it returns, the ones that feed the
raised-item ledger; not the rows of `move-plan.csv` (whose own `needs_a_look` column is free text
saying why a row wants judgement), and not manifest entries, which only the deterministic `audit`
writes here. The vocabulary and its extension rule are in
[`manifest-schema.md`](../file-preprocessing/references/manifest-schema.md).

Render `AUDIT.md` from the manifest as a pure function of the manifest (no clock; stamped from the
manifest's own `generated_at`). Every section carries its count **even when the count is zero**: a
sweep that saw nothing and a healthy folder must never read alike.

### 2. Interview the owner (a fixed ladder, one pass)

Show the audit, then ask, in this order, and record every answer in the rulebook:

1. **Who will use the maintained folder**, and does that need access boundaries inside it (one
   project, or split by audience)? **Confirm a boundary with the actual files**, never with a
   description of them: list, from the manifest, the paths on each side of the line the owner draws,
   and let them read the list. Owners describe a folder by what they meant it to hold; the files say
   what it does hold, and a boundary agreed in words moves the wrong ones.
2. **How far to reorganise**: present the depth ladder below as a comparison with what moves, what
   the owner relearns, reversibility and effort. The owner picks a depth; the plan never exceeds it.
3. **How new files arrive** today (a scanner to the root, attachments saved into subfolders,
   batches from a desktop), and whether anyone else writes to the folder. This decides the inbox.
4. **Which folders are closed matters** (ingested once as history, marked superseded) and which are
   live.
5. **Which formats are working formats**, and whether the owner will convert or export them. Under
   the class policy's default iWork is read directly, so an export is the owner's choice for their own
   use, never a condition of the system reading the document.
6. **Any explicit exclusions or identifier restrictions.** Full private content is the default
   under `wiki-maintenance`; compile excluded paths and any requested identifier restriction into
   job config. These decisions do not change the separate reorganisation depth selected above.
   See the enforcement boundaries in [`ARCHITECTURE.md`](../../ARCHITECTURE.md).
7. **Where AI outputs already sit** beside the sources, so the plan can relocate them.
8. **Language and naming** for renamed files and folders, where the material is bilingual — and the
   **names each person and organisation appears under**, every script and nickname included. The
   rulebook carries that alias list, and `file-preprocessing` is handed it in in-place mode, so a
   folder that has answered "who is this" once is not asked again per file.

If several agent filenames are needed, choose one rulebook source and generate byte-identical copies
(or supported links) for the others. Edit the authority, refresh copies in the same change, and have
reconcile check agreement. Do not create multiple independently maintained rulebooks.

### 3. Propose (the only model step)

From the audit and the answers, emit a **move-plan** (schema:
[`references/move-plan-schema.md`](references/move-plan-schema.md)). Rules:

- One row per action: `move`, `rename`, `delete`, `convert`, `create`, `rmdir`. Each carries the
  evidence hash of the file it touches (an `rmdir` or folder `rename` row excepted), the reason, the
  depth it belongs to, and the domain, so the owner can approve a domain at a time.
- **Never exceed the chosen depth.** Rows above it may be listed under a *later* heading for the
  next round, never mixed into this one.
- **Delete only redundant duplicates** proven by hash and outside any pack — a row names the
  redundant *path*, never the entry, so the canonical path always survives. Working copies are
  consolidated to their canonical home with a pointer note, never silently removed.
- **AI artefacts beside sources** (summaries, dashboards, session instruction files) move to the
  wiki or outputs tier the deployment declares; sources stay pure.
- **Content-based renames** (medium depth and above) are delegated to `file-preprocessing` in its
  in-place mode over the listed files, never re-implemented here.
- **Folder renames** carry the `wiki-maintenance` rename protocol: sweep every consumer of the old
  path in the same round, and log out-of-folder consumers as watch items.
- **Emptied folders** are removed only by an `rmdir` row, one per top-most folder the approved moves
  leave empty, proposed once those moves are approved and approved like any other row. It carries no
  evidence hash; the executor proves the folder empty on disk instead. Where the rulebook keeps empty
  folders (`keep_empty_folders`, the default), the owner declines the `rmdir` rows the tool proposes
  among their own folders; only the migrations folder's are approved by default.
- **Migrations are staged, never sent.** While a folder is being prepared, a file bound for another
  project moves by a `move` row into `_Migrations/<Project>/`, keeping its folder-relative path
  beneath, so the receiving project collects it from one place and a return is the exact reverse.
  Before the round, show the owner the actual files the boundary moves (step 2), and list against
  each staged path the copies that stay behind, so a duplicate is not taken for the file itself.
  Staging is a curation act, never a filing rule: the rulebook never routes new files into the
  migrations folder. It is a preparation act too: the folder is onboarded only once the migrations
  folder is empty, and once it is maintained no plan stages a file for another project, a move that
  belongs elsewhere being the owner's to make by hand.
- **Return migrations** bring a staged file the owner decides to keep back to its original path, by a
  `move` row out of `_Migrations/<Project>/`. When the approved return moves empty
  `_Migrations/<Project>/`, its `rmdir` row is proposed then, as for any emptied folder (above), and
  never in the same proposal as the moves, so a declined return cannot leave an `rmdir` that fails.
- **Never invent a taxonomy.** The owner's shape stays; the plan resolves conflicts inside it. A
  full re-taxonomy is a depth the owner must choose, and even then it is proposed as a mapping from
  every existing folder, never as a blank target tree.
- Anything the model cannot place with confidence is a `needs_a_look` — a `look` class, a
  `what_would_resolve`, and the evidence — not a guessed row. **One concern is one item, however
  many rows it touches**: an unfamiliar party, an unrecognised account, a folder whose purpose is
  unclear is asked once with its files as evidence, never once per file. The plan sees the whole
  folder at once, so it is the step that can tell a repeated question from a real one; the lifecycle
  rule is in [`ARCHITECTURE.md`](../../ARCHITECTURE.md).

### 4. Approve

The owner reviews the plan per domain and marks rows `approved`, `declined`, or `deferred`. Approval
is written **into the plan file**, so the executor has nothing to interpret. An unapproved row is
skipped and reported as skipped; it is never executed "because it was obviously fine".

### 5. Execute (deterministic; guards, not judgement)

Before anything moves, dry-run every row, delete rows included, under the executor's guards (a
destination clash excepted, which only the move itself sees), and fix or decline a row that fails.
Then execute approved rows in `seq` order: renames, moves and `create` rows first, conversions next,
`rmdir` rows once the moves that empty their folders are done, and deletions **last**, in a phase of
their own. Every row runs under the move guards the manifest reference defines (in-folder containment,
symlink refusal, hash-verify after the move, a two-phase op log so an interrupted round is resolved by
content, an undo entry per row), and two more: a file or package must hash to the row's evidence
before it moves, and nothing is ever overwritten. A `convert` row is complete only when the converted
file is verified (page or sheet count against the original) and the original rests under the archive
area the plan names (a `convert` row is not executed by the preparation tools; it is the owner's or
the deployment's). A failed row stops its domain and is reported with its reason; the rest of the plan
is not attempted "to finish the job".

- **The executor hashes exactly as the audit does.** A row's evidence is the manifest's content id,
  so the executor computes it the same way: a file's SHA-256, and a package's by the manifest's
  package hash rule. A second definition would refuse every package move as a hash mismatch, or pass
  one that should have failed.
- **Nothing is unlinked, and an `rmdir` needs an empty folder.** A deleted copy and a removed folder
  go to **the Bin**, and the undo entry records where each went, so either is restored by moving it
  back; an `rmdir` fails on any file left in its folder but `.DS_Store`. The exact rules are the
  plan schema's ([`rmdir` and the Bin](references/move-plan-schema.md#rmdir-and-the-bin)).
- **Deletes wait for a clean re-audit of the moves.** The executor refuses the delete phase until
  every other approved row is done and the folder has been re-audited since the last of them; run the
  step 6 proof on that re-audit, and start deleting only when it is clean.
- **Each delete row is re-verified against the fresh manifest**, not the one the plan was proposed
  from: the path must still be a copy that manifest marks `redundant`, a separate canonical copy must
  still exist, and both must still hash to the row's evidence on disk. Moves change which copy is
  canonical and what each copy's folder shares, so a delete judged against the old manifest could
  remove the copy that is now the one that matters.

On a case-insensitive filesystem, execute a case-only rename via an unused temporary name and
verify against filesystem identity as well as spelling; a case-sensitive comparison alone reports
phantom moves. Preserve the existing file on any failed rename.

**Expect a second round of redundancy.** Copy kinds are computed from the folder as it stands, so a
round changes them: once redundant copies and staged files leave, a folder's remaining files share a
different proportion with their canonical home, and a copy the last audit called a working copy can
now be redundant; a move can make another path canonical. Re-audit after every round, and propose the
redundancy it reveals as a further round, never folded into the round being executed.

### 6. Verify by re-audit

Run step 1 again, and prove the moves as a **(path, hash) diff**. Treat each manifest as the set of
(path, content id) pairs over every live path, copies included. The pairs that disappeared must be
exactly the executed rows' (`from`, `evidence`), and the pairs that appeared exactly their (`to`,
`evidence`); a folder rename accounts for every pair under the old path. Departures from
`_Migrations/<Project>/` after the other project collected its files are expected, and the proof
takes them only as an explicit allowance for that path, never as a silent pass. Anything else (a file
that moved that no row moved, a hash that changed, a count that shifted) is a **finding**, reported
with the row it should have belonged to. After the delete phase, re-audit once more and run the same
proof again from the same baseline: each done `delete` row's (`from`, `evidence`) pair is expected to
disappear too, so the proof then covers the whole round, and a canonical path that went with its
copy, or any other pair that changed, is a finding. Report
the round in the terms the counts mean: rows approved, executed, skipped, failed; files moved, renamed,
converted, deleted; findings.

### 7. Hand off

In preparation, the curated folder goes back to `pre-onboarding` for its extraction, cards and wiki,
and from there to `project-onboarding`. Either way, `project-onboarding` finds a folder with a
baseline manifest, a rulebook that records the chosen depth and rules, and no ambiguity a Schema
cannot route. Stamp the **folder-curation archetype**
(`../project-onboarding/archetypes/folder-curation/`) so the `audit` keeps running on a
cadence and `curate` can propose the next depth as a later round. The ladder is re-entrant: a
folder curated at light depth converges on medium one domain at a time, through the same plan and
approval loop, without a second migration.

## The depth ladder

| depth | what moves | what the owner relearns | when it fits |
|---|---|---|---|
| **light** | root strays into the inbox or their folder; hygiene defects; AI artefacts out of the sources; redundant duplicates moved to the Bin; system layer added | nothing | almost always the first round; the wiki carries the rest |
| **medium** | light, plus: overlapping homes resolved to one canonical home each; working-copy trees consolidated with pointer notes; generic names replaced by descriptive ones (via `file-preprocessing` in place); folder names normalised to the owner's language rule | a handful of moves | when routing ambiguity survives the Schema, one domain at a time |
| **full** | every folder mapped to a new top-level scheme | everything | rarely; only when the owner asks for it, and only as a mapping from every existing folder |

The wiki *is* the clean taxonomy. Reorganising the files to match it is the one thing the framework
says not to do, so **full** is offered for completeness and recommended against.

## Class policy (defaults; the rulebook may override per folder)

| class | matches | audit | later ingest |
|---|---|---|---|
| `document` | text-bearing formats: PDF, office documents, plain text, markup | hashed in full | read |
| `image` | photographs, screenshots, camera originals | hashed in full when under the size cap, else counted | read only when it is a scan of a document |
| `imaging` | medical or scientific image sets | counted per study | never read; the page notes the study exists |
| `software` | bundled viewers, installers, libraries beside data | counted per bundle | never read |
| `iwork` | Pages, Numbers and Keynote documents; a package counts as one item | hashed (a package by the manifest's package hash rule); a confidently matched export recorded, the rest listed once as unconverted | read directly, without the apps; a `convert` row only when the owner wants an export |
| other proprietary office formats | files the system cannot open | hashed, listed once as unconverted | read after a `convert` row |
| `email` | message files | hashed in full | read as text |
| `archive` | compressed bundles | hashed, contents listed when cheap | opened only on request |

A class decides cost as much as safety: a folder that is mostly photographs must not cost a full
walk of the photographs every tick. Count-only classes are still **counted**, per folder, every pass,
so a photograph folder that doubles overnight is visible.

## Principles

- **Audit first, always.** Nothing moves without a baseline manifest to reverse against.
- **Propose, approve, execute, verify.** Four separate steps with a record between each; the
  executor takes its rows only from the approved plan, and reads the audit for one thing: the fresh
  manifest it re-verifies delete rows against.
- **Opposite default to preprocessing.** That skill acts; this one refuses to act. Keep them
  separate skills sharing one manifest.
- **A copy can be a record.** Deletion is for redundancy proven by hash outside a pack; a
  submission pack is history and stays whole.
- **Nothing is permanently deleted.** Deleted copies and emptied folders go to the Bin, each with its
  undo entry, and no copy is deleted until the moves before it are proven. The Bin stays unemptied until the folder
  is onboarded: in a synced folder a removal reaches every device, and the undo entry syncs too, but the Bin it
  points to is on one machine only.
- **The owner's shape survives.** Resolve conflicts inside it; never replace it uninvited.
- **Counts, never silence.** Every audit section reports a number, zero included, and every round
  reports approved, executed, skipped, failed.
- **Skills describe; code enforces.** The guards named here are the deployment's to hold (the
  three-layer model in [`ARCHITECTURE.md`](../../ARCHITECTURE.md)), and during preparation the tools
  in `pre-onboarding/tools/` hold them; this skill says what they must guarantee.
