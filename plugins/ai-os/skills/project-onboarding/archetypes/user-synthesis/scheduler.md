# Scheduling the user-synthesis jobs

How a deployment wires the two jobs — a reactive `synthesise` and a periodic `reconcile`.
Platform-agnostic — the concrete timer is yours (a launch agent, a cron entry, a systemd timer, a
person running a command). The shared design is in [`ARCHITECTURE.md`](../../../../ARCHITECTURE.md).

## `synthesise` — reactive, gated on the *source wikis*

Run the **deterministic gate often** and let it no-op when nothing changed — the same pattern as a
reactive `ingest`, but the gate watches different inputs:

- **What the gate hashes:** the content of every project wiki this identity may access, plus the
  accessible-project set itself (a project becoming visible or invisible to the identity is a
  change), plus the vault's own `09 Schema` kind tables (an owner adding the row a proposed page
  waited for is a change), plus anything else that feeds the synthesis (e.g. each wiki's declared
  entity domains).
- **When the change is consumed:** record the hash as seen only **after the vault write succeeds**.
  A failed, skipped or rate-limited run leaves the change pending, so the next tick re-detects it —
  the same consume-on-success rule the file-ingest gate follows.
- **Why a frequent tick is safe:** the gate is a cheap hash walk with no model call; the synthesis
  itself is expensive (a strong model over many wikis), which is exactly why the gate exists. A burst
  of project-wiki updates between two ticks coalesces into one synthesis.
- **Contention is a clean skip.** A tick landing while a synthesis is still running skips quietly;
  the next tick retries.

One timer **per identity** — each identity's vault gates and synthesises independently.

## `reconcile` — periodic, on a clock

The twin runs on a **fixed cadence** (e.g. weekly), not the reactive gate — it is a whole-vault pass
that no single source change triggers, so there is nothing to gate on. It is the same shape as the
file-ingest `reconcile`:

- **No reactive gate.** It does not consult the `synthesise` seen-hash; it simply runs on its clock and
  reckons the whole vault against all accessible sources.
- **Deterministic sweeps first.** Before the model call, run the mechanical health sweeps (orphan pages,
  staleness, pages with no `kind:`, pages with no block in `_Audit/wiki-rationale.md`, pages whose
  verdict in `_Audit/vault-acceptance.json` is missing or `changes` (the findings of a `changes`
  verdict travel with the page), pages whose verdict's **kind fingerprint** is older than the kind's
  rows as they stand, log digest) and pass their findings into the prompt as a worklist — the model
  judges, the sweeps locate. The fingerprint, the record and the states are defined once, in
  `wiki-maintenance`'s *The rule in a user vault*; the sweep compares the fingerprint recorded with
  the verdict against the kind's rows now, never the page's write time (which a reactive `synthesise`
  advances with a fact-only update) and never the rationale block alone (which records the reader,
  the professional and the questions, not the fields or the tone). A page with no verdict is in the
  no-verdict list only, never in the out-of-step list. The acceptance state reaches the model only
  this way: neither prompt input shows the record itself. The review itself is the deployment's step,
  run after a write and on any page found without a verdict; a `refused` verdict (the reviewer was
  the author) is the deployment's to report to its operator, and goes to no worklist.
- **Same write context + consume-on-success** as `synthesise`.

One periodic timer **per identity**, alongside its reactive `synthesise` timer.

## The two constraints worth checking

- **Write context.** The vault usually lives in a synced/cloud folder; confirm the job runs in an
  execution context that can actually write it (see the execution-context section of
  `ARCHITECTURE.md` — an unattended scheduler often has to hop into a session that holds the
  capability).
- **Ordering with project jobs.** The synthesis reads project wikis, so it naturally runs *after*
  their ingests by gating: a project ingest changes a wiki, the next synthesis tick detects it. No
  explicit ordering or coupling between the timers is needed — the gate is the coordination.
