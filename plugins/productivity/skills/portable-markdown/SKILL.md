---
name: portable-markdown
description: >-
  Generate markdown files a person will actually open in a desktop editor — Typora, Obsidian, or a plain
  viewer — so the links land and no raw markup shows. Covers the link policy (a name that names a document
  should open it), destination encoding for spaces, brackets and CJK, anchors that render invisibly, table
  cells that survive model-written text, and HTML escaping inside inline elements. Use when a program or
  agent WRITES markdown for someone else to read: an audit or report over a folder of files, a generated
  index, a wiki page, a handover doc. Triggers include "the links don't work in Typora", "renders wrong in
  Obsidian", "markdown link with spaces or Chinese characters", "raw HTML showing in my markdown", "linking
  to a heading", and any task that emits .md a human opens rather than a browser renders.
---

# Portable markdown

A generated markdown file has two audiences: a renderer and a person. The trap is that "the renderer" is
not one renderer — the same file is opened in Typora, in Obsidian, and in whatever previews it in a
terminal or on GitHub, and their behaviour diverges in exactly the places generated documents lean on:
links, anchors, tables and inline HTML.

This skill is the set of rules that survive all of them, and the method for settling a question none of
them document. The verified behaviour matrix is in [`REFERENCE.md`](REFERENCE.md).

## The rule that prevents most of the damage

**A link's destination follows from what the link is FOR — and a name that names a document should open
that document.**

This sounds obvious and is the single most common defect in generated markdown, because the author is
thinking about document structure while the reader is thinking about the file. A summary table listing
"what happened to each of your files" exists to hand over documents; if its names jump to a section
further down the same page instead, every click is a small betrayal and the reader reports it as *the
links are broken*. They are not broken. They point at the wrong thing.

Split it by purpose:

| the link is… | destination |
|---|---|
| a name in a summary table, index, or list of documents | **the file** |
| a cross-reference inside an entry ("see the related entry", "merged from") | **in-document anchor** |
| a heading that titles a document's entry | **the file** (see *Anchors*) |

The file link is also the only form both Obsidian's and Typora's own help documents. Prefer it; treat the
in-document anchor as the extra you verified.

## The vault boundary — the one thing no amount of syntax fixes

**Obsidian resolves every path from the vault root and cannot follow a link that escapes it.** Its
help states it plainly — "Folder paths start at the vault root" — and driving it confirms there is no
graceful degradation: a relative link out of the vault throws
`Cannot read properties of null (reading 'getParentPrefix')`, and one that looks like a note path
makes Obsidian try to **create** it instead.

This matters because the natural layout puts the generated document *inside* a folder and the files it
describes *beside* that folder:

```
Project/
├── Wiki/          ← the vault, and where your generated pages live
└── Documents/     ← what those pages cite:  ../../Documents/x.pdf
```

Every such link works in Typora, which resolves on the filesystem, and is dead in Obsidian. No
encoding, extension or escaping changes that — it is a property of **where the vault is rooted**, not
of the page. So it is a decision before it is a defect, and there are exactly two resolutions:

| | what you get | what it costs |
|---|---|---|
| **Root the vault at the parent** (`Project/`) | every existing link works, in both editors and on mobile; no content changes at all | the vault now contains the documents — file tree, search and the "open note" list fill with them |
| **Keep the vault, and NAME instead of link** — state the path in backticks, link only to other notes in the vault | the vault stays a vault; works in every editor and on mobile | clicks become copies: the reader sees the path and opens it themselves |

The deciding number is usually **how much lives beside the vault**. In the case this skill came from,
rooting at the parent would have taken the vault from 28 indexed notes to 42 — but dragged **1,585
PDFs** and every household folder into the file tree, so the owner chose to keep the vault and name
the paths.

**If you choose to name rather than link, `outside_vault` becomes a repairable defect** and your
generator should report it as one. Before that choice it must NOT be — folding it in early invites a
mass rewrite of working links to satisfy a setting nobody has chosen. Report it as a named count until
the decision exists, then flip it.

Two things make the conversion cheap, and are worth checking before you dread it:

- These links almost always carry the path as their own **link text** already
  (`[Marriage/Ceremony/](../../Marriage/Ceremony/)`), so `` `Marriage/Ceremony/` `` loses nothing.
- It retires most of your encoding defects **by construction**. Every one of the `%26` failures in
  that wiki was on a link that escaped the vault; a rule that stops linking out stops producing them.

### The plugin route, and why it is not a free win

Obsidian community plugins *can* reach outside the vault — the one encountered here,
`external-file-embed-and-link`, describes itself as exactly that. Read its code before adopting it:
it registers **code-block processors** (`LinkRelativeToVault`, `EmbedRelativeToHome`, …), so a link is

````
```LinkRelativeToVault
../Health & Medical/report.pdf
```
````

which is not a markdown link. Typora renders it as a literal code block, and its manifest declares
`isDesktopOnly: true`, so mobile loses it. For a **generated** document that has to survive several
readers, that trades one editor for another. For hand-written notes in a single desktop Obsidian, it
is a reasonable choice.

Symlinking the documents into the vault is the other tempting escape. Check what your own tooling does
with symlinks first: in the deployment this came from, every wiki sweep resolves each page and skips
any whose real path escapes the vault root, so symlinked content would have been silently invisible to
the orphan, freshness and link checks — a visible problem traded for a quiet one.

## Link destinations

**URL-encode the destination.** Obsidian's help is explicit — "make sure to URL encode the link
destination. For example, blank spaces become `%20`" — and Typora resolves the same. In Python:

```python
from urllib.parse import quote
quote(relative_path, safe="/&")    # spaces → %20, ( ) → %28 %29, CJK → encoded; & stays LITERAL
```

**The ampersand is the exception, and it is the one that bites.** Neither Typora nor Obsidian decodes
`%26` when opening a local file — though both decode `%20` and CJK **in the same destination**, which
is what makes it so quiet. The link looks correctly encoded, and is, and opens nothing:

| destination | Typora 1.14.9 | Obsidian 1.12.7 |
|---|---|---|
| `…%20%26%20…` | "Cannot open location …", offers it as an `https://` URL | does not open — **creates** a stray note and a `Health %26 Medical` folder |
| `…%20&%20…` | opens the file | opens the file |

True for a markdown link and an HTML `<a href>` alike, so no form rescues `%26`. Obsidian's failure is
the worse one: the click *writes* into the vault rather than reporting anything. Filenames carrying `&`
are ordinary — "Brand Concept & Development Plan", "Health & Medical", "Teaware & Mino Ware" — so this
is not an edge case, it is a whole class of link silently dead.

**Encoding the brackets is load-bearing, not cosmetic.** Most tooling parses a link destination as
`[^)]+` — including link linters you may already run — so a raw `)` inside a filename silently truncates
the destination. Filenames written by humans and scanners contain `(1)`, `& Co`, `#2` constantly.

**Keep the file extension.** Obsidian: "Links to file formats other than Markdown needs to include a file
extension."

**Relative destinations, resolved from the file's own folder.** If your document is nested (a dated run
folder, a subdirectory index), state the depth as a deliberate constant with a comment, not an accident —
and note that a path stored relative to a *different* root has to be rebased before it becomes a link.

## Anchors

If you need in-document targets — cross-references between entries — you need an id per entry. Three
constraints collide:

1. **An empty `<a id="x"></a>` renders as literal visible text in Typora.** Not invisible, not ignored:
   the reader sees `<a id="doc-4b1671ff4451"></a>` in front of every heading. Putting it on its own line
   is no better; it becomes a grey HTML block.
2. **A slug of the heading text is not portable.** Typora lowercases and hyphenates; Obsidian matches
   literal heading text via `[[Note#Heading]]` wikilinks; GitHub has its own slugger and its own
   duplicate-disambiguation order. Long, CJK-heavy, punctuation-heavy headings — exactly what filenames
   produce — diverge between all three, and two folders can hold the same basename.
3. **Custom heading id syntax (`{#id}`) is documented by neither**, though Typora happens to consume it.

What works: **one element carrying both the id and the href**, wrapping the visible text.

```markdown
### <a id="doc-4b1671ff4451" href="Design/ALWAYSFLOW%20-%20Price%20List.pdf">ALWAYSFLOW - Price List.pdf</a>
```

An `<a>` **with content** renders only its content, in Typora and in any CommonMark renderer, while still
providing the target that `[name](#doc-4b1671ff4451)` resolves against. Where there is no file to open
(the target is gone), keep the element and drop the `href` — never emit an empty one.

Mint the id from a **stable identity you already have** — a content hash, a record id — not from the
title. Twelve hex characters is collision-free at any realistic scale and is ASCII, so no renderer has to
agree with you about slugging.

**Assert that no empty anchor survives.** `assert "></a>" not in rendered` is one line and catches the
exact regression.

## Text inside an inline element must be HTML-escaped

The moment a name sits inside `<a>…</a>` it is HTML, not markdown text. `html.escape()` it. Filenames
carry `&` constantly ("Goldfish & Cruise Ship", "Teaware & Mino Ware") and an unescaped one is at best
wrong and at worst breaks the element.

**An attribute value is HTML too.** Since the destination now keeps its `&` literal, the `href` must be
HTML-escaped as well, so that `&` becomes `&amp;` — an attribute is where a bare `&` opens a character
reference. That is *three* escapings in one element, each for a different position:

```python
f'<a id="{anchor_id}" href="{escape(href(target), quote=True)}">{escape(text)}</a>'
#         ^ ascii id           ^ percent-encoded, then entity-escaped   ^ entity-escaped
```

`&amp;` in the attribute is the form verified to open the file. None of the three substitutes for
another, and dropping the middle one is invisible until someone clicks a filename with an `&` in it.

## Tables

- **Escape pipes** in any cell text you did not write yourself. Obsidian documents `\|`. A `|` inside a
  model-written sentence or a filename breaks the ROW rather than erroring, silently swallowing the
  remaining columns.
- **Collapse newlines** in cell text for the same reason.
- Both apply to *any* text you did not author: model output, filenames, user notes.

```python
def table_cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")
```

## Charts and callouts

Both editors draw Mermaid charts from a fenced ` ```mermaid ` block, and both bundle the same
Mermaid release (11.13.0 in Obsidian 1.13.7 and Typora 1.14.10). Every kind a page needs for its data
renders with that library: `xychart-beta` bars and lines, `pie`, `gantt` and `timeline`. That was checked by
running each editor's own copy of the library in a browser, not by opening the page in the applications, so
treat it as expected rather than confirmed until someone opens the probe page (see the REFERENCE) in both
apps. Two things are known to differ, read from Typora's own source:

- **Typora draws a diagram only with its Diagrams preference on** (Preferences, Markdown, Syntax
  Support, Diagrams), and Typora applies that panel's settings only after a restart. Its documented
  default is off, and with it off a chart shows as its source code.
  Tell a Typora reader to turn it on once and restart Typora. A chart must therefore never be the only place its data
  lives: keep the table it was drawn from beside it, so the page reads the same with the chart off.
- **Callouts: use only the five GitHub alert types**, `> [!note]`, `> [!tip]`, `> [!important]`,
  `> [!warning]` and `> [!caution]`. Obsidian draws its own wider set (`info`, `todo`, `danger` and so
  on), but Typora boxes only these five (its "GitHub Style Alert" option, on by default) and shows any
  other as a plain quotation with the marker printed. **Write the marker alone on its line** and any
  title in bold on the next line: Typora hides the marker only when nothing follows it on its line, and
  otherwise prints `[!note] Title` as text inside the box; Obsidian shows its default title.

Generate chart blocks with a renderer rather than by hand, so the same data always gives the same
block. Whenever either editor moves a major version, reopen the probe page in both apps, the method below,
which also settles what this pass could only infer from each editor's library and source.

## Keep the render a pure function

If the document is regenerated — an audit, an index, a dashboard page — make the renderer a pure function
of its data, with no clock and no filesystem probing, and stamp it from the data's own timestamp rather
than `now()`. Then an unchanged input renders byte-identical, which is what lets you detect a hand-edited
or deleted file and heal it without rewriting an intact one on every run. A single `datetime.now()` in the
header destroys that property.

## The method: verify by driving the editor

**None of the behaviour above is fully documented by either editor.** Typora's reference does not mention
custom heading ids; Obsidian's help covers only `&nbsp;` and `<br>` for HTML. So the honest way to settle
a question is a probe document, opened in the real application, clicked.

Write one markdown file containing the same destination in every form and context you are considering —
paragraph, list item, table cell, heading; markdown link and HTML anchor; encoded and raw — plus a target
that says plainly when it has been reached. Then open it and click each one. Ten minutes of this beats any
amount of reasoning about what *should* work, and it is the only way to catch the asymmetries: a construct
that renders correctly but does not navigate, or navigates but shows raw markup.

Two failure modes this catches that reading cannot:

- **A change that fixes rendering and breaks behaviour.** Moving a heading's file link out of a markdown
  link and into an HTML `href` can render more cleanly and still open the file — but you only know that
  because you clicked it, and if you verified only the rendering you shipped a regression.
- **A defect that is neither the format nor the setup.** Before blaming an editor's configuration, count
  what your document actually contains. "The links don't work" turned out, in the case this skill came
  from, to be 657 in-document anchors versus 177 file links: every link the reader clicked was doing
  exactly what it was told, and what it was told was wrong.

## Checklist

Before shipping a generator that writes markdown for a person:

- [ ] Every name that names a document links to **the document**, not to a section about it
- [ ] Destinations percent-encoded with `safe="/&"`; **`&` left literal**; brackets encoded; extension present
- [ ] Inside an HTML attribute the href is entity-escaped too, so the `&` reads `&amp;`
- [ ] No empty `<a></a>` anywhere — asserted in a test
- [ ] Ids minted from a stable identity, not from the title
- [ ] Text inside an inline element HTML-escaped; hrefs percent-encoded
- [ ] Table cells: pipes escaped, newlines collapsed, for any text you did not author
- [ ] Render is a pure function of its data — no clock, no filesystem
- [ ] Each chart has its data table beside it; callouts use only `note`, `tip`, `important`, `warning`, `caution`
- [ ] Opened the real output in the editor the reader uses, and **clicked the links**

## Provenance

Charts and callouts checked 2026-10 for **Obsidian 1.13.7** and **Typora 1.14.10** (macOS) by rendering each
editor's own bundled Mermaid in a browser harness and reading Typora's switches from its source, not by driving
the editors (see the REFERENCE for what that does and does not prove); link rules
verified 2026-08 against **Typora 1.14.9** (macOS) and the published help for both editors
([support.typora.io](https://support.typora.io/), [obsidian.md/help](https://obsidian.md/help/)). The
per-construct results, including which forms navigate and which only render, are in
[`REFERENCE.md`](REFERENCE.md). Re-verify after a major version of either editor: several of these
behaviours are undocumented and can therefore change without a note.
