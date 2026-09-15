---
name: file-preprocessing
description: >-
  Preprocess a staging folder of unorganised files (scans, photos of documents, emptied-out drives —
  any type) that belong to no project yet: understand each file, categorise it, rename it to a
  descriptive party-first name in UK English, merge split scans back into whole documents, and hand
  back a finished, self-contained run folder — while maintaining a portable audit pair inside the
  folder: manifest.json (hash-keyed machine source of truth, schema family-ai-preprocess-manifest/1)
  and AUDIT.md (its human-readable rendering). Hash-keyed idempotency makes runs incremental and
  lets any conforming agent (an automated engine, a Claude Code session, any other AI with file
  access) continue another's work on the same folder. Use when handed a drop folder of accumulated
  files to triage before they join any project; the audit is the durable artefact that makes a later
  onboarding — by any system — cheap. Also callable in-place by folder-curation to rename
  already-filed files without moving them.
---

# file-preprocessing

A staging folder is a **conveyor, not a library**: files are dropped into `Incoming/`, a run turns
the batch into its own dated folder under `Runs/`, and that finished parcel is carried off. The
folder stays self-describing through two files that travel with it:

- **`manifest.json`** — the machine source of truth. One entry per file, keyed by the file's SHA-256
  content hash, so identity survives renames and moves. Schema
  `family-ai-preprocess-manifest/1` (authoritative definition: `references/manifest-schema.md`).
- **`AUDIT.md`** — a deterministic rendering of the manifest for humans and cold AI readers:
  category sections, per-file summaries and key facts, connections between files, a "Needs a look"
  list, and a "No longer present" list. Regenerated wholesale from the manifest every run — it is a
  view, never a second source of truth.

Colocation is the export story: each run folder also carries its own manifest+audit **slice** (paths
rebased relative to the run folder), so a collected parcel still explains itself wherever it ends
up; the root pair is the long memory that survives parcels leaving.

## The folder contract

```
<Staging Folder>/
  Incoming/            ← humans drop files here (nested drops fine)
  INSTRUCTIONS.md      ← optional standing operator context, family-editable. The per-run pasted
                         note is the SAME capability behind the same parser: either channel may
                         open with a ---fenced YAML front-matter of STRUCTURED engine directives
                         (split-scan merge geometry; themes; the alias list), stripped from the
                         model-facing body and validated strictly — a malformed block refuses the
                         run naming its source; a note-declared structure wins over a file-declared
                         one. The operator normally writes NEITHER: the planning step extracts
                         structure from plain prose (see the method), so context arrives as
                         ordinary words
  manifest.json        ← maintained by this method (root memory)
  AUDIT.md             ← maintained by this method
  Runs/<YYYY-MM-DD HHMM>/          ← one folder per run — the parcel a run hands back
    <Category>/…                   ← processed files, one level of category folders
    <Theme>/<Category>/…           ← only when the operator declared themes: worlds above the
                                     categories, each file assigned against the declared list,
                                     unknowns in the declared catch-all
    Needs a look/<Reason>/…        ← ONLY files a human must decide about (see below) — always at
                                     the run root, never per-theme
    _Archive/…                     ← originals of merged split scans, straightened sideways scans, and split bundles
    manifest.json · AUDIT.md       ← this run's slice, paths rebased
    NEEDS A LOOK.md                ← written ONLY when Needs a look/ is non-empty
```

The run-folder name is minute-granular, so it must be **collision-safe by rule**: if the name
already exists (two runs in one minute, an immediate retry), suffix deterministically —
` (2)`, ` (3)`… — never reuse or overwrite an existing parcel.

Reserved names (`Incoming`, `Runs`, `INSTRUCTIONS.md`, `manifest.json`, `AUDIT.md`,
`NEEDS A LOOK.md`, dotfiles, and any `_`-prefixed system folder) are never treated as content.
Pending vs done is visible at a glance: `Incoming/` empties as work completes.

## Needs a look — a reasoned surface, never a dumping ground

**Report the run in the terms the counts actually mean.** Merging and splitting deliberately make
"files in" and "documents out" differ, so state both — and count provenance (archived originals,
set-aside duplicates) APART from output, or a merge that takes two halves and yields one document
reads as no work done. Name WHERE the run's audit is rather than "see the audit": there is one per
run folder and one at the root. Never name a path that was not written — a dry run creates no
parcel, and a run can finish having applied nothing.

**The audit pair splits by scope.** Each run folder's `AUDIT.md` carries the full detail of the
files in it — including how each came to be (merged from, split from, straightened from, a
duplicate set aside). The audit at the folder ROOT is an INDEX of runs, one line each: re-rendering
every entry there duplicates each run's own audit, grows without bound, and describes files that
leave the moment a run folder is carried away.

**A run in flight must be visible as such.** If only one run can exist at a time, say so on the
surface: report liveness from the LOCK the engine holds, never inferred from the newest run row —
the engine takes the lock before it writes a row, and a refused dispatch writes none, so the row
alone cannot distinguish "no run" from "a run we cannot see yet". Publish what the run is doing
(stage, and a count for the long stages) into the run's own row, and let the FINAL write replace it
so progress cannot outlive the run it describes. While a run is live, do not render a waiting count
or a trigger the operator cannot act on.

"Needs a look" means **"read, but a human should decide"** — it must never mean "processing
failed". Two consequences:

- **A file dropped again that is already filed is SET ASIDE, not filed twice and not left
  loitering.** It moves to the run's `_Duplicates/` and the run reports how many. Three constraints
  shape this and each is load-bearing: the manifest is keyed by CONTENT HASH, so the copy must get
  **no entry of its own** (a second entry overwrites the filing it duplicates) — its location is
  recorded on the KEPT entry instead; the runs walker descends the whole run tree, so that record is
  also what stops the copy being rediscovered as a duplicate on every future run; and if the engine
  has a crash-recovery pass that repairs committed moves into manifest placements, the move must
  declare that it claims no placement, or the kept file's entry migrates onto the copy and the real
  filing is orphaned. A forced re-processing run re-admits what is in the drop folder, so a copy
  already set aside is not re-admitted — re-drop it.
- **A chunk's answers are reconciled against what the chunk asked before any of them is applied,
  and a chunk that fails reconciliation is retried halved, never applied in part.** Understanding
  runs in chunks, and a batch of near-identical inputs — a run of monthly statements, a folder of
  timestamped scans, images named by convention — is where a model quietly returns one answer for
  two files, or the same path twice, or a path it tidied on the way out. A *missing* answer is
  visible and the sweeper below takes it; an answer attached to the **wrong file** is a confident,
  well-formed, wrong document name that nothing downstream can detect and the audit will happily
  record. So match answers by an **id the engine issued**, never by position in the reply and never
  by the path echoed back — the path is precisely what gets normalised when two inputs look alike —
  and require exact set equality with the request, rejecting a duplicate id and an unknown one.
  Halving separates the look-alikes that caused the collapse; a chunk of one that still fails is a
  single unanswered file and falls to the sweeper. Applying the matched subset of a failed chunk is
  the tempting wrong move: it banks exactly the answers whose neighbours were mishandled.
- A file the understanding step failed to answer for — omitted from a reply, dropped by a chunk
  that failed reconciliation, or belonging to a chunk that died on a timeout/exhausted backend —
  gets **one in-run sweeper retry**: the
  unanswered files are re-asked in their own small chunk(s), with routing run fresh so a dead
  backend's files retry on the next eligible one. Still unanswered, the file **stays in
  `Incoming/`** with no manifest entry, and the next run retries it as an ordinary drop. Failures
  retry — first automatically within the run, then across runs; they are never filed as
  judgements. A first-round failure the sweeper fully recovers from is a healed run, not an error;
  only a failure that leaves files behind colours the run status.
- The look queue is OPEN QUESTIONS, and fresh operator context re-opens them: a run carrying a
  pasted note re-admits every look-flagged file for a fresh judgement — no force flag (force is
  for re-judging SETTLED filings; an open question never needs it). A resolved file moves into
  the CURRENT run's parcel, its hash-keyed entry advancing in place; the prior verdict is
  excluded from the prompt index like any candidate's, so it cannot contaminate the fresh one.
  A run with no note re-judges nothing.
- The operator's stated facts beat filename patterns: a file whose NAME claims half a split scan
  (单数页/odd pages) but which the context declares a COMPLETE document is exempted from pair
  detection entirely (declared `complete:` front-matter or extracted from prose through the same
  validators) — no merge hold, no lonely-half flag, no odd-pages note.
- The audit records HOW each document came to be, not just where it sits: per-entry
  Merged from/into, Split from/into and Straightened from/into lines, derived purely from the
  manifest's lineage fields. **A transformation whose output is consumed by a later step still has
  to be recorded somewhere** — a scan straightened before being merged has its upright copy eaten
  by the merge, so unless the straightening is written onto the archived original, the run reports
  work the audit cannot account for. Reconcile the counts a run reports against what is recorded,
  in a test — and **count the work where its record COMMITS, not where the work is minted**, or the
  same unaccountable claim simply moves to the failure path: a transformation whose document never
  files leaves the user's originals to be redone next run, and reporting it as done is a lie the
  audit cannot corroborate.
- **Every record of a location is reconciled against the folder, every run.** A record written once
  and never re-checked drifts: a set-aside copy the operator deletes by hand stays advertised for
  ever, and any count derived from that record climbs while the folder shrinks. Walkers cannot
  catch this alone — they enumerate what EXISTS and this is an absence — so reconcile at the
  source, which is what keeps every reader (the scan, the audit, an index) honest without each
  re-checking. Three rules make that reconciliation safe, and each one exists because its absence
  is a silent wrong answer:
  - **Judge by what the walk OBSERVED, not by a fresh existence probe.** The walk has already
    hashed the tree the records point into, so its digests answer both questions at once: is the
    file still there, and is it still the content this record claims. Existence alone cannot see a
    path whose bytes were replaced — the record then asserts for ever that a file is a copy of
    something it no longer contains.
  - **Only a PROVEN absence retires a record.** Retiring one is irreversible provenance loss about
    the user's own document, so every uncertainty resolves to keep-and-say, never drop-and-forget.
    Beware the language's convenience call: `Path.exists()`-style helpers answer *false* for a file
    that merely cannot be stat-ed, collapsing "gone" and "cannot tell" into one answer — a
    transient permission or I/O blip then erases provenance permanently. Distinguish
    not-found from any other error, keep the record on the latter, and report it.
  - **A path read out of a file is untrusted, even your own.** Records are joined to a root and
    probed, so run them through the same containment and symlink guards every other file-sourced
    path passes. A record that escapes the folder or has become a symlink cannot be one the engine
    wrote: refuse it *without* probing it, and say so.
- A file lands under `Needs a look/` only with a **stated reason, and the subfolder IS the
  reason**: `Unrecognisable/` (no substantive read possible — keeps its original filename; there is
  nothing trustworthy to rename it by), `No date/` (a date exists on the document but could not be
  read; an undated-but-understood file just files normally with the date absent from its name),
  `Too large/` (beyond every processing tier — terminal, original name, never retried), and
  `Flagged/` (the model flags with a concrete stated reason). An unexplained "low confidence" is
  NOT a reason: it files the document normally. `NEEDS A LOOK.md` inside the run folder lists each
  file with its reason; its very presence is the signal — a clean run writes none.

## The method

Work through these steps. Three are model calls — the whole-batch **planning** call, **Understand**,
and **Reduce**; every other step is deterministic.

1. **Scan.** Walk the whole folder as the manifest reference's **scan contract** defines it (hash
   every file; confirm each entry is still at its recorded path; adopt human moves; spot edited
   files and strays; flag departed entries) — that is the part every producer of this manifest
   shares. What the conveyor adds is the drop folder's own semantics: in `Incoming/`, a hash already
   live in the tree is a **duplicate** — leave it and note it; a hash whose entry is flagged
   `departed` is a **return** — reuse its recorded classification and filename with no model call,
   but place it into the CURRENT run's parcel, never back into the departed parcel its history
   names (that parcel has been carried off; recreating it would break the
   one-self-contained-parcel-per-run promise); the rest are candidates. And a placeholder is a
   refusal here, not a note: **refuse to start** while any dropped file is still a cloud
   placeholder — a partial run splits one logical drop across two parcels.
2. **Read — no arbitrary caps, a tiered ladder instead.** Extract text however the environment
   allows (a text read, OCR for scans/images, speech transcription for audio). Never truncate a
   long document and report it as whole: probe cheaply first (page count, text-layer presence) and
   pick a tier — a real text layer lifts in full at any size; a scan within the local OCR tier's
   measured capacity is read in full; past that, hand the whole file to a vision-capable model to
   read directly; past every tier, `Needs a look/Too large/` — a terminal, visible stop, never an
   infinite retry. A file with no extractable text at all is never guessed at: it goes to
   `Needs a look/Unrecognisable/` keeping its original stem, entry flagged `unreadable`.
   **The ladder is ordered by cost as much as by capability**, which is why it is a ladder and not a
   choice: the text read and the local tier are free at any volume, the vision tier is billed per
   page, and a backlog is thousands of pages. Descend only as far as a file actually needs, never
   enter at the top "to be safe", and name the tier each file was read at in its entry — a run whose
   spend cannot be attributed to a tier cannot be tuned (`extraction.tier`). The skill fixes the *rungs*; which backend
   fills a rung is the deployment's to declare and its own to keep current.
   **A rung must be checked against the material's languages, or it fails silently.** A local
   recogniser without the folder's script installed does not report that it cannot read the page: it
   returns nothing, and a document a person reads at a glance lands in `Needs a look/Unrecognisable/`
   as though it were a bad scan. Declare the scripts a rung covers, and treat an empty extraction
   from a file whose class says it should have text as a **capability gap to report** — falling
   through to the next rung — rather than a verdict about the document.
3. **Straighten sideways scans — before pairing, so merges consume upright halves.** Decide the
   clockwise correction (0/90/180/270) from the READING DIRECTION of the page's recognised text
   lines, never from recognition scores (modern recognisers read text at any rotation nearly
   equally well, so every orientation scores the same); vote weighted by characters over
   confident lines, and act only on a clear win — a genuinely mixed page is left alone. Rewrite a
   clear-verdict scan upright (a content-lossless page-rotation), re-extract it so OCR reads
   upright pages, file the upright copy as the work item, and rest the sideways original in the
   run's `_Archive/` — lineage `rotated_from` on the filed copy, `rotated_into` +
   `archived_original` on the original, mirroring the merge pair's, and archived only once the
   upright copy's own move lands. A failed orientation check is counted and the file proceeds
   as-is — the check is an enhancement, never a hostage-taker.
4. **Merge split scans.** A duplex-less scanner saves one document as two PDFs: odd pages and even
   pages, marked in the name (单数/双数, 奇数页/偶数页, 单页/双页, "odd pages"/"even pages" — an
   extensible marker table; never bare "odd"/"even", which appear in ordinary titles). Pair
   marker-named files whose remaining stems match; gate on page counts that can actually
   interleave — odd leads by default (odd = even or even+1), and an operator directive in the
   `INSTRUCTIONS.md` front-matter can declare a pair **even-first** (its first odd page is
   missing) and/or a half **scanned backwards**, with the gate evaluated for the declared
   geometry:

   ```yaml
   ---
   merge:
     - match: "<substring of the marker-cleaned stem>"
       order: even_first          # default odd_first
       reverse_even: true         # and/or reverse_odd
       note: "<free text, recorded in the audit>"
   ---
   ```

   The planning step (step 7's whole-batch planning, which runs BEFORE this one) also extracts this
   geometry from the operator's plain prose, so the operator normally writes no YAML at all —
   extracted structure passes the same validators, and declared front-matter always wins.
   Interleave into ONE new document and process that as the work
   item; move both originals to the run's `_Archive/` with entries pointing at the merged entry.
   The merged entry's id is the merged FILE's own SHA-256, like every entry — the hash contract
   and the move guards in step 10 are unchanged. **Re-merge deduplication works through the
   halves**: each half keeps its own hash-keyed entry (`archived_half`, `merged_into` → the merged
   id; the merged entry lists both in `merged_from`), so a re-dropped half is an ordinary
   duplicate of an already-filed file and the pair is never re-merged. That linkage — not the
   merged bytes — is what makes the merge deduplicable at all: PDF writers embed creation
   metadata, so the same halves never merge to identical bytes twice. **A marker-named file whose
   twin is not in this batch files VISIBLY**: it is understood like any file and lands in
   `Needs a look/` under its understood name with an engine-derived "(odd pages only)"-style note
   in the filename — an invisible wait state misleads ("waiting" on a finished run implies the
   run will act later; it never does). The entry keeps `original_name` (marker intact), so a
   human can still pair it by hand if the twin ever arrives. (Supersedes v4.0–4.1's wait-state
   rule.) Only a pair whose counts cannot
   interleave (under its declared geometry, when one is declared), or a merge that failed, is a
   human decision (`Needs a look/Flagged/`, reason stated). **The originals archive in the same step that files the merged document, never
   earlier** — if understanding the merged document fails, the halves must still be sitting in
   `Incoming/` as ordinary candidates and no parcel may reference a document nobody filed.
5. **Split confident bundles** (the PROPOSAL comes from the non-deterministic Understand step;
   everything this step itself does — validation and execution — is deterministic). One physical
   file sometimes holds several standalone documents
   (five reminder letters scanned as one PDF). The understanding step may propose a `split` —
   page ranges plus per-part fields — ONLY when the boundaries are certain and each part has its
   own date/type/parties. The engine validates a strict partition (every page exactly once, in
   order, ≥2 parts) and executes it whole or rejects it whole: a rejected proposal files the
   bundle as ONE document flagged with the reason, never a partial split. Parts are validated
   through the same entry path as any answer and flow through every later step; lineage mirrors
   the merge contract — parts carry `split_from`, the bundle archives to the run's `_Archive/`
   with `split_into` + the `archived_bundle` flag, and ONLY once every part's own move has
   landed. Keep part names concise ("PAYE Statutory Payment Repayment"), never an inventory.
6. **Understand** (a model call, one of the three). For each readable candidate, decide: `party`,
   `doc_type` (short English type), `doc_date` (from the document's own content, ISO, never
   invented), `detail`, `title`, a rich 2–3 sentence `summary`, `key_facts` (dates, amounts,
   reference numbers actually read), `parties`, `category`, `connections` (real relationships to
   already-audited files, referenced by manifest id), an optional structured
   `look` + `look_reason` (see below), and honest flags.
   **`look` is a closed vocabulary and `look_reason` explains rather than classifies.** The model
   may choose exactly one value, and only one: `flagged` — something about this document a person
   must decide, stated in `look_reason`. Every other look state in this skill is **computed, never
   chosen**: `unrecognisable` and `no_date` are the engine's verdicts about extraction, `too_large`
   is the ladder's terminal rung. Letting a model select a computed value re-opens the drift the
   folders exist to close — two files with the same defect classified differently because the wording
   drifted. The reason stays free text because a person reads it; the class stays closed because the
   engine routes on it (see the vocabulary in `references/manifest-schema.md`, which is extensible
   the way flags are — a consumer ignores a value it does not know). **Judge every file fresh from its
   content** — when re-processing a file the manifest already knows, exclude its own prior entry
   from any index shown to the model, so a stale verdict is never inherited; a rich summary is
   incompatible with an "unreadable"-style title. **A `date_unreadable` verdict from a text-only
   read earns one bounded second look with the actual file open before `No date/` ever sees it**
   — the proven failure is an extraction that truncated a date a human reads at a glance; only an
   answer with a real date and no attention request replaces the original judgement.
   **Known parties are context the step is given, not something it infers.** A staging folder
   belongs to no project yet, so there is no wiki and no rulebook to consult: the operator's channel
   is the standing `INSTRUCTIONS.md` and the pasted note, and an **alias list** — every name, script
   and nickname a person appears under — is one of the structures the planning step extracts from
   plain prose (step 7), through the same validators as declared front-matter. Given it, a document
   naming someone under an unfamiliar form is understood, not queried. Without it the party is simply
   recorded as read, `unknown_party` where it falls back — a flag, never a look: an unrecognised name
   is not by itself a reason to interrupt a person, and the batch usually explains it (step 7). In
   **in-place mode** the caller has a rulebook; it passes the alias list from it, so a folder that
   has already answered "who is this" is not asked twice. **Name and
   describe in UK English by default**
   (general terms translate; a hard-to-translate proper noun keeps both forms side by side, so the
   file stays findable by either); `INSTRUCTIONS.md` is the channel to ask otherwise. Reuse an
   existing category when one fits; create a new one only when none does (case-insensitively —
   "medical" must never mint a second "Medical"). The attention buckets ("Needs a look", legacy
   "Needs Review") are never categories the model may choose.
7. **Reduce across the whole batch — after every group's answers validate, before anything
   applies.** (Its sibling, the whole-batch PLANNING call, runs before the merge: it designs the
   category vocabulary AND extracts operator structure — merge geometry, themes, the alias list —
   from plain prose through exactly the front-matter validators; declared always wins over
   extracted.) Understanding in bounded groups leaves two things no group can settle: category
   consistency (a group's pick is an accident of packing) and relationships between files read in
   different groups. One reduce pass over every accepted entry's compact row (id, prospective
   filename, category, title, a short summary, date, parties) plus the prior-run index settles
   both: re-route files whose category disagrees with how the whole batch hangs together (never
   into an attention or archive placement — those are the engine's), and record the real
   relationships **on BOTH entries** — an invoice knows its receipt exactly as the receipt knows
   its invoice, including reverse links onto prior-run entries. It also **collapses the batch's
   repeated questions**: a concern about an entity that dozens of files raise separately — a party
   none of them explains, an unrecognised account or body — is one question with one answer, so
   reduce resolves what the batch itself settles (a name that appears in full on one document and
   abbreviated on twenty) and emits the residue **once**, keyed on the entity with the files as its
   evidence list, never once per file. Eighty look items with one answer between them is not
   attention; it is noise that hides the eight real ones. Advisory by construction: a
   failed reduce leaves the groups' own judgements standing.
   **The two model stages have opposite economics, and a deployment should route them separately.**
   Understand is per-file, small-context and high-volume — the cheapest backend that clears the bar,
   because the batch is what costs. Reduce and its planning sibling see everything at once and are
   the only steps whose judgement is about the *whole* batch — the strongest reasoning available, run
   twice a run. Routing both at one tier is a decision either way; make it deliberately (the
   framework rule is in [`ARCHITECTURE.md`](../../ARCHITECTURE.md)).
8. **Guard the answers — once, where they cross into the deterministic side.** Every free-text
   field the reasoning steps returned passes the deterministic redaction guard **here**, before any
   of them is used to name a file, move it, write an entry, raise an item or render a view. That is
   the whole set, named rather than gestured at: the fields that reach the manifest (`title`,
   `summary`, `key_facts`, `look_reason`, `parties`, and every `connections[].relation` — whoever
   wrote it, the understanding pass or the reduce pass that revised it, since reduce is advisory and
   a failed one leaves the groups' own relations standing), the ones only a filename is derived from
   (`party`, `doc_type`, `detail`), and the text of any item the run **raises** (`item`, `reason`,
   `what_would_resolve`, `owner_action`, `proposed_action` — `owner_action` above all, since naming
   which account to go and find is exactly what it is for) —
   an escalation about an unrecognised account is precisely where a model repeats the account
   number, and the ledger it lands in is read by people and by later runs. `parties`, `relation` and
   the raised text are the three a guard written from memory omits, and the three a model most
   naturally qualifies with the number it just read ("… — account 12345678"). Placing it at the manifest
   write would be too late: the very next step builds the filename out of `party` and `detail`, and
   a full account number a model put in `detail` would already be on the filesystem — in the name,
   in `current_path`, and in `rename_history` — before any guard saw it. One crossing, one guard,
   and everything downstream is already clean. The targets are typed, not a digit hunt —
   `reference_numbers` is a field this schema *wants* populated, so it passes at the depth the
   operator declared while account, card, licence and document numbers reduce to their last 4 — and
   every redaction is **counted and reported in the run summary**, because a guard that silently
   does nothing and one that silently does everything look the same from outside. The framework
   rule, and why the prompt instruction alone was never enough, is in
   [`ARCHITECTURE.md`](../../ARCHITECTURE.md).
9. **Name and place — deterministically, from the guarded fields.** Filename pattern:
   `<Party> - <DocType> <YYYY-MM-DD> <Detail>.<ext>` (e.g.
   `Wren - Lab Report 2026-03-14 Vitamin D.pdf`). Fallbacks are fixed: unknown party → `Unknown`; no
   trustworthy date → the date segment is omitted, never fabricated; empty detail → omitted. Keep
   the extension, lowercased. Sanitise every segment (NFC-normalise; strip path separators,
   control characters, trailing dots/spaces; cap length in UTF-8 bytes — filesystem limits are
   byte limits). On a name collision append ` (2)`, ` (3)`… — never overwrite, never skip.
10. **Move under guards** — the **move guards** the manifest reference defines, unchanged: in-folder
   containment and symlink refusal, destination folders created only when a move needs them, a
   hash-verify against the entry id after the move, a two-phase op log replayed on the next run so
   an interrupted move is resolved by content, and an undo entry appended before each move is
   attempted. The category and reason folders are this skill's destinations; the guards they are
   reached through are every producer's.
11. **Record.** Merge each entry into `manifest.json` (atomic write). A re-understood file keeps its
   identity fields (first seen, name history, placement) and refreshes the descriptive ones. An
   edited file is a new entry (new hash) understood **in place** — do not rename or move a file the
   human has already accepted under its name; the old entry departs.
12. **Reconcile presence — against a full walk, never a limited subset.** The scan contract's
   departed-entry rule (flag, never delete — the audit's history is the point), read through the
   conveyor: a whole run folder leaving is normal, so its entries simply depart rather than
   reading as loss, and a departed file's return sheds the flag.
13. **Render the views** from the manifest: `AUDIT.md` (self-describing header, sections by
   category, connections rendered to current filenames, "Needs a look" with each file's reason,
   "No longer present"), the run folder's manifest+audit slice, and `NEEDS A LOOK.md` when — and
   only when — the run's look folder is non-empty.

## Purpose-specific rereads and restart safety

Choose the read rung per **purpose**, not just per file: figures need layout-preserving columns and
sufficient text for the table, whereas understanding may need less. Declare truncation and read status
for each purpose; never reuse a summary as if it were a complete figures extraction. For targeted
rereads, worker restart joins, cache versioning and per-answer model provenance, follow
[the architecture's durable extract rules](../../ARCHITECTURE.md#durable-extracts-for-rendered-wikis-opt-in).
When degenerate-answer detection is enabled, that outcome stops the backend for the run rather than
spending the chunk retry budget on repeated non-answers.

## Interop

Because entries are keyed by content hash and every mutation is guarded and recorded, runs are
idempotent and **agents compose**: an automated engine can do the bulk pass, a human can hand-move
files (adopted next run), and any other AI following this skill can pick up the same folder and
continue — same manifest, same naming, same semantics. Cost control on big backlogs: process a
bounded batch per run (oldest first) and re-run; the manifest makes every pass incremental. The
bound must be **split-scan aware** or it starves: a waiting half must not consume a batch slot
(oldest-first would re-select it every run, and with a small bound its twin — sitting just past
the boundary — would never be admitted, deadlocking the queue), and a selected half pulls its
twin into the same batch even from beyond the boundary, so a pair always travels together (the
bound is a cost cap, not an exact count).

**In-place mode.** A caller (today `folder-curation`, at medium depth) may hand this skill a **list
of files that already live in their folders** and ask for understanding and renaming **without moving
them**: the file is understood exactly as a candidate would be, named by the same pattern, and
renamed in place; no run parcel is created, no category folder is minted, and the manifest entry
records the rename in `rename_history` with the caller's plan reference in `plan_ref`. Split-scan
merging and bundle splitting still apply (the merged or split output lands beside the original), and
the original rests in the caller's archive area rather than a run's `_Archive/`. In-place mode never
touches a file outside the list it was given. **The caller also hands over the folder's settled
answers** — the rulebook's alias list, its language and naming rule, and its per-domain sensitivity
depths — so a folder that has already answered "who is this" and "how deep for health" is not asked
again, and the redaction guard applies the owner's depths rather than the default.

The reference implementation is family-ai-os's `preprocess` engine (dashboard-triggered, chunked
LLM calls under a context budget with parallel chunk reads and strictly ordered applies, on-device
OCR + probe + orientation, native interleave-merge and page-rotation tools); this skill is the
portable spec any agent can execute by hand.
