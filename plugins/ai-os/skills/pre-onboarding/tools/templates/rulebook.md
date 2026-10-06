<!-- Stage: the rulebook, written with the owner's interview (SKILL.md step 2). Filled by the coordinating agent from
the owner's answers: replace every field in braces, delete a section the folder has no use for (never the reserved
names, the new files section or the migrations section), and remove this comment; doubled braces are literal.
**Pen:** the coordinating agent writes it and the owner agrees it before the twin is pinned. Save it as `CLAUDE.md`,
copy it byte for byte to `AGENTS.md`, and write `.familyai/rulebook.json` from the same answers. The wiki it names is
built under [the core wiki rule](../../../wiki-maintenance/SKILL.md#the-core-wiki-rule). `readiness.py` reads the
rulebook strictly, a statement at a time: any statement that names the migrations folder together with a routing word
is a finding, a negation included. Keep the wording below, which names the folder only where it says that approved plan
rows stage files there, and says elsewhere, without naming it, that new files are filed in this folder. Never name
another project in this file.
How each field is made:
- `folder_name`: the folder's own name. `folder_description`: the twin's `folder_description`.
- `users_and_boundaries`: the owner's answers on who uses the folder and what is held apart.
- `inbox`, `migrations_dir`, `wiki_dir`, `depth`, `identifiers`, `ocr_languages`: the twin's values.
- `reserved_extra`: one bullet per name in the twin's `reserved`, saying what it holds, or nothing. The bullets for
  `Outbox`, `Wiki` and the leading `_` rule are fixed: keep them.
- `how_files_arrive`: the owner's answer on how new files reach the folder, in a few words.
- `packs`, `active`, `finished`, `working_formats`, `exclusions`: one bullet per entry, each path in backticks, or the
  word none.
- `ai_outputs`: where AI outputs already sit, or none.
- `people`: one bullet per person or organisation, with every other name it appears under. -->
# {folder_name}: rulebook

The standing instructions for any AI session working in this folder. `AGENTS.md` is a byte-identical copy of this
file: change this one, copy it over the other, and review `.familyai/rulebook.json` against the change.

## What this folder is

{folder_description}

## Who uses it, and the boundaries inside it

{users_and_boundaries}

## Reserved names

These top-level names are the system's, and none is one of the owner's documents:

- `CLAUDE.md` and `AGENTS.md`: this rulebook and its copy.
- `GEMINI.md`: the name another engine reads its instructions from. It is reserved and never written here.
- `.familyai`: the machine-readable twins of this rulebook and of the wiki's Schema.
- `_Audit`: the audit, the plans, the extract records and the cards.
- `{inbox}`: where incoming material lands. It is read only to file what lands in it.
- `{migrations_dir}`: described under Migrations, below. It is not read.
- `{wiki_dir}`: the wiki.
- `Outbox` and `Wiki`: names the audit never walks, whatever sits under them.
- Any other top-level folder whose name begins with `_`: a system folder, skipped by the audit and never read by the
  deployment.
{reserved_extra}

## New files

- New files arrive in `{inbox}` {how_files_arrive}. The wiki's routing files each one within this folder, into an
  existing folder, and never creates a new top-level one.
- A file that seems to belong to another project is filed here like any other. The owner's own synthesis may suggest
  a move, and the owner makes it by hand.

## Migrations

Files the owner has approved for another project wait in `{migrations_dir}/<Project>/` only while a migration is
open, and only a plan row the owner approved puts them there. The owner clears the folder by hand before this folder
is onboarded, and a deployment onboards it only once it is empty.

## Reorganisation

Depth: {depth}. Nothing moves, is renamed or is removed without a plan row the owner approved. Removed items go to the
Bin, never unlinked. Emptied folders are kept unless the owner has said otherwise.

## Packs and deliberate copies

These folders keep deliberate copies of documents held elsewhere, so no copy inside one is deleted:

{packs}

## Live and closed matters

Live: {active}

Closed, ingested once as history: {finished}

## Working formats and exclusions

Working formats: {working_formats}

Paths the owner has excluded from reading: {exclusions}

Identifiers are written under the policy `{identifiers}`. Passwords and activation codes are never written.

## Where AI outputs sit

{ai_outputs}

## Languages and names

Documents are read in {ocr_languages}, most likely first. People and organisations, each with every other name it
appears under:

{people}

## The wiki

`{wiki_dir}` is this folder's wiki. Its Schema page, `90 Schema/90 Schema.md`, is its constitution: its layout,
routing, page contracts and page professionals. Follow the Schema, write each page as its one professional, and never
overwrite a page the owner has edited. A drafting agent is the one exception to opening the Schema page: its brief
carries the Schema's tables and everything else it needs, and tells it not to open the page.
