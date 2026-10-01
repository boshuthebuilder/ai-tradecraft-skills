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
| `wiki.py` | Folder profile, bundles, briefs, checks, rationale, review prompts, acceptance, moves, drift, charts |
| `readiness.py` | Hand-off readiness, including the hand-off contract ([below](#hand-off-readiness-readinesspy)) |
| `common.py` | Shared: settings loading, guarded writes, package hash, JSON parsing, token estimate |

The package hash (sha256 over an iWork package's members in walk order, directories and files sorted, each member
contributing relative path, NUL, member sha256 hex, newline) is shared with any deployment that reads the manifest.

## Building the wiki: `wiki.py` and the stage templates

The stages and who holds the pen at each are [`wiki-onboarding`](../../wiki-onboarding/SKILL.md)'s and
[the core wiki rule](../../wiki-maintenance/SKILL.md#the-core-wiki-rule)'s. A template in
[`templates/`](templates/) briefs each stage's author: `readers-interview.md`, `structure-brief.md` (the librarian),
`contract-brief.md` and `page-brief.md` (the page's professional), `review-owner.md` and `review-professional.md`.
Each opens with a comment naming its stage and who fills it: `wiki.py brief` renders the page brief and
`wiki.py review-prompts` the two review prompts, whole, dropping the comment; the coordinating agent fills the
others. Fields are in braces and doubled braces are literal, so each
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
what the Schema fixes filled in; the JSON a drafting agent returns (what `wiki-onboarding` step 4a names: each
page's full text, rationale block and Index entry, the agent's open questions and its check result);
and the checker command every drafting agent runs, `python3 <tools>/wiki.py check --root <root> --work <work>`.
The page map is every page under the wiki folder, every page in the Schema's Page professionals table, each Layout
section's folder note (`<NN Name>/<NN Name>.md`) and the pages briefed, each marked `exists` or `planned`. The
same inputs render the same bytes.

**`move`** moves pages (`{"20 Finance/Tax.md": "25 Tax & Duty/Tax & returns.md"}`) and rewrites every relative
link to or from a moved page, percent-encoded with `/` and `&` literal as `productivity:portable-markdown` sets
out (`../25%20Tax%20&%20Duty/Tax%20&%20returns.md`); links nothing moved under are left as written. It renames the
moved pages' rationale headings, removes the folders it empties, reports each moved page the Schema's Page
professionals table still names (edit the Schema, then compile), then lists every dead link left in the wiki;
either exits 1. It refuses, before it changes anything, a missing page, an existing or shared destination, one
under a file, one differing only in case from a page, another destination or a folder (a case-only rename of the
page itself stays possible where the file system allows it), a path outside the wiki and the Schema page itself.
Every destination is checked against the pages as they are before the run, so a swap (A to B and B to A) or a
chain (A to B and B to C) is refused as `destination exists`: make a swap in three runs through a temporary name
(A to T, then B to A, then T to B) and a chain in two from its far end (B to C, then A to B). It also reports, and
exits 1 for, each move that leaves the Schema's Layout wrong (`layout_to_update`): a page moved out of every Layout
section, or a section's folder note moved away.

A run writes every moved page at its destination, then rewrites the pages that link to them, and only then removes
the old pages. A failure part way therefore leaves every old page in place and every unmoved page's links resolving,
but a moved page already written may link to another moved page not yet written, and a rerun of the same map is
refused (`destination exists`). To recover, delete the pages the failed run wrote at the map's destinations, then
run the same map again.

**`drift`** lists `[page, line, path]` for every `sources:` entry and every backticked path in a page body (fenced
blocks skipped) that cites a departed path (held by a departed entry and by nothing live) or a migrating one
(staged under the migrations folder, or the path it was staged from). The Log is history and is not read. Every
count is reported, zero included, and any citation exits 1. After `03 Home/Lease notes .txt` leaves the fixture
and a re-audit marks it departed:

    {"wiki": "Alex Personal Wiki", "pages_read": 11, "departed_paths": 1, "migrating_paths": 2,
     "citing_departed": 1, "citing_migrating": 0, "pages_citing": 1,
     "departed": [["30 Home/30 Home.md", 31, "03 Home/Lease notes .txt"]], "migrating": []}

## Checking and accepting the wiki: `check`, `rationale`, `review-prompts`, `accept`

    wiki.py check          --root <folder> [--rationale <file.md>] [--acceptance <file.json>] [--out <file.json>]
    wiki.py rationale      --root <folder> --returns <dir|file.json> [--out <file.md>]
    wiki.py review-prompts --root <folder> --page <page> [--page <page> ...] --author-model <model>
                           --reviewer-model <model> [--sample 5] [--cards <dir>] [--out <dir>]
    wiki.py accept         --root <folder> --reply <file.json> --author-model <model> --reviewer-model <model>
                           [--date <YYYY-MM-DD>] [--out <file.json>]

Each also takes `--settings-dir`, `--work`, `--manifest` and `--read-only-root`. The rationale file and the
acceptance record are `wiki-maintenance`'s ([the rationale block](../../wiki-maintenance/SKILL.md#the-rationale-block)
and [acceptance](../../wiki-maintenance/SKILL.md#acceptance)); the formats below are these tools'.

**`check`** reads every page under the wiki folder (dot folders skipped) and prints JSON, exiting 1 when `problems`
is not zero. Every key is a count, a list whose length is the count, or a named state; the fixture's values are in
[`../tests/expected/wiki-check.json`](../tests/expected/wiki-check.json). `--rationale` and `--acceptance` read
those files from elsewhere; a path given that does not exist is refused (exit 2), while a default that does not
exist reads as `not recorded`. Line numbers count from the page's first line.

- `wiki`, `pages`: the wiki folder and its page count.
- `frontmatter_conforming` (`"12/12"`) and `frontmatter_bad`: pages carrying `provenance`, `last-updated` and
  `status`, and the pages that do not, or that write `sources:` as one value rather than a list.
  `superseded_pages` counts pages whose `status` is `superseded` (no problem).
- `dead_source_paths`, `[page, path]`: a `sources:` entry that does not exist, or a backticked span in a page body
  holding `/` (a file or a folder; a span wrapped onto the next line reads as one) whose first segment is a live
  top-level folder, one holding a live manifest entry or copy, and which does not exist. Such a span under any
  other first segment is counted in `backticked_paths_unchecked` (in the fixture, the Schema's `_Inbox/`). The
  Log's pages are history and are not read for paths.
- `dead_page_links`, `[page, link]`: a link to a `.md` that resolves to nothing. Which links are local is `move`'s
  rule (`local_link`: no scheme such as `http:`, `mailto:` or `obsidian:`, and not rooted at `/`), and a link with a
  title (`[Tax](Tax.md "t")`) is read as its target. A link to a page the page map only plans (as `brief` defines
  it) is dead until the page is written. `links_outside_page_map`, `[page, link]`: one that resolves to a file that
  is not a page of the wiki, such as the folder's `CLAUDE.md`.
- `em_dash_lines`, and the first ten as `em_dash_where`, `[page, line]`: body lines with an em dash outside inline
  code.
- `chart_blocks` and `charts_without_data_table`: chart pairing ([below](#charts-wikipy-chart)).
  `charts_not_renderable`, `[page, line, type]`: every Mermaid block that does not parse as a kind `chart` emits
  (its type is `pie`, `gantt` or `timeline`, or `xychart-beta` with exactly one `bar` or `line` series), a
  `flowchart` or `sequenceDiagram` included. Only the kinds verified to render in the owner's apps are allowed,
  pending the render spike (#96); a diagram the tool does not draw is written by hand and checked by nobody.
  `chart_sources_bad`, `[page, line, source]`: a paired chart's table row whose source `chart` would refuse:
  missing, resolving outside the folder, or under a reserved name. Those cells are checked there, not again as
  backticked paths.
- `deadlines`, `[date, page]`: every `deadlines:` entry in the pages' frontmatter (no problem).
- `documents_in_scope`, `documents_not_covered` and the first twenty as `not_covered_sample`: coverage. A live
  document outside the migrations folder is covered when a page names its path or a copy's (as `review-prompts`
  reads copies), in `sources:` or in backticks, or names its own parent folder in backticks, with or without the
  trailing `/` (`04 Study/` and `04 Study` cover `04 Study/Notes.rtf`, not `04 Study/Old/Notes.rtf`; a folder named
  without backticks covers nothing). The Schema page (its routing names folders to route them) and the Log do not
  cover.
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
  `acceptance_records_for_no_page`: acceptance, reported apart (below).
- `problems`: every finding above, summed. Acceptance is never part of it.

A rationale file, as `wiki-maintenance` defines it, is the line `# Wiki rationale`, then per page a heading
`### <page path>` followed at once by exactly five lines, `- Reader and use: `, `- Professional lens: `,
`- Shape: `, `- Changed from the previous page: ` and `- Left out or flagged: `, each with text after it; blank
lines go only between blocks. **`rationale`** writes that file from the drafters' returns (the JSON `brief` asks
for, each page with its `rationale` block): a `.json` file holding one return or a list of them, or a directory of
such files. It refuses (exit 2, nothing written) a malformed block, a block whose heading is not its entry's path,
and a page returned twice; otherwise it writes the whole file, pages sorted by path, so the same blocks give the
same bytes however they are grouped. The default output is `<root>/_Audit/wiki-rationale.md`; with
`--read-only-root`, write it elsewhere with `--out`. It prints `blocks`, `pages_without_block` and
`blocks_without_page`, exiting 1 when either list is not empty.

**`review-prompts`** renders, for each page, `templates/review-owner.md` (the contract's reader and questions, in
order, or for a `fixed` section a note that its shape is the method's) and `templates/review-professional.md` (the
page's professional, deliverable and tone, the contract, the section's routing, the documents and folders the page
cites, and a sample of facts from their cards), each carrying the page's text and sha256. They are working files,
written to `<out>/<page path without .md>.owner.md` and `.professional.md` (default `<work>/reviews/`) and refused
inside the folder; the same inputs render the same bytes. A reviewer model equal to the author model is refused.
The sample is fixed by rule, so a second review of a page checks the same facts: every non-empty date, amount and
reference number in the `key_facts` of the cards of the documents the page cites (in `sources:` or backticks, by
their path or a copy's), as `(the document's current path, kind, value)`, deduplicated and sorted. With `n` facts and
`--sample k`, all of them when `n <= k`; otherwise the facts at indices `(s + j * n // k) % n` for `j` from 0 to
`k - 1`, in index order, where `s` is the page path's sha256 read as an integer, modulo `n`: evenly spread over the
sorted facts, from an offset each page has its own.

**`accept`** records one verdict, for one page in one lens, in the acceptance record. It reads the reviewer's reply
(the JSON the review template asks for) after the coordinating agent has added a `response` to each finding, and
takes the models from `--author-model` and `--reviewer-model`. It refuses, exit 2 and nothing recorded: a page that
is not in the wiki; a lens other than `owner` or `professional`; a verdict other than `accepted` or `changes`; a
finding without its `where`, `finding` and `response`; `changes` without a finding; an `author` or `reviewer` in the
reply other than the flags; a `page_sha256` in the reply other than the page's now (the page changed after its
prompts were rendered); a page with no single professional (the record names it); and a `--date` that is not
`YYYY-MM-DD`, alone or followed by `T` and a valid time (`12:00`, `12:00:00`, with `Z`, `+0100` or `+01:00`). A
reviewer equal to the author, their names compared case-folded with spaces collapsed, is refused (exit 2) **and
recorded**, as `refused` with its reason, so the check reports it. The default record is
`<root>/_Audit/wiki-acceptance.json`; `--out` names another, read and added to alike.

How the record is written: `accept` takes an exclusive lock (`fcntl.flock`) on `<record>.lock`, created beside the
record and left there, reads the record, adds its one record and writes the whole file anew, to a temporary file
renamed over it, then releases the lock. Runs made at once therefore each keep their record, and no record is
changed or removed. A file system that cannot lock (some network shares) is refused, naming the lock: write the
record with `--out` on a local disk.

The acceptance record is JSON (UTF-8, indent 1, a final newline):

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

Records are kept in the order they were made. Each has, in this order, `page`, `lens` (`owner` or
`professional`), `verdict` (`accepted`, `changes` or `refused`), `sha256` (the page's when recorded),
`professional` (the page's then, from `common.page_voice`), `contract_sha256` (the sha256 of its section's compiled
contract then: the object `{reader, questions, fields}` from `wiki-schema.json`, the page contract as
`wiki-maintenance` defines it, or JSON `null` for a section without one, serialised with keys sorted, no spaces,
UTF-8; the section's list of professionals is left out, so naming another professional for another page of the
section changes no page's standing), `author_model` and `reviewer_model` (as
given, trimmed), `date` (`--date`, or the local time as `YYYY-MM-DDTHH:MM:SS+ZZZZ`) and `findings` (each `where`,
`finding` and `response`; other keys dropped), then `facts_checked` when the reply carries it (kept as given) and
`reason` on a refusal. A record of another shape, a record without `professional` or `contract_sha256` included,
fails loud in `check` and `accept`.

`check` reports each page's state from its latest record in each lens: `refused` when either lens's latest is a
refusal; `accepted` when both lenses' latest are `accepted` at the page's current sha256, under its current
professional and contract sha256; otherwise `not recorded`, with why (`no verdict recorded`, a lens with `no
verdict`, `changes asked`, `accepted an earlier version; the page changed since`, `accepted under an earlier
contract or professional`, or `accepted, but not verified: ` and why the page's professional cannot be read: the
Schema missing or stale, or the page without a single professional, as `pages_without_single_professional` says).
A page is accepted again after a change to its text, its contract or its professional, as the rule asks.
`acceptance_pages` lists `[page, state, why]`; `acceptance_counts` counts each state, zero included; `acceptance`
is `refused` when a page is, `accepted` when every page is, otherwise `not recorded`; `acceptance_not_verified`
lists, sorted, every page whose acceptance cannot be verified, recorded or not, because its professional and
contract cannot be read (no compiled Schema, a stale twin, or no single professional): read it rather than the
wording of the why text; `acceptance_records_for_no_page` lists the pages the record names that the wiki no longer
holds (moved or removed; their records stay as they were made). None of it counts as a problem or makes the check
pass, and a problem never unsets it.

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

## Repathing extract records: `extract.py repath`

    extract.py repath --root <folder> [--manifest <file>] [--out <extract dir>] [--apply]

Also takes `--settings-dir`, `--work` and `--read-only-root`. An extract record carries the path its document had
when it was read, so a curation round after extraction leaves it behind. Once the round's re-audit is proved,
`repath` rewrites each record's `path` to its document's `current_path` in the manifest, matched by content hash
(the record's id, its file name); nothing is read again, no model is called and nothing else in a record changes.
It is a dry run unless `--apply`, and writes through the guarded writer: with `--read-only-root`, `--apply` on
records inside the folder is refused before any is written (`--out` names records kept elsewhere). It prints
`records`, `applied`, `paths_changed`, `already_current`, `moves` (`[id, old path, new path]`), `departed_left`
and `not_in_manifest` (`[id, path]`: records of departed documents, and of ids the manifest does not hold, left
as they are), and exits 0. It refuses (exit 2, nothing written), naming each, any record whose document's paths
the manifest's canonical choice does not settle: no current path, copies naming no canonical copy, several, or one
other than the current path, or a current path another live entry holds; and a record whose `id` is not its file
name. Cards need no repair: they hold no path, only their document's id.

## Hand-off readiness: `readiness.py`

    readiness.py --root <folder> [--terms <file>] [--manifest <file>] [--out <file.json>]

Also takes `--settings-dir`, `--work` and `--read-only-root`. Read-only on the folder, it prints one JSON report
(also to `--out`, refused inside the folder with `--read-only-root`) and exits 0 when nothing is found, 1 on any
finding, and 2 on a tool error: a missing or malformed manifest, card, extract record or canary result, or a
crash, so 1 always means findings. The fixture's report is
[`../tests/expected/readiness.json`](../tests/expected/readiness.json).

Each check is a count, a state, `ok`, `finding: ...` or `not verified: ...`. `findings` lists every finding as
`[check, what]`, `check` being the report key that holds it; `not_verified` lists every named not-verified state
the same way, which is not a finding and not a pass either; `summary` counts both.

- `manifest`: the live, departed, migrating, root stray, redundant copy, hygiene and unconverted iWork counts and
  the items on disk, reported, not findings; `live_paths_missing` counts live entries whose current path is gone,
  a finding (the manifest is not current: re-audit).
- `records`, over the live documents `extract.py` reads (hashed ones): `missing_extracts`, `missing_cards`,
  `bad_category` (outside the rulebook's `card_categories`), `extract_paths_stale` (a record whose path is not the
  manifest's; the finding names the `extract.py repath` command that repairs it) and `contamination` (a card naming
  an isolation term its own source lacks, by `cards.py`'s rule; `not verified` without `--terms`). A count above
  zero is one finding.
- `isolation.canary`: per engine, the result `isolation.py canary --out` wrote to
  `<work>/state/canary-<engine>.json`: `passed`, `failed: ...` (a finding) or `not run: ...` (not verified).
- `wiki`: `wiki.py check`'s report ([above](#checking-and-accepting-the-wiki-check-rationale-review-prompts-accept)),
  reading the Schema from `--settings-dir`; its `problems` are one finding and its not-verified states are listed.
- `wiki_handoff`: `rationale_file`, a finding when `_Audit/wiki-rationale.md` is missing (`check` reports it
  `not recorded` without counting it, since drafting agents run `check` before the file is assembled);
  `pages_accepted`, `pages_not_accepted` and `pages_not_verified`: each page `check` does not report `accepted` is
  one finding naming the page, its state and why, a refused page included, except a page `check` lists in
  `acceptance_not_verified` (its professional and contract cannot be read, so its acceptance cannot be judged):
  those are counted and listed once as not verified, what keeps them unreadable (a missing or stale Schema twin,
  a page with no single professional) being a finding of its own.
- `rulebook`: `present`, `copies_identical` and `names_wiki_folder`. `scratch.left_in_audit`: folders in `_Audit/`
  other than `plans`, `extract` and `cards`.
- `handoff_contract`: `wiki_folder_named_after_folder`; `fixed_pages` (00 Index, 01 Deadlines, 90 Schema, 91 Log;
  numbered sections are `check`'s, where a page in no Layout section is a problem);
  `derived_pages_hold_nothing_hand_written` and `recurring_dates_in_frontmatter` (below);
  `rulebook_reserves_rulebook_filenames` (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`); `new_files_routed_within_folder`
  (no rulebook line routes new files to the migrations folder:
  [a project files within itself](../../wiki-maintenance/SKILL.md#rules-that-keep-it-safe));
  `settings_rulebook_json` and `settings_wiki_schema_json` (present and fresh).

**Derived pages.** The rule is `wiki-maintenance`'s *Deadlines are derived, not authored*
([rules that keep it safe](../../wiki-maintenance/SKILL.md#rules-that-keep-it-safe)), read through the keys its
roll-up reads ([canonical frontmatter][frontmatter]). It fixes no headings and asks for no list beyond the dates,
so readiness checks none. On `01 Deadlines`, every `YYYY-MM-DD` must be a page's `deadline` or `deadlines` date
(or fall on a page's `recurring` day), every such date of a page the sweeps read must be shown, and an empty
roll-up in a wiki of derived pages must say why (a page of headings or a bare "None" does not); every `MM-DD` must
be a page's `recurring` date, every `recurring` entry must read `{date: MM-DD, note}`, and every one must be
shown. Another page the Schema marks derived (an open-questions list) shows no date its sources would settle, so
it is named `not verified`.

[frontmatter]: ../../wiki-maintenance/SKILL.md#canonical-frontmatter--the-keys-the-deterministic-sweeps-read
