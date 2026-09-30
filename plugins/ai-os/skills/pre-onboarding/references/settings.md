# The settings twins

A folder carries its own rules in two human-written sources: its rulebook (`CLAUDE.md`, with a byte-identical
`AGENTS.md`) and its wiki's Schema page. Tools and the deployment cannot read prose reliably, so each source has a
machine-readable **twin** in `<folder>/.familyai/` (or wherever `--settings-dir` points):

| Twin | Source | Made by |
| --- | --- | --- |
| `rulebook.json` | `CLAUDE.md` | the preparing agent, from the owner's interview answers, in the same change as the rulebook |
| `wiki-schema.json` | `<folder name> Wiki/90 Schema/90 Schema.md` | `tools/settings.py compile`, never by hand |

The source is the authority; the twin is what code reads. Each twin records its source's sha256, so an edited
source makes the twin **stale**, never silently wrong. Every tool refuses a stale twin before it reads or writes
anything.

## `rulebook.json`

One JSON object. `version` and `rulebook_sha256` are required; every other key falls back to the default shown.
An unknown version, an unknown key or a value of the wrong shape fails loud.

| Key | Value | Default | Meaning |
| --- | --- | --- | --- |
| `version` | `1` | required | the format version of `rulebook.json` |
| `rulebook_sha256` | sha256 hex | required | the sha256 of `CLAUDE.md` when this twin was last reviewed against it; absent or empty means unpinned |
| `inbox` | folder name | `_Inbox` | the drop point at the top of the folder |
| `migrations_dir` | folder name | `_Migrations` | where files the owner approved for another project wait |
| `wiki_dir` | folder name | `<folder name> Wiki` | the wiki folder; must be exactly `<folder name> Wiki` |
| `reserved` | list of names | `[]` | top-level names reserved beyond the fixed set below |
| `depth` | `light`, `medium` or `full` | `light` | the reorganisation depth the owner chose (`folder-curation`'s ladder) |
| `packs` | list of folder paths | `[]` | submission records, whose copies are never deleted |
| `working_formats` | list of extensions | `[]` | formats the owner keeps working in, such as `.pages` |
| `active`, `finished` | lists of folder paths | `[]` | live matters, and closed matters ingested once as history |
| `people` | list of `{name, also, who}` | `[]` | each person or organisation: canonical name, every other name or script it appears under, and one line on who they are |
| `identifiers` | `stated`, `last-four` or `home-only` | `stated` | `wiki-maintenance`'s identifier policy: reference numbers in full unless the owner restricts them; passwords are never written under any policy |
| `boundaries` | list | `[]` | access boundaries inside the folder, as the owner described them |
| `card_categories` | list of names | a generic set | the categories a document card may carry |
| `folder_description` | text | `""` | one line on what the folder holds, for the card engine's brief |
| `exclude` | list of paths | `[]` | paths the owner excluded from reading |
| `keep_empty_folders` | `true` or `false` | `true` | whether emptied folders stay |
| `image_cap_mb`, `pack_keywords` | number, list of patterns | `25`, a generic list | audit tunables; rarely set |

**Reserved names.** The rulebook must name every top-level name the system reserves: `CLAUDE.md`, `AGENTS.md`,
`GEMINI.md`, `.familyai`, `_Audit`, the inbox, the migrations folder, the wiki folder, then anything in `reserved`.

**Pinning.** Once the owner has agreed the rulebook, write the twin from it and record the rulebook's hash
(`shasum -a 256 CLAUDE.md`) as `rulebook_sha256`. The pin records a review, not only a hash: after any edit to the
rulebook, read the change, bring the twin into line with it, then record the new hash. Re-pinning without that
review defeats the point.

## `wiki-schema.json`

### The Schema page's tables

`settings.py compile --root <folder>` reads four tables from the Schema page (`90 Schema/90 Schema.md` in the wiki
folder; `09 Schema/09 Schema.md` is read for a wiki laid out before the meta pages moved to the 90s). Each is the
one table under a `## ` heading of its name (a remark in brackets or after a colon may follow, as in
`## Layout (sections)`), with every row starting with `|`; tables in fenced code are ignored, and the page may carry
any other sections and tables. Headers are fixed, word for word:

| Table | Headers | Required |
| --- | --- | --- |
| Layout | `Section \| Pages \| Professional lens \| Kind` | yes |
| Routing | `Files under \| Section and page` | yes |
| Page contracts | `Section (professional) \| Reader \| Questions, most important first \| Fields every page carries` | yes |
| Page professionals | `Page \| Professional \| Deliverable \| Tone` | no |

A Page contracts table written before the Reader column (`Section (professional) \| Questions, most important
first \| Fields every page carries`) still compiles, with no reader; `check` reports it until the column is added.

What each cell holds:

- **Section** (Layout): a two-digit number, a space and the name, such as `20 Finance`; each number once.
  **Professional lens**: one professional, or several separated by `;`. **Kind**: `active`, `history` or `fixed`,
  optionally followed by `, derived` for a page generated from other pages that holds nothing hand-written.
- **Files under** (Routing): one or more folder prefixes, each in backticks and ending in `/`; each prefix routed
  once. **Section and page**: starts with the target section's two-digit number and a space, or is a note with no
  number, which routes nothing (`_Inbox/`, filed by the routing above).
- **Section (professional)** (Page contracts): a Layout section by number and name, with its professionals in
  brackets (left out, the Layout's are used); one contract per section. **Reader**: who reads these pages.
  **Questions**: numbered `1. … 2. …` from the start of the cell, in priority order (a single question is `1. …`
  too). **Fields**: the fields every page carries, separated by commas.
- **Page** (Page professionals): a page path relative to the wiki folder, under a Layout section, such as
  `20 Finance/Tax.md`; each page once. **Deliverable** and **Tone**: what the professional produces and how it
  reads.

A different header, a second table under one heading, a missing required table or a row that cannot be read as
above fails loud, naming the table and the row. Nothing is guessed.

```markdown
## Layout

| Section | Pages | Professional lens | Kind |
| --- | --- | --- | --- |
| 01 Deadlines | every forward date, rolled up | chief of staff | fixed, derived |
| 20 Finance | Bank accounts; Tax | private banker; chartered tax adviser | active |

## Routing

| Files under | Section and page |
| --- | --- |
| `02 Finance/Tax/` | 20 Tax |
| `02 Finance/`, `06 Work/` | 20 Bank accounts |

## Page contracts

| Section (professional) | Reader | Questions, most important first | Fields every page carries |
| --- | --- | --- | --- |
| 20 Finance (private banker; chartered tax adviser) | Alex | 1. Is anything due? 2. What is the tax position? | account, period, tax year, amounts |

## Page professionals

| Page | Professional | Deliverable | Tone |
| --- | --- | --- | --- |
| 20 Finance/Tax.md | chartered tax adviser | annual tax position letter | exact, dated |
```

### The compiled twin

Compilation is deterministic: the same Schema bytes give the same twin bytes, with no timestamp and paths relative
to the folder, so recompiling an unchanged Schema changes nothing. Tools check the twin's version and shape when
they read it, so a twin of another version or shape is refused as invalid rather than tripped over.

| Key | Value |
| --- | --- |
| `version` | `2` (version 1, compiled before sections carried a number and a name, is refused: recompile) |
| `schema_path` | the Schema page, relative to the folder |
| `schema_sha256` | the Schema page's sha256 when compiled |
| `sections` | Layout rows in order: `{number, name, kind, derived, pages, professionals}` |
| `routing` | one row per prefix, in table order: `{prefix, target, section}` (`section` is `null` for a note); a path routes by its longest matching prefix |
| `contracts` | `{number, name, professionals, reader, questions, fields}`, questions and fields as lists in order; `reader` is `null` from a table without the Reader column |
| `pages` | `{"<section>/<page>.md": {professional, deliverable, tone}}` |

### A page's professional

A page is written in the voice of one professional (tone only; facts, sources and format rules do not change):
its row in Page professionals when it has one; otherwise its section's professional, when the section names
exactly one. A page in a section that names several must be listed: `common.page_voice`, the one reading of this
rule, refuses it rather than pick one. Deliverable and tone come only from the page's own row.

## Stale twins

| What happened | State | Remedy |
| --- | --- | --- |
| `CLAUDE.md` edited since the pin | `stale` | review `rulebook.json` against it, then record the new hash |
| `rulebook.json` has no or an empty `rulebook_sha256` | `unpinned` | review it against `CLAUDE.md`, then record the hash |
| `CLAUDE.md` missing | `stale` | restore the rulebook |
| the Schema page edited since compiling | `stale` | `settings.py compile --root <folder>` |
| the Schema page moved or deleted | `stale` | restore it, then compile |
| a `90 Schema` page added to a wiki compiled from `09 Schema` | `stale` | `settings.py compile --root <folder>` |

Every tool that takes `--root` verifies both twins before it reads or writes anything, and refuses (exit 2),
printing `error: stale: …` or `error: unpinned: …` naming the source; a malformed twin is refused the same way.
Two skip that gate and report instead. `settings.py`: `compile` is the remedy (it still refuses a stale
`rulebook.json`, whose `wiki_dir` it reads) and `check` is the diagnosis. `readiness.py` reports a stale or unpinned
twin as a hand-off finding (exit 1), reading the settings without trusting them, as `check` does.

An absent twin is not stale: a folder has no `wiki-schema.json` before its wiki exists, and tools fall back to the
defaults without a `rulebook.json`. The tools that need a twin (`settings.py check`, `wiki.py bundles`, the
hand-off contract in `readiness.py`) say so.

## `settings.py check`

Prints `{"status": …, "findings": […], "count": n}` (also to `--out` when given) and exits 1 on any finding. One
defect gives one finding. It checks:

- both twins are present and fresh (`status.rulebook_json`, `status.wiki_schema_json`: `fresh`, `stale`,
  `unpinned`, `missing` or `invalid`);
- `wiki_dir` is `<folder name> Wiki`;
- the rulebook's text (valid UTF-8) names every reserved name, with the wiki folder as `<folder name> Wiki`, and
  every pack path;
- `CLAUDE.md` and `AGENTS.md` are byte-identical;
- the twin was compiled from a Schema inside the wiki folder;
- the Page contracts table has its Reader column;
- every section that is not `fixed` has a page contract.

These are the facts code can hold. Whether the rest of `rulebook.json` says what the rulebook's prose says is the
review that pinning records.
