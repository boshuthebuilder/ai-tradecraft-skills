<!-- Stages: the structure and each page's professional, after the readers interview in pre-onboarding (SKILL.md
step 7). Filled by the coordinating agent and given to a subagent: replace every field in braces; doubled braces are
literal. Save the filled brief as `<work>/briefs/structure.md`, so that it is scanned. `folder_name`: the folder's own
name. `owner_context`: as in `readers-interview.md`. `readers`: the readers interview's JSON reply, as recorded.
`profile`: the JSON `wiki.py profile` wrote (`<work>/profile.json`), in full. `current_schema`: the Schema page's text
as it stands, or `none yet` on a first run, without any routing row into the migrations folder or an excluded path. -->
# Structure brief: {folder_name}

The wiki stages after the readers interview in [`pre-onboarding`](../../SKILL.md#7-build-the-wiki), under
[the core wiki rule](../../../wiki-maintenance/SKILL.md#the-core-wiki-rule) in `wiki-maintenance`: the wiki's
sections and routing, then each page's professional. **Pen:** you, as the librarian, proposing; the owner agrees
the sections and routing first, then each page's professional, before any contract or page is written.

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
