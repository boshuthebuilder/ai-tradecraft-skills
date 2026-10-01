<!-- Stage 5, acceptance in the professional's lens. Filled by the coordinating agent: replace every field in
braces; doubled braces are literal. -->
# Professional review: {page}

The acceptance stage of [the core wiki rule](../../../wiki-maintenance/SKILL.md#the-core-wiki-rule) in
`wiki-maintenance`, in the professional's lens. **Pen:** you, {reviewer_model}, a model that did not write this
page ({author_model} wrote it), reading it as {professional}. You judge the page; you do not rewrite it.

## Its contract

{contract}

## The page

{page_text}

## Its sources

The folder is `{root}`; the page names each source by its folder-relative path. The section's evidence, one JSON
line per document (from `wiki.py bundles`): `{bundle}`

## Judge

In the professional's lens, as the rule's *Acceptance* sets it out:

1. Does it meet its contract: every question answered in order, every field carried or shown as **not on file**?
2. Do its facts match their sources? Check at least {sample} of them against the files they cite.
3. Does it stay in scope and in {professional}'s voice, with outside knowledge labelled and dated rules checked
   against their official source?

## Reply

JSON only; the verdict is `accept` or `revise`, and every finding says where on the page it is:

```json
{{"page": "{page}", "lens": "professional", "author": "{author_model}", "reviewer": "{reviewer_model}",
 "verdict": "<accept or revise>",
 "facts_checked": [{{"fact": "<as the page states it>", "source": "<path>", "matches": true}}],
 "findings": [{{"where": "<heading or line>", "finding": "<what breaks the contract, a source or the scope>"}}]}}
```
