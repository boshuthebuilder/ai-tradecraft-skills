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
| `wiki.py` | Evidence bundles, wiki checks, page moves with link rewriting, charts from cited rows |
| `readiness.py` | Hand-off readiness, including the hand-off contract |
| `common.py` | Shared: settings loading, guarded writes, package hash, JSON parsing, token estimate |

The package hash (sha256 over an iWork package's members in walk order, directories and files sorted, each member
contributing relative path, NUL, member sha256 hex, newline) is shared with any deployment that reads the manifest.

## Charts: `wiki.py chart`

    wiki.py chart --root <folder> --kind bar|line|pie|gantt|timeline --data <rows.csv|rows.json> --title <text>
                  [--out <file.md>]

Prints a fenced Mermaid block, a blank line, then its data table: the same rows, each with its source in backticks.
Both go into the page together, so the page cites the data its chart is drawn from; the same input always gives
the same bytes. `wiki.py check` counts every `xychart-beta`, `pie`, `gantt` and `timeline` block (`chart_blocks`)
and names each one whose next non-blank line does not start that table, with a backticked source on every row
(`charts_without_data_table`, page and line; each is a problem). The kinds offered are those the render probe,
[`../tests/probe/render-probe.md`](../tests/probe/render-probe.md), shows drawing in the apps the wiki is read in.

The data is a CSV file with a header row, or a JSON array of objects. Rows keep their order; every row has the
same columns, and no others.

| Kind | Mermaid | Columns |
| --- | --- | --- |
| `bar` | `xychart-beta`, one bar series | `label` or `period`, `value`, `unit`, `source` |
| `line` | `xychart-beta`, one line series | `period`, `value`, `unit`, `source` |
| `pie` | `pie` | `label`, `value`, `unit`, `source` |
| `gantt` | `gantt` | `label`, `start`, `end`, `source`; optional `section` |
| `timeline` | `timeline` | `date`, `label`, `source` |

Each rule is enforced; a breach exits 2 naming the row (counted from 1, the header not counted):

- Every row has a `source`: the folder-relative path of the file its figures come from, which must exist.
- A bar, line or pie series has at least three points (fewer figures belong in a sentence), none repeating a
  label or period.
- One unit or currency on every row. It labels the y-axis of a bar or line, and a pie's title must name it. A line's
  x-axis is its periods.
- Dates are `YYYY-MM-DD`: `start`, `end` and `date`, and any date inside a label, period or title. A gantt row may
  not end before it starts.
- Values are written exactly as given, never rounded, reformatted or reordered, so each is a plain decimal
  (`-?digits[.digits]`, no separators, symbols or exponent). A JSON number is read as its literal text: `1450.50`
  stays `1450.50`. A pie value is positive.
- No text holds what the chart or table cannot carry: `"`, a backtick, `|`, `#`, `;`, a control character or a
  space at either end; nor `:` in a gantt or timeline label or section.

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
