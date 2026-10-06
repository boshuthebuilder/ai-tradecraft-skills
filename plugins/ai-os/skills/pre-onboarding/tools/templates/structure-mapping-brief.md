<!-- Stage: the mapping, after the owner has decided the scope of the structure assessment in pre-onboarding (SKILL.md
step 7). Filled by the coordinating agent and given to a subagent, the records manager: replace every field in braces;
doubled braces are literal. Save the filled brief as `<work>/briefs/structure-mapping.md`, so that it is scanned.
`input_file`: the absolute path of the file `structure.py measure --out` wrote. `documents_file`: the absolute path of
the file `structure.py documents --out` wrote for the folders the owner approved. `scope`: one line for each folder the
owner approved, with the record's verdict for it and what the record says the owner would relearn. The reply is the
mapping `plan.py reorg --mapping` reads; the coordinator replaces its `scope` with the owner's own list. -->
# Structure mapping brief

The mapping that follows the structure assessment in [`pre-onboarding`](../../SKILL.md#7-assess-the-structure), before
the wiki is drafted under [the core wiki rule](../../../wiki-maintenance/SKILL.md#the-core-wiki-rule). **Pen:** you, as
the records manager, proposing; the owner has approved the folders below and nothing else, and approves every row of the
plan that follows before it runs.

## The task

Read two files and nothing else, and run nothing: `{input_file}` (the folder's tree and measures, for the folders that
exist now) and `{documents_file}` (every document under the folders the owner approved, with its card's fields). Propose
where each document or folder that belongs elsewhere should go.

## Scope

The owner approved these folders, and only these. Nothing outside them is moved from:

{scope}

## Rules

- **The owner's shape stays.** Use the folders the tree already has as destinations. Create a folder only where none is
  the right home, and then below an existing top-level folder. Never a blank target tree, and no new scheme.
- **Cover what is in scope.** Go through every sub-folder of each approved folder, and give a row to each document or
  folder that belongs somewhere else. What stays needs no row.
- **A document, or a folder as a whole.** A `from` that is a document moves that document into the folder `to`, keeping
  its name. A `from` that is a folder moves everything under it into `to`, keeping its sub-folders, and the folder is
  then empty. Move a folder whole only when everything in it belongs together; otherwise give each document its own row,
  by what its card says.
- **No duplicates.** If a document's content already lives in the folder you would send it to, leave it out: the light
  round drops copies. Never propose a delete.
- **Paths** are as the files write them, relative to the folder's top, with `/` between parts and no backticks.
  Do not name anything whose name reads `[withheld name]`.

## Reply

JSON only, exactly this shape:

```json
{{"scope": [<the folders listed under Scope, copied exactly>],
 "moves": [{{"from": "<a document or a folder>", "to": "<a folder that exists or is to be created>"}}]}}
```
