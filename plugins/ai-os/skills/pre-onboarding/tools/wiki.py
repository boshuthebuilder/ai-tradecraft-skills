#!/usr/bin/env python3
"""Wiki tools for drafting and checking a folder's wiki.

    wiki.py bundles --root R --out <dir>       per-section evidence bundles for drafting agents (JSONL), from cards
    wiki.py check   --root R [--out <json>]    deterministic checks; every item a count, zero included
    wiki.py move    --root R --map <json>      move pages ({"old rel": "new rel"}) and rewrite every relative link
    wiki.py chart   --root R --kind K --data <rows.csv|rows.json> --title T [--out <md>]
                                               a Mermaid chart and its data table, from cited rows

Bundles are routed by the compiled Schema routing (longest prefix wins) and record the manifest's sha256; a bundle
older than the manifest is refused (bundles go stale after any migration). Pages link only to other pages
(relative, spaces as %20, `&` literal); source files are named by folder-relative path in backticks.

Charts: `--data` is a CSV file with a header row or a JSON array of objects, rows kept in order, every row with the
same columns: bar `label` (or `period`), `value`, `unit`, `source`; line `period`, `value`, `unit`, `source`; pie
`label`, `value`, `unit`, `source`; gantt `label`, `start`, `end`, `source`, optional `section`; timeline `date`,
`label`, `source`. `source` is a folder-relative path that exists; values are plain decimals written exactly as
given; one unit per chart, on the y-axis or in a pie's title; dates YYYY-MM-DD; a series has three points or more.
A breach is refused, naming the row. The output is the Mermaid block, a blank line and its data table, which
`check` requires beside every xychart-beta, pie, gantt and timeline block (K8). Rules in full: tools/README.md.
"""
import argparse
import collections
import csv
import datetime
import decimal
import glob
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

BULK_TYPES = re.compile(r"(?i)reading|course material|lecture|book|textbook|journal|article|paper|photo|slides|"
                        r"presentation|notes|handout|guide|dictionary|homework|coursework|screenshot|casebook|"
                        r"brochure|report")
LINK = re.compile(r"\]\(([^)\s]+?\.md)(#[^)]*)?\)")
EM_DASH = "\u2014"
REQUIRED_FM = ("provenance", "last-updated", "status")


def load_manifest(root, path=None):
    p = path or os.path.join(root, "_Audit", "manifest.json")
    return p, json.load(open(p, encoding="utf-8"))["entries"]


def full_text(r):
    return "\n\n".join("[page %d]\n%s" % (p.get("n", 0), (p.get("text") or "").strip())
                       for p in r.get("pages", []) if (p.get("text") or "").strip() and p.get("tier") != "photo")


# ------------------------------------------------------------------------------------ bundles

def bundles(a):
    root, settings_dir, _work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    ws = common.load_wiki_schema(root, settings_dir)
    mpath, man = load_manifest(root, a.manifest)
    kinds = {s["number"]: s["kind"] for s in ws["sections"]}
    routes = sorted(((r["prefix"], r["section"]) for r in ws["routing"] if r["section"]), key=lambda x: -len(x[0]))
    cards_dir = os.path.join(root, "_Audit", "cards")
    extract_dir = os.path.join(root, "_Audit", "extract")
    out = os.path.abspath(a.out)
    writer = common.Writer(root)
    bund, unrouted, counts, compact = collections.defaultdict(list), [], collections.Counter(), collections.Counter()
    for h, e in sorted(man.items(), key=lambda x: x[1]["current_path"]):
        p = e["current_path"]
        if "departed" in e.get("flags", []) or p.startswith(rb["migrations_dir"] + "/"):
            continue
        sec = next((s for pre, s in routes if p.startswith(pre)), None)
        cp = os.path.join(cards_dir, h + ".json")
        if sec is None or not os.path.exists(cp):
            unrouted.append(p)
            continue
        c = json.load(open(cp, encoding="utf-8"))
        xr = json.load(open(os.path.join(extract_dir, h + ".json"), encoding="utf-8"))
        rec = {"id": h[:12], "path": p, "copies": [x["path"] for x in e.get("copies", []) if x["path"] != p],
               "pages": xr.get("page_count", 0), "read": xr.get("status")}
        rec.update({k: c.get(k) for k in ("title", "doc_type", "party", "parties", "doc_date", "category",
                                           "language", "sensitive")})
        active = kinds.get(sec) == "active"
        if not active and (c.get("category") in ("Reference & Reading", "Photos")
                           or BULK_TYPES.search(c.get("doc_type") or "")):
            compact[sec] += 1
            rec["compact"] = True
        else:
            rec.update({"summary": c.get("summary"), "key_facts": c.get("key_facts")})
            if active:
                t = full_text(xr)
                rec["text"] = t[:a.text_cap] + ("\n[... text truncated, %d chars total]" % len(t)
                                                if len(t) > a.text_cap else "")
        bund[sec].append(rec)
        counts[sec] += 1
    for sec, rows in bund.items():
        writer.text(os.path.join(out, "bundle_%s.jsonl" % sec),
                    "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    writer.json(os.path.join(out, "bundles.json"), {"manifest_sha256": common.sha256_file(mpath),
                                                    "sections": dict(counts), "compact": dict(compact),
                                                    "unrouted": unrouted}, indent=1)
    print(json.dumps({"routed": sum(counts.values()), "sections": dict(sorted(counts.items())),
                      "compact": dict(compact), "unrouted": len(unrouted)}, ensure_ascii=False))
    return 1 if unrouted else 0


# ------------------------------------------------------------------------------------ check

def parse_fm(txt):
    """Minimal reader for the wiki's frontmatter: scalar keys, and lists of quoted strings or {date, note}."""
    fm, key = {}, None
    for line in txt.splitlines():
        m = re.match(r"^([a-z_-]+):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            fm[key] = [] if val in ("", "[]") else val
            continue
        m = re.match(r"^\s+-\s+(.*)$", line)
        if m and key:
            item = m.group(1).strip()
            d = re.match(r"^\{date:\s*([0-9-]+),\s*note:\s*(.*)\}$", item)
            if not isinstance(fm.get(key), list):
                fm[key] = []
            fm[key].append({"date": d.group(1), "note": d.group(2)} if d else item.strip('"'))
    return fm


def strip_code(line):
    return re.sub(r"`[^`]*`", "", line)


def check_result(root, rb, man):
    """The wiki checks as a dict; every item a count (zero included) or a named not-recorded state."""
    wiki = os.path.join(root, rb["wiki_dir"])
    live = {h: e for h, e in man.items() if "departed" not in e.get("flags", [])}
    tops = {n for n in os.listdir(root) if not n.startswith(".")}
    pages = sorted(p for p in glob.glob(os.path.join(wiki, "**", "*.md"), recursive=True)
                   if not any(part.startswith(".") for part in os.path.relpath(p, wiki).split(os.sep)))
    res = collections.OrderedDict(wiki=rb["wiki_dir"], pages=len(pages))
    fm_bad, dead_src, dead_links, em, unchecked, dls, sup = [], [], [], [], 0, [], 0
    charts, unpaired = 0, []
    text = ""
    log_prefix = "91 Log" + os.sep
    for p in pages:
        rel = os.path.relpath(p, wiki)
        t = open(p, encoding="utf-8").read()
        text += t
        m = re.match(r"---\n(.*?)\n---\n", t, re.S)
        fm = parse_fm(m.group(1)) if m else {}
        if not all(k in fm for k in REQUIRED_FM):
            fm_bad.append(rel)
        if fm.get("status") == "superseded":
            sup += 1
        for s in fm.get("sources") or []:
            if isinstance(s, str) and not os.path.exists(os.path.join(root, s)):
                dead_src.append([rel, s])
        for d in fm.get("deadlines") or []:
            if isinstance(d, dict):
                dls.append([d.get("date"), rel])
        body = t[m.end():] if m else t
        if not rel.startswith(log_prefix):
            for tick in re.findall(r"`([^`\n]+)`", body):
                if "/" not in tick or tick.endswith("/") or "." not in tick[-6:]:
                    continue
                if tick.split("/", 1)[0] in tops:
                    if not os.path.exists(os.path.join(root, tick)):
                        dead_src.append([rel, tick])
                else:
                    unchecked += 1
        for lk, _anchor in LINK.findall(body):
            if lk.startswith("http"):
                continue
            if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(p), urllib.parse.unquote(lk)))):
                dead_links.append([rel, lk])
        em += [[rel, i] for i, line in enumerate(body.splitlines(), 1) if EM_DASH in strip_code(line)]
        for line, _kind, paired in chart_blocks(t):
            charts += 1
            if not paired:
                unpaired.append([rel, line])

    def covered(pth):
        if pth in text:
            return True
        parts = pth.split("/")
        for i in range(len(parts) - 1, 0, -1):
            d = "/".join(parts[:i])
            if "`" + d + "/" in text or "`" + d + "`" in text:
                return True
        return False

    scope = [e["current_path"] for e in live.values() if not e["current_path"].startswith(rb["migrations_dir"] + "/")]
    uncovered = [p for p in scope if not covered(p)]
    res.update(frontmatter_conforming="%d/%d" % (len(pages) - len(fm_bad), len(pages)), frontmatter_bad=fm_bad,
               superseded_pages=sup, dead_source_paths=dead_src, backticked_paths_unchecked=unchecked,
               dead_page_links=dead_links, em_dash_lines=len(em), em_dash_where=em[:10],
               chart_blocks=charts, charts_without_data_table=unpaired,
               deadlines=sorted(map(list, {tuple(x) for x in dls})),
               documents_in_scope=len(scope), documents_not_covered=len(uncovered), not_covered_sample=uncovered[:20])
    rat = os.path.join(root, "_Audit", "wiki-rationale.md")
    if os.path.exists(rat):
        blocks = set(re.findall(r"^### (.+?\.md)\s*$", open(rat, encoding="utf-8").read(), re.M))
        res["rationale"] = {"blocks": len(blocks),
                            "pages_without_block": sorted(os.path.relpath(p, wiki) for p in pages
                                                          if os.path.relpath(p, wiki) not in blocks)}
    else:
        res["rationale"] = "not recorded"
    acc = os.path.join(root, "_Audit", "wiki-acceptance.json")
    res["acceptance"] = "recorded" if os.path.exists(acc) else "not recorded"
    problems = len(fm_bad) + len(dead_src) + len(dead_links) + len(em) + len(uncovered) + len(unpaired)
    res["problems"] = problems
    return res


def check(a):
    root, settings_dir, _work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    _mp, man = load_manifest(root, a.manifest)
    res = check_result(root, rb, man)
    out = json.dumps(res, ensure_ascii=False, indent=1)
    if a.out:
        common.Writer(root if a.read_only_root else None).text(a.out, out)
    print(out)
    return 1 if res["problems"] else 0


# ------------------------------------------------------------------------------------ move

def move(a):
    root, settings_dir, _work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    wiki = os.path.join(root, rb["wiki_dir"])
    writer = common.Writer(root if a.read_only_root else None)
    moves = json.load(open(a.map, encoding="utf-8"))
    pages = sorted(os.path.relpath(p, wiki) for p in glob.glob(os.path.join(wiki, "**", "*.md"), recursive=True))
    for old in moves:
        if old not in pages:
            raise common.ToolError("page not found: %s" % old)
        if moves[old] in pages:
            raise common.ToolError("destination exists: %s" % moves[old])
    out = {}
    for old in pages:
        new = moves.get(old, old)
        txt = open(os.path.join(wiki, old), encoding="utf-8").read()

        def fix(m, old=old, new=new):
            lk, anchor = m.group(1), m.group(2) or ""
            if lk.startswith("http"):
                return m.group(0)
            tgt = os.path.normpath(os.path.join(os.path.dirname(old), urllib.parse.unquote(lk)))
            tgt = moves.get(tgt, tgt)
            rel = os.path.relpath(tgt, os.path.dirname(new) or ".")
            return "](" + urllib.parse.quote(rel, safe="/&") + anchor + ")"
        new_txt = LINK.sub(fix, txt)
        if new != old or new_txt != txt:
            out[new] = new_txt
    for new, txt in out.items():
        writer.text(os.path.join(wiki, new), txt)
    for old in moves:
        writer.check(os.path.join(wiki, old))
        os.remove(os.path.join(wiki, old))
    dead = [[p, lk] for p in glob.glob(os.path.join(wiki, "**", "*.md"), recursive=True)
            for lk, _ in LINK.findall(open(p, encoding="utf-8").read())
            if not lk.startswith("http") and not os.path.exists(
                os.path.normpath(os.path.join(os.path.dirname(p), urllib.parse.unquote(lk))))]
    print(json.dumps({"moved": len(moves), "rewritten": len(out), "dead_links": dead}, ensure_ascii=False))
    return 1 if dead else 0


# ------------------------------------------------------------------------------------ chart

CHART_COLUMNS = {  # kind: (the columns every row has, "a|b" meaning exactly one of the two; optional columns)
    "bar": (("label|period", "value", "unit", "source"), ()),
    "line": (("period", "value", "unit", "source"), ()),
    "pie": (("label", "value", "unit", "source"), ()),
    "gantt": (("label", "start", "end", "source"), ("section",)),
    "timeline": (("date", "label", "source"), ()),
}
SERIES = ("bar", "line", "pie")
CHART_TABLES = {  # K8: the header row of the data table `chart` writes after a block, by the block's Mermaid type
    "xychart-beta": re.compile(r"\| (Label|Period) \| Value \(.+\) \| Source \|"),
    "pie": re.compile(r"\| Label \| Value \(.+\) \| Source \|"),
    "gantt": re.compile(r"\| (Section \| )?Label \| Start \| End \| Source \|"),
    "timeline": re.compile(r"\| Date \| Label \| Source \|"),
}
TABLE_RULE = re.compile(r"\|( *:?-{3,}:? *\|)+")
SOURCED_ROW = re.compile(r"\|.*\| `[^`]+` \|")
NUMBER = re.compile(r"-?[0-9]+(\.[0-9]+)?")
ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
DATE_LIKE = re.compile(r"(?<![0-9])([0-9]{4}[-/.][0-9]{1,2}[-/.][0-9]{1,2}|[0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4})"
                       r"(?![0-9])")
UNCARRIED = '"`|#;'  # no chart text holds these: each breaks a Mermaid line or the Markdown table


def chart_rows(path):
    """The rows of a chart's data file, in order: a .csv with a header row, or a .json array of objects. Every value
    comes back as text exactly as written (a JSON number as its literal text)."""
    name = os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".csv", ".json"):
        raise common.ToolError("--data must be a .csv or .json file: %s" % path)
    if not os.path.isfile(path):
        raise common.ToolError("--data missing: %s" % path)
    if ext == ".csv":
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                table = [r for r in csv.reader(f) if r]
        except (UnicodeDecodeError, csv.Error) as e:
            raise common.ToolError("%s: not readable as UTF-8 CSV (%s)" % (path, e))
        if not table:
            raise common.ToolError("%s: empty; a chart's CSV starts with a header row" % path)
        head = table[0]
        if len(set(head)) != len(head):
            raise common.ToolError("%s: the header row repeats a column: %s" % (path, head))
        rows = []
        for n, r in enumerate(table[1:], 1):
            if len(r) != len(head):
                raise common.ToolError("%s row %d: %d cells, but the header has %d" % (name, n, len(r), len(head)))
            rows.append(dict(zip(head, r)))
    else:
        def pairs(items):
            keys = [k for k, _ in items]
            if len(set(keys)) != len(keys):
                raise common.ToolError("%s: an object repeats a key: %s" % (path, keys))
            return dict(items)

        def constant(c):
            raise common.ToolError("%s: %s is not a value a chart can show" % (path, c))
        try:
            with open(path, encoding="utf-8") as f:
                rows = json.load(f, parse_int=str, parse_float=str, parse_constant=constant, object_pairs_hook=pairs)
        except ValueError as e:
            raise common.ToolError("%s: not valid JSON (%s)" % (path, e))
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise common.ToolError("%s: expected a JSON array of objects, one per row" % path)
        for n, r in enumerate(rows, 1):
            for k, v in r.items():
                if not isinstance(v, str):
                    raise common.ToolError("%s row %d: %s must be text or a number, not %s"
                                           % (name, n, k, json.dumps(v)))
    if not rows:
        raise common.ToolError("%s: no rows" % path)
    return rows


def chart_date(value):
    """The date a YYYY-MM-DD text names, or None."""
    if not ISO_DATE.fullmatch(value):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def chart_text(value, what, where, uncarried=""):
    """`value`, refused (naming `where`) when empty, padded, holding a character the chart cannot carry or a date
    not written YYYY-MM-DD."""
    if value == "":
        raise common.ToolError("%s: no %s" % (where, what))
    if value != value.strip():
        raise common.ToolError("%s: %s %r has spaces at its ends" % (where, what, value))
    bad = sorted({ch for ch in value if ch in UNCARRIED + uncarried or ord(ch) < 32 or ord(ch) == 127})
    if bad:
        raise common.ToolError("%s: %s %r holds %s, which a chart or its table cannot carry"
                               % (where, what, value, " ".join(repr(c) for c in bad)))
    for m in DATE_LIKE.finditer(value):
        if chart_date(m.group(0)) is None:
            raise common.ToolError("%s: %s %r holds the date %r; write dates YYYY-MM-DD"
                                   % (where, what, value, m.group(0)))
    return value


def chart_source(root, value, where):
    if value == "":
        raise common.ToolError("%s: no source; every row names the file its figures come from, by folder-relative "
                               "path" % where)
    parts = (value[:-1] if value.endswith("/") else value).split("/")
    if (value != value.strip() or os.path.isabs(value) or "\\" in value or any(p in ("", ".", "..") for p in parts)
            or any(ch in "`|" or ord(ch) < 32 for ch in value)):
        raise common.ToolError("%s: source %r is not a folder-relative path" % (where, value))
    if not os.path.exists(os.path.join(root, value)):
        raise common.ToolError("%s: source %r does not exist in %s" % (where, value, root))


def chart_row_date(row, col, where):
    d = chart_date(row[col])
    if d is None:
        raise common.ToolError("%s: %s %r is not a date written YYYY-MM-DD" % (where, col, row[col]))
    return d


def render_chart(root, kind, title, rows, where):
    """The Mermaid block for `rows`, a blank line, then their data table; refused, naming the row (counted from 1,
    the header not counted), when a rule is broken. `where` names the data file in messages."""
    required, optional = CHART_COLUMNS[kind]
    cols = set(rows[0])
    for n, r in enumerate(rows, 1):
        if set(r) != cols:
            raise common.ToolError("%s row %d: columns %s differ from row 1's %s" % (where, n, sorted(r), sorted(cols)))
    if "source" not in cols:
        raise common.ToolError("%s: no source column; every row needs its source, the folder-relative path of the "
                               "file its figures come from" % where)
    names = []
    for need in required:
        have = [c for c in need.split("|") if c in cols]
        if len(have) != 1:
            raise common.ToolError("%s: a %s chart needs exactly one %s column" % (where, kind, " or ".join(
                repr(c) for c in need.split("|"))))
        names.append(have[0])
    unknown = sorted(cols - set(names) - set(optional))
    if unknown:
        raise common.ToolError("%s: unknown columns %s for a %s chart (it takes %s)" % (
            where, unknown, kind, ", ".join(required + optional)))
    if kind in SERIES and len(rows) < 3:
        raise common.ToolError("%s: a %s series needs at least three points, not %d; state fewer figures in a "
                               "sentence" % (where, kind, len(rows)))
    key = names[0]  # what names each row: its label, period or date
    chart_text(title, "title", "--title")
    seen = {}
    for n, r in enumerate(rows, 1):
        at = "%s row %d" % (where, n)
        chart_source(root, r["source"], at)
        if kind in SERIES:
            chart_text(r[key], key, at)
            if r[key] in seen:
                raise common.ToolError("%s: %s %r repeats row %d's" % (at, key, r[key], seen[r[key]]))
            seen[r[key]] = n
            if not NUMBER.fullmatch(r["value"]):
                raise common.ToolError("%s: value %r is not a plain decimal (digits, an optional minus sign and "
                                       "decimal point; no separators, symbols or exponent)" % (at, r["value"]))
            if kind == "pie" and decimal.Decimal(r["value"]) <= 0:
                raise common.ToolError("%s: pie value %r is not positive" % (at, r["value"]))
            chart_text(r["unit"], "unit", at)
            if r["unit"] != rows[0]["unit"]:
                raise common.ToolError("%s: unit %r differs from row 1's %r; a chart has one unit"
                                       % (at, r["unit"], rows[0]["unit"]))
        elif kind == "gantt":
            chart_text(r["label"], "label", at, ":")
            if "section" in r:
                chart_text(r["section"], "section", at, ":")
            start, end = chart_row_date(r, "start", at), chart_row_date(r, "end", at)
            if end < start:
                raise common.ToolError("%s: ends %s, before it starts %s" % (at, r["end"], r["start"]))
        else:
            chart_row_date(r, "date", at)
            chart_text(r["label"], "label", at, ":")
    if kind == "pie" and rows[0]["unit"] not in title:
        raise common.ToolError("--title %r must name the unit %r: a pie has no axis to carry it"
                               % (title, rows[0]["unit"]))
    return chart_block(kind, title, rows, key) + "\n" + chart_table(kind, rows, key)


def chart_block(kind, title, rows, key):
    if kind in ("bar", "line"):
        values = [r["value"] for r in rows]
        amounts = [decimal.Decimal(v) for v in values]
        y_axis = 'y-axis "%s"' % rows[0]["unit"]
        if min(amounts) >= 0 and max(amounts) > 0:
            y_axis += " 0 --> %s" % values[amounts.index(max(amounts))]
        lines = ["xychart-beta", 'title "%s"' % title, "x-axis [%s]" % ", ".join('"%s"' % r[key] for r in rows),
                 y_axis, "%s [%s]" % (kind, ", ".join(values))]
    elif kind == "pie":
        lines = ["pie title " + title] + ['"%s" : %s' % (r["label"], r["value"]) for r in rows]
    elif kind == "gantt":
        lines, section = ["gantt", "title " + title, "dateFormat YYYY-MM-DD"], None
        for r in rows:
            if "section" in r and r["section"] != section:
                section = r["section"]
                lines.append("section " + section)
            lines.append("%s :%s, %s" % (r["label"], r["start"], r["end"]))
    else:
        lines = ["timeline", "title " + title]
        for i, r in enumerate(rows):
            if i and r["date"] == rows[i - 1]["date"]:
                lines[-1] += " : " + r["label"]
            else:
                lines.append("%s : %s" % (r["date"], r["label"]))
    return "```mermaid\n%s\n%s\n```\n" % (lines[0], "\n".join("    " + x for x in lines[1:]))


def chart_table(kind, rows, key):
    if kind in SERIES:
        cols = [(key.capitalize(), key, "---"), ("Value (%s)" % rows[0]["unit"], "value", "---:")]
    elif kind == "gantt":
        cols = ([("Section", "section", "---")] if "section" in rows[0] else []) + [
            ("Label", "label", "---"), ("Start", "start", "---"), ("End", "end", "---")]
    else:
        cols = [("Date", "date", "---"), ("Label", "label", "---")]
    lines = ["| %s | Source |" % " | ".join(c[0] for c in cols), "| %s | --- |" % " | ".join(c[2] for c in cols)]
    lines += ["| %s | `%s` |" % (" | ".join(r[c[1]] for c in cols), r["source"]) for r in rows]
    return "\n".join(lines) + "\n"


def chart_blocks(text):
    """K8: the Mermaid blocks in a page of a type `chart` renders, as (line of the opening fence in the page, type,
    paired). Paired: the next non-blank line after the block starts the data table `chart` writes for that type,
    its header row, the rule row, then at least one row, every row ending in a backticked source."""
    lines = [x.strip() for x in text.splitlines()]
    found, i = [], 0
    while i < len(lines):
        if lines[i] != "```mermaid":
            i += 1
            continue
        start, i = i, i + 1
        while i < len(lines) and lines[i] != "```":
            i += 1
        kind = next((x.split()[0] for x in lines[start + 1:i] if x and not x.startswith("%%")), None)
        i += 1
        if kind not in CHART_TABLES:
            continue
        k, rows = i, []
        while k < len(lines) and not lines[k]:
            k += 1
        if k + 1 < len(lines) and CHART_TABLES[kind].fullmatch(lines[k]) and TABLE_RULE.fullmatch(lines[k + 1]):
            k += 2
            while k < len(lines) and lines[k].startswith("|"):
                rows.append(lines[k])
                k += 1
        found.append((start + 1, kind, bool(rows) and all(SOURCED_ROW.fullmatch(r) for r in rows)))
    return found


def chart(a):
    root, _settings_dir, _work = common.resolve(a)
    out = render_chart(root, a.kind, a.title, chart_rows(a.data), os.path.basename(a.data))
    if a.out:
        common.Writer(root if a.read_only_root else None).text(a.out, out)
    sys.stdout.write(out)
    return 0


def main():
    ap = argparse.ArgumentParser(description="Wiki tools")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common_args(p):
        p.add_argument("--root", required=True)
        p.add_argument("--settings-dir")
        p.add_argument("--work")
        p.add_argument("--manifest")
        p.add_argument("--read-only-root", action="store_true")
        return p

    p = common_args(sub.add_parser("bundles"))
    p.add_argument("--out", required=True)
    p.add_argument("--text-cap", type=int, default=12000)
    p = common_args(sub.add_parser("check"))
    p.add_argument("--out")
    p = common_args(sub.add_parser("move"))
    p.add_argument("--map", required=True)
    p = common_args(sub.add_parser("chart"))
    p.add_argument("--kind", required=True, choices=list(CHART_COLUMNS))
    p.add_argument("--data", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--out")
    a = ap.parse_args()
    return {"bundles": bundles, "check": check, "move": move, "chart": chart}[a.cmd](a)


if __name__ == "__main__":
    common.run_main(main)
