# synthesise prompt (single-shot, reactive, full re-synthesis)

The reasoning-stage template for the `synthesise` job. Filled with the access-scoped gather report,
it returns structured JSON a deterministic write stage applies to the identity's vault. Generic
starting template — `{…}` are filled by the deployment. The deployment guarantees the report contains
**only** wikis this identity may access; the template's job is coherence, not access control.

---

You are writing **{project_name}** — one person's synthesised view across every project wiki they can
see — following the conventions in the `wiki-maintenance` skill. This vault is **fully generated**:
you rebuild it wholesale each run, and no page in it is human-edited. It is the **only** place
cross-project links are allowed; you read project wikis, you never write into them.

## The sources — the project wikis this person may access

{gather_report}

The report lists each accessible project (name, id, its wiki's pages with excerpts) and a mechanical
**link backbone**: for each entity/concept, the project pages it appears in. The backbone is
ground truth for *where things appear* — every cross-project link you write must be supported by it
or by page content actually shown above. Never invent a page, an entity, or a connection.

## The vault's current structure

The vault lives under `{wiki_dir}/`.

{wiki_structure}

## Your task

Re-synthesise the vault as a coherent whole — a second brain, not a file listing:

1. **An entry page** (the vault's index): who this view is for is already known — open with the
   handful of things that currently matter most across their projects, then a navigable map of the
   vault's pages.
2. **Theme pages.** Where material from different projects genuinely belongs together (the same
   venture seen from two folders, a shared obligation, one timeline crossing projects), write a page
   that weaves it together and **names which project each strand came from**, linking each claim to
   its source page (`project id` + wiki-relative path — never an absolute filesystem path).
3. **Entity pages.** For people, organisations and things that appear in more than one project (use
   the backbone), one page each: what each project knows about them, reconciled — and where projects
   *disagree*, say so explicitly rather than silently picking one.
4. **Connections worth surfacing.** A small section for non-obvious links you found (a deadline in
   one project colliding with a commitment in another; the same counterparty under two names). Only
   real, sourced connections — an empty section is better than a stretched one.
5. **A dated log line** recording the pass.

Rules:

- **Traceable, always.** Every claim links to a source page shown in the report. If you cannot point
  to a source, leave the claim out.
- **Reconcile, don't average.** Conflicting claims between projects are surfaced as conflicts.
- **Sensitive identifiers, last-4 only**, exactly as the source pages already hold them.
- **Authored notes carry through.** Source material marked `provenance: manual` is owner-asserted and
  authoritative — represent it faithfully; never contradict it from derived material (surface a
  conflict instead).
- Give every page frontmatter: `provenance: derived`, `last-updated: {date}`, `status: current`.
- Keep the vault navigable and small: a reader should reach anything in two hops from the entry page.
  Prune by omission — any page you do not return may be removed by the deployment.

Return JSON only, matching this shape (every `wiki_pages[].path` must start with `{wiki_dir}/`; this
archetype never files items, so there is no `filings` field):

```json
{
  "verdict": "apply | skip",
  "wiki_pages": [{"path": "{wiki_dir}/...", "action": "create | update", "body": "..."}],
  "needs_a_look": [{"item": "...", "reason": "..."}],
  "log_entry": "## [{date}] synthesise | <projects read> | <short summary>",
  "notify": {"kind": "info", "priority": "low", "body": "..."}
}
```
