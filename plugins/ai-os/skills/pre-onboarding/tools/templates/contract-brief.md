<!-- Stage 4, the page contract. Filled by the coordinating agent and given to a subagent: replace every field in
braces; doubled braces are literal. Save the filled brief as `<work>/briefs/contract-<NN>.md`, so that it is scanned.
`section`: the section's number and name as the Layout has them (`20 Finance`). `professional`: the professional or
professionals the Layout names for it. `owner_context`, `readers`: as in `structure-brief.md`. `section_rows`: the
section's Layout row and any Page professionals rows under it, copied as they stand with their header rows.
`routing`: the Routing rows that target the section, copied the same way. `bundle`: the path of the section's
`bundle_<NN>.jsonl` in the bundles folder, which the subagent opens; not its contents. -->
# Contract brief: {section}

The first half of the page-writing stage of
[the core wiki rule](../../../wiki-maintenance/SKILL.md#the-core-wiki-rule) in `wiki-maintenance`: the page
contract for section {section}. **Pen:** you, as {professional}, drafting the contract; the owner agrees it
before any page of the section is written (`page-brief.md` is the next stage).

## The folder and its readers

{owner_context}

The readers, and the questions they ask, from the readers interview:

{readers}

## The section

Its rows in the Schema's Layout and Page professionals tables:

{section_rows}

The folders routed to it:

{routing}

Its evidence, one JSON line per document (from `wiki.py bundles`): `{bundle}`

## Draft the contract

- **Reader**: who reads these pages, from the readers interview.
- **Questions, most important first**: what this reader needs answered, in the order you would answer it; your
  row in [the professional catalogue](../../../wiki-maintenance/references/professionals.md) gives a first draft.
- **Fields every page carries**: what each page of the section shows; one with no evidence will read
  **not on file**, so ask only for what the owner's files can hold or should. A section that holds money names its
  period convention here (a financial year, a VAT period or a tax year) and whether amounts are net or gross of VAT.

## Reply

JSON only, the row in the Schema's Page contracts format
([`references/settings.md`](../../references/settings.md)):

```json
{{"row": "| {section} (<professionals>) | <reader> | 1. <question> 2. <question> | <field>, <field> |",
 "why": "<how the reader's questions and the evidence led to this contract>",
 "questions_for_the_owner": ["<a choice only the owner can make>"]}}
```
