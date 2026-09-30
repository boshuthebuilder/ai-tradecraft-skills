#!/usr/bin/env python3
"""The folder's settings twins in <root>/.familyai/ (or --settings-dir). Formats: `references/settings.md`.

    settings.py compile --root R   build wiki-schema.json from the Schema page's tables
    settings.py check   --root R   both twins fresh and consistent with the rulebook; every finding counted

`rulebook.json` is written by the preparing agent from the owner's answers, in the same change as the rulebook
(`CLAUDE.md`, with a byte-identical `AGENTS.md`), and records the rulebook's sha256. `wiki-schema.json` is compiled
from the Schema page's tables, each the one table under a `## ` heading of its name, with fixed headers:

- Layout: `Section | Pages | Professional lens | Kind`
- Routing: `Files under | Section and page`
- Page contracts: `Section (professional) | Reader | Questions, most important first | Fields every page carries`
- optional Page professionals: `Page | Professional | Deliverable | Tone`

Other headers, a missing required table and a row that cannot be read fail loud; nothing is guessed. Both twins
record their source's sha256; every tool refuses a twin whose source has changed since ("stale").
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

TABLES = {  # key: (heading, fixed headers, required)
    "layout": ("Layout", ["Section", "Pages", "Professional lens", "Kind"], True),
    "routing": ("Routing", ["Files under", "Section and page"], True),
    "contracts": ("Page contracts", ["Section (professional)", "Reader", "Questions, most important first",
                                     "Fields every page carries"], True),
    "pages": ("Page professionals", ["Page", "Professional", "Deliverable", "Tone"], False),
}
KINDS = ("active", "history", "fixed")
KIND_FLAGS = ("derived",)
SCHEMA_PAGES = ("90 Schema/90 Schema.md", "09 Schema/09 Schema.md")


def split_row(line):
    cells, cur, i = [], "", 0
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
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


def sections_of(text):
    """[(heading, [table, ...])] for every `## ` heading, in order; a table is its rows without the delimiter row.
    Fenced code is skipped."""
    out, fence, table = [], None, None
    for line in text.splitlines():
        m = re.match(r"\s*(```|~~~)", line)
        if m:
            fence = None if fence == m.group(1) else (fence or m.group(1))
            table = None
            continue
        if fence:
            continue
        if line.startswith("## "):
            out.append((line[3:].strip(), []))
            table = None
        elif line.lstrip().startswith("|") and out:
            if table is None:
                table = []
                out[-1][1].append(table)
            cells = split_row(line)
            if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                table.append(cells)
        else:
            table = None
    return out


def find_table(sections, key):
    """The rows under the one `## <heading>` section for `key`, header checked; [] for an absent optional table."""
    heading, headers, required = TABLES[key]
    found = [(h, tables) for h, tables in sections
             if re.fullmatch(r"%s(\s*[(:].*)?" % re.escape(heading), h, re.I)]
    if len(found) > 1:
        raise common.ToolError("Schema has %d sections headed %s (%s); keep one"
                               % (len(found), heading, ", ".join(repr(h) for h, _ in found)))
    if not found:
        if required:
            raise common.ToolError("Schema has no %s table: a `## %s` section holding one table headed | %s |"
                                   % (heading, heading, " | ".join(headers)))
        return []
    h, tables = found[0]
    if len(tables) != 1:
        raise common.ToolError("Schema section %r holds %d tables; it must hold exactly one" % (h, len(tables)))
    rows = tables[0] or [[]]
    if rows[0] != headers:
        raise common.ToolError("Schema section %r: table headers | %s |, expected exactly | %s |"
                               % (h, " | ".join(rows[0]), " | ".join(headers)))
    for n, row in enumerate(rows[1:], 1):
        if len(row) != len(headers):
            raise common.ToolError("Schema section %r row %d has %d cells, expected %d: %s"
                                   % (h, n, len(row), len(headers), row))
    return rows[1:]


def fail(table, row, why):
    raise common.ToolError("Schema %s table, row %s: %s" % (table, " | ".join(row), why))


def numbered(cell, table, row):
    m = re.fullmatch(r"(\d{2}) +(\S.*)", cell)
    if not m:
        fail(table, row, "%r does not start with a two-digit section number and a name" % cell)
    return m.group(1), m.group(2).strip()


def professionals(cell, table, row):
    names = [p.strip() for p in cell.split(";") if p.strip()]
    if not names:
        fail(table, row, "no professional named")
    return names


def questions(cell, table, row):
    """`1. First? 2. Second?` as a list in that order; the numbers must run 1, 2, 3 and so on."""
    marks = re.findall(r"(?:^|\s)(\d+)\.\s+", cell)
    if not marks:
        return [cell] if cell else fail(table, row, "no question")
    if [int(n) for n in marks] != list(range(1, len(marks) + 1)) or not re.match(r"1\.\s", cell):
        fail(table, row, "questions must be numbered 1., 2., 3. in priority order, not %s" % marks)
    return [q.strip() for q in re.split(r"(?:^|\s)\d+\.\s+", cell) if q.strip()]


def compile_text(text, schema_path):
    """The wiki-schema.json object for a Schema page's text (the sha256 is added by the caller)."""
    tables = sections_of(text)
    sections, by_number = [], {}
    for row in find_table(tables, "layout"):
        sec, pages, lens, kind = row
        number, name = numbered(sec, "Layout", row)
        if number in by_number:
            fail("Layout", row, "section %s is listed twice" % number)
        words = [k.strip() for k in kind.split(",")]
        if words[0] not in KINDS or any(w not in KIND_FLAGS for w in words[1:]):
            fail("Layout", row, "kind %r is not one of %s, optionally followed by %s"
                 % (kind, "/".join(KINDS), ", ".join(KIND_FLAGS)))
        s = {"number": number, "name": name, "kind": words[0], "derived": "derived" in words[1:],
             "pages": pages, "professionals": professionals(lens, "Layout", row)}
        by_number[number] = s
        sections.append(s)
    routing, prefixes = [], set()
    for row in find_table(tables, "routing"):
        files, target = row
        ps = re.findall(r"`([^`]+)`", files)
        if not ps or any(not p.endswith("/") for p in ps):
            fail("Routing", row, "name each folder prefix in backticks, ending in /")
        m = re.match(r"(\d{2})\b", target)
        if m and m.group(1) not in by_number:
            fail("Routing", row, "section %s is not in the Layout table" % m.group(1))
        for p in ps:
            if p in prefixes:
                fail("Routing", row, "prefix %r is routed twice" % p)
            prefixes.add(p)
            routing.append({"prefix": p, "target": target, "section": m.group(1) if m else None})
    contracts, contracted = [], set()
    for row in find_table(tables, "contracts"):
        sec, reader, qs, fields = row
        m = re.fullmatch(r"(.*?)\s*\(([^()]*)\)", sec)
        number, name = numbered(m.group(1) if m else sec, "Page contracts", row)
        if number not in by_number or by_number[number]["name"] != name:
            fail("Page contracts", row, "section %s %s is not in the Layout table" % (number, name))
        if number in contracted:
            fail("Page contracts", row, "section %s has two contracts" % number)
        contracted.add(number)
        if not reader:
            fail("Page contracts", row, "no reader named")
        field_list = [f.strip() for f in fields.split(",") if f.strip()]
        if not field_list:
            fail("Page contracts", row, "no required fields")
        contracts.append({"number": number, "name": name,
                          "professionals": professionals(m.group(2), "Page contracts", row) if m
                          else by_number[number]["professionals"],
                          "reader": reader, "questions": questions(qs, "Page contracts", row),
                          "fields": field_list})
    pages = {}
    for row in find_table(tables, "pages"):
        page, prof, deliverable, tone = row
        top = page.split("/", 1)[0]
        if not page.endswith(".md") or "/" not in page or not any(
                top == "%s %s" % (s["number"], s["name"]) for s in sections):
            fail("Page professionals", row, "%r is not a page path under a Layout section, like "
                 "'<section>/<page>.md'" % page)
        if page in pages:
            fail("Page professionals", row, "page listed twice")
        if not prof:
            fail("Page professionals", row, "no professional named")
        pages[page] = {"professional": prof, "deliverable": deliverable, "tone": tone}
    return {"version": common.SETTINGS_VERSION, "schema_path": schema_path, "schema_sha256": None,
            "sections": sections, "routing": routing, "contracts": contracts, "pages": pages}


def schema_path(root, wiki_dir):
    for rel in SCHEMA_PAGES:
        if os.path.exists(os.path.join(root, wiki_dir, rel)):
            return "%s/%s" % (wiki_dir, rel)
    raise common.ToolError("no Schema page under %s/ (looked for %s)" % (wiki_dir, ", ".join(SCHEMA_PAGES)))


def compile_schema(root, rb):
    rel = schema_path(root, rb["wiki_dir"])
    path = os.path.join(root, rel)
    with open(path, encoding="utf-8") as f:
        data = compile_text(f.read(), rel)
    data["schema_sha256"] = common.sha256_file(path)
    return data


def compile_cmd(a):
    root, settings_dir, _work = common.resolve(a, verify=False)
    rb = common.load_rulebook(root, settings_dir)
    data = compile_schema(root, rb)
    out = os.path.join(settings_dir, "wiki-schema.json")
    common.Writer(root if a.read_only_root else None).json(out, data, indent=1)
    print("compiled %s: %d sections, %d routing rows, %d contracts, %d page professionals" % (
        out, len(data["sections"]), len(data["routing"]), len(data["contracts"]), len(data["pages"])))
    return 0


def twin_state(load):
    """(state, value or error): fresh, stale, unpinned, missing or invalid."""
    try:
        value = load()
    except common.StaleTwin as e:
        return e.state, e
    except common.ToolError as e:
        return ("missing" if str(e).startswith("missing") else "invalid"), e
    return ("fresh" if value is not None else "missing"), value


def check_cmd(a):
    root, settings_dir, _work = common.resolve(a, verify=False)
    findings, status = [], {}
    claude, agents = (os.path.join(root, n) for n in ("CLAUDE.md", "AGENTS.md"))
    text = None
    if os.path.exists(claude):
        with open(claude, encoding="utf-8") as f:
            text = f.read()

    status["rulebook_json"], got = twin_state(lambda: common.load_rulebook(root, settings_dir, required=True))
    if status["rulebook_json"] != "fresh":
        findings.append(str(got))
    try:
        rb = common.load_rulebook(root, settings_dir, required=True, verify=False)
    except common.ToolError:
        rb = None
    if rb is None or text is None:
        status["rulebook_facts"] = "not verified: %s" % ("rulebook.json unreadable" if rb is None
                                                         else "CLAUDE.md missing")
    else:
        status["rulebook_facts"] = "checked"
        if rb["wiki_dir"] != os.path.basename(root) + " Wiki":
            findings.append("wiki_dir %r is not '<folder name> Wiki' (%r)" % (rb["wiki_dir"],
                                                                             os.path.basename(root) + " Wiki"))
        for name in common.reserved_names(rb):
            if name not in text:
                findings.append("the rulebook does not mention reserved name %r" % name)
        for pack in rb["packs"]:
            if pack not in text:
                findings.append("the rulebook does not mention pack %r" % pack)

    if text is not None and os.path.exists(agents):
        status["rulebook_copies_identical"] = common.sha256_file(claude) == common.sha256_file(agents)
        if not status["rulebook_copies_identical"]:
            findings.append("CLAUDE.md and AGENTS.md differ")
    else:
        status["rulebook_copies_identical"] = "not verified: a rulebook file is missing"
        findings.append("rulebook file missing: %s" % " and ".join(
            n for n, p in (("CLAUDE.md", claude), ("AGENTS.md", agents)) if not os.path.exists(p)))

    status["wiki_schema_json"], ws = twin_state(lambda: common.load_wiki_schema(root, settings_dir, required=True))
    if status["wiki_schema_json"] != "fresh":
        findings.append(str(ws))
    else:
        if rb and not ws["schema_path"].startswith(rb["wiki_dir"] + "/"):
            findings.append("wiki-schema.json was compiled from %r, outside the wiki folder %r"
                            % (ws["schema_path"], rb["wiki_dir"]))
        have = {c["number"] for c in ws["contracts"]}
        for s in ws["sections"]:
            if s["kind"] != "fixed" and s["number"] not in have:
                findings.append("section %s %s has no page contract" % (s["number"], s["name"]))
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
