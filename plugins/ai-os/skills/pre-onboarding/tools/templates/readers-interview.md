<!-- Stage: the readers interview, the first wiki stage in pre-onboarding (SKILL.md step 7). Held by the coordinating
agent itself, with the owner, and given to no subagent: replace every field in braces; doubled braces are literal.
`folder_name`: the folder's own name. `owner_context`: written from `rulebook.json`, as the head of every page brief
is: the folder and its `folder_description`; each of `people`, with its other names and who it is; the identifier
policy; the `boundaries`. `profile_summary`: from `wiki.py profile`, a line per top-level folder with its document
count, its main card categories and the span of its dates. -->
# Readers interview: {folder_name}

The first wiki stage in [`pre-onboarding`](../../SKILL.md#7-build-the-wiki), under
[the core wiki rule](../../../wiki-maintenance/SKILL.md#the-core-wiki-rule) in `wiki-maintenance`: who reads the
wiki, and what for. **Pen:** the owner, who answers; you ask, and write the answers down in the owner's words,
adding nothing of your own. Nothing about the wiki's shape is decided here.

## The folder

{owner_context}

What it holds, per folder (from `wiki.py profile`):

{profile_summary}

## Ask

A few questions, not a questionnaire (the interview in
[`wiki-onboarding`, step 3](../../../wiki-onboarding/SKILL.md)); follow up only where an answer is vague.

1. Who will read this wiki: the owner, and who else?
2. For each reader: what will they come to it for, and what will they decide or do with what they find?
3. For each reader: which questions will they ask it, most important first?
4. Is there anything a reader must not see, or that should be held back?

## Record

Reply with JSON only:

```json
{{"readers": [{{"reader": "<name or role>", "use": "<what they come for and act on>",
               "questions": ["<most important first>", "<next>"]}}],
 "held_back": ["<anything a reader must not see, as the owner put it>"],
 "notes": "<anything else the owner said about the wiki>"}}
```

The readers and their questions go to the librarian (`structure-brief.md`) and to each page's professional
(`contract-brief.md`), and end in the Schema: its readers and purpose, and each contract's Reader and Questions.
What the owner holds back goes into the rulebook's `boundaries`, which every page brief carries to its drafter, and
into the contract of any section it limits. No tool enforces it: the reviewers judge each page against its contract.
