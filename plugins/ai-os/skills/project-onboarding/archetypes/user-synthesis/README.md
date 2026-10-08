# user-synthesis archetype

The jobs that give a **person** a cross-project view: gated, LLM-reasoned passes that synthesise a
**user-tier** vault for one *identity* from the project-tier wikis that identity may access. Project
wikis stay self-contained (the `wiki-maintenance` rule); the user-tier vault is the one place
cross-project links live. The design rationale — tiers, identities, the type-1 vault shape, and the
twin rule — is in [`ARCHITECTURE.md`](../../../../ARCHITECTURE.md).

The user vault's **Knowledge** area is **incrementally evolved**, not regenerated each run, so it can
drift from its sources — and therefore the archetype is a **pair** (the twin rule), exactly like
file-ingest. Two jobs, named for what they do (a job's `id` equals its `mode`):

| job | mode | scheduling | scope |
|---|---|---|---|
| `synthesise` | `synthesise` | **reactive** — runs the deterministic gate often; no-ops when no accessible wiki changed | incremental: evolve the Knowledge slice the changed source wikis touch |
| `reconcile` | `reconcile` | **periodic** — a clock (e.g. weekly), not the reactive gate | full: reckon the *whole* vault against *all* accessible wikis — prune cruft, repair cross-refs, confirm the Schema holds |

## The split that makes it safe and cheap

- **Deterministic (the deployment's code):** the **gate** — hash the accessible wikis' content plus
  the accessible-project set; reach the model only when that hash moved, and record the hash as seen
  only **after a successful write** (a failed run re-detects). And the **access-scoping** — gather
  feeds the model *only* wikis this identity may access, so a cross-tier leak is impossible by
  construction, plus a mechanical link backbone (entity → project-page occurrences) so every link the
  synthesis makes is real and portable.
- **Reasoning (the model):** the synthesis itself — weaving the scoped sources into a coherent whole:
  themes, cross-project connections, a navigable index, every claim traceable to a source page.
  It also suggests cross-project migrations for the owner to make by hand (below).

## Write contract

The user vault is the **type-1 skeleton** (see *The type-1 user vault* in `ARCHITECTURE.md`): a single
self-contained vault of numbered areas, each with a folder-note. The synthesis owns **only** the
derived areas — `00 Index/` and `01 Knowledge/` — and writes them **incrementally**: it reads the
current Knowledge tree and makes **minimal stable changes**, preserving page paths so links survive. It
**never regenerates the vault wholesale**, and it **never touches** the owner-authored areas (`02
Ideas/`, `03 Reports/`). The deployment's write guards enforce this: an area write-fence (only `00
Index/`/`01 Knowledge/`), the same `.proposed.md` human-edit guard used everywhere, and in-root
containment. The synthesis never writes back into a project wiki.

Every page the synthesis writes has a **kind** from the vault's `09 Schema`, and each kind has one
contract and either fixes the page's professional or delegates the choice to the page
(`user-onboarding`, *The page kinds*, under
[the core wiki rule](../../../wiki-maintenance/SKILL.md#the-rule-in-a-user-vault)); the deployment shows
the Schema's **Page kinds** and **Kind contracts** tables, and the professional catalogue, to the
model with the vault's structure. The page declares `kind:` in its frontmatter, and `professional:`
where its kind delegates, and is written as that professional's deliverable, to its kind's contract.
A page whose kind has no row is proposed in `needs_a_look`, never written; the proposal rides the
raised-item ledger like any item, raised once and not again while it is open or dismissed, and the
gate re-runs the synthesis when the owner adds the row, because it hashes the kind tables, so a
missing row cannot livelock the vault. The deployment's write guards hold the keys as they hold the
write-fence: a `kind:` that names no row in `09 Schema`, or a `professional:` that is neither a
catalogue row nor named for the matter in the rationale block, is refused at the write and reported,
never written and later counted. For every page it creates,
and every page whose kind, professional or shape it changes, the synthesis returns a **`rationale`**
block on the `wiki_pages[]` entry (the five lines of `wiki-maintenance`'s rationale block, as five
fields); an update that only integrates a fact omits it; the Index, which both passes re-derive each
run from a tree that does not show it, carries a block on its first write and whenever the reconcile's
findings name it. The deployment's write stage renders `_Audit/wiki-rationale.md` from the field,
since the deployment owns the audit tier as it does in a project, and the write-fence stays as it is:
the synthesis never writes `_Audit/`. The field is additive and optional: a deployment that validates
the reply strictly allows it before advancing its pin.

Acceptance in a vault is the deployment's, and its one home is
[*The rule in a user vault*](../../../wiki-maintenance/SKILL.md#the-rule-in-a-user-vault): the
record (`_Audit/vault-acceptance.json`, the vault's own), the verdict vocabulary, what a verdict is
keyed to (the kind fingerprint and the anatomy, never the body) and how the states move. What the
archetype adds is the wiring: the review runs as a deployment step after a write and on any page
found without a verdict; the periodic sweep hands the reconcile, through `{reconcile_findings}`, the
pages with no kind, no block (or the rationale file's headings with the structure), no accepted
verdict, the findings of a `changes` verdict, and the pages whose verdict's kind fingerprint is older
than the kind's rows; the reconcile corrects or restores those it can and counts the rest
([`scheduler.md`](scheduler.md)). Nothing reaches the reactive `synthesise` this way: it has no
findings input, so a stale-row page waits for the reconcile.

Because Knowledge is incremental, the artefact can drift — hence the **`reconcile` twin**: a periodic
whole-vault pass under the **same** write contract (still incremental, still fenced to the derived
areas), differing only in **breadth** (the whole vault against all sources, not the changed slice) and
**cadence** (a clock, not the reactive gate). See the twin rule in `ARCHITECTURE.md`.

## Proposed migrations

A project files every new item within itself, so a file that belongs to another project stays where
it was filed until the owner moves it
([`wiki-maintenance`'s rule](../../../wiki-maintenance/SKILL.md#rules-that-keep-it-safe)). While a
folder is being prepared, a curation round may stage a migration through plan rows the owner approves
([`folder-curation`'s staging rule](../../../folder-curation/SKILL.md#3-propose-the-only-model-step)),
and the folder is onboarded only once the migrations folder is empty; once a folder is maintained, the
synthesis, the one pass that reads both projects, is where a cross-project **migration** is proposed,
as a suggestion. Both templates return a suggestion as an ordinary `needs_a_look` item, one per
matter, with an optional `migration` field: the two project ids, the files by the folder-relative
paths the holding project's page cites, and the pages that show it, which are its evidence. Its
`owner_action` names the move for the owner to make by hand, or to decline. Most runs propose none,
and an item without the field is unchanged.

The synthesis never moves a file and never writes into a project, and no other job moves one for
it: the deployment surfaces the item to the owner as a suggestion, and the owner makes the move by
hand in the folders, never as a guarded cross-project move the deployment executes. Because a
suggestion is a `needs_a_look` item, it rides the raised-item ledger: an open or dismissed one is not
raised again, and a declined one stays declined. A deployment that does not read `migration` still
surfaces the item for the owner; one that does can show the two projects, the files and the evidence
beside it. The field is additive and optional: a deployment that validates the reply strictly allows
it before advancing its pin.

## Files

- **`jobs.yaml`** — the two job declarations (`synthesise` + `reconcile`) to copy into the config.
- **`synthesise.md`** — the reactive incremental prompt (the per-job procedure; references `wiki-maintenance`).
- **`reconcile.md`** — the periodic whole-vault prompt (the twin; references `wiki-maintenance`).
- **`scheduler.md`** — how to wire the reactive gate + the periodic clock, and the execution-context constraint.

## How to use

Stamp one instance **per identity** that wants a cross-project view: copy the files, fill the
`{placeholders}`, scaffold the type-1 skeleton, map the identity's vault in your deployment's path
config, and wire the reactive timer (for `synthesise`) plus the periodic clock (for `reconcile`). The
vault needs no inbox and no `wiki-onboarding` pass; it is scaffolded to the type-1 skeleton with its
page kinds agreed, and the synthesis evolves its Knowledge area from there. The full flow is the **`user-onboarding`** skill.

These templates are generic by design: they name no real owner, host, or platform. The deployment
supplies the timer, the storage, the model runner, the access rule, and the deterministic guards the
templates *describe* but do not themselves enforce.
