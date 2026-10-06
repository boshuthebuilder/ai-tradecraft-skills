#!/usr/bin/env python3
"""Wiki tools for proposing, drafting and checking a folder's wiki.

    wiki.py profile --root R T [--depth 2] [--out <json>] per-folder documents, copies, cards by category, date span
                                                           and top parties, for the librarian's structure proposal
    wiki.py bundles --root R T [--out <dir>] [--reuse]    per-section evidence bundles (JSONL) for drafting agents,
                                                           in <work>/bundles/ by default, never in the folder
    wiki.py brief   --root R T --page P [--page P ...] [--out <md>]
                                                           the drafting brief for a set of pages, from
                                                           templates/page-brief.md
    wiki.py check   --root R [--page P ...] [--rationale <md>] [--acceptance <json>] [--out <json>]
                                                           deterministic checks; every item a count, zero included,
                                                           or a named not-verified state; acceptance reported apart
    wiki.py rationale --root R --returns <dir|json> [--out <md>]
                                                           _Audit/wiki-rationale.md from the drafters' returns
    wiki.py review-prompts --root R T --page P [--page P ...] --author-model A --reviewer-model B [--sample 5]
                           [--cards <dir>] [--out <dir>]   the owner's and the professional's review prompt per page
    wiki.py accept  --root R --reply <json> --author-model A --reviewer-model B [--date D] [--out <json>]
                                                           record one review verdict in _Audit/wiki-acceptance.json
    wiki.py move    --root R --map <json>                  move pages ({"old rel": "new rel"}), rewrite every
                                                           relative link to or from them
    wiki.py drift   --root R [--out <json>]                page lines and `sources:` entries citing a departed or
                                                           migrating path
    wiki.py chart   --root R --kind K --data <rows.csv|rows.json> --title T [--out <md>]
                                                           a Mermaid chart and its data table, from cited rows
    wiki.py deadlines --root R [--today D] [--write [--out <md>]]
                                                           the derived `01 Deadlines` page, from the pages'
                                                           `deadline`, `deadlines` and `recurring` frontmatter

Every subcommand takes --settings-dir, --work, --manifest (default <root>/_Audit/manifest.json) and
--read-only-root; profile and bundles also take --cards and --extract (default <root>/_Audit/cards, .../extract).
`T` is `--terms F` (the operator's isolation terms file) or `--no-isolation-terms`, one of which `profile`, `bundles`,
`brief` and `review-prompts` require (the refusal `cards.py work` makes): they write what a model will read, and every
string they write (a path, a card field, extract text, a page's text) is shielded first, each term and marker of the
list replaced by `[withheld name]` (`isolation.shield`; the placeholder stands in a path, so a path that carries a
term is not one a command can open). They say on stderr how many occurrences were replaced, never which. A short
term also masks inside longer words, which garbles the word and never leaks the term: prefer full names. The one
thing left as it was is the sha256 of a page in a review prompt, which `accept` compares with the page on disk.
Page paths are relative to the wiki folder, source paths to the folder. Bundles, briefs and review prompts are
working files, never written inside the folder, and so is every report written with --out (profile, check, drift, chart:
they carry manifest, card or path data, are registered for a later purge, and profile, check and drift also print their
JSON); rationale and accept write their audit file, the owner's gate record, in <root>/_Audit/ by default.

Check: every page under the wiki folder (dot folders skipped). Problems, each counted: a page missing a frontmatter
key (provenance, last-updated, status) or with `sources:` written as one value rather than a list; a `sources:`
entry that does not exist; a backticked body span holding `/` whose first segment is a live top-level folder (one
holding a live manifest entry or copy) and that does not exist (any other such span is counted as unchecked; the
Log's pages are history and not read); a link that does not resolve, or resolves to a file that is not a page (a
link to a page the page map only plans is dead until the page is written), local links being those `move` rewrites
(`local_link`) and a link's "title" allowed; a body line with an em dash outside inline code (lines counted from the
page's first); a document in scope (live, and not withheld: `common.withheld`) that no page names by its path or a
copy's, in `sources:` or a backticked span, and whose own parent folder no page names in backticks, with or without the
trailing `/` (the Schema page's routing and the Log do not count); a Mermaid block that does not parse as a kind
`chart` renders, a chart block without its data table, or a table source `chart` would refuse (missing, outside the
folder or reserved); a page with no single professional (`common.page_voice` refuses it); and in the rationale file
(below) a page with no block, a block for no page, a page's second block, a malformed block, or a block whose
Professional lens, up to its first `;`, does not name the page's professional (names compared case-folded, spaces
collapsed). Each heading is reported once, by the first that holds of: repeated, malformed, for no page, lens. Without
a compiled Schema the professional checks are `not verified`; without a rationale file, `rationale` is `not
recorded`. A --rationale or --acceptance path given that does not exist is refused. With --page (a drafting agent's
check, the command its brief names) only those pages are read: a link to a page the page map plans but nobody has
written yet is listed in `links_to_planned_pages` rather than as dead, and coverage, rationale and acceptance read
`not checked`, left to the coordinator's whole-wiki check.

Rationale: `_Audit/wiki-rationale.md`, as `wiki-maintenance` defines it: the line `# Wiki rationale`, then per page
a heading `### <page path>` and exactly five lines, `- Reader and use: `, `- Professional lens: `, `- Shape: `,
`- Changed from the previous page: `, `- Left out or flagged: `, each followed by text; blank lines only between
blocks. `rationale` reads the returns `brief` asks drafters for (a JSON file holding one return or a list of them,
or a directory of such files), refuses a malformed block, a heading that is not its entry's path and a page returned
twice, and writes the whole file, pages sorted by path; it exits 1 when a page in the wiki has no block or a block
names no page in it.

Review prompts: per page, templates/review-owner.md (the contract's reader and questions, in order) and
templates/review-professional.md (the page's professional, deliverable and tone, the contract, the section's
routing, the page's cited documents and folders, and a sample of facts from their cards), each with the page's text
and sha256, written to <out>/<page path less .md>.owner.md and .professional.md (default <work>/reviews). The
sample: every date, amount and reference number in the key_facts of the cards of the documents the page cites (in
`sources:` or backticks, by their path or a copy's), as (current path, kind, value), deduplicated and sorted;
all of them when there are --sample or fewer, otherwise --sample of them at indices (s + j * n // k) % n for j in
0..k-1, sorted, where n is the number of facts, k is --sample and s is the page path's sha256 as an integer modulo n.
The same inputs render the same bytes. A reviewer model equal to the author model is refused.

Acceptance record, `_Audit/wiki-acceptance.json` (JSON, indent 1, UTF-8):
    {"version": 1, "records": [<record>, ...]}
records in the order they were made, one per `accept`, each:
    {"page": "<page path>", "lens": "owner" | "professional", "verdict": "accepted" | "changes" | "refused",
     "sha256": "<the page's sha256 when recorded>", "professional": "<its professional then, common.page_voice>",
     "contract_sha256": "<sha256 of its section's compiled contract then, see below>",
     "author_model": "<as given>", "reviewer_model": "<as given>",
     "date": "<--date, or now as YYYY-MM-DDTHH:MM:SS+ZZZZ>",
     "findings": [{"where": "...", "finding": "...", "response": "..."}],
     "facts_checked": [...] (only when the reply carries it, as given), "reason": "..." (refused only)}
The contract sha256 is of the section's compiled contract {reader, questions, fields}, as `wiki-maintenance`
defines a page contract (JSON null for a section without one, a fixed section), serialised with keys sorted, no
spaces, UTF-8; the page's own professional is recorded and compared apart, so a professional added to the section
for another page changes no page's standing. `accept` reads the
reviewer's reply (the JSON the review template asks for, a `response` added to each finding), refuses (exit 2,
nothing recorded) a page that is not in the wiki or has no single professional, an unknown lens or verdict, a
finding without its where, finding and response, `changes` without a finding, an author or reviewer in the reply
other than the flags, a `page_sha256` other than the page's now, and a --date that is not YYYY-MM-DD, alone or
followed by T and a valid time. A reviewer equal to the author (names case-folded, spaces collapsed) is refused and
recorded as `refused`, with its reason. Under an exclusive lock on <record>.lock, left beside it, `accept` reads
the record, adds its one record and writes the whole file anew (a temporary file renamed over it), so runs made at
once each keep theirs; no record is changed or removed. Check reports each page's state from its latest record per
lens: `refused` when either lens's latest is a refusal; `accepted` when both lenses' latest accepted the page's
current sha256 under its current professional and contract sha256; otherwise `not recorded`, saying why (a page
edited since, or whose contract or professional changed since, falls back to it; without a compiled Schema an
acceptance cannot be verified). The wiki's state is `refused` if any page is, `accepted` if every page is, otherwise
`not recorded`. `acceptance_not_verified` lists the pages whose acceptance cannot be verified, recorded or not,
because their professional and contract cannot be read (no compiled Schema, a stale twin, no single professional).
`acceptance_records_for_no_page` lists the pages that records name and the wiki no longer holds (a page moved or
removed; its records stay as made). Acceptance never counts as a problem and never makes the check
pass.

Bundles: each live manifest entry that is not withheld (`common.withheld`: under the migrations folder, or excluded by
the rulebook) routes by the compiled Schema routing, its longest matching prefix (a note row, with no section, routes nothing). A routed entry with a card joins its
section's `bundle_<NN>.jsonl`; entries with no route, or routed but with no card, are listed as `unrouted` and
`uncarded`. A withheld document is in no bundle, list or record (a `copies` list names none of its copies either) and is
counted in the summary (`held_for_another_project`, `excluded`). `bundles.json` records the manifest's sha256, a digest of
the routing and section kinds the bundles were built by, `common.withheld_digest` (the exclusions, the migrations folder,
the documents then withheld and every path, copies included, they hold), the shield they were built under (`shield`:
whether terms were given and the sha256 of the sorted forms, never the forms) and the non-default arguments they were
built with. Every tool's start purges bundles built under another withheld set; a consumer (`brief`, and `bundles
--reuse`) also refuses bundles whose recorded digests differ from the current withheld set, checked first (the files are
removed), then the shield (the same: bundles built under other terms, or none, may hold a term this run would withhold,
and an older bundles.json records none), then the manifest's and the routing's: bundles go stale after any migration,
re-audit, routing change or change to the migrations folder, `exclude` or terms file, and are rebuilt by the command
the refusal names. A rebuild removes bundles.json first, so one that fails part way leaves none to trust.

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
left in the wiki: edit the Schema, then compile). A swap or a chain is refused: references/tools.md gives the
runs that make one.

Drift: a departed path is one a departed entry held that no live entry holds; a migrating path is one staged under
the migrations folder or the path it was staged from, when nothing live holds it. The Log's pages are history and
are not read. Fences open and close as `chart_blocks` reads them; line numbers count from the page's first line.

Malformed input (a manifest, card, extract record or bundles.json of the wrong shape, a file where a folder must
be) is refused by name, exit 2.

Deadlines: renders `01 Deadlines/01 Deadlines.md` as a derived roll-up of the wiki pages' frontmatter, in exactly the
form `readiness.py` reads, with that tool's own reading of the pages and its own grammar (`readiness.read_sources`,
`parse_entry`'s layout, the intro, banner and heading lines), so the page it renders is one the readiness check of the
Deadlines page accepts. A dry run prints the page and writes nothing; `--write` writes it, to `--out` when given,
otherwise to the wiki's own page. See `deadlines`.

Charts: `--data` is a CSV file with a header row or a JSON array of objects, rows kept in order, every row with the
same columns: bar `label` (or `period`), `value`, `unit`, `source`; line `period`, `value`, `unit`, `source`; pie
`label`, `value`, `unit`, `source`; gantt `label`, `start`, `end`, `source`, optional `section`; timeline `date`,
`label`, `source`. `source` is a file or folder under the root, outside its reserved names; values are plain
decimals written exactly as given; one unit per chart, on the y-axis or in a pie's title; dates YYYY-MM-DD; a
series has three points or more. A breach is refused, naming the row. The output is the Mermaid block, a blank line
and its data table, which `check` requires beside every xychart-beta, pie, gantt and timeline block (chart
pairing). Rules in full: references/tools.md.
"""
import argparse
import bisect
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
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cards  # noqa: E402
import common  # noqa: E402
import isolation  # noqa: E402

BULK_TYPES = re.compile(r"(?i)reading|course material|lecture|book|textbook|journal|article|paper|photo|slides|"
                        r"presentation|notes|handout|guide|dictionary|homework|coursework|screenshot|casebook|"
                        r"brochure|report")
LINK = re.compile(r"\]\(([^)\s]+?\.md)(#[^)\s]*)?((?:\s+\"[^\"]*\"|\s+'[^']*')?)\)")  # target, #anchor, "title"
EM_DASH = "\u2014"
REQUIRED_FM = ("provenance", "last-updated", "status")
TEMPLATES = os.path.join(HERE, "templates")
LOG_DIR = "91 Log"  # the Log section: its lines are history, so drift (like check) does not read them
BUNDLE_FILE = re.compile(r"bundle_.+\.jsonl")
DOC_DATE = re.compile(r"[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?")
TEXT_CAP = 12000  # characters of a document's text an active section's bundle carries
RATIONALE_TITLE = "# Wiki rationale"
RATIONALE_LABELS = ("Reader and use", "Professional lens", "Shape", "Changed from the previous page",
                    "Left out or flagged")
ACCEPTANCE_VERSION = 1
ACCEPTANCE_KEYS = ("page", "lens", "verdict", "sha256", "professional", "contract_sha256", "author_model",
                   "reviewer_model", "date", "findings")
ACCEPTANCE_STATES = ("accepted", "not recorded", "refused")
LENSES = ("owner", "professional")
VERDICTS = ("accepted", "changes")  # a reviewer's; `accept` records a third, refused
FINDING_KEYS = ("where", "finding", "response")
FACT_KINDS = collections.OrderedDict([("dates", "date"), ("amounts", "amount"),
                                      ("reference_numbers", "reference number")])  # card key_facts, in the sample


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise common.ToolError("cannot read %s (%s)" % (path, e.strerror or e))
    except (ValueError, RecursionError) as e:
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
    for kind in FACT_KINDS:  # each key fact kind, when present, is a list of text (a bare string would be read
        facts = card.get("key_facts", {}).get(kind, [])  # as its characters)
        if not (isinstance(facts, list) and all(isinstance(x, str) for x in facts)):
            raise common.ToolError("malformed card: %s: key_facts.%s must be a list of text; re-card it (cards.py "
                                   "work --redo)" % (path, kind))
    return card


def load_extract(extract_dir, h, card_path):
    path = os.path.join(extract_dir, h + ".json")
    if not os.path.exists(path):
        raise common.ToolError("card %s has no extract record %s; extract the document again" % (card_path, path))
    xr = read_object(path)
    if xr.get("id") != h:  # the rule `extract.py repath` holds a record to: it is this document's, named by its hash
        raise common.ToolError("malformed extract record %s: its id is %r, not %s; extract the document again"
                               % (path, xr.get("id"), h))
    pages = xr.get("pages", [])
    if not isinstance(pages, list):
        raise common.ToolError("malformed extract record %s: pages must be a list; extract the document again" % path)
    for i, p in enumerate(pages, 1):
        if not (isinstance(p, dict) and ("n" not in p or type(p["n"]) is int)
                and (p.get("text") is None or isinstance(p["text"], str))):  # a null n would crash full_text
            raise common.ToolError("malformed extract record %s: page %d must be an object whose n is a whole number "
                                   "and whose text is text or null; extract the document again" % (path, i))
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
    """A page path relative to the wiki folder: `/` separated, ending in .md, no part empty, hidden (a dot first),
    with a space at either end or holding a control character (below U+0020, or U+007F)."""
    return (isinstance(p, str) and p.endswith(".md") and "\\" not in p
            and not any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in p)
            and all(x and x == x.strip() and not x.startswith(".") for x in p.split("/")))


def schema_rel(root, rb, ws):
    """The Schema page relative to the wiki folder, or None."""
    rel = ws["schema_path"] if ws else common.schema_page(root, rb["wiki_dir"])
    return rel[len(rb["wiki_dir"]) + 1:] if rel else None


def working_file(root, path, what):
    """`path`, refused when it is inside the folder: `what` is a working file, kept in the work dir or elsewhere."""
    return common.working_file(root, path, what)


def cards_dirs(a, root):
    """The cards and extract folders, refused by name when either is a file."""
    out = []
    for given, flag, default, kind in ((a.cards, "--cards", "cards", "card"),
                                       (a.extract, "--extract", "extract", "extract")):
        path = os.path.realpath(given) if given else os.path.join(root, "_Audit", default)
        if os.path.exists(path) and not os.path.isdir(path):
            raise common.ToolError("%s %s is a file, not a folder of %s records" % (flag, path, kind))
        out.append(path)
    return tuple(out)


class Shielded:
    """The shield of one command (`isolation.shield`), counting what it replaces."""

    def __init__(self, evidence):
        self.evidence, self.count = evidence, 0

    def text(self, value):
        out, n = isolation.shield(value, self.evidence)
        self.count += n
        return out

    def value(self, value):
        out, n = isolation.shield_value(value, self.evidence)
        self.count += n
        return out

    def report(self, what):
        if self.count:
            print("shielded %d occurrence(s) of an isolation term in %s" % (self.count, what), file=sys.stderr)


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
    document counts a party once). A document held for another project (`migrating`) or excluded (`excluded`) is
    counted and never profiled, and no copy of one is named. Every name it writes (a folder, a party, a category) is
    shielded (`isolation.shield`)."""
    if a.depth < 1 or a.parties < 1:
        raise common.ToolError("--depth and --parties count from 1")
    shield = Shielded(isolation.evidence_of(a))
    root, settings_dir, work = common.resolve(a)
    if a.out:
        common.working_file(root, a.out, "profile reports")
    rb = common.load_rulebook(root, settings_dir)
    _mp, man = load_manifest(root, a.manifest)
    cards_dir, _x = cards_dirs(a, root)
    names = people_names(rb)
    rows = collections.defaultdict(lambda: {"documents": 0, "copies": 0, "copies_of": collections.Counter(),
                                            "carded": 0, "categories": collections.Counter(), "dates": [],
                                            "parties": collections.Counter()})
    total = {"documents": 0, "carded": 0, "copies": 0, "migrating": 0, "excluded": 0, "departed": 0}
    categories = collections.Counter()

    def folders(path):
        parts = path.split("/")[:-1]
        return ["/".join(parts[:i]) for i in range(1, min(len(parts), a.depth) + 1)] if parts else ["(root)"]

    for h, e in sorted(man.items(), key=lambda x: x[1]["current_path"]):
        p = e["current_path"]
        if "departed" in e.get("flags", []):
            total["departed"] += 1
            continue
        why = common.withheld(rb, p)
        if why:  # held for another project or excluded: counted, and never profiled or named
            total["migrating" if why == "migrations" else "excluded"] += 1
            continue
        card = load_card(cards_dir, h)
        total["documents"] += 1
        parties = set()
        category = shield.text(card.get("category") or "Other") if card else None
        if card:
            total["carded"] += 1
            categories[category] += 1
            for n in [card.get("party") or ""] + list(card.get("parties") or []):
                n = n.strip()
                if n and n.lower() != "unknown":
                    parties.add(shield.text(names.get(n.lower(), n)))
        shown = shield.text(p)
        for f in folders(shown):
            r = rows[f]
            r["documents"] += 1
            if card:
                r["carded"] += 1
                r["categories"][category] += 1
                if DOC_DATE.fullmatch(card.get("doc_date") or ""):
                    r["dates"].append(card["doc_date"])
                r["parties"].update(parties)
        for c in e.get("copies", []):
            if c["path"] == p or common.withheld(rb, c["path"]):
                continue
            total["copies"] += 1
            for f in folders(shield.text(c["path"])):
                rows[f]["copies"] += 1
                rows[f]["copies_of"][folders(shown)[0]] += 1

    def ranked(counter, n=None):
        return [[k, v] for k, v in sorted(counter.items(), key=lambda x: (-x[1], x[0]))][:n]

    out = collections.OrderedDict(folder=shield.text(os.path.basename(root)), depth=a.depth, **total)
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
        common.register_output(root, work, rb, a.out, man)
    sys.stdout.write(text)
    shield.report("the profile")
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
SHIELD_ARGS = ("--terms", "--no-isolation-terms")  # the shield a build was given; a rebuild is asked under the caller's
BUNDLES_META = {"manifest_sha256": str, "routing_sha256": str, "withheld_sha256": str, "shield": dict, "arguments": dict,
                "sections": dict, "compact": dict, "files": dict, "unrouted": list, "uncarded": list,
                "held_for_another_project": int, "excluded": int}


def shield_record(evidence):
    """What bundles.json records of the shield its bundles were built under: whether terms were given, and the sha256
    of the sorted forms (`isolation.shield_digest`), never the forms."""
    return {"terms": bool(evidence), "sha256": isolation.shield_digest(evidence)}


def build_arguments(a):
    """The non-default arguments `bundles` was given (absolute paths, and --text-cap when not the default), so a
    rebuild command can repeat them."""
    out = collections.OrderedDict((flag, os.path.realpath(getattr(a, key))) for key, flag in BUILD_ARGS
                                  if getattr(a, key, None))
    if getattr(a, "text_cap", TEXT_CAP) != TEXT_CAP:
        out["--text-cap"] = str(a.text_cap)
    if getattr(a, "terms", None):
        out["--terms"] = os.path.realpath(a.terms)
    elif getattr(a, "no_isolation_terms", False):
        out["--no-isolation-terms"] = ""
    return out


def bundles_command(verb, root, bdir, arguments):
    args = ["--root", root, "--out", bdir] + [x for k, v in arguments.items() for x in ([k, v] if v else [k])]
    return "%s them: wiki.py bundles %s" % (verb, " ".join(shlex.quote(x) for x in args))


REUSE_ARGS = ("--cards", "--extract", "--text-cap")  # what `bundles --reuse` must have been built with, as asked


def fresh_bundles(root, bdir, mpath, ws, arguments, rb, man, evidence, reuse=False):
    """bundles.json in `bdir`, refused unless it is one `bundles` wrote, built from the current manifest, routing, withheld
    documents and shield (`evidence`, the caller's), with every section's file there. The rebuild command repeats the
    arguments the bundles were built with (`arguments`, the caller's, when none are recorded), under the caller's shield.
    With `reuse`, the caller's --cards, --extract and --text-cap (defaults included) must be those the bundles were
    built with."""
    caller = arguments
    meta_path = os.path.join(bdir, "bundles.json")
    if not os.path.lexists(meta_path):
        raise common.ToolError("no bundles in %s; %s" % (bdir, bundles_command("build", root, bdir, arguments)))
    meta = read_object(meta_path)
    recorded = meta.get("arguments")
    texts = isinstance(recorded, dict) and all(isinstance(x, str) for kv in recorded.items() for x in kv)
    if texts:
        arguments = collections.OrderedDict([(k, v) for k, v in recorded.items() if k not in SHIELD_ARGS]
                                            + [(k, v) for k, v in caller.items() if k in SHIELD_ARGS])
    rebuild = bundles_command("rebuild", root, bdir, arguments)
    if meta.get("withheld_sha256") != common.withheld_digest(rb, man):
        remove_bundle_files(bdir)  # first, so stale files are always removed: they hold what must not be in a bundle
        raise common.ToolError("stale bundles: %s was built when other documents were held for another project or "
                               "excluded (the migrations folder or `exclude` in rulebook.json changed, or a re-audit "
                               "moved what is withheld), so the bundles were removed; %s" % (meta_path, rebuild))
    if meta.get("shield") != shield_record(evidence):
        remove_bundle_files(bdir)  # as above: built under other terms, or none, they may hold a term this run withholds
        raise common.ToolError("stale bundles: %s was built under another isolation shield (a different terms file, "
                               "--terms against --no-isolation-terms, or bundles made before the shield was "
                               "recorded), so the bundles were removed; %s" % (meta_path, rebuild))
    bad = sorted(k for k, kind in BUNDLES_META.items() if not isinstance(meta.get(k), kind)
                 or (k in ("sections", "compact") and not all(type(v) is int for v in meta[k].values()))
                 or (kind is int and type(meta.get(k)) is not int)
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
    if reuse:
        defaults = {"--cards": os.path.join(root, "_Audit", "cards"),
                    "--extract": os.path.join(root, "_Audit", "extract"), "--text-cap": str(TEXT_CAP)}
        for flag in REUSE_ARGS:
            built, asked = arguments.get(flag, defaults[flag]), caller.get(flag, defaults[flag])
            if built != asked:
                raise common.ToolError("bundles in %s were built with %s %s, not %s; %s"
                                       % (bdir, flag, built, asked, bundles_command("rebuild", root, bdir, caller)))
    return meta


def bundle_summary(meta):
    return {"routed": sum(meta["sections"].values()), "sections": meta["sections"], "compact": meta["compact"],
            "unrouted": meta["unrouted"], "uncarded": meta["uncarded"],
            "held_for_another_project": meta["held_for_another_project"], "excluded": meta["excluded"]}


@os_errors
def bundles(a):
    shield = Shielded(isolation.evidence_of(a))
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
        meta = fresh_bundles(root, out, mpath, ws, arguments, rb, man, shield.evidence, reuse=True)
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
    counts, compact, held = collections.Counter(), collections.Counter(), collections.Counter()
    for h, e in sorted(man.items(), key=lambda x: x[1]["current_path"]):
        p = e["current_path"]
        if "departed" in e.get("flags", []):
            continue
        why = common.withheld(rb, p)
        if why:  # held for another project or excluded: counted, and in no bundle, list or record
            held[why] += 1
            continue
        sec = route(ws, p)
        if sec is None:
            unrouted.append(shield.text(p))
            continue
        c = load_card(cards_dir, h)
        if c is None:
            uncarded.append(shield.text(p))
            continue
        xr = load_extract(extract_dir, h, os.path.join(cards_dir, h + ".json"))
        rec = {"id": h[:12], "path": p, "copies": [x["path"] for x in e.get("copies", [])
                                                   if x["path"] != p and not common.withheld(rb, x["path"])],
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
        bund[sec].append({k: v if k == "id" else shield.value(v) for k, v in rec.items()})
        counts[sec] += 1
    writer.makedirs(out)
    files = {sec: "bundle_%s.jsonl" % sec for sec in sorted(bund)}
    for sec, name in files.items():
        writer.text(os.path.join(out, name), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in bund[sec]))
    for name in sorted(os.listdir(out)):
        if BUNDLE_FILE.fullmatch(name) and name not in files.values():
            os.remove(writer.check(os.path.join(out, name)))
    meta = collections.OrderedDict(
        manifest_sha256=digest, routing_sha256=routing_digest(ws), withheld_sha256=common.withheld_digest(rb, man),
        shield=shield_record(shield.evidence), arguments=arguments, text_cap=a.text_cap,
        sections=dict(sorted(counts.items())), compact=dict(sorted(compact.items())), files=files,
        unrouted=unrouted, uncarded=uncarded, held_for_another_project=held["migrations"], excluded=held["excluded"])
    writer.text(meta_path, json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    common.register_rendered(work, out, meta["withheld_sha256"], "bundles")
    print(json.dumps(bundle_summary(meta), ensure_ascii=False))
    shield.report("the bundles")
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


def withheld_note(found):
    """The line a brief gives a page that already cites a withheld document (`found`, from `withheld_citer`): where, and
    what to do, with no path in it."""
    why = sorted({common.WITHHELD_WHY[w] for _line, w in found})
    return ("- Withheld citation: line%s %s cite%s a document the tools may not read (%s). Take each citation off the "
            "page, and every fact drawn from that document with it; do not open the document, and do not name its "
            "path." % ("" if len(found) == 1 else "s", ", ".join(str(line) for line, _w in found),
                       "s" if len(found) == 1 else "", " or ".join(why)))


def page_entry(p, state, sec, voice, contract, ws, bundle, rb, found=()):
    lines = ["### %s" % p, "",
             "- Status: %s" % ("exists (revise it)" if state == "exists" else "planned (write it)")]
    lines += [withheld_note(found)] if found else []
    lines += [
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
    routes, hidden = section_routes(rb, ws, sec["number"])
    lines.append("- Files routed to the section:%s" % ("" if routes or hidden else " none"))
    lines += route_lines(routes, hidden)
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
    """The JSON a drafting agent returns: what `wiki-onboarding` step 4a names (the pages it wrote, each page's
    rationale block, its Index entry, its open questions and its check result), one entry per page."""
    shape = {"pages": [{"path": p, "text": "<the page exactly as written to the wiki folder, frontmatter first>",
                        "rationale": "<its rationale block: the heading and five lines given below, joined by \\n>",
                        "index_entry": "<the page's line in the Index: what it holds, in a few words>"}
                       for p in pages],
             "open_questions": ["<for the owner or the coordinating agent: a gap, sources that disagree, a dated "
                                "rule left unchecked, a page the evidence shows is missing>"],
             "check_result": {"problems": 0,
                              "links_to_planned_pages": ["<a link to a page the map plans but nobody has written "
                                                         "yet>"]}}
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


def md_cell(value):
    return " ".join(str(value).split()).replace("|", "\\|")


def md_table(headers, rows):
    return "\n".join(["| %s |" % " | ".join(headers), "| %s |" % " | ".join("---" for _ in headers)]
                      + ["| %s |" % " | ".join(md_cell(c) for c in row) for row in rows])


def schema_tables(rb, ws):
    """The Schema's four tables as markdown, from the compiled twin, with every routing row whose prefix is withheld left
    out (a line says how many): what a brief embeds in place of the Schema page, which lists those rows."""
    shown = [r for r in ws["routing"] if not common.path_withheld(rb, {}, r["prefix"])]
    hidden = len(ws["routing"]) - len(shown)
    parts = ["### Layout", "", md_table(["Section", "Pages", "Professional lens", "Kind"], [
        ["%s %s" % (x["number"], x["name"]), x["pages"], "; ".join(x["professionals"]),
         x["kind"] + (", derived" if x["derived"] else "")] for x in ws["sections"]]),
        "", "### Routing", "", md_table(["Files under", "Section and page"], [["`%s`" % r["prefix"], r["target"]]
                                                                              for r in shown])]
    if hidden:
        parts += ["", "%d routing row%s into a withheld folder %s not shown." % (hidden, "" if hidden == 1 else "s",
                                                                                 "is" if hidden == 1 else "are")]
    parts += ["", "### Page contracts", "", md_table(
        ["Section (professional)", "Reader", "Questions, most important first", "Fields every page carries"],
        [["%s %s (%s)" % (c["number"], c["name"], "; ".join(c["professionals"])), c["reader"] or "",
          " ".join("%d. %s" % (i, q) for i, q in enumerate(c["questions"], 1)), ", ".join(c["fields"])]
         for c in ws["contracts"]])]
    if ws["pages"]:
        parts += ["", "### Page professionals", "", md_table(
            ["Page", "Professional", "Deliverable", "Tone"],
            [[p, v["professional"], v["deliverable"], v["tone"]] for p, v in sorted(ws["pages"].items())])]
    return "\n".join(parts)


def remove_bundle_files(bdir):
    """Remove `bundles.json` and the section files of the bundles in `bdir`: the bundles were built before a change to
    what is withheld, and hold documents that must not be in one."""
    for name in sorted(os.listdir(bdir)):
        if name == "bundles.json" or BUNDLE_FILE.fullmatch(name):
            os.remove(os.path.join(bdir, name))


@os_errors
def brief(a):
    shield = Shielded(isolation.evidence_of(a))
    root, settings_dir, work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    ws = common.load_wiki_schema(root, settings_dir)
    mpath, man = load_manifest(root, a.manifest)
    bdir = os.path.realpath(a.bundles) if a.bundles else os.path.join(work, "bundles")
    meta = fresh_bundles(root, bdir, mpath, ws, build_arguments(a), rb, man, shield.evidence)
    wiki = os.path.join(root, rb["wiki_dir"])
    pages = sorted(set(a.page))
    for p in pages:
        if not is_page_path(p):
            raise common.ToolError("--page %r is not a page path relative to the wiki folder, like "
                                   "'<NN Section>/<Page>.md'" % p)
    voices = {p: common.page_voice(ws, p) for p in pages}
    contracts = {c["number"]: c for c in ws["contracts"]}
    pmap = page_map(ws, wiki, pages)
    entries, skeletons, cites = [], [], withheld_citer(root, rb, man, ws)
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
        found = cites(p, read_text(os.path.join(wiki, *p.split("/")))) if pmap[p] == "exists" else []
        entries.append(page_entry(p, pmap[p], sec, voices[p], contract, ws, bundle, rb, found))
        skeletons.append(rationale_skeleton(p, pmap[p], voices[p], contract))
    checker = ["python3", os.path.join(HERE, "wiki.py"), "check", "--root", root, "--work", work]
    checker += ["--settings-dir", settings_dir] if a.settings_dir else []
    checker += ["--manifest", os.path.realpath(mpath)] if a.manifest else []
    for p in pages:
        checker += ["--page", p]
    text = render_template(
        "page-brief.md", folder_name=os.path.basename(root), owner_context=owner_context(root, rb),
        pages="\n\n".join(entries),
        page_map="\n".join("- `%s` (%s%s)" % (p, s, ", in this brief" if p in pages else "") for p, s in pmap.items()),
        bundles_dir=bdir, wiki_dir=wiki, schema_tables=schema_tables(rb, ws),
        checker=" ".join(shlex.quote(x) for x in checker), return_shape=return_shape(pages),
        rationale="\n\n".join(skeletons))
    text = shield.text(text)
    if a.out:
        target = working_file(root, a.out, "briefs")
        common.Writer(root).text(target, text)
        common.register_rendered(work, target, common.withheld_digest(rb, man))
    sys.stdout.write(text)
    shield.report("the brief")
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


def live_top_folders(man):
    """Every top-level folder holding a live manifest entry or a copy of one."""
    tops = set()
    for e in man.values():
        if "departed" not in e.get("flags", []):
            for p in [e["current_path"]] + [c["path"] for c in e.get("copies", [])]:
                if "/" in p:
                    tops.add(p.split("/", 1)[0])
    return tops


def schema_for_check(root, settings_dir):
    """(the compiled Schema or None, why it is None): `check` reports without it rather than refusing."""
    try:
        ws = common.load_wiki_schema(root, common.settings_dir_for(root, settings_dir), required=False)
    except common.ToolError as e:
        return None, "not verified: %s" % e
    return ws, None if ws else "not verified: no compiled Schema (wiki-schema.json); run settings.py compile"


def rationale_block_problem(lines):
    """None when `lines`, those under a block's heading, are the five labelled lines in order; else what is wrong."""
    if len(lines) != len(RATIONALE_LABELS):
        return "%d line%s under the heading, not %d" % (len(lines), "" if len(lines) == 1 else "s",
                                                        len(RATIONALE_LABELS))
    for n, (line, label) in enumerate(zip(lines, RATIONALE_LABELS), 1):
        if not line.startswith("- %s: " % label):  # lines come right-stripped, so text follows the label
            return "line %d is not \"- %s: <text>\"" % (n, label)
    return None


PLACEHOLDER = re.compile(r"<[^<>/]+>")  # `<year>`: a complete one, an opening `<` and a closing `>` round a name


def literal_prefix(span):
    """For a backticked path: "" when it holds no routing pattern, else the folders before its first segment holding
    `*` or a complete `<...>` placeholder, as a path ending in `/`, or None when that first segment is itself the
    pattern. `[`, `]` and `?` are not patterns, and neither is a lone `<` or `>`: file and folder names carry them, so
    they are read as the characters they are."""
    parts = span.split("/")
    for i, part in enumerate(parts):
        if "*" in part or PLACEHOLDER.search(part):
            return "/".join(parts[:i]) + "/" if i else None
    return ""


def star_matches(root, span):
    """True when something under `root` matches `span`, read with `*` as the only wildcard (`[`, `]` and `?` are the
    characters they are)."""
    pattern = "/".join(glob.escape(part).replace("[*]", "*") for part in span.split("/"))
    return bool(glob.glob(os.path.join(glob.escape(root), pattern)))


def span_state(root, span):
    """`found`, `dead` or `unchecked` for a backticked path under a live top-level folder. A path that exists as
    written is found. One with no pattern, or whose folders before a `*` or `<...>` pattern are missing, is dead
    (a name is never read as a pattern it is not: `Invoice [3].pdf` is not `Invoice 3.pdf`). A `*` pattern with its
    folders present is found when something matches it, and unchecked when nothing does or when it holds a complete
    `<...>` placeholder, since what a pattern stands in for cannot be told; one patterned from its first segment is
    unchecked."""
    if os.path.exists(os.path.join(root, span)):
        return "found"
    literal = literal_prefix(span)
    if literal is None:
        return "unchecked"
    if not literal or not os.path.exists(os.path.join(root, literal)):
        return "dead"
    return "found" if not PLACEHOLDER.search(span) and star_matches(root, span) else "unchecked"


def parse_rationale(text):
    """The rationale file as ([(heading, lines under it)], [[place, what is wrong]] for the file itself): blocks in
    file order, each heading's text after `### ` stripped, its lines up to the next heading with trailing blank
    lines dropped. The file opens with the title line; before the first block only blank lines may follow it."""
    lines = text.split("\n")
    problems, first = [], 1
    if lines[0].rstrip() != RATIONALE_TITLE:
        problems.append([RATIONALE_TITLE, "the file does not open with it"])
        first = 0 if lines[0].startswith("### ") else 1  # a wrong first line stands in for the title
    blocks, current = [], None
    for n, line in enumerate(lines[first:], first + 1):
        if line.startswith("### "):
            current = (line[4:].strip(), [])
            blocks.append(current)
        elif current is not None:
            current[1].append(line.rstrip())
        elif line.strip():
            problems.append(["(before the first block)", "line %d is outside any block" % n])
    for _h, body in blocks:
        while body and not body[-1]:
            body.pop()
    return blocks, problems


def lens_professional(line):
    """The professional a block's Professional lens line names: its text up to the first `;`."""
    return line[len("- Professional lens: "):].split(";", 1)[0].strip()


def norm_name(name):
    """A model's or a professional's name as compared: case folded, whitespace collapsed."""
    return " ".join(name.split()).casefold()


def rationale_findings(text, pages, voices):
    """The rationale checks for `pages` (the pages that exist): see the module docstring. `voices` is {page: its
    professional} for the pages that have one, or None without a compiled Schema. Each heading is reported once,
    by the first that holds of: repeated, malformed, for no page, its lens not naming the page's professional."""
    blocks, malformed = parse_rationale(text)
    heads = collections.Counter(h for h, _l in blocks)
    named, orphans = [], []
    for h, body in blocks:
        if heads[h] > 1:
            continue  # reported once, as repeated
        why = "the heading is not a page path" if not is_page_path(h) else rationale_block_problem(body)
        if why:
            malformed.append([h, why])
        elif h not in pages:
            orphans.append(h)
        elif voices is not None and h in voices and norm_name(lens_professional(body[1])) != norm_name(voices[h]):
            named.append([h, lens_professional(body[1]), voices[h]])
    return collections.OrderedDict(
        blocks=len(blocks), pages_without_block=sorted(p for p in pages if p not in heads),
        blocks_without_page=sorted(orphans), blocks_repeated=sorted(h for h, k in heads.items() if k > 1),
        blocks_malformed=malformed, professional_not_named=named if voices is not None else None)


# ------------------------------------------------------------------------------------ acceptance

def contract_sha256(ws, page):
    """sha256 of the compiled contract of the page's section ({reader, questions, fields}: the page contract as
    `wiki-maintenance` defines it, not the section's list of professionals), or of JSON null for a section without
    one (a fixed section), serialised canonically: keys sorted, no spaces, UTF-8."""
    sec = section_of(ws, page)
    c = next((x for x in ws["contracts"] if x["number"] == sec["number"]), None)
    obj = {k: c[k] for k in ("reader", "questions", "fields")} if c else None
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def page_standing(ws, why, page):
    """(the page's professional, its contract's sha256), or (None, why they cannot be read): `why` the Schema was
    not read (missing or stale), or why `common.page_voice` refuses the page, as pages_without_single_professional
    gives it."""
    if not ws:
        return None, why
    try:
        return common.page_voice(ws, page)["professional"], contract_sha256(ws, page)
    except common.ToolError as e:
        return None, str(e)


def load_acceptance(path):
    """The acceptance record's records, in order; a record that is not in the format the module docstring gives
    fails loud."""
    data = read_json(path)
    if not (isinstance(data, dict) and set(data) == {"version", "records"} and data["version"] == ACCEPTANCE_VERSION
            and isinstance(data["records"], list)):
        raise common.ToolError("%s: not an acceptance record ({\"version\": %d, \"records\": [...]})"
                               % (path, ACCEPTANCE_VERSION))
    for i, r in enumerate(data["records"]):
        ok = (isinstance(r, dict) and set(ACCEPTANCE_KEYS) <= set(r) <= set(ACCEPTANCE_KEYS) | {"facts_checked",
                                                                                                "reason"}
              and is_page_path(r["page"]) and r["lens"] in LENSES and r["verdict"] in VERDICTS + ("refused",)
              and common.is_sha256(r["sha256"]) and common.is_sha256(r["contract_sha256"])
              and all(isinstance(r[k], str) and r[k].strip()
                      for k in ("professional", "author_model", "reviewer_model", "date"))
              and isinstance(r["findings"], list) and (r["verdict"] != "refused" or isinstance(r.get("reason"), str)))
        if not ok:
            raise common.ToolError("%s: records[%d] is not a record in the acceptance format (tools/README.md)"
                                   % (path, i))
        if r["verdict"] != "refused" and norm_name(r["author_model"]) == norm_name(r["reviewer_model"]):
            raise common.ToolError("%s: records[%d] was reviewed by its author model %r; only a refusal may be "
                                   "recorded by the model that wrote the page" % (path, i, r["reviewer_model"]))
    return data["records"]


def acceptance_states(records, now):
    """[[page, state, why]] for each page in `now` ({page: (its sha256, its professional or None, its contract's
    sha256 or why the two cannot be read)}), from its latest record per lens."""
    latest = {(r["page"], r["lens"]): r for r in records}
    out = []
    for p in sorted(now):
        sha, prof, contract = now[p]
        got = {lens: latest.get((p, lens)) for lens in LENSES}
        refused = [lens for lens in LENSES if got[lens] and got[lens]["verdict"] == "refused"]
        if refused:
            out.append([p, "refused", "; ".join("%s lens: %s" % (lens, got[lens]["reason"]) for lens in refused)])
            continue

        def standing(r):
            return prof is not None and norm_name(r["professional"]) == norm_name(prof) \
                and r["contract_sha256"] == contract
        if all(got[lens] and got[lens]["verdict"] == "accepted" and got[lens]["sha256"] == sha and standing(got[lens])
               for lens in LENSES):
            out.append([p, "accepted", "both lenses accepted this version"])
            continue
        if not any(got.values()):
            out.append([p, "not recorded", "no verdict recorded"])
            continue
        why = []
        for lens in LENSES:
            r = got[lens]
            if r is None:
                why.append("%s lens: no verdict" % lens)
            elif r["verdict"] == "changes":
                why.append("%s lens: changes asked%s" % (lens, "" if r["sha256"] == sha
                                                         else " of an earlier version; review it again"))
            elif r["sha256"] != sha:
                why.append("%s lens: accepted an earlier version; the page changed since" % lens)
            elif prof is None:
                why.append("%s lens: accepted, but not verified: %s" % (lens, contract))
            elif not standing(r):
                why.append("%s lens: accepted under an earlier contract or professional" % lens)
        out.append([p, "not recorded", "; ".join(why)])
    return out


# ------------------------------------------------------------------------------------ check

COLLAPSE = re.compile(r"/(?:\.?/)+|(?<=/)[^/\s]+/\.\./")  # `//` and `/./`, and `name/../`: each is the path without it
LINK_TARGET = re.compile(r"\]\([ \t]*(<[^>\n]*>|[^)\s]*)|^[ \t]{0,3}\[[^\]\n]+\]:[ \t]*(<[^>\n]*>|\S+)", re.M)


def path_forms(span, base="", root_name=""):
    """The folded folder-relative spellings of a path a page names (a citation, a link's target), so that every spelling of
    one path is the same: percent-escapes decoded (as often as they nest), `\\` read as `/`, a `file://` prefix dropped,
    then `posixpath.normpath` (`./`, `//` and `name/../` gone, the trailing `/` dropped), leading `../` dropped, then
    `common.fold`. With `base`, the folder a link on the page is relative to, the path resolved from it is a form too. With
    `root_name`, the folder's own name, so is the path after any segment of that name: climbing out of the folder and back in
    by its name (`../../../Alex Personal/06 Work/x`), a path through the cloud drive (`iCloud Drive/Alex Personal/x`) or
    one that spells the folder's location another way (`/tmp/..` for `/private/tmp/..`, `file://`) all name `06 Work/x`."""
    s = span.strip()
    s = s[1:-1].strip() if s.startswith("<") and s.endswith(">") else s
    for _ in range(4):
        decoded = urllib.parse.unquote(s)
        if decoded == s:
            break
        s = decoded
    s = re.sub(r"^file://[^/]*", "", s.replace("\\", "/"))
    cands = [s] + ([posixpath.join(base, s)] if base and not s.startswith("/") else [])
    segs = s.split("/")
    cands += ["/".join(segs[j + 1:]) for j, seg in enumerate(segs[:-1]) if root_name and common.fold(seg) == common.fold(root_name)]
    forms = set()
    for cand in cands:
        n = posixpath.normpath(cand).lstrip("/") if cand else ""
        while n.startswith("../"):
            n = n[3:]
        n = common.fold(n.rstrip("/"))
        if n and n not in (".", ".."):
            forms.add(n)
    return forms


def collapse(text):
    """(`text` with `//`, `/./` and `name/../` taken out, offsets): `offsets[i]` is where `text[i]` stood in the original."""
    at = list(range(len(text)))
    for _ in range(8):
        out, idx, last, hit = [], [], 0, False
        for m in COLLAPSE.finditer(text):
            hit = True
            end = m.start() + (1 if m.group(0).startswith("/") else 0)
            out.append(text[last:end])
            idx += at[last:end]
            last = m.end()
        if not hit:
            break
        out.append(text[last:])
        idx += at[last:]
        text, at = "".join(out), idx
    return text, at


def link_targets(text):
    """[(line, target)]: every link target in `text`, of any kind of file or none: `](target)` (a title after it is not
    part of it), a reference definition `[name]: target`."""
    return [(text.count("\n", 0, m.start()) + 1, m.group(1) or m.group(2)) for m in LINK_TARGET.finditer(text)]


def withheld_citer(root, rb, man, ws):
    """`cites(rel, text, skip=())` -> [(line, why)]: where the wiki page `rel` (its text) names a withheld document or
    folder, the one rule `check` reports as `cites_withheld` and `review-prompts` refuses a page on. Two things count,
    and a path is judged by `common.fold`, so a case or Unicode variant of it is the same path:

    - a citation, a `sources:` entry or a backticked span (`citations`): a path a withheld entry holds (a copy at an
      included path too), or a path under the migrating folder or an excluded path that the manifest holds as a file
      or a folder, so a placeholder such as `_Migrations/<Project>/` that names none is not one;
    - a withheld path anywhere in the page's text, in plain text and in fenced blocks, and in the text with its
      percent-escapes decoded (a link's target): every path a withheld entry holds, and every withheld folder the
      manifest holds (an excluded path, a project folder in the migrating folder), as the path with its separators.

    `skip` is a set of (line, span) to leave out (a chart's source cell, judged as a chart source). The Schema page and
    the Log may name a withheld folder, as a routing row or a history line does, but not a withheld document: only a
    folder is let stand there. `why` is `migrations` or `excluded`; no path is returned."""
    live = {h: e for h, e in man.items() if "departed" not in e.get("flags", [])}
    withheld_at = common.withheld_paths(rb, man)  # {fold(path): why}, every path a withheld entry holds
    live_paths = {common.fold(p) for e in live.values()
                  for p in [e["current_path"]] + [c["path"] for c in e.get("copies", [])]}
    live_folders = {"/".join(q.split("/")[:i]) for q in live_paths for i in range(1, q.count("/") + 1)}
    folders = {}  # {fold(path) + "/": why}: the withheld folders the manifest holds, and the folders `exclude` names
    for q in live_paths:
        parts = q.split("/")
        for i in range(1, len(parts)):
            here = "/".join(parts[:i])
            why = common.withheld(rb, here)
            if why:
                folders.setdefault(here + "/", why)
    for e in rb["exclude"]:
        k = common.fold(e).rstrip("/")
        if k not in withheld_at:
            folders.setdefault(k + "/", "excluded")
    exempt = lambda rel: rel.startswith(LOG_DIR + "/") or rel == schema_rel(root, rb, ws)

    def named(forms):
        """(why, "document" | "folder") for a path as `path_forms` spells it, or None."""
        for bare in sorted(forms):
            if bare in withheld_at:
                return withheld_at[bare], "document"
            why = common.withheld(rb, bare)
            if why and (bare in live_paths or bare in live_folders):
                return why, "folder"
        return None

    root_name = os.path.basename(root)
    inc_paths = {common.fold(p) for e in live.values() if not common.withheld(rb, e["current_path"])
                 for p in [e["current_path"]] + [c["path"] for c in e.get("copies", [])] if not common.withheld(rb, p)}
    inc_folders = {"/".join(q.split("/")[:i]) for q in inc_paths for i in range(1, q.count("/") + 1)}
    live_ends = set(inc_paths) | inc_folders | {f + "/" for f in inc_folders}  # what a live path may read as
    for q in list(live_ends):  # and as it reads after a segment named as the folder is, as `path_forms` reads a link
        segs = q.split("/")
        live_ends.update("/".join(segs[j + 1:]) for j, seg in enumerate(segs[:-1]) if seg == common.fold(root_name))
    ending_with = {}

    def literal(span, base=""):
        """True when `span`, read as a folder-relative path and no other way, is a live, included document's or folder's
        path: it is that document, whatever its folder's name makes of it as a path after that name."""
        return any(f in inc_paths or f in inc_folders for f in path_forms(span, base))

    def explained(text, e, token):
        """True when the withheld `token`, which ends at `text[e]` and follows a `/`, is the end of a live, included
        document's path (or of a live, included folder's, with its `/`) that the text before and up to `e` ends with:
        `Photos (2024)/Scan 1.pdf` is that document, not the staged root stray `Scan 1.pdf`. A direct suffix test, no
        reading of where the longer path starts: a bracket, an apostrophe, a comma or a glued word before it cannot
        matter. The live path must start a path segment, though: the character before it is no letter, digit, `-`, `_`
        or `.`, so `MyPhotos/Scan 1.pdf` is not `Photos/Scan 1.pdf`. Anything else is a citation."""
        if token not in ending_with:
            ending_with[token] = [q for q in live_ends if q.endswith("/" + token)]
        return any(text[:e].endswith(q) and (e == len(q) or not (text[e - len(q) - 1].isalnum()
                                                                or text[e - len(q) - 1] in "_-."))
                   for q in ending_with[token])

    def scan(lines):
        """[(line number, why, kind)] for every token of `withheld_at` and `folders` in `lines`, read three ways: each
        line followed by a space (wrapped at a space); the lines' indentation, quote marks and line breaks taken out
        (wrapped after any character, a `/` included); and joined by a space except at a `/` or before a `.`. `//` and
        `/./` are taken out of each; a blank line and a heading line (`#`) are joined to the next with a space in the
        second and third readings, since no path is wrapped across a paragraph. An occurrence (its line and column) that a live document explains in any of the
        three readings is not a citation, so a path hard-wrapped at a space or at a `/` is judged as it was written."""
        seen = {}
        for variant in ("spaced", "bare", "mixed"):
            tidy = [x if variant == "spaced" else re.sub(r"^[\s>]+", "", x).rstrip() for x in lines]
            keys = [common.fold(x) for x in tidy]
            lead = [len(x) - len(y) for x, y in zip(lines, tidy)]  # what the reading took off the front of each line
            joined, starts = "", []
            for n, k in enumerate(keys):
                starts.append(len(joined))
                follows = keys[n + 1] if n + 1 < len(keys) else ""
                joined += k + ("" if (variant == "bare" or variant == "mixed" and (k.endswith("/") or follows[:1] in "/."))
                               and k and follows and not k.startswith("#") else " ")
            text, at = collapse(joined)
            for tokens, kind in ((withheld_at, "document"), (folders, "folder")):
                for token, why in tokens.items():
                    i = text.find(token)
                    while i >= 0:
                        after = i + len(token)
                        if (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")) and (
                                kind == "folder" or after >= len(text) or not (text[after].isalnum()
                                                                              or text[after] == "_")):
                            line = bisect.bisect_right(starts, at[i])
                            column = at[i] - starts[line - 1] + lead[line - 1]
                            key = (line, column, why, kind, token)
                            seen[key] = seen.get(key, False) or (i > 0 and text[i - 1] == "/"
                                                                 and explained(text, after, token))
                        i = text.find(token, i + 1)
        return [(line, why, kind) for (line, _c, why, kind, _t), ok in seen.items() if not ok]

    def cites(rel, text, skip=()):
        found = set()
        for line, span in citations(text):
            hit = None if (line, span) in skip or literal(span) else named(path_forms(span, "", root_name))
            if hit:
                found.add((line, hit[0], hit[1]))
        base = posixpath.join(rb["wiki_dir"], posixpath.dirname(rel))
        for line, target in link_targets(text):
            hit = named(path_forms(target, base, root_name)) if target and not literal(target, base) else None
            if hit and line not in {l for l, _s in skip}:
                found.add((line, hit[0], hit[1]))
        lines = text.split("\n")
        for body in (lines, urllib.parse.unquote(text).split("\n")):
            found.update(f for f in scan(body) if f[0] not in {l for l, _s in skip})
        if exempt(rel):
            found = {f for f in found if f[2] == "document"}
        return sorted({(line, why) for line, why, _kind in found})
    return cites


def check_result(root, rb, man, settings_dir=None, rationale_path=None, acceptance_path=None, only=None):
    """The wiki checks as a dict; every item a count (zero included) or a named not-verified state. The compiled
    Schema is read from `settings_dir` (default <root>/.familyai), the rationale file and acceptance record from
    <root>/_Audit/ unless given; a path given that does not exist is refused.

    `only` (a list of pages) is a drafting agent's check: findings on those pages alone, a link to a page the map
    plans but nobody has written yet counted as pending rather than dead, and coverage, rationale and acceptance left
    to the coordinator's whole-wiki check (each a named not-checked state), since sibling sections are still being
    drafted."""
    for given, what in ((rationale_path, "rationale file"), (acceptance_path, "acceptance record")):
        if given and not os.path.isfile(given):
            raise common.ToolError("the %s given does not exist: %s" % (what, given))
    root = os.path.realpath(root)
    wiki = os.path.join(root, rb["wiki_dir"])
    ws, ws_why = schema_for_check(root, settings_dir)
    live = {h: e for h, e in man.items() if "departed" not in e.get("flags", [])}
    tops = live_top_folders(man)
    reserved = chart_reserved(rb, man)
    pages = wiki_pages(wiki)
    in_map = set(pages)  # a link to a page the map only plans resolves to nothing: dead until the page is written
    if only is not None:
        for p in only:
            if p not in in_map:
                raise common.ToolError("--page %r is not a page in %s" % (p, wiki))
        planned = {p for p, state in page_map(ws, wiki, only).items() if state == "planned"} if ws else set()
    pending = []
    not_covering = {p for p in pages if p.startswith(LOG_DIR + "/") or p == schema_rel(root, rb, ws)}
    res = collections.OrderedDict(wiki=rb["wiki_dir"], pages=len(pages))
    fm_bad, dead_src, dead_links, outside, em, unchecked, dls, sup = [], [], [], [], [], 0, [], 0
    charts, unpaired, unrenderable, bad_chart_src = 0, [], [], []
    cited, shas = set(), {}
    cites_withheld, cites = [], withheld_citer(root, rb, man, ws)
    for rel in pages:
        if only is not None and rel not in only:
            continue  # a sibling's page is never opened: it may be mid-write
        path = os.path.join(wiki, *rel.split("/"))
        try:
            shas[rel] = common.sha256_file(path)
            t = read_text(path)
        except (OSError, UnicodeDecodeError):  # a page that cannot be read is not one that conforms
            shas.setdefault(rel, "")
            fm_bad.append(rel)
            continue
        m = re.match(r"---\n(.*?)\n---\n", t, re.S)
        fm = parse_fm(m.group(1)) if m else {}
        fm_lines = t[:m.end()].count("\n") if m else 0
        if not all(k in fm for k in REQUIRED_FM) or not isinstance(fm.get("sources", []), list):
            fm_bad.append(rel)  # a required key missing, or `sources:` written as one value rather than a list
        if fm.get("status") == "superseded":
            sup += 1
        for s in fm.get("sources") if isinstance(fm.get("sources"), list) else []:
            # spelt exactly as its folder lists it: a case variant opens the file on macOS and would pass for it
            if isinstance(s, str) and common.named_exactly(root, s.rstrip("/")) is None:
                dead_src.append([rel, s])
        for d in fm.get("deadlines") or []:
            if isinstance(d, dict):
                dls.append([d.get("date"), rel])
        body = t[m.end():] if m else t
        in_tables = set()
        for c in chart_parts(t):
            if c["type"] in CHART_TABLES:
                charts += 1
                if not c["paired"]:
                    unpaired.append([rel, c["line"]])
            if c["kind"] is None:
                unrenderable.append([rel, c["line"], c["type"]])
            for line, src in c["sources"]:
                in_tables.add((line, src))
                try:
                    chart_source(root, src, "", reserved)
                except common.ToolError:
                    bad_chart_src.append([rel, line, src])
        spans = citations(t)
        # the page must not depend on a document the tools may not read; the path stays out of the report
        cites_withheld += [[rel, line, why] for line, why in cites(rel, t, in_tables)]
        if rel not in not_covering:
            cited.update(span for _line, span in spans)
        if not rel.startswith(LOG_DIR + "/"):
            for line, span in spans:
                if line <= fm_lines or "/" not in span or (line, span) in in_tables:
                    continue  # a `sources:` entry (checked above), no path, or a chart's source (checked with it)
                state = span_state(root, span) if span.split("/", 1)[0] in tops else "unchecked"
                if state == "dead":
                    dead_src.append([rel, span])
                elif state == "unchecked":
                    unchecked += 1
        for lk, _anchor, _title in LINK.findall(body):
            if not local_link(lk):
                continue  # as `move` decides: a scheme (http:, mailto:, obsidian:) or a path rooted at /
            target = link_target(rel, lk)
            if not os.path.exists(os.path.normpath(os.path.join(wiki, target))):
                (pending if only is not None and target in planned else dead_links).append([rel, lk])
            elif target not in in_map:
                outside.append([rel, lk])
        em += [[rel, fm_lines + i] for i, line in enumerate(body.splitlines(), 1) if EM_DASH in strip_code(line)]

    def covered(e):
        """Named by its path or a copy's, or its own parent folder named, with or without the trailing `/`."""
        pth = e["current_path"]
        folder = pth.rsplit("/", 1)[0] if "/" in pth else None
        return (any(x in cited for x in [pth] + [c["path"] for c in e.get("copies", [])])
                or folder is not None and (folder + "/" in cited or folder in cited))

    withheld = collections.Counter(common.withheld(rb, e["current_path"]) for e in live.values())
    in_scope = sorted((e for e in live.values() if not common.withheld(rb, e["current_path"])),
                      key=lambda e: e["current_path"])
    scope = [e["current_path"] for e in in_scope]
    uncovered = [e["current_path"] for e in in_scope if not covered(e)] if only is None else []
    voices, no_voice = None, ws_why
    if ws:
        voices, no_voice = {}, []
        for p in pages if only is None else sorted(only):
            try:
                voices[p] = common.page_voice(ws, p)["professional"]
            except common.ToolError as e:
                no_voice.append([p, str(e)])
    res.update(frontmatter_conforming="%d/%d" % (len(pages) - len(fm_bad), len(pages)), frontmatter_bad=fm_bad,
               superseded_pages=sup, dead_source_paths=dead_src, backticked_paths_unchecked=unchecked,
               dead_page_links=dead_links, links_outside_page_map=outside, em_dash_lines=len(em),
               em_dash_where=em[:10], chart_blocks=charts, charts_without_data_table=unpaired,
               charts_not_renderable=unrenderable, chart_sources_bad=bad_chart_src,
               deadlines=sorted(map(list, {tuple(x) for x in dls})),
               cites_withheld=cites_withheld,
               documents_in_scope=len(scope), documents_held_for_another_project=withheld["migrations"],
               documents_excluded=withheld["excluded"], documents_not_covered=len(uncovered),
               not_covered_sample=uncovered[:20],
               pages_without_single_professional=no_voice)
    problems = (len(fm_bad) + len(dead_src) + len(dead_links) + len(outside) + len(em) + len(uncovered)
                + len(unpaired) + len(unrenderable) + len(bad_chart_src) + len(cites_withheld)
                + (len(no_voice) if ws else 0))
    if only is not None:
        whole = "not checked: scoped to %d page(s); the coordinator's whole-wiki check judges it" % len(only)
        res.update(frontmatter_conforming="%d/%d" % (len(only) - len(fm_bad), len(only)),
                   scoped_to=sorted(only), links_to_planned_pages=pending, documents_not_covered=whole,
                   not_covered_sample=[], rationale=whole, acceptance=whole)
        res["problems"] = problems
        return res
    rat = rationale_path or os.path.join(root, "_Audit", "wiki-rationale.md")
    if os.path.exists(rat):
        found = rationale_findings(read_text(rat), pages, voices)
        if found["professional_not_named"] is None:
            found["professional_not_named"] = ws_why
        problems += sum(len(v) for k, v in found.items() if k != "blocks" and isinstance(v, list))
        res["rationale"] = found
    else:
        res["rationale"] = "not recorded"
    acc = acceptance_path or os.path.join(root, "_Audit", "wiki-acceptance.json")
    records = load_acceptance(acc) if os.path.exists(acc) else []
    unread = ws_why[len("not verified: "):] if ws_why else None
    standing = {p: page_standing(ws, unread, p) for p in pages}
    states = acceptance_states(records, {p: (shas[p],) + standing[p] for p in pages})
    counts = collections.Counter(s for _p, s, _w in states)
    res["acceptance"] = ("refused" if counts["refused"] else "accepted" if states and counts["accepted"] == len(states)
                         else "not recorded")
    res["acceptance_counts"] = collections.OrderedDict((s, counts[s]) for s in ACCEPTANCE_STATES)
    res["acceptance_pages"] = states
    res["acceptance_not_verified"] = sorted(p for p in pages if standing[p][0] is None)  # a structured reading
    res["acceptance_records_for_no_page"] = sorted({r["page"] for r in records} - set(pages))  # moved or removed
    res["problems"] = problems  # acceptance is its own state, never a problem and never a pass
    return res


@os_errors
def check(a):
    root, settings_dir, work = common.resolve(a)
    if a.out:
        common.working_file(root, a.out, "check reports")
    rb = common.load_rulebook(root, settings_dir)
    _mp, man = load_manifest(root, a.manifest)
    res = check_result(root, rb, man, settings_dir=settings_dir,
                       rationale_path=os.path.realpath(a.rationale) if a.rationale else None,
                       acceptance_path=os.path.realpath(a.acceptance) if a.acceptance else None,
                       only=sorted(set(a.page)) if a.page else None)
    out = json.dumps(res, ensure_ascii=False, indent=1)
    if a.out:
        common.Writer(root if a.read_only_root else None).text(a.out, out)
        common.register_output(root, work, rb, a.out, man)
    print(out)
    return 1 if res["problems"] else 0


# ------------------------------------------------------------------------------------ rationale

def drafter_returns(src):
    """[(file, return)] from a drafter's return file (one return object or a list of them) or a directory of such
    .json files, in name order."""
    if os.path.isdir(src):
        files = sorted(os.path.join(src, n) for n in os.listdir(src) if n.endswith(".json"))
        if not files:
            raise common.ToolError("no .json returns in %s" % src)
    elif os.path.isfile(src):
        files = [src]
    else:
        raise common.ToolError("--returns missing: %s" % src)
    out = []
    for f in files:
        data = read_json(f)
        for ret in data if isinstance(data, list) else [data]:
            if not (isinstance(ret, dict) and isinstance(ret.get("pages"), list)):
                raise common.ToolError("%s: a drafter's return is an object with a \"pages\" list (wiki.py brief "
                                       "gives its shape)" % f)
            out.append((f, ret))
    return out


@os_errors
def rationale(a):
    root, settings_dir, _work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    wiki = os.path.join(root, rb["wiki_dir"])
    blocks = {}
    for f, ret in drafter_returns(os.path.realpath(a.returns)):
        for i, entry in enumerate(ret["pages"]):
            path = entry.get("path") if isinstance(entry, dict) else None
            where = "%s: pages[%d]%s" % (f, i, " (%s)" % path if isinstance(path, str) else "")
            if not is_page_path(path):
                raise common.ToolError("%s: path is not a page path relative to the wiki folder" % where)
            text = entry.get("rationale")
            if not isinstance(text, str):
                raise common.ToolError("%s: no rationale block" % where)
            lines = [x.rstrip() for x in text.strip("\n").replace("\r\n", "\n").split("\n")]
            if lines[0] != "### " + path:
                raise common.ToolError("%s: the block's heading is %r, not '### %s'" % (where, lines[0], path))
            why = rationale_block_problem(lines[1:])
            if why:
                raise common.ToolError("%s: malformed rationale block: %s" % (where, why))
            if path in blocks:
                raise common.ToolError("%s: page returned twice (also in %s)" % (where, blocks[path][0]))
            blocks[path] = (f, lines)
    if not blocks:
        raise common.ToolError("no pages in the returns")
    text = RATIONALE_TITLE + "\n\n" + "\n".join("\n".join(blocks[p][1]) + "\n" for p in sorted(blocks))
    out = a.out or os.path.join(root, "_Audit", "wiki-rationale.md")
    common.Writer(root if a.read_only_root else None).text(out, text)
    pages = wiki_pages(wiki)
    res = collections.OrderedDict(blocks=len(blocks), pages_without_block=[p for p in pages if p not in blocks],
                                  blocks_without_page=sorted(set(blocks) - set(pages)))
    print(json.dumps(res, ensure_ascii=False))
    return 1 if res["pages_without_block"] or res["blocks_without_page"] else 0


# ------------------------------------------------------------------------------------ review prompts

def fenced(text):
    """`text` in a Markdown fence longer than any backtick run inside it."""
    run = max([len(x) for x in re.findall(r"`+", text)] + [2]) + 1
    return "%smarkdown\n%s%s%s" % ("`" * run, text, "" if text.endswith("\n") else "\n", "`" * run)


def fact_sample(page, facts, k):
    """At most `k` of `facts` (a sorted list), by the rule in the module docstring."""
    n = len(facts)
    if n <= k:
        return list(facts)
    s = int(hashlib.sha256(page.encode("utf-8")).hexdigest(), 16) % n
    return [facts[i] for i in sorted((s + j * n // k) % n for j in range(k))]


def held_paths(rb, man):
    """({path: entry id} for every path a live entry that is not withheld holds, its current path and its copies', bar
    a copy under a withheld path; {path: why} for every path a live withheld entry holds). A withheld document
    (`common.withheld`) is never indexed as one a prompt may open, load a card for or count."""
    held = {}
    for h, e in sorted(man.items()):
        if "departed" in e.get("flags", []) or common.withheld(rb, e["current_path"]):
            continue
        held[e["current_path"]] = h
        for c in e.get("copies", []):
            if not common.withheld(rb, c["path"]):
                held.setdefault(c["path"], h)
    return held, common.withheld_paths(rb, man)


def page_sources(text, man, held, cards_dir, rb, withheld_at):
    """(the lines listing what the page cites, its facts, how many cited paths are withheld): documents with their
    card's title, folders with the paths held directly in them, anything else holding `/` as not in the manifest;
    facts as in fact_sample, each under its document's current path, so a document cited by two of its paths gives its
    facts once. A cited path that is withheld (`common.path_withheld`) is named as withheld and nothing else: no
    card, title, fact or canonical path is read, and no folder count includes it."""
    by_folder = collections.Counter(p.rsplit("/", 1)[0] for p in held if "/" in p)
    lines, facts, hidden = [], set(), 0
    for path in sorted({span for _l, span in citations(text)}):
        why = common.path_withheld(rb, withheld_at, path)
        if why:
            hidden += 1
            lines.append("- `%s`: withheld (%s); not to be opened, and the page is not checked against it"
                         % (path, common.WITHHELD_WHY[why]))
        elif path in held:
            h = held[path]
            card = load_card(cards_dir, h)
            current = man[h]["current_path"]
            lines.append("- `%s`: %s%s" % (path, card.get("title") or "untitled card" if card else "no card",
                                           ", a copy of `%s`" % current if current != path else ""))
            kf = card.get("key_facts") if card and isinstance(card.get("key_facts"), dict) else {}
            for kind in FACT_KINDS:
                values = kf.get(kind) if isinstance(kf.get(kind), list) else []
                facts.update((current, kind, v.strip()) for v in values if isinstance(v, str) and v.strip())
        elif by_folder[path.rstrip("/")]:
            n = by_folder[path.rstrip("/")]
            lines.append("- `%s`: a folder, %d file%s directly in it" % (path, n, "" if n == 1 else "s"))
        elif "/" in path:
            lines.append("- `%s`: not a document or folder in the manifest" % path)
    return lines, sorted(facts), hidden


def section_routes(rb, ws, number):
    """(the routing rows into section `number` a brief or a prompt may show, how many it hides): a row whose prefix is
    a withheld path, such as the migrations folder or an excluded folder, would name it to a model."""
    shown, hidden = [], 0
    for r in ws["routing"]:
        if r["section"] != number:
            continue
        if common.path_withheld(rb, {}, r["prefix"]):
            hidden += 1
        else:
            shown.append(r)
    return shown, hidden


def route_lines(routes, hidden):
    lines = ["  - `%s`: %s" % (r["prefix"], r["target"]) for r in routes]
    return lines + (["  - %d route%s to a withheld folder, not shown" % (hidden, "" if hidden == 1 else "s")]
                    if hidden else [])


def contract_lines(voice, contract):
    lines = ["- Professional: %s (%s)" % (voice["professional"], "the page's row in the Page professionals table"
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
    return "\n".join(lines)


@os_errors
def review_prompts(a):
    shield = Shielded(isolation.evidence_of(a))
    root, settings_dir, work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    ws = common.load_wiki_schema(root, settings_dir)
    _mp, man = load_manifest(root, a.manifest)
    author, reviewer = a.author_model.strip(), a.reviewer_model.strip()
    if not author or not reviewer:
        raise common.ToolError("--author-model and --reviewer-model name the models that wrote and review the pages")
    if norm_name(author) == norm_name(reviewer):
        raise common.ToolError("refused: the reviewer model %r is the author model %r; acceptance is by a model that "
                               "did not write the page" % (reviewer, author))
    if a.sample < 1:
        raise common.ToolError("--sample counts from 1")
    wiki = os.path.join(root, rb["wiki_dir"])
    have = set(wiki_pages(wiki))
    pages = sorted(set(a.page))
    for p in pages:
        if p not in have:
            raise common.ToolError("--page %r is not a page in %s" % (p, wiki))
    out = working_file(root, a.out, "review prompts") if a.out else os.path.join(work, "reviews")
    cards_dir = os.path.realpath(a.cards) if a.cards else os.path.join(root, "_Audit", "cards")
    if os.path.exists(cards_dir) and not os.path.isdir(cards_dir):
        raise common.ToolError("--cards %s is a file, not a folder of card records" % cards_dir)
    contracts = {c["number"]: c for c in ws["contracts"]}
    held, withheld_at = held_paths(rb, man)
    cites = withheld_citer(root, rb, man, ws)
    writer, written, withheld_cited, refused = common.Writer(root), [], {}, []
    for p in pages:
        voice, sec = common.page_voice(ws, p), section_of(ws, p)
        contract = contracts.get(sec["number"])
        if contract is None and sec["kind"] != "fixed":
            raise common.ToolError("section %s %s has no page contract in the Schema, so %s cannot be reviewed "
                                   "against one" % (sec["number"], sec["name"], p))
        path = os.path.join(wiki, *p.split("/"))
        text = read_text(path)
        found = cites(p, text)
        if found:  # the page depends on a document the tools may not read: no prompt, and none left from before
            refused += [[p, line, why] for line, why in found]
            for lens in ("owner", "professional"):
                stale = os.path.join(out, *p[:-3].split("/")) + ".%s.md" % lens
                if os.path.lexists(stale):
                    os.remove(writer.check(stale))
            continue
        reader = contract["reader"] if contract and contract["reader"] else "the owner"
        questions = ("\n".join("%d. %s" % (i, q) for i, q in enumerate(contract["questions"], 1)) if contract else
                     "None in the Schema: the section is fixed, so its shape is the method's (`wiki-onboarding` and "
                     "`wiki-maintenance`). Judge whether %s can use the page for what that shape is for." % reader)
        sources, facts, hidden = page_sources(text, man, held, cards_dir, rb, withheld_at)
        if hidden:
            withheld_cited[p] = hidden
        sample = fact_sample(p, facts, a.sample)
        routes, hidden_routes = section_routes(rb, ws, sec["number"])
        scope = "\n".join(["- Section: %s %s, %s%s" % (sec["number"], sec["name"], sec["kind"],
                                                       ", derived" if sec["derived"] else ""),
                           "- Files routed to the section:%s" % ("" if routes or hidden_routes else " none")]
                          + route_lines(routes, hidden_routes))
        fields = dict(page=p, author_model=author, reviewer_model=reviewer, wiki_dir=rb["wiki_dir"], page_text=fenced(text))
        fields = dict({k: shield.text(v) for k, v in fields.items()}, page_sha256=common.sha256_file(path))
        owner = render_template("review-owner.md", reader=shield.text(reader), questions=shield.text(questions),
                                **fields)
        prof = render_template(
            "review-professional.md", professional=shield.text(voice["professional"]),
            contract=shield.text(contract_lines(voice, contract)), scope=shield.text(scope), root=shield.text(root),
            sources=shield.text("\n".join(sources) or "- none: the page cites no document or folder"),
            facts=shield.text("\n".join("%d. `%s`, %s: %s" % (i, f[0], FACT_KINDS[f[1]], f[2])
                                        for i, f in enumerate(sample, 1))
                             or "None: no card of a document the page cites holds a date, amount or reference number."),
            sampled="%d of %d" % (len(sample), len(facts)), **fields)
        base = os.path.join(out, *p[:-3].split("/"))
        for lens, body in (("owner", owner), ("professional", prof)):
            writer.text(base + ".%s.md" % lens, body)
            common.register_rendered(work, base + ".%s.md" % lens, common.withheld_digest(rb, man))
        written.append([p, base + ".owner.md", base + ".professional.md"])
    print(json.dumps({"prompts": written, "withheld_cited": withheld_cited, "refused": refused}, ensure_ascii=False,
                     indent=1))
    shield.report("the review prompts")
    if refused:
        raise common.ToolError("refused to render %d page(s) that cite a withheld document, no prompt written for "
                               "them: %s; take each citation off the page (`wiki.py check` lists them as "
                               "cites_withheld)" % (len({r[0] for r in refused}),
                                                    "; ".join("%s line %d" % (r[0], r[1]) for r in refused)))
    return 0


# ------------------------------------------------------------------------------------ accept

ISO_TIME = re.compile(r"([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?(Z|[+-]([0-9]{2}):?([0-9]{2}))?")


def valid_date(value):
    """True for YYYY-MM-DD, alone or followed by T and a valid time (HH:MM, or HH:MM:SS), with an optional zone
    (Z, +HHMM or +HH:MM)."""
    day, t, rest = value.partition("T")
    try:
        datetime.date.fromisoformat(day)
    except ValueError:
        return False
    if not ISO_DATE.fullmatch(day):
        return False
    if not t:
        return True
    m = ISO_TIME.fullmatch(rest)
    return bool(m) and int(m.group(1)) < 24 and int(m.group(2)) < 60 and int(m.group(3) or 0) < 60 \
        and (m.group(4) in (None, "Z") or int(m.group(5)) < 24 and int(m.group(6)) < 60)


def append_record(writer, out, rec):
    """Add `rec` to the acceptance record at `out` and return how many it now holds. An exclusive lock on
    `<out>.lock` (created beside it and left there) is held from reading the record to replacing it, so runs made at
    once each add theirs; the file is rewritten whole, through a temporary file renamed over it."""
    import fcntl  # POSIX (macOS, Linux), like the rest of the tools
    lock = writer.check(out + ".lock")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(lock, "a", encoding="utf-8") as held:
        try:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX)
        except OSError as e:  # a file system without locks, such as some network shares
            raise common.ToolError("cannot lock %s: %s; use --out on a local disk" % (lock, e.strerror or e))
        records = load_acceptance(out) if os.path.exists(out) else []
        writer.text(out, json.dumps({"version": ACCEPTANCE_VERSION, "records": records + [rec]}, ensure_ascii=False,
                                    indent=1) + "\n")
    return len(records) + 1


@os_errors
def accept(a):
    root, settings_dir, _work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    ws = common.load_wiki_schema(root, settings_dir)
    wiki = os.path.join(root, rb["wiki_dir"])
    reply = read_json(a.reply)
    if not isinstance(reply, dict):
        raise common.ToolError("%s: a review reply is a JSON object" % a.reply)
    page, lens = reply.get("page"), reply.get("lens")
    if not (is_page_path(page) and page in wiki_pages(wiki)):
        raise common.ToolError("%s: page %r is not a page in %s" % (a.reply, page, wiki))
    if lens not in LENSES:
        raise common.ToolError("%s: lens %r is not one of %s" % (a.reply, lens, ", ".join(LENSES)))
    author, reviewer = a.author_model.strip(), a.reviewer_model.strip()
    if not author or not reviewer:
        raise common.ToolError("--author-model and --reviewer-model name the models that wrote and reviewed the page")
    for key, given in (("author", author), ("reviewer", reviewer)):
        if key in reply and not (isinstance(reply[key], str) and norm_name(reply[key]) == norm_name(given)):
            raise common.ToolError("%s: the reply names %s %r, but --%s-model is %r" % (a.reply, key, reply[key], key,
                                                                                       given))
    if a.date is not None and not valid_date(a.date):
        raise common.ToolError("--date %r is not a date YYYY-MM-DD, alone or with a valid time after a T" % a.date)
    try:
        professional = common.page_voice(ws, page)["professional"]
    except common.ToolError as e:
        raise common.ToolError("%s; a page is accepted in its one professional's lens" % e)
    sha = common.sha256_file(os.path.join(wiki, *page.split("/")))
    out = a.out or os.path.join(root, "_Audit", "wiki-acceptance.json")
    rec = collections.OrderedDict(page=page, lens=lens, verdict=None, sha256=sha, professional=professional,
                                  contract_sha256=contract_sha256(ws, page), author_model=author,
                                  reviewer_model=reviewer, date=a.date or common.now_local(), findings=[])
    writer = common.Writer(root if a.read_only_root else None)
    if norm_name(author) == norm_name(reviewer):
        rec.update(verdict="refused", reason="the reviewer model %r is the author model %r; a page is accepted "
                   "only by a model that did not write it" % (reviewer, author))
        append_record(writer, out, rec)
        raise common.ToolError("refused, and recorded as refused: %s (%s lens of %s)" % (rec["reason"], lens, page))
    if reply.get("page_sha256", sha) != sha:
        raise common.ToolError("%s: the reply reviewed %s at sha256 %s, but the page is now %s; render its review "
                               "prompts again and review it again" % (a.reply, page, reply["page_sha256"], sha))
    verdict, findings = reply.get("verdict"), reply.get("findings", [])
    if verdict not in VERDICTS:
        raise common.ToolError("%s: verdict %r is not one of %s" % (a.reply, verdict, ", ".join(VERDICTS)))
    if not isinstance(findings, list):
        raise common.ToolError("%s: findings is a list" % a.reply)
    for i, f in enumerate(findings):
        if not (isinstance(f, dict) and all(isinstance(f.get(k), str) and f[k].strip() for k in FINDING_KEYS)):
            raise common.ToolError("%s: findings[%d] needs %s, each as text: the reviewer's where and finding, and "
                                   "the response to it" % (a.reply, i, ", ".join(FINDING_KEYS)))
    if verdict == "changes" and not findings:
        raise common.ToolError("%s: a changes verdict names at least one finding" % a.reply)
    rec.update(verdict=verdict, findings=[{k: f[k] for k in FINDING_KEYS} for f in findings])
    if "facts_checked" in reply:
        if not isinstance(reply["facts_checked"], list):
            raise common.ToolError("%s: facts_checked is a list" % a.reply)
        rec["facts_checked"] = reply["facts_checked"]
    count = append_record(writer, out, rec)
    print(json.dumps({"page": page, "lens": lens, "verdict": verdict, "sha256": sha, "records": count},
                     ensure_ascii=False))
    return 0


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
    return [[p, lk] for p in wiki_pages(wiki) for lk, _a, _t in LINK.findall(read_text(os.path.join(wiki, p)))
            if local_link(lk) and not os.path.exists(os.path.join(wiki, *link_target(p, lk).split("/")))]


def check_moves(wiki, moves, pages, schema):
    """Refuse, before anything is written, a map that could not be carried out whole."""
    if os.path.islink(wiki):
        raise common.ToolError("the wiki folder %s is a symbolic link, which could lead outside the folder" % wiki)
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
                                   "separated, ending in .md, no part empty, hidden, with a space at either end or "
                                   "holding a control character)" % new)
        if new in pages or os.path.lexists(os.path.join(wiki, *new.split("/"))):
            raise common.ToolError("destination exists: %s" % new)
        parts = new.split("/")
        for i in range(1, len(parts)):
            above = "/".join(parts[:i])
            path = os.path.join(wiki, *parts[:i])
            if above in targets or os.path.islink(path) or (os.path.lexists(path) and not os.path.isdir(path)):
                kind = ("page this map moves there" if above in targets
                        else "symbolic link, which could lead outside the wiki" if os.path.islink(path) else "file")
                raise common.ToolError("destination %s lies under %s, which is a %s, not a folder" % (new, above, kind))
    twice = sorted(n for n, k in collections.Counter(moves.values()).items() if k > 1)
    if twice:
        raise common.ToolError("two pages moved to one destination: %s" % ", ".join(twice))
    case_clashes(wiki, moves, pages)


def case_clashes(wiki, moves, pages):
    """Refuse a destination that differs only in case from an existing page (other than the page moved there, so a
    case-only rename stays possible where the file system allows it), from another destination, or, in a folder, from
    an existing folder or another destination's folder: a case-insensitive file system would merge what a
    case-sensitive one keeps apart."""
    folders = collections.defaultdict(set)
    for d, ds, _fs in os.walk(wiki):
        ds[:] = sorted(x for x in ds if not x.startswith("."))
        for x in ds:
            rel = os.path.relpath(os.path.join(d, x), wiki).replace(os.sep, "/")
            folders[rel.casefold()].add(rel)
    for new in moves.values():
        parts = new.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            folders["/".join(parts[:i]).casefold()].add("/".join(parts[:i]))
    for old, new in sorted(moves.items()):
        parts = new.split("/")
        for i in range(1, len(parts)):
            rel = "/".join(parts[:i])
            other = sorted(folders[rel.casefold()] - {rel})
            if other:
                raise common.ToolError("destination %s: its folder %s differs only in case from the folder %s"
                                       % (new, rel, other[0]))
        page = next((p for p in pages if p != old and p != new and p.casefold() == new.casefold()), None)
        if page:
            raise common.ToolError("destination %s differs only in case from the page %s" % (new, page))
        dest = next((n for n in sorted(moves.values()) if n != new and n.casefold() == new.casefold()), None)
        if dest:
            raise common.ToolError("destinations %s and %s differ only in case" % (new, dest))


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
            lk, anchor, title = m.group(1), m.group(2) or "", m.group(3)
            if not local_link(lk):
                return m.group(0)
            tgt = link_target(old, lk)
            if new == old and tgt not in moves:
                return m.group(0)
            link = "](" + link_to(new, moves.get(tgt, tgt)) + anchor + title + ")"
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
    """{fold(folder-relative path): "departed" | "migrating"}: see the module docstring. A path is compared as
    `common.fold` compares, and the paths a withheld document held before it moved come from the one source `check` uses
    (`common.prior_paths`, part of `common.withheld_paths`): the path a staged document was staged from and the
    placements in its history are migrating, those of an excluded one departed."""
    live = set()
    for e in man.values():
        if "departed" not in e.get("flags", []):
            live.add(common.fold(e["current_path"]))
            live.update(common.fold(c["path"]) for c in e.get("copies", []))
    out = {}
    for e in man.values():
        held = [e["current_path"]] + [c["path"] for c in e.get("copies", [])]
        if "departed" in e.get("flags", []):
            out.update({common.fold(p): "departed" for p in held if common.fold(p) not in live
                        and common.fold(p) not in out})
        elif "migrating" in e.get("flags", []):
            for raw in held:
                if common.in_migrations(rb, raw):
                    out[common.fold(raw)] = "migrating"
                    origin = common.staged_origin(rb, raw)
                    if origin and common.fold(origin) not in live:
                        out[common.fold(origin)] = "migrating"
    for p, why in common.prior_paths(rb, man).items():
        out.setdefault(p, "migrating" if why == "migrations" else "departed")
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
    root, settings_dir, work = common.resolve(a)
    if a.out:
        common.working_file(root, a.out, "drift reports")
    rb = common.load_rulebook(root, settings_dir)
    _mp, man = load_manifest(root, a.manifest)
    wiki = os.path.join(root, rb["wiki_dir"])
    paths = drift_paths(rb, man)
    at = common.withheld_paths(rb, man)
    kinds = collections.Counter(paths.values())
    pages = [p for p in wiki_pages(wiki) if not p.startswith(LOG_DIR + "/")]
    cited = {"departed": [], "migrating": []}

    def shown(path, kind):
        """The path as the report names it: a path that is withheld, and every path of a migrating document (staged for
        another project, and the path it left), is named as withheld and no more."""
        why = "migrations" if kind == "migrating" else next(
            (w for f in sorted(path_forms(path, "", os.path.basename(root))) for w in [common.path_withheld(rb, at, f)] if w), None)
        return "withheld (%s)" % common.WITHHELD_WHY[why] if why else path
    for p in pages:
        for line, path in citations(read_text(os.path.join(wiki, *p.split("/")))):
            kind = next((paths[f] for f in sorted(path_forms(path, "", os.path.basename(root))) if f in paths), None)
            if kind:
                cited[kind].append([p, line, shown(path, kind)])
    res = collections.OrderedDict(
        wiki=rb["wiki_dir"], pages_read=len(pages), departed_paths=kinds["departed"],
        migrating_paths=kinds["migrating"], citing_departed=len(cited["departed"]),
        citing_migrating=len(cited["migrating"]),
        pages_citing=len({c[0] for cs in cited.values() for c in cs}), departed=cited["departed"],
        migrating=cited["migrating"])
    text = json.dumps(res, ensure_ascii=False, indent=1) + "\n"
    if a.out:
        common.Writer(root if a.read_only_root else None).text(a.out, text)
        common.register_output(root, work, rb, a.out, man)
    sys.stdout.write(text)
    return 1 if res["citing_departed"] or res["citing_migrating"] else 0


# ------------------------------------------------------------------------------------ deadlines

def deadline_lines(r, groups, when):
    """The roll-up's lines for `groups`, {(date, note): [pages]} in order: `- **<when>**: <titles>. <note> (<links>)`,
    or `- **<when>**: <titles> (<links>)` with no note. The titles are the linked pages' own, each once, in the order
    of the links; a link's text is its page's path without `.md` and its target the path from the Deadlines page,
    percent-encoded with `/` and `&` literal, so the line reads back as `parse_entry` reads it."""
    lines = []
    for (key, note), pages in groups:
        titles = ", ".join(dict.fromkeys(posixpath.basename(p)[:-3] for p in pages))
        links = ", ".join("[%s](%s)" % (p[:-3], link_to(r.DEADLINES, p)) for p in pages)
        lines.append("- **%s**: %s%s (%s)" % (when(key), titles, ". " + note if note else "", links))
    return lines


def render_deadlines(r, src, today):
    """The derived Deadlines page for what `readiness.read_sources` read (`src`), built on the day `today`. Dated
    entries go under Upcoming from `today` on and under Past before it, yearly ones under Every year in calendar order,
    a line apart for each (date, note) with every page that gives it named in the one line, ordered by title; what
    could not be read goes under Could not read, and a wiki whose readable pages give no date says so in the banner."""
    groups = collections.defaultdict(list)
    for key, note, page in src.entries:
        groups[(key, note)].append(page)
    ordered = sorted((k, sorted(ps, key=lambda p: (posixpath.basename(p)[:-3], p))) for k, ps in groups.items())
    dated = [g for g in ordered if r.ISO_DAY.fullmatch(g[0][0])]  # the others are MM-DD, a date every year
    upcoming = [g for g in dated if g[0][0] >= today]
    past = [g for g in dated if g[0][0] < today]
    yearly = [g for g in ordered if not r.ISO_DAY.fullmatch(g[0][0])]
    blocks = ["---\nprovenance: derived\nlast-updated: %s\nstatus: current\n---" % today, r.TITLE, r.INTRO_FIXTURE]
    if not src.entries and src.scanned:
        blocks.append((r.BANNER_LINE % ":").replace("{}", str(src.scanned)))
    blocks.append("\n\n".join([r.UPCOMING] + ["\n".join(deadline_lines(r, upcoming, lambda d: d)) or r.NOTHING]))
    for heading, rows, when in ((r.EVERY_YEAR, yearly, r.rendered_month_day), (r.PAST, past, lambda d: d)):
        if rows:
            blocks.append("\n\n".join([heading, "\n".join(deadline_lines(r, rows, when))]))
    if src.unread_lines:
        blocks.append("\n\n".join([r.UNREAD, r.UNREAD_INTRO, "\n".join(src.unread_lines)]))
    return "\n\n".join(blocks) + "\n", (len(upcoming), len(yearly), len(past))


@os_errors
def deadlines(a):
    import readiness as r  # here, not above: readiness imports this module, and holds the roll-up's grammar
    root, settings_dir, _work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    wiki = os.path.join(root, rb["wiki_dir"])
    if not os.path.isdir(wiki):
        raise common.ToolError("no wiki folder: %s" % wiki)
    clock_day = datetime.date.fromtimestamp(common.clock()).isoformat()
    today = clock_day if a.today is None else a.today
    if not r.real_day(today):
        raise common.ToolError("--today %r is not a day written YYYY-MM-DD" % today)
    if today > clock_day:
        raise common.ToolError("--today %s is after today (%s): the page's last-updated is a build stamp, never after "
                               "today, and readiness reports one that is" % (today, clock_day))
    if a.out and not a.write:
        raise common.ToolError("--out names where --write puts the page; without --write nothing is written")
    src = r.read_sources(wiki, r.roll_up_pages(wiki))
    if src.outside:
        raise common.ToolError("cannot render: what the roll-up writes for %d page(s) is not known, since their "
                               "frontmatter uses YAML this tool does not read (%s); rewrite each within the subset "
                               "readiness.py reads (references/tools.md, the frontmatter subset), quoting a value "
                               "that YAML would read as anything but text"
                               % (len(src.outside), "; ".join(x[len("not verified: "):] for x in src.outside)))
    page, (upcoming, yearly, past) = render_deadlines(r, src, today)
    target = a.out or os.path.join(wiki, *r.DEADLINES.split("/"))
    if a.write:
        common.Writer(root if a.read_only_root else None).text(target, page)
    else:
        sys.stdout.write(page)
    print("deadlines: %d upcoming, %d every year, %d past, %d could not read; %s %s"
          % (upcoming, yearly, past, len(src.unread_lines), "wrote" if a.write else "would write (a dry run: --write "
             "writes it)", os.path.relpath(target, root)), file=sys.stderr)
    fix = [("deadline entries not a real YYYY-MM-DD", src.bad_days),
           ("recurring entries not {date, note} with a date as MM-DD or a day and a month name", src.bad)]
    for what, items in fix:
        if items:
            print("fix in the pages' frontmatter, %d %s (%s)" % (len(items), what, r.sample(items)), file=sys.stderr)
    return 1 if src.unread_lines or src.bad_days or src.bad else 0


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
SOURCE_CELL = re.compile(r"\| `([^`]+)` \|\Z")
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


def chart_reserved(rb, man=None):
    """The names under which a chart's source may not lie: the folder's reserved names, every path the owner excluded
    from reading, and with the manifest every path (a copy's too) of a document it withholds (the figures of a chart
    come from its sources, so they must be ones the tools may read). Compared as `common.fold` compares."""
    names = common.reserved_names(rb)
    held = list(common.withheld_paths(rb, man)) if man else []
    return names + [e for e in rb["exclude"] + held if e not in names]


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
        name = next((n for n in reserved if common.fold(rel) == common.fold(n).rstrip("/")
                     or common.fold(rel).startswith(common.fold(n).rstrip("/") + "/")), None)
        if name:
            raise common.ToolError("%s: source %r is under %s, which the folder reserves or the owner excluded from "
                                   "reading; cite a document the tools may read" % (where, value, name))


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


def chart_parts(text):
    """Every Mermaid block in a page, as `chart_blocks` finds them, whatever its type: {"line": the line of its
    opening fence, "type": its Mermaid type (the first word of its first line that is not a %% comment) or None,
    "kind": the `chart` kind it parses as or None, "paired": as `chart_blocks` says, "sources": [(line, source)] for
    each row of its data table when paired}. A block parses as a kind `chart` renders when its type is pie, gantt or
    timeline, or xychart-beta holding exactly one bar or line series."""
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
        mtype = next((x.split()[0] for x in body if x and not x.startswith("%%")), None)
        if mtype == "xychart-beta":
            series = [x.split()[0] for x in body if x.split()[:1] in (["bar"], ["line"])]
            kind = series[0] if len(series) == 1 else None
        else:
            kind = mtype if mtype in ("pie", "gantt", "timeline") else None
        k, rows = i, []
        while k < len(lines) and not lines[k]:
            k += 1
        if (mtype in CHART_TABLES and k + 1 < len(lines) and CHART_TABLES[mtype].fullmatch(lines[k])
                and TABLE_RULE.fullmatch(lines[k + 1])):
            k += 2
            while k < len(lines) and lines[k].startswith("|"):
                rows.append((k + 1, lines[k]))
                k += 1
        paired = bool(rows) and all(SOURCED_ROW.fullmatch(r) for _n, r in rows)
        found.append({"line": start, "type": mtype, "kind": kind, "paired": paired,
                      "sources": [(n, SOURCE_CELL.search(r).group(1)) for n, r in rows] if paired else []})
    return found


def chart_blocks(text):
    """Chart pairing: the Mermaid blocks in a page of a type `chart` renders, as (line of the opening fence in the
    page, type, paired). Only a fence opened at the outermost level with the info string `mermaid` counts: one
    quoted inside another fenced block (backticks or tildes, closed only by a fence of the same character at least
    as long) or in an indented code block is an example, not a chart. Paired: the next non-blank line after the
    block starts the data table `chart` writes for that type, its header row, the rule row, then at least one row,
    every row ending in a backticked source."""
    return [(c["line"], c["type"], c["paired"]) for c in chart_parts(text) if c["type"] in CHART_TABLES]


def chart(a):
    root, settings_dir, work = common.resolve(a)
    if a.out:
        common.working_file(root, a.out, "charts")
    rb = common.load_rulebook(root, settings_dir)
    reserved = chart_reserved(rb)
    rows, places = chart_rows(a.data)
    out = render_chart(root, a.kind, a.title, rows, os.path.basename(a.data), places, reserved)
    if a.out:
        common.Writer(root if a.read_only_root else None).text(a.out, out)
        common.register_output(root, work, rb, a.out)
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
    isolation.add_terms_args(p)
    p.add_argument("--depth", type=int, default=2, help="folder levels profiled (default 2)")
    p.add_argument("--parties", type=int, default=5, help="top parties listed per folder (default 5)")
    p.add_argument("--out")
    p = card_args(common_args(sub.add_parser("bundles")))
    isolation.add_terms_args(p)
    p.add_argument("--out", help="the bundles directory, the tool's own: a rebuild removes bundles.json and "
                   "bundle_*.jsonl there (default <work>/bundles; never inside the folder)")
    p.add_argument("--text-cap", type=int, default=TEXT_CAP)
    p.add_argument("--reuse", action="store_true", help="use the bundles already built, refused when stale")
    p = common_args(sub.add_parser("brief"))
    isolation.add_terms_args(p)
    p.add_argument("--page", action="append", required=True, help="a page to brief, relative to the wiki folder")
    p.add_argument("--bundles", help="the bundles directory (default <work>/bundles)")
    p.add_argument("--out", help="also write the brief here (never inside the folder)")
    p = common_args(sub.add_parser("check"))
    p.add_argument("--rationale", help="the rationale file (default <root>/_Audit/wiki-rationale.md)")
    p.add_argument("--acceptance", help="the acceptance record (default <root>/_Audit/wiki-acceptance.json)")
    p.add_argument("--page", action="append", help="check only this page (repeatable): a drafting agent's check, "
                   "leaving coverage, rationale and acceptance to the whole-wiki check")
    p.add_argument("--out")
    p = common_args(sub.add_parser("rationale"))
    p.add_argument("--returns", required=True, help="a drafter's return (.json) or a directory of them")
    p.add_argument("--out", help="the rationale file (default <root>/_Audit/wiki-rationale.md)")
    p = common_args(sub.add_parser("review-prompts"))
    isolation.add_terms_args(p)
    p.add_argument("--page", action="append", required=True, help="a page to review, relative to the wiki folder")
    p.add_argument("--author-model", required=True, help="the model that wrote the pages")
    p.add_argument("--reviewer-model", required=True, help="the model that reviews them (never the author)")
    p.add_argument("--sample", type=int, default=5, help="facts from the cards to check per page (default 5)")
    p.add_argument("--cards", help="card records (default <root>/_Audit/cards)")
    p.add_argument("--out", help="the prompts directory (default <work>/reviews; never inside the folder)")
    p = common_args(sub.add_parser("accept"))
    p.add_argument("--reply", required=True, help="the reviewer's JSON reply, a response added to each finding")
    p.add_argument("--author-model", required=True, help="the model that wrote the page")
    p.add_argument("--reviewer-model", required=True, help="the model that reviewed it")
    p.add_argument("--date", help="the date recorded (default now)")
    p.add_argument("--out", help="the acceptance record (default <root>/_Audit/wiki-acceptance.json)")
    p = common_args(sub.add_parser("move"))
    p.add_argument("--map", required=True)
    p = common_args(sub.add_parser("drift"))
    p.add_argument("--out")
    p = common_args(sub.add_parser("deadlines"))
    p.add_argument("--today", help="the day the page is built for, YYYY-MM-DD (default the local date); a dated "
                   "entry before it is Past, and it is the page's last-updated, which is never after today")
    p.add_argument("--write", action="store_true", help="write the page (default: print it, change nothing)")
    p.add_argument("--out", help="where --write puts the page (default <root>/<wiki>/01 Deadlines/01 Deadlines.md)")
    p = common_args(sub.add_parser("chart"))
    p.add_argument("--kind", required=True, choices=list(CHART_COLUMNS))
    p.add_argument("--data", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--out")
    a = ap.parse_args()
    return {"profile": profile, "bundles": bundles, "brief": brief, "check": check, "rationale": rationale,
            "review-prompts": review_prompts, "accept": accept, "move": move, "drift": drift, "chart": chart,
            "deadlines": deadlines}[a.cmd](a)


if __name__ == "__main__":
    common.run_main(main)
