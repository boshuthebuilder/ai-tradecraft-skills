# move-plan.csv — the curation plan, approvals and execution record

One file per curation round at `_Audit/plans/<YYYY-MM-DD>/move-plan.csv`, UTF-8, header row,
RFC 4180 quoting (paths contain commas and quotes). A second round on the same day takes a suffix
(`<YYYY-MM-DD>-2`): a plan folder holds one plan, and a proposal written into a folder that already holds one
replaces it, approvals and all, in the preparation tools. The proposer fills the first eleven columns; the
owner fills the approval pair; the executor fills the last three (the owner's approval also sets
`status`). Rows are never deleted or reordered; a withdrawn proposal is a row with
`approved = declined`. A proposer may seed `status` with `proposed`; recording the owner's approval
sets it to `pending`, and a decline to `skipped`. A path ending in `/` names a folder.

| column | filled by | values |
|---|---|---|
| `seq` | proposer | 1-based integer, execution order |
| `domain` | proposer | the owner's top-level folder or subject the row belongs to, for per-domain approval |
| `depth` | proposer | `light`, `medium`, `full`; never above the depth the owner chose for this round |
| `action` | proposer | `move`, `rename`, `delete`, `convert`, `create`, `rmdir` |
| `from` | proposer | folder-relative path today (empty for `create`; for `rmdir`, the folder to remove) |
| `to` | proposer | folder-relative path after (empty for `delete` and `rmdir`); a `move` the proposer cannot place, such as a root stray, is proposed with it empty, and the agent writes the owner's chosen destination here before the row is approved, with a tool that reads and writes CSV and changes no other cell (the preparation's `plan.py` has no command for it, and its dry-run `execute` refuses a row left without one) |
| `evidence` | proposer | the sha256 id of the file (a package's by the manifest's package hash rule); for a `delete`, the id of the entry whose `copies` list holds the path in `from`; none for a folder rename or an `rmdir` (an `rmdir`'s emptiness is proved on disk) |
| `reason` | proposer | one sentence, the audit finding it resolves (e.g. `redundant copy of <id> in the same folder`) |
| `kind` | proposer | for `delete`: `redundant` only (a `working_copy` or `pack` row is never a delete); for `convert`: the target format; for a `move` staging a file for another project: the moved path's copy kind, empty when its entry has one path |
| `sweep` | proposer | for a folder `rename`: `yes` when the wiki-maintenance rename protocol must run; the consumers found are listed in the execution `note` |
| `needs_a_look` | proposer | empty, or the reason this row is a proposal the owner must judge rather than a mechanical one |
| `approved` | owner | `approved`, `declined`, `deferred`; a blank row is treated as `deferred` |
| `approved_at` | owner | ISO datetime |
| `status` | proposer (`proposed`), owner (`pending`, `skipped`), executor (the rest) | `proposed`, `pending`, `done`, `skipped`, `failed`, `reverted` |
| `executed_at` | executor | ISO datetime |
| `note` | executor | the failure reason, the undo entry's id (which says where in the Bin a removed item went), or the rename sweep's consumer list |

Rules the schema encodes: a `delete` row's `from` must be a path its entry's `copies` list marks
`redundant`, and `evidence` must be that entry's own id — the canonical path is never deleted, and a
row that would remove an entry's last live path is invalid; a `convert` row is `done` only after
verification and archiving of the original; a folder `rename` with `sweep = yes` is `done` only after every in-folder consumer of the
old path is rewritten and out-of-folder consumers are logged as watch items. The executor takes its
rows only from this file; the one other thing it reads is the fresh manifest a `delete` row is
re-verified against.

## `rmdir` and the Bin

- An `rmdir` row removes a folder only when no file is left under it but `.DS_Store` (the folder
  metadata a desktop file browser leaves behind): any other file under it fails the row, and empty
  subfolders go to the Bin with it.
- Nothing is unlinked. A `delete` row's copy and an `rmdir` row's folder move to **the Bin**: the
  user's bin by default, or one the operator names. On a name clash the item takes a number, and the
  row's undo entry records where it went, so it is restored by moving it back. Keep the Bin unemptied until
  the folder is onboarded: in a synced folder (iCloud Drive, say) a removal reaches every device, while the undo
  log and the Bin's copy exist on the machine that ran the plan only.
- `delete` rows run in a phase of their own, after every other approved row is `done` and the folder
  has been re-audited since the last of them. Each is re-verified against that fresh manifest, not the
  one the plan was proposed from: the path is still marked `redundant`, a separate canonical copy
  exists, and both still hash to `evidence` on disk.
