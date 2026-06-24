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

## Write contract

The user vault is the **type-1 skeleton** (see *The type-1 user vault* in `ARCHITECTURE.md`): a single
self-contained vault of numbered areas, each with a folder-note. The synthesis owns **only** the
derived areas — `00 Index/` and `01 Knowledge/` — and writes them **incrementally**: it reads the
current Knowledge tree and makes **minimal stable changes**, preserving page paths so links survive. It
**never regenerates the vault wholesale**, and it **never touches** the owner-authored areas (`02
Ideas/`, `03 Reports/`). The deployment's write guards enforce this: an area write-fence (only `00
Index/`/`01 Knowledge/`), the same `.proposed.md` human-edit guard used everywhere, and in-root
containment. The synthesis never writes back into a project wiki.

Because Knowledge is incremental, the artefact can drift — hence the **`reconcile` twin**: a periodic
whole-vault pass under the **same** write contract (still incremental, still fenced to the derived
areas), differing only in **breadth** (the whole vault against all sources, not the changed slice) and
**cadence** (a clock, not the reactive gate). See the twin rule in `ARCHITECTURE.md`.

## Files

- **`jobs.yaml`** — the two job declarations (`synthesise` + `reconcile`) to copy into the config.
- **`synthesise.md`** — the reactive incremental prompt (the per-job procedure; references `wiki-maintenance`).
- **`reconcile.md`** — the periodic whole-vault prompt (the twin; references `wiki-maintenance`).
- **`scheduler.md`** — how to wire the reactive gate + the periodic clock, and the execution-context constraint.

## How to use

Stamp one instance **per identity** that wants a cross-project view: copy the files, fill the
`{placeholders}`, scaffold the type-1 skeleton, map the identity's vault in your deployment's path
config, and wire the reactive timer (for `synthesise`) plus the periodic clock (for `reconcile`). The
vault needs no inbox and no `wiki-onboarding` pass; it is scaffolded to the type-1 skeleton, and the
synthesis evolves its Knowledge area from there. The full flow is the **`user-onboarding`** skill.

These templates are generic by design: they name no real owner, host, or platform. The deployment
supplies the timer, the storage, the model runner, the access rule, and the deterministic guards the
templates *describe* but do not themselves enforce.
