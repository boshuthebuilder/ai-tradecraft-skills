<!-- Stage 4, writing the pages. Rendered by `wiki.py brief`, which fills every field in braces and drops this
comment; doubled braces are literal. -->
# Page brief: {folder_name}

This is the page-writing stage of
[the core wiki rule](../../../wiki-maintenance/SKILL.md#the-core-wiki-rule) in `wiki-maintenance`. **Pen:** you,
writing each page below as its professional, addressed to the owner, in that professional's voice
([one professional per page](../../../wiki-maintenance/SKILL.md#one-professional-per-page)). Next, the owner and
the professional accept each page, through a model that did not write it.

## The folder and its owner

{owner_context}

## Your pages

{pages}

## The page map

Every page that exists or is planned. Link only to these pages, by relative path encoded as
`productivity:portable-markdown` sets out (spaces as `%20`, `&` literal).

{page_map}

## Evidence

The bundles in `{bundles_dir}` hold one JSON line per document routed to a section: its path, copies, card
(title, type, parties, date, summary, key facts) and, for an active section, its text. They were checked fresh
against the current manifest and routing before this brief was made. Open a source file itself when a bundle line
is not enough.

## What you may read

This brief, the Schema page, the core wiki rule, the bundles above and the source files they list or your pages
cite. Read nothing else: not the manifest or `AUDIT.md`, nothing else under `_Audit/`, and nothing outside this
folder.

## What to do

1. Read the Schema page, `{schema_path}`, and the core wiki rule: its page contracts, rich pages, outside
   knowledge and history pages are how each page is written.
2. Write each page to its path under `{wiki_dir}/`, to its contract and in its professional's voice. Draw any
   chart with `wiki.py chart`, from the page's own cited rows.
3. Run the checker, scoped to your pages, and fix every finding it names. A link to a page the map plans but
   nobody has written yet is listed as pending, not dead; coverage is judged later, over the whole wiki:

       {checker}

4. Fill each page's rationale block (below).
5. Reply with JSON only, in this shape: per page its text, rationale block and Index entry; then your open
   questions and the checker's result.

```json
{return_shape}
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

{rationale}
