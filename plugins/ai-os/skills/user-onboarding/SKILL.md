---
name: user-onboarding
description: >-
  Onboard a *person* (an identity) into an AI-OS-style setup: stand up their type-1 user vault (a
  "second brain") and wire the synthesis jobs that keep it current. Use when giving someone a
  synthesised, cross-project view over the project wikis they can access — distinct from
  project-onboarding, which onboards a folder of documents. Covers the storage-ownership handshake
  (the user owns the folder and shares it into the worker), the type-1 vault skeleton it scaffolds,
  the page kinds its `09 Schema` names (one professional and one contract each, under the core wiki
  rule), and stamping the user-synthesis archetype (an incremental `synthesise` plus its periodic
  `reconcile` twin), which also suggests cross-project migrations for the owner to make by hand. For a document
  folder use project-onboarding (after pre-onboarding for a lived-in one); for the synthesis archetype
  details see project-onboarding/archetypes/user-synthesis.
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
jobs follow, use **wiki-maintenance**. The projects a synthesis reads are onboarded first, each as
its own project: a tidy folder through `project-onboarding`, a lived-in one prepared through
[`pre-onboarding`](../pre-onboarding/SKILL.md) and then onboarded (the sequence is in
[`ARCHITECTURE.md`](../../ARCHITECTURE.md#preparing-a-folder-before-onboarding)).

## The shape of an onboarded identity

When onboarding is done:

- the identity's **user vault** exists, **owned by the user and shared into the worker** (never created
  on the worker — see *Storage ownership* in `ARCHITECTURE.md`);
- it is the **type-1 skeleton** — a single self-contained vault of numbered areas, each with a
  folder-note (`00 Index/`, `01 Knowledge/`, `02 Ideas/`, `03 Reports/`, `09 Schema/`, `10 Log/`),
  plus `_Audit/`, the audit tier;
- its `09 Schema` names the **page kinds** (the Index, an entity, a matter, a theme, a folder note),
  each with one professional and one contract, agreed by the owner (step 3), so every page the
  synthesis writes has a voice and questions to answer, under
  [the core wiki rule](../wiki-maintenance/SKILL.md#the-rule-in-a-user-vault);
- `_Audit/` holds the rationale file and the acceptance record, written by the deployment, never by
  the synthesis;
- the deployment's path config maps the identity's vault to its shared-in location, and the vault reads
  as **present** (materialised), not evicted/missing;
- the identity is registered with an **access scope** — the set of projects whose wikis its synthesis
  may read (the one access rule, single-homed in the deployment);
- the **user-synthesis archetype** is stamped: a reactive `synthesise` job and its periodic `reconcile`
  twin, both declaring `wiki-maintenance` as their capability;
- the synthesis is where **cross-project migrations are suggested**: when the wikis it reads show that
  files one project holds belong to another, it raises the move, with its evidence, for the owner to
  make by hand or decline, and no job carries it out (the archetype's
  [proposed migrations](../project-onboarding/archetypes/user-synthesis/README.md#proposed-migrations));
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
target's?). Record the scope in the deployment's config; never widen it implicitly. The scope governs
the owner confirmation records too: the synthesis sees the records of in-scope projects and no others
(the archetype's
[owner confirmation records](../project-onboarding/archetypes/user-synthesis/README.md#owner-confirmation-records)).
An identity needs
no model login of its own: each engine is logged in once per machine, and what isolates one
identity's synthesis from another's is the scoped gather and each call's own context
([one login per machine](../../ARCHITECTURE.md#execution-context-constraints-why-the-indirection-exists)).

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
- `_Audit/` — the audit tier, deployment-written: `wiki-rationale.md` (a rationale block per page) and
  `vault-acceptance.json` (the vault's own acceptance record, in the shape
  [the rule in a user vault](../wiki-maintenance/SKILL.md#the-rule-in-a-user-vault) defines). The
  synthesis never writes here.

Every structural folder gets a **same-name folder-note** with a high-level summary + how-to-read (the
Obsidian Folder Notes convention). There is **no inbox** — a user vault takes no file drops.

**The page kinds.** The vault keeps the core wiki rule per page kind
([`wiki-maintenance`](../wiki-maintenance/SKILL.md#the-rule-in-a-user-vault)). A **chief of staff**,
the professional whose desk spans every department, proposes the kinds, because a second brain is
organised by what its owner must track and decide across projects, not by where documents sit. The
owner agrees them before the first synthesis. The method's default kinds:

| kind | pages | professional | deliverable and tone |
|---|---|---|---|
| index | `00 Index/` | chief of staff | briefing note; brisk, ranked by urgency, one line per item |
| entity | a person or organisation known to more than one project | personal assistant | contact sheet and follow-up list; warm, efficient: what each project knows, reconciled, and where they disagree |
| matter | one venture, obligation or timeline that spans projects | delegated to the page: the professional of the matter, chosen from [the catalogue](../wiki-maintenance/references/professionals.md) by the synthesis as it writes the page and named in the page's `professional:` frontmatter and its rationale block | that professional's deliverable |
| theme | how several matters fit together: the overall money picture, the year's dates across projects | delegated to the page: the professional whose deliverable is that view (money: the financial planner; dates: the chief of staff), named in `professional:` | that professional's deliverable |
| folder note | the same-name note of `01 Knowledge/` and of each sub-tree under it (the `00 Index/` note is the index's; the other areas' notes are not the synthesis's to write) | librarian | catalogue; orderly, neutral, complete |

Every page has exactly one professional, as the core rule says. A kind either **fixes** it (index, entity,
folder note) or **delegates** the choice to the page (matter, theme): a page of a delegating kind carries
`professional:` in its frontmatter, a catalogue row or a professional named for the matter, so a later
pass keeps the voice the page was written in rather than re-choosing it. The owner agrees the delegation
when agreeing the kind. A deployment may add a kind; the Index's is never removed. Each kind has a **contract**: who reads it,
the questions in order, the fields every page of the kind carries. The Index's is the chief of staff's
three questions, what needs the owner's decision now, what falls due next and what is waiting on
someone else, then the map into Knowledge. Record both in `09 Schema` as two tables with fixed headers
beside the stability rules: **Page kinds** (kind | professional | deliverable and tone) and
**Kind contracts** (kind | reader | questions in order | fields), named so that neither is mistaken
for a project Schema's tables, which `pre-onboarding`'s `settings.py compile` reads and a vault never
feeds it. The deployment shows both tables, and
[the professional catalogue](../wiki-maintenance/references/professionals.md), to the synthesis with
the vault's structure, so a delegated choice has a vocabulary. The kind's contract questions govern a
page; the professional supplies the tone, and the voice is tone only: facts, sources, provenance,
frontmatter and the format rules are the same whoever the page speaks as. The librarian keeps
`09 Schema` and `10 Log`, as in a project wiki; the tree under `01 Knowledge/` still emerges, page by
page, from the projects.

### 4. Register the identity + stamp the user-synthesis archetype

- Register a synthesis project for the identity (`<identity>-brain` / `type: user-synthesis`), and map
  its vault path in the per-host path config (the shared-in location from step 1).
- Stamp the **user-synthesis archetype**: copy `jobs.yaml` (both jobs — `synthesise` + `reconcile`),
  `synthesise.md`, `reconcile.md`, fill the `{placeholders}`, and declare `wiki-maintenance` as the
  capability. The vault is **folder-IS-vault** (the folder is the vault root, no wiki subfolder).

### 5. Verify the wiring before trusting it

- The vault **resolves and is present** (materialised), not evicted or missing — a synthesis must never
  run against a half-synced folder.
- The **access scope** is correct: the synthesis sees exactly the intended projects' wikis and no
  others (check a project *outside* scope is absent from the gather view), and the same for the owner
  confirmation records: one in an in-scope project appears in the gather view, one in an out-of-scope
  project does not.
- The **reactive gate** fires on a source-wiki change, and on an owner confirmation record added or
  changed in an in-scope project while its wiki is unchanged, and no-ops otherwise; the **periodic**
  reconcile is on its clock.

### 6. First synthesis + hand off

Run one `synthesise` so `00 Index/`+`01 Knowledge/` hold a real starting view. Then **accept** the pages
it wrote, in the owner's lens and each page's professional's, through a model that did not write them,
in the two lenses and with the briefing
[`wiki-onboarding`'s reader acceptance step](../wiki-onboarding/SKILL.md#6-reader-acceptance-the-owners-lens-and-the-professionals)
gives the reviewer, but recorded in the vault's own record, `_Audit/vault-acceptance.json`, by the
deployment, not by `pre-onboarding`'s `wiki.py accept`, which cannot run on a vault. What the record
holds, what a verdict is keyed to (the kind fingerprint and the anatomy, never the body, so a routine
synthesis that only integrates a fact keeps it), and how a page later created, reshaped or found out
of step is reviewed, corrected or raised, is
[the rule in a user vault](../wiki-maintenance/SKILL.md#the-rule-in-a-user-vault): the deployment
runs that review as a step after a write and on any page found without a verdict, and the archetype's
`scheduler.md` says what its sweep hands the reconcile. `wiki-onboarding`'s order rule, under which
any later edit voids a verdict, governs the interactive session that builds a project wiki before its
hand-off, not a vault maintained by jobs. Then hand off: the vault
now maintains itself — a project wiki the identity can access changes, or an owner confirmation
record lands in one of its folders, and the next synthesis tick evolves the Knowledge slice it
touched; the weekly reconcile reckons the whole vault for drift. Authored ideas
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
- **One access rule.** The synthesis reads only the wikis, and the owner confirmation records, of the
  projects the identity may access — single-homed, never re-derived per surface.
- **Every page the synthesis writes has a kind.** Its kind has one contract in `09 Schema` and either
  fixes the page's professional or delegates it to the page's `professional:` frontmatter; the synthesis
  writes the page as that professional and returns its rationale block, and a page whose kind has no row
  is proposed, not written.
