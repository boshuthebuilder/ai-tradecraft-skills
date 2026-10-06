<!-- Stage 5, acceptance in the professional's lens. Rendered by `wiki.py review-prompts`, which fills every field
in braces and drops this comment; doubled braces are literal. -->
# Professional review: {page}

The acceptance stage of [the core wiki rule](../../../wiki-maintenance/SKILL.md#the-core-wiki-rule) in
`wiki-maintenance`, in the professional's lens. **Pen:** you, {reviewer_model}, a model that did not write this
page ({author_model} wrote it), reading it as {professional}. You judge the page; you do not rewrite it.

## Its contract

{contract}

## Its scope

{scope}

## The page

`{page}` in `{wiki_dir}`, as it stands (sha256 `{page_sha256}`):

{page_text}

## Its sources

The folder is `{root}`; the page names each source by its folder-relative path. **A source marked "do not open" is a
document whose text or path carries a name kept from you: never open its file.** Judge the page against its card as
the line gives it, and say in a finding what you could not check:

{sources}

## Facts to check

{sampled} facts from the cards of the documents the page cites, chosen by a fixed rule, so a second review of
this page checks the same ones (the facts of a source marked "do not open" are left out). Open each source above that is
not marked "do not open" and confirm the fact there, then check whether the page states it as the source does:

{facts}

## Judge

In the professional's lens, as the rule's *Acceptance* sets it out:

1. Does it meet its contract: every question answered in order, every field carried or shown as **not on file**?
2. Do its facts match their sources: the facts above, and any other figure on the page you doubt?
3. Does it stay in its scope and in {professional}'s voice, with outside knowledge labelled and dated rules checked
   against their official source?

For a fixed page (the Index, Deadlines, the Schema or the Log) judge it for what it is for, as
[`wiki-onboarding`, step 6](../../../wiki-onboarding/SKILL.md#6-reader-acceptance-the-owners-lens-and-the-professionals)
sets out. Open the page and its sources that are not marked "do not open", and nothing else in the folder.

## Reply

JSON only. The verdict is `accepted`, or `changes` with at least one finding; every finding says where on the page
it is. Copy the page's sha256 as given: it ties your verdict to the version you read.

```json
{{"page": "{page}", "page_sha256": "{page_sha256}", "lens": "professional", "author": "{author_model}",
 "reviewer": "{reviewer_model}", "verdict": "<accepted or changes>",
 "facts_checked": [{{"fact": "<as the source states it>", "source": "<path>",
                    "on_page": "<as the page states it, or not stated>", "matches": true}}],
 "findings": [{{"where": "<heading or line>", "finding": "<what breaks the contract, a source or the scope>"}}]}}
```
