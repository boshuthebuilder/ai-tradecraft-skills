# Scheduling the user-synthesis jobs

How a deployment wires the two jobs — a reactive `synthesise` and a periodic `reconcile`.
Platform-agnostic — the concrete timer is yours (a launch agent, a cron entry, a systemd timer, a
person running a command). The shared design is in [`ARCHITECTURE.md`](../../../../ARCHITECTURE.md).

## `synthesise` — reactive, gated on the *source wikis and records*

Run the **deterministic gate often** and let it no-op when nothing changed — the same pattern as a
reactive `ingest`, but the gate watches different inputs:

- **What the gate hashes:** the content of every project wiki this identity may access, plus the
  accessible-project set itself (a project becoming visible or invisible to the identity is a
  change), plus the owner confirmation records in those projects' folders (small files; a record the
  project's ingest has not yet folded in still reaches the vault on the next tick), plus anything else
  that feeds the synthesis (e.g. each wiki's declared entity domains).
- **When the change is consumed:** record the hash as seen only **after the vault write succeeds**.
  A failed, skipped or rate-limited run leaves the change pending, so the next tick re-detects it —
  the same consume-on-success rule the file-ingest gate follows. A record whose **full** text the run
  did not show, omitted for budget, truncated, or unreadable when the gather reached it, is not
  consumed either: consumption is per record, its hash stays pending, and the gather shows pending
  records before the rest, so a budget that is always exceeded drains in order rather than marking an
  unread record seen. A pending record that **fails to read** does not open the gate by itself: the
  gate retries the read cheaply each tick and fires for that record only when the read succeeds, so a
  record that never decodes cannot run the costliest pass every tick with nothing new to show. After a
  bounded number of consecutive failed reads, and at once for one record larger than the whole budget
  on its own, the gate marks the record **blocked**, not seen: it raises it once to the owner as an
  item naming the file (fail loud, through the raised-item ledger so it is not raised again) and takes
  it out of the pending set so later records drain; the passes treat it as unreadable, leaving what
  may rest on it as it is. Blocked is keyed to the record's content hash and checked against the
  budget as it stands, so an edited record, or a larger budget, returns it to pending. The capture
  surface bounds a record's size at capture ([`wiki-maintenance`](../../../wiki-maintenance/SKILL.md#the-shape-of-a-folder)),
  which is what should make a blocked record rare.
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
  a Knowledge page citing a source page or record that no longer exists, where a cited record is
  resolved against its project's folder and one the gather omitted is not shown rather than vanished;
  staleness, pages with no `kind:`, no block in `_Audit/wiki-rationale.md` or no accepted verdict in
  `_Audit/wiki-acceptance.json`, pages whose verdict was recorded under an older version of their
  kind's row in `09 Schema`, log digest) and pass their findings into the prompt as a worklist — the
  model judges, the sweeps locate. The marker for a changed kind row is a **fingerprint of the whole
  row**, the fixed professional and every contract column (reader, questions, fields), which the
  deployment records with each verdict in `_Audit/wiki-acceptance.json` and compares with the row as
  it stands; a page is out of step when they differ, or when it has no verdict at all. Never the
  page's write time, which a reactive `synthesise` can advance with a fact-only update after the row
  changed, and never the rationale block alone, whose professional-lens line records the professional
  and the questions but not the reader or the fields. The acceptance state reaches the model only this way: neither prompt input shows the
  acceptance record itself. A page found with no verdict is handed to the acceptance review directly,
  which runs on any page without a verdict, not only after a write; a page found refused carries the
  review's findings in the worklist, so the reconcile can return it corrected and the review runs
  again.
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
