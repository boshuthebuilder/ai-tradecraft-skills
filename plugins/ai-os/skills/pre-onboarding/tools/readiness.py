#!/usr/bin/env python3
"""Readiness for hand-off: is the prepared folder in the shape an onboarding flow relies on?

Read-only on the folder. Every check reports a count (zero included) or a named not-verified state, never silence:

- manifest: live, departed, migrating, root strays, redundant copies, hygiene, unconverted;
- records: every live document has an extract record and a card; card categories valid; extract paths agree with
  the manifest; contamination against the operator's isolation terms (not verified without `--terms`);
- wiki: the wiki checks (pages, frontmatter, sources, links, em dashes, coverage, rationale, acceptance);
- rulebook: `CLAUDE.md` and `AGENTS.md` identical and naming the wiki folder; scratch folders left in `_Audit/`;
- hand-off contract: wiki at `<folder name> Wiki/` with 00 Index, 01 Deadlines, 90 Schema, 91 Log; derived pages
  hold nothing hand-written; recurring dates in frontmatter; the deployment's rulebook filenames reserved; new files
  routed within the folder (migrations are the owner's cross-project synthesis to propose); settings twins fresh.

    python3 readiness.py --root R [--terms F] [--out <json>]
"""
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cards as C  # noqa: E402
import common  # noqa: E402
import isolation  # noqa: E402
import wiki as W  # noqa: E402

ROLLUP_HEADINGS = {"Deadlines", "01 Deadlines", "Upcoming", "Past", "Could not read", "Every year"}
FIXED = ("00 Index/00 Index.md", "01 Deadlines/01 Deadlines.md", "90 Schema/90 Schema.md", "91 Log/91 Log.md")


def contract(root, rb, settings_dir):
    items = collections.OrderedDict()
    wiki = os.path.join(root, rb["wiki_dir"])
    items["wiki_folder_named_after_folder"] = "ok" if rb["wiki_dir"] == os.path.basename(root) + " Wiki" \
        else "finding: %s" % rb["wiki_dir"]
    missing = [p for p in FIXED if not os.path.exists(os.path.join(wiki, p))]
    items["fixed_pages"] = "ok" if not missing else "finding: missing %s" % missing
    dl = os.path.join(wiki, FIXED[1])
    if os.path.exists(dl):
        heads = re.findall(r"^#{1,3} (.+?)\s*$", open(dl, encoding="utf-8").read(), re.M)
        extra = [h for h in heads if h not in ROLLUP_HEADINGS]
        recurring_fm = any("\nrecurring:" in open(p, encoding="utf-8").read()
                           for p in glob.glob(os.path.join(wiki, "**", "*.md"), recursive=True))
        body = open(dl, encoding="utf-8").read()
        hand_table = "Every year" in heads and not recurring_fm
        items["derived_pages_hold_nothing_hand_written"] = (
            "ok" if not extra and not hand_table else
            "finding: %s" % ("; ".join(["headings %s" % extra] if extra else []) +
                             ("recurring dates written by hand on 01 Deadlines, not in page frontmatter"
                              if hand_table else "")))
        del body
    else:
        items["derived_pages_hold_nothing_hand_written"] = "not verified: no Deadlines page"
    rbt = open(os.path.join(root, "CLAUDE.md"), encoding="utf-8").read() if os.path.exists(
        os.path.join(root, "CLAUDE.md")) else ""
    items["rulebook_reserves_rulebook_filenames"] = "ok" if all(n in rbt for n in common.RULEBOOK_FILES) else \
        "finding: not reserved: %s" % [n for n in common.RULEBOOK_FILES if n not in rbt]
    routes_out = [l.strip() for l in rbt.splitlines() if rb["migrations_dir"] + "/" in l
                  and re.search(r"(?i)new file|dropped|goes to|go to", l)]
    items["new_files_routed_within_folder"] = "ok" if not routes_out else \
        "finding: the rulebook routes new files to %s/ (%d line(s)); migrations are the owner's cross-project " \
        "synthesis to propose" % (rb["migrations_dir"], len(routes_out))
    try:
        common.load_rulebook(root, settings_dir, required=True)
        items["settings_rulebook_json"] = "ok"
    except common.ToolError as e:
        items["settings_rulebook_json"] = "finding: %s" % e
    try:
        common.load_wiki_schema(root, settings_dir, required=True)
        items["settings_wiki_schema_json"] = "ok"
    except common.ToolError as e:
        items["settings_wiki_schema_json"] = "finding: %s" % e
    return items


def main():
    ap = common.base_args("Readiness for hand-off")
    ap.add_argument("--terms", help="the operator's isolation terms file (contamination is not verified without it)")
    ap.add_argument("--out")
    ap.add_argument("--manifest")
    a = ap.parse_args()
    # A diagnosis, not a gate: a stale wiki-schema.json is a hand-off finding below. A stale rulebook.json is still
    # refused here, because the other checks read it.
    root, settings_dir, _work = common.resolve(a, verify=False)
    rb = common.load_rulebook(root, settings_dir)
    audit = os.path.join(root, "_Audit")
    mpath = a.manifest or os.path.join(audit, "manifest.json")
    man = json.load(open(mpath, encoding="utf-8"))
    ents = man["entries"]
    live = {h: e for h, e in ents.items() if "departed" not in e.get("flags", [])}
    summ_p = os.path.join(os.path.dirname(mpath), "summary.json")
    summ = json.load(open(summ_p, encoding="utf-8")) if os.path.exists(summ_p) else {}
    out = collections.OrderedDict()
    out["manifest"] = {"generated_at": man.get("generated_at"), "live_entries": len(live),
                       "departed_entries": len(ents) - len(live),
                       "migrating": sum("migrating" in e.get("flags", []) for e in live.values()),
                       "root_strays": sum("root_stray" in e.get("flags", []) for e in live.values()),
                       "redundant_copies": sum(1 for e in live.values() for c in e.get("copies", [])
                                               if c["kind"] == "redundant"),
                       "hygiene": sum("hygiene" in e.get("flags", []) for e in live.values()),
                       "unconverted_iwork": sum("unconverted" in e.get("flags", []) for e in live.values()),
                       "items_on_disk": summ.get("items", "not verified: no summary.json")}
    extract_dir, cards_dir = os.path.join(audit, "extract"), os.path.join(audit, "cards")
    evidence = isolation.load_terms(a.terms) if a.terms else None
    miss_x = [h for h in live if not os.path.exists(os.path.join(extract_dir, h + ".json"))]
    miss_c = [h for h in live if not os.path.exists(os.path.join(cards_dir, h + ".json"))]
    badcat, contam, stale = 0, 0, 0
    for h in live:
        cp, xp = os.path.join(cards_dir, h + ".json"), os.path.join(extract_dir, h + ".json")
        if not (os.path.exists(cp) and os.path.exists(xp)):
            continue
        c = json.load(open(cp, encoding="utf-8"))
        x = json.load(open(xp, encoding="utf-8"))
        badcat += c.get("category") not in rb["card_categories"]
        stale += x.get("path") != live[h]["current_path"]
        if evidence:
            blob = json.dumps({k: v for k, v in c.items() if k != "card_meta"}, ensure_ascii=False)
            contam += bool(isolation.contamination(blob, C.full_text(x), evidence))
    out["records"] = {"missing_extracts": len(miss_x), "missing_cards": len(miss_c), "bad_category": badcat,
                      "extract_paths_stale": stale,
                      "contamination": contam if evidence else "not verified: no --terms"}
    out["wiki"] = W.check_result(root, rb, ents)
    rbf = [os.path.join(root, f) for f in ("CLAUDE.md", "AGENTS.md")]
    if all(os.path.exists(p) for p in rbf):
        body = open(rbf[0], "rb").read()
        out["rulebook"] = {"copies_identical": body == open(rbf[1], "rb").read(),
                           "names_wiki_folder": rb["wiki_dir"].encode() in body}
    else:
        out["rulebook"] = "finding: rulebook file missing"
    out["scratch"] = {"left_in_audit": sorted(d for d in os.listdir(audit) if d.startswith(("_deploy", "_wikibuild")))}
    out["handoff_contract"] = contract(root, rb, settings_dir)
    findings = sum(1 for v in out["handoff_contract"].values() if str(v).startswith("finding"))
    out["summary"] = {"handoff_findings": findings, "wiki_problems": out["wiki"]["problems"],
                      "records_missing": len(miss_x) + len(miss_c)}
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out:
        common.Writer(root if a.read_only_root else None).text(a.out, text)
    print(text)
    return 1 if findings or out["wiki"]["problems"] or miss_x or miss_c else 0


if __name__ == "__main__":
    common.run_main(main)
