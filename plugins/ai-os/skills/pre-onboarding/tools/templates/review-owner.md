<!-- Stage 5, acceptance in the owner's lens. Filled by the coordinating agent: replace every field in braces;
doubled braces are literal. -->
# Owner review: {page}

The acceptance stage of [the core wiki rule](../../../wiki-maintenance/SKILL.md#the-core-wiki-rule) in
`wiki-maintenance`, in the owner's lens. **Pen:** you, {reviewer_model}, a model that did not write this page
({author_model} wrote it), reading it as {reader}. You judge the page; you do not rewrite it.

## The reader's questions, most important first

{questions}

## The page

{page_text}

## Judge

In the owner's lens, as the rule's *Acceptance* sets it out:

1. Can {reader} answer each question from the page, in that order, the first from its opening lines?
2. Can they act on what it says: what is due, by when, what to do next?
3. Is anything unclear, buried, contradictory or missing, as they would see it?

## Reply

JSON only; the verdict is `accept` or `revise`, and every finding says where on the page it is:

```json
{{"page": "{page}", "lens": "owner", "author": "{author_model}", "reviewer": "{reviewer_model}",
 "verdict": "<accept or revise>",
 "findings": [{{"where": "<heading or line>", "finding": "<what the reader cannot answer or do>"}}]}}
```
