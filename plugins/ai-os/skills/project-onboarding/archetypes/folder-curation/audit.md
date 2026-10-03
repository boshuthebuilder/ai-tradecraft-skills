# audit — the deterministic pass (a specification, not a prompt)

**This pass makes no model call and takes no placeholders.** It is a hashing walk plus a pure render,
so it sits entirely below the determinism boundary: the same folder state yields the same
`_Audit/manifest.json` and the same `_Audit/AUDIT.md`, byte for byte. The file is here because the
archetype's other job has a template and a reader will look for this one's; what it specifies is code
the deployment writes, not text a model reads.

The walk itself is the manifest reference's **scan contract**
(`plugins/ai-os/skills/file-preprocessing/references/manifest-schema.md`) — hash under the class
policy, confirm recorded paths, adopt human moves, spot edited files and strays, flag departed
entries. The manifest it maintains is `family-ai-preprocess-manifest/2`. The method behind every
computed field is the `folder-curation` skill; this file states what a conforming `audit` job must
produce, and nothing about *why*.

## What the pass computes

Per entry, on top of the scan contract's own fields:

- **A type class** from the project's class policy (`classes:` in `jobs.yaml`), which decides whether
  the entry is hashed in full or counted only.
- **A package is one item.** A document stored as a folder of member files (an iWork `.pages`,
  `.numbers` or `.key` package) is one entry, never walked into: its id follows the manifest
  reference's package hash rule, and the entry carries `package`.
- **Files staged for another project.** Every live path under the migrations folder's `<Project>/`
  (`_Migrations/<Project>/` by default) sets the entry's `migrating` flag, with that project in
  `migration_target`. The staged file stays counted until the other project collects it; the entry is
  then `departed`, or, where a copy stays behind, loses the flag.
- **Duplicate groups** by content hash across the whole tree. Copies of the same bytes share one
  entry, so a group is one entry whose `copies` list holds every live path, each tagged `canonical`,
  `redundant`, `working_copy` or `pack`. A count-only entry is never a duplicate candidate.
- **Overlapping homes** — one subject with more than one folder its documents land in, detected by
  name and by duplicate groups spanning two trees. Recorded as a pair id on every participating
  entry (`overlap`), with the file count on each side.
- **Generic names** — a stem that is a device or scanner default (`generic_name`), counted per folder.
- **Unconverted formats** — an `iwork` or other proprietary file for which no export could be
  confidently matched (`unconverted`), counted per class and per folder, never per run. The match is
  on the **normalised stem across the whole folder**, not the same-folder sibling: exports live one
  folder over and under modified names, and a false `unconverted` becomes a `convert` row that makes
  a second export. Candidates are ranked **same folder, then nearest common ancestor, then closest
  modification time**, and an export is **claimed once** — one export cannot convert three files, or
  a single recent export clears the flag on every year of an archive that shares its stem. Match
  strength then decides the flag: an identical normalised stem clears it (the file is converted; the
  pairing is still recorded in `convert_candidate`), a stem that agrees only after a modifier is
  folded out leaves it set *with* the candidate named, and no match at all leaves it set with no
  candidate. A **confident** pairing is carried forward and re-confirmed by the export's **content
  id** rather than its name — this pass recomputes from disk every run, so a pairing held by name
  dies at the first rename and the file is re-flagged for ever. That re-confirmation is a shortcut
  past the search, not a replacement: when the recorded id is no longer in the folder — the ordinary
  re-export gives the export new bytes — the search runs again. A **weak** pairing is provisional
  either way: re-run the search every pass, so the export the owner makes in answer to the flag is
  found. The comparison stays on names and timestamps: a content-level match would mean reading
  documents, which this pass never does (it hashes and names; the class policy's reading is the later
  ingest's), and it makes no model call.
- **Hygiene defects** (`hygiene`, kind in `look_reason`) — leading/trailing whitespace in a name,
  hidden system files, names differing only by case, path components over the filesystem's byte limit.
- **Root strays** (`root_stray`) — anything at the folder root that is not a declared reserved name.
- **Live vs closed** per top-level folder, from the newest modification and the density of recent
  changes.
- **Drift since the last pass** (from the second run on): added, removed, moved (same hash at a new
  path — adopted, not flagged), edited (same path, new hash), new duplicate groups, new root strays,
  and new files landing in an overlapping home.

## What the pass renders

`AUDIT.md` is a pure function of the manifest — **stamped from the manifest's own `generated_at`,
never from the clock**, so re-rendering an unchanged manifest is a no-op. Sections, in this order:

1. Header (folder, schema, `generated_at`, entry count)
2. **Summary by class** — per class: files, bytes, hashed vs count-only
3. **Root strays**
4. **Overlapping homes** — each pair with the count on each side
5. **Duplicate groups** — split by kind, with a per-kind count and per-kind totals
6. **Generic names** — per folder
7. **Unconverted formats** — per class and folder
8. **Hygiene**
9. **Live vs closed** — per top-level folder
10. **Drift since last pass** — omitted only on the first pass, which says so
11. **Migrating out**: each path staged for another project, grouped by its `migration_target`, with
    the count; they leave the folder once that project collects them
12. **Needs a look**: findings a person must judge, grouped by **class** and each carrying its
    reason. Every class this pass emits is *computed* — read from the flags and fields the walk set,
    never inferred from a phrase — so the counts do not depend on wording, and a file with several
    defects appears under each. One concern is one finding: a condition that holds for forty files
    is one entry with forty pieces of evidence, not forty entries.

**Every section prints its count, including zero.** A sweep that saw nothing and a healthy folder
must never read alike; a section that renders nothing at all is indistinguishable from a section that
never ran.

## Fail loud

- **An unreadable subtree is `error`, named with its path**, and the pass reports partial counts as
  partial — never a clean total over a tree it could not finish walking.
- **A cloud placeholder is `placeholder`**: refuse to hash it, report it, and carry on. This job is
  read-only, so a placeholder is a finding rather than the refusal-to-start it is in
  `file-preprocessing`.
- **A walk that cannot finish inside its budget reports `partial`** with the subtree it stopped in.
  A truncated walk that reports a clean count is the failure this whole archetype exists to make
  visible.
