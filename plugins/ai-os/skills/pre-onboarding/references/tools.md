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
| `isolation.py` | no | no | no | `scan`'s and `canary`'s result | no |
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
- **Packs.** Every copy in a pack is marked `pack`, even one beside its canonical copy, so no plan deletes it. A
  pack is a folder the rulebook lists in `packs` or one whose path matches its `pack_keywords` (by default
  `application`, `passport`, `renew`, `visa`, `submission` and `evidence`, ignoring case). A listed pack that is not
  an existing folder, named exactly (each part compared with its folder's listing, case included, in Unicode NFC),
  refuses the run, here and in `plan.py`: it would match nothing and leave its copies deletable.
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
| `prove` | proves the executed rows by a (path, hash) diff of two manifests |

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
- **`return`** writes a `move` row per listed path from `<migrations folder>/<Project>/<path>` back to `<path>`. It
  adds no `rmdir` row: once the return rows are approved, `rmdirs` proposes the folder they empty.

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

    plan.py approve --plan <move-plan.csv> --rows <rows> [--note <text>] [--decline | --defer]

`--rows` is a list such as `1-5,7`, or `all`. Each row named gets `approved` (`approved`; `declined` with
`--decline`; `deferred`, not this round, with `--defer`), `approved_at` (the local time), `status` (`pending` when
approved, otherwise `skipped`) and the note. A row left blank is not approved, and `execute` skips it.

### `rmdirs`

    plan.py rmdirs --root <folder> --plan <move-plan.csv> [--approve-note <text>]

Adds an `rmdir` row for each top-most folder that holds nothing but the files the plan's approved `move` rows take
away (and `.DS_Store`), unless it already has one. The rows are `proposed`, or approved at once with
`--approve-note`, for a folder the owner has already agreed to remove.

### `check`

    plan.py check --root <folder> --plan <move-plan.csv> [--manifest <file>]

A dry run of every row, `delete` rows included (checked against the manifest), under the executor's own guards:
the rules [the plan schema](../../folder-curation/references/move-plan-schema.md) encodes and
[folder-curation step 5](../../folder-curation/SKILL.md#5-execute-deterministic-guards-not-judgement) sets out.
Prints a `FAIL` line per failing row and `rows ok <n> failed <n>`; exit 1 on any failure. A destination that
already exists is seen only by `execute`.

### `execute`

    plan.py execute --root <folder> --plan <move-plan.csv> [--apply] [--phase main|deletes] [--bin <dir>]
                    [--manifest <file>]

Without `--apply` it prints what each row would do and changes nothing. With it, rows run in `seq` order:

- **`main`** (the default) runs every approved row but `delete`: `create`, a file or package `move` or `rename`
  (missing folders created), a folder `rename`, and `rmdir`.
- **`deletes`** runs only the approved `delete` rows, against the manifest `--manifest` names.

Each row runs under the guards of [folder-curation step 5](../../folder-curation/SKILL.md#5-execute-deterministic-guards-not-judgement)
and [the plan schema](../../folder-curation/references/move-plan-schema.md), the delete phase's included
([`rmdir` and the Bin](../../folder-curation/references/move-plan-schema.md#rmdir-and-the-bin)).

The Bin is `--bin`, or the user's bin (`~/.Trash`); an item whose name is taken there gets ` (<n>)`. Each change is
logged to `<plan folder>/undo.log` as JSON lines: an `intent` line before it and a `done` line with its reverse
after. Each row's `status` becomes `done`, `failed` or `skipped`, with `executed_at` and a `note` (`undo.log seq
<n>`, or the failure). A failed row stops its domain: later rows in it are skipped. An approved `convert` row is
named and left pending, since a conversion is the owner's or the deployment's, and the delete phase does not wait
for it; a row of an action the executor does not know fails. Exit 1 when a row failed.

### `prove`

    plan.py prove --plan <move-plan.csv> --before <manifest> --after <manifest> [--allow-departed-under <prefix> ...]

Treats each manifest as the set of (path, content id) pairs over every live path, copies included. The pairs that
disappeared must be exactly the `done` file `move`, `rename` and `delete` rows' (`from`, `evidence`), and the pairs
that appeared exactly the moves' and renames' (`to`, `evidence`); a `done` folder rename accounts for every pair under
its old path, and `rmdir` and `create` rows change no pair. Prints JSON: `gone_unexpected`, `new_unexpected`,
`gone_missing`, `new_missing`, `rows_checked` and `ok`; exit 0 only when `ok`. `--allow-departed-under <prefix>`,
repeatable, names a path prefix whose departures are expected, such as `_Migrations/<Project>/` once that project has
collected its files; it excuses only pairs that disappeared under that prefix. Run it after the main phase's re-audit,
and again, on the same before-manifest, after the delete phase's.

## `extract.py`

    extract.py --root <folder> --lane main|apps [--worker <k>/<N>] [--retry-failed] [--manifest <file>]
               [--out <dir>] [--ocr-bin <file>]
    extract.py repath --root <folder> [--manifest <file>] [--out <dir>] [--apply]

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

Local OCR reads in the languages the rulebook lists as `ocr_languages`, most likely first (default `en-GB`;
[the settings reference](settings.md#rulebookjson)). Each is a BCP 47 code, read in any letter case, and mapped by
its language and script or region, else by its language alone, to tesseract's languages (`eng`, `fra`, `deu`,
`spa`, `chi_sim`, `chi_tra`) and Vision's (`en-US`, `fr-FR`, `de-DE`, `es-ES`, `zh-Hans`, `zh-Hant`): `en`, `fr`,
`de` and `es` in any region, `zh-Hans` (or `zh-CN`, `zh-SG`) and `zh-Hant` (or `zh-TW`, `zh-HK`, `zh-MO`). Any
other code refuses the run before anything is written. tesseract reads with every language at once. Vision reads
with every language in one pass, unless the list holds Chinese and another language: then it reads first with the
Chinese codes and English, and, when that finds fewer than five Chinese characters, again with the other codes,
keeping the better reading. A reading is clean when it has at least 40 characters, mostly letters, digits, spaces
and ordinary punctuation, a word of three Latin letters or at least 15 Chinese characters, and (from Vision) a
confidence of at least 0.45.

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

### `repath`

    extract.py repath --root <folder> [--manifest <file>] [--out <extract dir>] [--apply]

An extract record carries the path its document had when it was read, so a curation round after extraction leaves
it behind. Once the round's re-audit is proved, `repath` rewrites each record's `path` to its document's
`current_path` in the manifest, matched by content hash (the record's id, its file name); nothing is read again, no
model is called and nothing else in a record changes. It prints `records`, `applied`, `paths_changed`,
`already_current`, `moves` (`[id, old path, new path]`), `departed_left` and `not_in_manifest` (`[id, path]`:
records of departed documents, and of ids the manifest does not hold, left as they are), and exits 0.

It is a dry run unless `--apply`. It refuses (exit 2, nothing written), naming each: a manifest `wiki.py` would
refuse; a record whose `id` is not its file name; a record whose document's paths the manifest's canonical choice
does not settle (copies naming no canonical copy, several, or one other than the current path, or a current path
another live entry holds); and a move to a current path that is not in the folder, since the manifest is then older
than the folder: re-audit first. `--apply` writes every repathed record to a temporary file beside it, through the
guarded writer (with `--read-only-root`, records inside the folder are refused; `--out` names records kept
elsewhere), and only then replaces the records. Whatever stops it part way, no temporary file stays: an OS error
or a refusal exits 2 naming the records already replaced, and anything else (an interrupt) is raised again once
the temporary files are gone. Cards need no repair: they hold no path, only their document's id.

## `iwa.py` and `page_ocr.swift`

`iwa.py` is a library `extract.py` calls, with no command of its own: it reads the `.iwa` streams of an iWork
package or zipped iWork file (Snappy-compressed protobuf) and walks every message generically, keeping the fields
that are human text, in storage order.

`page_ocr.swift` builds the `page-ocr` helper: `page-ocr [--lang <codes>] <image> ...` prints one JSON line per image
(`file`, `text`, `confidence`, `lines`, and `error` when it failed); `page-ocr --stdin` reads one image path per
line, where `LANG=<codes>|<path>` sets the languages for that image. `extract.py` keeps one `--stdin` process
running and restarts it if it stalls; its first run compiles Vision's model, which takes about a minute.

## `vision.py`

    vision.py --root <folder> --model <vision model> [--worker <k>/<N>] [--out <dir>] [--lanes <markers>]

The vision lane: a model reads the page images local OCR could not read cleanly. It drains `<work>/vision_queue/`,
taking the images of records still `needs_vision` whose id falls to worker k of N, six to a call. Each call copies its
images, as `p1.png` to `p6.png`, into a fresh, otherwise empty folder, and `agy` reads them there in its sandboxed
plan mode, the one call that may open files; the reply must return every image, in the order sent, each with its text,
or the attempt fails. A transcription replaces the page's text (tier `vision`, engine `agy`, the local text kept as
`local_text`; an empty one makes the page `blank`), and the record is written back to `--out` (default
`<root>/_Audit/extract`); once none of its pages is pending, its status becomes `ok`, or `partial` if a page was left
unread. A page whose batch fails three times is marked `unread`, its local text kept. Tries are kept in
`<work>/state/vision_tries_<k>.json`.

It sleeps through quota, stops (exit 3) while `<work>/state/ALERT` exists, and stops (exit 2) on a credential file or
a setup problem, which is not counted as a failed try. It exits once every done marker named in `--lanes` (default
`extract_main0,extract_apps0`; name every extraction worker's) exists and its share of the queue has stayed empty for
two looks a minute apart, writing `<work>/state/vision<k>.done`.

## `engines.py`

<!-- provisional: the engines' environment-variable lists (#91) -->

A library: the adapters every model call goes through, `Agy` (Gemini through the `agy` command-line tool) and
`Codex` (ChatGPT through `codex exec`). The rule it holds is the skill's
[engine isolation](../SKILL.md#engine-isolation), measured on the operator's machine (spike #91); the flags in use
are in the file, pinned by its tests, and what is still provisional is marked there.

- **Each call** runs in the working directory the caller gives (a fresh, empty one from `engines.fresh_dir`), with
  the prompt on standard input, in its own process group, killed on timeout (900 seconds for `agy`, 1,500 for
  `codex`; the pipes are then waited on for at most five seconds). Output is read as UTF-8, undecodable bytes
  replaced. `agy` runs sandboxed in plan mode, with an environment from which every key, token, credential, secret,
  base URL and endpoint variable is removed (`ANTHROPIC_API_KEY` and the like, any name ending `_API_KEY`,
  `_TOKEN`, `_CREDENTIALS`, `_SECRET`, `_BASE_URL`, `_API_BASE` or `_ENDPOINT`, and
  `GOOGLE_APPLICATION_CREDENTIALS`); proxy settings stay. `codex` runs read-only and ephemeral, ignoring user
  configuration and rules, with every tool feature it can disable disabled, and an environment of only `LANG`,
  `TMPDIR`, `USER`, `LOGNAME`, `HOME` and `PATH`. An output schema, when given, goes to `codex` as `--output-schema`,
  and it needs it strict (every object closed, every property required). `agy` is never given `--json-schema`: in plan
  mode that flag sends the model through plan mode's workflow (a `write_to_file` of a `plan.md` into agy's own state
  folder, `finish` steps, and a reply that asks to be approved before the JSON, or the finish tool's task summary in
  place of the answer, as real runs of agy 1.2.16 showed), which the tool-step rule below discards. So the schema's
  text is appended to the prompt, after "Reply with JSON only, matching this JSON Schema exactly:", counted by the
  size limit below, and the engine checks nothing against it: the caller does (`cards.py` checks every card). A
  schema file that cannot be read is a `SetupError`.
- **Outcomes.** `QuotaError` for quota text (quota, 429, exhausted, rate limit, usage limit, too many requests),
  whatever the exit code and before an empty answer is judged, with `reset_seconds` read from "Resets in 2h13m5s" or
  "try again at 5:12 PM" where the message says; `DegenerateError` for an empty answer; `ToolUseError` when the
  model used a tool (a `codex` tool item, or an `agy` tool step, which agy 1.2.16 streams as a `step_update` event
  with `step_type: "tool"`, a `tool_name` and a `tool_info`; any step type other than `user_input`,
  `agent_response` and agy's own `system_message` counts, whatever its keys, as does any other event naming a tool,
  action, function or call) or `agy` was refused one (a denied action), the reply discarded, allowed or not. The
  vision lane alone lets `agy` open its images: a step whose tools are all `view_file`, `list_dir` or
  `find_by_name`, and only when every string in its parameters, under any key and at any depth, that is or may be a
  path resolves inside the call's own folder, links and `..` resolved. That is a value under a key named for a path,
  a directory or a file, a value that looks like a path, a `file:` URL (parsed: the host must be empty or
  `localhost`, escapes are decoded and `..` resolved) and any value that names something that exists in the folder,
  such as a link, which is judged by where it leads; a string that names nothing is not a path, and one that cannot
  be judged, such as a URL of another scheme, is refused. Any other tool, a step naming no tool, or a read elsewhere
  fails there too;
  `PromptTooLong` before an `agy` call whose prompt is over 180,000 UTF-8 bytes (`AGY_MAX_PROMPT_BYTES`): agy
  cuts a message at about 192,000 bytes of prompt text, silently, and leaves the model a stored copy to read with a
  tool these calls deny. The figure is measured on agy 1.2.16 with `gemini-3.1-pro-high`, is the same for ASCII and CJK,
  counts the text's bytes (not characters, tokens or the serialised message) and sits 6% under the cut; an agy
  upgrade calls for a re-probe, about six calls. `PromptCut`, a `PromptTooLong`, when a prompt that passed that
  check was cut all the same: a stream event names `transcript_full.jsonl` (agy's stored copy) and the final
  result refuses a `command`. The two are on different lines of a real stream (the model's tool steps, then the
  result), so they are combined across it. That evidence only ever turns a failure into a clearer one, since a cut
  the task does not notice leaves no trace. `EngineError` for anything else. Two stop the run rather than the
  call: `SetupError` (no binary, `agy` without a model, a `codex` schema that is not strict) and
  `CredentialError` (below).
- **A per-project state folder** (`state_home`, the engine's `HOME` or `CODEX_HOME`) is optional, and the
  preparation sets none: both engines keep their one login as a file in the machine's home, so a separate folder
  would need it copied. When set, it is scanned before and after every call, and a regular file (not a symbolic link) whose name
  is shaped like a credential store (`auth.json`, `oauth_creds.json`, `tokens.json`, `cookies.sqlite`, `.netrc`,
  `.env`, `id_rsa`, `*.pem` and the like; notes and public keys excepted) stops the run.

## `isolation.py`

    isolation.py scan   --terms <file> --path <file or folder> [--path ...] [--if-present <file> ...] [--out <result.json>]
    isolation.py canary --terms <file> --engine agy|codex [--model <id>] --out <result.json>

Keeps other projects out of model-facing context. The terms file's format is in
[the card contract](cards.md#the-terms-file); `agy` needs `--model`.

- **`scan`** reads every file named, and every `.md`, `.json`, `.py`, `.txt`, `.sh`, `.swift`, `.csv`, `.jsonl`,
  `.toml`, `.yaml` and `.yml` file under each folder named, following links into folders (skills are often installed
  as links) with each real folder read once, so a link loop ends; a broken link, or a folder that cannot be
  read, is an error, never a skip. A path that does not exist is refused. It expands `~` and environment variables in every path itself, so a quoted
  `~/.codex/AGENTS.md` works. An `--if-present` file (an engine's global instruction file, such as
  `~/.codex/AGENTS.md` or `~/.gemini/GEMINI.md`) is read when the machine has it. One missing from a folder that
  exists is not an error: it is listed in `absent` and printed on standard error in plain words. One still holding
  `~` or `$` after expansion, whose folder does not exist (`~/.codx/AGENTS.md`), or that is a broken link, is refused
  with exit 2 and no result: that is a typo or an engine the machine lacks, and it must never read as a clean scan.
  Read `absent`: it should hold only files the machine really lacks. The paths assume each engine's default home
  (`~/.codex`, `~/.gemini`): a codex under another `CODEX_HOME` needs that folder's files given instead. It prints
  `{checked_at, files_checked, files_with_terms, absent, terms, pass}`, also to `--out`. A file holding a term is
  listed as `<n>:<path>`, `n` the index of the path it came from (every `--path` first, then each `--if-present`
  file the machine has) and the path relative to it, with every term and marker masked as `<term>` (a later path
  masking alike gets `#2`, `#3`). `pass` needs at least one file checked and none with a term; exit 1 otherwise.
  Scan every file a model is shown: the tools folder (its prompts, templates and schemas), the folder's
  `.familyai/` (the owner context the card instructions are filled from), the wiki briefs and review prompts, and
  the global files an engine reads whatever the folder.
- **`canary`** checks a cooperating engine, and nothing more. Each run invents a fresh name (a capitalised nonsense
  word, from `secrets`, clear of every term), and asks the engine, in a fresh empty folder and as a factual check of
  its setup, for every personal, family or account name, organisation, company, property, street, address or place
  in its whole context (system and instruction files included), as exactly one line: `NAMES:` and the names
  separated by commas, starting with that one, and nothing else. It writes `{engine, checked_at, terms, marker,
  model, effort, reply, usage, hits, answered, pass}` (and `error` when there is one) to `--out`, the reply and any
  error with their terms masked, and prints it without the reply. `model` is the id given (`cli-default` when none)
  and `effort` is the codex effort the canary ran at (`low`; agy's is part of its model id, so `null`). `answered` is
  true only when, after surrounding whitespace, the reply is a **single line** that is `NAMES:` and a
  comma-separated list, whose first item is the invented name (any case) and whose every item is name-like: one to
  six words, none of `. ! ? ; :` (or `*` or a backtick) inside it, no word (any case) from the closed set i, me, my,
  we, our, you, your, not, no, nope, nothing, none, cannot, can't, won't, decline, private, withheld, redacted, and
  not wrapped in brackets. Anything else is unanswered, which fails: a second line, a code fence, bold, a bullet, a
  trailing full stop, an empty item or an item that fails the name-like test. An honest reply in another shape fails closed, which
  costs a rerun and never gives a false pass. `pass` needs `answered` and no term in the reply. What it proves is that
  the engine answers in the form asked and names no banned term. It cannot prove that a model withholding names
  deliberately holds nothing back (a well-formed `NAMES:` line holding only the invented name passes): no reply can
  prove an absence, and the invented name is in the message, not in an instruction file. The scan of every file a
  model is shown, and the contamination check on every card, cover that. Exit 0 on a pass.

Neither writes a term out, and each removes its `--out` file before it even parses its command line, so a run that
stops early or is refused (a missing `--terms` or `--model`, a bad path) leaves no earlier pass behind. The result files are the record that the gate ran: `readiness.py` reads each engine's
canary from `<work>/state/canary-<engine>.json` ([`isolation.canary`](#readinesspy)), and no tool reads the scan's.
With nothing to list there is no terms file, so neither can run, and readiness reports each canary as `not run`
([the skill](../SKILL.md#5-open-the-gate-to-the-engines)).

## `cards.py`

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
| `--model` | the engine's model id (with `agy`, the effort is part of the id); `agy` without one is refused | none |
| `--effort` | `codex` reasoning effort | `medium` |
| `--light-model` | `codex` model for section notes, run at low effort | the main engine |
| `--terms`, `--no-isolation-terms` | the isolation list, or the logged statement that none is needed; `work` needs one of them | none |
| `--worker` | take every Nth batch file, from the kth | `0/1` |
| `--redo` | a file of ids to card again, one per line | none |
| `--small-chars`, `--batch-chars`, `--batch-items`, `--textless-batch`, `--section-chars`, `--single-max` | the batch budgets, in characters and items | 60,000; 180,000; 30; 60; 400,000; 600,000, except that with `--engine agy` (the default) `--small-chars`, `--batch-chars`, `--section-chars` and `--single-max` default to 50,000 (`AGY_BUDGET_CHARS`): three-byte CJK text plus the largest card prompt's own overhead (about 27 KB measured) then stays under agy's 180,000-byte limit, where 60,000 characters would not (so a document over `--small-chars` is read in sections: single mode is not used with agy's defaults) |
| `--section-tokens`, `--single-tokens` | budgets in estimated tokens instead (for `codex`, 110,000 and 150,000) | unset |

`--redo` plans each id as a first run would (its size decides: a long document is read in sections, reusing the
cached notes), and refuses an id with no extract record. Batches go in `<work>/batches/`, section notes in
`<work>/sections/`, each file named by the document, the engine, the section and a hash of the section's own text, the budget, the model
and effort that wrote the notes and the prompt (so a changed budget, model or prompt never reuses old notes; a cached
file that is empty or lacks its `[section k of n]` header is read again). To force a re-read, delete the document's
files in `<work>/sections/` (they start with the first 16 characters of its id). `--section-chars` and
`--section-tokens` under 1,000 are refused; a worker writes `<work>/state/cards<k>.done`
(or `redo<k>.done`) when it finishes, and stops (exit 3) while `<work>/state/ALERT` exists.

## `refs.py`

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
are relative to the wiki folder, source paths to the folder. Bundles, briefs and review prompts are working files,
refused inside the folder; `profile`, `check` and `drift` print JSON and write `--out` where `--read-only-root`
allows; `rationale` and `accept` write their audit file (default in `<root>/_Audit/`) the same way.

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

Malformed input (a manifest, card, extract record or `bundles.json` of the wrong shape, or a file where a folder
must be) is refused by name, exit 2.

### `profile`

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

    wiki.py bundles --root <folder> [--out <dir>] [--reuse] [--text-cap 12000] [--cards <dir>] [--extract <dir>]

Routes every live manifest entry outside the migrations folder by the compiled routing (its longest matching prefix; a
note row routes nothing) and writes one `bundle_<NN>.jsonl` per section to `--out` (default `<work>/bundles`; refused
inside the folder, and the tool's own: a rebuild removes `bundles.json` and the section files there). Each line is a
document: its short id, path, other copies, pages, extract status, and from its card `title`, `doc_type`, `party`,
`parties`, `doc_date`, `category`, `language` and `sensitive`; then `summary` and `key_facts`, and in an `active`
section the full text, capped at `--text-cap` characters. In any other section, reading, photos and other bulk
material is listed `compact`, without summary or text. A card with no extract record is refused.

`bundles.json` records `manifest_sha256`, `routing_sha256` (the routing rows and section kinds), `arguments` (the
non-default `--settings-dir`, `--manifest`, `--cards`, `--extract` and `--text-cap` it was built with), `text_cap`,
the counts per section, the files, and the `unrouted` and `uncarded` paths; either list non-empty exits 1. A
rebuild removes `bundles.json` before anything else, so one that fails part way leaves none to trust, and removes
section files it no longer writes.

**Staleness.** `brief`, and `bundles --reuse` (which reuses fresh bundles without rebuilding), refuse (exit 2)
bundles whose recorded `manifest_sha256` differs from the current manifest's, whose `routing_sha256` differs from
the current Schema's, or whose files are missing, and name the command that rebuilds them with the recorded
`arguments`. `--reuse` also refuses bundles built with other `--cards`, `--extract` or `--text-cap` than the ones
it is given. Every curation round ends in a re-audit that rewrites the manifest, so bundles built before it are
refused rather than read.

### `brief`

    wiki.py brief --root <folder> --page <page> [--page <page> ...] [--bundles <dir>] [--out <file>]

Renders `templates/page-brief.md` for a set of pages, sorted, so the order given does not matter: each page's
professional, deliverable and tone ([a page's professional](settings.md#a-pages-professional)) and its section's
contract (reader, questions, fields; a `fixed` section takes the method's shape, and any other section without a
contract is refused); the routing into its section and its bundle; the owner context from `rulebook.json` (folder
description, people with aliases, identifier policy, boundaries); the page map; each page's rationale block with what
the Schema fixes filled in; the JSON a drafting agent returns, which is what [wiki-onboarding step
4a](../../wiki-onboarding/SKILL.md#4a-draft-the-pages-when-every-document-has-been-read) names (`pages`, each with its
`path`, `text`, `rationale` and `index_entry`, then `open_questions` and `check_result`); and the checker command
every drafting agent runs, `python3 <tools>/wiki.py check --root <root> --work <work> --page <page> ...`, scoped to
the pages briefed. The page map is every page
under the wiki folder, every page in the Schema's Page professionals table, each Layout section's folder note (`<NN
Name>/<NN Name>.md`) and the pages briefed, each marked `exists` or `planned`. It refuses stale bundles, and writes
`--out` only outside the folder. The same inputs render the same bytes.

### The stage templates

In [`tools/templates/`](../tools/templates/), one per stage, each opening with a comment naming its stage and who
fills it; fields are in braces and doubled braces are literal, so each fills as a Python format string, and each
asks for JSON back. `brief` renders the page brief and `review-prompts` the two review prompts, whole, dropping the
comment; the coordinating agent fills the others.

| Template | Stage and pen | Fields |
| --- | --- | --- |
| `readers-interview.md` | readers; the owner answers | `folder_name`, `owner_context`, `profile_summary` |
| `structure-brief.md` | sections, routing and each page's professional; the librarian proposes | `folder_name`, `owner_context`, `readers`, `profile`, `current_schema` |
| `contract-brief.md` | a section's contract; its professional drafts | `section`, `professional`, `owner_context`, `readers`, `section_rows`, `routing`, `bundle` |
| `page-brief.md` | the pages; their professional writes | rendered whole by `brief` |
| `review-owner.md` | acceptance in the owner's lens; a model that did not write the page | rendered whole by `review-prompts` |
| `review-professional.md` | acceptance in the professional's lens; the same | rendered whole by `review-prompts` |

[`card-instructions.md`](../tools/templates/card-instructions.md), the card engine's instructions, sits beside
them ([the card contract](cards.md#what-the-engine-is-given)).

### `check`

    wiki.py check --root <folder> [--page <page> ...] [--rationale <file.md>] [--acceptance <file.json>]
                  [--out <file.json>]

Reads every page under the wiki folder (dot folders skipped) and prints JSON, also to `--out`, exiting 1 when
`problems` is not zero. `--page` (repeatable) is a drafting agent's check, the command its brief names: only those
pages are read, a link to a page the page map plans but nobody has written yet is listed in
`links_to_planned_pages` rather than in `dead_page_links`, `scoped_to` lists the pages read, and `documents_not_covered`, `rationale` and `acceptance`
read `not checked: scoped to N page(s)`, since sibling sections are still being drafted; the coordinator's
whole-wiki check judges them. Every key is a count, a list whose length is the count, or a named state; the fixture's
values are in [`../tests/expected/wiki-check.json`](../tests/expected/wiki-check.json). `--rationale` and
`--acceptance` read those files from elsewhere; a path given that does not exist is refused (exit 2), while a
default that does not exist reads as `not recorded`. Line numbers count from the page's first line.

- `wiki`, `pages`: the wiki folder and its page count.
- `frontmatter_conforming` (such as `"12/12"`) and `frontmatter_bad`: pages carrying `provenance`, `last-updated`
  and `status`, and the pages that do not, or that write `sources:` as one value rather than a list.
  `superseded_pages` counts pages whose `status` is `superseded` (no problem).
- `dead_source_paths`, `[page, path]`: a `sources:` entry that does not exist, or a backticked span in a page body
  holding `/` (a file or a folder; a span wrapped onto the next line reads as one) whose first segment is a live
  top-level folder, one holding a live manifest entry or copy, and which does not exist. A span that exists as
  written is found, whatever it holds. `[`, `]` and `?` are the characters they are, never a pattern, since file and
  folder names carry them: `Invoice [3].pdf` is not `Invoice 3.pdf`, so a stale one is dead. Only a `*` or a
  complete `<...>` in a segment (an opening `<`, a name and a closing `>`; a lone `<` or `>` is a character of the
  name) makes a span a routing pattern (as a Schema's routing writes them), judged up to its first
  patterned segment: dead when the folders before it do not exist; when they do, a `*` pattern is found if something
  matches it, and otherwise (nothing matches, or it holds a `<...>` placeholder) counted in
  `backticked_paths_unchecked`, since what the pattern stands in for cannot be told. A span under any other first
  segment, or patterned from its first segment, is counted there too (in the fixture, the Schema's `_Inbox/`). The
  Log's pages are history and are not read for paths. `readiness.py` names the unchecked count in its `wiki.problems`
  finding, beside the problems.
- `dead_page_links`, `[page, link]`: a link to a `.md` that resolves to nothing. A link is local when it has no
  scheme (`http:`, `mailto:`, `obsidian:`) and is not rooted at `/`, as `move` reads it (`local_link`), and a link
  with a title (`[Tax](Tax.md "t")`) is read as its target. A link to a page the page map only plans (as `brief`
  defines it) is dead until the page is written. `links_outside_page_map`, `[page, link]`: one that resolves to a
  file that is not a page of the wiki, such as the folder's `CLAUDE.md`.
- `em_dash_lines`, and the first ten as `em_dash_where`, `[page, line]`: body lines with an em dash outside inline
  code.
- `chart_blocks` and `charts_without_data_table`: chart pairing ([`chart`](#chart)). `charts_not_renderable`,
  `[page, line, type]`: every Mermaid block that does not parse as a kind `chart` emits (`pie`, `gantt`,
  `timeline`, or `xychart-beta` with exactly one `bar` or `line` series), a `flowchart` or `sequenceDiagram`
  included: only the kinds verified to render in the owner's apps are allowed, and a diagram the tool does not draw
  is written by hand and checked by nobody. `chart_sources_bad`, `[page, line, source]`: a paired chart's table row
  whose source `chart` would refuse (missing, resolving outside the folder, or under a reserved name); those cells
  are checked there, not again as backticked paths.
- `deadlines`, `[date, page]`: every `deadlines:` entry in the pages' frontmatter (no problem).
- `documents_in_scope`, `documents_not_covered` and the first twenty as `not_covered_sample`: coverage. A live
  document outside the migrations folder is covered when a page names its path or a copy's, in `sources:` or in
  backticks, or names its own parent folder in backticks, with or without the trailing `/` (`04 Study/` and
  `04 Study` cover `04 Study/Notes.rtf`, not `04 Study/Old/Notes.rtf`; a folder named without backticks covers
  nothing). The Schema page (whose routing names folders to route them) and the Log do not cover.
- `pages_without_single_professional`, `[page, why]`: a page `common.page_voice` refuses, unlisted in a section
  naming several professionals or in no section; `not verified: ...` without a compiled, fresh Schema.
- `rationale`: `not recorded` without the rationale file; otherwise `blocks` (how many headings), then as lists
  `pages_without_block`, `blocks_without_page`, `blocks_repeated` (a page's second block), `blocks_malformed`
  (`[heading, why]`, and `["# Wiki rationale", ...]` or `["(before the first block)", ...]` for the file itself)
  and `professional_not_named` (`[page, named, the page's professional]`, or `not verified: ...` without a
  Schema). A block's professional is its `- Professional lens:` text up to the first `;`, compared with
  `common.page_voice`'s case-folded and with spaces collapsed. Each heading is reported once, by the first that
  holds of: repeated, malformed, for no page, lens.
- `acceptance`, `acceptance_counts`, `acceptance_pages`, `acceptance_not_verified` and
  `acceptance_records_for_no_page`: acceptance, reported apart ([the record](#_auditwiki-acceptancejson)).
- `problems`: every finding above, summed. Acceptance is never part of it.

### `rationale`

    wiki.py rationale --root <folder> --returns <dir|file.json> [--out <file.md>]

Writes the rationale file from the drafters' returns (the JSON `brief` asks for, each page with its `rationale`
block): a `.json` file holding one return or a list of them, or a directory of such files. The file is
[`wiki-maintenance`'s](../../wiki-maintenance/SKILL.md#the-rationale-block): the line `# Wiki rationale`, then per
page a heading `### <page path>` followed at once by exactly five lines, `- Reader and use: `,
`- Professional lens: `, `- Shape: `, `- Changed from the previous page: ` and `- Left out or flagged: `, each with
text after it; blank lines go only between blocks. It refuses (exit 2, nothing written) a malformed block, a block
whose heading is not its entry's path, and a page returned twice; otherwise it writes the whole file, pages sorted
by path, so the same blocks give the same bytes however they are grouped. The default output is
`<root>/_Audit/wiki-rationale.md`; with `--read-only-root`, write it elsewhere with `--out`. It prints `blocks`,
`pages_without_block` and `blocks_without_page`, exiting 1 when either list is not empty.

### `review-prompts`

    wiki.py review-prompts --root <folder> --page <page> [--page <page> ...] --author-model <model>
                           --reviewer-model <model> [--sample 5] [--cards <dir>] [--out <dir>]

Renders, for each page, `templates/review-owner.md` (the contract's reader and questions, in order, or for a
`fixed` section a note that its shape is the method's) and `templates/review-professional.md` (the page's
professional, deliverable and tone, the contract, the section's routing, the documents and folders the page cites,
and a sample of facts from their cards), each carrying the page's text and sha256. They are working files, written
to `<out>/<page path without .md>.owner.md` and `.professional.md` (default `<work>/reviews/`) and refused inside the
folder; the same inputs render the same bytes. A reviewer model equal to the author model is refused.

The sample is fixed by rule, so a second review of a page checks the same facts: every non-empty date, amount and
reference number in the `key_facts` of the cards of the documents the page cites (in `sources:` or backticks, by
their path or a copy's), as (the document's current path, kind, value), deduplicated and sorted. With `n` facts and
`--sample k`, all of them when `n <= k`; otherwise the facts at indices `(s + j * n // k) % n` for `j` from 0 to
`k - 1`, in index order, where `s` is the page path's sha256 read as an integer, modulo `n`: evenly spread over the
sorted facts, from an offset each page has its own.

The reviewer replies in JSON, as the template asks: `page`, `page_sha256` (copied from the prompt, tying the
verdict to the version read), `lens` (`owner` or `professional`), `author`, `reviewer`, `verdict` (`accepted`, or
`changes` with at least one finding) and `findings`, each `{where, finding}`; the professional's reply also carries
`facts_checked`, each `{fact, source, on_page, matches}`.

### `accept`

    wiki.py accept --root <folder> --reply <file.json> --author-model <model> --reviewer-model <model>
                   [--date <YYYY-MM-DD>] [--out <file.json>]

Records one verdict, for one page in one lens, in the acceptance record. It reads the reviewer's reply after the
coordinating agent has added a `response` to each finding, and takes the models from `--author-model` and
`--reviewer-model`. It refuses, exit 2 and nothing recorded: a page that is not in the wiki; a lens other than
`owner` or `professional`; a verdict other than `accepted` or `changes`; a finding without its `where`, `finding`
and `response`; `changes` without a finding; an `author` or `reviewer` in the reply other than the flags; a
`page_sha256` in the reply other than the page's now (the page changed after its prompts were rendered); a page
with no single professional (the record names it); and a `--date` that is not `YYYY-MM-DD`, alone or followed by `T`
and a valid time (`12:00`, `12:00:00`, with `Z`, `+0100` or `+01:00`). A reviewer equal to the author, their names
compared case-folded with spaces collapsed, is refused (exit 2) **and recorded**, as `refused` with its reason, so
the check reports it. The default record is `<root>/_Audit/wiki-acceptance.json`; `--out` names another, read and
added to alike.

How the record is written: `accept` takes an exclusive lock (`fcntl.flock`) on `<record>.lock`, created beside the
record and left there, reads the record, adds its one record and writes the whole file anew, to a temporary file
renamed over it, then releases the lock. Runs made at once therefore each keep their record, and no record is
changed or removed. A file system that cannot lock (some network shares) is refused, naming the lock: write the
record with `--out` on a local disk.

### `_Audit/wiki-acceptance.json`

The acceptance record [`wiki-maintenance` asks for](../../wiki-maintenance/SKILL.md#acceptance), as JSON (UTF-8,
indent 1, a final newline):

    {"version": 1,
     "records": [
      {"page": "20 Finance/Tax.md", "lens": "owner", "verdict": "accepted",
       "sha256": "<the page's sha256 when recorded>", "professional": "chartered tax adviser",
       "contract_sha256": "<its section's contract's sha256 then>", "author_model": "model-a",
       "reviewer_model": "model-b",
       "date": "2024-06-30", "findings": [{"where": "opening line", "finding": "...", "response": "..."}]},
      {"page": "20 Finance/Tax.md", "lens": "professional", "verdict": "refused", "sha256": "...",
       "professional": "chartered tax adviser", "contract_sha256": "...", "author_model": "model-a",
       "reviewer_model": "Model-A", "date": "2024-06-30T12:00:00+0000", "findings": [],
       "reason": "the reviewer model 'Model-A' is the author model 'model-a'; ..."}]}

Records are kept in the order they were made. Each has, in this order:

- `page`, `lens` (`owner` or `professional`) and `verdict` (`accepted`, `changes` or `refused`);
- `sha256`: the page's when recorded;
- `professional`: the page's then, from `common.page_voice`;
- `contract_sha256`: the sha256 of its section's compiled contract then, the object `{reader, questions, fields}`
  from `wiki-schema.json` (the page contract as `wiki-maintenance` defines it), or JSON `null` for a section without
  one, serialised with keys sorted, no spaces, UTF-8. The section's list of professionals is left out, so naming
  another professional for another page of the section changes no page's standing;
- `author_model` and `reviewer_model`, as given, trimmed;
- `date`: `--date`, or the local time as `YYYY-MM-DDTHH:MM:SS+ZZZZ`;
- `findings`, each `where`, `finding` and `response` (other keys dropped);
- `facts_checked` when the reply carries it, kept as given, and `reason` on a refusal.

A record of another shape, one without `professional` or `contract_sha256` included, fails loud in `check` and
`accept`.

**States.** `check` reports each page's state from its latest record in each lens: `refused` when either lens's
latest is a refusal; `accepted` when both lenses' latest are `accepted` at the page's current sha256, under its
current professional and contract sha256; otherwise `not recorded`, with why (`no verdict recorded`, a lens with
`no verdict`, `changes asked`, `accepted an earlier version; the page changed since`, `accepted under an earlier
contract or professional`, or `accepted, but not verified: ` and why the page's professional cannot be read: the
Schema missing or stale, or the page without a single professional). A page is accepted again after a change to its
text, its contract or its professional, as the rule asks.

- `acceptance_pages`: `[page, state, why]` per page.
- `acceptance_counts`: each state counted, zero included.
- `acceptance`: `refused` when a page is, `accepted` when every page is, otherwise `not recorded`.
- `acceptance_not_verified`: sorted, every page whose acceptance cannot be verified, recorded or not, because its
  professional and contract cannot be read (no compiled Schema, a stale twin, or no single professional). Read it
  rather than the wording of the why text.
- `acceptance_records_for_no_page`: the pages the record names that the wiki no longer holds (moved or removed;
  their records stay as they were made).

None of it counts as a problem or makes the check pass, and a problem never unsets it.

### `move`

    wiki.py move --root <folder> --map <file.json>

Moves pages, `{"20 Finance/Tax.md": "25 Tax & Duty/Tax & returns.md"}`, and rewrites every relative link to or from
a moved page, percent-encoded with `/` and `&` literal as `productivity:portable-markdown` sets out
(`../25%20Tax%20&%20Duty/Tax%20&%20returns.md`); a link neither end of which moved is left as written. It renames
the moved pages' rationale headings, removes the folders it empties, and prints JSON: `moved`, `pages_rewritten`,
`links_rewritten`, `folders_removed`, `rationale_blocks_renamed`, `schema_rows_to_update` (each moved page the
Schema's Page professionals table still names), `layout_to_update` (each move that leaves the Schema's Layout wrong:
a page moved out of every Layout section, or a section's folder note moved away) and `dead_links` left anywhere in
the wiki; any of the last three exits 1. For the first two, edit the Schema, then compile.

It refuses, before changing anything: a missing page; an existing or shared destination; a destination under a
file; one differing only in case from a page, another destination or a folder (a case-only rename of the page
itself stays possible where the file system allows it); a path outside the wiki; and the Schema page itself. Every
destination is checked against the pages as they are before the run, so a swap or a chain is refused as
`destination exists`: make a swap in three runs through a temporary name (A to T, then B to A, then T to B) and a
chain in two from its far end (B to C, then A to B). A run writes every moved page first, then rewrites the pages
linking to them, and only then removes the old pages; after a failure part way, delete the pages it wrote at the
map's destinations and run the same map again.

### `drift`

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

    readiness.py --root <folder> [--terms <file>] [--manifest <file>] [--out <file.json>]

The [hand-off contract](../SKILL.md#the-hand-off-contract), checked. Read-only on the folder, it reads the settings
twins without trusting them, so a stale or unpinned twin is a finding rather than a refusal. It prints one JSON
report (also to `--out`, refused inside the folder with `--read-only-root`) and exits 0 when nothing is found, 1 on
any finding, and 2 on a tool error: a missing or malformed manifest (a live entry without `hashed` true or false
included) or canary result, or a crash, so 1 always means findings (a malformed card or extract record is a finding,
counted with the rest). The fixture's report is
[`../tests/expected/readiness.json`](../tests/expected/readiness.json).

Each check is a count, a state, `ok`, `finding: ...` or `not verified: ...`. `findings` lists every finding as
`[check, what]`, `check` being the report key that holds it; `not_verified` lists every named not-verified state the
same way, which is not a finding and not a pass either, and does not change the exit code; `summary` counts both.

- `manifest`: the live, departed, migrating, root stray, redundant copy, hygiene and unconverted iWork counts and
  the items on disk, reported, not findings; `live_paths_missing` counts live entries whose current path is gone, a
  finding (the manifest is not current: re-audit).
- `records`, over the live documents `extract.py` reads (hashed ones): `missing_extracts`, `missing_cards`,
  `malformed_cards` (a card not in the card format, such as a `sensitive` that is not true or false: counted and
  named, never the end of the check, so a folder carded by an older tool shows every card to redo),
  `malformed_extracts` (an extract record that is not JSON, not UTF-8, not an object, unreadable, or whose pages are
  not a list of page objects with a whole-number `n` when they have one: counted and named the same way, by the
  document's path and the reason, with no absolute path; remove it and run `extract.py` again),
  `bad_category` (outside the rulebook's `card_categories`), `extract_paths_stale` (a record whose path is not the
  manifest's; the finding names the [`extract.py repath`](#repath) command that repairs it, after the malformed
  extract records, which `repath` cannot read, are dealt with) and `contamination` (a
  card naming an isolation term its own source lacks, by `cards.py`'s rule; `not verified` without `--terms`). A
  count above zero is one finding. A check that needed a card or extract record that could not be read says so for
  that document rather than reading it clean: `extract_paths_stale` and `contamination` become `not verified for N
  document(s) whose ... is malformed` (after the count, `1; not verified ...`, when some documents were checked and
  one held a finding), and are listed in `not_verified`.
- `isolation.canary`: per engine (`agy` and `codex`), the result `isolation.py canary --out` wrote to
  `<work>/state/canary-<engine>.json`: `passed (model M, effort E)`, `failed: ...` (a finding), `not run: ...` (not
  verified) or `not verified: ...` (a pass recorded without `answered` and the invented `marker`, so from a canary a
  refusal could pass: run it again). A pass names the model that was cleared (`model not recorded` for a result that
  has none), so a reader can compare it with `card_meta.model` of the cards; nothing compares them for you.
- `wiki`: [`wiki.py check`](#check-1)'s report, reading the Schema from `--settings-dir`; its `problems` are one
  finding and its not-verified states are listed.
- `wiki_handoff`: `rationale_file`, a finding when `_Audit/wiki-rationale.md` is missing (`check` reports it `not
  recorded` without counting it, since drafting agents run `check` before the file is assembled); `pages_accepted`,
  `pages_not_accepted` and `pages_not_verified`: each page `check` does not report `accepted` is one finding naming
  the page, its state and why, a refused page included, except a page `check` lists in `acceptance_not_verified`
  (its professional and contract cannot be read, so its acceptance cannot be judged): those are counted and listed
  once as not verified, what keeps them unreadable (a missing or stale Schema twin, a page with no single
  professional) being a finding of its own. `records_for_no_page` lists the pages the acceptance record names that
  the wiki no longer holds, as information only (records stay as they were made).
- `rulebook`: `present`, `valid_utf8` (as `settings.py check` reads it), `copies_identical` and `names_wiki_folder`.
  `scratch.left_in_audit`: folders in `_Audit/` other than `plans`, `extract` and `cards`.
- `handoff_contract`: `wiki_folder_named_after_folder`; `fixed_pages` (`00 Index`, `01 Deadlines`, `90 Schema`,
  `91 Log`; numbered sections are `check`'s, where a page in no Layout section is a problem);
  `derived_pages_hold_nothing_hand_written`, `recurring_dates_in_frontmatter` and `other_derived_pages` (below);
  `rulebook_reserves_rulebook_filenames` and `new_files_routed_within_folder`
  ([a project files within itself](../../wiki-maintenance/SKILL.md#rules-that-keep-it-safe)), both reading the
  rulebook's prose by substring and keyword: a filename is reserved when `CLAUDE.md`, `AGENTS.md` or `GEMINI.md` is
  written anywhere in `CLAUDE.md`, and new files are routed out when a line names the migrations folder
  (`_Migrations/`) together with "new file", "dropped", "goes to" or "go to", in any case, so a line saying where
  approved migrations wait passes and one saying new files go there does not; `settings_rulebook_json` and
  `settings_wiki_schema_json` (present and fresh).

**Derived pages.** The rule is `wiki-maintenance`'s *Deadlines are derived, not authored*
([rules that keep it safe](../../wiki-maintenance/SKILL.md#rules-that-keep-it-safe)), read through the keys its
roll-up reads
([canonical frontmatter](../../wiki-maintenance/SKILL.md#canonical-frontmatter--the-keys-the-deterministic-sweeps-read)),
`01 Deadlines` being the derived list of forward dates.

**The Deadlines page may hold only what the roll-up renders from the pages' frontmatter; every other line is
reported.** No date is looked for in the page's text, so no shape of hand-kept date can be missed or mistaken for
rendered output. The page is read against the roll-up's output grammar instead:

1. Each page the roll-up reads (every `.md` under the wiki folder, dot folders and dot files included, but not its
   derived pages, `Index`, `Log`, `Deadlines`, `Coming Events`, `Open Questions`, `Schema` and `Conventions`, nor a
   `.proposed.md` or `.superseded.md` sibling) is read by the frontmatter subset below, and what the roll-up could
   write is worked out from it (superseded pages left out):
   - the entries `(date, note, page)`: each `recurring` item gives its month and day, each `deadline` its date (its
     first ten characters) with its `deadline_note`, each `deadlines` item its date, the note being what YAML reads,
     with its whitespace collapsed;
   - the lines of its "Could not read" list, in its exact wording, **each as many times as the roll-up writes it**
     (one the page lacks is reported too, as an incomplete page):
     `- <page> (unreadable: <exception class>)` for a page that cannot be read (a file that is not UTF-8),
     `- <page> (malformed frontmatter)` for one the roll-up cannot read as a mapping whatever YAML says (below), and
     `- <page> (unreadable recurring date: <the first 60 characters of the item as Python writes it>; <the way to write
     it>)` for each `recurring` item it refuses, a quoted bare item staying a string and a quoted empty value `''`.

   One predicate says which pages the roll-up reads, and it is the roll-up's own: every page that reads, bar those
   named above, **whatever its `provenance`** (the roll-up skips none), so a page with `provenance: manual` or
   `calendar` is a source for what the page may hold and for what it must show alike.

**The frontmatter subset.** Readiness reads a defined subset of the frontmatter, or says it did not. The subset is a
fence at column 0 (`---`, the page's first line, closed by a line starting `---`), and between the fences:

- plain `key: value` pairs at column 0, the key a word (`[A-Za-z_][A-Za-z0-9_-]*`);
- a value that is a plain, single-quoted or double-quoted scalar (an empty quoted one is the empty string, not no
  value; a double-quoted scalar's only escapes are `\"` and `\\`), a flow mapping `{date: ..., note: ...}` on one line,
  or `[]`, or no value, which a block list under it may follow;
- a block list, its items at one indent (column 0 included) each a flow mapping, a block mapping of plain `key: value`
  pairs over its lines, or a bare scalar (a quoted bare item stays a string, never a date);
- a trailing ` # comment` after a scalar or after a flow mapping's closing `}`, and whole-line comments;
- in a flow mapping, an unquoted comma ends a value and what follows is a key of its own.

Anything else makes the deadline check say `not verified: <page> uses YAML this check does not read (<construct>)`,
which is neither a finding nor a pass and is listed in `not_verified` (`handoff_contract.frontmatter_read`). The
constructs named are: indented frontmatter and a multi-line scalar, a `? ` key, a `...` marker, anchors, aliases and
tags, `|` and `>` scalars, a flow mapping over several lines or with a comment inside, a flow sequence, a nested flow or
block collection, a quoted `status`, a quoted key or a key that is not a plain word, a colon and space inside a plain
scalar, an unclosed quote or text after a quoted scalar, a double-quoted escape other than `\"` and `\\`, a tab for
indentation, a directive, list items at different indents, a line over 20,000 characters, a block over 200,000,
text after the opening fence, and a plain value YAML reads as a bool, null, number, time or date (below). While any
page is out of scope only the judgements that depend on reading it are withheld: whether an entry is backed by the
pages, and how often and why the roll-up lists that page under "Could not read" (a line there naming it is accepted
when it is in the roll-up's error-line grammar, `malformed frontmatter` or a refused recurring date, since it was read as
text and is not unreadable). The rest is still judged, because it does not depend on the YAML: every line of the
Deadlines page outside the roll-up's grammar, a "Could not read" line outside the error-line grammar or naming a page
the roll-up does not read, the lines the other pages give, an entry's date form, an unreadable date, a duplicated
line, the Deadlines page's own frontmatter.

A frontmatter is `malformed` only for what needs no YAML reader to see: a fence that never closes, a list where the
keys should be (the first line is a `-` item), bare words with no colon anywhere, or a day the calendar does not have
where a date is read (`2025-02-30`, which PyYAML cannot build, so the roll-up lists the page as malformed). What
PyYAML would read but the subset does not is out of scope, never malformed.

**A plain scalar PyYAML reads as anything but text is out of scope.** The roll-up writes the value YAML gives, not
the text the page holds (`note: yes` is written `True`, `12:30` is `750`, `2025-01-31` a date), and the check has only
the text. So an unquoted scalar that PyYAML's resolver turns into a bool (`yes`, `no`, `on`, `off`, `true`, `false`,
and `y` and `n`, which YAML 1.1 reads so, in any case), a null (`null`, `~`), a number (a decimal, `0x1F`, `0b1`,
`0405`, `1_000`, `1.5`, `.inf`), a time (`12:30`, a sexagesimal number), a date, `<<` or `=` is named as `a plain value
YAML reads as <bool|null|number|time|date|merge key|value>`, wherever the roll-up shows a value: a `note`, a
`deadline_note`, any other value in a mapping that holds one. A quoted scalar is always text, and `yes please`,
`12:30 sharp` and `04-05` are text. A key the roll-up never writes (`title: yes`) is not judged. An empty plain value
is no value. A `date`, a bare list item and `deadline` keep their own reading for the values it can give exactly: a
calendar day, a bool, a null, a decimal whole number or float (so `{date: yes}` is a recurring item the roll-up refuses,
shown as `{'date': True}`); any other kind is out of scope as above. The suite checks the rule against a copy of
PyYAML's own resolver patterns over every short string of the characters that matter, so nothing within the subset is
read otherwise than PyYAML reads it.

2. The page is read line by line. The grammar is its frontmatter, which holds `provenance: derived`, `status:
   current` and a `last-updated` day, once each, and nothing else; the headings `# Deadlines`, `## Upcoming`,
   `## Every year`, `## Past` and `## Could not read`; the italic intro; `_None._`; blank lines; the empty-roll-up
   banner, which is accepted only directly after the intro or the title, only when the pages give no entry at all,
   and with any count of pages (a callout is its marker line, then its text line); the lines under `## Could not
   read`, each in the roll-up's error-line grammar (`- <page> (<reason>)`, the page one the roll-up reads and the
   reason one of the three forms in step 1) and, for a page that reads, one in the set from step 1; and entries. A
   line that appears twice is reported. The lines the roll-up always writes are required: the title, the intro and
   `## Upcoming`; and, with what the page shows or the pages give, `## Every year` beside a recurring entry,
   `## Past` beside a past one, the intro line of a "Could not read" list that is there, and `_None._` when no page
   gives a forward deadline (judged only while every page is read). A missing one is reported as an incomplete
   derived page naming it. The fixture's roll-up writes no em dash, so its intro puts a colon where the reference
   roll-up puts the dash, as its entries do.
3. An entry is `- **<date>**`, then the page titles and, when there is one, the note, each after a spaced em dash
   (the reference deployment's roll-up), or `: <note>` (the fixture's roll-up), then ` (<links>)` ending the line. The links are read from
   the end of the line, each `[<page path without .md, or its title>](<its path from the roll-up, percent-encoded>)`
   to a different page of the wiki, so a page name holding brackets, `](` or a long encoded name is read by its own
   text and no target length is capped. The titles are the linked pages' own, so a note is never guessed at.
4. An entry is clean only when its date is in the form the roll-up writes (`<day> <Month name>`, no ordinal and no
   leading zero, or `YYYY-MM-DD`) and its `(date, note, page)` is in the set from step 1, the dated ones by their full
   date and the recurring ones by month and day, the note exactly. `04-05` or `April 5th` in an entry line is
   hand-edited. One whose date no page carries is reported as that date, a `YYYY-MM-DD` no page's frontmatter carries
   or a day and month no page's `recurring` list carries; one whose date is not a date the contract reads (`5-Apr`,
   `5 Sept 26`) is an `unreadable yearly date`. Every other line is `hand-written content in a derived page`, with
   its line number and its first forty characters (an invisible character shown by its code): a table, a heading or
   a sentence of the page's own, a link or text added to an entry, a note or page the frontmatter does not give, a
   date in link text, in separate cells, in another script or with a zero-width character in it, a line in the page's
   frontmatter that the roll-up does not write, a line of "Could not read" it did not write. A `YYYY-MM-DD` on a line
   that is no entry is also judged by the check on dated deadlines.

Completeness is by date, not by entry: a page dropped from a folded line, or an entry deleted while its date shows
elsewhere, is not reported. The roll-up regenerates the page, so readiness checks only that nothing hand-written is on
it. Every search is bounded and each line is read in one pass, so a line of 100,000 characters costs a pass over it. A
frontmatter `recurring` date is read as the reference deployment's roll-up reads it, so both sides accept the same spellings:
`MM-DD`, month first, two digits each; or a day and a month name, the day first or the month first (`5 April`,
`April 5`), the name in full, its first three letters or `sept`, in any case, the day with an optional lower-case
ordinal (`5th Apr`). Any other numeric form (`6/4`, `4-5`) is refused, as is a day the month cannot have (`31
April`); 29 February is a date. The roll-up shows the month in words, so a numeric `MM-DD` written the wrong way round
shows on the page. The sources are the pages that are not `superseded`. The grammar's text is checked against the
real roll-up: `tests/rollups/` holds the pages the reference deployment's roll-up rendered for a plain wiki, an empty one with its banner, a
recurring-only one, one with a "Could not read" list, one of page names holding brackets and long encoded targets, one
of the YAML rules (a comma, a comment, a comment after `}`, block items), one of refused items (a quoted empty value, a
quoted bare item, the same item twice) and one of pages under a dot folder and of `.superseded.md` and `.proposed.md`
siblings; each must read clean (`rollups/capture.py` refreshes them).

- `derived_pages_hold_nothing_hand_written`: the page holds only what the roll-up renders (above); every `YYYY-MM-DD`
  on it is a page's `deadline` or `deadlines` date (`YYYY-MM-DD` or `{date, note}`); the roll-up shows every such
  date of a page the roll-up reads that is not before its `last-updated` (one before it is past, not forward), and a
  `last-updated` after today, by the tools' clock, is a finding, forward then being judged from today; a deadline
  entry that is not a real `YYYY-MM-DD`, bare or in `{date, note}`, is a finding; and a roll-up with nothing to show
  (no forward deadline and no recurring date) in a wiki of derived pages says why (a page of headings or a bare
  "None" does not).
- `recurring_dates_in_frontmatter`: every yearly date on the roll-up is a page's `recurring` date and none is
  unreadable; every `recurring` entry reads `{date, note}`, the date as `MM-DD` (month first) or a day and a month
  name, a day the month has, with a note; and the roll-up lists each (a `YYYY-MM-DD` on the same day does not show
  it).
- `other_derived_pages`: another page the Schema marks derived (an open-questions list) shows no date its sources
  would settle, so it is named `not verified`, apart from the roll-up's result.

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
| `reviews/` | `wiki.py review-prompts` | each page's `.owner.md` and `.professional.md` review prompt |
| `state/extract_<lane><k>.done`, `state/vision<k>.done`, `state/cards<k>.done`, `state/redo<k>.done` | each worker | done markers |
| `state/vision_tries_<k>.json` | `vision.py` | failed tries per image |
| `state/card_err_<id>.txt` | `cards.py work` | why a document could not be carded |
| `state/redo_done_<k>.txt` | `cards.py work --redo` | ids re-carded so far |
| `state/redo_refs.txt` | `refs.py --apply` | ids to re-card |
| `state/ALERT` | `cards.py work` | a contamination alert; every worker stops while it exists |
| `state/canary-<engine>.json` | `isolation.py canary --out` | the canary's result, which `readiness.py` reads |
