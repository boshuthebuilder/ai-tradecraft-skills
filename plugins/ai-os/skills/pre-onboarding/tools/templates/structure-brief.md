<!-- Stages 2 and 3, the structure and each page's professional. Filled by the coordinating agent: replace every
field in braces; doubled braces are literal. -->
# Structure brief: {folder_name}

The second and third stages of [the core wiki rule](../../../wiki-maintenance/SKILL.md#the-core-wiki-rule) in
`wiki-maintenance`: the wiki's sections and routing, then each page's professional. **Pen:** you, as the
librarian, proposing; the owner agrees the sections and routing first, then each page's professional, before any
contract or page is written.

## The folder

{owner_context}

## Its readers

From the readers interview:

{readers}

## What it holds

From `wiki.py profile`: per folder, its documents and copies, its cards by category, their date span and the
parties most often named.

{profile}

## The Schema so far

{current_schema}

## Propose

1. **Sections and routing**, as the rule's *Sections by responsibility* sets out. Route every folder in the
   profile, by its longest prefix, or name it with why it routes nowhere.
2. **Each page's professional**, as the rule's *One professional per page* sets out, from
   [the professional catalogue](../../../wiki-maintenance/references/professionals.md) or named for the matter,
   with the deliverable and tone the page will take.

Write the Layout, Routing and Page professionals tables exactly in the Schema's format
([`references/settings.md`](../../references/settings.md)), so they compile unchanged once agreed.

## Reply

JSON only:

```json
{{"layout": "<the Layout table>", "routing": "<the Routing table>",
 "page_professionals": "<the Page professionals table>",
 "reasons": [{{"row": "<a section, prefix or page>", "why": "<the files or the reader's question behind it>"}}],
 "not_routed": [{{"folder": "<folder>", "why": "<why it has no section>"}}],
 "questions_for_the_owner": ["<a choice only the owner can make>"]}}
```
