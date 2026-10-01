#!/usr/bin/env python3
"""Readiness for hand-off: is the prepared folder in the shape an onboarding flow relies on?

Read-only on the folder. Every check reports a count (zero included), a state, a finding or a named not-verified
state, never silence. Every finding is listed in `findings` as [check, what], `check` being the report key that
holds it, and every named not-verified state in `not_verified` the same way: it is not a finding, but it is not a
pass either, and the operator reads it.

- manifest: live, departed, migrating, root strays, redundant copies, hygiene and unconverted iWork entries, and the
  items on disk (reported, not findings); `live_paths_missing`, live entries whose current path is gone, is a
  finding (the manifest is not current: re-audit);
- records: every live hashed document (those `extract.py` reads) has an extract record and a card, each card's
  category is one the rulebook allows, every extract record's path agrees with the manifest (else the finding
  names the repair, `extract.py repath`), and no card names an isolation term its own source lacks (not verified
  without --terms). A count above zero is one finding;
- isolation: per engine, the canary result `isolation.py canary --out` wrote to `<work>/state/canary-<engine>.json`:
  `passed`, `failed: ...` (a finding) or `not run: ...` (not verified);
- wiki: `wiki.py check`, as it reports; its problems are one finding, its not-verified states are listed;
- wiki_handoff: the rationale file exists (`check` does not count it missing, since drafting agents run `check`
  before it is assembled), and every page is accepted: each page `check` does not report `accepted` is one
  finding, naming the page, its state and why (a refused page included), except a page `check` lists in
  `acceptance_not_verified` (its professional and contract cannot be read), whose acceptance is not verified;
- rulebook: `CLAUDE.md` and `AGENTS.md` present, identical and naming the wiki folder; scratch: no folder in
  `_Audit/` but the prepared folder's own (`plans`, `extract`, `cards`);
- handoff_contract, each "ok", "finding: ..." or "not verified: ...": the wiki folder is `<folder name> Wiki`; the
  fixed pages 00 Index, 01 Deadlines, 90 Schema and 91 Log exist; derived pages hold nothing hand-written and
  recurring dates live in page frontmatter (see `deadline_items`); the rulebook reserves the deployment's rulebook
  filenames and routes no new file to the migrations folder; both settings twins present and fresh.

Numbered sections are held by `check`: a page outside every Layout section of the compiled Schema is one of its
problems. Exit 0 when nothing is found, 1 on any finding, 2 on a tool error (a missing or malformed manifest, card,
extract record or canary result, or a crash).

    python3 readiness.py --root R [--terms F] [--manifest M] [--out <json>]
"""
import collections
import json
import os
import re
import shlex
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cards as C  # noqa: E402
import common  # noqa: E402
import isolation  # noqa: E402
import wiki as W  # noqa: E402

FIXED = ("00 Index/00 Index.md", "01 Deadlines/01 Deadlines.md", "90 Schema/90 Schema.md", "91 Log/91 Log.md")
DEADLINES = FIXED[1]
AUDIT_DIRS = ("plans", "extract", "cards")  # the folders a prepared folder's _Audit/ holds; any other is scratch
CANARY_ENGINES = ("agy", "codex")  # isolation.py canary --engine
FRONTMATTER = re.compile(r"---\n(.*?)\n---\n", re.S)  # as wiki.py check reads it
DAY = re.compile(r"(?<![0-9])[0-9]{4}-([0-9]{2}-[0-9]{2})(?![0-9])")  # a dated deadline; group 1 its MM-DD
YEARLY = re.compile(r"(?<![0-9-])((?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01]))(?![0-9-])")  # a recurring MM-DD
RECURRING_ITEM = re.compile(r"\{\s*date:\s*[\"']?([0-9-]+)[\"']?\s*(?:,.*)?\}")  # {date: MM-DD, note: ...}
SAYS_NOTHING = re.compile(r"(?i)[\s>*_`|-]*(none|nothing|n/?a)?[\s.*_`|-]*")
SAMPLE = 5


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def sample(items):
    shown = "; ".join(str(x) for x in items[:SAMPLE])
    return shown + (" and %d more" % (len(items) - SAMPLE) if len(items) > SAMPLE else "")


def split_page(text):
    """(frontmatter, body, the number of lines before the body)."""
    m = FRONTMATTER.match(text)
    return (W.parse_fm(m.group(1)), text[m.end():], text[:m.end()].count("\n")) if m else ({}, text, 0)


# ------------------------------------------------------------------------------------ derived pages

def frontmatter_dates(fm):
    """(the YYYY-MM-DD dates in `deadline` and `deadlines`, the MM-DD dates in `recurring`, the `recurring` entries
    not in the form {date: MM-DD, note}) of one page's frontmatter."""
    days, yearly, bad = set(), set(), []
    for key in ("deadline", "deadlines"):
        v = fm.get(key)
        for it in v if isinstance(v, list) else [v] if v else []:
            d = str(it.get("date") if isinstance(it, dict) else it).strip().strip("\"'")
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", d):
                days.add(d)
    v = fm.get("recurring")
    for it in v if isinstance(v, list) else [v] if v else []:
        m = RECURRING_ITEM.fullmatch(it.strip()) if isinstance(it, str) else None
        d = it.get("date") if isinstance(it, dict) else m.group(1) if m else None
        if d and YEARLY.fullmatch(d):
            yearly.add(d)
        else:
            bad.append(it if isinstance(it, str) else json.dumps(it, ensure_ascii=False))
    return days, yearly, bad


def deadline_items(wiki, pages, ws):
    """(derived pages hold nothing hand-written, recurring dates in frontmatter): each "ok", "finding: ..." or
    "not verified: ...". The rule is wiki-maintenance's "Deadlines are derived, not authored"
    (../../wiki-maintenance/SKILL.md#rules-that-keep-it-safe), read through the frontmatter keys its roll-up reads
    (#canonical-frontmatter--the-keys-the-deterministic-sweeps-read, including which pages the sweeps skip). It
    fixes no headings and asks for no list beyond the dates, so none is checked: only that every date on the
    Deadlines roll-up comes from a page's frontmatter, that the roll-up carries every one of them, and that an empty
    roll-up says why. Another page the Schema marks derived (an open-questions list) is built from the pages in a
    way no date shows, so it is named as not verified."""
    if DEADLINES not in pages:
        why = "not verified: no %s (fixed_pages reports it)" % DEADLINES
        return why, why
    derived_dirs = tuple("%s %s/" % (s["number"], s["name"]) for s in (ws or {}).get("sections", []) if s["derived"])
    others = [p for p in pages if p != DEADLINES and p.startswith(derived_dirs)] if derived_dirs else []
    days, yearly = collections.defaultdict(list), collections.defaultdict(list)  # date: the pages holding it
    swept_days, swept_yearly, bad, any_derived = set(), set(), [], False
    for p in pages:
        if p == DEADLINES or p in others:
            continue
        fm, _body, _n = split_page(read(os.path.join(wiki, *p.split("/"))))
        d, y, b = frontmatter_dates(fm)
        for x in d:
            days[x].append(p)
        for x in y:
            yearly[x].append(p)
        if fm.get("status") != "superseded" and fm.get("provenance") not in ("manual", "calendar"):
            swept_days |= d
            swept_yearly |= y
        bad += ["%s: %s" % (p, e) for e in b]
        any_derived = any_derived or fm.get("provenance") == "derived"
    _fm, body, offset = split_page(read(os.path.join(wiki, *DEADLINES.split("/"))))
    hand, hand_yearly, shown_days, shown_yearly = [], [], set(), set()
    for n, line in enumerate(body.splitlines(), offset + 1):
        for m in DAY.finditer(line):
            shown_days.add(m.group(0))
            shown_yearly.add(m.group(1))
            if m.group(0) not in days and m.group(1) not in yearly:  # a recurring date may show as its next day
                hand.append("line %d: %s" % (n, m.group(0)))
        for m in YEARLY.finditer(line):
            shown_yearly.add(m.group(1))
            if m.group(1) not in yearly:
                hand_yearly.append("line %d: %s" % (n, m.group(1)))
    derived = []
    if hand:
        derived.append("%s holds %d date(s) no page's frontmatter carries (%s)" % (DEADLINES, len(hand), sample(hand)))
    missing = ["%s (%s)" % (d, ", ".join(days[d])) for d in sorted(swept_days - shown_days)]
    if missing:
        derived.append("%s lacks %d page deadline(s) (%s)" % (DEADLINES, len(missing), sample(missing)))
    says = [line for line in body.splitlines() if line.strip() and not line.lstrip().startswith("#")
            and not SAYS_NOTHING.fullmatch(line)]
    if not days and not yearly and any_derived and not says:
        derived.append("%s is an empty roll-up that does not say why" % DEADLINES)
    recurring = []
    if hand_yearly:
        recurring.append("%s holds %d yearly date(s) no page's recurring: list carries (%s)"
                         % (DEADLINES, len(hand_yearly), sample(hand_yearly)))
    if bad:
        recurring.append("%d recurring: entr(ies) not {date: MM-DD, note} (%s)" % (len(bad), sample(bad)))
    missing = ["%s (%s)" % (d, ", ".join(yearly[d])) for d in sorted(swept_yearly - shown_yearly)]
    if missing:
        recurring.append("%s lacks %d recurring date(s) (%s)" % (DEADLINES, len(missing), sample(missing)))
    derived_item = ("finding: " + "; ".join(derived) if derived else
                    "not verified: %s (derived, not a Deadlines roll-up)" % sample(others) if others else "ok")
    return derived_item, "finding: " + "; ".join(recurring) if recurring else "ok"


# ------------------------------------------------------------------------------------ the hand-off contract

def contract(root, rb, settings_dir, ws, pages, rulebook_text):
    items = collections.OrderedDict()
    wiki = os.path.join(root, rb["wiki_dir"])
    folder_wiki = os.path.basename(root) + " Wiki"
    items["wiki_folder_named_after_folder"] = "ok" if rb["wiki_dir"] == folder_wiki else \
        "finding: the wiki folder is %r, not %r" % (rb["wiki_dir"], folder_wiki)
    missing = [p for p in FIXED if p not in pages]
    items["fixed_pages"] = "ok" if not missing else "finding: missing %s" % ", ".join(missing)
    items["derived_pages_hold_nothing_hand_written"], items["recurring_dates_in_frontmatter"] = \
        deadline_items(wiki, pages, ws)
    if rulebook_text is None:
        items["rulebook_reserves_rulebook_filenames"] = items["new_files_routed_within_folder"] = \
            "not verified: CLAUDE.md missing (rulebook.present reports it)"
    else:
        unreserved = [n for n in common.RULEBOOK_FILES if n not in rulebook_text]
        items["rulebook_reserves_rulebook_filenames"] = "ok" if not unreserved else \
            "finding: the rulebook does not reserve %s" % ", ".join(unreserved)
        routes_out = [line.strip() for line in rulebook_text.splitlines() if rb["migrations_dir"] + "/" in line
                      and re.search(r"(?i)new file|dropped|goes to|go to", line)]
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


# ------------------------------------------------------------------------------------ the other checks

def manifest_counts(root, man, ents, summary_path):
    live = {h: e for h, e in ents.items() if "departed" not in e.get("flags", [])}
    summ = W.read_object(summary_path) if os.path.exists(summary_path) else {}
    gone = sorted(e["current_path"] for e in live.values()
                  if not os.path.lexists(os.path.join(root, e["current_path"])))
    return live, gone, collections.OrderedDict([
        ("generated_at", man.get("generated_at")), ("live_entries", len(live)),
        ("departed_entries", len(ents) - len(live)),
        ("migrating", sum("migrating" in e.get("flags", []) for e in live.values())),
        ("root_strays", sum("root_stray" in e.get("flags", []) for e in live.values())),
        ("redundant_copies", sum(1 for e in live.values() for c in e.get("copies", [])
                                 if c.get("kind") == "redundant")),
        ("hygiene", sum("hygiene" in e.get("flags", []) for e in live.values())),
        ("unconverted_iwork", sum("unconverted" in e.get("flags", []) for e in live.values())),
        ("items_on_disk", summ.get("items", "not verified: no summary.json beside the manifest")),
        ("live_paths_missing", len(gone))])


def record_checks(root, rb, live, evidence):
    """{check: [what, ...]} for the records, and each check's count or state."""
    audit = os.path.join(root, "_Audit")
    xdir, cdir = os.path.join(audit, "extract"), os.path.join(audit, "cards")
    found = collections.OrderedDict((k, []) for k in ("missing_extracts", "missing_cards", "bad_category",
                                                      "extract_paths_stale", "contamination"))
    for h, e in sorted(live.items(), key=lambda kv: kv[1]["current_path"]):
        if not e.get("hashed"):
            continue  # counted only, never read: extract.py makes no record for it
        path = e["current_path"]
        card = W.load_card(cdir, h)
        x = W.load_extract(xdir, h, os.path.join(cdir, h + ".json")) \
            if os.path.exists(os.path.join(xdir, h + ".json")) else None
        if x is None:
            found["missing_extracts"].append(path)
        elif x.get("path") != path:
            found["extract_paths_stale"].append("%r is now %r" % (x.get("path"), path))
        if card is None:
            found["missing_cards"].append(path)
            continue
        if card.get("category") not in rb["card_categories"]:
            found["bad_category"].append("%s: %r" % (path, card.get("category")))
        if evidence and x is not None:
            blob = json.dumps({k: v for k, v in card.items() if k != "card_meta"}, ensure_ascii=False)
            if isolation.contamination(blob, C.full_text(x), evidence):
                found["contamination"].append(path)  # the terms themselves are never written out
    counts = collections.OrderedDict((k, len(v)) for k, v in found.items())
    if not evidence:
        counts["contamination"] = "not verified: no --terms"
    return found, counts


def canary(work, engine):
    """passed, failed: ... or not run: ..., from the result isolation.py canary wrote."""
    rel = os.path.join("state", "canary-%s.json" % engine)
    path = os.path.join(work, rel)
    if not os.path.exists(path):
        return "not run: no %s in the work directory (isolation.py canary --out)" % rel
    res = W.read_object(path)
    if res.get("engine") != engine or not isinstance(res.get("pass"), bool):
        raise common.ToolError("%s is not a canary result for %s; run isolation.py canary again" % (path, engine))
    if res["pass"]:
        return "passed"
    why = ("%s isolation term(s) in the engine's reply" % res.get("hits") if "reply" in res
           else "the engine gave no answer (%s)" % res.get("error", "no error recorded"))
    return "failed: %s, checked %s" % (why, res.get("checked_at"))


def repath_command(root, a):
    cmd = ["extract.py", "repath", "--root", root]
    for flag, value in (("--settings-dir", a.settings_dir), ("--work", a.work), ("--manifest", a.manifest)):
        if value:
            cmd += [flag, os.path.realpath(value)]
    return " ".join(shlex.quote(x) for x in cmd + ["--apply"])


def main():
    ap = common.base_args("Readiness for hand-off")
    ap.add_argument("--terms", help="the operator's isolation terms file (contamination is not verified without it)")
    ap.add_argument("--out")
    ap.add_argument("--manifest", help="default <root>/_Audit/manifest.json")
    a = ap.parse_args()
    # A diagnosis, not a gate: a stale or unpinned twin is a hand-off finding below, so the settings are read here
    # without trusting them (as settings.py check does). A malformed rulebook.json still fails loud.
    root, settings_dir, work = common.resolve(a, verify=False)
    rb = common.load_rulebook(root, settings_dir, verify=False)
    mpath, ents = W.load_manifest(root, a.manifest)
    evidence = isolation.load_terms(a.terms) if a.terms else None
    audit = os.path.join(root, "_Audit")
    wiki = os.path.join(root, rb["wiki_dir"])
    pages = W.wiki_pages(wiki)
    try:
        ws = common.load_wiki_schema(root, settings_dir, required=False)
    except common.ToolError:
        ws = None  # a stale or malformed twin: handoff_contract.settings_wiki_schema_json reports it
    claude, agents = (os.path.join(root, n) for n in ("CLAUDE.md", "AGENTS.md"))
    rulebook_text = read(claude) if os.path.exists(claude) else None

    out = collections.OrderedDict()
    live, gone, out["manifest"] = manifest_counts(root, W.read_object(mpath), ents,
                                                  os.path.join(os.path.dirname(mpath), "summary.json"))
    found, out["records"] = record_checks(root, rb, live, evidence)
    out["isolation"] = {"canary": collections.OrderedDict((e, canary(work, e)) for e in CANARY_ENGINES)}
    out["wiki"] = W.check_result(root, rb, ents, settings_dir=settings_dir)
    rows = out["wiki"]["acceptance_pages"]
    cannot_read = set(out["wiki"]["acceptance_not_verified"])  # no readable professional and contract to judge by
    unverifiable = [row for row in rows if row[0] in cannot_read and row[1] == "not recorded"]
    not_accepted = [row for row in rows if row[1] != "accepted" and row not in unverifiable]  # a refusal stands
    out["wiki_handoff"] = collections.OrderedDict([
        ("rationale_file", "finding: _Audit/wiki-rationale.md is missing; wiki.py rationale assembles it from the "
                           "drafters' returns" if out["wiki"]["rationale"] == "not recorded" else "ok"),
        ("pages_accepted", "%d/%d" % (len(rows) - len(not_accepted) - len(unverifiable), len(rows))),
        ("pages_not_accepted", len(not_accepted)), ("pages_not_verified", len(unverifiable))])
    missing = [os.path.basename(p) for p in (claude, agents) if not os.path.exists(p)]
    out["rulebook"] = collections.OrderedDict([
        ("present", "finding: missing %s" % " and ".join(missing) if missing else "ok"),
        ("copies_identical", "not verified: %s missing" % " and ".join(missing) if missing
         else common.sha256_file(claude) == common.sha256_file(agents)),
        ("names_wiki_folder", "not verified: CLAUDE.md missing" if rulebook_text is None
         else rb["wiki_dir"] in rulebook_text)])
    out["scratch"] = {"left_in_audit": sorted(d for d in os.listdir(audit) if d not in AUDIT_DIRS
                                              and os.path.isdir(os.path.join(audit, d)))
                      if os.path.isdir(audit) else []}
    out["handoff_contract"] = contract(root, rb, settings_dir, ws, pages, rulebook_text)

    findings, unverified = [], []
    if gone:
        findings.append(["manifest.live_paths_missing", "%d live entr(ies) whose current path is gone (%s); "
                         "re-audit (audit.py)" % (len(gone), sample(gone))])
    if isinstance(out["manifest"]["items_on_disk"], str):
        unverified.append(["manifest.items_on_disk", out["manifest"]["items_on_disk"]])
    what = {"missing_extracts": "live document(s) with no extract record",
            "missing_cards": "live document(s) with no card",
            "bad_category": "card(s) with a category the rulebook does not allow",
            "extract_paths_stale": "extract record(s) whose path the manifest no longer holds",
            "contamination": "card(s) naming an isolation term their own source lacks"}
    for key, hits in found.items():
        if hits:
            fix = "; repath them: %s" % repath_command(root, a) if key == "extract_paths_stale" else ""
            findings.append(["records." + key, "%d %s (%s)%s" % (len(hits), what[key], sample(hits), fix)])
    if isinstance(out["records"]["contamination"], str):
        unverified.append(["records.contamination", out["records"]["contamination"]])
    for engine, state in out["isolation"]["canary"].items():
        if state.startswith("failed"):
            findings.append(["isolation.canary." + engine, state])
        elif state.startswith("not run"):
            unverified.append(["isolation.canary." + engine, state])
    if out["wiki"]["problems"]:
        findings.append(["wiki.problems", "wiki.py check reports %d problem(s)" % out["wiki"]["problems"]])
    for key, value in out["wiki"].items():
        for k, v in (value.items() if isinstance(value, dict) else [(None, value)]):
            if isinstance(v, str) and v.startswith("not verified"):
                unverified.append([".".join(x for x in ("wiki", key, k) if x), v])
    if out["wiki_handoff"]["rationale_file"] != "ok":
        findings.append(["wiki_handoff.rationale_file", out["wiki_handoff"]["rationale_file"]])
    for page, state, why in not_accepted:
        findings.append(["wiki_handoff.pages_not_accepted", "%s: %s (%s)" % (page, state, why)])
    if unverifiable:
        unverified.append(["wiki_handoff.pages_not_verified", "%d page(s) whose acceptance cannot be judged: their "
                           "professional and contract cannot be read (%s)"
                           % (len(unverifiable), sample([row[0] for row in unverifiable]))])
    said = {"copies_identical": "CLAUDE.md and AGENTS.md differ; copy CLAUDE.md over AGENTS.md",
            "names_wiki_folder": "the rulebook does not name the wiki folder %r" % rb["wiki_dir"]}
    for key, value in out["rulebook"].items():
        if value is False or isinstance(value, str) and value.startswith("finding"):
            findings.append(["rulebook." + key, said[key] if value is False else value])
        elif isinstance(value, str) and value.startswith("not verified"):
            unverified.append(["rulebook." + key, value])
    if out["scratch"]["left_in_audit"]:
        findings.append(["scratch.left_in_audit", "folders left in _Audit/: %s" % sample(
            out["scratch"]["left_in_audit"])])
    for key, value in out["handoff_contract"].items():
        if value.startswith("finding"):
            findings.append(["handoff_contract." + key, value])
        elif value.startswith("not verified"):
            unverified.append(["handoff_contract." + key, value])
    out["findings"], out["not_verified"] = findings, unverified
    out["summary"] = collections.OrderedDict([("findings", len(findings)), ("not_verified", len(unverified))])
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out:
        common.Writer(root if a.read_only_root else None).text(a.out, text)
    print(text)
    return 1 if findings else 0


def run():
    """A crash is a tool error (exit 2), never read as findings (exit 1)."""
    try:
        common.run_main(main)
    except Exception:  # noqa: BLE001 (anything not caught above is a crash)
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    run()
