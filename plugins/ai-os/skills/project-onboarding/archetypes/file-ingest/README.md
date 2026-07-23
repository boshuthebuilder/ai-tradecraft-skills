# file-ingest archetype

The standard job pair for a folder of accumulating documents kept current by a synthesised wiki.
`project-onboarding` stamps this out for a new project; the conventions both jobs follow live in the
`wiki-maintenance` skill; the design rationale is in [`ARCHITECTURE.md`](../../../../ARCHITECTURE.md).

Two jobs, named for what they do (a job's `id` equals its `mode`):

| job | mode | scheduling | scope |
|---|---|---|---|
| `ingest` | `ingest` | **reactive** — runs the deterministic gate often; no-ops when nothing changed | incremental: drain the inbox, update the pages each new/changed source touches |
| `reconcile` | `reconcile` | **periodic** — a fixed cadence (e.g. weekly) | comprehensive: reckon the whole wiki against the files; dedupe, sweep orphans, fix stale claims |

## Files

- **`jobs.yaml`** — the job declarations to copy into a project's config.
- **`ingest.md`** — the `ingest` job's prompt template (the per-job procedure; references `wiki-maintenance`).
- **`reconcile.md`** — the `reconcile` job's prompt template.
- **`scheduler.md`** — how to wire the reactive `ingest` and the periodic `reconcile` in a deployment.

## How to use

Copy the four files, then fill the `{placeholders}` and the deployment-specific config fields. The
default is to use the prompt templates **unchanged** and let the project's own Schema page (written by
`wiki-onboarding`) plus the `wiki-maintenance` skill carry the specifics — specialise a template only
where the generic shape genuinely falls short for one project.

These templates are generic by design: they name no real owner, host, or platform. A deployment
supplies the timer, the storage, the model runner, and the deterministic write-guards that the
templates *describe* but do not themselves enforce (see the three-layer model in `ARCHITECTURE.md`).
