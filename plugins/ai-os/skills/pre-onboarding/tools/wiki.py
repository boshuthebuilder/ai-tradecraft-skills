#!/usr/bin/env python3
"""Wiki tools for drafting and checking a folder's wiki.

    wiki.py bundles --root R --out <dir>       per-section evidence bundles for drafting agents (JSONL), from cards
    wiki.py check   --root R [--out <json>]    deterministic checks; every item a count, zero included
    wiki.py move    --root R --map <json>      move pages ({"old rel": "new rel"}) and rewrite every relative link

Bundles are routed by the compiled Schema routing (longest prefix wins) and record the manifest's sha256; a bundle
older than the manifest is refused (bundles go stale after any migration). Pages link only to other pages
(relative, spaces as %20, `&` literal); source files are named by folder-relative path in backticks.
"""
import argparse
import collections
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
    problems = len(fm_bad) + len(dead_src) + len(dead_links) + len(em) + len(uncovered)
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
    a = ap.parse_args()
    return {"bundles": bundles, "check": check, "move": move}[a.cmd](a)


if __name__ == "__main__":
    common.run_main(main)
