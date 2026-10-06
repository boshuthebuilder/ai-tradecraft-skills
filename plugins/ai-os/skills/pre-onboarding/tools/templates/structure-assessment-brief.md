<!-- Stage: the structure assessment, between the cards and the wiki in pre-onboarding (SKILL.md step 7). Filled by the
coordinating agent and given to a subagent, the records manager: replace every field in braces; doubled braces are
literal. Save the filled brief as `<work>/briefs/structure-assessment.md`, so that it is scanned. `input_file`: the
absolute path of the file `structure.py measure --out` wrote, the one file the subagent reads. The reply is written to
`_Audit/structure-assessment.md` and checked with `structure.py check`. -->
# Structure assessment brief

The structure assessment in [`pre-onboarding`](../../SKILL.md#7-assess-the-structure), before the wiki is drafted under
[the core wiki rule](../../../wiki-maintenance/SKILL.md#the-core-wiki-rule). **Pen:** you, as the records manager,
assessing; the owner decides the scope, folder by folder, from your record, and nothing moves before they do.

## The task

You are the records manager for one person's document folder. Read one file, `{input_file}`: the folder's tree (folders
with document counts), measures of its structure, and a sample of summary cards (path, document type, party, category,
date, title). From that alone, decide whether the folder's structure needs re-organising, and where. Read only that
file; open nothing else and run nothing.

Moving files has a real cost. The owner must relearn where things are, and anything outside the folder that points at a
moved file (bookmarks, other apps, emails with paths) breaks. A wiki will be built over the folder whatever you decide,
organised by responsibility, so the owner will not depend on the folder's structure to find things. So **leaving a
folder as it is is the default**, and you recommend moving files only where the current structure costs the owner
something real: one subject they would look for in two or more places, a folder that mixes unrelated matters so its name
no longer says what is in it, a duplicate tree, a dump of many unrelated files with no order, or names that say nothing.
A folder that is merely different from how you would have arranged it is left alone.

A measure that the file says *stands out* only marks where to look. It is not a finding: judge the folder from the
numbers and the cards together, quote the numbers you rely on, and leave a folder as it is when its flag has an innocent
reason. Strays at the root and duplicates alone are the light tidy's, which runs anyway, not a reason to re-organise.

## Verdicts

For each top-level folder, and for any sub-folder the file marks as standing out, give one verdict:

- **leave as it is**: the structure works; nothing moves.
- **tidy inside**: the folder's place and purpose are right, but things inside it need sorting (duplicates out, a few
  files to their right sub-folder, names made descriptive). Moves stay within the folder.
- **restructure**: the folder's contents belong elsewhere or need a new shape; files leave it or it is replaced.

Then one overall verdict for the whole folder:

- **no re-org**: every verdict is leave as it is (a stray or a duplicate at most, which the light tidy already handles);
- **targeted**: tidy inside or restructure, confined to a few named folders, with the rest left alone;
- **full**: most of the top-level structure needs a new shape.

Say how much would move: `Documents that would move: <N> of <M>`, M the number of documents the file gives for the
whole folder, and N the documents that the folders you marked tidy inside or restructure would send somewhere else. A
copy the light tidy would drop, and a stray it would place, are not counted. A targeted verdict can still move most of
the documents, and this line is how the owner sees it.

## Reply

Reply with exactly this record and nothing else:

```
# Structure assessment

Overall: <no re-org | targeted | full>
Reason: <two or three sentences>
Documents that would move: <N> of <M>

### <folder path>
- Verdict: <leave as it is | tidy inside | restructure>
- Evidence: <the measures and cards that decide it, with their numbers>
- What the owner would relearn: <none, or roughly how many files move and from where>
```

One `###` block per folder you assess, top-level folders first, in the tree's order; sub-folders only where their
measures stand out. Write a folder's path as the file's tree gives it, without `(root)` and without backticks. A folder
whose name reads `[withheld name]` cannot be named in your record, so leave it out and say so in the Reason. Each block
is exactly those three lines, each with text. With no re-org, every block says leave as it is, and N is 0.
