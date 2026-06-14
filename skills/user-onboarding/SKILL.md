---
name: user-onboarding
description: >-
  Onboard a *person* (an identity) into an AI-OS-style setup: stand up their type-1 user vault (a
  "second brain") and wire the synthesis jobs that keep it current. Use when giving someone a
  synthesised, cross-project view over the project wikis they can access — distinct from
  project-onboarding, which onboards a folder of documents. Covers the storage-ownership handshake
  (the user owns the folder and shares it into the worker), the type-1 vault skeleton it scaffolds,
  and stamping the user-synthesis archetype (an incremental `synthesise` plus its periodic `reconcile`
  twin). For a document folder use project-onboarding; for the synthesis archetype details see
  project-onboarding/archetypes/user-synthesis.
---

# user-onboarding

Onboarding a **person** is a different shape from onboarding a **folder**. A project is a folder of
documents that gets a wiki (`project-onboarding`). An *identity* gets a **user-tier vault** — a "second
brain" — that is *synthesised over* the project wikis that identity may access: the one place
cross-project links live. This skill is the flow for that: the storage handshake, the vault skeleton,
and wiring the synthesis jobs, so a person arrives with a working, self-maintaining cross-project view.

Like `project-onboarding`, it is a **guideline**, not a script. The concrete acts — accepting a share,
writing path config, scheduling a timer — are deployment-specific. This skill describes *what a
correctly-onboarded identity looks like* and the order to build it; it points at the
**user-synthesis archetype** (`../project-onboarding/archetypes/user-synthesis/`) for the job templates
and at [`ARCHITECTURE.md`](../../ARCHITECTURE.md) for the why (tiers, identities, the type-1 vault, the
twin rule, storage ownership).

## When to use

- A person should have a synthesised, cross-project view over the wikis they can access.
- You are setting up a new identity in an AI-OS-style deployment.

For a folder of documents, use **project-onboarding**. For the ongoing maintenance conventions the
jobs follow, use **wiki-maintenance**.

## The shape of an onboarded identity

When onboarding is done:

- the identity's **user vault** exists, **owned by the user and shared into the worker** (never created
  on the worker — see *Storage ownership* in `ARCHITECTURE.md`);
- it is the **type-1 skeleton** — a single self-contained vault of numbered areas, each with a
  folder-note (`00 Index/`, `01 Knowledge/`, `02 Ideas/`, `03 Reports/`, `09 Schema/`, `10 Log/`);
- the deployment's path config maps the identity's vault to its shared-in location, and the vault reads
  as **present** (materialised), not evicted/missing;
- the identity is registered with an **access scope** — the set of projects whose wikis its synthesis
  may read (the one access rule, single-homed in the deployment);
- the **user-synthesis archetype** is stamped: a reactive `synthesise` job and its periodic `reconcile`
  twin, both declaring `wiki-maintenance` as their capability;
- a first synthesis has run, so `00 Index/` and `01 Knowledge/` hold a real starting view.

## The method

### 1. Storage handshake — the user owns the folder, shares it into the worker

**Do this first; it is the binding prerequisite.** The user vault must live on the *user's own* cloud
account, not the worker's (see *Storage ownership* in `ARCHITECTURE.md`):

1. The **user** creates the vault folder under their **own** identity (named distinctly, e.g.
   `<Identity> Second Brain`).
2. The user **shares** it to the worker account (`<worker-account>`).
3. The worker **accepts** the invite, so the folder materialises in the worker's filesystem.

This keeps the storage on the user's plan and the ownership with the user (revocable; off the worker's
quota). A deployment that *creates* the folder on the worker has inverted the model — undo it.

### 2. Scope the identity (read-only)

Decide which projects this identity may access — the synthesis will read **only** those wikis. This is
the same access rule the deployment enforces everywhere (do the requester's tags intersect the
target's?). Record the scope in the deployment's config; never widen it implicitly.

### 3. Scaffold the type-1 skeleton

Stand up the vault skeleton (idempotent — never overwrite a hand-filled page). The areas and their
roles (see *The type-1 user vault* in `ARCHITECTURE.md`):

- `00 Index/` — the map (system-maintained by `synthesise`).
- `01 Knowledge/` — **derived**; the synthesis owns it, an emergent, **incrementally evolved**
  cross-project hierarchy. Starts empty.
- `02 Ideas/` — **authored**; flat, atomic one-idea-per-file pages captured via the interactive
  surfaces. Starts empty.
- `03 Reports/` — AI documents, date-binned (`03 Reports/YYYY/MM/`). Starts empty.
- `09 Schema/` — the vault's constitution: organising principles + stability rules (prefer stable
  paths, reorganise only on strong signal, a depth ceiling). **Not** a rigid domain taxonomy —
  Knowledge structure emerges from the projects.
- `10 Log/` — append-only run history.

Every structural folder gets a **same-name folder-note** with a high-level summary + how-to-read (the
Obsidian Folder Notes convention). There is **no inbox** — a user vault takes no file drops.

### 4. Register the identity + stamp the user-synthesis archetype

- Register a synthesis project for the identity (`brain-<identity>` / `type: user-synthesis`), and map
  its vault path in the per-host path config (the shared-in location from step 1).
- Stamp the **user-synthesis archetype**: copy `jobs.yaml` (both jobs — `synthesise` + `reconcile`),
  `synthesise.md`, `reconcile.md`, fill the `{placeholders}`, and declare `wiki-maintenance` as the
  capability. The vault is **folder-IS-vault** (the folder is the vault root, no wiki subfolder).

### 5. Verify the wiring before trusting it

- The vault **resolves and is present** (materialised), not evicted or missing — a synthesis must never
  run against a half-synced folder.
- The **access scope** is correct: the synthesis sees exactly the intended projects' wikis and no
  others (check a project *outside* scope is absent from the gather view).
- The **reactive gate** fires on a source-wiki change and no-ops otherwise; the **periodic** reconcile
  is on its clock.

### 6. First synthesis + hand off

Run one `synthesise` so `00 Index/`+`01 Knowledge/` hold a real starting view, then hand off: the vault
now maintains itself — a project wiki the identity can access changes, the next synthesis tick evolves
the Knowledge slice it touched; the weekly reconcile reckons the whole vault for drift. Authored ideas
land in `02 Ideas/` through the interactive capture surfaces, never by hand in the vault.

## Principles

- **Storage stays with the user.** Created in their account, shared into the worker — always (step 1).
- **The folder is the vault.** Type-1 is folder-IS-vault; the synthesis writes vault-relative paths
  under the derived areas only.
- **Knowledge is derived + incremental; Ideas are authored; Reports are AI documents.** Three areas,
  three determinism stories. The synthesis owns `00 Index/`+`01 Knowledge/` and touches nothing else.
- **Knowledge ⊥ Ideas.** Knowledge never links un-incubated ideas; a matured idea is *promoted to a
  project*, which the synthesis then stitches into Knowledge — never folded in directly.
- **Incremental ⇒ a twin.** Because Knowledge is evolved not regenerated, the archetype is a
  `synthesise`/`reconcile` pair (the twin rule), exactly like file-ingest.
- **One access rule.** The synthesis reads only the wikis the identity may access — single-homed, never
  re-derived per surface.
