#!/usr/bin/env python3
"""The structure assessment (pre-onboarding step 7): measure a folder's structure, list the documents of the folders
the owner approves, and check the records manager's record. No model is called here.

    structure.py measure   --root R T --out <input.md> [--measures <json>] [--depth 3] [--sample 5]
                                                       every structure signal per folder, and the judge's input file
    structure.py documents --root R T --folder F [--folder F ...] --out <md>
                                                       every live document under the folders, with its card's fields,
                                                       for the author of a mapping
    structure.py check     --root R [--record <md>]    the assessment record's shape, against the manifest

`T` is `--terms F` (the operator's isolation terms file) or `--no-isolation-terms`, one of which `measure` and
`documents` require, as the wiki commands do: they write what a model will read, so every string they write (a path, a
folder, a party, a category, a title) is shielded first, each term and marker replaced by `[withheld name]`
(`isolation.shield`), and they say on stderr how many occurrences were replaced, never which. A folder whose name
carries a term reads `[withheld name]` to the model, so a record or a mapping cannot name it: rename the folder or
exclude it, and measure again. Both write working files, outside the folder and registered for a later purge.

Measures. Read from the manifest and the cards, never the documents. A *document* is a live path (a copy is a document
of its own); a *content* is one manifest entry, however many paths hold it. A document the tools may not read, staged
for another project or excluded (`common.withheld`), and a departed one, is left out of every figure and only counted.
A folder with no live document below it is not in the manifest, so it is not here either. Shares over contents
(categories, parties, duplicates) are over distinct contents, so a copy never inflates a subject; a card-less content
has no category and is counted apart (`without_card`). For the root and every folder down to `--depth` (3) each signal
is a value, zero included, with a `stands_out` flag where it crosses the threshold the output names beside it
(`PARAMS`), fixed before any judgement and never tuned to a folder:

    wide                  at least 15 documents directly in the folder (a `flat_dump` when it has no sub-folder)
    mixed                 at least 5 carded contents directly in it, the commonest category holding at most 0.6 of them
    duplicate_subtree     at least 3 contents, every one of which also lives in one other folder that is not nested
                          with it (any depth). Each folder that meets this is counted, both folders of a copied pair
                          among them, and so is a folder above several copied sub-folders as well as each of those;
                          only a folder that merely wraps one (no document of its own, one sub-folder) is not counted
                          again, nor named as the other folder
    generic_names         at least 5 canonical documents below it, at least 0.3 of them named like a scanner or device
                          default (the audit's `generic_name`)
    generic_folder_name   named like New folder, Stuff, Misc, Other or Downloads
    single_child_chain    starts a run of at least 2 folders that each hold one folder and no document
    root_strays           at least 1 document directly at the root (the root row only)
    subject spread        a category, or a party other than the folder's main one (card `party` and `parties`, aliases
                          folded to the rulebook's names), whose contents sit in at least 3 top-level homes

A flag draws attention. It never decides a verdict: whether a folder needs changing is for the records manager to judge
and the owner to approve, and duplicates and strays alone are the light round's, not a structure problem.

The judge's input (`--out`) holds the folder tree with counts, the whole-folder measures, a per-folder table with each
folder's flags, and a card sample (up to `--sample` cards per folder, from the documents directly in it, sorted by path
and evenly spaced, so the same input gives the same bytes). It names no verdict. Below `--depth` the tree and the
sample stop, and a folder that stands out deeper is named in the whole-folder measures. An input over `MAX_BYTES` is
refused: lower `--sample` or `--depth`.

Record, `_Audit/structure-assessment.md`: the line `# Structure assessment`, then `Overall: <no re-org | targeted |
full>`, `Reason: <text>` and `Documents that would move: <N> of <M>` (M the live documents, as `measure` counts them,
and N at most M), then per assessed folder a heading `### <folder path>` and exactly three lines, `- Verdict: <leave as
it is | tidy inside | restructure>`, `- Evidence: <text>` and `- What the owner would relearn: <text>`; blank lines
only between the header lines and blocks. `check` reports every problem, exit 1: a line out of place or malformed, a
heading that is no folder holding live documents, a folder given twice, no block at all, M that is not the live
document count, N over M, `no re-org` with a block other than `leave as it is` or with N above 0, `targeted` or `full`
with every block `leave as it is`, and N of 0 beside a `targeted` or `full` verdict or a block that is `tidy inside` or
`restructure`. A heading is compared in Unicode NFC (`common.as_spelled`), so a folder stored decomposed is found by
its composed name. It prints the counts, never a folder of the manifest.
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common  # noqa: E402
import isolation  # noqa: E402
import wiki  # noqa: E402

PARAMS = collections.OrderedDict([
    ("wide_documents", 15), ("mixed_min_contents", 5), ("mixed_top_share", 0.6), ("duplicate_min_contents", 3),
    ("generic_min_documents", 5), ("generic_share", 0.3), ("chain_folders", 2), ("root_strays", 1),
    ("spread_homes", 3)])
FLAGS = ("wide", "flat_dump", "mixed", "duplicate_subtree", "generic_names", "generic_folder_name",
         "single_child_chain", "root_strays")
GENERIC_FOLDER = re.compile(r"^(new folder|untitled folder|misc|miscellaneous|stuff|other|others|various|random|"
                            r"downloads|downloads from .*|scans|temp|tmp)( \(\d+\)| \d+)?$", re.I)
ROOT = "(root)"
MAX_BYTES = 400000
SPREAD_LISTED = 40  # subjects listed with at least 2 homes; one that stands out is always listed
RECORD_TITLE = "# Structure assessment"
RECORD = os.path.join("_Audit", "structure-assessment.md")
OVERALLS = ("no re-org", "targeted", "full")
VERDICTS = ("leave as it is", "tidy inside", "restructure")
HEADER = ("Overall", "Reason", "Documents that would move")
BLOCK = ("Verdict", "Evidence", "What the owner would relearn")
MOVE_LINE = re.compile(r"Documents that would move: ([0-9]+) of ([0-9]+)")


def share(n, d):
    return round(n / d, 3) if d else 0.0


def top_share(counter):
    """(the commonest category, its share of the contents counted) of a Counter, ties to the name that sorts first."""
    if not counter:
        return None, None
    name, n = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return name, share(n, sum(counter.values()))


def home_of(path):
    parts = path.split("/")
    return parts[0] if len(parts) > 1 else ROOT


def folders_of(path):
    parts = path.split("/")[:-1]
    return ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]


def nested(f, g):
    return f == g or g.startswith(f + "/") or f.startswith(g + "/")


def below(path, folder):
    return not folder or path.startswith(folder + "/")


def load_documents(rb, man, cards_dir):
    """(documents, the cards, what is left out) of the folder. A document is {path, id, current, canonical, generic}:
    its path, its content's id and current path, whether the path is the current one, and whether that name is a device
    default (the audit's `generic_name`, a flag of the current path alone). `cards` is {id: card} for the live contents
    that have one. What is left out (departed, held for another project, excluded) is counted by kind, a path at a time
    as the documents are (a copy under the migrations folder is one held document), never named."""
    docs = []
    for p, h in sorted(common.live_document_paths(rb, man).items()):
        cur = man[h]["current_path"]
        docs.append({"path": p, "id": h, "current": cur, "canonical": p == cur,
                     "generic": p == cur and bool(man[h].get("generic_name"))})
    cards = {}
    for h in sorted({d["id"] for d in docs}):
        card = wiki.load_card(cards_dir, h)
        if card is not None:
            cards[h] = card
    left = collections.Counter()
    for e in man.values():
        paths = [c["path"] for c in e.get("copies", [])] or [e["current_path"]]
        for p in paths:
            if "departed" in e.get("flags", []):
                left["departed"] += 1
            else:
                why = common.withheld(rb, e["current_path"]) or common.withheld(rb, p)
                if why:
                    left["held_for_another_project" if why == "migrations" else "excluded"] += 1
    return docs, cards, left


def folder_rows(docs, cards):
    """(the rows, {folder: the single-child chain starting there}) for the root and every folder holding a live
    document, in tree order, each a measure per signal with its `stands_out` flags (the module docstring)."""
    def category(h):
        return cards[h].get("category") or "Other"

    folders = {""}
    docs_of, ids_of, held_by = collections.defaultdict(list), collections.defaultdict(set), collections.defaultdict(set)
    direct = collections.defaultdict(list)
    for d in docs:
        direct[os.path.dirname(d["path"])].append(d)
        for f in [""] + folders_of(d["path"]):
            folders.add(f)
            docs_of[f].append(d)
            ids_of[f].add(d["id"])
            if f:
                held_by[d["id"]].add(f)
    children = collections.defaultdict(list)
    for f in sorted(folders):
        if f:
            children[os.path.dirname(f)].append(f)

    wraps = {f for f in folders if f and not direct.get(f) and len(children[f]) == 1}  # a link of a single-child chain
    twin = {}  # folder -> (the share of its contents that also live in its best other folder, that folder)
    for f in sorted(folders):
        ids = ids_of[f]
        if f and f not in wraps and len(ids) >= PARAMS["duplicate_min_contents"]:
            overlap = collections.Counter(g for i in ids for g in held_by[i] if g not in wraps and not nested(f, g))
            if overlap:
                best = min((-n / len(ids), len(ids_of[g]), g) for g, n in overlap.items())
                twin[f] = (-best[0], best[2])
    chain = {}
    for f in sorted(folders, key=lambda x: -len(x.split("/")) if x else 1):
        chain[f] = 1 + chain[children[f][0]] if f in wraps else 0

    rows = []
    for f in sorted(folders, key=lambda x: x.split("/") if x else []):
        here = direct.get(f, [])
        d_ids, s_ids = {d["id"] for d in here}, ids_of[f]
        cat_d = collections.Counter(category(i) for i in d_ids if i in cards)
        cat_s = collections.Counter(category(i) for i in s_ids if i in cards)
        top_d, share_d = top_share(cat_d)
        top_s, share_s = top_share(cat_s)
        canonical = [d for d in docs_of[f] if d["canonical"]]
        generic = sum(d["generic"] for d in canonical)
        cover, partner = twin.get(f, (0.0, None))
        row = collections.OrderedDict([
            ("folder", f or ROOT), ("depth", len(f.split("/")) if f else 0),
            ("documents_direct", len(here)), ("contents_direct", len(d_ids)), ("documents", len(docs_of[f])),
            ("contents", len(s_ids)), ("subfolders", len(children[f])),
            ("carded_direct", sum(1 for i in d_ids if i in cards)), ("categories_direct", len(cat_d)),
            ("top_category_direct", top_d), ("top_share_direct", share_d), ("categories", len(cat_s)),
            ("top_category", top_s), ("top_share", share_s), ("without_card", sum(1 for i in s_ids if i not in cards)),
            ("copies_elsewhere", sum(1 for d in docs_of[f] if not below(d["current"], f))),
            ("duplicate_cover", round(cover, 3)), ("duplicate_of", partner), ("generic_documents", generic),
            ("canonical_documents", len(canonical)), ("generic_share", share(generic, len(canonical))),
            ("single_child_chain", chain[f]), ("generic_folder_name", bool(f and GENERIC_FOLDER.match(
                os.path.basename(f)))), ("root_strays", len(here) if not f else 0)])
        stand = set()
        if f and row["documents_direct"] >= PARAMS["wide_documents"]:
            stand |= {"wide"} | ({"flat_dump"} if not children[f] else set())
        if f and row["carded_direct"] >= PARAMS["mixed_min_contents"] and row["top_share_direct"] <= PARAMS[
                "mixed_top_share"]:
            stand.add("mixed")
        if f and row["contents"] >= PARAMS["duplicate_min_contents"] and cover == 1.0:
            stand.add("duplicate_subtree")
        if f and row["canonical_documents"] >= PARAMS["generic_min_documents"] and row["generic_share"] >= PARAMS[
                "generic_share"]:
            stand.add("generic_names")
        if row["generic_folder_name"]:
            stand.add("generic_folder_name")
        if f and chain[f] >= PARAMS["chain_folders"] and not chain[os.path.dirname(f)]:
            stand.add("single_child_chain")
        if not f and row["root_strays"] >= PARAMS["root_strays"]:
            stand.add("root_strays")
        row["stands_out"] = [x for x in FLAGS if x in stand]
        rows.append(row)
    return rows, chain


def subject_spread(docs, cards, names):
    """({category: top-level homes}, {party other than the main one: homes}, the main party): a content sits in the
    home of its current path, and the main party is the one most cards name as their `party`, aliases folded to the
    rulebook's names (ties to the name that sorts first). A party is any name in a card's `party` or `parties` but
    `Unknown`."""
    def person(n):
        return names.get(n.strip().lower(), n.strip())
    main = collections.Counter(person(c["party"]) for c in cards.values() if (c.get("party") or "").strip())
    owner = sorted(main.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if main else None
    cat_homes, party_homes = collections.defaultdict(set), collections.defaultdict(set)
    for h, cur in sorted({(d["id"], d["current"]) for d in docs}):
        if h not in cards:
            continue
        cat_homes[cards[h].get("category") or "Other"].add(home_of(cur))
        for n in [cards[h].get("party") or ""] + list(cards[h].get("parties") or []):
            n = person(n)
            if n and n.lower() != "unknown" and n != owner:
                party_homes[n].add(home_of(cur))
    return cat_homes, party_homes, owner


def spread_listing(homes):
    """([{subject, homes, stands_out, home_folders}], how many subjects stand out, how many more are in 2 homes and not
    listed): every subject at the threshold, then those in 2 homes while `SPREAD_LISTED` allows."""
    th = PARAMS["spread_homes"]
    wide = sorted(((n, len(h)) for n, h in homes.items() if len(h) >= th), key=lambda kv: (-kv[1], kv[0]))
    two = sorted(((n, len(h)) for n, h in homes.items() if 2 <= len(h) < th), key=lambda kv: (-kv[1], kv[0]))
    shown = wide + two[:max(0, SPREAD_LISTED - len(wide))]
    items = [collections.OrderedDict([("subject", n), ("homes", k), ("stands_out", k >= th),
                                      ("home_folders", sorted(homes[n]))]) for n, k in shown]
    return items, len(wide), len(two) - (len(shown) - len(wide))


def compute(rb, docs, cards, left, depth):
    """The measures of the folder, {version, params, summary, signals, spread, folders}: the module docstring.
    `folders` is a list in tree order for the root and each folder down to `depth`, never a mapping keyed by path;
    `signals` has each signal whole-folder, at any depth, with where it stands out. Computed on the real paths:
    shielding is the caller's."""
    rows, chain = folder_rows(docs, cards)
    cat_homes, party_homes, owner = subject_spread(docs, cards, wiki.people_names(rb))
    cats, n_cat, _ = spread_listing(cat_homes)
    parties, n_party, parties_unlisted = spread_listing(party_homes)
    listed = [r for r in rows if r["depth"] >= 1]
    root_row = rows[0]
    th = PARAMS["spread_homes"]

    def where(flag):
        return [r["folder"] for r in rows if flag in r["stands_out"]]

    def signal(threshold, found, **extra):
        return collections.OrderedDict([("threshold", threshold), ("count", len(found)), ("stands_out", bool(found)),
                                        ("where", found)] + list(extra.items()))

    def subjects(items):
        return [collections.OrderedDict([("subject", x["subject"]), ("homes", x["homes"])]) for x in items
                if x["stands_out"]]
    canon = [d for d in docs if d["canonical"]]
    starts = sorted(f for f, n in chain.items() if f and n >= PARAMS["chain_folders"] and not chain[
        os.path.dirname(f)])
    deepest = max(chain.items(), key=lambda kv: (kv[1], kv[0]))
    judged = [r for r in listed if r["carded_direct"] >= PARAMS["mixed_min_contents"]]
    lowest = min(judged, key=lambda r: (r["top_share_direct"], r["folder"]), default=None)
    largest = max(listed, key=lambda r: (r["documents_direct"], r["folder"]), default=None)
    copies = sum(1 for d in docs if not d["canonical"])
    contents = {d["id"] for d in docs}
    signals = collections.OrderedDict([
        ("parties_in_many_homes", collections.OrderedDict([
            ("threshold", "parties other than the main one in at least %d top-level homes" % th), ("count", n_party),
            ("stands_out", n_party > 0), ("where", subjects(parties))])),
        ("categories_in_many_homes", collections.OrderedDict([
            ("threshold", "categories in at least %d top-level homes" % th), ("count", n_cat),
            ("stands_out", n_cat > 0), ("where", subjects(cats))])),
        ("mixed_folders", signal(
            "at least %d carded contents directly in the folder, the commonest category at most %s of them"
            % (PARAMS["mixed_min_contents"], PARAMS["mixed_top_share"]), where("mixed"),
            lowest_top_share=lowest["top_share_direct"] if lowest else None,
            lowest_top_share_folder=lowest["folder"] if lowest else None)),
        ("duplicate_subtrees", signal(
            "at least %d contents, all of them also in one other folder not nested with it"
            % PARAMS["duplicate_min_contents"],
            [collections.OrderedDict([("folder", r["folder"]), ("also_in", r["duplicate_of"]),
                                      ("contents", r["contents"])]) for r in rows
             if "duplicate_subtree" in r["stands_out"]])),
        ("wide_folders", signal(
            "at least %d documents directly in the folder" % PARAMS["wide_documents"],
            [collections.OrderedDict([("folder", r["folder"]), ("documents", r["documents_direct"])])
             for r in listed if "wide" in r["stands_out"]],
            largest_direct=largest["documents_direct"] if largest else 0,
            largest_direct_folder=largest["folder"] if largest else None)),
        ("flat_dumps", signal("a wide folder with no sub-folder", where("flat_dump"))),
        ("generic_name_folders", signal(
            "at least %d canonical documents below the folder, at least %s of them named like a device or scanner "
            "default" % (PARAMS["generic_min_documents"], PARAMS["generic_share"]), where("generic_names"),
            generic_documents=sum(d["generic"] for d in canon),
            generic_share=share(sum(d["generic"] for d in canon), len(canon)))),
        ("generic_folder_names", signal("a folder named like New folder, Stuff, Misc, Other or Downloads",
                                        where("generic_folder_name"))),
        ("single_child_chains", signal(
            "a run of at least %d folders that each hold one folder and no document" % PARAMS["chain_folders"],
            starts, deepest_chain=deepest[1], deepest_chain_start=deepest[0] or None)),
        ("root_strays", signal("at least %d document directly at the root" % PARAMS["root_strays"],
                               where("root_strays"), documents=root_row["root_strays"])),
    ])
    summary = collections.OrderedDict([
        ("documents", len(docs)), ("contents", len(contents)), ("carded", len(cards)),
        ("without_card", len(contents) - len(cards)), ("held_for_another_project", left["held_for_another_project"]),
        ("excluded", left["excluded"]), ("departed", left["departed"]),
        ("top_level_folders", len({home_of(d["path"]) for d in docs} - {ROOT})), ("folders", len(rows) - 1),
        ("max_depth", max(r["depth"] for r in rows)), ("categories", len(cat_homes)), ("main_party", owner),
        ("copies", copies),
        ("copy_share", share(copies, len(docs))), ("parties_in_2_homes_not_listed", parties_unlisted)])
    return collections.OrderedDict([
        ("version", "structure-measures/1"), ("params", PARAMS), ("summary", summary), ("signals", signals),
        ("spread", collections.OrderedDict([("categories", cats), ("parties", parties)])),
        ("folders", [r for r in rows if r["depth"] <= depth])])


def esc(value):
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def sample(items, k):
    """Up to `k` items, evenly spaced over the list in its order: the same on every run."""
    n = len(items)
    if n <= k:
        return list(items)
    return [items[round(i * (n - 1) / (k - 1))] for i in range(k)] if k > 1 else items[:1]


CARD_HEAD = ["| path | doc_type | party | category | doc_date | title |", "|---|---|---|---|---|---|"]


def card_line(path, card):
    if card is None:
        return "| `%s` | (no card) | | | | |" % esc(path)
    return "| %s |" % " | ".join(["`%s`" % esc(path)] + [esc(card.get(k, "")) for k in (
        "doc_type", "party", "category", "doc_date", "title")])


def listing(items, more=0):
    return (", ".join(items) if items else "none") + (" and %d more" % more if more else "")


def render_input(res, docs, cards, depth, k):
    """The judge's input as text, from the measures and the documents (real paths; the caller shields it whole)."""
    s, sig = res["summary"], res["signals"]
    rows = {r["folder"]: r for r in res["folders"]}
    direct = collections.defaultdict(dict)
    for d in docs:
        direct[os.path.dirname(d["path"])][d["path"]] = d["id"]
    out = ["# Structure facts and a card sample", "",
           "Computed from the folder's manifest and its document cards (one card per distinct document), without "
           "opening any document. Paths are relative to the folder's top, written `(root)`. A *document* is a file (a "
           "copy is a document of its own); a *content* is one distinct document (copies share it). Categories, "
           "parties and dates are the cards'. A measure that *stands out* crossed the threshold written beside it: "
           "that marks where to look, and is no finding.", "",
           "## 1. Folder tree (folders only, to depth %d; documents directly in the folder / documents in all)" % depth,
           ""]
    for r in res["folders"]:
        out.append("%s- `%s`: %d / %d" % ("  " * r["depth"], r["folder"].split("/")[-1], r["documents_direct"],
                                          r["documents"]))
    if s["max_depth"] > depth:
        out += ["", "Folders deeper than %d are counted in the folder above them; one that stands out is named below."
                % depth]
    dup = sig["duplicate_subtrees"]
    wide, mixed, spread = sig["wide_folders"], sig["mixed_folders"], sig["categories_in_many_homes"]
    chains, strays = sig["single_child_chains"], sig["root_strays"]
    out += ["", "## 2. Measures for the whole folder", "",
            "- documents: %d; distinct contents: %d, %d of them with a card; top-level folders holding documents: %d; "
            "folders in all: %d; deepest folder depth: %d" % (s["documents"], s["contents"], s["carded"],
                                                              s["top_level_folders"], s["folders"], s["max_depth"]),
            "- left out and only counted: held for another project %d, excluded %d, departed %d"
            % (s["held_for_another_project"], s["excluded"], s["departed"]),
            "- documents directly at the root: %d (%s)" % (strays["documents"], "stands out" if strays["stands_out"]
                                                           else "does not stand out"),
            "- documents that are a second or later copy of a content held elsewhere: %d (%s of all documents)"
            % (s["copies"], s["copy_share"]),
            "- folders whose every content also lives in one other folder that is not nested with them (at least %d "
            "contents): %s" % (PARAMS["duplicate_min_contents"], listing(
                ["`%s` (also in `%s`)" % (x["folder"], x["also_in"]) for x in dup["where"][:30]],
                max(0, dup["count"] - 30))),
            "- most documents directly in one folder: %d (`%s`). Folders with at least %d directly in them: %s. Of "
            "those, with no sub-folder: %s" % (
                wide["largest_direct"], wide["largest_direct_folder"] or "none", PARAMS["wide_documents"],
                listing(["`%s` (%d)" % (x["folder"], x["documents"]) for x in wide["where"]]),
                listing(["`%s`" % x for x in sig["flat_dumps"]["where"]])),
            "- documents named like a device or scanner default (the audit's generic-name flag): %d, %s of the "
            "canonical documents. Folders where that share crosses the threshold (%s): %s" % (
                sig["generic_name_folders"]["generic_documents"], sig["generic_name_folders"]["generic_share"],
                sig["generic_name_folders"]["threshold"],
                listing(["`%s`" % x for x in sig["generic_name_folders"]["where"]])),
            "- folders named like New folder, Stuff, Misc, Other or Downloads: %s"
            % listing(["`%s`" % x for x in sig["generic_folder_names"]["where"]]),
            "- longest run of folders that each hold only one folder and no document: %d%s. Runs of at least %d start "
            "at: %s" % (chains["deepest_chain"], " (from `%s`)" % chains["deepest_chain_start"]
                        if chains["deepest_chain_start"] else "", PARAMS["chain_folders"],
                        listing(["`%s`" % x for x in chains["where"]])),
            "- categories on the cards: %d. Categories in at least %d different top-level homes (a document at the "
            "root is one home): %s" % (s["categories"], PARAMS["spread_homes"], listing(
                ["%s (%d)" % (x["subject"], x["homes"]) for x in spread["where"]])),
            "- the folder's main party is %s. Other parties and organisations (card `party` and `parties`) in at "
            "least %d top-level homes: %s" % (s["main_party"] or "not known", PARAMS["spread_homes"], listing(
                ["%s (%d)" % (x["subject"], x["homes"]) for x in sig["parties_in_many_homes"]["where"]])),
            "- folders with at least %d carded contents directly in them whose commonest category holds at most %s of "
            "them: %s. The lowest commonest-category share among folders with at least %d carded contents directly in "
            "them: %s%s" % (PARAMS["mixed_min_contents"], PARAMS["mixed_top_share"], listing(
                ["`%s` (%d categories, top share %s)" % (x, rows[x]["categories_direct"], rows[x]["top_share_direct"])
                 if x in rows else "`%s`" % x for x in mixed["where"]]), PARAMS["mixed_min_contents"],
                "not defined" if mixed["lowest_top_share"] is None else mixed["lowest_top_share"],
                " (`%s`)" % mixed["lowest_top_share_folder"] if mixed["lowest_top_share_folder"] else ""),
            "", "## 3. Measures per folder (the root and folders down to depth %d)" % depth, "",
            "Columns: documents directly in the folder; documents in all; sub-folders; distinct categories among the "
            "contents directly in it, and the commonest one's share; the same for all contents below it; documents "
            "below it that are a copy of a content whose current path is elsewhere; documents below it named like a "
            "device or scanner default (of the canonical ones); and the thresholds the folder crosses.", "",
            "| folder | direct | in all | sub-folders | categories (direct) | top share (direct) | categories (all) | "
            "top share (all) | copies | generic names | stands out |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["folders"]:
        out.append("| `%s` | %d | %d | %d | %d | %s | %d | %s | %d | %d of %d | %s |" % (
            esc(r["folder"]), r["documents_direct"], r["documents"], r["subfolders"], r["categories_direct"],
            "-" if r["top_share_direct"] is None else r["top_share_direct"], r["categories"],
            "-" if r["top_share"] is None else r["top_share"], r["copies_elsewhere"], r["generic_documents"],
            r["canonical_documents"], ", ".join(r["stands_out"]) or "none"))
    out += ["", "## 4. Card sample (up to %d cards per folder, from the documents directly in it, sorted by path and "
            "evenly spaced)" % k, ""]
    for r in res["folders"]:
        here = direct.get("" if r["folder"] == ROOT else r["folder"], {})
        carded = sorted(p for p, h in here.items() if h in cards)
        out += ["### `%s` (%d document%s directly in it)" % (esc(r["folder"]), len(here),
                                                          "" if len(here) == 1 else "s"), ""]
        if not here:
            out += ["No documents directly in this folder.", ""]
        elif not carded:
            out += ["None of its %d has a card." % len(here), ""]
        else:
            out += CARD_HEAD + [card_line(p, cards[here[p]]) for p in sample(carded, k)] + [""]
    return "\n".join(out) + "\n"


def render_documents(docs, cards, folders):
    """The documents under each folder of `folders`, with their cards' fields, as text (real paths; the caller shields
    it)."""
    out = ["# Documents under the folders in scope", "",
           "Every live document under each folder, with its card's fields (one card per distinct document; a copy is a "
           "document of its own, and a document with no card is listed without them). Paths are relative to the "
           "folder's top.", ""]
    for f in folders:
        rows = sorted((d["path"], cards.get(d["id"])) for d in docs if below(d["path"], f))
        out += ["## `%s` (%d document%s)" % (esc(f), len(rows), "" if len(rows) == 1 else "s"), ""] + CARD_HEAD
        out += [card_line(p, card) for p, card in rows] + [""]
    return "\n".join(out) + "\n"


def prepare(a):
    """The start `measure` and `documents` share: the shield, the settings, the manifest, the cards folder and the
    output path, which is refused inside the folder."""
    shield = wiki.Shielded(isolation.evidence_of(a))
    root, settings_dir, work = common.resolve(a)
    out = common.working_file(root, a.out, "structure files")
    rb = common.load_rulebook(root, settings_dir)
    _mp, man = wiki.load_manifest(root, a.manifest)
    cards_dir = os.path.realpath(a.cards) if a.cards else os.path.join(root, "_Audit", "cards")
    if not os.path.isdir(cards_dir):
        raise common.ToolError("no cards in %s: the structure is assessed after the cards (cards.py)" % cards_dir)
    return shield, root, work, out, rb, man, cards_dir


def write_working(a, root, work, rb, man, path, text, shrink):
    """`text` as the working file `path`, refused over `MAX_BYTES` (saying how to make it smaller) and registered for a
    later purge."""
    size = len(text.encode("utf-8"))
    if size > MAX_BYTES:
        raise common.ToolError("the file would be %d bytes, over the %d a model is given: %s"
                               % (size, MAX_BYTES, shrink))
    common.Writer(root if a.read_only_root else None).text(path, text)
    common.register_output(root, work, rb, path, man)


@wiki.os_errors
def measure(a):
    """The measures and the judge's input (see the module docstring), both shielded, written outside the folder."""
    if a.depth < 1 or a.sample < 1:
        raise common.ToolError("--depth and --sample count from 1")
    shield, root, work, out, rb, man, cards_dir = prepare(a)
    measures_path = common.working_file(root, a.measures or os.path.join(os.path.dirname(out), "measures.json"),
                                        "structure files")
    docs, cards, left = load_documents(rb, man, cards_dir)
    res = compute(rb, docs, cards, left, a.depth)
    text = shield.text(render_input(res, docs, cards, a.depth, a.sample))
    report = json.dumps(shield.value(res), ensure_ascii=False, indent=1) + "\n"
    shrink = "lower --sample or --depth"
    write_working(a, root, work, rb, man, out, text, shrink)
    write_working(a, root, work, rb, man, measures_path, report, shrink)
    sys.stdout.write(report)
    shield.report("the structure input and measures")
    return 0


@wiki.os_errors
def documents(a):
    """Every live document under each --folder, with its card's fields, shielded, for the author of a mapping."""
    shield, root, work, out, rb, man, cards_dir = prepare(a)
    docs, cards, _left = load_documents(rb, man, cards_dir)
    have = {f for d in docs for f in folders_of(d["path"])}
    index = common.spelling_index(have)
    wanted = sorted({common.as_spelled(index, f[:-1] if f.endswith("/") else f) for f in a.folder})
    for f in wanted:
        if f not in have:
            raise common.ToolError("--folder %r is not a folder holding live documents" % f)
    write_working(a, root, work, rb, man, out, shield.text(render_documents(docs, cards, wanted)),
                  "name fewer folders")
    shield.report("the documents of the scope")
    print("%d folder(s), %d document(s) -> %s" % (len(wanted), sum(
        1 for d in docs if any(below(d["path"], f) for f in wanted)), out))
    return 0


# ------------------------------------------------------------------------------------ the record

def parse_record(text):
    """(header, blocks, problems) of a record: `header` {label: (line number, text)} for the lines before the first
    block, `blocks` [(line number, heading, [(line number, line)])], each block's trailing blank lines dropped, and what
    is out of place before the first block or in the title."""
    lines = text.replace("\r\n", "\n").split("\n")
    problems, header, blocks = [], {}, []
    if lines[0].rstrip() != RECORD_TITLE:
        problems.append("the record does not open with %r" % RECORD_TITLE)
    for n, line in enumerate(lines[1:], 2):
        line = line.rstrip()
        if line.startswith("### "):
            blocks.append((n, line[4:].strip(), []))
        elif blocks:
            blocks[-1][2].append((n, line))
        elif line:
            label = next((x for x in HEADER if line == x + ":" or line.startswith(x + ": ")), None)
            if label is None:
                problems.append("line %d is outside the header and any block" % n)
            elif label in header:
                problems.append("line %d: %s is given twice" % (n, label))
            elif label != HEADER[len(header)]:
                problems.append("line %d: %s is out of order (the header is %s)" % (n, label, ", ".join(HEADER)))
            else:
                header[label] = (n, line[len(label) + 1:].strip())
    for _n, _h, body in blocks:
        while body and not body[-1][1]:
            body.pop()
    return header, blocks, problems


def check_block(n, heading, body, folders):
    """(the verdict or None, the problems) of one block: a heading that is a folder holding live documents (`heading`
    already as the manifest spells it), and exactly the three labelled lines, the verdict one of `VERDICTS`."""
    where = "line %d (%s)" % (n, heading)
    problems = []
    if isolation.PLACEHOLDER.search(heading):
        problems.append("%s: a folder the shield hid, which no command can open; rename the folder or exclude it, then "
                        "measure again" % where)
    elif heading not in folders:
        problems.append("%s: not a folder holding live documents" % where)
    if len(body) != len(BLOCK):
        return None, problems + ["%s: %d line(s) under the heading, not %d" % (where, len(body), len(BLOCK))]
    for (ln, line), label in zip(body, BLOCK):
        if not line.startswith("- %s: " % label) or not line[len("- %s: " % label):].strip():
            return None, problems + ["line %d (%s): not \"- %s: <text>\"" % (ln, heading, label)]
    verdict = body[0][1][len("- Verdict: "):].strip()
    if verdict not in VERDICTS:
        return None, problems + ["line %d (%s): Verdict is %r, not one of %s" % (body[0][0], heading, verdict,
                                                                                  " | ".join(VERDICTS))]
    return verdict, problems


def check_record(text, live_documents, folders):
    """The report of `check`, {overall, documents, would_move, blocks, verdicts, problems, ok}, for the record `text`
    of a folder with `live_documents` live documents and `folders`, the folders holding any."""
    header, blocks, problems = parse_record(text)
    for label in HEADER:
        if label not in header:
            problems.append("no %r line" % (label + ":"))
        elif not header[label][1]:
            problems.append("line %d: %s has no text" % (header[label][0], label))
    overall = header["Overall"][1] if "Overall" in header else None
    if overall is not None and overall not in OVERALLS:
        problems.append("line %d: Overall is %r, not one of %s" % (header["Overall"][0], overall, " | ".join(OVERALLS)))
    would_move = None
    if "Documents that would move" in header:
        n, line = header["Documents that would move"]
        m = MOVE_LINE.fullmatch("Documents that would move: " + line)
        if m is None:
            problems.append("line %d: not \"Documents that would move: <N> of <M>\" with N and M whole numbers" % n)
        else:
            would_move = int(m.group(1))
            if int(m.group(2)) != live_documents:
                problems.append("line %d: M is %s, but the folder has %d live documents (the number `measure` counts)"
                                % (n, m.group(2), live_documents))
            if would_move > int(m.group(2)):
                problems.append("line %d: N (%d) is more than M (%s)" % (n, would_move, m.group(2)))
    verdicts, seen = collections.OrderedDict((v, 0) for v in VERDICTS), collections.Counter()
    unreadable = False
    index = common.spelling_index(folders)
    for n, heading, body in blocks:
        heading = common.as_spelled(index, heading)     # a name typed composed is the folder stored decomposed
        if seen[heading]:
            problems.append("line %d (%s): the folder is assessed twice" % (n, heading))
        seen[heading] += 1
        verdict, found = check_block(n, heading, body, folders)
        problems += found
        if verdict:
            verdicts[verdict] += 1
        else:
            unreadable = True
    if not blocks:
        problems.append("no folder is assessed: a record holds a ### block for each folder it judges")
    changing = verdicts["tidy inside"] + verdicts["restructure"]
    if overall == "no re-org" and changing:
        problems.append("Overall is no re-org, but %d folder(s) are tidy inside or restructure" % changing)
    if overall == "no re-org" and would_move:
        problems.append("Overall is no re-org, but %d documents would move" % would_move)
    if would_move == 0 and overall in ("targeted", "full"):
        problems.append("Overall is %s, but no document would move (N is 0): a re-organisation that moves nothing is "
                        "no re-org" % overall)
    if would_move == 0 and changing:
        problems.append("N is 0, but %d folder(s) are tidy inside or restructure (a document that is renamed or sent "
                        "to another folder counts as moved)" % changing)
    if overall in ("targeted", "full") and blocks and not changing and not unreadable:
        problems.append("Overall is %s, but every folder is leave as it is" % overall)
    assessed = {common.as_spelled(index, h) for _n, h, _b in blocks}
    return collections.OrderedDict([
        ("overall", overall), ("documents", live_documents), ("would_move", would_move), ("blocks", len(blocks)),
        ("verdicts", verdicts),
        ("top_level_folders_without_block", len({f for f in folders if "/" not in f} - assessed)),
        ("problems", problems), ("ok", not problems)])


@wiki.os_errors
def check(a):
    """The record's shape, against the manifest (the module docstring); exit 1 when it has a problem."""
    root, settings_dir, _work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    _mp, man = wiki.load_manifest(root, a.manifest)
    path = os.path.realpath(a.record) if a.record else os.path.join(root, RECORD)
    if not os.path.isfile(path):
        raise common.ToolError("record missing: %s; the records manager's reply is written there" % path)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError as e:
        raise common.ToolError("%s is not valid UTF-8 (%s)" % (path, e))
    live = common.live_document_paths(rb, man)
    folders = {f for p in live for f in folders_of(p)}
    res = check_record(text, len(live), folders)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res["ok"] else 1


def main():
    ap = argparse.ArgumentParser(description="Structure assessment: measure, list the scope's documents, check the "
                                             "record")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common_args(p):
        p.add_argument("--root", required=True)
        p.add_argument("--settings-dir")
        p.add_argument("--work")
        p.add_argument("--manifest")
        p.add_argument("--read-only-root", action="store_true")
        return p

    def model_args(p):
        isolation.add_terms_args(p)
        p.add_argument("--cards", help="card records (default <root>/_Audit/cards)")
        p.add_argument("--out", required=True, help="the file written (never inside the folder)")
        return p

    p = model_args(common_args(sub.add_parser("measure")))
    p.add_argument("--measures", help="the measures JSON (default measures.json beside --out)")
    p.add_argument("--depth", type=int, default=3, help="folder levels listed (default 3)")
    p.add_argument("--sample", type=int, default=5, help="cards sampled per folder (default 5)")
    p = model_args(common_args(sub.add_parser("documents")))
    p.add_argument("--folder", action="append", required=True, help="a folder in scope, relative to the folder")
    p = common_args(sub.add_parser("check"))
    p.add_argument("--record", help="the record (default <root>/_Audit/structure-assessment.md)")
    a = ap.parse_args()
    return {"measure": measure, "documents": documents, "check": check}[a.cmd](a)


if __name__ == "__main__":
    common.run_main(main)
