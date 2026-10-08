# reconcile prompt (single-shot, periodic, **whole-vault**)

The reasoning-stage template for the `reconcile` job — the periodic twin of `synthesise`. Same write
contract (incremental, fenced to the derived areas), but it reckons the **whole** vault against **all**
accessible sources rather than the slice a single source change touched. It exists because the Knowledge
area is incrementally maintained and can therefore drift (the twin rule in `ARCHITECTURE.md`). Generic
template — `{…}` are filled by the deployment.
The optional `migration` field on a `needs_a_look` item carries a proposed cross-project migration, and
the optional `rationale` field on a `wiki_pages[]` entry the page's rationale block, exactly as in
`synthesise` (see the archetype's README).

---

You are **reconciling** **{project_name}** — one person's synthesised view across every project wiki
they can see — following the conventions in the `wiki-maintenance` skill. This is the periodic
whole-vault pass: not "what changed since last run" but "does the *entire* Knowledge tree still hold up
against *everything* the person can see". The same rules as `synthesise` apply — you own **only**
`00 Index/` and `01 Knowledge/`, you never touch `02 Ideas/` or `03 Reports/`, and you **evolve, never
regenerate**. The difference is breadth: you are examining the whole vault for drift, not extending it.

## The sources — every project wiki this person may access

{gather_report}

The report also carries, per accessible project, every **owner confirmation record** in its folders,
by folder-relative path with its text, and names any omitted or unreadable this run (say so in the log
line). A record is the owner's statement, with the authority of `provenance: manual` content; a
project page carries its fact as a `derived` line citing it. You never write a record anywhere.

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
that no longer exists), staleness, pages with no `kind:` or no rationale block, pages whose acceptance
is not recorded or refused, and a log digest. Use these as a worklist: they tell you *where* to look;
your job is the judgement of *what* to do.

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
5. **Keep every page in its voice.** Every Knowledge page carries a `kind:` that `09 Schema`'s Page
   kinds table names, and reads as its professional, to its kind's contract: the kind's fixed
   professional, or, where the kind delegates, the one the page names in `professional:`, which you
   keep rather than re-choose. A page with no kind, a delegated page with no professional, one that
   has slid into generic prose, or one the findings name as last written before its kind's contract
   changed, is rewritten in its voice and to its contract with a `rationale` whose `changed` line says
   so; a page that fits no kind is proposed in `needs_a_look`, not re-kinded. Where the findings name
   the pages with no rationale block, or the structure shows the headings of
   `_Audit/wiki-rationale.md`, count them; where the findings name the pages whose acceptance is not
   recorded or refused, count those too; give each count in the log line, and for a coverage shown
   neither way say so. Never invent a count. An unaccepted page is not yours to accept: name it, and
   leave the verdict to the review the deployment runs.
6. **Re-derive the Index** so it reflects the reconciled tree, as the chief of staff's briefing note.
7. **Proposed migrations, when the sources show one** (optional), exactly as `synthesise` sets out:
   one `needs_a_look` item per matter with its `migration` filled, for the owner to make by hand or decline.
   Seeing every accessible project at once, this pass is where files one project holds for another
   are easiest to spot; never re-propose one the ledger holds as open or dismissed.
8. **A dated log line** recording the reconcile.

Rules: identical to `synthesise` — incremental (return only changed pages; un-returned pages are kept),
traceable to a source, **figures copied character-for-character from the source** (name the page if it
isn't shown this run), reconcile-don't-average, full source-supported identifiers by default, `provenance: derived` +
`last-updated: {date}` + `status:` + `kind:` on every page you write, and `professional:` where the
kind delegates it, the voice tone only (the facts,
sources and format rules the same whoever the page speaks as; no page blends two voices), a `rationale`
on every page you create or reshape, Knowledge ⊥ Ideas. **A record is the owner's word**, with the
authority `wiki-maintenance` gives it and as `synthesise` sets out: a Knowledge page that disagrees
with an owner confirmation record is brought back into line with the record, never towards a document
that does not exist, and nothing a record settles is re-raised. The reconcile may write
more broadly than a reactive synthesise, but it is still an **edit** of the existing tree, never a
wholesale rebuild. **An observation is a wiki write, not an alert** — a `needs_a_look` carries an `owner_action` only when there is a physical act the owner must perform that this system cannot (the exact file or place, in one sentence); otherwise `owner_action` is null and the item is recorded, not queued, because the page you just wrote is where it will be read. **If you cite an open item, supersede it or say why both stand.** Both rules are stated in full in the archetype's other template. **Do not re-raise a `previously_raised` open or dismissed item** — reference it;
reopen a recently-resolved one only on changed evidence. **A no-change run is silent** — if nothing
drifted and you raised nothing, omit `notify`; when you *do* raise a `needs_a_look`, keep `notify` and
set its `kind` to `action`.

Return JSON only (every `wiki_pages[].path` under `00 Index/` or `01 Knowledge/`; no `filings`):

```json
{
  "verdict": "apply | skip",
  "wiki_pages": [{"path": "01 Knowledge/...", "action": "create | update", "body": "...", "rationale": {"reader_and_use": "...", "professional_lens": "<professional>; questions answered in order: 1. ... 2. ...", "shape": "...", "changed": "what this version changed", "left_out": "nothing, OR what and why"}}],
  "needs_a_look": [{"item": "...", "reason": "...", "owner_action": "null, OR one sentence naming the physical act only the owner can perform: name the exact file or place", "what_would_resolve": "one sentence: the single decision or action that closes this", "proposed_action": "optional: what you would do on a yes", "migration": {"from_project": "<project id>", "to_project": "<project id>", "paths": ["<folder-relative path the from_project's page cites>"], "pages": ["<project id>: <wiki-relative page path>"]}}],
  "log_entry": "## [{date}] reconcile | <projects read> | <what drifted, what was fixed; pages with no rationale block: N; not accepted: N; or: coverage not shown>",
  "notify": {"kind": "info | action", "priority": "low", "body": "..."}
}
```

`migration` is optional: include it only on an item that proposes a migration (task 7), and leave it
out of every other item. `rationale` is required on a `create`, on an `update` that changes the
page's kind, professional or shape, and on an `update` that rewrites the page to a changed contract
(task 5), and omitted on an update that only integrates a fact.
