# Tool reference

The tools in [`../tools/`](../tools/) do the exact parts of [`pre-onboarding`](../SKILL.md): standard-library Python
3.9 or later, plus one Swift helper for Apple Vision OCR. Nothing in them names a folder, a person or a project;
each reads the folder's own settings twins ([the settings reference](settings.md)). Run each as
`python3 <tools>/<tool>.py`, where `<tools>` is the skill's `tools/` folder. A section marked provisional in this
file's source describes an interface still landing.

## Common flags

Stated once here; each tool's section below lists only its own.

| Flag | Meaning | Default |
| --- | --- | --- |
| `--root <folder>` | the folder being prepared; required wherever it is taken | none |
| `--settings-dir <dir>` | where `rulebook.json` and `wiki-schema.json` live | `<root>/.familyai` |
| `--work <dir>` | working state outside the folder: logs, caches, batches, queues, bundles, briefs; refused inside the folder | `~/.ai-os-pre-onboarding/<folder name>`, each run of characters other than letters, digits, `.`, `_` and `-` replaced by `-` |
| `--out <path>` | where the tool writes its result; each tool's own default is in its section | per tool |
| `--read-only-root` | refuse any write inside `--root`; with `--out` elsewhere, it proves a tool against a real folder without changing it | off |

| Tool | `--root` | `--settings-dir` | `--work` | `--out` | `--read-only-root` |
| --- | --- | --- | --- | --- | --- |
| `audit.py` | yes | yes | yes | output folder | yes |
| `plan.py` | `light`, `migrate`, `return`, `rmdirs`, `check`, `execute` | as `--root` | no | plan folder, for `light`, `migrate`, `return` | `light`, `migrate`, `return`, `rmdirs` |
| `extract.py` | yes | yes | yes | records folder | yes |
| `vision.py` | yes | yes | yes | records folder | yes |
| `cards.py` | yes | yes | yes | cards folder | yes |
| `refs.py` | yes | yes | yes | no | yes |
| `isolation.py` | no | no | no | `canary`'s result | no |
| `settings.py` | yes | yes | accepted, unused | `check`'s result | yes |
| `wiki.py` | yes | yes | yes | per subcommand | yes |
| `readiness.py` | yes | yes | yes | result file | yes |

`plan.py`'s subcommands with `--root`, `extract.py`, `wiki.py` and `readiness.py` also take `--manifest <file>`
(default `<root>/_Audit/manifest.json`).

**The stale-twin gate.** Every tool that takes `--root` refuses a stale, unpinned or malformed settings twin before
it reads or writes anything, except `settings.py` (`compile` is the remedy, `check` the diagnosis) and
`readiness.py`, which report it ([stale twins](settings.md#stale-twins)).

**Exit codes.** `0`: done, nothing to act on. `1`: the tool ran and reports something to act on (a finding, a
failed row, a problem). `2`: refused, with `error: <why>` on standard error (a stale twin, a bad argument, a guard).
`3`: stopped by an alert (`cards.py work`, `vision.py`).

**Writes.** Every record and result a tool writes goes through `common.Writer`: a temporary file, synced, then
renamed into place, so no reader sees half a file; with `--read-only-root`, a path inside the folder is refused
before anything is written. State files in the work directory are written directly.

**The clock.** `PRE_ONBOARDING_NOW` (seconds since the epoch) freezes the clock for the tests, so their outputs
compare byte for byte; nothing else should set it.

## Before the first run

- **The OCR helper.** Build it once in the tools folder: `swiftc -O page_ocr.swift -o page-ocr` (macOS 13 or later),
  or give its path with `extract.py --ocr-bin`.
- **Local readers** `extract.py` finds on the `PATH` or in the usual install folders: `pdftotext`, `pdfinfo` and
  `pdftoppm` (poppler; needed for PDFs), `tesseract` (the second OCR tier), `textutil` and `sips` (macOS; `.doc`,
  `.rtf`, `.odt` and `.html`, and resizing queued page images), `soffice` (LibreOffice; legacy `.ppt` and `.xls`).
  A missing reader is named in the record it would have read, never skipped silently.
- **The engines**: the `agy` and `codex` command-line tools, each logged in once on this machine.

## `audit.py`

    audit.py --root <folder> [--out <dir>] [--cache <file>] [--dataless fail|read]

The deterministic audit of [`folder-curation` step 1](../../folder-curation/SKILL.md#1-audit-deterministic-never-moves-anything),
with no model call. It writes `manifest.json` (schema `family-ai-preprocess-manifest/2`), `summary.json` and
`AUDIT.md` to `--out` (default `<root>/_Audit`), merging with the manifest already there, so first-seen dates,
rename history and departures are kept; a manifest of another schema there is refused.

- **What it walks.** Everything under the root but, at the top: the rulebook files, `.familyai`, `Outbox`, `Wiki`,
  the wiki folder, the rulebook's `reserved` names, and every `_`-prefixed folder except the migrations folder.
  Dot files and folders are counted as hidden, `.icloud` files as cloud placeholders and symbolic links as links;
  none is followed. An iWork package is one item, hashed by the manifest's package hash rule.
- **What it hashes.** Every item in full, except an image over the rulebook's `image_cap_mb`, which is counted with
  a synthetic id. Hashes are cached in `--cache` (default `<work>/hashcache.json`) by path, size and modification
  time.
- **Cloud files.** A file whose bytes are not on this machine stops the audit (exit 2) with a list, unless
  `--dataless read`, which reads it and so downloads it.

## `plan.py`

The curation rounds of [`folder-curation` steps 3 to 6](../../folder-curation/SKILL.md#3-propose-the-only-model-step),
in the plan format of [`move-plan-schema.md`](../../folder-curation/references/move-plan-schema.md). A plan folder
is `<root>/_Audit/plans/<YYYY-MM-DD>/`; `--out` and `--plan` are read relative to the current directory, not the
root.

| Subcommand | Does |
| --- | --- |
| `light` | proposes a light-depth round |
| `migrate`, `return` | propose staging files for another project, or bringing them back |
| `approve` | records the owner's decision on rows |
| `rmdirs` | adds rows removing the folders the approved moves empty |
| `check` | dry-runs every row under the executor's guards |
| `execute` | carries out the approved rows |
| `prove` | proves the executed moves by a (path, hash) diff of two manifests |

### `light`

    plan.py light --root <folder> --out <plan folder> [--manifest <file>] [--deletes-only]

Writes `<plan folder>/move-plan.csv` with a row, `status` `proposed`, for:

- each root stray: a `move` with `to` left empty and `needs_a_look` asking the owner to choose its folder;
- each file whose name has a space at either end or before its extension: a `rename` dropping the spaces (and a
  hyphen left dangling before the extension), with `needs_a_look` when a file of the new name exists;
- each folder whose name has a space at either end: a folder `rename`, `sweep` `no`, the reason counting the files
  inside;
- each redundant copy outside any pack: a `delete`, `kind` `redundant`, `evidence` the entry's id, the reason naming
  the copy kept.

Files under the migrations folder and redundant copies are not renamed. `--deletes-only` writes only the delete
rows.

### `migrate` and `return`

    plan.py migrate --root <folder> --project <Project> --paths-file <file> --out <plan folder> [--reason <text>]
    plan.py return  --root <folder> --project <Project> --paths-file <file> --out <plan folder> [--reason <text>]

The paths file holds one folder-relative path per line; blank lines and lines starting with `#` are skipped.

- **`migrate`** writes a `move` row per listed path to `<migrations folder>/<Project>/<path>`, in domain
  `Migrations`, `kind` the moved path's copy kind (empty when its entry has one path), `needs_a_look` naming the
  copies that stay behind. A listed path ending in `/` stands for every live path under it, copies included.
- **`return`** writes a `move` row per listed path from `<migrations folder>/<Project>/<path>` back to `<path>`; when
  the round returns everything staged for that project, it adds an `rmdir` row for `<migrations folder>/<Project>/`.

Both also write `review.tsv` beside the plan.

### `review.tsv`

Tab-separated, no header, one line per staged path or missing path, for the owner to read before approving:

| Column | `migrate` | `return` |
| --- | --- | --- |
| 1 | the project, or `MISSING` for a listed path the manifest does not know | `MISSING` |
| 2 | the path | the staged path not found |
| 3 | its copy kind: `canonical`, `redundant`, `working_copy` or `pack`, or empty when its entry has one path | empty |
| 4 | the other copies of the same content, separated by `; `, which stay behind | empty |

Nothing reads `review.tsv` back. What the owner changes in a round is the paths file (and the round is proposed
again), a stray's destination in the plan's `to` column, and their decisions, which `approve` records.

### `approve`

    plan.py approve --plan <move-plan.csv> --rows <rows> [--note <text>] [--decline]

`--rows` is a list such as `1-5,7`, or `all`. Each row named gets `approved` (`approved`, or `declined` with
`--decline`), `approved_at` (the local time), `status` (`pending`, or `skipped` when declined) and the note. A row
left blank is not approved, and `execute` skips it.

### `rmdirs`

    plan.py rmdirs --root <folder> --plan <move-plan.csv> [--approve-note <text>]

Adds an `rmdir` row for each top-most folder that holds nothing but the files the plan's approved `move` rows take
away (and `.DS_Store`), unless it already has one. The rows are `proposed`, or approved at once with
`--approve-note`, for a folder the owner has already agreed to remove.

### `check`

    plan.py check --root <folder> --plan <move-plan.csv> [--manifest <file>]

A dry run of every row, under the executor's own guards: a `delete` is outside any pack, its path is one the
manifest marks `redundant`, a separate canonical copy exists and both hash to `evidence` on disk; a file `move` or
`rename` has its source, hashing to `evidence`; every path stays inside the folder with no symbolic link on it.
Prints a `FAIL` line per failing row and `rows ok <n> failed <n>`; exit 1 on any failure. A destination that
already exists is seen only by `execute`.

### `execute`

    plan.py execute --root <folder> --plan <move-plan.csv> [--apply] [--phase main|deletes] [--bin <dir>]
                    [--manifest <file>]

Without `--apply` it prints what each row would do and changes nothing. With it, rows run in `seq` order:

- **`main`** (the default) runs every approved row but `delete`: `create`; a file or package `move` or `rename`
  (its hash equal to `evidence` before and after, never over an existing path, missing folders created); a folder
  `rename`; an `rmdir`, only of a folder with nothing left in it but `.DS_Store`, moved to the Bin.
- **`deletes`** runs only the approved `delete` rows, and refuses to start unless every other approved row is
  `done` and the manifest (`--manifest`) was written after the last of them. Each row is checked again against that
  manifest and on disk, as `check` does, and the copy is moved to the Bin.

The Bin is `--bin`, or the user's bin (`~/.Trash`); an item whose name is taken there gets ` (<n>)`. Each change is
logged to `<plan folder>/undo.log` as JSON lines: an `intent` line before it and a `done` line with its reverse
after. Each row's `status` becomes `done`, `failed` or `skipped`, with `executed_at` and a `note` (`undo.log seq
<n>`, or the failure). A failed row stops its domain: later rows in it are skipped. A row of any other action, such
as `convert`, fails. Exit 1 when a row failed.

### `prove`

    plan.py prove --plan <move-plan.csv> --before <manifest> --after <manifest> [--allow-departed-under <prefix> ...]

Treats each manifest as the set of (path, content id) pairs over every live path, copies included. The pairs that
disappeared must be exactly the `done` file `move` and `rename` rows' (`from`, `evidence`), and the pairs that
appeared exactly their (`to`, `evidence`); a `done` folder rename accounts for every pair under its old path.
Prints JSON: `gone_unexpected`, `new_unexpected`, `gone_missing`, `new_missing`, `rows_checked` and `ok`; exit 0
only when `ok`. `--allow-departed-under <prefix>`, repeatable, names a path prefix whose departures are expected,
such as `_Migrations/<Project>/` once that project has collected its files; it excuses only pairs that disappeared
under that prefix. `delete` and `rmdir` rows are not proved here: check the deletes against the fresh manifest
([folder-curation step 6](../../folder-curation/SKILL.md#6-verify-by-re-audit)).

## `extract.py`

    extract.py --root <folder> --lane main|apps [--worker <k>/<N>] [--retry-failed] [--manifest <file>]
               [--out <dir>] [--ocr-bin <file>]

The full text of every live, hashed document in the manifest (images over the size cap are not read; staged files
are), every page, with local tools only. Records go to `--out` (default `<root>/_Audit/extract`), one
`<id>.json` per document. An existing record is never rewritten, except a `failed` one with `--retry-failed`.

### Lanes and workers

- **`apps`**: iWork documents, legacy `.ppt`, `.pot`, `.pps` and `.xls`, and packages. One worker.
- **`main`** (the default): everything else, split by `--worker <k>/<N>` (default `0/1`): worker k takes the
  documents whose id's first eight hex digits leave k when divided by N.

Each run writes `<work>/index/extract_<lane><k>.jsonl` as it goes and, when it ends, the done marker
`<work>/state/extract_<lane><k>.done` that `vision.py` waits for. Exit 1 when any record failed.

### Tiers

| Format | How it is read |
| --- | --- |
| PDF | per page: the text layer, unless it is broken (spaces decoded as `)` or `!`); otherwise the page is rendered at 200 dpi and read by Apple Vision (`page-ocr`), then tesseract; a page none reads cleanly is queued for the vision lane |
| image | Apple Vision; fewer than 80 characters read makes it a photo, not a document |
| Pages, Numbers, Keynote | `iwa.py`, reading the package without the apps; the package's preview image, by OCR, when that finds no text |
| `.docx`, `.pptx` (with its notes), `.xlsx` | parsed directly |
| `.doc`, `.rtf`, `.odt`, `.html` | `textutil` |
| legacy `.ppt`, `.xls` | exported to PDF by LibreOffice, then read as a PDF |
| `.txt`, `.md`, `.csv` | decoded as UTF-8, GB 18030 or UTF-16, else Latin-1 |
| zip archive | its list of members |
| anything else | as text when it plainly is text; otherwise `no_reader` |

Apple Vision is asked first for Chinese and English; when that finds fewer than five Chinese characters, it is
asked again for English and French, and the better reading kept. A reading is clean when it has at least 40
characters, mostly letters, digits, spaces and ordinary punctuation, a word of three Latin letters or at least 15
Chinese characters, and (from Vision) a confidence of at least 0.45.

### The record

| Key | What it holds |
| --- | --- |
| `id`, `path`, `class` | the manifest entry's id, current path and class |
| `status` | `ok`, `partial` (a page not read, or an iWork file read from its preview), `blank`, `photo`, `listed` (an archive), `no_reader`, `needs_vision` (pages queued for the vision lane) or `failed` |
| `page_count`, `chars` | pages, and characters of text in all |
| `tiers` | how many pages each tier read |
| `pages` | `[{n, text, tier, ...}]`; `tier` is `text_layer`, `local_ocr` (with `engine` `vision` or `tesseract`, and `conf` from Vision), `pending_vision` (with `queued`, the image's name), `blank`, `none` (with a `note`: the page could not be rendered), `photo` or `listing`, and after the vision lane `vision` or `unread`; `via` names an indirect reader (`iwa`, `preview_image`, `textutil`, `libreoffice`) |
| `extractor`, `extracted_at` | the tool's version and the time |
| `notes` | a local OCR tool that was missing where a page needed it, or an iWork read that failed |
| `error` | on a `failed` record, why |

## `iwa.py` and `page_ocr.swift`

`iwa.py` is a library `extract.py` calls, with no command of its own: it reads the `.iwa` streams of an iWork
package or zipped iWork file (Snappy-compressed protobuf) and walks every message generically, keeping the fields
that are human text, in storage order.

`page_ocr.swift` builds the `page-ocr` helper: `page-ocr [--lang <codes>] <image> ...` prints one JSON line per image
(`file`, `text`, `confidence`, `lines`, and `error` when it failed); `page-ocr --stdin` reads one image path per
line, where `LANG=<codes>|<path>` sets the languages for that image. `extract.py` keeps one `--stdin` process
running and restarts it if it stalls; its first run compiles Vision's model, which takes about a minute.

## `vision.py`

<!-- provisional: #92 -->

    vision.py --root <folder> --model <vision model> [--worker <k>/<N>] [--out <dir>] [--lanes <markers>]

The vision lane: a model reads the page images local OCR could not read cleanly. It drains
`<work>/vision_queue/`, taking the images of records still `needs_vision` whose id falls to worker k of N, six to a
call. Each call copies its images, as `p1.png` to `p6.png`, into a fresh, otherwise empty folder, and `agy` reads
them there in its sandboxed plan mode; the reply must name exactly the images sent. A transcription replaces the
page's text (tier `vision`, engine `agy`, the local text kept as `local_text`; an empty one makes the page `blank`),
and the record is written back to `--out` (default `<root>/_Audit/extract`); once none of its pages is pending, its
status becomes `ok`, or `partial` if a page was left unread. A page whose batch fails three times is marked
`unread`, its local text kept. Tries are kept in
`<work>/state/vision_tries_<k>.json`.

It sleeps through quota, and stops (exit 3) while `<work>/state/ALERT` exists. It exits once every done marker
named in `--lanes` (default `extract_main0,extract_apps0`; name every extraction worker's) exists and its share of
the queue has stayed empty for two looks a minute apart, writing `<work>/state/vision<k>.done`.

## `engines.py`

<!-- provisional: #92 -->
<!-- provisional: #91 -->

A library: the adapters every model call goes through, `Agy` (Gemini through the `agy` command-line tool) and
`Codex` (ChatGPT through `codex exec`). The rule it holds is the skill's
[engine isolation](../SKILL.md#engine-isolation); the exact flags are in the file, set by the isolation spike.

- **Each call** runs in the working directory the caller gives (a fresh, empty one from `engines.fresh_dir`), with
  the prompt on standard input, in its own process group, killed on timeout (900 seconds for `agy`, 1,500 for
  `codex`). `agy` runs sandboxed in plan mode, with the environment minus `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `GEMINI_API_KEY` and `GOOGLE_API_KEY`; `codex` runs read-only and ephemeral, ignoring user configuration and
  rules, with every tool feature it can disable disabled, and an environment of only `LANG`, `TMPDIR`, `USER`,
  `LOGNAME`, `HOME` and `PATH`. An output schema, when given, is passed to the engine.
- **Outcomes.** `QuotaError` for quota text (quota, 429, exhausted, rate limit, usage limit, too many requests),
  whatever the exit code, with `reset_seconds` read from "Resets in 2h13m5s" or "try again at 5:12 PM" where the
  message says; `DegenerateError` for an empty answer; `ToolUseError` when `codex` reports a tool item, the reply
  discarded; `EngineError` for anything else, such as an `agy` result that is not a success.
- **A per-project state folder** (`state_home`, the engine's `HOME` or `CODEX_HOME`) is optional; no caller sets
  one yet. When set, it is scanned before and after every call, and a regular file named like a credential
  (`auth.json`, or a name containing oauth, token, creds or credential) fails the call.

## `isolation.py`

<!-- provisional: #92 -->

    isolation.py scan   --terms <file> --path <file or folder> [--path ...]
    isolation.py canary --terms <file> --engine agy|codex [--model <id>] --out <result.json>

Keeps other projects out of model-facing context. The terms file's format is in
[the card contract](cards.md#the-terms-file).

- **`scan`** reads every `.md`, `.json`, `.py`, `.txt`, `.sh`, `.swift`, `.csv` and `.jsonl` file under each path
  and prints `{"files_with_terms": {file: count}, "terms": n}`; exit 1 when any file holds a term. Scan every file
  a model is shown: the tools folder (its prompts and templates), the folder's `.familyai/` (the owner context the
  card instructions are filled from) and the wiki briefs.
- **`canary`** asks the engine, in a fresh empty folder, to list every personal name, family name, company,
  property, street or address in its context other than the message. It writes `{engine, checked_at, terms, reply,
  usage, hits, pass}` (or `error`) to `--out` and prints it without the reply; `pass` needs a reply with no term in
  it. Exit 0 on a pass. The result is the record that the gate ran; no tool reads it.

## `cards.py`

<!-- provisional: #92 -->

    cards.py build --root <folder> [--extract <dir>] [--out <dir>]
    cards.py work  --root <folder> --engine agy|codex --model <id> (--terms <file> | --no-isolation-terms)
                   [--worker <k>/<N>] [--redo <ids file>] [--effort <level>] [--light-model <id>] [budgets]

One card per live document. What a card holds, how it is written and joined, and how it is checked:
[the card contract](cards.md).

| Flag | Meaning | Default |
| --- | --- | --- |
| `--extract` | extract records | `<root>/_Audit/extract` |
| `--out` | cards | `<root>/_Audit/cards` |
| `--engine` | `agy` or `codex` | `agy` |
| `--model` | the engine's model id (with `agy`, the effort is part of the id); give one for `agy` | none |
| `--effort` | `codex` reasoning effort | `medium` |
| `--light-model` | `codex` model for section notes, run at low effort | the main engine |
| `--terms`, `--no-isolation-terms` | the isolation list, or the logged statement that none is needed; `work` needs one of them | none |
| `--worker` | take every Nth batch file, from the kth | `0/1` |
| `--redo` | a file of ids to card again, one per line | none |
| `--small-chars`, `--batch-chars`, `--batch-items`, `--textless-batch`, `--section-chars`, `--single-max` | the batch budgets, in characters and items | 60,000; 180,000; 30; 60; 400,000; 600,000 |
| `--section-tokens`, `--single-tokens` | budgets in estimated tokens instead (for `codex`, 110,000 and 150,000) | unset |

Batches go in `<work>/batches/`, section notes in `<work>/sections/`; a worker writes `<work>/state/cards<k>.done`
(or `redo<k>.done`) when it finishes, and stops (exit 3) while `<work>/state/ALERT` exists.

## `refs.py`

<!-- provisional: #92 -->

    refs.py --root <folder> [--apply] [--cards <dir>] [--extract <dir>]

Restores truncated reference numbers on cards from each card's own source, with no model call
([the card contract](cards.md#repair-from-the-cards-own-source)). Without `--apply` it only counts; with it, it
writes the restored cards and `<work>/state/redo_refs.txt`, the ids for `cards.py work --redo`. It refuses (exit 2)
under any identifier policy but `stated`. `--cards` and `--extract` default to `<root>/_Audit/cards` and
`<root>/_Audit/extract`.

## `settings.py`

    settings.py compile --root <folder>
    settings.py check   --root <folder> [--out <file>]

`compile` writes `wiki-schema.json` from the Schema page's tables; `check` reports both twins' state and the
rulebook's facts, exit 1 on any finding. Formats, rules and findings: [the settings reference](settings.md).

## `wiki.py`

The tools for building and checking the wiki, in the stages of
[the core wiki rule](../../wiki-maintenance/SKILL.md#the-core-wiki-rule) as
[`wiki-onboarding`](../../wiki-onboarding/SKILL.md) applies them. Every subcommand takes `--manifest`; page paths
are relative to the wiki folder, source paths to the folder.

| Subcommand | Does |
| --- | --- |
| `profile` | per-folder statistics for the librarian's structure proposal |
| `bundles` | per-section evidence for the drafting agents |
| `brief` | the drafting brief for a set of pages |
| `chart` | a Mermaid chart and its data table, from cited rows |
| `check` | the deterministic wiki checks |
| `rationale` | assembles `_Audit/wiki-rationale.md` |
| `review-prompts`, `accept` | acceptance prompts, and the verdicts recorded |
| `move` | moves pages and rewrites every link to and from them |
| `drift` | page lines citing a path that has left or is leaving |

<!-- provisional: #93 -->

`profile`, `brief` and `drift`, `bundles --reuse` and the refusal of stale bundles arrive with the wiki tools
(issue #93); until then `bundles` needs `--out` and `move` refuses less. `rationale`, `review-prompts` and
`accept` arrive with the wiki checker (issue #94).

### `profile`

<!-- provisional: #93 -->

    wiki.py profile --root <folder> [--depth 2] [--parties 5] [--cards <dir>] [--extract <dir>] [--out <file>]

For the readers interview and the librarian: per top-level folder and subfolder down to `--depth`, its live
documents (by current path), the copies held there of documents living elsewhere (and the folders those live in),
and from the documents' cards their categories, the span of their `doc_date`s and their top `--parties` parties,
aliases folded to the rulebook's canonical names. Migrating and departed entries are counted, not profiled. Prints
JSON (`folder`, `depth`, `documents`, `carded`, `copies`, `migrating`, `departed`, `uncarded`, `categories`, and
`folders`, one object each), also to `--out` where `--read-only-root` allows. For example, a folder that only
mirrors others:

    {"folder": "05 Archive", "documents": 0, "copies": 4, "copies_of": {"04 Study": 3, "06 Work": 1},
     "carded": 0, "categories": {}, "dated": 0, "earliest": null, "latest": null, "parties": []}

### `bundles`

<!-- provisional: #93 -->

    wiki.py bundles --root <folder> [--out <dir>] [--reuse] [--text-cap 12000] [--cards <dir>] [--extract <dir>]

Routes every live manifest entry outside the migrations folder by the compiled routing (its longest matching
prefix; a note row routes nothing) and writes one `bundle_<NN>.jsonl` per section to `--out` (default
`<work>/bundles`; refused inside the folder). Each line is a document: its short id, path, other copies, pages,
extract status, and from its card `title`, `doc_type`, `party`, `parties`, `doc_date`, `category`, `language` and
`sensitive`; then `summary` and `key_facts`, and in an `active` section the full text, capped at `--text-cap`
characters. In any other section, reading, photos and other bulk material is listed `compact`, without summary or
text. A card with no extract record is refused.

`bundles.json` records `manifest_sha256`, `routing_sha256` (the routing rows and section kinds), `text_cap`, the
counts per section, the files, and the `unrouted` and `uncarded` paths; either list non-empty exits 1. A rebuild
removes section files it no longer writes.

**Staleness.** `brief`, and `bundles --reuse` (which reuses fresh bundles without rebuilding), refuse (exit 2)
bundles whose recorded `manifest_sha256` differs from the current manifest's, whose `routing_sha256` differs from
the current Schema's, or whose files are missing, and name the command that rebuilds them. Every curation round
ends in a re-audit that rewrites the manifest, so bundles built before it are refused rather than read.

### `brief`

<!-- provisional: #93 -->

    wiki.py brief --root <folder> --page <page> [--page <page> ...] [--bundles <dir>] [--out <file>]

Renders `templates/page-brief.md` for a set of pages, sorted, so the order given does not matter: each page's
professional, deliverable and tone ([a page's professional](settings.md#a-pages-professional)) and its section's
contract (reader, questions, fields; a `fixed` section takes the method's shape, and any other section without a
contract is refused); the routing into its section and its bundle; the owner context from `rulebook.json` (folder
description, people with aliases, identifier policy, boundaries); the page map; each page's rationale block with
what the Schema fixes filled in; the JSON a drafting agent returns (each page's full text and rationale block, its
check result and its flags for the owner); and the checker command every drafting agent runs. The page map is every
page under the wiki folder, every page in the Schema's Page professionals table, each Layout section's folder note
(`<NN Name>/<NN Name>.md`) and the pages briefed, each marked `exists` or `planned`. It refuses stale bundles, and
writes `--out` only outside the folder. The same inputs render the same bytes.

### The stage templates

<!-- provisional: #93 -->

In `tools/templates/`, one per stage, each opening with a comment naming its stage and who fills it; fields are in
braces and doubled braces are literal, so each fills as a Python format string, and each asks for JSON back.

| Template | Stage and pen | Fields |
| --- | --- | --- |
| `readers-interview.md` | readers; the owner answers | `folder_name`, `owner_context`, `profile_summary` |
| `structure-brief.md` | sections, routing and each page's professional; the librarian proposes | `folder_name`, `owner_context`, `readers`, `profile`, `current_schema` |
| `contract-brief.md` | a section's contract; its professional drafts | `section`, `professional`, `owner_context`, `readers`, `section_rows`, `routing`, `bundle` |
| `page-brief.md` | the pages; their professional writes | rendered whole by `brief` |
| `review-owner.md` | acceptance in the owner's lens; a model that did not write the page | `page`, `page_text`, `author_model`, `reviewer_model`, `reader`, `questions` |
| `review-professional.md` | acceptance in the professional's lens; the same | `page`, `page_text`, `author_model`, `reviewer_model`, `professional`, `contract`, `root`, `bundle`, `sample` |

[`card-instructions.md`](../tools/templates/card-instructions.md), the card engine's instructions, sits beside
them ([the card contract](cards.md#what-the-engine-is-given)).

### `check`

    wiki.py check --root <folder> [--out <file>]

Reads every page under the wiki folder (dot folders skipped) and prints JSON, also to `--out`; exit 1 when
`problems` is not zero.

| Key | What it reports |
| --- | --- |
| `wiki`, `pages` | the wiki folder and its page count |
| `frontmatter_conforming`, `frontmatter_bad` | pages with `provenance`, `last-updated` and `status`, as `n/total`, and the pages without |
| `superseded_pages` | pages whose `status` is `superseded` |
| `dead_source_paths` | `[page, path]` for each `sources:` entry that does not exist, and each backticked file path in a page body whose first segment is a top-level name of the folder and does not exist (the Log is not read for these) |
| `backticked_paths_unchecked` | backticked file paths whose first segment is no top-level name, counted |
| `dead_page_links` | `[page, link]` for each relative link to a `.md` file that does not resolve |
| `em_dash_lines`, `em_dash_where` | lines holding an em dash outside code spans, and the first ten `[page, line]` |
| `chart_blocks`, `charts_without_data_table` | chart pairing, below under [`chart`](#chart) |
| `deadlines` | `[date, page]` from every page's `deadlines:` frontmatter |
| `documents_in_scope`, `documents_not_covered`, `not_covered_sample` | coverage: each live document outside the migrations folder must be named by its path anywhere in the wiki, or have a folder above it named in backticks; the first 20 not covered |
| `rationale` | `{blocks, pages_without_block}` from `_Audit/wiki-rationale.md`'s `### <page>` headings, or `not recorded` |
| `acceptance` | `recorded` when `_Audit/wiki-acceptance.json` exists, otherwise `not recorded` |
| `problems` | bad frontmatter, dead sources, dead links, em dash lines, documents not covered and unpaired charts, added up |

<!-- provisional: #94 -->

The wiki checker (issue #94) extends it so that every section reports a count, zero included, or a named
not-verified state: links must also point only at pages on the page map; coverage counts a document named by its
path or counted under its own parent folder in backticks; chart blocks must be renderable, with their data table
and sources beside them; each page must have one rationale block naming that page's professional; and acceptance
is reported as `accepted`, `not recorded` or `refused`, never folded into a pass. Until then, a page without a
rationale block is listed but not counted as a problem.

### `rationale`

<!-- provisional: #94 -->

Assembles the drafters' returned blocks into `_Audit/wiki-rationale.md` in the fixed five-line format
([the rationale block](../../wiki-maintenance/SKILL.md#the-rationale-block)). Its arguments are not in code yet.

### `review-prompts` and `accept`

<!-- provisional: #94 -->

`review-prompts` renders the acceptance prompts: the owner's lens (a set of the reader's real questions) and the
professional's (the contract, a deterministic sample of facts to check against the cards, the scope). `accept`
records the verdicts in `_Audit/wiki-acceptance.json` with the models that wrote and reviewed the page, and refuses
a verdict whose reviewer is its author. Their arguments are not in code yet.

### `_Audit/wiki-acceptance.json`

<!-- provisional: #94 -->

What is fixed today:

- **Its path**, beside the audit pair, and what it records: each page's verdict in the owner's lens and in its
  professional's, the model that wrote the page and the model that reviewed it, and each finding with the response
  to it ([wiki-onboarding step 6](../../wiki-onboarding/SKILL.md#6-reader-acceptance-the-owners-lens-and-the-professionals)).
  A verdict whose reviewer is its author is refused.
- **What `check` reports now**: `acceptance: "recorded"` when the file exists, `"not recorded"` when it does not.
- **The reviewers' replies**, whose shape the review templates fix: `{"page", "lens", "author", "reviewer",
  "verdict", "findings"}`, with `lens` `owner` or `professional`, `verdict` `accept` or `revise`, and each finding
  `{"where", "finding"}`; the professional's reply also carries `facts_checked`, each `{"fact", "source",
  "matches"}`.

**Gap (#94).** The file's own layout is not in code yet: its top-level keys, how verdicts are grouped by page and
lens, how the response to a finding is recorded, and how `accepted`, `not recorded` and `refused` are derived from
it. Fill this section in when the checker lands.

### `move`

<!-- provisional: #93 -->

    wiki.py move --root <folder> --map <file.json>

Moves pages, `{"20 Finance/Tax.md": "25 Tax & Duty/Tax & returns.md"}`, and rewrites every relative link to or from
a moved page, percent-encoded with `/` and `&` literal as `productivity:portable-markdown` sets out
(`../25%20Tax%20&%20Duty/Tax%20&%20returns.md`); a link neither end of which moved is left as written. It renames
the moved pages' rationale headings, removes the folders it empties, and prints JSON: `moved`, `pages_rewritten`,
`links_rewritten`, `folders_removed`, `rationale_blocks_renamed`, `schema_rows_to_update` (each moved page the
Schema's Page professionals table still names: edit the Schema, then compile) and `dead_links` left anywhere in the
wiki; either of the last two exits 1. It refuses, before changing anything, a missing page, an existing or shared
destination, a path outside the wiki and the Schema page itself.

### `drift`

<!-- provisional: #93 -->

    wiki.py drift --root <folder> [--out <file>]

Lists `[page, line, path]` for every `sources:` entry and every backticked path in a page body (fenced blocks
skipped) that cites a departed path (one a departed entry held and nothing live holds) or a migrating one (staged
under the migrations folder, or the path it was staged from). The Log is history and is not read. Every count is
reported, zero included, and any citation exits 1. After `03 Home/Lease notes .txt` leaves a folder and a re-audit
marks it departed:

    {"wiki": "Alex Personal Wiki", "pages_read": 11, "departed_paths": 1, "migrating_paths": 2,
     "citing_departed": 1, "citing_migrating": 0, "pages_citing": 1,
     "departed": [["30 Home/30 Home.md", 31, "03 Home/Lease notes .txt"]], "migrating": []}

### `chart`

    wiki.py chart --root <folder> --kind bar|line|pie|gantt|timeline --data <rows.csv|rows.json> --title <text>
                  [--out <file.md>]

Prints a fenced Mermaid block, a blank line, then its data table: the same rows, each with its source in backticks.
Both go into the page together, so the page cites the data its chart is drawn from; the same input always gives
the same bytes. Chart pairing, in `wiki.py check`: it counts every `xychart-beta`, `pie`, `gantt` and `timeline`
block (`chart_blocks`) and names each one whose next non-blank line does not start that table, with a backticked
source on every row (`charts_without_data_table`, page and line; each is a problem). Only a block opened at the
outermost level with the info string `mermaid` counts; one quoted inside another fenced block or an indented code
block is an example, not a chart. The kinds offered are those the render probe,
[`../tests/probe/render-probe.md`](../tests/probe/render-probe.md), shows drawing in the apps the wiki is read in.

The data is a CSV file with a header row, or a JSON array of objects (UTF-8, a byte order mark allowed). Rows keep
their order; every row has the same columns, and no others.

| Kind | Mermaid | Columns |
| --- | --- | --- |
| `bar` | `xychart-beta`, one bar series | `label` or `period`, `value`, `unit`, `source` |
| `line` | `xychart-beta`, one line series | `period`, `value`, `unit`, `source` |
| `pie` | `pie` | `label`, `value`, `unit`, `source` |
| `gantt` | `gantt` | `label`, `start`, `end`, `source`; optional `section` |
| `timeline` | `timeline` | `date`, `label`, `source` |

Each rule is enforced; a breach exits 2 naming the row as its file shows it: `line N` of a CSV file (blank lines
counted, the header on line 1) or `row N` of a JSON array (from 1).

- Every row has a `source`: the folder-relative path of the file or folder under the root its figures come from.
  It must exist, resolve inside the root (a symbolic link out of it is refused) and lie outside the folder's reserved
  names (the wiki, `_Audit`, `.familyai`, the inbox, the migrations folder, the rulebook files and any the rulebook
  adds): they hold the system's own files, or files not yet filed or leaving, never a document to cite.
- A bar, line or pie series has at least three points (fewer figures belong in a sentence), none repeating a
  label or period.
- One unit or currency on every row. It labels the y-axis of a bar or line, and a pie's title must name it as a
  word (`GBP` is not named by `GBPX`). A line's x-axis is its periods.
- Dates are `YYYY-MM-DD`: `start`, `end` and `date`, and any date inside a label, period, section, unit or title,
  whether written in figures (`1/2/24`, `01.02.2024`, `2024/03/01`) or with a month name (`2 Mar 2024`,
  `March 2, 2024`). A month and year alone (`March 2024`) is a period, not a date, and figures that cannot be a day
  and a month (`v1.2.34`) are not a date. A gantt row may not end before it starts.
- Values are written exactly as given, never rounded, reformatted or reordered, so each is a plain decimal
  (`-?digits[.digits]`, no separators, symbols or exponent). A JSON number is read as its literal text: `1450.50`
  stays `1450.50`. A pie value is positive.
- No text holds what the chart or table cannot carry: `"`, a backtick, `|`, `#`, `;`, a control character, a
  space at either end, or `%%` at the start (a Mermaid comment); nor `:` in a gantt or timeline label or section.
  A gantt label or section may not start with a gantt keyword (`title`, `section`, `dateFormat`, `axisFormat`,
  `tickInterval`, `excludes`, `includes`, `todayMarker`, `click`, `weekday`, `topAxis`; case matters), which
  Mermaid would read as that statement rather than a task.

The rest is fixed: a bar or line y-axis runs from 0 to the largest value when none is negative (otherwise Mermaid
scales it); a gantt writes a `section` line wherever the section changes from the row before; timeline rows
sharing the date of the row before share its line. For example, `rows.csv`:

    label,value,unit,source
    Rent,1450,GBP,02 Finance/Budget.xlsx
    Utilities,150,GBP,02 Finance/Budget.xlsx
    Savings,400,GBP,02 Finance/Budget.xlsx

rendered with `--kind pie --title "Planned monthly spending (GBP)"`:

    ```mermaid
    pie title Planned monthly spending (GBP)
        "Rent" : 1450
        "Utilities" : 150
        "Savings" : 400
    ```

    | Label | Value (GBP) | Source |
    | --- | ---: | --- |
    | Rent | 1450 | `02 Finance/Budget.xlsx` |
    | Utilities | 150 | `02 Finance/Budget.xlsx` |
    | Savings | 400 | `02 Finance/Budget.xlsx` |

## `readiness.py`

    readiness.py --root <folder> [--terms <file>] [--manifest <file>] [--out <file>]

The [hand-off contract](../SKILL.md#the-hand-off-contract), checked, read-only on the folder: it reads the settings
twins without trusting them, so a stale or unpinned twin is a finding rather than a refusal. It prints JSON, also to
`--out` (where `--read-only-root` allows):

| Key | What it reports |
| --- | --- |
| `manifest` | `generated_at`; `live_entries`, `departed_entries`, `migrating`, `root_strays`, `redundant_copies`, `hygiene`, `unconverted_iwork`; `items_on_disk` from `summary.json`, or not verified without it |
| `records` | `missing_extracts`, `missing_cards` (over every live entry), `bad_category`, `extract_paths_stale` (records whose path differs from the manifest's), `contamination` (not verified without `--terms`) |
| `wiki` | the result of `wiki.py check` |
| `rulebook` | `copies_identical` (`CLAUDE.md` and `AGENTS.md`) and `names_wiki_folder`, or a finding when either file is missing |
| `scratch` | `left_in_audit`: folders in `_Audit/` whose names start `_deploy` or `_wikibuild` |
| `handoff_contract` | each `ok` or `finding: <what>`: `wiki_folder_named_after_folder`; `fixed_pages` (`00 Index`, `01 Deadlines`, `90 Schema`, `91 Log`, each as `<NN Name>/<NN Name>.md`); `derived_pages_hold_nothing_hand_written` (`01 Deadlines` has only its roll-up headings, and no hand-kept `Every year` table while no page carries `recurring:`; not verified without the page); `rulebook_reserves_rulebook_filenames` (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`); `new_files_routed_within_folder` (no rulebook line routes new files to the migrations folder); `settings_rulebook_json` and `settings_wiki_schema_json` (present and fresh) |
| `summary` | `handoff_findings`, `wiki_problems`, `records_missing` |

It exits 1 when a hand-off contract item is a finding, the wiki check has problems, or a record is missing.

<!-- provisional: #97 -->

The hand-off check (issue #97) makes every item a count or a named not-verified state, and a failure of the whole:
no contamination, extract paths agreeing with the manifest, the rulebook copies identical and naming the wiki
folder, no scratch folders left in `_Audit/`, and the wiki check including acceptance. Today `bad_category`,
`extract_paths_stale`, `contamination`, the `rulebook` pair and `scratch` are reported but do not change the exit
code, so read them in the report.

## `common.py`

The helpers every tool shares: settings loading and the stale-twin gate, `Writer`, `reserved_names` (every
top-level name a rulebook must reserve), `pack_matcher`, `page_voice` (the one reading of
[a page's professional](settings.md#a-pages-professional)), JSON parsing of model replies, the token estimate and
`sha256_package`. `sha256_package` is the manifest's package hash rule
([`manifest-schema.md`](../../file-preprocessing/references/manifest-schema.md#added-in-2)), which the audit, the
plan executor and any deployment reading the manifest must compute alike.

## Working files

In the work directory, never in the folder:

| Path | Written by | What |
| --- | --- | --- |
| `logs/<tool>.log` | every tool that logs | a line per step, also on standard error |
| `hashcache.json` | `audit.py` | hashes by path, size and modification time |
| `index/extract_<lane><k>.jsonl` | `extract.py` | a line per record written |
| `vision_queue/<id>_<page>.png` | `extract.py`, drained by `vision.py` | page images for the vision lane |
| `batches/<bucket>_<seq>.json` | `cards.py build` | the card batches |
| `sections/` | `cards.py work` | cached section notes of long documents |
| `bundles/` | `wiki.py bundles` | the section bundles and `bundles.json` |
| `state/extract_<lane><k>.done`, `state/vision<k>.done`, `state/cards<k>.done`, `state/redo<k>.done` | each worker | done markers |
| `state/vision_tries_<k>.json` | `vision.py` | failed tries per image |
| `state/card_err_<id>.txt` | `cards.py work` | why a document could not be carded |
| `state/redo_done_<k>.txt` | `cards.py work --redo` | ids re-carded so far |
| `state/redo_refs.txt` | `refs.py --apply` | ids to re-card |
| `state/ALERT` | `cards.py work` | a contamination alert; every worker stops while it exists |
