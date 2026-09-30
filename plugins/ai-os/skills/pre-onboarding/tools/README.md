# pre-onboarding tools

Standard-library Python (3.9+) plus one Swift helper for Apple Vision OCR. Generic and settings-driven: nothing
here names a folder, a person or a project. Every tool takes `--root <folder>`; most also take `--settings-dir`
(default `<root>/.familyai`), `--work` (state outside the folder, default `~/.ai-os-pre-onboarding/<folder>`) and
`--read-only-root` (refuse any write inside the folder, used with `--out` elsewhere to prove a tool). Every tool
that takes `--root` refuses a stale settings twin before it reads or writes anything, except `settings.py check` and
`readiness.py`, which report it, and `settings.py compile`, which is how a stale `wiki-schema.json` is fixed; the
twins' formats are in [`../references/settings.md`](../references/settings.md).

| Tool | What it does |
| --- | --- |
| `audit.py` | Deterministic audit: manifest `/2`, `AUDIT.md`, `summary.json`; merges with the previous manifest |
| `plan.py` | Curation plans: `light`, `migrate`, `return`, `approve`, `rmdirs`, `check`, `execute`, `prove` |
| `extract.py` | Full text per page: text layer, broken-layer detection, Vision OCR, tesseract, office and iWork readers |
| `iwa.py` | iWork text without the apps (Snappy-compressed protobuf, walked generically) |
| `page_ocr.swift` | Apple Vision OCR helper; build with `swiftc -O page_ocr.swift -o page-ocr` |
| `vision.py` | Model vision lane for pages local OCR could not read |
| `engines.py` | agy and codex adapters: stdin prompts, sandboxed, tool use refused, typed outcomes, credential guard |
| `isolation.py` | Isolation terms scan and per-engine canary |
| `cards.py` | One card per document; deterministic whole-chunk join; contamination guard |
| `refs.py` | Deterministic repair of truncated reference numbers from each card's own source |
| `settings.py` | Compile `wiki-schema.json` from the Schema's tables; check both twins and the rulebook's facts |
| `wiki.py` | Folder profile, evidence bundles, drafting briefs, checks, page moves, drift, charts from cited rows |
| `readiness.py` | Hand-off readiness, including the hand-off contract |
| `common.py` | Shared: settings loading, guarded writes, package hash, JSON parsing, token estimate |

The package hash (sha256 over an iWork package's members in walk order, directories and files sorted, each member
contributing relative path, NUL, member sha256 hex, newline) is shared with any deployment that reads the manifest.

## Building the wiki: `wiki.py` and the stage templates

The stages and who holds the pen at each are [`wiki-onboarding`](../../wiki-onboarding/SKILL.md)'s and
[the core wiki rule](../../wiki-maintenance/SKILL.md#the-core-wiki-rule)'s. A template in
[`templates/`](templates/) briefs each stage's author: `readers-interview.md`, `structure-brief.md` (the librarian),
`contract-brief.md` and `page-brief.md` (the page's professional), `review-owner.md` and `review-professional.md`.
Each opens with a comment naming its stage and who fills it: `wiki.py brief` renders the page brief whole and drops
the comment; the coordinating agent fills the others. Fields are in braces and doubled braces are literal, so each
fills as a Python format string. Each asks for JSON back.

    wiki.py profile --root <folder> [--depth 2] [--parties 5] [--out <file.json>]
    wiki.py bundles --root <folder> [--out <dir>] [--reuse] [--text-cap 12000]
    wiki.py brief   --root <folder> --page <page> [--page <page> ...] [--bundles <dir>] [--out <file.md>]
    wiki.py move    --root <folder> --map <file.json>
    wiki.py drift   --root <folder> [--out <file.json>]

Each also takes `--settings-dir`, `--work` and `--manifest` (default `<root>/_Audit/manifest.json`); `profile` and
`bundles` take `--cards` and `--extract` (default `<root>/_Audit/cards` and `<root>/_Audit/extract`). Bundles and
briefs are working files, refused inside the folder; `profile` and `drift` print JSON, also to `--out` where
`--read-only-root` allows.

**`profile`** gives the librarian, per top-level folder and subfolder down to `--depth`, its live documents (by
current path), the copies held there (and the folders their documents live in), the documents' cards by
category, the span of their `doc_date`s and their top parties, aliases folded to the rulebook's canonical names.
Migrating and departed entries are counted, not profiled. For example, a folder that only mirrors others:

    {"folder": "05 Archive", "documents": 0, "copies": 4, "copies_of": {"04 Study": 3, "06 Work": 1},
     "carded": 0, "categories": {}, "dated": 0, "earliest": null, "latest": null, "parties": []}

**`bundles`** routes every live manifest entry outside the migrations folder by the compiled routing (longest
prefix; a note row routes nothing) and writes one `bundle_<NN>.jsonl` per section: a line per document with its
path, copies and card, and the full text (capped) for an active section; in any other section, reading, photos
and other bulk material is listed compact, without summary. `bundles.json` records `manifest_sha256`,
`routing_sha256` (the routing rows and section kinds), the counts, and the `unrouted` and `uncarded` paths, which
exit 1. A rebuild removes section files it no longer writes.

**Staleness.** A consumer checks the bundles before using them: `brief`, and `bundles --reuse`, which reuses fresh
bundles without rebuilding. Either refuses (exit 2) bundles whose recorded `manifest_sha256` differs from the
current manifest's, or whose `routing_sha256` differs from the current Schema's, or whose files are missing, and
names the command to rebuild them, with the non-default arguments the bundles were built with (recorded in
`bundles.json` as `arguments`). A rebuild removes `bundles.json` before anything else, so one that fails part way
leaves none to trust. Any migration or curation round ends in a re-audit, which rewrites the manifest,
so bundles built before it are refused rather than read.

**`brief`** renders `templates/page-brief.md` for a set of pages (sorted, so the order given does not matter):
each page's professional, deliverable and tone (`common.page_voice`) and its section's contract (reader,
questions, fields; a `fixed` section takes the method's shape, and any other section without a contract is
refused), the routing into its section and its bundle; the owner context from `rulebook.json` (folder
description, people with aliases, identifier policy, boundaries); the page map; each page's rationale block with
what the Schema fixes filled in; the JSON a drafting agent returns (each page's full text and rationale block);
and the checker command every drafting agent runs, `python3 <tools>/wiki.py check --root <root> --work <work>`.
The page map is every page under the wiki folder, every page in the Schema's Page professionals table, each Layout
section's folder note (`<NN Name>/<NN Name>.md`) and the pages briefed, each marked `exists` or `planned`. The
same inputs render the same bytes.

**`move`** moves pages (`{"20 Finance/Tax.md": "25 Tax & Duty/Tax & returns.md"}`) and rewrites every relative
link to or from a moved page, percent-encoded with `/` and `&` literal as `productivity:portable-markdown` sets
out (`../25%20Tax%20&%20Duty/Tax%20&%20returns.md`); links nothing moved under are left as written. It renames the
moved pages' rationale headings, removes the folders it empties, reports each moved page the Schema's Page
professionals table still names (edit the Schema, then compile), then lists every dead link left in the wiki;
either exits 1. It refuses a missing page, an existing or shared destination, a path outside the wiki and the
Schema page itself, before it changes anything. A swap (A to B and B to A) or a chain (A to B and B to C) is
refused as `destination exists`: make it in two runs, a swap through a temporary name (A to T and B to A, then T to
B) and a chain from its far end (B to C, then A to B). It also reports, and exits 1 for, each move that leaves the
Schema's Layout wrong (`layout_to_update`): a page moved out of every Layout section, or a section's folder note
moved away. Moved pages are written first, so a failure later in a run leaves no link to a page that was not
moved.

**`drift`** lists `[page, line, path]` for every `sources:` entry and every backticked path in a page body (fenced
blocks skipped) that cites a departed path (held by a departed entry and by nothing live) or a migrating one
(staged under the migrations folder, or the path it was staged from). The Log is history and is not read. Every
count is reported, zero included, and any citation exits 1. After `03 Home/Lease notes .txt` leaves the fixture
and a re-audit marks it departed:

    {"wiki": "Alex Personal Wiki", "pages_read": 11, "departed_paths": 1, "migrating_paths": 2,
     "citing_departed": 1, "citing_migrating": 0, "pages_citing": 1,
     "departed": [["30 Home/30 Home.md", 31, "03 Home/Lease notes .txt"]], "migrating": []}

## Charts: `wiki.py chart`

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
