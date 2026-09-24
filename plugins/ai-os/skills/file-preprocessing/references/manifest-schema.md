# family-ai-preprocess-manifest — the manifest schema (/1 and /2)

`manifest.json` at the staging-folder root. Top level:

```json
{
  "schema": "family-ai-preprocess-manifest/1",
  "generator_version": "<producer's own version string>",
  "generated_at": "<ISO datetime of the last write>",
  "entries": { "<sha256-hex>": { … } }
}
```

`entries` is keyed by the file's **SHA-256 content hash** — the entry's stable id. Identity follows
the bytes, not the name: renames and moves update `current_path`, never the key. An unknown
`schema` value must be treated as a foreign file (fail loud), never silently rewritten.

`/2` is a strict superset of `/1`: every `/1` field keeps its meaning; the fields below are added.
A `/1` consumer reading a `/2` file must ignore the fields it does not know; a `/2` consumer reading
a `/1` file treats every added field as absent. The schema string is
`family-ai-preprocess-manifest/2`. Producers: `file-preprocessing` (either), `folder-curation`
(always `/2`).

## Entry fields

| field | type | meaning |
|---|---|---|
| `id` | string | the sha256 hex, equal to the entry's key |
| `original_name` | string | the filename as dropped, before any rename |
| `current_path` | string | folder-relative path today, e.g. `Medical/Wren - Lab Report 2026-03-14 Vitamin D.pdf` |
| `rename_history` | list | `{path, at, run_id}` per placement, oldest first |
| `category` | string | the category folder name |
| `title` | string | one-line title |
| `summary` | string | 2–3 sentences, the document's own language |
| `key_facts` | object | `{dates: [], amounts: [], reference_numbers: []}` — strings actually read from the document |
| `parties` | list of strings | every person/organisation involved |
| `doc_date` | string or null | ISO date from the document's content; null when none was trustworthy |
| `language` | string | primary language code (`en`, `zh`, …) |
| `pages` | int or null | page count when known |
| `extraction` | object | how the text was obtained: `{ocr: bool, tesseract: bool, speech: bool, status: string|null, tier: string|null}` — `tier` names the rung of the read ladder that actually produced the text (`text_layer`, `local_ocr`, `vision`, `speech`, or a rung the deployment adds), so a run's spend can be attributed. `none` when no rung produced any — the entry is `unreadable` or `too_large` — which is a real outcome to count, not an absence. `null` means only "written before this field existed"; it is never a silent default for a read that happened |
| `connections` | list | `{to: <sha256 of a related entry>, relation: <why>}` — real relationships only, recorded on BOTH entries (an invoice's entry names the receipt exactly as the receipt's names the invoice) |
| `flags` | list of strings | named states, see below |
| `look` | string, optional | the **class** of the single concern that makes this entry a human's decision — for `file-preprocessing`, the placement class of the `Needs a look/` folder it landed in (`unrecognisable`, `no_date`, `too_large`, `flagged`). At most one, because a file lands in one folder. Absent when the entry raises no decision. Which producer writes this field, and what a producer that does *not* does instead, is in the vocabulary section below |
| `look_reason` | string, optional | why this file needs a human decision, in the flagger's own words; absence ≡ `""` (every pre-v4 entry lacks it — consumers must treat missing as "no reason") |
| `merged_from` | list, optional | on a merged split-scan document: the two source halves' sha256 ids |
| `merged_into` | string, optional | on an archived split-scan half: the merged entry's sha256 id |
| `rotated_from` | string, optional | on a straightened (upright) copy of a sideways scan: the original's sha256 id |
| `rotated_into` | string, optional | on the archived sideways original: the upright copy's sha256 id |
| `split_from` | string, optional | on a part extracted from a split bundle: the bundle's sha256 id |
| `split_into` | list, optional | on an archived bundle: the parts' sha256 ids |
| `theme` | string, optional | the declared theme (world) the file was assigned to, when the run declared themes |
| `first_seen` | string | ISO datetime the file first entered the manifest |
| `processed_at` | string | ISO datetime of the last understanding pass |
| `departed_at` | string, optional | present only while `departed` is flagged |

### Added in /2

| field | type | meaning |
|---|---|---|
| `class` | string | the type class from the class policy: `document`, `image`, `imaging`, `software`, `iwork`, `email`, `archive`, `other` |
| `size` | int | bytes at last scan |
| `mtime` | string | ISO datetime of the file's last modification at last scan |
| `hashed` | bool | `false` for count-only classes (the key is then derived from `size:mtime:path` and marked `synthetic_id: true`); such an entry is never a duplicate candidate |
| `synthetic_id` | bool, optional | present and `true` when `hashed` is `false` |
| `copies` | list, optional | every live path holding these bytes: `{path, kind}`, `kind` being `canonical`, `redundant`, `working_copy` or `pack`. Present only when the entry has more than one path; exactly one is `canonical` |
| `overlap` | string, optional | the overlap pair id this file's folder participates in (the audit's *Overlapping homes*) |
| `generic_name` | bool, optional | the stem is a device or scanner default |
| `plan_ref` | string, optional | `plans/<date>/move-plan.csv#<seq>` of the last approved row that touched this entry |
| `convert_candidate` | object, optional | on a proprietary-class entry, the export the audit found for it: `{id, path, match}`. `id` is the export's own sha256 and is the authority — the pairing is re-confirmed by it first, so renaming either file does not break it; `path` is where that content sat at the last scan. `match` is `stem` (identical normalised stem) or `stem_near` (normalised stem plus a modifier — "final", "signed", an appended date), and records how the pairing was *first* established. Absent means no candidate was found at all. A `stem` match means the file **is** converted, so the entry carries no `unconverted` flag; a `stem_near` match is `unconverted` *with* the candidate named, so a `convert` row can point at what it thinks is not the export |

**Duplicates do not mint entries.** Copies of the same bytes share one hash, so they share one key
and one entry — the `/1` rule that a copy gets no entry of its own, unchanged. A duplicate group
therefore *is* an entry, and needs no group id of its own. What `/2` adds is `copies`: the several
live paths that one entry has, each with the kind that decides what may be done to it. `redundant`
is the only kind a deletion may name; a `working_copy` is consolidated to the canonical path with a
pointer note; a `pack` copy is a submission record and stays whole. A count-only entry (`hashed:
false`) is never a duplicate candidate and never carries `copies`.

## Flags

`low_confidence` (extraction was weak) · `unreadable` (no extractable text; filed to
`Needs a look/Unrecognisable/` unguessed, original stem kept) · `too_large` (beyond every
processing tier; filed to `Needs a look/Too large/`, terminal) · `archived_half` (an original
half of a merged split scan, resting in the run's `_Archive/`) · `partial_read` (legacy: only part
of the document was read under the old page cap — no longer produced, still recognised) ·
`undated` (no trustworthy document date) · `unknown_party` (party fell back to `Unknown`) ·
`departed` (the file is no longer anywhere in the folder; the entry is history, never deleted) ·
`needs_a_look` (a human decision is wanted — always accompanied by a `look` class, and by a
non-empty `look_reason` when that class is `flagged`; the computed classes are self-explaining, the
folder being the reason) · `archived_original` (the sideways original of a straightened scan, resting in the run's
`_Archive/`; `rotated_into` names the upright copy, whose own entry carries `rotated_from` back) ·
`archived_bundle` (a multi-document file split into its parts, resting in the run's `_Archive/`;
`split_into` names the parts, whose own entries carry `split_from` back).

The vocabulary is extensible; consumers must ignore flags they don't know. A merged split-scan
document's entry id is still the merged file's own SHA-256 (the hash contract is uniform);
**re-merge deduplication** rides the halves' own hash-keyed entries via `merged_from`/`merged_into`
— necessary because PDF writers embed creation metadata, so the same halves never merge to
identical bytes twice.

**Added in /2:** `root_stray` · `unconverted` (an `iwork` or other proprietary file for which no
export could be confidently matched — the match rule is the `folder-curation` skill's; a confident
match clears the flag, a weak one leaves it set with the candidate named in `convert_candidate`) ·
`hygiene` (a name defect; the defect kind
goes in `look_reason`). Same rule as before: consumers ignore flags they don't know. All three
describe the entry's path — on an entry that has a `copies` list they describe its canonical one;
the other copies are described by their own `kind`, not by a flag.

## The `look` vocabulary

`look` is the **class** of a concern; `look_reason` is its explanation. The split exists because two
readers need different things: the engine routes on the class (a folder, a section, a count), and a
person reads the reason. Keep the class closed and the reason free, never the reverse — a class
carried in prose has to be recovered by keyword-matching a sentence a model wrote, and two files
with the same defect then land in different places because the wording drifted.

**Producer `file-preprocessing`:** `unrecognisable` · `no_date` · `too_large` · `flagged`. Exactly
one applies, because the file lands in exactly one `Needs a look/<Reason>/` folder. The first three
are the engine's own verdicts — computed from what extraction returned and which rung of the read
ladder was reached; only `flagged` is a model's to choose, and it always carries a non-empty
`look_reason`.

**Producer `folder-curation`:** `misfiled` · `credentials` · `flagged`, all three the `curate`
step's judgements, explained by the item's own `reason` (that output's field name; `look_reason` is
this file's). They classify the **escalation items** `curate` returns in its `needs_a_look` array —
the ones that feed the raised-item ledger — and *not* rows in `move-plan.csv`, whose `needs_a_look`
column is free text saying why a row wants judgement rather than a class. Nor do they reach a
manifest entry: in that archetype the manifest is written only by the deterministic `audit`, which
makes no model call, so a `look` on an *entry* is `file-preprocessing`'s alone. The audit's **computed** findings are not in
this field either: a curated file routinely has several at once (a root stray that is also
generically named), and they are already carried by the flags and fields the walk sets
(`root_stray`, `generic_name`, `unconverted`, `hygiene`, `overlap`, `copies[].kind`). Its *Needs a
look* sections are grouped from those, not from a second encoding of them — one home per fact, and
no cardinality to reconcile.

**A computed class is never model-selected**, in either producer. A class the engine can derive is
derived — offering it to a model as a choice reintroduces exactly the drift a closed vocabulary
removes, and makes an audit's counts a function of phrasing.

The vocabulary is **extensible the way flags are**: a consumer ignores a `look` value it does not
know rather than failing, and reads an unknown class as "needs a look, class unrecognised" — never
as no look at all. A missing `look` on an entry flagged `needs_a_look` is an entry written before
the field existed: read it as `flagged`.

## Consumer rules

- Match files to entries by hash first, path second. A file whose hash is absent from `entries` has
  never been understood.
- Never delete an entry; `departed` marks absence.
- When writing, preserve identity fields you didn't re-derive (`first_seen`, `rename_history`,
  `original_name`), write atomically, and bump `generated_at`.
- **A `stem` pairing is sticky; a `stem_near` one is provisional.** Carry the previous pass's
  `convert_candidate` forward and re-confirm it by `id`: for a **confident** (`stem`) pairing, that
  is the whole check — if the content is still in the folder the pairing holds whatever either file
  is now called, which is what stops the first descriptive rename (including the ones this system's
  own medium-depth curation performs) from re-flagging a converted file for ever. A **weak**
  (`stem_near`) pairing is different: the entry is still `unconverted`, so the search **runs again
  every pass** and a real export appearing later upgrades the pairing. And a confident pairing whose
  `id` is **no longer in the folder** falls back to the search too — that is the ordinary re-export
  (the owner edits the document and exports again, so the export's content, and therefore its id,
  changes). Re-confirmation is a shortcut past the search, never a replacement for it. Skipping the search while a
  weak candidate survives is the trap — the owner exports `Report.pdf` in answer to the flag, the
  stale `Report draft.pdf` is still present, and the flag never clears.
- **Identifier handling follows the declared policy.** Full source-supported identifiers are
  retained by default. Any explicit owner restriction applies before writing to every affected
  typed and free-text field, including parties, connection relations, filename components and
  raised items. Do not scrub arbitrary digits. See the crossing rule in
  [`ARCHITECTURE.md`](../../../ARCHITECTURE.md#redaction-is-a-guard-not-an-instruction).
- `AUDIT.md` is derived; regenerate it from the manifest rather than editing it.

## Shared contracts

Two pieces of machinery every producer of this manifest runs: the walk that keeps it true, and the
guards every move it records passes through. They live here, beside the schema they operate on, so
`file-preprocessing` and `folder-curation` cite one home rather than each carrying a copy that
drifts. A skill *describes* these; a deployment's code is what holds them.

### The scan contract

Walk the whole folder and reckon the manifest to what is on disk:

- **Hash every file (SHA-256)** — the entry's id, so identity follows the bytes, not the name.
- **A class policy decides what is hashed.** Which files are hashed in full, which are **count-only**,
  and which are never presented to a model at all is a per-folder policy, not a fixed rule — a
  library that is mostly photographs or medical imaging must not cost a full hash walk every pass. A
  count-only entry carries `hashed: false` (with `synthetic_id: true`) and **is never a duplicate
  candidate**; it is still *counted*, per folder, every pass, so a folder that doubles overnight is
  visible.
- **Confirm each entry's file is still at its recorded path.**
- **Adopt human moves** — the same hash at a new path updates the entry's placement; the human won
  that argument, and nothing is moved back.
- **Spot edited files** (a known path with a new hash) and **strays** (a path and hash the manifest
  has never seen).
- **Flag departed entries** — an entry whose file is no longer anywhere in the folder gains
  `departed` with a last-seen stamp. Entries are **never deleted**; the history is the point, and a
  departed file's return sheds the flag.
- **Bytes that are not local are a named state, not a skip.** A cloud placeholder cannot be hashed:
  report it as `placeholder` and let the caller decide what that means for the pass (a run that must
  act on it refuses to start; a read-only audit records it and carries on). Never treat an
  unhashable file as absent, and never guess its content.

The walk is a **pure function of folder state**: the same folder yields the same manifest, which is
what lets a later pass diff against it and call the difference drift.

### The move guards

Every move, rename, or deletion this manifest records passes all of these, and none of them is a
judgement call:

- **Containment.** Source and target must both stay inside the folder — refuse `..`, absolute paths,
  and any symlinked path component. A path read out of a file is untrusted, even one you wrote.
- **Create destination folders only when a move actually needs them.**
- **Hash-verify after the move.** The moved bytes' hash must equal the entry id; a mismatch is a loud
  error, never a silent success.
- **A two-phase op log**, where the environment supports it: intent → committed, fsync'd inside the
  folder (e.g. `.familyai/preprocess-log.jsonl`), replayed on the next pass so an interrupted move is
  resolved **by content**, and a committed move the manifest never learnt about is repaired from the
  log.
- **An undo entry per executed move, appended *before* the move is attempted**, and sufficient to
  reverse it by content: an entry written only after a successful move cannot describe the move that
  failed halfway, which is the one a person needs to reverse.
