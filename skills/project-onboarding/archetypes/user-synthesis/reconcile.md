# reconcile prompt (single-shot, periodic, **whole-vault**)

The reasoning-stage template for the `reconcile` job — the periodic twin of `synthesise`. Same write
contract (incremental, fenced to the derived areas), but it reckons the **whole** vault against **all**
accessible sources rather than the slice a single source change touched. It exists because the Knowledge
area is incrementally maintained and can therefore drift (the twin rule in `ARCHITECTURE.md`). Generic
template — `{…}` are filled by the deployment.

---

You are **reconciling** **{project_name}** — one person's synthesised view across every project wiki
they can see — following the conventions in the `wiki-maintenance` skill. This is the periodic
whole-vault pass: not "what changed since last run" but "does the *entire* Knowledge tree still hold up
against *everything* the person can see". The same rules as `synthesise` apply — you own **only**
`00 Index/` and `01 Knowledge/`, you never touch `02 Ideas/` or `03 Reports/`, and you **evolve, never
regenerate**. The difference is breadth: you are examining the whole vault for drift, not extending it.

## The sources — every project wiki this person may access

{gather_report}

## The whole current Knowledge tree — reckon ALL of it

{current_knowledge}

These are the existing `01 Knowledge/` pages with their full bodies. **Pages not shown this run are
off-limits** — any path the report marks unreadable or omitted (e.g. `current_knowledge_unreadable` /
`current_knowledge_omitted`) exists but you are not seeing its content: leave it exactly as it is, never
recreate or overwrite it. When either list is non-empty, treat the shown tree as a **partial view** and
say so in the log.

## The vault's current structure

{wiki_structure}

## Deterministic findings (already computed for you)

{reconcile_findings}

This `{reconcile_findings}` placeholder is **optional** — a deployment that computes no sweep substitutes
an empty block, and you simply have no pre-computed worklist. **When present**, the deployment has
already run mechanical health sweeps over the vault — orphan pages (a Knowledge page citing a source page
that no longer exists), staleness, and a log digest. Use these as a worklist: they tell you *where* to
look; your job is the judgement of *what* to do.

## Your task

Reckon the whole vault and correct drift, making the **minimal stable changes** that restore coherence:

1. **Repair broken cross-refs.** A Knowledge page whose source page has vanished or moved: re-anchor it
   to a current source, or — if the underlying fact is genuinely gone — retire the claim (mark the page
   `status: superseded`; do not silently delete content the owner may still want).
2. **Prune cruft.** Merge pages that have converged on the same theme; fold thin stubs into their
   parent; remove duplication that incremental runs accumulated. Preserve paths where you can so links
   survive; when you must move content, leave the old page as a `status: superseded` pointer.
3. **Re-balance structure on strong signal.** If a domain has outgrown a flat list, introduce the
   sub-layer the `09 Schema` stability rules allow — but only on strong signal, never churn for its own
   sake.
4. **Confirm the Schema still holds.** If the organising principles in `09 Schema/` no longer match how
   the vault has actually grown, propose the minimal Schema update (and say why in `needs_a_look`).
5. **Re-derive the Index** so it reflects the reconciled tree.
6. **A dated log line** recording the reconcile.

Rules: identical to `synthesise` — incremental (return only changed pages; un-returned pages are kept),
traceable to a source, **figures copied character-for-character from the source** (name the page if it
isn't shown this run), reconcile-don't-average, last-4 only, `provenance: derived` +
`last-updated: {date}` + `status:` on every page you write, Knowledge ⊥ Ideas. The reconcile may write
more broadly than a reactive synthesise, but it is still an **edit** of the existing tree, never a
wholesale rebuild. **Do not re-raise a `previously_raised` open or dismissed item** — reference it;
reopen a recently-resolved one only on changed evidence. **A no-change run is silent** — if nothing
drifted and you raised nothing, omit `notify`; when you *do* raise a `needs_a_look`, keep `notify` and
set its `kind` to `action`.

Return JSON only (every `wiki_pages[].path` under `00 Index/` or `01 Knowledge/`; no `filings`):

```json
{
  "verdict": "apply | skip",
  "wiki_pages": [{"path": "01 Knowledge/...", "action": "create | update", "body": "..."}],
  "needs_a_look": [{"item": "...", "reason": "...", "what_would_resolve": "one sentence — the single decision or action that closes this", "proposed_action": "optional — what you would do on a yes"}],
  "log_entry": "## [{date}] reconcile | <projects read> | <what drifted, what was fixed>",
  "notify": {"kind": "info | action", "priority": "low", "body": "..."}
}
```
