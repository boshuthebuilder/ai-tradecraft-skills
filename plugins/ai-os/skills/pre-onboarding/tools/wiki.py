#!/usr/bin/env python3
"""Wiki tools for proposing, drafting and checking a folder's wiki.

    wiki.py profile --root R [--depth 2] [--out <json>]   per-folder documents, copies, cards by category, date span
                                                           and top parties, for the librarian's structure proposal
    wiki.py bundles --root R [--out <dir>] [--reuse]      per-section evidence bundles (JSONL) for drafting agents,
                                                           in <work>/bundles/ by default, never in the folder
    wiki.py brief   --root R --page P [--page P ...] [--out <md>]
                                                           the drafting brief for a set of pages, from
                                                           templates/page-brief.md
    wiki.py check   --root R [--out <json>]                deterministic checks; every item a count, zero included
    wiki.py move    --root R --map <json>                  move pages ({"old rel": "new rel"}), rewrite every
                                                           relative link to or from them
    wiki.py drift   --root R [--out <json>]                page lines and `sources:` entries citing a departed or
                                                           migrating path
    wiki.py chart   --root R --kind K --data <rows.csv|rows.json> --title T [--out <md>]
                                                           a Mermaid chart and its data table, from cited rows

Every subcommand takes --settings-dir, --work, --manifest (default <root>/_Audit/manifest.json) and
--read-only-root; profile and bundles also take --cards and --extract (default <root>/_Audit/cards, .../extract).
Page paths are relative to the wiki folder, source paths to the folder. Bundles and briefs are working files, never
written inside the folder; profile, check and drift print JSON and write --out where --read-only-root allows.

Bundles: each live manifest entry outside the migrations folder routes by the compiled Schema routing, its
longest matching prefix (a note row, with no section, routes nothing). A routed entry with a card joins its
section's `bundle_<NN>.jsonl`; entries with no route, or routed but with no card, are listed as `unrouted` and
`uncarded`. `bundles.json` records the manifest's sha256, a digest of the routing and section kinds the bundles
were built by, and the non-default arguments they were built with. A consumer (`brief`, and `bundles --reuse`)
refuses bundles whose recorded digests differ from the current manifest's and routing's: bundles go stale after any
migration, re-audit or routing change, and are rebuilt by the command the refusal names. A rebuild removes
bundles.json first, so one that fails part way leaves none to trust.

Brief: the pages' professionals, deliverables and tones (`common.page_voice`), their sections' contracts, the owner
context from rulebook.json, the page map, the bundle paths (refused when stale), each page's rationale block to
fill, the JSON a drafting agent returns and the checker command it runs. The page map is every page that exists
(each .md file under the wiki folder, dot folders skipped) or is planned: each page in the Schema's Page
professionals table, each Layout section's folder note `<NN Name>/<NN Name>.md`, and the pages being briefed.
The same inputs render the same bytes.

Links: pages link only to other pages, by relative path percent-encoded with `/` and `&` literal (spaces as %20);
source files are named by folder-relative path in backticks. `move` refuses a map it could not carry out whole
before writing anything, writes the moved pages before rewriting links to them, rewrites only links whose page or
target moved, removes the folders it empties and renames the pages' rationale headings. It names each moved page
the Schema's Page professionals table lists and each move that leaves the Layout wrong (exit 1, with any dead link
left in the wiki: edit the Schema, then compile). A swap or a chain is refused; make it in two runs.

Drift: a departed path is one a departed entry held that no live entry holds; a migrating path is one staged under
the migrations folder or the path it was staged from, when nothing live holds it. The Log's pages are history and
are not read. Fences open and close as `chart_blocks` reads them; line numbers count from the page's first line.

Malformed input (a manifest, card, extract record or bundles.json of the wrong shape, a file where a folder must
be) is refused by name, exit 2.

Charts: `--data` is a CSV file with a header row or a JSON array of objects, rows kept in order, every row with the
same columns: bar `label` (or `period`), `value`, `unit`, `source`; line `period`, `value`, `unit`, `source`; pie
`label`, `value`, `unit`, `source`; gantt `label`, `start`, `end`, `source`, optional `section`; timeline `date`,
`label`, `source`. `source` is a file or folder under the root, outside its reserved names; values are plain
decimals written exactly as given; one unit per chart, on the y-axis or in a pie's title; dates YYYY-MM-DD; a
series has three points or more. A breach is refused, naming the row. The output is the Mermaid block, a blank line
and its data table, which `check` requires beside every xychart-beta, pie, gantt and timeline block (chart
pairing). Rules in full: tools/README.md.
"""
import argparse
import collections
import csv
import datetime
import decimal
import functools
import glob
import hashlib
import json
import os
import posixpath
import re
import shlex
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cards  # noqa: E402
import common  # noqa: E402

BULK_TYPES = re.compile(r"(?i)reading|course material|lecture|book|textbook|journal|article|paper|photo|slides|"
                        r"presentation|notes|handout|guide|dictionary|homework|coursework|screenshot|casebook|"
                        r"brochure|report")
LINK = re.compile(r"\]\(([^)\s]+?\.md)(#[^)]*)?\)")
EM_DASH = "\u2014"
REQUIRED_FM = ("provenance", "last-updated", "status")
TEMPLATES = os.path.join(HERE, "templates")
LOG_DIR = "91 Log"  # the Log section: its lines are history, so drift (like check) does not read them
BUNDLE_FILE = re.compile(r"bundle_.+\.jsonl")
DOC_DATE = re.compile(r"[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?")
TEXT_CAP = 12000  # characters of a document's text an active section's bundle carries


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise common.ToolError("cannot read %s (%s)" % (path, e.strerror or e))
    except ValueError as e:
        raise common.ToolError("%s: not valid JSON (%s)" % (path, e))


def read_object(path):
    """The JSON object in `path` (`common.read_json_object`), an unreadable file named rather than a traceback."""
    try:
        return common.read_json_object(path)
    except OSError as e:
        raise common.ToolError("cannot read %s (%s)" % (path, e.strerror or e))


def os_errors(fn):
    """A subcommand whose OS errors (a file where a folder must be, a folder where a file must be, no permission)
    exit as named errors, never as tracebacks."""
    @functools.wraps(fn)
    def run(a):
        try:
            return fn(a)
        except OSError as e:
            raise common.ToolError("%s: %s" % (e.filename or fn.__name__, e.strerror or e))
    return run


def load_manifest(root, path=None):
    """The manifest's entries, refused unless each is an object with a current path, and flags and copies (when
    present) are lists."""
    p = path or os.path.join(root, "_Audit", "manifest.json")
    if not os.path.exists(p):
        raise common.ToolError("manifest missing: %s; run audit.py first" % p)
    entries = read_object(p).get("entries")
    if not isinstance(entries, dict):
        raise common.ToolError("%s has no \"entries\" object; it is not a manifest audit.py wrote" % p)
    for h, e in sorted(entries.items()):
        ok = (isinstance(e, dict) and isinstance(e.get("current_path"), str) and e["current_path"] != ""
              and isinstance(e.get("flags", []), list) and isinstance(e.get("copies", []), list)
              and all(isinstance(c, dict) and isinstance(c.get("path"), str) for c in e.get("copies", [])))
        if not ok:
            raise common.ToolError("%s: entry %s is malformed: it needs a current_path, and its flags and copies "
                                   "must be lists (copies of {path, kind}); re-run audit.py" % (p, h))
    return p, entries


CARD_TYPES = {"doc_type": str, "party": str, "parties": list, "doc_date": str, "title": str, "summary": str,
              "key_facts": dict, "category": str, "language": str, "sensitive": bool}


def load_card(cards_dir, h):
    """The card for entry `h`, None when it has none; refused, named, when it is not an object or a field it has
    is of the wrong type (profile and bundles read cards alike)."""
    path = os.path.join(cards_dir, h + ".json")
    if not os.path.exists(path):
        return None
    try:
        card = read_object(path)
    except common.ToolError as e:
        raise common.ToolError("malformed card: %s; re-card it (cards.py work --redo)" % e)
    for key, kind in CARD_TYPES.items():
        if key in card and not (isinstance(card[key], kind)
                                and (key != "parties" or all(isinstance(x, str) for x in card[key]))):
            raise common.ToolError("malformed card: %s: %s must be %s; re-card it (cards.py work --redo)"
                                   % (path, key, "a list of text" if key == "parties" else kind.__name__))
    return card


def load_extract(extract_dir, h, card_path):
    path = os.path.join(extract_dir, h + ".json")
    if not os.path.exists(path):
        raise common.ToolError("card %s has no extract record %s; extract the document again" % (card_path, path))
    xr = read_object(path)
    if not (isinstance(xr.get("pages", []), list) and all(isinstance(p, dict) for p in xr.get("pages", []))):
        raise common.ToolError("malformed extract record %s: pages must be a list of objects; extract the document "
                               "again" % path)
    return xr


def full_text(r):
    return "\n\n".join("[page %d]\n%s" % (p.get("n", 0), (p.get("text") or "").strip())
                       for p in r.get("pages", []) if (p.get("text") or "").strip() and p.get("tier") != "photo")


def wiki_pages(wiki):
    """Every page under the wiki folder, relative to it with `/` separators, sorted; dot folders and files (an
    editor's settings) are skipped, as `check` skips them."""
    out = []
    for d, ds, fs in os.walk(wiki):
        ds[:] = sorted(x for x in ds if not x.startswith("."))
        out += [os.path.relpath(os.path.join(d, f), wiki).replace(os.sep, "/") for f in fs
                if f.endswith(".md") and not f.startswith(".")]
    return sorted(out)


def is_page_path(p):
    """A page path relative to the wiki folder: `/` separated, ending in .md, no part empty, hidden (a dot first) or
    with a space at either end."""
    return (isinstance(p, str) and p.endswith(".md") and "\\" not in p
            and all(x and x == x.strip() and not x.startswith(".") for x in p.split("/")))


def schema_rel(root, rb, ws):
    """The Schema page relative to the wiki folder, or None."""
    rel = ws["schema_path"] if ws else common.schema_page(root, rb["wiki_dir"])
    return rel[len(rb["wiki_dir"]) + 1:] if rel else None


def working_file(root, path, what):
    """`path`, refused when it is inside the folder: `what` is a working file, kept in the work dir or elsewhere."""
    real = os.path.realpath(path)
    if real == root or real.startswith(root + os.sep):
        raise common.ToolError("%s are working files, never written inside the folder: %s" % (what, path))
    return real


def cards_dirs(a, root):
    return (os.path.realpath(a.cards) if a.cards else os.path.join(root, "_Audit", "cards"),
            os.path.realpath(a.extract) if a.extract else os.path.join(root, "_Audit", "extract"))


# ------------------------------------------------------------------------------------ profile

def people_names(rb):
    """Every name and alias the rulebook records, lower-cased, to its canonical name."""
    names = {}
    for p in rb["people"]:
        for n in [p["name"]] + p.get("also", []):
            names.setdefault(n.strip().lower(), p["name"])
    return names


@os_errors
def profile(a):
    """Per folder, for the folder and each subfolder down to --depth: live documents (by current path), copies
    held there of documents whose current path is elsewhere or beside them, and from the documents' cards the
    categories, the doc_date span and the top parties (aliases folded to the rulebook's canonical names; each
    document counts a party once)."""
    if a.depth < 1 or a.parties < 1:
        raise common.ToolError("--depth and --parties count from 1")
    root, settings_dir, _work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    _mp, man = load_manifest(root, a.manifest)
    cards_dir, _x = cards_dirs(a, root)
    names = people_names(rb)
    migr = rb["migrations_dir"] + "/"
    rows = collections.defaultdict(lambda: {"documents": 0, "copies": 0, "copies_of": collections.Counter(),
                                            "carded": 0, "categories": collections.Counter(), "dates": [],
                                            "parties": collections.Counter()})
    total = {"documents": 0, "carded": 0, "copies": 0, "migrating": 0, "departed": 0}
    categories = collections.Counter()

    def folders(path):
        parts = path.split("/")[:-1]
        return ["/".join(parts[:i]) for i in range(1, min(len(parts), a.depth) + 1)] if parts else ["(root)"]

    for h, e in sorted(man.items(), key=lambda x: x[1]["current_path"]):
        p = e["current_path"]
        if "departed" in e.get("flags", []):
            total["departed"] += 1
            continue
        if p.startswith(migr):
            total["migrating"] += 1
            continue
        card = load_card(cards_dir, h)
        total["documents"] += 1
        parties = set()
        if card:
            total["carded"] += 1
            categories[card.get("category") or "Other"] += 1
            for n in [card.get("party") or ""] + list(card.get("parties") or []):
                n = n.strip()
                if n and n.lower() != "unknown":
                    parties.add(names.get(n.lower(), n))
        for f in folders(p):
            r = rows[f]
            r["documents"] += 1
            if card:
                r["carded"] += 1
                r["categories"][card.get("category") or "Other"] += 1
                if DOC_DATE.fullmatch(card.get("doc_date") or ""):
                    r["dates"].append(card["doc_date"])
                r["parties"].update(parties)
        for c in e.get("copies", []):
            if c["path"] == p or c["path"].startswith(migr):
                continue
            total["copies"] += 1
            for f in folders(c["path"]):
                rows[f]["copies"] += 1
                rows[f]["copies_of"][folders(p)[0]] += 1

    def ranked(counter, n=None):
        return [[k, v] for k, v in sorted(counter.items(), key=lambda x: (-x[1], x[0]))][:n]

    out = collections.OrderedDict(folder=os.path.basename(root), depth=a.depth, **total)
    out["uncarded"] = total["documents"] - total["carded"]
    out["categories"] = dict(ranked(categories))
    out["folders"] = [collections.OrderedDict(
        folder=f, documents=r["documents"], copies=r["copies"], copies_of=dict(sorted(r["copies_of"].items())),
        carded=r["carded"], categories=dict(ranked(r["categories"])), dated=len(r["dates"]),
        earliest=min(r["dates"]) if r["dates"] else None, latest=max(r["dates"]) if r["dates"] else None,
        parties=ranked(r["parties"], a.parties)) for f, r in sorted(rows.items())]
    text = json.dumps(out, ensure_ascii=False, indent=1) + "\n"
    if a.out:
        common.Writer(root if a.read_only_root else None).text(a.out, text)
    sys.stdout.write(text)
    return 0


# ------------------------------------------------------------------------------------ bundles

def route(ws, path):
    """The section number a folder-relative path routes to: its longest matching prefix's, or None when no prefix
    matches or that prefix's row is a note (no section)."""
    best = None
    for r in ws["routing"]:
        if path.startswith(r["prefix"]) and (best is None or len(r["prefix"]) > len(best["prefix"])):
            best = r
    return best["section"] if best else None


def routing_digest(ws):
    """sha256 of what routing a bundle depends on: every routing row's prefix and section, and each section's kind."""
    basis = {"routing": [[r["prefix"], r["section"]] for r in ws["routing"]],
             "kinds": {s["number"]: s["kind"] for s in ws["sections"]}}
    return hashlib.sha256(json.dumps(basis, sort_keys=True).encode("utf-8")).hexdigest()


BUILD_ARGS = (("settings_dir", "--settings-dir"), ("manifest", "--manifest"), ("cards", "--cards"),
              ("extract", "--extract"))
BUNDLES_META = {"manifest_sha256": str, "routing_sha256": str, "arguments": dict, "sections": dict, "compact": dict,
                "files": dict, "unrouted": list, "uncarded": list}


def build_arguments(a):
    """The non-default arguments `bundles` was given (absolute paths, and --text-cap when not the default), so a
    rebuild command can repeat them."""
    out = collections.OrderedDict((flag, os.path.realpath(getattr(a, key))) for key, flag in BUILD_ARGS
                                  if getattr(a, key, None))
    if getattr(a, "text_cap", TEXT_CAP) != TEXT_CAP:
        out["--text-cap"] = str(a.text_cap)
    return out


def bundles_command(verb, root, bdir, arguments):
    args = ["--root", root, "--out", bdir] + [x for kv in arguments.items() for x in kv]
    return "%s them: wiki.py bundles %s" % (verb, " ".join(shlex.quote(x) for x in args))


def fresh_bundles(root, bdir, mpath, ws, arguments):
    """bundles.json in `bdir`, refused unless it is one `bundles` wrote, built from the current manifest and routing,
    with every section's file there. The rebuild command repeats the arguments the bundles were built with
    (`arguments`, the caller's, when none are recorded)."""
    meta_path = os.path.join(bdir, "bundles.json")
    if not os.path.lexists(meta_path):
        raise common.ToolError("no bundles in %s; %s" % (bdir, bundles_command("build", root, bdir, arguments)))
    meta = read_object(meta_path)
    recorded = meta.get("arguments")
    texts = isinstance(recorded, dict) and all(isinstance(x, str) for kv in recorded.items() for x in kv)
    if texts:
        arguments = recorded
    rebuild = bundles_command("rebuild", root, bdir, arguments)
    bad = sorted(k for k, kind in BUNDLES_META.items() if not isinstance(meta.get(k), kind)
                 or (k in ("sections", "compact") and not all(type(v) is int for v in meta[k].values()))
                 or (k == "arguments" and not texts))
    if bad:
        raise common.ToolError("%s is not a bundles.json that wiki.py bundles wrote (%s missing or malformed); %s"
                               % (meta_path, ", ".join(bad), rebuild))
    have = common.sha256_file(mpath)
    if meta.get("manifest_sha256") != have:
        raise common.ToolError("stale bundles: %s records manifest sha256 %s, but %s is now %s (bundles go stale "
                               "after any migration or re-audit); %s"
                               % (meta_path, meta.get("manifest_sha256"), mpath, have, rebuild))
    if meta.get("routing_sha256") != routing_digest(ws):
        raise common.ToolError("stale bundles: %s was routed by another Schema routing or section kinds; %s"
                               % (meta_path, rebuild))
    missing = sorted(str(f) for f in meta["files"].values()
                     if not (isinstance(f, str) and BUNDLE_FILE.fullmatch(f) and os.path.isfile(os.path.join(bdir, f))))
    if missing:
        raise common.ToolError("incomplete bundles in %s: %s missing; %s" % (bdir, ", ".join(missing), rebuild))
    return meta


def bundle_summary(meta):
    return {"routed": sum(meta["sections"].values()), "sections": meta["sections"], "compact": meta["compact"],
            "unrouted": meta["unrouted"], "uncarded": meta["uncarded"]}


@os_errors
def bundles(a):
    root, settings_dir, work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    ws = common.load_wiki_schema(root, settings_dir)
    mpath, man = load_manifest(root, a.manifest)
    digest = common.sha256_file(mpath)
    out = working_file(root, a.out, "bundles") if a.out else os.path.join(work, "bundles")
    if os.path.exists(out) and not os.path.isdir(out):
        raise common.ToolError("--out %s is a file; bundles go in a directory" % out)
    writer = common.Writer(root)
    arguments = build_arguments(a)
    if a.reuse:
        meta = fresh_bundles(root, out, mpath, ws, arguments)
        print(json.dumps(bundle_summary(meta), ensure_ascii=False))
        return 1 if meta["unrouted"] or meta["uncarded"] else 0
    meta_path = os.path.join(out, "bundles.json")
    if os.path.isdir(meta_path):
        raise common.ToolError("%s is a directory; bundles.json must be a file, so remove it" % meta_path)
    if os.path.lexists(meta_path):
        os.remove(writer.check(meta_path))  # first: a rebuild that fails anywhere leaves no bundles.json to trust
    kinds = {s["number"]: s["kind"] for s in ws["sections"]}
    cards_dir, extract_dir = cards_dirs(a, root)
    bund, unrouted, uncarded = collections.defaultdict(list), [], []
    counts, compact = collections.Counter(), collections.Counter()
    for h, e in sorted(man.items(), key=lambda x: x[1]["current_path"]):
        p = e["current_path"]
        if "departed" in e.get("flags", []) or p.startswith(rb["migrations_dir"] + "/"):
            continue
        sec = route(ws, p)
        if sec is None:
            unrouted.append(p)
            continue
        c = load_card(cards_dir, h)
        if c is None:
            uncarded.append(p)
            continue
        xr = load_extract(extract_dir, h, os.path.join(cards_dir, h + ".json"))
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
    writer.makedirs(out)
    files = {sec: "bundle_%s.jsonl" % sec for sec in sorted(bund)}
    for sec, name in files.items():
        writer.text(os.path.join(out, name), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in bund[sec]))
    for name in sorted(os.listdir(out)):
        if BUNDLE_FILE.fullmatch(name) and name not in files.values():
            os.remove(writer.check(os.path.join(out, name)))
    meta = collections.OrderedDict(
        manifest_sha256=digest, routing_sha256=routing_digest(ws), arguments=arguments, text_cap=a.text_cap,
        sections=dict(sorted(counts.items())), compact=dict(sorted(compact.items())), files=files,
        unrouted=unrouted, uncarded=uncarded)
    writer.text(meta_path, json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(bundle_summary(meta), ensure_ascii=False))
    return 1 if unrouted or uncarded else 0


# ------------------------------------------------------------------------------------ brief

def owner_context(root, rb):
    people = "\n".join("- %s%s%s" % (p["name"], " (also %s)" % ", ".join(p["also"]) if p.get("also") else "",
                                      ": " + p["who"] if p.get("who") else "") for p in rb["people"])
    bounds = "\n".join("- %s" % (b if isinstance(b, str) else json.dumps(b, ensure_ascii=False, sort_keys=True))
                       for b in rb["boundaries"])
    return "\n".join([
        "The folder `%s`: %s" % (os.path.basename(root), rb["folder_description"] or "no description recorded."),
        "", "People and organisations, each with the other names they appear under:", "",
        people or "- none recorded", "",
        "Identifiers (`%s`): reference numbers %s. Passwords and activation codes are never written, under any "
        "policy." % (rb["identifiers"], cards.identifier_rule(rb)), "",
        "Boundaries inside the folder:", "", bounds or "- none recorded"])


def section_of(ws, page):
    return next(s for s in ws["sections"] if page.startswith("%s %s/" % (s["number"], s["name"])))


def page_map(ws, wiki, briefed):
    """{page: "exists" | "planned"}: see the module docstring."""
    have = set(wiki_pages(wiki))
    planned = set(ws["pages"]) | {"%s %s/%s %s.md" % ((s["number"], s["name"]) * 2) for s in ws["sections"]}
    return {p: "exists" if p in have else "planned" for p in sorted(have | planned | set(briefed))}


def page_entry(p, state, sec, voice, contract, ws, bundle):
    lines = ["### %s" % p, "",
             "- Status: %s" % ("exists (revise it)" if state == "exists" else "planned (write it)"),
             "- Section: %s %s, %s%s" % (sec["number"], sec["name"], sec["kind"],
                                         ", derived" if sec["derived"] else ""),
             "- Professional: %s (%s)" % (voice["professional"], "the page's row in the Page professionals table"
                                          if voice["source"] == "page" else "the section's one professional"),
             "- Deliverable: %s" % (voice["deliverable"] or "not recorded; the professional's usual deliverable"),
             "- Tone: %s" % (voice["tone"] or "not recorded; the professional's usual tone")]
    if contract:
        lines += ["- Reader: %s" % (contract["reader"] or "not recorded in the Schema"),
                  "- Questions, most important first:"]
        lines += ["  %d. %s" % (i, q) for i, q in enumerate(contract["questions"], 1)]
        lines.append("- Fields every page carries: %s" % ", ".join(contract["fields"]))
    else:
        lines.append("- Contract: the method's own, as a fixed section (`wiki-onboarding` and `wiki-maintenance` "
                     "give its shape)")
    routes = [r for r in ws["routing"] if r["section"] == sec["number"]]
    lines.append("- Files routed to the section:%s" % ("" if routes else " none"))
    lines += ["  - `%s`: %s" % (r["prefix"], r["target"]) for r in routes]
    lines.append("- Bundle: %s" % bundle)
    return "\n".join(lines)


def rationale_skeleton(p, state, voice, contract):
    reader = contract["reader"] if contract and contract["reader"] else "<who reads the page>"
    asks = (" ".join("%d. %s" % (i, q) for i, q in enumerate(contract["questions"], 1)) if contract
            else "<the questions the page answers, numbered in its order>")
    return "\n".join([
        "### %s" % p,
        "- Reader and use: %s, <what they use the page for>" % reader,
        "- Professional lens: %s; questions answered in order: %s" % (voice["professional"], asks),
        "- Shape: <the page's structure and visuals and why, or \"as the Schema sets out\">",
        "- Changed from the previous page: %s" % ("first version" if state == "planned"
                                                  else "<what this version changed>"),
        "- Left out or flagged: <what was left out and why, and what was flagged for the owner, or \"nothing\">"])


def return_shape(pages):
    shape = {"pages": [{"path": p, "text": "<the page exactly as written to the wiki folder, frontmatter first>",
                        "rationale": "<its rationale block: the heading and five lines above, joined by \\n>"}
                       for p in pages],
             "check_problems_on_these_pages": 0,
             "flags": ["<for the owner or the coordinating agent: a gap, sources that disagree, a dated rule "
                       "left unchecked, a finding the checker names on another page>"]}
    return json.dumps(shape, ensure_ascii=False, indent=1)


def render_template(name, **fields):
    """A template in tools/templates, its leading comment dropped, its relative links made absolute (so they still
    resolve wherever the rendered text is read) and its fields filled."""
    text = re.sub(r"\A<!--.*?-->\n+", "", read_text(os.path.join(TEMPLATES, name)), flags=re.S)

    def absolute(m):
        path, _hash, anchor = m.group(1).partition("#")
        return "](%s%s)" % (urllib.parse.quote(os.path.normpath(os.path.join(TEMPLATES, path)), safe="/&"),
                            "#" + anchor if anchor else "")
    return re.sub(r"\]\((\.\.?/[^)\s]*)\)", absolute, text).format(**fields)


@os_errors
def brief(a):
    root, settings_dir, work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    ws = common.load_wiki_schema(root, settings_dir)
    mpath, _man = load_manifest(root, a.manifest)
    bdir = os.path.realpath(a.bundles) if a.bundles else os.path.join(work, "bundles")
    meta = fresh_bundles(root, bdir, mpath, ws, build_arguments(a))
    wiki = os.path.join(root, rb["wiki_dir"])
    pages = sorted(set(a.page))
    for p in pages:
        if not is_page_path(p):
            raise common.ToolError("--page %r is not a page path relative to the wiki folder, like "
                                   "'<NN Section>/<Page>.md'" % p)
    voices = {p: common.page_voice(ws, p) for p in pages}
    contracts = {c["number"]: c for c in ws["contracts"]}
    pmap = page_map(ws, wiki, pages)
    entries, skeletons = [], []
    for p in pages:
        sec = section_of(ws, p)
        contract = contracts.get(sec["number"])
        if contract is None and sec["kind"] != "fixed":
            raise common.ToolError("section %s %s has no page contract in the Schema; its professional drafts one "
                                   "first (templates/contract-brief.md)" % (sec["number"], sec["name"]))
        f = meta["files"].get(sec["number"])
        n, k = meta["sections"].get(sec["number"], 0), meta["compact"].get(sec["number"], 0)
        bundle = ("`%s` (%d document%s%s)" % (os.path.join(bdir, f), n, "" if n == 1 else "s",
                                              ", %d of them compact: listed without summary or text" % k if k else "")
                  if f else "none: no carded document routes to this section")
        entries.append(page_entry(p, pmap[p], sec, voices[p], contract, ws, bundle))
        skeletons.append(rationale_skeleton(p, pmap[p], voices[p], contract))
    checker = ["python3", os.path.join(HERE, "wiki.py"), "check", "--root", root, "--work", work]
    checker += ["--settings-dir", settings_dir] if a.settings_dir else []
    checker += ["--manifest", os.path.realpath(mpath)] if a.manifest else []
    text = render_template(
        "page-brief.md", folder_name=os.path.basename(root), owner_context=owner_context(root, rb),
        pages="\n\n".join(entries),
        page_map="\n".join("- `%s` (%s%s)" % (p, s, ", in this brief" if p in pages else "") for p, s in pmap.items()),
        bundles_dir=bdir, wiki_dir=wiki, schema_path=os.path.join(root, ws["schema_path"]),
        checker=" ".join(shlex.quote(x) for x in checker), return_shape=return_shape(pages),
        rationale="\n\n".join(skeletons))
    if a.out:
        common.Writer(root).text(working_file(root, a.out, "briefs"), text)
    sys.stdout.write(text)
    return 0


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

def local_link(lk):
    """True for a link to a file by relative path: no scheme (http:, mailto:, obsidian:) and not rooted at /."""
    return not (lk.startswith("/") or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", lk))


def link_target(page, lk):
    """The page a relative link on `page` points at, relative to the wiki folder."""
    return posixpath.normpath(posixpath.join(posixpath.dirname(page), urllib.parse.unquote(lk)))


def link_to(page, target):
    """The relative link from `page` to `target`, percent-encoded with `/` and `&` literal."""
    return urllib.parse.quote(posixpath.relpath(target, posixpath.dirname(page) or "."), safe="/&")


def dead_links(wiki):
    return [[p, lk] for p in wiki_pages(wiki) for lk, _a in LINK.findall(read_text(os.path.join(wiki, p)))
            if local_link(lk) and not os.path.exists(os.path.join(wiki, *link_target(p, lk).split("/")))]


def check_moves(wiki, moves, pages, schema):
    """Refuse, before anything is written, a map that could not be carried out whole."""
    if not (isinstance(moves, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in moves.items())):
        raise common.ToolError("--map must be a JSON object of page path to new page path")
    targets = set(moves.values())
    for old, new in sorted(moves.items()):
        if old not in pages:
            raise common.ToolError("page not found: %s" % old)
        if old == schema:
            raise common.ToolError("%s is the Schema page, which the settings twin is compiled from; move it by hand "
                                   "and recompile" % old)
        if not is_page_path(new):
            raise common.ToolError("destination %r is not a page path inside the wiki folder (relative, `/` "
                                   "separated, ending in .md, no part empty, hidden or with a space at either end)"
                                   % new)
        if new in pages or os.path.lexists(os.path.join(wiki, *new.split("/"))):
            raise common.ToolError("destination exists: %s" % new)
        parts = new.split("/")
        for i in range(1, len(parts)):
            above = "/".join(parts[:i])
            path = os.path.join(wiki, *parts[:i])
            if above in targets or (os.path.lexists(path) and not os.path.isdir(path)):
                raise common.ToolError("destination %s lies under %s, which is a %s, not a folder"
                                       % (new, above, "page this map moves there" if above in targets else "file"))
    twice = sorted(n for n, k in collections.Counter(moves.values()).items() if k > 1)
    if twice:
        raise common.ToolError("two pages moved to one destination: %s" % ", ".join(twice))


def layout_findings(ws, moves):
    """[old, new, why] for each move that leaves the Schema's Layout wrong: a page moved out of every Layout section,
    or a section's folder note moved away."""
    if not ws:
        return []
    homes = {"%s %s" % (s["number"], s["name"]) for s in ws["sections"]}
    out = []
    for old, new in sorted(moves.items()):
        if new.split("/")[0] not in homes or "/" not in new:
            out.append([old, new, "the new path is in no Layout section"])
        folder = old.split("/")[0]
        if folder in homes and old == "%s/%s.md" % (folder, folder):
            out.append([old, new, "the old path was section %s's folder note" % folder])
    return out


@os_errors
def move(a):
    root, settings_dir, _work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    ws = common.load_wiki_schema(root, settings_dir, required=False)
    wiki = os.path.join(root, rb["wiki_dir"])
    writer = common.Writer(root if a.read_only_root else None)
    moves = read_json(a.map)
    pages = wiki_pages(wiki)
    check_moves(wiki, moves, pages, schema_rel(root, rb, ws))
    out, links = {}, 0
    for old in pages:
        new = moves.get(old, old)
        txt = read_text(os.path.join(wiki, old))

        def fix(m, old=old, new=new):
            nonlocal links
            lk, anchor = m.group(1), m.group(2) or ""
            if not local_link(lk):
                return m.group(0)
            tgt = link_target(old, lk)
            if new == old and tgt not in moves:
                return m.group(0)
            link = "](" + link_to(new, moves.get(tgt, tgt)) + anchor + ")"
            links += link != m.group(0)
            return link
        new_txt = LINK.sub(fix, txt)
        if new != old or new_txt != txt:
            out[new] = new_txt
    # moved pages first: a failure while rewriting the others then leaves no link to a page that was not moved
    moved = set(moves.values())
    for new, txt in sorted(out.items(), key=lambda x: (x[0] not in moved, x[0])):
        writer.text(os.path.join(wiki, *new.split("/")), txt)
    emptied = set()
    for old in sorted(moves):
        os.remove(writer.check(os.path.join(wiki, *old.split("/"))))
        parts = old.split("/")[:-1]
        emptied.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
    removed = []
    for d in sorted(emptied, key=lambda x: -x.count("/")):  # deepest first; a folder a move emptied goes
        path = os.path.join(wiki, *d.split("/"))
        if os.path.isdir(path) and not os.listdir(path):
            os.rmdir(writer.check(path))
            removed.append(d)
    renamed = 0
    rat = os.path.join(root, "_Audit", "wiki-rationale.md")
    if moves and os.path.exists(rat):
        text = read_text(rat)

        def rename(m):
            nonlocal renamed
            if m.group(1) not in moves:
                return m.group(0)
            renamed += 1
            return "### " + moves[m.group(1)]
        new_text = re.sub(r"^### (.+?\.md)[ \t]*$", rename, text, flags=re.M)
        if new_text != text:
            writer.text(rat, new_text)
    named = [[old, moves[old]] for old in sorted(moves) if ws and old in ws["pages"]]
    layout = layout_findings(ws, moves)
    dead = dead_links(wiki)
    print(json.dumps({"moved": len(moves), "pages_rewritten": len(out), "links_rewritten": links,
                      "folders_removed": sorted(removed), "rationale_blocks_renamed": renamed,
                      "schema_rows_to_update": named, "layout_to_update": layout, "dead_links": dead},
                     ensure_ascii=False))
    if named:
        print("the Schema's Page professionals table names %d moved page(s) by the old path; edit those rows, then "
              "settings.py compile" % len(named), file=sys.stderr)
    if layout:
        print("the Schema's Layout no longer matches %d move(s) (layout_to_update); edit the Layout, then "
              "settings.py compile" % len(layout), file=sys.stderr)
    return 1 if dead or named or layout else 0


# ------------------------------------------------------------------------------------ drift

def drift_paths(rb, man):
    """{folder-relative path: "departed" | "migrating"}: see the module docstring."""
    live = set()
    for e in man.values():
        if "departed" not in e.get("flags", []):
            live.add(e["current_path"])
            live.update(c["path"] for c in e.get("copies", []))
    migr = rb["migrations_dir"] + "/"
    out = {}
    for e in man.values():
        held = [e["current_path"]] + [c["path"] for c in e.get("copies", [])]
        if "departed" in e.get("flags", []):
            out.update({p: "departed" for p in held if p not in live and p not in out})
        elif "migrating" in e.get("flags", []):
            for p in held:
                if p.startswith(migr):
                    out[p] = "migrating"
                    staged_from = p[len(migr):].split("/", 1)[1:]
                    if staged_from and staged_from[0] not in live:
                        out[staged_from[0]] = "migrating"
    return out


def fence_opened(line):
    """The fence `line` opens, by the rule `chart_blocks` reads fences with (FENCE_OPEN: 0 to 3 spaces, then three
    or more backticks or tildes; a backtick fence's info string holds no backtick), or None."""
    m = FENCE_OPEN.fullmatch(line)
    return m.group(1) if m and not (m.group(1)[0] == "`" and "`" in m.group(2)) else None


def fence_closed(line, fence):
    m = FENCE_CLOSE.fullmatch(line)
    return bool(m) and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence)


CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)  # a run of n backticks closes at the next run of n


def citations(text):
    """[(line, path)]: every `sources:` entry in the page's frontmatter, and every code span in its body (fenced
    blocks skipped; a span may wrap onto the next line, read as one space), with the line it starts on."""
    lines = text.split("\n")
    found, body = [], 0
    if lines and lines[0] == "---" and "---" in lines[1:]:
        body = lines.index("---", 1) + 1
        key = None
        for n in range(1, body - 1):
            m = re.match(r"^([A-Za-z_-]+):", lines[n])
            if m:
                key = m.group(1)
                continue
            m = re.match(r"^\s+-\s+(.*?)\s*$", lines[n])
            if m and key == "sources":
                found.append((n + 1, m.group(1).strip('"').strip("'")))
    fence, rest = None, []
    for line in lines[body:]:
        if fence:
            fence = None if fence_closed(line, fence) else fence
            rest.append("")
            continue
        fence = fence_opened(line)
        rest.append("" if fence else line)
    i = 0
    while i < len(rest):
        if not rest[i].strip():
            i += 1
            continue
        j = i
        while j < len(rest) and rest[j].strip():
            j += 1
        para = "\n".join(rest[i:j])
        for m in CODE_SPAN.finditer(para):
            found.append((body + i + para.count("\n", 0, m.start()) + 1, re.sub(r"[ \t]*\n[ \t]*", " ", m.group(2))))
        i = j
    return sorted(found)


@os_errors
def drift(a):
    root, settings_dir, _work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    _mp, man = load_manifest(root, a.manifest)
    wiki = os.path.join(root, rb["wiki_dir"])
    paths = drift_paths(rb, man)
    kinds = collections.Counter(paths.values())
    pages = [p for p in wiki_pages(wiki) if not p.startswith(LOG_DIR + "/")]
    cited = {"departed": [], "migrating": []}
    for p in pages:
        for line, path in citations(read_text(os.path.join(wiki, *p.split("/")))):
            if path in paths:
                cited[paths[path]].append([p, line, path])
    res = collections.OrderedDict(
        wiki=rb["wiki_dir"], pages_read=len(pages), departed_paths=kinds["departed"],
        migrating_paths=kinds["migrating"], citing_departed=len(cited["departed"]),
        citing_migrating=len(cited["migrating"]),
        pages_citing=len({c[0] for cs in cited.values() for c in cs}), departed=cited["departed"],
        migrating=cited["migrating"])
    text = json.dumps(res, ensure_ascii=False, indent=1) + "\n"
    if a.out:
        common.Writer(root if a.read_only_root else None).text(a.out, text)
    sys.stdout.write(text)
    return 1 if res["citing_departed"] or res["citing_migrating"] else 0


# ------------------------------------------------------------------------------------ chart

CHART_COLUMNS = {  # kind: (the columns every row has, "a|b" meaning exactly one of the two; optional columns)
    "bar": (("label|period", "value", "unit", "source"), ()),
    "line": (("period", "value", "unit", "source"), ()),
    "pie": (("label", "value", "unit", "source"), ()),
    "gantt": (("label", "start", "end", "source"), ("section",)),
    "timeline": (("date", "label", "source"), ()),
}
SERIES = ("bar", "line", "pie")
CHART_TABLES = {  # chart pairing: the header row of the data table `chart` writes after a block, by Mermaid type
    "xychart-beta": re.compile(r"\| (Label|Period) \| Value \([^|]+\) \| Source \|"),
    "pie": re.compile(r"\| Label \| Value \([^|]+\) \| Source \|"),
    "gantt": re.compile(r"\| (Section \| )?Label \| Start \| End \| Source \|"),
    "timeline": re.compile(r"\| Date \| Label \| Source \|"),
}
TABLE_RULE = re.compile(r"\|( *:?-{3,}:? *\|)+")
SOURCED_ROW = re.compile(r"\|.*\| `[^`]+` \|")
FENCE_OPEN = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
FENCE_CLOSE = re.compile(r" {0,3}(`{3,}|~{3,})[ \t]*")
NUMBER = re.compile(r"-?[0-9]+(\.[0-9]+)?")
ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
         r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?")
DAY = r"[0-9]{1,2}(?:st|nd|rd|th)?"
DATE_LIKE = re.compile(  # a date in any spelling: year first, day and month in figures, or a named month with a day
    r"(?<![0-9a-z.])(?:(?P<ymd>[0-9]{4}(?P<s1>[-/.])[0-9]{1,2}(?P=s1)[0-9]{1,2})"
    r"|(?P<a>[0-9]{1,2})(?P<s2>[-/.])(?P<b>[0-9]{1,2})(?P=s2)(?:[0-9]{4}|[0-9]{2})"
    r"|%s (?:of )?%s,? [0-9]{2}(?:[0-9]{2})?|%s %s,? [0-9]{2}(?:[0-9]{2})?)(?![0-9a-z]|\.[0-9])"
    % (DAY, MONTH, MONTH, DAY), re.I)
UNCARRIED = '"`|#;'  # no chart text holds these: each breaks a Mermaid line or the Markdown table
GANTT_KEYWORDS = ("title", "section", "dateFormat", "axisFormat", "tickInterval", "excludes", "includes",
                  "todayMarker", "click", "weekday", "topAxis")  # a gantt line starting with one is not a task


def chart_rows(path):
    """The rows of a chart's data file, in order, and where each is: a .csv with a header row (`line N` of the file,
    blank lines counted, the header on line 1 when first), or a .json array of objects (`row N`, from 1). Every value
    comes back as text exactly as written (a JSON number as its literal text)."""
    name = os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".csv", ".json"):
        raise common.ToolError("--data must be a .csv or .json file: %s" % path)
    if not os.path.isfile(path):
        raise common.ToolError("--data missing: %s" % path)
    if ext == ".csv":
        table = []
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                start = 1
                for r in reader:
                    if r:
                        table.append(("line %d" % start, r))
                    start = reader.line_num + 1
        except (UnicodeDecodeError, csv.Error) as e:
            raise common.ToolError("%s: not readable as UTF-8 CSV (%s)" % (path, e))
        if not table:
            raise common.ToolError("%s: empty; a chart's CSV starts with a header row" % path)
        head = table[0][1]
        if len(set(head)) != len(head):
            raise common.ToolError("%s: the header row repeats a column: %s" % (path, head))
        rows, places = [], []
        for place, r in table[1:]:
            if len(r) != len(head):
                raise common.ToolError("%s %s: %d cells, but the header has %d" % (name, place, len(r), len(head)))
            rows.append(dict(zip(head, r)))
            places.append(place)
    else:
        def pairs(items):
            keys = [k for k, _ in items]
            if len(set(keys)) != len(keys):
                raise common.ToolError("%s: an object repeats a key: %s" % (path, keys))
            return dict(items)

        def constant(c):
            raise common.ToolError("%s: %s is not a value a chart can show" % (path, c))
        try:
            with open(path, encoding="utf-8-sig") as f:
                rows = json.load(f, parse_int=str, parse_float=str, parse_constant=constant, object_pairs_hook=pairs)
        except ValueError as e:
            raise common.ToolError("%s: not valid JSON (%s)" % (path, e))
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise common.ToolError("%s: expected a JSON array of objects, one per row" % path)
        places = ["row %d" % n for n in range(1, len(rows) + 1)]
        for place, r in zip(places, rows):
            for k, v in r.items():
                if not isinstance(v, str):
                    raise common.ToolError("%s %s: %s must be text or a number, not %s"
                                           % (name, place, k, json.dumps(v)))
    if not rows:
        raise common.ToolError("%s: no rows" % path)
    return rows, places


def chart_date(value):
    """The date a YYYY-MM-DD text names, or None."""
    if not ISO_DATE.fullmatch(value):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def chart_text(value, what, where, uncarried=""):
    """`value`, refused (naming `where`) when empty, padded, opening with `%%` (a Mermaid comment), holding a
    character the chart cannot carry, or holding a date not written YYYY-MM-DD."""
    if value == "":
        raise common.ToolError("%s: no %s" % (where, what))
    if value != value.strip():
        raise common.ToolError("%s: %s %r has spaces at its ends" % (where, what, value))
    if value.startswith("%%"):
        raise common.ToolError("%s: %s %r starts with %%%%, which Mermaid reads as a comment" % (where, what, value))
    bad = sorted({ch for ch in value if ch in UNCARRIED + uncarried or ord(ch) < 32 or ord(ch) == 127})
    if bad:
        raise common.ToolError("%s: %s %r holds %s, which a chart or its table cannot carry"
                               % (where, what, value, " ".join(repr(c) for c in bad)))
    for m in DATE_LIKE.finditer(value):
        if m.group("ymd") and chart_date(m.group(0)):
            continue
        if m.group("a") and not (0 < int(m.group("a")) <= 31 and 0 < int(m.group("b")) <= 31
                                 and min(int(m.group("a")), int(m.group("b"))) <= 12):
            continue  # figures that cannot be a day and a month, such as a version number
        raise common.ToolError("%s: %s %r holds the date %r; write dates YYYY-MM-DD"
                               % (where, what, value, m.group(0)))
    return value


def chart_source(root, value, where, reserved):
    """Refuse a source that is not a file or folder inside the folder being prepared (`root`, a real path), or that
    lies under one of its reserved names (the wiki, _Audit, the settings, the inbox and the like), which are not
    data."""
    if value == "":
        raise common.ToolError("%s: no source; every row names the file or folder its figures come from, by "
                               "folder-relative path" % where)
    parts = (value[:-1] if value.endswith("/") else value).split("/")
    if (value != value.strip() or os.path.isabs(value) or "\\" in value or any(p in ("", ".", "..") for p in parts)
            or any(ch in "`|" or ord(ch) < 32 for ch in value)):
        raise common.ToolError("%s: source %r is not a folder-relative path" % (where, value))
    real = os.path.realpath(os.path.join(root, value))
    if not os.path.exists(real):
        raise common.ToolError("%s: source %r does not exist in %s" % (where, value, root))
    if not real.startswith(root + os.sep):
        raise common.ToolError("%s: source %r resolves to %s, outside %s" % (where, value, real, root))
    for rel in (value.rstrip("/"), os.path.relpath(real, root).replace(os.sep, "/")):
        name = next((n for n in reserved if rel.casefold() == n.casefold()
                     or rel.casefold().startswith(n.casefold() + "/")), None)
        if name:
            raise common.ToolError("%s: source %r is under %s, which the folder reserves; cite the document itself"
                                   % (where, value, name))


def chart_row_date(row, col, where):
    d = chart_date(row[col])
    if d is None:
        raise common.ToolError("%s: %s %r is not a date written YYYY-MM-DD" % (where, col, row[col]))
    return d


def render_chart(root, kind, title, rows, where, places, reserved):
    """The Mermaid block for `rows`, a blank line, then their data table; refused when a rule is broken, naming the
    row by `where` (the data file) and its entry in `places` (as `chart_rows` gives them). `reserved` is the folder's
    reserved top-level names, under which no source may lie."""
    required, optional = CHART_COLUMNS[kind]
    cols = set(rows[0])
    for place, r in zip(places, rows):
        if set(r) != cols:
            raise common.ToolError("%s %s: columns %s differ from the first row's %s"
                                   % (where, place, sorted(r), sorted(cols)))
    if "source" not in cols:
        raise common.ToolError("%s: no source column; every row needs its source, the folder-relative path of the "
                               "file or folder its figures come from" % where)
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
    for place, r in zip(places, rows):
        at = "%s %s" % (where, place)
        chart_source(root, r["source"], at, reserved)
        if kind in SERIES:
            chart_text(r[key], key, at)
            if r[key] in seen:
                raise common.ToolError("%s: %s %r repeats %s's" % (at, key, r[key], seen[r[key]]))
            seen[r[key]] = place
            if not NUMBER.fullmatch(r["value"]):
                raise common.ToolError("%s: value %r is not a plain decimal (digits, an optional minus sign and "
                                       "decimal point; no separators, symbols or exponent)" % (at, r["value"]))
            if kind == "pie" and decimal.Decimal(r["value"]) <= 0:
                raise common.ToolError("%s: pie value %r is not positive" % (at, r["value"]))
            chart_text(r["unit"], "unit", at)
            if r["unit"] != rows[0]["unit"]:
                raise common.ToolError("%s: unit %r differs from the first row's %r; a chart has one unit"
                                       % (at, r["unit"], rows[0]["unit"]))
        elif kind == "gantt":
            for col in ("label", "section"):
                if col in r:
                    chart_text(r[col], col, at, ":")
                    if r[col].split()[0] in GANTT_KEYWORDS:
                        raise common.ToolError("%s: %s %r starts with the gantt keyword %r, so Mermaid would not read "
                                               "it as a task" % (at, col, r[col], r[col].split()[0]))
            start, end = chart_row_date(r, "start", at), chart_row_date(r, "end", at)
            if end < start:
                raise common.ToolError("%s: ends %s, before it starts %s" % (at, r["end"], r["start"]))
        else:
            chart_row_date(r, "date", at)
            chart_text(r["label"], "label", at, ":")
    if kind == "pie" and not re.search(r"(?<!\w)%s(?!\w)" % re.escape(rows[0]["unit"]), title):
        raise common.ToolError("--title %r must name the unit %r as a word: a pie has no axis to carry it"
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
    """Chart pairing: the Mermaid blocks in a page of a type `chart` renders, as (line of the opening fence in the
    page, type, paired). Only a fence opened at the outermost level with the info string `mermaid` counts: one
    quoted inside another fenced block (backticks or tildes, closed only by a fence of the same character at least
    as long) or in an indented code block is an example, not a chart. Paired: the next non-blank line after the
    block starts the data table `chart` writes for that type, its header row, the rule row, then at least one row,
    every row ending in a backticked source."""
    raw = text.splitlines()
    lines = [x.strip() for x in raw]
    found, i = [], 0

    def closes(line, fence):
        m = FENCE_CLOSE.fullmatch(line)
        return bool(m) and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence)
    while i < len(raw):
        m = FENCE_OPEN.fullmatch(raw[i])
        i += 1
        if not m or (m.group(1)[0] == "`" and "`" in m.group(2)):
            continue  # not a fence (indented four or more is code; a backtick after backticks is inline code)
        fence, start = m.group(1), i
        while i < len(raw) and not closes(raw[i], fence):
            i += 1
        body, i = lines[start:i], i + 1
        if m.group(2).split()[:1] != ["mermaid"]:
            continue
        kind = next((x.split()[0] for x in body if x and not x.startswith("%%")), None)
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
        found.append((start, kind, bool(rows) and all(SOURCED_ROW.fullmatch(r) for r in rows)))
    return found


def chart(a):
    root, settings_dir, _work = common.resolve(a)
    reserved = common.reserved_names(common.load_rulebook(root, settings_dir))
    rows, places = chart_rows(a.data)
    out = render_chart(root, a.kind, a.title, rows, os.path.basename(a.data), places, reserved)
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

    def card_args(p):
        p.add_argument("--cards", help="card records (default <root>/_Audit/cards)")
        p.add_argument("--extract", help="extract records (default <root>/_Audit/extract)")
        return p

    p = card_args(common_args(sub.add_parser("profile")))
    p.add_argument("--depth", type=int, default=2, help="folder levels profiled (default 2)")
    p.add_argument("--parties", type=int, default=5, help="top parties listed per folder (default 5)")
    p.add_argument("--out")
    p = card_args(common_args(sub.add_parser("bundles")))
    p.add_argument("--out", help="the bundles directory (default <work>/bundles; never inside the folder)")
    p.add_argument("--text-cap", type=int, default=TEXT_CAP)
    p.add_argument("--reuse", action="store_true", help="use the bundles already built, refused when stale")
    p = common_args(sub.add_parser("brief"))
    p.add_argument("--page", action="append", required=True, help="a page to brief, relative to the wiki folder")
    p.add_argument("--bundles", help="the bundles directory (default <work>/bundles)")
    p.add_argument("--out", help="also write the brief here (never inside the folder)")
    p = common_args(sub.add_parser("check"))
    p.add_argument("--out")
    p = common_args(sub.add_parser("move"))
    p.add_argument("--map", required=True)
    p = common_args(sub.add_parser("drift"))
    p.add_argument("--out")
    p = common_args(sub.add_parser("chart"))
    p.add_argument("--kind", required=True, choices=list(CHART_COLUMNS))
    p.add_argument("--data", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--out")
    a = ap.parse_args()
    return {"profile": profile, "bundles": bundles, "brief": brief, "check": check, "move": move, "drift": drift,
            "chart": chart}[a.cmd](a)


if __name__ == "__main__":
    common.run_main(main)
