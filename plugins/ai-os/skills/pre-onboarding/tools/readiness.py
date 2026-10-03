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
  `records_for_no_page` (records naming a page the wiki no longer holds) is information only;
- rulebook: `CLAUDE.md` and `AGENTS.md` present, valid UTF-8, identical and naming the wiki folder; scratch: no
  folder in `_Audit/` but the prepared folder's own (`plans`, `extract`, `cards`);
- handoff_contract, each "ok", "finding: ..." or "not verified: ...": the wiki folder is `<folder name> Wiki`; the
  fixed pages 00 Index, 01 Deadlines, 90 Schema and 91 Log exist; derived pages hold nothing hand-written and
  recurring dates live in page frontmatter, with any other derived page not verified (see `deadline_items`); the
  rulebook reserves the deployment's rulebook filenames and routes no new file to the migrations folder (read by
  keyword, see `contract`); both settings twins present and fresh.

Numbered sections are held by `check`: a page outside every Layout section of the compiled Schema is one of its
problems. Exit 0 when nothing is found, 1 on any finding, 2 on a tool error (a missing or malformed manifest, such
as a live entry without `hashed` true or false, card, extract record or canary result, or a crash).

    python3 readiness.py --root R [--terms F] [--manifest M] [--out <json>]
"""
import collections
import datetime
import json
import os
import re
import shlex
import sys
import time
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
DAY = re.compile(r"(?<![0-9])[0-9]{4}-[0-9]{2}-[0-9]{2}(?![0-9])")  # a dated deadline, as the roll-up writes it
ISO_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
MARK = r"[*_`]*"  # emphasis or code around a date
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december")
# A yearly date as written: MM-DD, month first, or a day with an English month name ("5 April", "April 5",
# "5th Apr"), the form a roll-up shows to its reader.
YEARLY = r"[0-9]{2}-[0-9]{2}(?![0-9-])|[0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?|[A-Za-z]{3,9}\.?\s+[0-9]{1,2}(?:st|nd|rd|th)?"
# Where the roll-up lists one: opening a list item, or alone in a table cell. Mid-sentence it is prose ("pages
# 10-12", "on 5 April we moved"), not a listed date.
YEARLY_ITEM = re.compile(r"^\s*(?:[-*+]|[0-9]+\.)\s+%s(%s)%s(?![0-9A-Za-z])" % (MARK, YEARLY, MARK))
YEARLY_CELL = re.compile(r"\|\s*%s(%s)%s\s*(?=\|)" % (MARK, YEARLY, MARK))
DATE_ITEM = re.compile(r"\{\s*date:\s*[\"']?([^,\"'}]+?)[\"']?\s*(?:,\s*note:\s*(.*?))?\s*\}")  # {date: ..., note: ...}
DAYS_IN_MONTH = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)  # 02-29 comes round in a leap year
SAYS_NOTHING = re.compile(r"(?i)[\s>*_`|-]*(none|nothing|n/?a)?[\s.*_`|-]*")
SAMPLE = 5


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def month_day(s):
    """The `MM-DD` a yearly date names (`MM-DD` month first, or a day with an English month name, full or its first
    three letters), or None when it names no day some year has. Any other numeric form is None: `6/4` reads either
    way round."""
    s = (s or "").strip()
    m = re.fullmatch(r"([0-9]{2})-([0-9]{2})", s)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
    else:
        m = (re.fullmatch(r"([0-9]{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?", s)
             or re.fullmatch(r"([A-Za-z]{3,9})\.?\s+([0-9]{1,2})(?:st|nd|rd|th)?", s))
        if not m:
            return None
        word, number = (m.group(2), m.group(1)) if m.group(1).isdigit() else (m.group(1), m.group(2))
        names = [i for i, name in enumerate(MONTHS, 1) if name == word.lower() or name[:3] == word.lower()]
        if not names:
            return None
        month, day = names[0], int(number)
    if not (1 <= month <= 12 and 1 <= day <= DAYS_IN_MONTH[month - 1]):
        return None
    return "%02d-%02d" % (month, day)


def yearly_dates(line):
    """The yearly dates a roll-up line lists (see YEARLY_ITEM), each as its MM-DD."""
    return [md for d in YEARLY_ITEM.findall(line) + YEARLY_CELL.findall(line) for md in [month_day(d)] if md]


def sample(items):
    shown = "; ".join(str(x) for x in items[:SAMPLE])
    return shown + (" and %d more" % (len(items) - SAMPLE) if len(items) > SAMPLE else "")


def split_page(text):
    """(frontmatter, body, the number of lines before the body)."""
    m = FRONTMATTER.match(text)
    return (W.parse_fm(m.group(1)), text[m.end():], text[:m.end()].count("\n")) if m else ({}, text, 0)


# ------------------------------------------------------------------------------------ derived pages

def date_entry(it):
    """(date, note) of one frontmatter date entry: `{date: ..., note: ...}` (as wiki.py parses it, or as text), or a
    bare date; the note is None when there is none."""
    if isinstance(it, dict):
        return str(it.get("date", "")).strip().strip("\"'"), (it.get("note") or "").strip() or None
    text = str(it).strip()
    m = DATE_ITEM.fullmatch(text)
    return (m.group(1), (m.group(2) or "").strip().strip("\"'") or None) if m else (text.strip("\"'"), None)


def real_day(s):
    """True for `YYYY-MM-DD` naming a day the calendar has."""
    if not ISO_DAY.fullmatch(s or ""):
        return False
    try:
        datetime.date(int(s[:4]), int(s[5:7]), int(s[8:]))
    except ValueError:
        return False
    return True


def frontmatter_dates(fm):
    """(the YYYY-MM-DD dates in `deadline` and `deadlines`, each a date or {date, note}; the MM-DD dates in
    `recurring`; the `deadline` and `deadlines` entries not read as a real YYYY-MM-DD; the `recurring` entries not in
    the form {date: MM-DD, note}, with a day the month has and a note) of one page's frontmatter."""
    days, yearly, bad_days, bad = set(), set(), [], []

    def shown(it):
        return it if isinstance(it, str) else json.dumps(it, ensure_ascii=False)
    for key in ("deadline", "deadlines"):
        v = fm.get(key)
        for it in v if isinstance(v, list) else [v] if v else []:
            d, _note = date_entry(it)
            if real_day(d):
                days.add(d)
            else:
                bad_days.append("%s: %s" % (key, shown(it)))
    v = fm.get("recurring")
    for it in v if isinstance(v, list) else [v] if v else []:
        d, note = date_entry(it)
        if month_day(d) and note:
            yearly.add(month_day(d))
        else:
            bad.append(shown(it))
    return days, yearly, bad_days, bad


def deadline_items(wiki, pages, ws):
    """(derived pages hold nothing hand-written, recurring dates in frontmatter, other derived pages): each "ok",
    "finding: ..." or "not verified: ...". The rule is wiki-maintenance's "Deadlines are derived, not authored"
    (../../wiki-maintenance/SKILL.md#rules-that-keep-it-safe), read through the frontmatter keys its roll-up reads
    (#canonical-frontmatter--the-keys-the-deterministic-sweeps-read, including which pages the sweeps skip), with
    01 Deadlines the derived list of forward dates. It fixes no headings and asks for no list beyond the dates, so
    none is checked. The roll-up writes a dated deadline as YYYY-MM-DD and a recurring date as MM-DD (opening a list
    item or alone in a table cell): every such date on it must come from a current page's frontmatter, except the
    roll-up's own `last-updated` (a build stamp); it must show every deadline of a page the sweeps read that is not
    before its `last-updated` (a `last-updated` after today is a finding, and forward is then judged from today, the
    tools' clock), and every recurring date by its own MM-DD; a roll-up with none of those to show says why; and a
    deadline entry that is not a real YYYY-MM-DD, bare or in {date, note}, is reported, as a malformed recurring
    entry is. Another page the Schema marks derived (an open-questions list) is built from the pages in a way no date
    shows, so it is named as not verified, apart."""
    derived_dirs = tuple("%s %s/" % (s["number"], s["name"]) for s in (ws or {}).get("sections", []) if s["derived"])
    others = [p for p in pages if p != DEADLINES and p.startswith(derived_dirs)] if derived_dirs else []
    other_item = "not verified: %s (derived, built from the pages in a way no date shows)" % sample(others) \
        if others else "ok"
    if DEADLINES not in pages:
        why = "not verified: no %s (fixed_pages reports it)" % DEADLINES
        return why, why, other_item
    days, yearly = collections.defaultdict(list), collections.defaultdict(list)  # date: the current pages holding it
    swept_days, swept_yearly, bad_days, bad, any_derived = set(), set(), [], [], False
    for p in pages:
        if p == DEADLINES or p in others:
            continue
        fm, _body, _n = split_page(read(os.path.join(wiki, *p.split("/"))))
        if fm.get("status") == "superseded":
            continue  # no longer the wiki's: the roll-up shows none of its dates
        d, y, bd, b = frontmatter_dates(fm)
        for x in d:
            days[x].append(p)
        for x in y:
            yearly[x].append(p)
        if fm.get("provenance") not in ("manual", "calendar"):
            swept_days |= d
            swept_yearly |= y
        bad_days += ["%s: %s" % (p, e) for e in bd]
        bad += ["%s: %s" % (p, e) for e in b]
        any_derived = any_derived or fm.get("provenance") == "derived"
    fm, body, offset = split_page(read(os.path.join(wiki, *DEADLINES.split("/"))))
    derived = []
    stamp = str(fm.get("last-updated", "")).strip().strip("\"'")
    stamp = stamp if real_day(stamp) else None
    today = time.strftime("%Y-%m-%d", time.localtime(common.clock()))
    if stamp and stamp > today:  # a build not yet made: a finding, and forward is judged from today
        derived.append("%s is last-updated %s, after today (%s)" % (DEADLINES, stamp, today))
        stamp = today
    hand, hand_yearly, shown_days, shown_yearly = [], [], set(), set()
    for n, line in enumerate(body.splitlines(), offset + 1):
        for m in DAY.finditer(line):
            shown_days.add(m.group(0))
            if m.group(0) not in days and m.group(0) != stamp:
                hand.append("line %d: %s" % (n, m.group(0)))
        for d in yearly_dates(line):
            shown_yearly.add(d)
            if d not in yearly:
                hand_yearly.append("line %d: %s" % (n, d))
    if hand:
        derived.append("%s holds %d date(s) no current page's frontmatter carries (%s)"
                       % (DEADLINES, len(hand), sample(hand)))
    forward = {d for d in swept_days if stamp is None or d >= stamp}  # one before the roll-up's build is past
    missing = ["%s (%s)" % (d, ", ".join(days[d])) for d in sorted(forward - shown_days)]
    if missing:
        derived.append("%s lacks %d page deadline(s) (%s)" % (DEADLINES, len(missing), sample(missing)))
    if bad_days:
        derived.append("%d deadline entr(ies) not a real YYYY-MM-DD or {date, note} (%s)"
                       % (len(bad_days), sample(bad_days)))
    says = [line for line in body.splitlines() if line.strip() and not line.lstrip().startswith("#")
            and not SAYS_NOTHING.fullmatch(line)]
    if not forward and not swept_yearly and any_derived and not says:  # nothing to list, and no word why
        derived.append("%s is an empty roll-up that does not say why" % DEADLINES)
    recurring = []
    if hand_yearly:
        recurring.append("%s holds %d yearly date(s) no page's recurring: list carries (%s)"
                         % (DEADLINES, len(hand_yearly), sample(hand_yearly)))
    if bad:
        recurring.append("%d recurring: entr(ies) not {date, note} with a date as MM-DD (month first) or a day and "
                         "a month name, a day the month has (%s)"
                         % (len(bad), sample(bad)))
    missing = ["%s (%s)" % (d, ", ".join(yearly[d])) for d in sorted(swept_yearly - shown_yearly)]
    if missing:
        recurring.append("%s lacks %d recurring date(s) (%s)" % (DEADLINES, len(missing), sample(missing)))
    return ("finding: " + "; ".join(derived) if derived else "ok",
            "finding: " + "; ".join(recurring) if recurring else "ok", other_item)


# ------------------------------------------------------------------------------------ the hand-off contract

def contract(root, rb, settings_dir, ws, pages, rulebook_text):
    items = collections.OrderedDict()
    wiki = os.path.join(root, rb["wiki_dir"])
    folder_wiki = os.path.basename(root) + " Wiki"
    items["wiki_folder_named_after_folder"] = "ok" if rb["wiki_dir"] == folder_wiki else \
        "finding: the wiki folder is %r, not %r" % (rb["wiki_dir"], folder_wiki)
    missing = [p for p in FIXED if p not in pages]
    items["fixed_pages"] = "ok" if not missing else "finding: missing %s" % ", ".join(missing)
    items["derived_pages_hold_nothing_hand_written"], items["recurring_dates_in_frontmatter"], \
        items["other_derived_pages"] = deadline_items(wiki, pages, ws)
    # The rulebook is prose, read by keyword and substring: each filename written anywhere in it reserves it, and a
    # line naming the migrations folder with "new file", "dropped", "goes to" or "go to" routes new files there.
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
    found = collections.OrderedDict((k, []) for k in ("missing_extracts", "missing_cards", "malformed_cards",
                                                      "bad_category", "extract_paths_stale", "contamination"))
    for h, e in sorted(live.items(), key=lambda kv: kv[1]["current_path"]):
        if not isinstance(e.get("hashed"), bool):
            raise common.ToolError("manifest entry %s (%s) records no hashed true or false; it is not a manifest "
                                   "audit.py wrote: re-run audit.py" % (h, e["current_path"]))
        if not e["hashed"]:
            continue  # counted only, never read: extract.py makes no record for it
        path = e["current_path"]
        try:
            card = W.load_card(cdir, h)
        except common.ToolError as ex:  # counted with the rest, never the end of the check
            found["malformed_cards"].append("%s: %s" % (path, str(ex).split(": ", 2)[-1]))
            card = False
        x = W.load_extract(xdir, h, os.path.join(cdir, h + ".json")) \
            if os.path.exists(os.path.join(xdir, h + ".json")) else None
        if x is None:
            found["missing_extracts"].append(path)
        elif x.get("path") != path:
            found["extract_paths_stale"].append("%r is now %r" % (x.get("path"), path))
        if card is None:
            found["missing_cards"].append(path)
            continue
        if card is False:
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
    not_utf8, rulebook_text = [], None
    for p in (claude, agents):
        if os.path.exists(p):
            with open(p, "rb") as f:
                raw = f.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as e:  # a finding, as settings.py check makes it; the rest read it as it is
                not_utf8.append("%s (byte %d)" % (os.path.basename(p), e.start))
                text = raw.decode("utf-8", "replace")
            rulebook_text = text if p == claude else rulebook_text

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
        ("pages_not_accepted", len(not_accepted)), ("pages_not_verified", len(unverifiable)),
        ("records_for_no_page", out["wiki"]["acceptance_records_for_no_page"])])  # information: records stay as made
    missing = [os.path.basename(p) for p in (claude, agents) if not os.path.exists(p)]
    out["rulebook"] = collections.OrderedDict([
        ("present", "finding: missing %s" % " and ".join(missing) if missing else "ok"),
        ("valid_utf8", "finding: not valid UTF-8: %s" % ", ".join(not_utf8) if not_utf8 else "ok"),
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
            "malformed_cards": "card(s) not in the card format; re-card them (cards.py work --redo)",
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
