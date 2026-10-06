<!-- Stage 5, acceptance in the owner's lens. Rendered by `wiki.py review-prompts`, which fills every field in braces
and drops this comment; doubled braces are literal. -->
# Owner review: {page}

The acceptance stage of [the core wiki rule](../../../wiki-maintenance/SKILL.md#the-core-wiki-rule) in
`wiki-maintenance`, in the owner's lens. **Pen:** you, {reviewer_model}, a model that did not write this page
({author_model} wrote it), reading it as {reader}. You judge the page; you do not rewrite it.

## The reader's questions, most important first

{questions}

## The page

`{page}` in `{wiki_dir}`, as it stands (sha256 `{page_sha256}`):

{page_text}

Open no source file: the owner's lens judges the page as its reader would, from the page alone.

## Judge

In the owner's lens, as the rule's *Acceptance* sets it out:

1. Can {reader} answer each question from the page, in that order, the first from its opening lines?
2. Can they act on what it says: what is due, by when, what to do next?
3. Is anything unclear, buried, contradictory or missing, as they would see it?

For a fixed page (the Index, Deadlines, the Schema or the Log) judge it for what it is for, as
[`wiki-onboarding`, step 6](../../../wiki-onboarding/SKILL.md#6-reader-acceptance-the-owners-lens-and-the-professionals)
sets out.

## Reply

JSON only. The verdict is `accepted`, or `changes` with at least one finding; every finding says where on the page
it is. Copy the page's sha256 as given: it ties your verdict to the version you read.

```json
{{"page": "{page}", "page_sha256": "{page_sha256}", "lens": "owner", "author": "{author_model}",
 "reviewer": "{reviewer_model}", "verdict": "<accepted or changes>",
 "findings": [{{"where": "<heading or line>", "finding": "<what the reader cannot answer or do>"}}]}}
```
