# user-synthesis archetype

The job that gives a **person** a cross-project view: a single, gated, LLM-reasoned pass that
synthesises a **user-tier** wiki for one *identity* from the project-tier wikis that identity may
access. Project wikis stay self-contained (the `wiki-maintenance` rule); the user-tier wiki is the
one place cross-project links live. The design rationale — tiers, identities, and why this archetype
has no `reconcile` twin — is in [`ARCHITECTURE.md`](../../../../ARCHITECTURE.md).

One job, named for what it does (a job's `id` equals its `mode`):

| job | mode | scheduling | scope |
|---|---|---|---|
| `synthesise` | `synthesise` | **reactive** — runs the deterministic gate often; no-ops when no accessible wiki changed | full: re-synthesise the identity's vault from every project wiki it may access |

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

The output vault is **fully generated** ("do not hand-edit"): a run may regenerate it wholesale, and
there is no human-edit guard to honour inside it — but writes stay inside the vault root via the
deployment's write guards, and the synthesis never writes back into a project wiki.

**No `reconcile` twin.** Each run is a full re-synthesis over current sources; there is no
incrementally-maintained artefact to drift. If a deployment later makes the synthesis incremental
(for cost), it re-earns a periodic full pass — see the twin rule in `ARCHITECTURE.md`.

## Files

- **`jobs.yaml`** — the job declaration to copy into the identity's synthesis config.
- **`synthesise.md`** — the prompt template (the per-job procedure; references `wiki-maintenance`).
- **`scheduler.md`** — how to wire the reactive gate, and the execution-context constraint.

## How to use

Stamp one instance **per identity** that wants a cross-project view: copy the files, fill the
`{placeholders}`, map the identity's vault in your deployment's path config, and wire the reactive
timer. The vault is derived — it needs no inbox, no Schema interview, and no `wiki-onboarding` pass;
its structure is whatever the synthesis writes.

These templates are generic by design: they name no real owner, host, or platform. The deployment
supplies the timer, the storage, the model runner, the access rule, and the deterministic guards the
templates *describe* but do not themselves enforce.
