# Page brief: Alex Personal

This is the page-writing stage of
[the core wiki rule](<skills>/wiki-maintenance/SKILL.md#the-core-wiki-rule) in `wiki-maintenance`. **Pen:** you,
writing each page below as its professional, addressed to the owner, in that professional's voice
([one professional per page](<skills>/wiki-maintenance/SKILL.md#one-professional-per-page)). Next, the owner and
the professional accept each page, through a model that did not write it.

## The folder and its owner

The folder `Alex Personal`: Alex Example's personal papers: identity, money, home and language study.

People and organisations, each with the other names they appear under:

- Alex Example (also Alex, 亚历克斯): owner of this folder
- Robin Example (also Robin): Alex's partner
- Robin Trading Ltd: Alex's employer

Identifiers (`stated`): reference numbers written IN FULL exactly as in the document. Passwords and activation codes are never written, under any policy.

Boundaries inside the folder:

- none recorded

## Your pages

### 20 Finance/Cash position.md

- Status: exists (revise it)
- Section: 20 Finance, active
- Professional: CFO (the page's row in the Page professionals table)
- Deliverable: cash note
- Tone: numerate, brief
- Reader: Alex
- Questions, most important first:
  1. Is anything due?
  2. What came in and went out?
  3. What is the tax position?
- Fields every page carries: account, period, balances, tax year, amounts
- Files routed to the section:
  - `02 Finance/Tax/`: 20 Tax
  - `02 Finance/`: 20 Bank accounts and Cash position
  - `06 Work/`: 20 Tax (employment income)
- Bundle: `<tmp>/a/work/bundles/bundle_20.jsonl` (6 documents)

### 20 Finance/Tax.md

- Status: exists (revise it)
- Section: 20 Finance, active
- Professional: chartered tax adviser (the page's row in the Page professionals table)
- Deliverable: annual tax position letter
- Tone: exact, dated
- Reader: Alex
- Questions, most important first:
  1. Is anything due?
  2. What came in and went out?
  3. What is the tax position?
- Fields every page carries: account, period, balances, tax year, amounts
- Files routed to the section:
  - `02 Finance/Tax/`: 20 Tax
  - `02 Finance/`: 20 Bank accounts and Cash position
  - `06 Work/`: 20 Tax (employment income)
- Bundle: `<tmp>/a/work/bundles/bundle_20.jsonl` (6 documents)

## The page map

Every page that exists or is planned. Link only to these pages, by relative path encoded as
`productivity:portable-markdown` sets out (spaces as `%20`, `&` literal).

- `00 Index/00 Index.md` (exists)
- `01 Deadlines/01 Deadlines.md` (exists)
- `02 People/02 People.md` (exists)
- `10 Identity/10 Identity.md` (exists)
- `20 Finance/20 Finance.md` (exists)
- `20 Finance/Bank accounts.md` (exists)
- `20 Finance/Cash position.md` (exists, in this brief)
- `20 Finance/Tax.md` (exists, in this brief)
- `30 Home/30 Home.md` (exists)
- `40 Study/40 Study.md` (exists)
- `90 Schema/90 Schema.md` (exists)
- `91 Log/91 Log.md` (exists)

## Evidence

The bundles in `<tmp>/a/work/bundles` hold one JSON line per document routed to a section: its path, copies, card
(title, type, parties, date, summary, key facts) and, for an active section, its text. They were checked fresh
against the current manifest and routing before this brief was made. Open a source file itself when a bundle line
is not enough.

## What you may read

This brief, the Schema page, the core wiki rule, the bundles above and the source files they list or your pages
cite. Read nothing else: not the manifest or `AUDIT.md`, nothing else under `_Audit/`, and nothing outside this
folder.

## What to do

1. Read the Schema page, `<tmp>/a/Alex Personal/Alex Personal Wiki/90 Schema/90 Schema.md`, and the core wiki rule: its page contracts, rich pages, outside
   knowledge and history pages are how each page is written.
2. Write each page to its path under `<tmp>/a/Alex Personal/Alex Personal Wiki/`, to its contract and in its professional's voice. Draw any
   chart with `wiki.py chart`, from the page's own cited rows.
3. Run the checker, scoped to your pages, and fix every finding it names. A link to a page the map plans but
   nobody has written yet is listed as pending, not dead; coverage is judged later, over the whole wiki:

       python3 <skills>/pre-onboarding/tools/wiki.py check --root '<tmp>/a/Alex Personal' --work <tmp>/a/work --page '20 Finance/Cash position.md' --page '20 Finance/Tax.md'

4. Fill each page's rationale block (below).
5. Reply with JSON only, in this shape: per page its text, rationale block and Index entry; then your open
   questions and the checker's result.

```json
{
 "pages": [
  {
   "path": "20 Finance/Cash position.md",
   "text": "<the page exactly as written to the wiki folder, frontmatter first>",
   "rationale": "<its rationale block: the heading and five lines given below, joined by \\n>",
   "index_entry": "<the page's line in the Index: what it holds, in a few words>"
  },
  {
   "path": "20 Finance/Tax.md",
   "text": "<the page exactly as written to the wiki folder, frontmatter first>",
   "rationale": "<its rationale block: the heading and five lines given below, joined by \\n>",
   "index_entry": "<the page's line in the Index: what it holds, in a few words>"
  }
 ],
 "open_questions": [
  "<for the owner or the coordinating agent: a gap, sources that disagree, a dated rule left unchecked, a page the evidence shows is missing>"
 ],
 "check_result": {
  "problems": 0,
  "links_to_planned_pages": [
   "<a link to a page the map plans but nobody has written yet>"
  ]
 }
}
```

## What the checks read

The checker, and later the hand-off check, read every page as plain text, so write to these rules:

- **No em dash** in the body outside inline code. A source title, supplier name or menu name that holds one goes
  inside backticks; elsewhere use a comma, a colon or two sentences.
- **Frontmatter** is plain `key: value` pairs at the left edge between `---` fences. Quote every `note` and
  `deadline_note`: an unquoted value with a colon and a space in it, a bare `yes`, `no`, `on` or `off`, or a time such
  as `12:30` is read as something other than text, and the page cannot be verified.
- **Dates.** A forward date goes in `deadlines:` as `YYYY-MM-DD`, or as a date with a quoted note. A date that comes
  round every year goes in `recurring:`, written as the day and the month name in full: a reader who writes the day
  first reads it right, where `04-05` reads either way round.

```yaml
deadlines:
  - date: 2026-04-05
    note: "VAT return due"
recurring:
  - date: 5 April
    note: "Year end for the accounts"
```

## The rationale blocks

One per page, kept in `_Audit/wiki-rationale.md`: the heading, then exactly five lines. What the Schema fixes is
filled in; replace each part in angle brackets.

### 20 Finance/Cash position.md
- Reader and use: Alex, <what they use the page for>
- Professional lens: CFO; questions answered in order: 1. Is anything due? 2. What came in and went out? 3. What is the tax position?
- Shape: <the page's structure and visuals and why, or "as the Schema sets out">
- Changed from the previous page: <what this version changed>
- Left out or flagged: <what was left out and why, and what was flagged for the owner, or "nothing">

### 20 Finance/Tax.md
- Reader and use: Alex, <what they use the page for>
- Professional lens: chartered tax adviser; questions answered in order: 1. Is anything due? 2. What came in and went out? 3. What is the tax position?
- Shape: <the page's structure and visuals and why, or "as the Schema sets out">
- Changed from the previous page: <what this version changed>
- Left out or flagged: <what was left out and why, and what was flagged for the owner, or "nothing">
