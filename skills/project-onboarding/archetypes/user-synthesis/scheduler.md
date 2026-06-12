# Scheduling the user-synthesis job

How a deployment wires the single `synthesise` job. Platform-agnostic — the concrete timer is yours
(a launch agent, a cron entry, a systemd timer, a person running a command). The shared design is in
[`ARCHITECTURE.md`](../../../../ARCHITECTURE.md).

## `synthesise` — reactive, gated on the *source wikis*

Run the **deterministic gate often** and let it no-op when nothing changed — the same pattern as a
reactive `ingest`, but the gate watches different inputs:

- **What the gate hashes:** the content of every project wiki this identity may access, plus the
  accessible-project set itself (a project becoming visible or invisible to the identity is a
  change), plus anything else that feeds the synthesis (e.g. each wiki's declared entity domains).
- **When the change is consumed:** record the hash as seen only **after the vault write succeeds**.
  A failed, skipped or rate-limited run leaves the change pending, so the next tick re-detects it —
  the same consume-on-success rule the file-ingest gate follows.
- **Why a frequent tick is safe:** the gate is a cheap hash walk with no model call; the synthesis
  itself is expensive (a strong model over many wikis), which is exactly why the gate exists. A burst
  of project-wiki updates between two ticks coalesces into one synthesis.
- **Contention is a clean skip.** A tick landing while a synthesis is still running skips quietly;
  the next tick retries.

One timer **per identity** — each identity's vault gates and synthesises independently.

## The two constraints worth checking

- **Write context.** The vault usually lives in a synced/cloud folder; confirm the job runs in an
  execution context that can actually write it (see the execution-context section of
  `ARCHITECTURE.md` — an unattended scheduler often has to hop into a session that holds the
  capability).
- **Ordering with project jobs.** The synthesis reads project wikis, so it naturally runs *after*
  their ingests by gating: a project ingest changes a wiki, the next synthesis tick detects it. No
  explicit ordering or coupling between the timers is needed — the gate is the coordination.
