# Verified behaviour matrix

Everything here was **driven in the application**, not read from documentation, because most of it is
undocumented. Where the vendors *do* state a rule it is quoted and attributed.

Verified 2026-08-06 against **Typora 1.14.9** on macOS 15. Obsidian rows marked *documented* come from
[obsidian.md/help](https://obsidian.md/help/); Obsidian rows marked *unverified* were not driven.

## Links and anchors — Typora 1.14.9, clicked

| construct | renders | ⌘-click behaviour |
|---|---|---|
| `[text](Sub%20Folder/a%20file%20%28x%29%20中文.txt)` | link | **opens the file** |
| same in a list item | link | **opens the file** |
| same in a table cell | link | **opens the file** |
| `[text](#custom-id)` → `<a id="custom-id">` | link | **jumps** |
| same in a list item | link | **jumps** |
| same in a table cell | link | **jumps** |
| `<a id="x"></a>` (empty) inline in a heading | **raw text: `<a id="x"></a>`** | — |
| `<a id="x"></a>` (empty) on its own line | **raw text, grey HTML block** | — |
| `<a id="x" href="path">Name</a>` in a heading | **only `Name`** | **opens the file** |
| `### Heading {#custom-id}` | only `Heading` — the `{#id}` is consumed | (target resolves) |

**The decisive pair:** an empty `<a>` shows its own source; an `<a>` *with content* shows only the
content. That is what makes id-plus-href-on-one-element the form to use.

## Links and the vault boundary — Obsidian 1.x, clicked

| construct (page inside `Vault/`, target outside it) | ⌘-click behaviour |
|---|---|
| `[x](../../Docs/A%20Report.pdf)` — file, outside the vault | **dead** — Obsidian treats it as an in-vault path |
| `[x](../../Docs/Folder/)` — folder, outside the vault | **throws** `Cannot read properties of null (reading 'getParentPrefix')` |
| `[x](../Sub/Note.md)` — inside the vault | opens |
| `[x](../Sub/Note)` — inside the vault, no extension | opens (Typora does **not**) |
| `file:///Users/someone/…` | dead on any machine but the author's |

Clicking a dead out-of-vault link is not inert: one form made Obsidian attempt to **create** the
target. Nothing was written in the observed case, but treat the click as a write attempt, not a no-op.

The same links all open in Typora, which resolves on the filesystem. This asymmetry is the single
biggest portability trap for a generated document, and it is invisible to any syntax check.

### Escapes that do not work

| escape | verdict |
|---|---|
| `external-file-embed-and-link` plugin (v1.5.9) | reads outside the vault, but only through **code-block processors** (` ```LinkRelativeToVault `) — not a markdown link. Typora renders the block literally, and `isDesktopOnly: true` in its manifest drops mobile |
| symlink the documents into the vault | Obsidian follows it, but any generator sweep that resolves a page's real path and skips what escapes the vault root goes blind to the linked content — a visible failure traded for a silent one |
| `file:///…` absolute URL | opens only on the machine that generated it |

The two resolutions that do work are in SKILL.md: root the vault at the parent, or state the path as
text and link only inside the vault. Both are decisions about the vault, not repairs to the page.

## Charts and callouts: Obsidian 1.13.7 and Typora 1.14.10, 2026-10

Each editor's own bundled `mermaid.min.js` (both 11.13.0; Obsidian ships a one-line text-measuring patch)
rendered the probe page ([`render-probe.md`](../../../ai-os/skills/pre-onboarding/tests/probe/render-probe.md), one block of each kind
`wiki.py chart` writes) in a browser, each block mounted in the page the way the editors mount it. Typora's
switches were read from its own source: diagrams render only when `enableDiagram` is set (default off), and a
blockquote becomes an alert box only for `/^\s*\[!(note|warning|important|tip|caution)\]/i` when
`enableAlert` is set (default on). The editors themselves were not driven for this pass; reopen the probe in
each before relying on a new kind.

| construct | Obsidian 1.13.7 | Typora 1.14.10 |
| --- | --- | --- |
| `xychart-beta` bar | renders | renders, with Diagrams on |
| `xychart-beta` line | renders | renders, with Diagrams on |
| `pie` | renders | renders, with Diagrams on |
| `gantt` (validity bar) | renders | renders, with Diagrams on |
| `timeline` | renders | renders, with Diagrams on |
| any of the above, Diagrams off | n/a | the fenced source code, as text |
| `> [!note]` / `tip` / `important` / `warning` / `caution` | callout box | alert box |
| `> [!note] Title text` | box titled "Title text" | alert box, "Title text" as its first line |
| `> [!info]`, `[!todo]`, `[!danger]` and other Obsidian types | callout box | plain quotation, marker printed |

A gantt mounted outside the page has no width to lay out against and draws nothing (0 px wide); mounted in
place it fills the column. Test a renderer's output in place, as an editor shows it.

## Documented rules

| rule | source |
|---|---|
| "make sure to URL encode the link destination. For example, blank spaces become `%20`" | Obsidian, *documented* |
| "Links to file formats other than Markdown needs to include a file extension" | Obsidian, *documented* |
| invalid characters in a link target: `# \| ^ : %% [[ ]]` | Obsidian, *documented* |
| pipe in a table escaped as `\|` | Obsidian, *documented* |
| heading link form is `[[Note#Heading]]`; block link is `[[Note#^blockid]]` | Obsidian, *documented* |
| "Block references are specific to Obsidian and not part of the standard Markdown format" | Obsidian, *documented* |
| "You can use HTML to style content where pure Markdown does not provide support" | Typora, *documented* |
| "you only need one blank line … to create a new paragraph" | Typora, *documented* |
| custom heading ids | **documented by neither** (Typora consumes `{#id}` in practice) |
| markdown link to an in-document anchor | **documented by Typora only** |

Obsidian's help documents in-document navigation **only** in wikilink form (`[[#Heading]]`), which is
Obsidian-specific syntax and inert in Typora. There is therefore **no in-document link form documented by
both** — which is why the portable choice is the file link, with the anchor as a verified extra.

## Encoding

`urllib.parse.quote(path, safe="/&")` produces what both accept:

| character | becomes | why it matters |
|---|---|---|
| space | `%20` | required by Obsidian's help |
| `&` | **stays `&`** | **`%26` opens in NEITHER editor** — see the row below |
| `(` `)` | `%28` `%29` | a raw `)` truncates the destination for any `[^)]+` parser |
| `#` | `%23` | otherwise read as a fragment |
| CJK | percent-encoded UTF-8 | round-trips through `unquote` for verification |

### The ampersand, clicked (2026-08-06, against a real 1.4 MB PDF)

| destination | Typora 1.14.9 | Obsidian 1.12.7 |
|---|---|---|
| `…%20%26%20…`, markdown link | "Cannot open location …", offers `https://…` | does not open — **creates** a stray note + folder |
| `…%20%26%20…`, HTML `<a href>` | same failure | (same class) |
| `…%20&%20…`, markdown link | **opens** | **opens** |
| `…%20&amp;%20…`, HTML `<a href>` | **opens** | — |

Both editors decode `%20` and CJK **in the same destination** that they fail to decode `%26` in. That
asymmetry is why this is invisible to review: the destination is correctly encoded by the documented
rule, and dead. Obsidian's variant is a **write**, not a read failure.

A generated document cannot detect this by checking whether the target exists: `unquote("%26")` gives
the real path, so the link is valid on disk and dead in the hand. It has to be named as its own defect.

Escaping is **two separate jobs** when text sits inside an inline element: `html.escape()` the visible
text, percent-encode the `href`. Neither substitutes for the other.

## Probe template

Write this, open it, click every link. Adapt the destinations.

```markdown
# Probe

## Contexts
Paragraph: [file](Sub%20Folder/a%20file%20%28x%29%20中文.txt) · [anchor](#target)

- List: [file](Sub%20Folder/a%20file%20%28x%29%20中文.txt) · [anchor](#target)

| where | file | anchor |
|---|---|---|
| table cell | [file](Sub%20Folder/a%20file%20%28x%29%20中文.txt) | [anchor](#target) |

## Forms
### <a id="target" href="Sub%20Folder/a%20file%20%28x%29%20中文.txt">id + href on one element</a>
### <a id="empty"></a>[separate empty anchor](Sub%20Folder/a%20file%20%28x%29%20中文.txt)
### [plain markdown heading link](Sub%20Folder/a%20file%20%28x%29%20中文.txt)
```

Put a target file at that path whose content says plainly that it was reached — "target file reached" —
so a click that opens *something* is distinguishable from a click that opened the right thing.

## Things that look like defects and are not

- **Typora showing `##` or raw HTML in a block.** Its live editor reveals a block's source while the
  cursor is inside it. Move the cursor away before judging; check the outline pane, which shows the parsed
  heading text.
- **A file that looks larger than what you wrote.** `len(str)` counts characters, `ls` counts bytes, and
  CJK is three bytes per character. Compare renders, not sizes.
- **An audit whose links "don't work".** Count the destinations first. In the case this skill came from,
  657 of 834 links were in-document anchors and every one of them worked exactly as written — the defect
  was the policy, not the syntax.
