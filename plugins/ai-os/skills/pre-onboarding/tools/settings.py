#!/usr/bin/env python3
"""The folder's settings twins in <root>/.familyai/ (or --settings-dir).

    settings.py compile --root R   build wiki-schema.json from the Schema page's tables
    settings.py check   --root R   both twins fresh and consistent with the rulebook; every finding counted

`rulebook.json` is written by the preparing agent from the owner's answers, in the same change as the rulebook
(`CLAUDE.md`, with a byte-identical `AGENTS.md`), and records the rulebook's sha256. `wiki-schema.json` is compiled
from the Schema page's tables, which use fixed headers:

- Layout: `Section | Pages | Professional lens | Kind`
- Routing: `Files under | Section and page`
- Page contracts: `Section (professional) | Questions, most important first | Fields every page carries`
- optional Page professionals: `Page | Professional | Deliverable | Tone`

A section whose table has other headers fails loud. Both twins record their source's sha256; every tool refuses a
twin whose source has changed since ("stale").
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

HEADERS = {
    "layout": ["Section", "Pages", "Professional lens", "Kind"],
    "routing": ["Files under", "Section and page"],
    "contracts": ["Section (professional)", "Questions, most important first", "Fields every page carries"],
    "pages": ["Page", "Professional", "Deliverable", "Tone"],
}
HEADINGS = {"layout": r"layout", "routing": r"routing", "contracts": r"page contracts", "pages": r"page professionals"}


def split_row(line):
    cells, cur, i = [], "", 0
    s = line.strip().strip("|")
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if s[i] == "|":
            cells.append(cur.strip())
            cur = ""
        else:
            cur += s[i]
        i += 1
    cells.append(cur.strip())
    return cells


def tables_by_heading(text):
    """{heading text: [rows]} for the first table under each `## ` heading."""
    out, heading, rows, in_table = {}, None, [], False
    for line in text.splitlines() + [""]:
        if line.startswith("## "):
            if heading and rows and heading not in out:
                out[heading] = rows
            heading, rows, in_table = line[3:].strip(), [], False
            continue
        if line.lstrip().startswith("|"):
            if heading and heading not in out:
                cells = split_row(line)
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                in_table = True
        elif in_table and rows:
            if heading not in out:
                out[heading] = rows
            in_table = False
    return out


def find_table(tables, key, required):
    for heading, rows in tables.items():
        if re.match(HEADINGS[key], heading, re.I):
            if rows[0] != HEADERS[key]:
                raise common.ToolError("Schema section %r: table headers %s, expected %s" % (heading, rows[0],
                                                                                            HEADERS[key]))
            return rows[1:]
    if required:
        raise common.ToolError("Schema has no %s table (a `## %s` section with headers %s)" % (
            key, key.capitalize(), HEADERS[key]))
    return []


def schema_path(root, wiki_dir):
    for rel in ("90 Schema/90 Schema.md", "09 Schema/09 Schema.md"):
        if os.path.exists(os.path.join(root, wiki_dir, rel)):
            return "%s/%s" % (wiki_dir, rel)
    raise common.ToolError("no Schema page under %s/" % wiki_dir)


def section_number(text):
    m = re.match(r"\s*(\d{2})\b", text)
    return m.group(1) if m else None


def compile_schema(root, rb):
    rel = schema_path(root, rb["wiki_dir"])
    text = open(os.path.join(root, rel), encoding="utf-8").read()
    tables = tables_by_heading(text)
    sections = []
    for sec, pages, lens, kind in find_table(tables, "layout", True):
        sections.append({"section": sec, "number": section_number(sec), "pages": pages, "professional": lens,
                         "kind": kind})
    routing = []
    for files, target in find_table(tables, "routing", True):
        routing.append({"prefixes": re.findall(r"`([^`]+)`", files) or [files], "target": target,
                        "section": section_number(target)})
    contracts = []
    for sec, questions, fields in find_table(tables, "contracts", True):
        m = re.match(r"(.*?)\s*\((.*)\)\s*$", sec)
        qs = [q.strip() for q in re.split(r"(?:^|\s)\d+\.\s+", questions) if q.strip()]
        contracts.append({"section": m.group(1) if m else sec, "number": section_number(sec),
                          "professional": m.group(2) if m else "", "questions": qs, "fields": fields})
    pages = {}
    for page, prof, deliverable, tone in find_table(tables, "pages", False):
        pages[page] = {"professional": prof, "deliverable": deliverable, "tone": tone}
    return {"version": common.SETTINGS_VERSION, "schema_path": rel,
            "schema_sha256": common.sha256_file(os.path.join(root, rel)),
            "sections": sections, "routing": routing, "contracts": contracts, "pages": pages}


def compile_cmd(a):
    root, settings_dir, _work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    data = compile_schema(root, rb)
    writer = common.Writer(root if a.read_only_root else None)
    out = os.path.join(settings_dir, "wiki-schema.json")
    writer.json(out, data, indent=1)
    print("compiled %s: %d sections, %d routing rows, %d contracts, %d page professionals" % (
        out, len(data["sections"]), len(data["routing"]), len(data["contracts"]), len(data["pages"])))
    return 0


def check_cmd(a):
    root, settings_dir, _work = common.resolve(a)
    findings = []
    rb_path = os.path.join(settings_dir, "rulebook.json")
    claude, agents = os.path.join(root, "CLAUDE.md"), os.path.join(root, "AGENTS.md")
    status = {"rulebook_json": "missing" if not os.path.exists(rb_path) else "present"}
    try:
        rb = common.load_rulebook(root, settings_dir, required=True)
        status["rulebook_json"] = "fresh" if rb.get("rulebook_sha256") else "unpinned"
        text = open(claude, encoding="utf-8").read() if os.path.exists(claude) else ""
        for name in rb["reserved"] + [rb["wiki_dir"]] + rb["packs"]:
            if name not in text:
                findings.append("rulebook does not mention %r" % name)
        if rb["wiki_dir"] != os.path.basename(root) + " Wiki":
            findings.append("wiki_dir %r is not '<folder name> Wiki'" % rb["wiki_dir"])
    except common.ToolError as e:
        findings.append(str(e))
    if os.path.exists(claude) and os.path.exists(agents):
        status["rulebook_copies_identical"] = open(claude, "rb").read() == open(agents, "rb").read()
        if not status["rulebook_copies_identical"]:
            findings.append("CLAUDE.md and AGENTS.md differ")
    else:
        status["rulebook_copies_identical"] = "not verified: a rulebook file is missing"
        findings.append("rulebook file missing")
    try:
        ws = common.load_wiki_schema(settings_dir, root, required=True)
        status["wiki_schema_json"] = "fresh"
        numbers = {s["number"] for s in ws["sections"] if s["kind"] != "fixed"}
        have = {c["number"] for c in ws["contracts"]}
        for n in sorted(x for x in numbers - have if x):
            findings.append("section %s has no page contract" % n)
    except common.ToolError as e:
        status["wiki_schema_json"] = "stale or missing"
        findings.append(str(e))
    print(json.dumps({"status": status, "findings": findings, "count": len(findings)}, ensure_ascii=False, indent=1))
    return 1 if findings else 0


def main():
    ap = argparse.ArgumentParser(description="Folder settings twins")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("compile", "check"):
        p = sub.add_parser(name)
        p.add_argument("--root", required=True)
        p.add_argument("--settings-dir")
        p.add_argument("--work")
        p.add_argument("--read-only-root", action="store_true")
    a = ap.parse_args()
    return compile_cmd(a) if a.cmd == "compile" else check_cmd(a)


if __name__ == "__main__":
    common.run_main(main)
