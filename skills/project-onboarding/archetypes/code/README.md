# code archetype

The job pair for a **code project** — a git repository the system reads (never writes) and reports on.
Unlike `file-ingest`, a code project's source of truth is a **git clone**, not a folder of documents,
so its jobs read the clone's history and write **reports**, and it offers **no `ingest`**. The design
rationale is in [`ARCHITECTURE.md`](../../../../ARCHITECTURE.md).

Two jobs, named for what they do (a job's `id` equals its `mode`):

| job | mode | scheduling | scope |
|---|---|---|---|
| `digest` | `digest` | **periodic** (e.g. weekly) | a plain-language summary of what changed — for a non-expert owner |
| `review` | `code-review` | **periodic** (e.g. weekly) | a correctness/risk review of the recent changes |

Both are **read-only over the code**: the gather stage reads the clone deterministically (recent
commits + their file churn via `git`); the reasoning summarises/reviews; the write stage emits a
report page into the project's **reports area** through the deployment's deterministic write-guards.
The code itself is never modified — there is no write path to it.

## Storage shape (why this archetype is different)

A code project separates **code** from **artefacts**, linked by a recorded path (not a symlink):

- the **code** is a git clone on the worker (a deployment-local path), kept current by a `fetch`;
- the **artefacts** (this archetype's reports, plus the project's machine config) live in the
  project's own shared/owned folder — the "home" — which is where the report pages land.

A deployment supplies both locations and records the clone path in the project's config; the jobs read
`backing.path` (the clone) and write under the home's reports area.

## Files

- **`jobs.yaml`** — the job declarations to copy into a project's config.
- **`digest.md`** — the `digest` job's prompt template.
- **`code-review.md`** — the `review` job's prompt template.
- **`scheduler.md`** — how to wire the two periodic jobs, and the deterministic git read they depend on.

## How to use

Copy the files, fill the `{placeholders}`, and point the deployment's gather at the project's git
clone. The templates are generic by design: they name no real owner, host, repository, or platform. A
deployment supplies the timer, the clone, the model runner, and the deterministic write-guards the
templates *describe* but do not themselves enforce (the three-layer model in `ARCHITECTURE.md`).

A code project may also emit an optional **cross-project report** for a person's user-level wiki (a
notable decision or risk worth remembering beyond this one project). That is a *guarded* cross-project
write the deployment routes through its user-level capture — never a raw write from these templates.
