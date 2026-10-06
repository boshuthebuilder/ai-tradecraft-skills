"""`wiki.py check`, `rationale`, `review-prompts` and `accept`, on fixture copies.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests

Each test works on its own copy of the fixture, with the frozen tests/expected/manifest.json as its manifest and the
Schema compiled into the copy; the committed fixture is never touched. The copy starts before review: the fixture's
prepared records (its extracts, cards and acceptance record, which readiness reads) are removed, and a few synthetic
cards (CARDS below) carry the review prompts' facts. Each defect the checker looks for is planted once in a fresh
copy and must be reported exactly once, as the only problem.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.realpath(os.path.join(HERE, "..", "tools"))
TIMEOUT = 600  # seconds: a tool that hangs fails its test instead of the run
FIXTURE = os.path.join(HERE, "fixture", "Alex Personal")
MANIFEST = os.path.join(HERE, "expected", "manifest.json")
WIKI = "Alex Personal Wiki"
RATIONALE = os.path.join("_Audit", "wiki-rationale.md")
ACCEPTANCE = os.path.join("_Audit", "wiki-acceptance.json")
TAX = "20 Finance/Tax.md"
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import common  # noqa: E402
from shield_flag import with_terms_flag  # noqa: E402
import wiki  # noqa: E402

CARDS = {  # path: title and key_facts of a synthetic card; the Tax page cites all three and Budget.numbers
    "02 Finance/Tax/Tax return 2023.pdf": ("Tax return 2022 to 2023", {
        "dates": ["2023-12-12"], "amounts": ["38400", "5160"], "reference_numbers": ["UTR 1234567890"]}),
    "06 Work/Contract.docx": ("Employment contract", {
        "dates": ["2022-05-01"], "amounts": ["one month's notice"], "reference_numbers": []}),
    "06 Work/Essay.docx": ("Essay: why learn a third language", {
        "dates": ["2023-11"], "amounts": [], "reference_numbers": [" "]}),  # a blank fact is no fact
}
TAX_FACTS = sorted([  # what the Tax page's cards hold, as (path, kind, value); Budget.numbers has no card
    ("02 Finance/Tax/Tax return 2023.pdf", "dates", "2023-12-12"),
    ("02 Finance/Tax/Tax return 2023.pdf", "amounts", "38400"),
    ("02 Finance/Tax/Tax return 2023.pdf", "amounts", "5160"),
    ("02 Finance/Tax/Tax return 2023.pdf", "reference_numbers", "UTR 1234567890"),
    ("06 Work/Contract.docx", "dates", "2022-05-01"),
    ("06 Work/Contract.docx", "amounts", "one month's notice"),
    ("06 Work/Essay.docx", "dates", "2023-11")])
PROBLEM_LISTS = ("frontmatter_bad", "dead_source_paths", "cites_withheld", "dead_page_links", "links_outside_page_map",
                 "charts_without_data_table", "charts_not_renderable", "chart_sources_bad",
                 "pages_without_single_professional")


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def run(tool, *args):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, tool)] + with_terms_flag(tool, args), capture_output=True, text=True,
                       encoding="utf-8", timeout=TIMEOUT)
    return r.returncode, r.stdout, r.stderr


def tree_digest(root):
    h = hashlib.sha256()
    for d, ds, fs in os.walk(root):
        ds.sort()
        for f in sorted(fs):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode() + b"\0" + read(p, "rb") + b"\n")
    return h.hexdigest()


def edit(path, old, new):
    text = read(path)
    if text.count(old) != 1:
        raise AssertionError("%r is not in %s exactly once" % (old, path))
    write(path, text.replace(old, new))


def compile_schema(root, work):
    code, _out, err = run("settings.py", "compile", "--root", root, "--work", work)
    if code:
        raise AssertionError(err)


def make_copy(parent):
    """A fixture copy under `parent` with the frozen manifest, a compiled Schema twin and CARDS; returns its root."""
    root = os.path.join(parent, "Alex Personal")
    shutil.copytree(FIXTURE, root)
    for name in ("extract", "cards"):
        shutil.rmtree(os.path.join(root, "_Audit", name))
    os.remove(os.path.join(root, ACCEPTANCE))
    shutil.copy(MANIFEST, os.path.join(root, "_Audit", "manifest.json"))
    compile_schema(root, os.path.join(parent, "work"))
    ids = {e["current_path"]: h for h, e in json.loads(read(MANIFEST))["entries"].items()}
    for path, (title, facts) in CARDS.items():
        write(os.path.join(root, "_Audit", "cards", ids[path] + ".json"),
              json.dumps({"id": ids[path], "title": title, "key_facts": facts}, ensure_ascii=False))
    return root


def contract_digest(root, number):
    """The sha256 the acceptance record keeps for a section's contract, computed from the compiled twin."""
    ws = json.loads(read(os.path.join(root, ".familyai", "wiki-schema.json")))
    c = next(x for x in ws["contracts"] if x["number"] == number)
    obj = {k: c[k] for k in ("reader", "questions", "fields")}
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def blocks_of(text):
    """{page: its rationale block, heading and five lines} from a rationale file in the fixture's format."""
    return {b.split("\n", 1)[0][4:]: b.strip("\n") for b in re.split(r"\n(?=### )", text)[1:]}


def findings(res):
    """{problem key: how many}, for every key holding at least one finding."""
    counts = {k: len(res[k]) for k in PROBLEM_LISTS if isinstance(res[k], list)}
    counts.update(em_dash_lines=res["em_dash_lines"], documents_not_covered=res["documents_not_covered"])
    if isinstance(res["rationale"], dict):
        counts.update({"rationale." + k: len(v) for k, v in res["rationale"].items() if isinstance(v, list)})
    return {k: v for k, v in counts.items() if v}


class Copy(unittest.TestCase):
    """Each test works on its own fixture copy; the committed fixture is never touched."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="wiki_check_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = make_copy(os.path.join(self.tmp, "a"))
        self.work = os.path.join(self.tmp, "a", "work")

    def wiki(self, cmd, *args, root=None):
        return run("wiki.py", cmd, "--root", root or self.root, "--work", self.work, *args)

    def ok(self, cmd, *args, code=0, **kw):
        got, out, err = self.wiki(cmd, *args, **kw)
        self.assertEqual(got, code, out + err)
        return out

    def refused(self, cmd, *args, **kw):
        code, out, err = self.wiki(cmd, *args, **kw)
        self.assertEqual(code, 2, out + err)
        self.assertNotIn("Traceback", err)
        return err

    def check(self, *args, root=None):
        code, out, err = self.wiki("check", *args, root=root)
        self.assertIn(code, (0, 1), err)
        res = json.loads(out)
        self.assertEqual(code, 1 if res["problems"] else 0)
        return res

    def page(self, rel, root=None):
        return os.path.join(root or self.root, WIKI, *rel.split("/"))

    def sha(self, rel):
        return hashlib.sha256(read(self.page(rel), "rb")).hexdigest()


# ------------------------------------------------------------------------------------ check

def edit_block(root, page, change):
    """Replace `page`'s block in the rationale file with change(its five lines)."""
    path = os.path.join(root, RATIONALE)
    old = blocks_of(read(path))[page]
    lines = old.split("\n")
    edit(path, old + "\n", "\n".join(lines[:1] + change(lines[1:])) + "\n")


def lens_of(root, page):
    return blocks_of(read(os.path.join(root, RATIONALE)))[page].split("\n")[2]


def line_of(root, page, text):
    return read(os.path.join(root, WIKI, *page.split("/"))).split("\n").index(text) + 1


# Each defect: what it is, the key reporting it, a function of the copy's root giving the expected finding (the one
# item in that key's list, or for em dashes and coverage the item in em_dash_where and not_covered_sample), and
# the plant, a function of (root, work).
DEFECTS = [
    ("a page missing a frontmatter key", "frontmatter_bad", lambda r: "40 Study/40 Study.md",
     lambda r, w: edit(os.path.join(r, WIKI, "40 Study", "40 Study.md"), "status: current\n", "")),
    ("a sources: entry that does not exist", "dead_source_paths",
     lambda r: ["20 Finance/Cash position.md", "02 Finance/Tax/Budget 2025.xlsx"],
     lambda r, w: edit(os.path.join(r, WIKI, "20 Finance", "Cash position.md"),
                       '  - "02 Finance/Tax/Budget final.xlsx"\n',
                       '  - "02 Finance/Tax/Budget final.xlsx"\n  - "02 Finance/Tax/Budget 2025.xlsx"\n')),
    ("a backticked file under a live folder that does not exist", "dead_source_paths",
     lambda r: ["30 Home/30 Home.md", "03 Home/Gas bill.pdf"],  # a span wrapped onto two lines reads as one
     lambda r, w: edit(os.path.join(r, WIKI, "30 Home", "30 Home.md"), "Alex rents 3 Example Road",
                       "The gas bill is `03 Home/Gas\nbill.pdf`.\n\nAlex rents 3 Example Road")),
    ("a backticked folder under a live folder that does not exist", "dead_source_paths",
     lambda r: ["30 Home/30 Home.md", "03 Home/Garden/"],
     lambda r, w: edit(os.path.join(r, WIKI, "30 Home", "30 Home.md"), "Alex rents 3 Example Road",
                       "Nothing is filed in `03 Home/Garden/`.\n\nAlex rents 3 Example Road")),
    ("a link that does not resolve", "dead_page_links", lambda r: ["20 Finance/20 Finance.md", "Pensions.md"],
     lambda r, w: edit(os.path.join(r, WIKI, "20 Finance", "20 Finance.md"), "- [Tax](Tax.md)",
                       "- [Pensions](Pensions.md): none yet.\n- [Tax](Tax.md)")),
    ("a link outside the page map", "links_outside_page_map",
     lambda r: ["20 Finance/20 Finance.md", "../../CLAUDE.md"],
     lambda r, w: edit(os.path.join(r, WIKI, "20 Finance", "20 Finance.md"), "- [Tax](Tax.md)",
                       "- [The rules](../../CLAUDE.md): the folder's rulebook.\n- [Tax](Tax.md)")),
    ("an em dash outside code", "em_dash_lines", lambda r: ["40 Study/40 Study.md", 8],
     lambda r, w: edit(os.path.join(r, WIKI, "40 Study", "40 Study.md"), "certificate, 2023 to 2024.",
                       "certificate \u2014 2023 to 2024 (`\u2014` in code is not counted).")),
    ("a document no page covers", "documents_not_covered", lambda r: "03 Home/Lease notes .txt",
     lambda r, w: edit(os.path.join(r, WIKI, "30 Home", "30 Home.md"),
                       "| Lease notes | | `03 Home/Lease notes .txt` |\n", "")),
    ("a document whose folder is named only as a prefix of another path", "documents_not_covered",
     lambda r: "04 Study/Notes.rtf",
     lambda r, w: edit(os.path.join(r, WIKI, "40 Study", "40 Study.md"), "| `04 Study/` | 5 | certificates, slides, "
                       "essay, notes |", "| `04 Study/Slides.pptx` | 1 | slides |")),
    ("a document named only by its grandparent folder", "documents_not_covered",
     lambda r: "01 Identity/Passport renewal 2021/Application form.docx",
     lambda r, w: edit(os.path.join(r, WIKI, "10 Identity", "10 Identity.md"),
                       "`01 Identity/Passport renewal 2021/` (2 files: the scan copy and\n"
                       "`01 Identity/Passport renewal 2021/Application form.docx`, which names the previous passport "
                       "P0987654).", "`01 Identity/`.")),
    ("a document named only on the Log", "documents_not_covered", lambda r: "03 Home/Lease notes .txt",
     lambda r, w: (edit(os.path.join(r, WIKI, "30 Home", "30 Home.md"),
                        "| Lease notes | | `03 Home/Lease notes .txt` |\n", ""),
                   edit(os.path.join(r, WIKI, "91 Log", "91 Log.md"), "fixture folder.",
                        "fixture folder.\n\n## [2024-07-01] ingest | `03 Home/Lease notes .txt`"))),
    ("sources: written as one value, not a list", "frontmatter_bad", lambda r: "40 Study/40 Study.md",
     lambda r, w: edit(os.path.join(r, WIKI, "40 Study", "40 Study.md"), "status: current\n",
                       'status: current\nsources: "04 Study/Notes.rtf"\n')),
    ("a chart without its data table", "charts_without_data_table",
     lambda r: ["30 Home/30 Home.md", line_of(r, "30 Home/30 Home.md", "```mermaid")],
     lambda r, w: edit(os.path.join(r, WIKI, "30 Home", "30 Home.md"),
                       "| Date | Label | Source |\n| --- | --- | --- |\n"
                       "| 2024-05-01 | Lease renewed to 2025-04-30 | `03 Home/Lease renewal.pdf` |\n"
                       "| 2024-03-15 | Electricity bill GBP 96.40 | `03 Home/Utilities /Electricity bill.pdf` |\n\n",
                       "")),
    ("a Mermaid block no kind of chart renders", "charts_not_renderable",
     lambda r: ["40 Study/40 Study.md", line_of(r, "40 Study/40 Study.md", "```mermaid"), "flowchart"],
     lambda r, w: edit(os.path.join(r, WIKI, "40 Study", "40 Study.md"), "| Folder | Files |",
                       "```mermaid\nflowchart LR\n    French --> Chinese\n```\n\n| Folder | Files |")),
    ("a chart source that does not exist", "chart_sources_bad",
     lambda r: ["20 Finance/Cash position.md", line_of(r, "20 Finance/Cash position.md",
                                                       "| Savings | 400 | `02 Finance/Tax/Budget 2025.xlsx` |"),
                "02 Finance/Tax/Budget 2025.xlsx"],
     lambda r, w: edit(os.path.join(r, WIKI, "20 Finance", "Cash position.md"),
                       "| Savings | 400 | `02 Finance/Tax/Budget final.xlsx` |",
                       "| Savings | 400 | `02 Finance/Tax/Budget 2025.xlsx` |")),
    ("a chart source under a reserved name", "chart_sources_bad",
     lambda r: ["20 Finance/Cash position.md", line_of(r, "20 Finance/Cash position.md",
                                                       "| Savings | 400 | `_Audit/wiki-rationale.md` |"),
                "_Audit/wiki-rationale.md"],
     lambda r, w: edit(os.path.join(r, WIKI, "20 Finance", "Cash position.md"),
                       "| Savings | 400 | `02 Finance/Tax/Budget final.xlsx` |",
                       "| Savings | 400 | `_Audit/wiki-rationale.md` |")),
    ("a page with no single professional", "pages_without_single_professional",
     lambda r: ["20 Finance/20 Finance.md", "page '20 Finance/20 Finance.md' is not in the Schema's Page "
                "professionals table and section 20 Finance names 3 professionals (private banker; CFO; chartered "
                "tax adviser); list the page"],
     lambda r, w: (edit(os.path.join(r, WIKI, "90 Schema", "90 Schema.md"),
                        "| 20 Finance/20 Finance.md | private banker | finance overview | measured |\n", ""),
                   compile_schema(r, w))),
    ("a page with no rationale block", "rationale.pages_without_block", lambda r: "40 Study/40 Study.md",
     lambda r, w: edit(os.path.join(r, RATIONALE), blocks_of(read(os.path.join(r, RATIONALE)))["40 Study/40 Study.md"]
                       + "\n\n", "")),
    ("a block for no page", "rationale.blocks_without_page", lambda r: "20 Finance/Pensions.md",
     lambda r, w: edit(os.path.join(r, RATIONALE), "### 20 Finance/Tax.md\n", blocks_of(read(os.path.join(
         r, RATIONALE)))[TAX].replace(TAX, "20 Finance/Pensions.md") + "\n\n### 20 Finance/Tax.md\n")),
    ("a page's second block", "rationale.blocks_repeated", lambda r: "30 Home/30 Home.md",
     lambda r, w: write(os.path.join(r, RATIONALE), read(os.path.join(r, RATIONALE)) + "\n" + blocks_of(read(
         os.path.join(r, RATIONALE)))["30 Home/30 Home.md"] + "\n")),
    ("a block missing a line", "rationale.blocks_malformed", lambda r: [TAX, "4 lines under the heading, not 5"],
     lambda r, w: edit_block(r, TAX, lambda ls: ls[:2] + ls[3:])),
    ("a block with its lines out of order", "rationale.blocks_malformed",
     lambda r: [TAX, 'line 3 is not "- Shape: <text>"'],
     lambda r, w: edit_block(r, TAX, lambda ls: ls[:2] + [ls[3], ls[2]] + ls[4:])),
    ("a malformed block for a path that is no page", "rationale.blocks_malformed",
     lambda r: ["20 Finance/Pensions.md", "1 line under the heading, not 5"],
     lambda r, w: write(os.path.join(r, RATIONALE), read(os.path.join(r, RATIONALE))
                        + "\n### 20 Finance/Pensions.md\n- Reader and use: Alex, for the pension.\n")),
    ("a repeated block, one naming another professional", "rationale.blocks_repeated",
     lambda r: "20 Finance/Cash position.md",
     lambda r, w: write(os.path.join(r, RATIONALE), read(os.path.join(r, RATIONALE)) + "\n" + blocks_of(read(
         os.path.join(r, RATIONALE)))["20 Finance/Cash position.md"].replace("lens: CFO;", "lens: private banker;")
                        + "\n")),
    ("a block with a label left empty", "rationale.blocks_malformed",
     lambda r: [TAX, 'line 5 is not "- Left out or flagged: <text>"'],
     lambda r, w: edit_block(r, TAX, lambda ls: ls[:4] + ["- Left out or flagged: "])),
    ("a block under a heading that is no page path", "rationale.blocks_malformed",
     lambda r: ["Notes on the wiki", "the heading is not a page path"],
     lambda r, w: write(os.path.join(r, RATIONALE), read(os.path.join(r, RATIONALE))
                        + "\n### Notes on the wiki\n- Written by hand.\n")),
    ("a rationale file without its title", "rationale.blocks_malformed",
     lambda r: ["# Wiki rationale", "the file does not open with it"],
     lambda r, w: edit(os.path.join(r, RATIONALE), "# Wiki rationale\n", "# Rationale\n")),
    ("text before the first block", "rationale.blocks_malformed",
     lambda r: ["(before the first block)", "line 2 is outside any block"],
     lambda r, w: edit(os.path.join(r, RATIONALE), "# Wiki rationale\n", "# Wiki rationale\nNotes.\n")),
    ("a block whose lens names another professional", "rationale.professional_not_named",
     lambda r: ["20 Finance/Cash position.md", "private banker", "CFO"],
     lambda r, w: edit_block(r, "20 Finance/Cash position.md", lambda ls: ls[:1] + [
         ls[1].replace("Professional lens: CFO;", "Professional lens: private banker;")] + ls[2:])),
]


class CheckTest(Copy):
    def test_the_fixture_has_no_problems(self):
        res = self.check()
        self.assertEqual((res["problems"], findings(res)), (0, {}))
        self.assertEqual(res["rationale"], {"blocks": 12, "pages_without_block": [], "blocks_without_page": [],
                                            "blocks_repeated": [], "blocks_malformed": [],
                                            "professional_not_named": []})
        self.assertEqual((res["pages"], res["chart_blocks"], res["documents_in_scope"]), (12, 4, 17))
        self.assertEqual(res["backticked_paths_unchecked"], 1)  # the Schema's `_Inbox/`: no live folder
        self.assertEqual(res["acceptance"], "not recorded")
        self.assertEqual(res["acceptance_counts"], {"accepted": 0, "not recorded": 12, "refused": 0})
        self.assertEqual(res["acceptance_pages"][0], ["00 Index/00 Index.md", "not recorded", "no verdict recorded"])
        self.assertEqual(res["acceptance_not_verified"], [])

    def test_each_defect_is_reported_once(self):
        names = [d[0] for d in DEFECTS]
        self.assertEqual(len(set(names)), len(names))
        for n, (name, key, expected, plant) in enumerate(DEFECTS):
            with self.subTest(defect=name):
                parent = os.path.join(self.tmp, "d%d" % n)
                root = make_copy(parent)
                plant(root, os.path.join(parent, "work"))
                res = self.check(root=root)
                self.assertEqual((res["problems"], findings(res)), (1, {key: 1}))
                if key == "em_dash_lines":
                    got = res["em_dash_where"][0]
                elif key == "documents_not_covered":
                    got = res["not_covered_sample"][0]
                elif key.startswith("rationale."):
                    got = res["rationale"][key.split(".")[1]][0]
                else:
                    got = res[key][0]
                self.assertEqual(got, expected(root))

    def test_a_professional_differing_only_in_case_and_spacing_is_named(self):
        edit_block(self.root, "20 Finance/Cash position.md", lambda ls: ls[:1] + [
            ls[1].replace("Professional lens: CFO;", "Professional lens: cfo;")] + ls[2:])
        edit_block(self.root, TAX, lambda ls: ls[:1] + [
            ls[1].replace("lens: chartered tax adviser;", "lens: Chartered  Tax\tAdviser;")] + ls[2:])
        res = self.check()
        self.assertEqual((res["problems"], res["rationale"]["professional_not_named"]), (0, []))

    def test_coverage_forms(self):
        study = self.page("40 Study/40 Study.md")
        edit(study, "| `04 Study/` | 5 |", "| `04 Study` | 5 |")  # a folder without its trailing slash covers
        edit(self.page(TAX), "`06 Work/Essay.docx`", "`05 Archive/Essay.docx`")  # so does a copy's path
        res = self.check()
        self.assertEqual((res["problems"], res["documents_not_covered"]), (0, 0))
        edit(study, "| `04 Study` | 5 |", "| 04 Study | 5 |")  # a folder named without backticks does not
        self.assertEqual(self.check()["not_covered_sample"], ["04 Study/Notes.rtf", "04 Study/Slides.pptx"])

    def exclude(self, *paths, root=None):
        """The rulebook's `exclude` set to `paths`: the twin only (its pin is of CLAUDE.md, which is not touched)."""
        twin = os.path.join(root or self.root, ".familyai", "rulebook.json")
        write(twin, json.dumps(dict(json.loads(read(twin)), exclude=list(paths)), ensure_ascii=False, indent=1))

    def test_an_excluded_document_is_never_required_by_coverage_and_never_named(self):
        """No page names it, and none need: it is counted, never listed, so its path is in no output."""
        plant = [d for d in DEFECTS if d[0] == "a document no page covers"][0][3]
        plant(self.root, self.work)
        self.assertEqual(self.check()["not_covered_sample"], ["03 Home/Lease notes .txt"])
        self.exclude("03 Home/Lease notes .txt")
        res = self.check()
        self.assertEqual((res["problems"], res["documents_not_covered"], res["not_covered_sample"]), (0, 0, []))
        self.assertEqual((res["documents_in_scope"], res["documents_excluded"],
                          res["documents_held_for_another_project"]), (16, 1, 1))
        self.assertNotIn("Lease notes", json.dumps(res))

    def test_an_excluded_folder_takes_everything_under_it_out_of_scope(self):
        study = sum(e["current_path"].startswith("04 Study/") for e in json.loads(read(MANIFEST))["entries"].values())
        self.assertEqual(study, 4)
        self.exclude("04 Study")
        res = self.check()
        self.assertEqual((res["documents_in_scope"], res["documents_excluded"]), (17 - study, study))

    def test_a_document_held_for_another_project_is_counted_apart(self):
        res = self.check()
        self.assertEqual((res["documents_in_scope"], res["documents_held_for_another_project"],
                          res["documents_excluded"]), (17, 1, 0))
        self.assertEqual(self.check("--page", TAX)["documents_held_for_another_project"], 1)

    def cites(self, *excluded, cite=(), page=TAX):
        twin = os.path.join(self.root, ".familyai", "rulebook.json")
        write(twin, json.dumps(dict(json.loads(read(twin)), exclude=list(excluded)), ensure_ascii=False, indent=1))
        if cite:
            write(self.page(page), read(self.page(page)) + "\n" + "".join("Also see `%s`.\n" % c for c in cite))
        return self.check()

    def test_a_page_citing_an_excluded_document_is_a_problem_and_names_no_path(self):
        res = self.cites("06 Work")
        found = res["cites_withheld"]  # the `sources:` entry and the two spans of the body that name it
        self.assertEqual([[p, why] for p, _line, why in found], [[TAX, "excluded"]] * 3)
        self.assertEqual((res["problems"], findings(res)), (3, {"cites_withheld": 3}))
        text = read(self.page(TAX)).split("\n")
        self.assertEqual([text[line - 1].count("06 Work") > 0 for _p, line, _w in found], [True, True, True])
        self.assertNotIn("06 Work", json.dumps(found))

    def test_a_page_citing_a_copy_of_a_withheld_document_or_a_staged_one_is_a_problem_too(self):
        res = self.cites("06 Work", cite=["05 Archive/Essay.docx", "_Migrations/Other Project/02 Finance/Old invoice.pdf",
                                          "_Migrations/Other Project/02 Finance/"])
        self.assertEqual(sorted(why for _p, _l, why in res["cites_withheld"]),
                         ["excluded"] * 4 + ["migrations"] * 2)

    def test_only_a_citation_of_a_withheld_document_counts(self):
        res = self.cites("06 Work", cite=["_Migrations/<Project>/", "_Migrations/", "06 Work/Nothing.docx", "06 Workshop/x.pdf",
                                          "05 Archive/", "04 Study/Notes.rtf"])
        self.assertEqual(len(res["cites_withheld"]), 4, "the three the Tax page already has, and a file under the "
                         "excluded folder; not the placeholder, the bare migrations folder or the near names")

    def test_the_schema_and_the_log_may_name_a_withheld_folder_but_not_a_withheld_document(self):
        res = self.cites("06 Work")
        pages = {p for p, _l, _w in res["cites_withheld"]}
        self.assertEqual(pages, {TAX})
        self.assertIn("06 Work/", read(os.path.join(self.root, WIKI, "90 Schema", "90 Schema.md")))
        log = os.path.join(self.root, WIKI, "91 Log", "91 Log.md")
        write(log, read(log) + "\n## [2024-07-01] ingest | `06 Work/Contract.docx` (the nanny's contract)\n")
        schema = os.path.join(self.root, WIKI, "90 Schema", "90 Schema.md")
        write(schema, read(schema) + "\nA worked example: `06 Work/Essay.docx`.\n")
        compile_schema(self.root, self.work)
        res = self.check()
        self.assertEqual(sorted({p for p, _l, _w in res["cites_withheld"]}),
                         [TAX, "90 Schema/90 Schema.md", "91 Log/91 Log.md"])
        self.assertEqual(len([c for c in res["cites_withheld"] if c[0] != TAX]), 2)

    def test_a_case_or_unicode_variant_of_a_withheld_path_is_still_a_citation(self):
        text = read(self.page(TAX)).replace("06 Work/", "06 work/")
        write(self.page(TAX), text)
        self.assertEqual(len(self.cites("06 Work")["cites_withheld"]), 3, "the variants a macOS path opens")
        man = os.path.join(self.root, "_Audit", "manifest.json")
        m = json.loads(read(man))
        accented = unicodedata.normalize("NFD", "06 Work/Caf\u00e9 menu.txt")  # as the file system stores it
        next(iter(m["entries"].values()))["copies"] = []
        m["entries"]["f" * 64] = {"id": "f" * 64, "current_path": accented, "class": "document", "hashed": True,
                                  "flags": [], "size": 1, "mtime": "2024-06-01T00:00:00Z"}
        write(man, json.dumps(m))
        page = self.page("40 Study/40 Study.md")
        write(page, read(page) + "\nThe menu is `%s`.\n" % unicodedata.normalize("NFC", "06 Work/Caf\u00e9 menu.txt"))
        found = [c for c in self.check()["cites_withheld"] if c[0] == "40 Study/40 Study.md"]
        self.assertEqual([c[2] for c in found], ["excluded"])
        code, out, err = self.wiki("review-prompts", "--page", "40 Study/40 Study.md", "--author-model", "a",
                                   "--reviewer-model", "b", "--out", os.path.join(self.tmp, "q"))
        self.assertEqual(code, 2, out + err)
        self.assertNotIn("Caf", err)

    def test_a_withheld_path_in_plain_text_a_fence_or_a_link_is_a_citation(self):
        self.exclude("06 Work")
        edits = {"plain text": "The contract is 06 Work/Contract.docx, signed in May.\n",
                 "a fence": "```text\n06 Work/Contract.docx\n```\n",
                 "a link": "See [the contract](../../06%20Work/Contract.docx).\n",
                 "other case": "See 06 WORK/contract.DOCX.\n"}
        page = self.page("40 Study/40 Study.md")
        base = read(page)
        for name, text in edits.items():
            with self.subTest(name):
                write(page, base + "\n" + text)
                found = [c for c in self.check()["cites_withheld"] if c[0] == "40 Study/40 Study.md"]
                self.assertEqual([c[2] for c in found], ["excluded"], name)
        write(page, base + "\nWorkshop 06 Workshop/x and the Work/Contract.docx idea.\n")
        self.assertEqual([c for c in self.check()["cites_withheld"] if c[0] == "40 Study/40 Study.md"], [])

    LOG = "91 Log/91 Log.md"

    def test_a_page_citing_a_staged_document_by_the_path_it_was_staged_from_is_a_problem(self):
        """`_Migrations/Other Project/02 Finance/Old invoice.pdf` was staged from `02 Finance/Old invoice.pdf`: the page
        still names the old path, which no live document holds, and drift already treats it as staged."""
        page = "40 Study/40 Study.md"
        self.base = {page: read(self.page(page))}
        self.assertEqual([c[2] for c in self.appended(page, "The invoice is `02 Finance/Old invoice.pdf`.\n")],
                         ["migrations"])
        self.assertEqual([c[2] for c in self.appended(page, "See 02 Finance/Old\ninvoice.pdf for it.\n")],
                         ["migrations"])
        code, out, err = self.wiki("review-prompts", "--page", page, "--author-model", "a", "--reviewer-model", "b",
                                   "--out", os.path.join(self.tmp, "q"))
        self.assertEqual(code, 2, out + err)
        self.assertNotIn("Old invoice", err)

    LIVE_FOLDERS = ("Photos", "Photos (2024)", "Alex's Scans", "Receipts, 2024", "Scans [old]")  # each holds a live `Scan 1.pdf`
    PRIVATE = "Alex's Scans/Private [old]/Secret, 2024.pdf"  # excluded, and its names hold an apostrophe, brackets, a comma

    def live_paths(self):
        return ["%s/Scan 1.pdf" % f for f in self.LIVE_FOLDERS] + ["Backups/%s/Scan 1.pdf" % os.path.basename(self.root),
                                                                    "Old (2019)/06 Work/Contract.docx",
                                                                    "05 Archive/06 Work/Contract.docx"]

    def live_inside_a_copy_of_the_folder(self):
        """A live document under a folder that is a copy of this one: a page may name it from the copy's own name."""
        return "Archive/%s/Reports/Scan 1.pdf" % os.path.basename(self.root)

    def stage_a_root_stray(self):
        """`_Migrations/Other Project/Scan 1.pdf` staged from the root (its history names `Scan 1.pdf`), `06 Work/Contract.docx`
        and the private folder excluded, and different live documents named `Scan 1.pdf` in folders whose names hold
        brackets, an apostrophe, a comma, and one that is the folder's own name; the page to append to."""
        man = os.path.join(self.root, "_Audit", "manifest.json")
        m = json.loads(read(man))
        entries = [("_Migrations/Other Project/Scan 1.pdf", ["migrating"]), (self.PRIVATE, [])]
        entries += [(path, []) for path in self.live_paths() + [self.live_inside_a_copy_of_the_folder(), "Backups/Staff/pay.pdf"]]
        for path, flags in entries:
            i = hashlib.sha256(path.encode()).hexdigest()
            m["entries"][i] = {"id": i, "current_path": path, "class": "document", "hashed": True, "flags": flags,
                               "copies": [], "size": 1, "mtime": "2024-06-01T00:00:00Z",
                               "rename_history": [{"path": "Scan 1.pdf" if flags else path, "at": "2024-06-01T00:00:00Z",
                                                   "run_id": "x"}]}
        write(man, json.dumps(m))
        os.makedirs(os.path.join(self.root, *self.PRIVATE.split("/")[:-1]))
        os.makedirs(os.path.join(self.root, "Staff"))
        self.exclude("06 Work/Contract.docx", "Alex's Scans/Private [old]", "Staff")
        page = "40 Study/40 Study.md"
        self.base = {page: read(self.page(page))}
        return page

    def spellings_of_the_folder(self):
        """The folder's location spelt as a page might: its real path, the same without the leading /private a macOS
        temporary folder has, another volume's host form, and through the cloud drive."""
        out = [self.root, "file://" + self.root, "file://localhost" + self.root, "iCloud Drive/" + os.path.basename(self.root)]
        if self.root.startswith("/private/"):
            out.append(self.root[len("/private"):])
        return out

    @staticmethod
    def layouts(path):
        """The ways a page may carry `path`, whatever its names hold: in a citation, in prose, in links, in a list, in a
        quotation, starting a line (the line before ends in a word), indented, and hard-wrapped at a slash and at a space."""
        head, _slash, tail = path.rpartition("/")
        out = {"cited": "See `%s`." % path, "in prose": "See %s for it." % path,
               "a link": "See [s](%s)." % urllib.parse.quote(path), "a link in angle brackets": "See [s](<%s>)." % path,
               "a list item": "- %s" % path, "a numbered item": "1. %s here" % path, "a blockquote": "> %s" % path,
               "a nested quotation": "> > %s" % path, "indented": "  %s" % path,
               "starting a line": "Some words ahead\n%s here" % path,
               "starting a line after a long word": "Documentation\n%s" % path,
               "wrapped at a space": path.replace(" ", "\n", 1) if " " in path else path.replace(".", "\n.", 1),
               "wrapped inside a name": path[:3] + "\n" + path[3:]}
        if head:
            out.update({"wrapped at a slash": "%s/\n%s" % (head, tail), "wrapped at a slash in a list": "- %s/\n  %s" % (head, tail),
                        "wrapped at a slash in a quotation": "> %s/\n> %s" % (head, tail)})
        return out

    def test_a_withheld_path_is_a_citation_in_every_form_that_resolves_to_it_and_not_for_a_live_document_of_the_same_tail(self):
        """A match of a withheld path that follows a `/` is explained, and no citation, when it ends a live, included
        document's path that the text before it ends with: `Photos (2024)/Scan 1.pdf` is that document, not the staged root
        stray `Scan 1.pdf`, whatever brackets, apostrophes or commas its names hold and however the page lays it out; every
        spelling of the withheld path itself, a climb out of the folder and back in by its name included, is flagged."""
        page = self.stage_a_root_stray()
        name = os.path.basename(self.root)
        for what, doc, why in (("the excluded document", "06 Work/Contract.docx", "excluded"),
                               ("the staged document", "_Migrations/Other Project/Scan 1.pdf", "migrations"),
                               ("the path it was staged from", "Scan 1.pdf", "migrations"),
                               ("an excluded document with brackets, an apostrophe and a comma", self.PRIVATE, "excluded")):
            quoted = urllib.parse.quote(doc)
            forms = {"in prose, after a slash": "See /%s for it." % doc, "in prose after the folder's name":
                     "See %s/%s for it." % (name, doc),
                     "a link climbing out and back in by the folder's name":
                     "See [x](../../../%s/%s)." % (urllib.parse.quote(name), quoted),
                     "text climbing out and back in by the folder's name": "See ../../../%s/%s here." % (name, doc),
                     "a link by ../ and the folder's name": "See [x](../%s/%s)." % (urllib.parse.quote(name), quoted),
                     "text by ../ and the folder's name": "See ../%s/%s here." % (name, doc),
                     "a link climbing to the folder": "See [x](../../%s)." % quoted,
                     "a wrapped path after the folder's name": "See %s/\n%s here." % (name, doc)}
            for n, where in enumerate(self.spellings_of_the_folder()):
                forms["the folder spelt another way (%d) in prose" % n] = "See %s/%s here." % (where, doc)
                forms["the folder spelt another way (%d) in a citation" % n] = "See `%s/%s`." % (where, doc)
                forms["the folder spelt another way (%d) in a link" % n] = "See [x](%s/%s)." % (urllib.parse.quote(
                    where, safe="/:"), quoted)
            forms.update({"laid out: " + k: v for k, v in self.layouts(doc).items()})
            for form, text in forms.items():
                with self.subTest(what=what, form=form):
                    found = self.appended(page, text + "\n")
                    self.assertEqual({c[2] for c in found}, {why}, text)
        live = {}
        for path in self.live_paths():
            live.update({"%s: %s" % (path, k): v for k, v in self.layouts(path).items()})
        live.update({"climbing out and back in by the folder's name, linked": "See [s](../../../%s/Photos/Scan%%201.pdf)." %
                     urllib.parse.quote(name),
                     "climbing out and back in by the folder's name": "See ../../../%s/Photos (2024)/Scan 1.pdf here." % name,
                     "through the cloud drive": "See iCloud Drive/%s/Receipts, 2024/Scan 1.pdf here." % name,
                     "after the folder's name": "See %s/Scans [old]/Scan 1.pdf here." % name,
                     "after the folder's name, a live document of that name": "See Backups/%s/Scan 1.pdf here." % name,
                     "the folder spelt another way": "See `%s/Alex's Scans/Scan 1.pdf`." % self.spellings_of_the_folder()[-1],
                     "a longer path that ends in a live document's": "See `20 Finance/Photos (2024)/Scan 1.pdf`.",
                     "named from a copy of the folder's own name, as a link reads it": "See %s/Reports/Scan 1.pdf here." % name,
                     "the same in a link": "See [s](../../../%s/Reports/Scan%%201.pdf)." % urllib.parse.quote(name)})
        for form, text in live.items():
            with self.subTest(live=form):
                self.assertEqual(self.appended(page, text + "\n"), [], text)
        blockers = {
            # a name that only ends in a live folder's name is no path that starts a segment there
            "a folder that is not live, ending in a live one's name": ("See `Household (2019)/06 Work/Contract.docx`.", "excluded"),
            "the same in prose": ("See Household (2019)/06 Work/Contract.docx here.", "excluded"),
            "MyPhotos": ("See MyPhotos/Scan 1.pdf here.", "migrations"),
            "Family-Photos": ("See Family-Photos/Scan 1.pdf here.", "migrations"),
            "Old_Photos": ("See `Old_Photos/Scan 1.pdf`.", "migrations"),
            "Old.Photos": ("See Old.Photos/Scan 1.pdf here.", "migrations"),
            "NotBackups, the withheld folder": ("See `NotBackups/Staff/pay.pdf`.", "excluded"),
            "OldBackups, the withheld folder": ("See OldBackups/Staff/pay.pdf here.", "excluded"),
            "TaxReports, as the copy's Reports": ("See TaxReports/Scan 1.pdf here.", "migrations"),
            # a live folder at the end of one paragraph, a withheld path opening the next
            "a list of folders, then a blank line": ("Folders reviewed: 02 Finance/, Photos/\n\nScan 1.pdf was staged for another "
                                                     "project.", "migrations"),
            "a slash and the path, after a blank line": ("Everything else is in Photos\n\n/Scan 1.pdf was staged.", "migrations"),
            "a quotation, then a blank line": ("> Kept in Photos/\n\nScan 1.pdf was staged.", "migrations"),
            "an indented path after a blank line": ("Folders: Photos/\n\n    Scan 1.pdf was staged.", "migrations"),
            "the excluded document after a blank line": ("Older papers: Old (2019)/\n\n06 Work/Contract.docx is the contract.",
                                                         "excluded"),
            "the withheld folder after a blank line": ("Copies are in Backups/\n\nStaff/pay.pdf is the payroll.", "excluded"),
            "a heading, with no blank line": ("## Photos/\nScan 1.pdf was staged for another project.", "migrations"),
            "a heading before the excluded document": ("## Old (2019)/\n06 Work/Contract.docx is the contract.", "excluded")}
        for form, (text, why) in blockers.items():
            with self.subTest(blocker=form):
                self.assertEqual({c[2] for c in self.appended(page, text + "\n")}, {why}, text)
                code, out, err = self.wiki("review-prompts", "--page", page, "--author-model", "a", "--reviewer-model", "b",
                                           "--out", os.path.join(self.tmp, "q"))
                self.assertEqual(code, 2, "review-prompts rendered a page that cites a withheld document: " + text + err)
        with self.subTest(live="a live folder explains a withheld folder of the same tail"):
            for text in ("See `Backups/Staff/pay.pdf`.", "See Backups/Staff/pay.pdf here.", "See [s](Backups/Staff/pay.pdf).",
                         "- Backups/Staff/pay.pdf", "> Backups/\nStaff/pay.pdf"):
                self.assertEqual(self.appended(page, text + "\n"), [], text)
        with self.subTest(unexplained="the withheld folder itself"):
            for text in ("See Staff/pay.pdf here.", "See `Staff/pay.pdf`.", "See /Staff/pay.pdf here.",
                         "See %s/Staff/pay.pdf here." % name, "See Other/Staff/pay.pdf here."):
                self.assertEqual({c[2] for c in self.appended(page, text + "\n")}, {"excluded"}, text)
        for form, text in {"an unknown longer path": "See Other/Scan 1.pdf here.",
                           "a web address": "See https://example.org/Scan 1.pdf here.",
                           "the folder's name as a live document is not": "See Archive/%s/Scan 1.pdf here." % name}.items():
            with self.subTest(unexplained=form):
                self.assertEqual([c[2] for c in self.appended(page, text + "\n")], ["migrations"], text)

    def test_a_document_moved_by_a_round_and_then_staged_is_withheld_at_the_path_it_started_at(self):
        """`04 Study/Notes.rtf` is moved to `04 Study/Class notes.rtf`, then staged from there. The audits that saw it do
        the work: the first placement must be in `rename_history`, or the page that still cites the first path passes
        (the manifest here is one an audit made before it recorded the first placement)."""
        man = os.path.join(self.root, "_Audit", "manifest.json")
        m = json.loads(read(man))
        for e in m["entries"].values():
            e["rename_history"] = []
        write(man, json.dumps(m))
        audit = lambda: self.assertEqual(run("audit.py", "--root", self.root, "--work", self.work)[0], 0)
        os.rename(os.path.join(self.root, "04 Study", "Notes.rtf"), os.path.join(self.root, "04 Study", "Class notes.rtf"))
        audit()
        staged = os.path.join(self.root, "_Migrations", "Other Project", "04 Study")
        os.makedirs(staged)
        os.rename(os.path.join(self.root, "04 Study", "Class notes.rtf"), os.path.join(staged, "Class notes.rtf"))
        audit()
        page = "40 Study/40 Study.md"
        self.base = {page: read(self.page(page))}
        for cited in ("04 Study/Notes.rtf", "04 Study/Class notes.rtf"):
            with self.subTest(cited=cited):
                found = self.appended(page, "The notes are `%s`.\n" % cited)
                self.assertIn("migrations", [c[2] for c in found])
                self.assertIn(len(self.base[page].split("\n")) + 1, [c[1] for c in found])
        self.appended(page, "The notes are `04 Study/Notes.rtf`.\n")  # the page now cites only the first path, A
        code, out, err = self.wiki("review-prompts", "--page", page, "--author-model", "a", "--reviewer-model", "b",
                                   "--out", os.path.join(self.tmp, "q"))
        self.assertEqual(code, 2, out + err)
        self.assertIn("refused to render 1 page(s) that cite a withheld document", err)
        self.assertNotIn("Notes.rtf", err)

    def test_the_paths_a_withheld_document_held_before_it_moved_are_withheld_for_check_and_for_drift(self):
        man = os.path.join(self.root, "_Audit", "manifest.json")
        m = json.loads(read(man))
        contract = next(e for e in m["entries"].values() if e["current_path"] == "06 Work/Contract.docx")
        contract["rename_history"] = [{"path": "Drafts/Contract draft.docx", "at": "2024-01-01T00:00:00Z", "run_id": "x"},
                                      {"path": "06 Work/Contract.docx", "at": "2024-02-01T00:00:00Z", "run_id": "y"}]
        write(man, json.dumps(m))
        self.exclude("06 Work")
        page = "40 Study/40 Study.md"
        self.base = {page: read(self.page(page))}
        found = self.appended(page, "The draft is `Drafts/Contract draft.docx`.\n")
        self.assertEqual([c[2] for c in found], ["excluded"])
        code, out, err = self.wiki("drift")
        self.assertEqual(code, 1, out + err)
        cited = json.loads(out)["departed"]
        self.assertEqual([c[:1] + c[2:] for c in cited if c[0] == page], [[page, "withheld (excluded)"]])
        self.assertNotIn("Contract draft", out, "drift names a path an excluded document held")
        # a live document that is not withheld holds that path now: it names that document, not the withheld one
        m["entries"]["e" * 64] = {"id": "e" * 64, "current_path": "Drafts/Contract draft.docx", "class": "document",
                                  "hashed": True, "flags": [], "copies": [], "size": 1, "mtime": "2024-06-01T00:00:00Z"}
        write(man, json.dumps(m))
        self.assertEqual(self.appended(page, "The draft is `Drafts/Contract draft.docx`.\n"), [])

    def appended(self, page, text):
        """The check's `cites_withheld` entries for `page` after `text` is added to the end of its text."""
        write(self.page(page), self.base[page] + "\n" + text)
        return [c for c in self.check()["cites_withheld"] if c[0] == page]

    def test_a_withheld_document_wrapped_across_lines_at_any_point_is_a_citation(self):
        """Only the one file is excluded, so the folder `06 Work` is not withheld and naming it is no citation: the
        page is caught by the whole path, joined however the line was broken. The Log may name a folder, never a file."""
        self.exclude("06 Work/Contract.docx")
        self.base = {p: read(self.page(p)) for p in ("40 Study/40 Study.md", self.LOG)}
        wraps = {"after the slash": "The contract is 06 Work/\nContract.docx, signed in May.\n",
                 "before the slash": "The contract is 06 Work\n/Contract.docx, signed in May.\n",
                 "inside the folder name": "The contract is 06 Wo\nrk/Contract.docx, signed in May.\n",
                 "inside the file name": "The contract is 06 Work/Contr\nact.docx, signed in May.\n",
                 "before the extension": "The contract is 06 Work/Contract\n.docx, signed in May.\n",
                 "indented in a list": "- The contract is 06 Work/\n  Contract.docx, signed in May.\n",
                 "in a quotation": "> The contract is 06 Work/\n> Contract.docx, signed in May.\n",
                 "over three lines": "The contract is 06\nWork/\nContract.docx, signed in May.\n"}
        for page in self.base:
            for name, text in wraps.items():
                with self.subTest(page=page, wrap=name):
                    self.assertEqual([c[2] for c in self.appended(page, text)], ["excluded"])
            with self.subTest(page=page, wrap="a longer name"):
                self.assertEqual(self.appended(page, "The contract is 06 Work/\nContract.docx2 and more.\n"), [])
        self.assertEqual(self.appended("40 Study/40 Study.md", "Work and 06 Work/\nOther.docx are not it.\n"), [])

    def test_a_withheld_path_spelt_with_dots_doubled_slashes_or_escapes_is_the_same_path(self):
        self.exclude("06 Work/Contract.docx")
        self.base = {"40 Study/40 Study.md": read(self.page("40 Study/40 Study.md"))}
        page = "40 Study/40 Study.md"
        spellings = {"a dot segment": "See `06 Work/./Contract.docx`.", "a doubled slash": "See `06 Work//Contract.docx`.",
                     "a parent segment": "See `06 Work/Other/../Contract.docx`.",
                     "a leading dot": "See `./06 Work/Contract.docx`.", "percent escapes": "See `06%20Work/Contract.docx`.",
                     "escaped twice": "See `06%2520Work/Contract.docx`.",
                     "in plain text": "See 06 Work/./Contract.docx for it.", "in a fence": "```\n06 Work//Contract.docx\n```",
                     "a backslash": "See `06 Work\\Contract.docx`."}
        for name, text in spellings.items():
            with self.subTest(name):
                self.assertEqual([c[2] for c in self.appended(page, text)], ["excluded"])

    def test_a_link_to_a_withheld_document_of_any_kind_spelt_any_way_is_a_citation(self):
        """A link's target is resolved from the page (`../` goes up), decoded, normalised and folded, for a file of any
        extension, an angle-bracketed target, a reference definition and a folder."""
        page = "40 Study/40 Study.md"
        links = {"a docx": ("06 Work/Contract.docx", "[c](../06%20Work/Contract.docx)"),
                 "a dot segment": ("06 Work/Contract.docx", "[c](../06%20Work/./Contract.docx)"),
                 "doubled escapes": ("06 Work/Contract.docx", "[c](../06%2520Work/Contract.docx)"),
                 "an angle target": ("06 Work/Contract.docx", "[c](<../06 Work//Contract.docx> \"the contract\")"),
                 "a reference": ("06 Work/Contract.docx", "[c]: ../06 work/CONTRACT.docx"),
                 "from the folder root": ("06 Work/Contract.docx", "[c](06%20Work/Contract.docx)"),
                 "up and down": ("06 Work/Contract.docx", "[c](../40%20Study/../06%20Work/Contract.docx)"),
                 "a folder": ("06 Work", "[w](../06%20Work)"),
                 "a folder with a slash": ("06 Work", "[w](../06%20Work/)")}
        self.base = {page: read(self.page(page))}
        for name, (excluded, link) in links.items():
            with self.subTest(name):
                self.exclude(excluded)
                self.assertEqual([c[2] for c in self.appended(page, "See " + link + ".")], ["excluded"])
        self.exclude("06 Work/Contract.docx")
        self.assertEqual(self.appended(page, "See [c](../06%20Work/Other.docx) and [d](../06%20Work/Contract.docx2).\n"),
                         [], "a link to other files")

    def test_a_sources_entry_spelt_in_another_case_is_dead(self):
        """It opens the file on macOS, so a test of existence would pass for it."""
        edit(self.page(TAX), '  - "06 Work/Contract.docx"', '  - "06 work/Contract.docx"')
        self.assertEqual(self.check()["dead_source_paths"], [[TAX, "06 work/Contract.docx"]])

    def test_a_chart_whose_source_is_excluded_is_a_problem(self):
        res = self.cites("03 Home/Lease renewal.pdf")
        self.assertEqual(len(res["chart_sources_bad"]), 1)
        self.assertEqual(res["chart_sources_bad"][0][0], "30 Home/30 Home.md")

    def test_a_chart_whose_source_is_a_copy_of_an_excluded_document_is_a_problem(self):
        """`04 Study/Essay.docx` is an included path, but a copy of the excluded `06 Work/Essay.docx`: the figures of a
        chart drawn from it come from a document the tools may not read, and the chart's source cell is judged by the
        chart rule, so only the chart check can refuse it."""
        edit(self.page("30 Home/30 Home.md"), "Lease renewed to 2025-04-30 | `03 Home/Lease renewal.pdf`",
             "Lease renewed to 2025-04-30 | `04 Study/Essay.docx`")
        self.assertEqual(self.check()["chart_sources_bad"], [], "not withheld yet")
        res = self.cites("06 Work")
        self.assertEqual([c[0] for c in res["chart_sources_bad"]], ["30 Home/30 Home.md"])

    def test_a_scoped_check_reports_the_citations_of_its_pages_only(self):
        self.exclude("06 Work")
        self.assertEqual(len(self.check("--page", TAX)["cites_withheld"]), 3)
        self.assertEqual(self.check("--page", "00 Index/00 Index.md")["cites_withheld"], [])

    def test_live_top_folders(self):
        man = {"a": {"current_path": "07 Old/x.pdf", "flags": ["departed"], "copies": [{"path": "09 Gone/x.pdf"}]},
               "b": {"current_path": "01 A/y.pdf", "flags": [], "copies": [{"path": "08 C/y.pdf"}]},
               "c": {"current_path": "z.pdf", "flags": []}}
        self.assertEqual(wiki.live_top_folders(man), {"01 A", "08 C"})

    def test_a_link_to_a_planned_page_is_dead(self):
        os.remove(self.page("40 Study/40 Study.md"))
        res = self.check()
        self.assertIn(["00 Index/00 Index.md", "../40%20Study/40%20Study.md"], res["dead_page_links"])
        self.assertEqual(res["links_outside_page_map"], [])

    def test_a_drafting_agents_check_is_scoped_to_its_pages(self):
        """Sections are drafted in parallel: an agent is answerable for its own pages, and a link to a page the map
        plans but a sibling has not written yet is pending, not dead."""
        os.remove(self.page("40 Study/40 Study.md"))
        write(self.page(TAX), read(self.page(TAX)) + "\nA dash \u2014 here.\n")
        index = "00 Index/00 Index.md"
        res = self.check("--page", index)
        self.assertEqual((res["problems"], res["dead_page_links"], res["em_dash_lines"]), (0, [], 0))
        self.assertEqual(res["links_to_planned_pages"], [[index, "../40%20Study/40%20Study.md"]])
        self.assertEqual((res["scoped_to"], res["frontmatter_conforming"]), ([index], "1/1"))
        for key in ("documents_not_covered", "rationale", "acceptance"):
            self.assertTrue(res[key].startswith("not checked: scoped to 1 page(s)"), key)
        res = self.check("--page", TAX)
        self.assertEqual((res["problems"], res["em_dash_where"][0][0]), (1, TAX))
        res = self.check()
        self.assertIn([index, "../40%20Study/40%20Study.md"], res["dead_page_links"])
        self.assertNotIn("links_to_planned_pages", res)
        self.assertIn("is not a page in", self.refused("check", "--page", "40 Study/40 Study.md"))

    def test_a_scoped_check_never_opens_a_siblings_page(self):
        with open(self.page(TAX), "wb") as f:
            f.write(b"\xff\xfe half written by another agent")
        res = self.check("--page", "00 Index/00 Index.md")
        self.assertEqual((res["problems"], res["frontmatter_conforming"]), (0, "1/1"))

    def test_a_path_given_that_does_not_exist_is_refused(self):
        for flag in ("--rationale", "--acceptance"):
            with self.subTest(flag=flag):
                self.assertIn("does not exist", self.refused("check", flag, os.path.join(self.tmp, "none")))

    def test_a_path_under_no_live_folder_is_counted_unchecked(self):
        edit(self.page("30 Home/30 Home.md"), "Alex rents", "The vet's bill is `07 Pets/Vet bill.pdf`.\n\nAlex rents")
        res = self.check()
        self.assertEqual((res["problems"], res["backticked_paths_unchecked"]), (0, 2))

    def test_a_pattern_in_a_path_is_judged_up_to_the_pattern(self):
        """A routing pattern names folders that exist; only the part a pattern stands in for cannot be told."""
        edit(self.page("30 Home/30 Home.md"), "Alex rents", "Statements go to `02 Finance/Statement*/` and "
             "`02 Finance/<year>/x.pdf`; scans to `02 Finance/Gone/*.pdf`.\n\nAlex rents")
        res = self.check()
        self.assertEqual(res["dead_source_paths"], [["30 Home/30 Home.md", "02 Finance/Gone/*.pdf"]])
        self.assertEqual(res["backticked_paths_unchecked"], 3)

    HOME = "30 Home/30 Home.md"
    NAMES_WITH_SPECIALS = ("02 Finance/Statement [final].pdf", "02 Finance/Tax [2024]/Return.pdf",
                           "02 Finance/What?.pdf")

    def cite(self, *spans):
        edit(self.page(self.HOME), "Alex rents", "Cited: %s.\n\nAlex rents" % ", ".join("`%s`" % s for s in spans))

    def test_a_dead_path_whose_name_holds_brackets_or_a_question_mark_is_dead(self):
        """File and folder names carry `[`, `]` and `?`, so one that is missing is a dead path, never an unchecked
        pattern: reading it as a pattern let three dead paths through as problems: 0."""
        self.cite(*self.NAMES_WITH_SPECIALS)
        res = self.check()
        self.assertEqual(res["dead_source_paths"], [[self.HOME, s] for s in self.NAMES_WITH_SPECIALS])
        self.assertEqual((res["problems"], res["backticked_paths_unchecked"]), (3, 1))  # the Schema's `_Inbox/`

    def test_a_file_whose_name_holds_brackets_or_a_question_mark_resolves(self):
        for rel in self.NAMES_WITH_SPECIALS:
            write(os.path.join(self.root, *rel.split("/")), "x")
        self.cite(*self.NAMES_WITH_SPECIALS)
        res = self.check()
        self.assertEqual((res["problems"], res["dead_source_paths"], res["backticked_paths_unchecked"]), (0, [], 1))

    def test_a_name_with_brackets_or_a_question_mark_is_never_read_as_a_pattern(self):
        """A stale citation after a tidy that strips brackets is what the check exists to catch: `Invoice [3].pdf`
        is not `Invoice 3.pdf`, `What?.pdf` is not `Whatx.pdf`, and a folder that is gone is not `Tax 2/`."""
        for rel in ("02 Finance/Invoice 3.pdf", "02 Finance/Whatx.pdf", "02 Finance/Tax 2/Return.pdf"):
            write(os.path.join(self.root, *rel.split("/")), "x")
        spans = ("02 Finance/Invoice [3].pdf", "02 Finance/What?.pdf", "02 Finance/Tax [2024]/*.pdf")
        self.cite(*spans)
        res = self.check()
        self.assertEqual(sorted(res["dead_source_paths"]), sorted([self.HOME, s] for s in spans))
        self.assertEqual((res["problems"], res["backticked_paths_unchecked"]), (3, 1))

    NAMES_WITH_ANGLES = ("02 Finance/Q1 <draft.pdf", "02 Finance/Rate > 5.pdf", "02 Finance/Fees > 5 < 10/Return.pdf")

    def test_a_lone_angle_bracket_in_a_name_is_literal_and_a_missing_one_is_dead(self):
        """Only a whole `<name>` stands in for a value: `<` or `>` alone is a character in a file's name."""
        self.cite(*self.NAMES_WITH_ANGLES)
        res = self.check()
        self.assertEqual(sorted(res["dead_source_paths"]), sorted([self.HOME, s] for s in self.NAMES_WITH_ANGLES))
        self.assertEqual((res["problems"], res["backticked_paths_unchecked"]), (3, 1))

    def test_a_file_whose_name_holds_a_lone_angle_bracket_resolves(self):
        for rel in self.NAMES_WITH_ANGLES:
            write(os.path.join(self.root, *rel.split("/")), "x")
        self.cite(*self.NAMES_WITH_ANGLES)
        res = self.check()
        self.assertEqual((res["problems"], res["dead_source_paths"], res["backticked_paths_unchecked"]), (0, [], 1))

    def test_a_whole_placeholder_is_a_pattern_whatever_stands_in_for_it(self):
        write(os.path.join(self.root, "02 Finance", "2024", "x.pdf"), "x")
        self.cite("02 Finance/<year>/x.pdf", "02 Finance/<year>/gone.pdf", "02 Finance/Gone/<year>/x.pdf",
                  "02 Finance/Q<n>.pdf")
        res = self.check()
        self.assertEqual(res["dead_source_paths"], [[self.HOME, "02 Finance/Gone/<year>/x.pdf"]])
        self.assertEqual(res["backticked_paths_unchecked"], 4)  # the three that name an existing folder, and `_Inbox/`

    def test_a_star_pattern_is_found_when_something_matches_and_dead_when_its_folder_is_gone(self):
        write(os.path.join(self.root, "02 Finance", "Tax [2024]", "Return.pdf"), "x")
        self.cite("02 Finance/*.pdf", "02 Finance/Tax [2024]/*.pdf", "02 Finance/Statement*/",
                  "02 Finance/Gone/*.pdf", "02 Finance/Tax [2023]/*.pdf")
        res = self.check()
        self.assertEqual(res["dead_source_paths"], [[self.HOME, "02 Finance/Gone/*.pdf"],
                                                    [self.HOME, "02 Finance/Tax [2023]/*.pdf"]])
        # unchecked: the Schema's `_Inbox/`, and `Statement*/`, whose folders exist but which nothing matches
        self.assertEqual(res["backticked_paths_unchecked"], 2)

    def test_the_schema_routing_covers_no_document(self):
        edit(self.page("40 Study/40 Study.md"), "| `04 Study/` | 5 | certificates, slides, essay, notes |\n", "")
        res = self.check()
        self.assertEqual(res["not_covered_sample"], ["04 Study/Notes.rtf", "04 Study/Slides.pptx"])
        self.assertIn("`04 Study/`", read(self.page("90 Schema/90 Schema.md")))

    def test_without_a_compiled_schema_the_professionals_are_not_verified(self):
        os.remove(os.path.join(self.root, ".familyai", "wiki-schema.json"))
        edit_block(self.root, "20 Finance/Cash position.md", lambda ls: ls[:1] + [
            ls[1].replace("Professional lens: CFO;", "Professional lens: private banker;")] + ls[2:])
        res = self.check()
        self.assertEqual(res["problems"], 0)
        for got in (res["pages_without_single_professional"], res["rationale"]["professional_not_named"]):
            self.assertTrue(got.startswith("not verified: no compiled Schema"), got)
        self.assertEqual(len(res["acceptance_not_verified"]), 12)  # every page, and no problem

    def test_without_a_rationale_file(self):
        os.remove(os.path.join(self.root, RATIONALE))
        res = self.check()
        self.assertEqual((res["rationale"], res["problems"]), ("not recorded", 0))
        other = os.path.join(self.tmp, "rationale.md")
        write(other, read(os.path.join(FIXTURE, RATIONALE)))
        self.assertEqual(self.check("--rationale", other)["rationale"]["blocks"], 12)

    def test_check_and_move_agree_on_which_links_are_local(self):
        finance = self.page("20 Finance/20 Finance.md")
        edit(finance, "- [Tax](Tax.md)", '[a](/etc/x.md) [b](obsidian://open?vault=x&file=y.md) [c](mailto:a@b.md) '
             '[e](Nope.md) [d](Tax.md "t")\n\n- [Tax](Tax.md)')
        dead = [["20 Finance/20 Finance.md", "Nope.md"]]
        res = self.check()
        self.assertEqual((res["dead_page_links"], res["links_outside_page_map"], res["problems"]), (dead, [], 1))
        self.assertEqual(wiki.LINK.findall('[d](Tax.md "t") [f](A.md#x \'y\')'),
                         [("Tax.md", "", ' "t"'), ("A.md", "#x", " 'y'")])
        moves = os.path.join(self.tmp, "map.json")
        write(moves, json.dumps({"40 Study/40 Study.md": "40 Study/Courses.md"}))
        moved = json.loads(self.ok("move", "--map", moves, code=1))
        self.assertEqual(moved["dead_links"], dead)
        write(moves, json.dumps({TAX: "20 Finance/Tax and returns.md"}))
        moved = json.loads(self.ok("move", "--map", moves, code=1))
        self.assertEqual((moved["dead_links"], moved["schema_rows_to_update"]),
                         (dead, [[TAX, "20 Finance/Tax and returns.md"]]))
        self.assertIn('[e](Nope.md) [d](Tax%20and%20returns.md "t")', read(finance))
        self.assertEqual(self.check()["dead_page_links"], dead)

    def test_chart_parts(self):
        def kinds(body):
            return [(c["type"], c["kind"]) for c in wiki.chart_parts("```mermaid\n%s```\n" % body)]
        self.assertEqual(kinds("xychart-beta\n    bar [1, 2, 3]\n"), [("xychart-beta", "bar")])
        self.assertEqual(kinds("xychart-beta\n    line [1, 2, 3]\n"), [("xychart-beta", "line")])
        self.assertEqual(kinds("xychart-beta\n    bar [1, 2, 3]\n    line [1, 2, 3]\n"), [("xychart-beta", None)])
        self.assertEqual(kinds("%%{init: {}}%%\npie title x\n"), [("pie", "pie")])
        self.assertEqual(kinds("sequenceDiagram\n"), [("sequenceDiagram", None)])
        self.assertEqual(kinds(""), [(None, None)])
        self.assertEqual(wiki.chart_parts("```python\nprint(1)\n```\n"), [])


# ------------------------------------------------------------------------------------ rationale

class RationaleTest(Copy):
    def returns(self, groups, as_list=False):
        """A directory of drafters' returns (or one file holding a list of them), one return per group of
        pages; returns its path."""
        blocks = blocks_of(read(os.path.join(FIXTURE, RATIONALE)))
        rets = []
        for g in groups:  # the shape `brief` asks drafters for, each page's rationale block filled in
            ret = json.loads(wiki.return_shape(g))
            for entry in ret["pages"]:
                entry["rationale"] = blocks[entry["path"]] + "\n"
            rets.append(ret)
        path = os.path.join(self.tmp, "returns%d" % len(os.listdir(self.tmp)))
        if as_list:
            write(path + ".json", json.dumps(rets, ensure_ascii=False))
            return path + ".json"
        for i, r in enumerate(rets):
            write(os.path.join(path, "section-%d.json" % i), json.dumps(r, ensure_ascii=False))
        return path

    def pages(self):
        return sorted(blocks_of(read(os.path.join(FIXTURE, RATIONALE))))

    def test_rebuilds_the_fixture_file_byte_for_byte(self):
        pages = self.pages()
        fixture = read(os.path.join(FIXTURE, RATIONALE), "rb")
        out = os.path.join(self.tmp, "a.md")
        res = json.loads(self.ok("rationale", "--returns", self.returns([pages[7:], pages[:3], pages[3:7]]),
                                 "--out", out))
        self.assertEqual(res, {"blocks": 12, "pages_without_block": [], "blocks_without_page": []})
        self.assertEqual(read(out, "rb"), fixture)
        again = os.path.join(self.tmp, "b.md")
        self.ok("rationale", "--returns", self.returns([pages[::-1][:5], pages[::-1][5:]], as_list=True),
                "--out", again)
        self.assertEqual(read(again, "rb"), fixture)
        os.remove(os.path.join(self.root, RATIONALE))
        self.ok("rationale", "--returns", self.returns([pages]))
        self.assertEqual(read(os.path.join(self.root, RATIONALE), "rb"), fixture)

    def test_a_page_left_out_exits_1(self):
        pages = [p for p in self.pages() if p != "40 Study/40 Study.md"]
        out = os.path.join(self.tmp, "a.md")
        res = json.loads(self.ok("rationale", "--returns", self.returns([pages]), "--out", out, code=1))
        self.assertEqual(res["pages_without_block"], ["40 Study/40 Study.md"])
        self.assertEqual(self.check("--rationale", out)["rationale"]["pages_without_block"], ["40 Study/40 Study.md"])

    def test_refusals(self):
        pages = self.pages()
        blocks = blocks_of(read(os.path.join(FIXTURE, RATIONALE)))
        bad = {
            "four lines": (TAX, "\n".join(blocks[TAX].split("\n")[:5]), "4 lines under the heading, not 5"),
            "another heading": (TAX, blocks[TAX].replace("### 20 Finance/Tax.md", "### 20 Finance/Taxes.md"),
                                "not '### 20 Finance/Tax.md'"),
            "a blank line inside": (TAX, blocks[TAX].replace("\n- Shape", "\n\n- Shape"), "6 lines"),
            "no block": (TAX, None, "no rationale block"),
            "not a page path": ("../Tax.md", blocks[TAX].replace(TAX, "../Tax.md"), "not a page path"),
        }
        for name, (path, text, why) in bad.items():
            with self.subTest(name=name):
                src = os.path.join(self.tmp, name + ".json")
                entry = {"path": path, "text": ""}
                if text is not None:
                    entry["rationale"] = text
                write(src, json.dumps({"pages": [entry]}))
                self.assertIn(why, self.refused("rationale", "--returns", src, "--out",
                                                os.path.join(self.tmp, "x.md")))
        twice = self.returns([pages, [TAX]])
        self.assertIn("page returned twice", self.refused("rationale", "--returns", twice, "--out",
                                                          os.path.join(self.tmp, "x.md")))
        write(os.path.join(self.tmp, "shape.json"), json.dumps({"page": TAX}))
        self.assertIn('an object with a "pages" list', self.refused(
            "rationale", "--returns", os.path.join(self.tmp, "shape.json"), "--out", os.path.join(self.tmp, "x.md")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "x.md")))

    def test_read_only_root(self):
        before = tree_digest(self.root)
        returns = self.returns([self.pages()])
        self.assertIn("--read-only-root", self.refused("rationale", "--returns", returns, "--read-only-root"))
        self.ok("rationale", "--returns", returns, "--read-only-root", "--out", os.path.join(self.tmp, "r.md"))
        self.assertEqual(tree_digest(self.root), before)


# ------------------------------------------------------------------------------------ review prompts

class ReviewPromptsTest(Copy):
    def prompts(self, *pages, out=None, code=0, models=("model-a", "model-b"), root=None):
        args = [x for p in pages for x in ("--page", p)]
        args += ["--author-model", models[0], "--reviewer-model", models[1]]
        args += ["--out", out] if out else []
        return json.loads(self.ok("review-prompts", *args, code=code, root=root))

    def assert_filled(self, text, page):
        """Every field filled: no brace left outside the page's text and the JSON reply shape."""
        rest = re.sub(r"```json\n.*?```", "", text.replace(read(self.page(page)), ""), flags=re.S)
        self.assertNotIn("{", rest)
        self.assertNotIn("}", rest)

    def texts(self, out):
        return {os.path.relpath(os.path.join(d, f), out): read(os.path.join(d, f), "rb")
                for d, _ds, fs in os.walk(out) for f in fs}

    def test_byte_stable(self):
        a, b = os.path.join(self.tmp, "a-prompts"), os.path.join(self.tmp, "b-prompts")
        res = self.prompts(TAX, "00 Index/00 Index.md", out=a)
        self.assertEqual(res["prompts"], [["00 Index/00 Index.md", os.path.join(a, "00 Index", "00 Index.owner.md"),
                                           os.path.join(a, "00 Index", "00 Index.professional.md")],
                                          [TAX, os.path.join(a, "20 Finance", "Tax.owner.md"),
                                           os.path.join(a, "20 Finance", "Tax.professional.md")]])
        self.prompts("00 Index/00 Index.md", TAX, TAX, out=b)
        first = self.texts(a)
        self.assertEqual(sorted(first), ["00 Index/00 Index.owner.md", "00 Index/00 Index.professional.md",
                                         "20 Finance/Tax.owner.md", "20 Finance/Tax.professional.md"])
        self.assertEqual(self.texts(b), first)
        other = make_copy(os.path.join(self.tmp, "b"))
        c = os.path.join(self.tmp, "c-prompts")
        self.prompts(TAX, "00 Index/00 Index.md", out=c, root=other)
        self.assertEqual({k: v.replace(other.encode(), self.root.encode()) for k, v in self.texts(c).items()}, first)
        self.prompts(TAX)
        self.assertTrue(os.path.exists(os.path.join(self.work, "reviews", "20 Finance", "Tax.owner.md")))

    def test_owner_prompt(self):
        out = os.path.join(self.tmp, "p")
        self.prompts(TAX, out=out)
        text = read(os.path.join(out, "20 Finance", "Tax.owner.md"))
        for part in ("# Owner review: 20 Finance/Tax.md", "**Pen:** you, model-b, a model that did not write this "
                     "page\n(model-a wrote it), reading it as Alex.",
                     "1. Is anything due?\n2. What came in and went out?\n3. What is the tax position?",
                     "(sha256 `%s`)" % self.sha(TAX), "```markdown\n" + read(self.page(TAX)) + "```\n",
                     '"page_sha256": "%s"' % self.sha(TAX)):
            self.assertIn(part, text)
        self.assert_filled(text, TAX)
        self.prompts("30 Home/30 Home.md", out=out)  # a page holding a fence is fenced by a longer one
        home = read(os.path.join(out, "30 Home", "30 Home.owner.md"))
        self.assertIn("````markdown\n" + read(self.page("30 Home/30 Home.md")) + "````\n", home)
        self.assert_filled(home, "30 Home/30 Home.md")

    def test_professional_prompt_and_its_facts(self):
        out = os.path.join(self.tmp, "p")
        self.prompts(TAX, out=out)
        text = read(os.path.join(out, "20 Finance", "Tax.professional.md"))
        for part in ("reading it as chartered tax adviser.",
                     "- Professional: chartered tax adviser (the page's row in the Page professionals table)",
                     "- Deliverable: annual tax position letter\n- Tone: exact, dated\n- Reader: Alex",
                     "- Fields every page carries: account, period, balances, tax year, amounts",
                     "- Section: 20 Finance, active", "  - `06 Work/`: 20 Tax (employment income)",
                     "The folder is `%s`" % self.root, "5 of 7 facts from the cards"):
            self.assertIn(part, text)
        sample = wiki.fact_sample(TAX, TAX_FACTS, 5)
        kinds = {"dates": "date", "amounts": "amount", "reference_numbers": "reference number"}
        listed = "\n".join("%d. `%s`, %s: %s" % (i, p, kinds[k], v) for i, (p, k, v) in enumerate(sample, 1))
        self.assertIn("\n\n" + listed + "\n\n## Judge", text)
        self.assert_filled(text, TAX)

    def test_sources_list(self):
        out = os.path.join(self.tmp, "p")
        self.prompts(TAX, "40 Study/40 Study.md", "20 Finance/Bank accounts.md", out=out)
        tax = read(os.path.join(out, "20 Finance", "Tax.professional.md"))
        self.assertIn("\n\n- `02 Finance/Tax/Budget.numbers`: no card\n"
                      "- `02 Finance/Tax/Tax return 2023.pdf`: Tax return 2022 to 2023\n"
                      "- `06 Work/Contract.docx`: Employment contract\n"
                      "- `06 Work/Essay.docx`: Essay: why learn a third language\n\n", tax)
        study = read(os.path.join(out, "40 Study", "40 Study.professional.md"))
        self.assertIn("- `04 Study/`: a folder, 5 files directly in it\n- `04 Study/Cours de français.pdf`: no card",
                      study)
        self.assertIn("- `05 Archive/`: a folder, 4 files directly in it", study)
        self.assertIn("0 of 0 facts", study)
        self.assertIn("None: no card of a document the page cites holds a date", study)
        bank = read(os.path.join(out, "20 Finance", "Bank accounts.professional.md"))
        self.assertIn("- `02 Finance/Bank statement 2024-03 (1).pdf`: no card, a copy of "
                      "`02 Finance/Bank statement 2024-03.pdf`", bank)

    def test_a_folder_cited_without_its_trailing_slash(self):
        write(self.page(TAX), read(self.page(TAX)) + "\nThe working papers are in `02 Finance/Tax`.\n")
        out = os.path.join(self.tmp, "p")
        self.prompts(TAX, out=out)
        tax = read(os.path.join(out, "20 Finance", "Tax.professional.md"))
        self.assertRegex(tax, r"- `02 Finance/Tax`: a folder, \d+ files? directly in it")
        self.assertNotIn("`02 Finance/Tax`: not a document or folder", tax)

    OTHER = "_Migrations/Other Project/02 Finance/Old invoice.pdf"

    def withhold(self, *excluded, cite=(), card_for=None):
        """The rulebook `exclude`s `excluded`; the Tax page cites `cite` as well; `card_for` (a path) is given a card
        with a title and key facts, as a document carded before it was staged or excluded would have."""
        twin = os.path.join(self.root, ".familyai", "rulebook.json")
        write(twin, json.dumps(dict(json.loads(read(twin)), exclude=list(excluded)), ensure_ascii=False, indent=1))
        if cite:
            write(self.page(TAX), read(self.page(TAX)) + "\n" + "".join("Also see `%s`.\n" % c for c in cite))
        if card_for:
            ids = {e["current_path"]: h for h, e in json.loads(read(MANIFEST))["entries"].items()}
            write(os.path.join(self.root, "_Audit", "cards", ids[card_for] + ".json"), json.dumps(
                {"id": ids[card_for], "title": "Invoice 2022-117 from the other project", "key_facts": {
                    "dates": ["2022-03-01"], "amounts": ["GBP 800.00"], "reference_numbers": ["INV 2022/117"]}}))

    def review(self, page=TAX):
        """The professional prompt of `page`, and the command's output."""
        out = os.path.join(self.tmp, "p")
        res = self.prompts(page, out=out)
        return read(os.path.join(out, *(page[:-3] + ".professional.md").split("/"))), res

    @staticmethod
    def sections(prompt):
        """The model-facing parts built from the manifest and the cards: the scope, the sources and the facts."""
        scope = prompt.split("## Its scope")[1].split("## The page")[0]
        return scope + prompt.split("## Its sources")[1].split("## Judge")[0]

    def sources_of(self, text, *excluded):
        """`page_sources` for `text` against the fixture's manifest and cards, with the rulebook excluding `excluded`: the
        defence of the prompt itself, whatever `review-prompts` lets through."""
        rb = dict(common.DEFAULTS, exclude=list(excluded))
        man = json.loads(read(MANIFEST))["entries"]
        held, at = wiki.held_paths(rb, man)
        return wiki.page_sources(text, man, held, os.path.join(self.root, "_Audit", "cards"), rb, at)

    def test_a_cited_excluded_document_is_named_only_as_withheld(self):
        lines, facts, hidden = self.sources_of("`06 Work/Contract.docx` and `06 Work/Essay.docx`", "06 Work")
        self.assertEqual(lines, ["- `06 Work/Contract.docx`: withheld (excluded); not to be opened, and the page is "
                                 "not checked against it",
                                 "- `06 Work/Essay.docx`: withheld (excluded); not to be opened, and the page is not "
                                 "checked against it"])
        self.assertEqual((facts, hidden), ([], 2), "no card was read: no title, no fact")
        lines, facts, _hidden = self.sources_of("`06 Work/Contract.docx`")  # nothing excluded: its card is read
        self.assertEqual((lines, facts), (["- `06 Work/Contract.docx`: Employment contract"],
                                          [("06 Work/Contract.docx", "amounts", "one month's notice"),
                                           ("06 Work/Contract.docx", "dates", "2022-05-01")]))

    def test_a_cited_document_staged_for_another_project_is_named_only_as_withheld(self):
        ids = {e["current_path"]: h for h, e in json.loads(read(MANIFEST))["entries"].items()}
        write(os.path.join(self.root, "_Audit", "cards", ids[self.OTHER] + ".json"), json.dumps(
            {"id": ids[self.OTHER], "title": "Invoice 2022-117 from the other project", "key_facts": {
                "dates": ["2022-03-01"], "amounts": ["GBP 800.00"], "reference_numbers": ["INV 2022/117"]}}))
        lines, facts, hidden = self.sources_of("`%s`" % self.OTHER)
        self.assertEqual(lines, ["- `%s`: withheld (held for another project); not to be opened, and the page is not "
                                 "checked against it" % self.OTHER])
        self.assertEqual((facts, hidden), ([], 1))

    def test_a_cited_copy_of_a_withheld_document_does_not_name_its_canonical_path(self):
        """06 Work/Essay.docx is the canonical copy: with it excluded, its copy in 05 Archive is as withheld, and the
        line names neither its title nor `06 Work/Essay.docx`."""
        lines, facts, hidden = self.sources_of("`05 Archive/Essay.docx`", "06 Work")
        self.assertEqual(lines, ["- `05 Archive/Essay.docx`: withheld (excluded); not to be opened, and the page is not "
                                 "checked against it"])
        self.assertEqual((facts, hidden), ([], 1))
        lines, _facts, _hidden = self.sources_of("`05 Archive/Essay.docx`")  # not excluded: the old line, with its leak
        self.assertEqual(lines, ["- `05 Archive/Essay.docx`: Essay: why learn a third language, a copy of "
                                 "`06 Work/Essay.docx`"])

    def test_a_cited_withheld_folder_is_named_as_withheld_and_counts_no_file(self):
        lines, _facts, hidden = self.sources_of("`05 Archive/` `_Migrations/Other Project/02 Finance/` `04 Study/`",
                                                "05 Archive")
        self.assertEqual(hidden, 2)
        self.assertEqual(lines[0], "- `04 Study/`: a folder, 5 files directly in it")
        self.assertEqual([x.split(":")[1].strip(" ") .split(";")[0] for x in lines[1:]],
                         ["withheld (excluded)", "withheld (held for another project)"])
        lines, _f, _h = self.sources_of("`05 Archive/`")  # not excluded: the count a withheld folder must not give
        self.assertEqual(lines, ["- `05 Archive/`: a folder, 4 files directly in it"])

    def test_a_placeholder_for_the_migrations_folder_renders_as_withheld(self):
        """The one withheld citation `check` lets stand, since it names no document: the prompt still withholds it."""
        write(self.page(TAX), read(self.page(TAX)).replace("`06 Work/Contract.docx`", "`02 Finance/Tax/Budget.numbers`")
              .replace('  - "06 Work/Contract.docx"\n', "").replace("`06 Work/Essay.docx`", "`_Migrations/<Project>/`"))
        prompt, res = self.review()
        self.assertIn("- `_Migrations/<Project>/`: withheld (held for another project); not to be opened", prompt)
        self.assertEqual(res["withheld_cited"], {TAX: 1})
        self.assertEqual(res["refused"], [])

    def withhold_and_prompt(self, *excluded, cite=(), pages=(TAX, "00 Index/00 Index.md"), out=None):
        self.withhold(*excluded, cite=cite)
        args = [x for p in pages for x in ("--page", p)]
        return self.wiki("review-prompts", *args, "--author-model", "model-a", "--reviewer-model", "model-b",
                         "--out", out or os.path.join(self.tmp, "p"))

    def test_a_page_citing_a_withheld_document_is_refused_by_page_and_line_never_by_path(self):
        out = os.path.join(self.tmp, "p")
        code, stdout, err = self.withhold_and_prompt("06 Work", out=out)
        self.assertEqual(code, 2, stdout + err)
        res = json.loads(stdout)
        lines = [n for n, line in enumerate(read(self.page(TAX)).split("\n"), 1) if "06 Work" in line]
        self.assertEqual(res["refused"], [[TAX, n, "excluded"] for n in lines])
        self.assertEqual([p[0] for p in res["prompts"]], ["00 Index/00 Index.md"], "the other page still renders")
        self.assertIn("refused to render 1 page(s) that cite a withheld document, no prompt written for them: "
                      "%s" % "; ".join("%s line %d" % (TAX, n) for n in lines), err)
        self.assertNotIn("06 Work", err + json.dumps(res["refused"]), "a withheld path is named")
        self.assertNotIn("Contract", err)
        self.assertEqual(sorted(self.texts(out)), ["00 Index/00 Index.owner.md", "00 Index/00 Index.professional.md"])

    def test_a_prompt_written_before_the_page_cited_a_withheld_document_is_removed(self):
        out = os.path.join(self.tmp, "p")
        self.prompts(TAX, out=out)  # carries the title and the facts of the documents the page cites
        self.assertEqual(len(self.texts(out)), 2)
        code, _stdout, err = self.withhold_and_prompt("06 Work", pages=(TAX,), out=out)
        self.assertEqual(code, 2, err)
        self.assertEqual(self.texts(out), {}, "a prompt built from a withheld document's card was left behind")

    def test_every_citation_check_flags_is_refused_and_a_page_it_does_not_flag_renders(self):
        for cite, why in (("05 Archive/Essay.docx", "excluded"), ("05 Archive/", None), ("04 Study/Notes.rtf", None)):
            with self.subTest(cite=cite):
                self.setUp()
                bank = "20 Finance/Bank accounts.md"
                self.withhold("06 Work")
                write(self.page(bank), read(self.page(bank)) + "\nSee `%s`.\n" % cite)
                flagged = self.check()["cites_withheld"]
                code, stdout, err = self.wiki("review-prompts", "--page", bank, "--author-model", "a",
                                              "--reviewer-model", "b", "--out", os.path.join(self.tmp, "q"))
                self.assertEqual(code, 2 if why else 0, stdout + err)
                self.assertEqual([[p, l, w] for p, l, w in flagged if p == bank], json.loads(stdout)["refused"],
                                 "check and review-prompts disagree")

    def test_the_schema_and_the_log_are_not_refused_for_naming_a_withheld_folder(self):
        code, stdout, err = self.withhold_and_prompt("06 Work", pages=("90 Schema/90 Schema.md", "91 Log/91 Log.md"))
        self.assertEqual(code, 0, stdout + err)
        self.assertEqual(json.loads(stdout)["refused"], [])

    def test_the_log_naming_a_withheld_document_is_refused_and_its_prompt_names_none(self):
        log = os.path.join(self.root, WIKI, "91 Log", "91 Log.md")
        write(log, read(log) + "\n- Filed `06 Work/Contract.docx` (the nanny's contract).\n")
        out = os.path.join(self.tmp, "p")
        code, stdout, err = self.withhold_and_prompt("06 Work", pages=("91 Log/91 Log.md", "00 Index/00 Index.md"),
                                                     out=out)
        self.assertEqual(code, 2, stdout + err)
        refused = json.loads(stdout)["refused"]
        self.assertEqual([r[0] for r in refused], ["91 Log/91 Log.md"])
        self.assertNotIn("Contract", err)
        self.assertEqual(sorted(self.texts(out)), ["00 Index/00 Index.owner.md", "00 Index/00 Index.professional.md"])

    def test_the_routes_into_a_withheld_folder_are_not_shown(self):
        self.withhold("06 Work")
        prompt, _res = self.review("20 Finance/Bank accounts.md")
        scope = prompt.split("## Its scope")[1].split("## The page")[0]
        self.assertNotIn("06 Work", scope)
        self.assertIn("  - 1 route to a withheld folder, not shown", scope)
        self.assertIn("  - `02 Finance/`: 20 Bank accounts and Cash position", scope, "a route to an included folder is shown")

    def test_a_folder_holding_one_excluded_file_still_counts_the_others(self):
        before = self.review()[0]
        self.withhold("04 Study/Notes.rtf", cite=["04 Study/"])
        prompt, _res = self.review()
        self.assertRegex(prompt, r"- `04 Study/`: a folder, [34] files? directly in it")
        self.assertIn("04 Study/", prompt)
        self.assertNotIn("withheld", prompt.split("## Its sources")[1].split("04 Study/")[0])

    def test_a_page_citing_nothing_withheld_is_unchanged_and_counts_none(self):
        prompt, res = self.review()
        self.assertEqual(res["withheld_cited"], {})
        self.assertNotIn("withheld", prompt)

    def test_a_file_given_as_the_cards_folder_is_refused(self):
        cards = os.path.join(self.tmp, "cards.json")
        write(cards, "{}")
        err = self.refused("review-prompts", "--page", TAX, "--author-model", "model-a", "--reviewer-model",
                           "model-b", "--cards", cards)
        self.assertIn("is a file, not a folder of card records", err)

    def test_a_document_cited_by_its_copy_too_gives_its_facts_once(self):
        ids = {e["current_path"]: h for h, e in json.loads(read(MANIFEST))["entries"].items()}
        statement = "02 Finance/Bank statement 2024-03.pdf"
        write(os.path.join(self.root, "_Audit", "cards", ids[statement] + ".json"), json.dumps({
            "title": "Statement", "key_facts": {"dates": ["2024-03-31"], "amounts": ["2410.00", "4160.00"],
                                                "reference_numbers": ["12345678"]}}))
        out = os.path.join(self.tmp, "p")
        self.prompts("20 Finance/Bank accounts.md", out=out)
        bank = read(os.path.join(out, "20 Finance", "Bank accounts.professional.md"))
        self.assertIn("- `02 Finance/Bank statement 2024-03 (1).pdf`: Statement, a copy of `%s`" % statement, bank)
        self.assertIn("4 of 4 facts", bank)
        self.assertIn("1. `%s`, amount: 2410.00\n2. `%s`, amount: 4160.00\n3. `%s`, date: 2024-03-31\n"
                      "4. `%s`, reference number: 12345678\n" % ((statement,) * 4), bank)

    def test_a_card_whose_key_facts_are_not_lists_is_refused(self):
        ids = {e["current_path"]: h for h, e in json.loads(read(MANIFEST))["entries"].items()}
        write(os.path.join(self.root, "_Audit", "cards", ids["06 Work/Contract.docx"] + ".json"),
              json.dumps({"title": "Employment contract", "key_facts": {"dates": "2022-05-01"}}))
        err = self.refused("review-prompts", "--page", TAX, "--author-model", "a", "--reviewer-model", "b")
        self.assertIn("key_facts.dates must be a list of text", err)
        saved = wiki.load_card  # page_sources reads only lists, even from a card that reached it unchecked
        self.addCleanup(setattr, wiki, "load_card", saved)
        wiki.load_card = lambda _d, _h: {"title": "t", "key_facts": {"dates": "2022-05-01", "amounts": ["12"]}}
        self.assertEqual(wiki.page_sources("`06 Work/Contract.docx`", {"h": {"current_path": "06 Work/Contract.docx"}},
                                           {"06 Work/Contract.docx": "h"}, "cards", dict(common.DEFAULTS), {})[1],
                         [("06 Work/Contract.docx", "amounts", "12")])

    def test_fixed_page(self):
        out = os.path.join(self.tmp, "p")
        self.prompts("00 Index/00 Index.md", out=out)
        owner = read(os.path.join(out, "00 Index", "00 Index.owner.md"))
        self.assertIn("reading it as the owner.", owner)
        self.assertIn("None in the Schema: the section is fixed", owner)
        prof = read(os.path.join(out, "00 Index", "00 Index.professional.md"))
        self.assertIn("- Professional: chief of staff (the section's one professional)", prof)
        self.assertIn("- Contract: the method's own, as a fixed section", prof)
        self.assertIn("- Files routed to the section: none", prof)

    def test_fact_sample_rule(self):
        facts = [("a", "dates", str(i)) for i in range(10)]
        self.assertEqual(wiki.fact_sample("p.md", facts[:3], 5), facts[:3])
        for page in ("p.md", "q.md", TAX):
            s = int(hashlib.sha256(page.encode()).hexdigest(), 16) % 10
            want = [facts[i] for i in sorted((s + j * 10 // 4) % 10 for j in range(4))]
            self.assertEqual(wiki.fact_sample(page, facts, 4), want)
            self.assertEqual(len(set(want)), 4)
        self.assertNotEqual(wiki.fact_sample("p.md", facts, 4), wiki.fact_sample("q.md", facts, 4))

    def test_refusals(self):
        out = os.path.join(self.tmp, "p")
        err = self.refused("review-prompts", "--page", TAX, "--author-model", "Model-A", "--reviewer-model",
                           " model-a ", "--out", out)
        self.assertIn("refused: the reviewer model", err)
        self.assertIn("not a page in", self.refused("review-prompts", "--page", "20 Finance/Pensions.md",
                                                    "--author-model", "a", "--reviewer-model", "b", "--out", out))
        self.assertIn("never written inside the folder", self.refused(
            "review-prompts", "--page", TAX, "--author-model", "a", "--reviewer-model", "b", "--out",
            os.path.join(self.root, "_Audit", "reviews")))
        edit(self.page("90 Schema/90 Schema.md"),
             "| 20 Finance/20 Finance.md | private banker | finance overview | measured |\n", "")
        compile_schema(self.root, self.work)
        self.assertIn("list the page", self.refused("review-prompts", "--page", "20 Finance/20 Finance.md",
                                                    "--author-model", "a", "--reviewer-model", "b", "--out", out))
        self.assertFalse(os.path.exists(out))


# ------------------------------------------------------------------------------------ accept

class AcceptTest(Copy):
    def reply(self, page, lens, verdict="accepted", findings=(), **extra):
        body = {"page": page, "lens": lens, "verdict": verdict, "findings": list(findings)}
        body.update(extra)
        path = os.path.join(self.tmp, "reply-%d.json" % len(os.listdir(self.tmp)))
        write(path, json.dumps(body, ensure_ascii=False))
        return path

    def accept(self, page, lens, author="model-a", reviewer="model-b", *args, code=0, **reply):
        return self.ok("accept", "--reply", self.reply(page, lens, **reply), "--author-model", author,
                       "--reviewer-model", reviewer, "--date", "2024-06-30", *args, code=code)

    def records(self, path=None):
        return json.loads(read(path or os.path.join(self.root, ACCEPTANCE)))["records"]

    def state(self, res, page):
        return next(s[1:] for s in res["acceptance_pages"] if s[0] == page)

    def test_models_differing_only_in_case_and_spacing_are_one(self):
        self.assertIn("refused, and recorded", self.refused(
            "accept", "--reply", self.reply(TAX, "owner"), "--author-model", "model  a", "--reviewer-model", "Model A"))
        self.assertIn("refused: the reviewer model", self.refused(
            "review-prompts", "--page", TAX, "--author-model", "model\ta", "--reviewer-model", "MODEL A"))

    def test_hand_edited_records_fail_loud(self):
        self.accept(TAX, "owner")
        good = json.loads(read(os.path.join(self.root, ACCEPTANCE)))
        rec = good["records"][0]
        cases = {"a bad sha256": dict(rec, sha256="abc"), "an unknown lens": dict(rec, lens="reader"),
                 "an unknown verdict": dict(rec, verdict="accept"), "an extra key": dict(rec, colour="red"),
                 "no professional": {k: v for k, v in rec.items() if k != "professional"},
                 "a bad contract sha256": dict(rec, contract_sha256=None),
                 "a refusal without its reason": dict(rec, verdict="refused"),
                 "an empty professional": dict(rec, professional=" "),
                 "a professional not text": dict(rec, professional=5)}
        for name, bad in cases.items():
            with self.subTest(case=name):
                write(os.path.join(self.root, ACCEPTANCE), json.dumps({"version": 1, "records": [bad]}))
                self.assertIn("records[0] is not a record", self.refused("check"))
        write(os.path.join(self.root, ACCEPTANCE), json.dumps(dict(good, version=2)))
        self.assertIn("not an acceptance record", self.refused("check"))

    def test_a_loaded_verdict_reviewed_by_its_author_fails_loud(self):
        self.accept(TAX, "owner")
        good = json.loads(read(os.path.join(self.root, ACCEPTANCE)))
        rec = dict(good["records"][0], reviewer_model=" Model-A ")
        write(os.path.join(self.root, ACCEPTANCE), json.dumps(dict(good, records=[rec])))
        self.assertIn("records[0] was reviewed by its author model", self.refused("check"))
        refusal = dict(rec, verdict="refused", reason="the reviewer model is the author model")
        write(os.path.join(self.root, ACCEPTANCE), json.dumps(dict(good, records=[refusal])))
        self.assertEqual(self.state(self.check(), TAX)[0], "refused")

    def test_reviewer_equal_to_author_is_refused_and_recorded(self):
        err = self.refused("accept", "--reply", self.reply(TAX, "owner"), "--author-model", " Model-A ",
                           "--reviewer-model", "model-a", "--date", "2024-06-30")
        self.assertIn("refused, and recorded as refused: the reviewer model 'model-a' is the author model 'Model-A'",
                      err)
        self.assertEqual(self.records(), [{
            "page": TAX, "lens": "owner", "verdict": "refused", "sha256": self.sha(TAX),
            "professional": "chartered tax adviser", "contract_sha256": contract_digest(self.root, "20"),
            "author_model": "Model-A",
            "reviewer_model": "model-a", "date": "2024-06-30", "findings": [],
            "reason": "the reviewer model 'model-a' is the author model 'Model-A'; a page is accepted only by a "
                      "model that did not write it"}])
        res = self.check()
        self.assertEqual((res["problems"], res["acceptance"]), (0, "refused"))
        self.assertEqual(res["acceptance_counts"], {"accepted": 0, "not recorded": 11, "refused": 1})
        self.assertEqual(self.state(res, TAX)[0], "refused")
        self.accept(TAX, "owner")
        self.accept(TAX, "professional")
        res = self.check()
        self.assertEqual((self.state(res, TAX)[0], res["acceptance"]), ("accepted", "not recorded"))

    def test_both_lenses_accept_a_version_until_it_changes(self):
        self.accept(TAX, "owner")
        res = self.check()
        self.assertEqual(self.state(res, TAX), ["not recorded", "professional lens: no verdict"])
        self.accept(TAX, "professional", facts_checked=[{"fact": "UTR 1234567890", "matches": True}])
        res = self.check()
        self.assertEqual(self.state(res, TAX), ["accepted", "both lenses accepted this version"])
        self.assertEqual(res["acceptance_counts"], {"accepted": 1, "not recorded": 11, "refused": 0})
        with open(self.page(TAX), "a", encoding="utf-8") as f:
            f.write("\nThe 2023 to 2024 return is not yet due.\n")
        res = self.check()
        self.assertEqual(self.state(res, TAX), [
            "not recorded", "owner lens: accepted an earlier version; the page changed since; professional lens: "
            "accepted an earlier version; the page changed since"])
        self.assertEqual(res["problems"], 0)

    def test_a_new_contract_or_professional_undoes_acceptance(self):
        schema = self.page("90 Schema/90 Schema.md")
        steps = (("| Alex | 1. Is anything due?", "| Alex | 1. Is anything due now?"),
                 ("| 20 Finance/Tax.md | chartered tax adviser |", "| 20 Finance/Tax.md | tax accountant |"))
        for old, new in steps:
            with self.subTest(change=new):
                self.accept(TAX, "owner")
                self.accept(TAX, "professional")
                self.assertEqual(self.state(self.check(), TAX)[0], "accepted")
                edit(schema, old, new)
                compile_schema(self.root, self.work)
                self.assertEqual(self.state(self.check(), TAX), [
                    "not recorded", "owner lens: accepted under an earlier contract or professional; professional "
                    "lens: accepted under an earlier contract or professional"])
        self.assertEqual(self.records()[-1]["professional"], "chartered tax adviser")
        os.remove(os.path.join(self.root, ".familyai", "wiki-schema.json"))
        self.accept(TAX, "owner", code=2)  # a record names the page's professional, so a Schema is needed

    def test_a_professional_added_for_another_page_changes_no_standing(self):
        self.accept(TAX, "owner")
        self.accept(TAX, "professional")
        schema = self.page("90 Schema/90 Schema.md")
        for old in ("| private banker; CFO; chartered tax adviser | active |",
                    "| 20 Finance (private banker; CFO; chartered tax adviser) |"):
            edit(schema, old, old.replace("chartered tax adviser", "chartered tax adviser; pensions adviser"))
        edit(schema, "| 20 Finance/Tax.md |", "| 20 Finance/Pensions.md | pensions adviser | pension note | plain |\n"
             "| 20 Finance/Tax.md |")
        compile_schema(self.root, self.work)
        ws = json.loads(read(os.path.join(self.root, ".familyai", "wiki-schema.json")))
        self.assertIn("pensions adviser", ws["contracts"][1]["professionals"])
        self.assertEqual(self.state(self.check(), TAX), ["accepted", "both lenses accepted this version"])

    def test_why_an_acceptance_cannot_be_verified(self):
        page = "20 Finance/20 Finance.md"
        self.accept(page, "owner")
        self.accept(page, "professional")
        edit(self.page("90 Schema/90 Schema.md"),
             "| 20 Finance/20 Finance.md | private banker | finance overview | measured |\n", "")
        compile_schema(self.root, self.work)
        res = self.check()
        why = res["pages_without_single_professional"][0][1]
        self.assertIn("list the page", why)
        self.assertEqual((res["acceptance_not_verified"], res["problems"] - len(findings(res))), ([page], 0))
        self.assertEqual(self.state(res, page), [
            "not recorded", "owner lens: accepted, but not verified: %s; professional lens: accepted, but not "
            "verified: %s" % (why, why)])

    def test_a_lock_that_cannot_be_taken_is_named(self):
        import errno
        import fcntl
        from unittest import mock
        import common
        out = os.path.join(self.tmp, "record", "wiki-acceptance.json")
        with mock.patch.object(fcntl, "flock", side_effect=OSError(errno.ENOLCK, os.strerror(errno.ENOLCK))):
            with self.assertRaises(common.ToolError) as caught:
                wiki.append_record(common.Writer(None), out, {"page": TAX})
        self.assertEqual(str(caught.exception), "cannot lock %s.lock: %s; use --out on a local disk"
                         % (out, os.strerror(errno.ENOLCK)))
        self.assertFalse(os.path.exists(out))

    def test_records_for_pages_that_moved(self):
        self.accept("30 Home/30 Home.md", "owner")
        moves = os.path.join(self.tmp, "map.json")
        write(moves, json.dumps({"30 Home/30 Home.md": "30 Home/Home.md"}))
        self.ok("move", "--map", moves, code=1)
        res = self.check()
        self.assertEqual((res["acceptance_records_for_no_page"], res["problems"]), (["30 Home/30 Home.md"], 0))
        self.assertEqual(self.state(res, "30 Home/Home.md"), ["not recorded", "no verdict recorded"])

    def test_concurrent_runs_each_add_their_record(self):
        pages = sorted(blocks_of(read(os.path.join(self.root, RATIONALE))))[:6]
        runs = []
        for page in pages:
            for lens in ("owner", "professional"):
                runs.append(subprocess.Popen(
                    [sys.executable, os.path.join(TOOLS, "wiki.py"), "accept", "--root", self.root, "--work",
                     self.work, "--reply", self.reply(page, lens), "--author-model", "a", "--reviewer-model", "b"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        for r in runs:
            _out, err = r.communicate(timeout=TIMEOUT)
            self.assertEqual(r.returncode, 0, err)
        self.assertEqual(len(self.records()), 12)
        self.assertEqual(sorted((r["page"], r["lens"]) for r in self.records()),
                         sorted((p, lens) for p in pages for lens in ("owner", "professional")))
        self.assertEqual(self.check()["acceptance_counts"]["accepted"], 6)

    def test_dates(self):
        for date, code in (("2024-06-30", 0), ("2024-06-30T12:00", 0), ("2024-06-30T12:00:00+0100", 0),
                           ("2024-06-30T12:00:00Z", 0), ("2024-06-30T12:00:00+01:00", 0), ("2024-02-30", 2),
                           ("2024-06-30T25:00", 2), ("2024-06-30T12:00junk", 2), ("2024-06-30T", 2),
                           ("20240630", 2), ("30/06/2024", 2), ("2024-06-30T12:60", 2), ("2024-06-30T12:00:60", 2),
                           ("2024-06-30T12:00+25:00", 2), ("2024-06-30T12:00+01:60", 2)):
            with self.subTest(date=date):
                self.accept(TAX, "owner", "a", "b", "--date", date, code=code)

    def test_changes_asked(self):
        found = [{"where": "opening line", "finding": "no date for the next return", "response": "added it"}]
        self.accept(TAX, "owner", verdict="changes", findings=found)
        self.assertEqual(self.records()[0]["findings"], found)
        self.assertEqual(self.state(self.check(), TAX), ["not recorded", "owner lens: changes asked; professional "
                                                                         "lens: no verdict"])

    def test_the_record_format(self):
        facts = [{"fact": "UTR 1234567890", "source": "02 Finance/Tax/Tax return 2023.pdf", "on_page": "UTR "
                  "1234567890", "matches": True}]
        found = [{"where": "table", "finding": "no source column label", "response": "kept: it reads clearly",
                  "severity": "low"}]
        out = json.loads(self.accept(TAX, "professional", facts_checked=facts, findings=found, author="model-a",
                                     reviewer="model-b", page_sha256=self.sha(TAX)))
        self.assertEqual(out, {"page": TAX, "lens": "professional", "verdict": "accepted", "sha256": self.sha(TAX),
                               "records": 1})
        text = read(os.path.join(self.root, ACCEPTANCE))
        self.assertTrue(text.endswith("}\n"))
        data = json.loads(text)
        self.assertEqual(list(data), ["version", "records"])
        self.assertEqual(data["version"], 1)
        rec = data["records"][0]
        self.assertEqual(list(rec), ["page", "lens", "verdict", "sha256", "professional", "contract_sha256",
                                     "author_model", "reviewer_model", "date", "findings", "facts_checked"])
        self.assertEqual((rec["professional"], rec["contract_sha256"]),
                         ("chartered tax adviser", contract_digest(self.root, "20")))
        self.assertEqual((rec["findings"], rec["facts_checked"]), ([{k: found[0][k] for k in
                                                                     ("where", "finding", "response")}], facts))
        self.ok("accept", "--reply", self.reply(TAX, "owner"), "--author-model", "a", "--reviewer-model", "b")
        self.assertRegex(self.records()[1]["date"], r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}[+-][0-9]{4}$")

    def test_malformed_replies_are_refused_and_not_recorded(self):
        stale = "0" * 64
        cases = {
            "a finding without its response": dict(verdict="changes", findings=[{"where": "top", "finding": "x"}]),
            "changes without a finding": dict(verdict="changes"),
            "the old vocabulary": dict(verdict="accept"),
            "a stale sha256": dict(page_sha256=stale),
            "another reviewer in the reply": dict(reviewer="model-c"),
            "another author in the reply": dict(author="model-c"),
        }
        whys = ["findings[0] needs where, finding, response", "a changes verdict names at least one finding",
                "verdict 'accept' is not one of accepted, changes", "the page is now",
                "the reply names reviewer 'model-c', but --reviewer-model is 'model-b'",
                "the reply names author 'model-c'"]
        for (name, extra), why in zip(cases.items(), whys):
            with self.subTest(case=name):
                err = self.refused("accept", "--reply", self.reply(TAX, "owner", **extra), "--author-model",
                                   "model-a", "--reviewer-model", "model-b")
                self.assertIn(why, err)
        for page, lens, why in ((TAX, "reader", "lens 'reader' is not one of owner, professional"),
                                ("20 Finance/Pensions.md", "owner", "is not a page in"),
                                ("../CLAUDE.md", "owner", "is not a page in")):
            with self.subTest(page=page, lens=lens):
                self.assertIn(why, self.refused("accept", "--reply", self.reply(page, lens), "--author-model", "a",
                                                "--reviewer-model", "b"))
        self.assertIn("--date", self.refused("accept", "--reply", self.reply(TAX, "owner"), "--author-model", "a",
                                             "--reviewer-model", "b", "--date", "30/06/2024"))
        self.assertFalse(os.path.exists(os.path.join(self.root, ACCEPTANCE)))

    def test_every_page_accepted_and_still_a_problem(self):
        for page in sorted(blocks_of(read(os.path.join(self.root, RATIONALE)))):
            for lens in ("owner", "professional"):
                self.accept(page, lens)
        res = self.check()
        self.assertEqual((res["acceptance"], res["acceptance_counts"]["accepted"], res["problems"]),
                         ("accepted", 12, 0))
        edit(os.path.join(self.root, RATIONALE), blocks_of(read(os.path.join(self.root, RATIONALE)))[TAX] + "\n\n",
             "")
        res = self.check()  # a problem the check finds is not outweighed by acceptance, nor acceptance by it
        self.assertEqual((res["acceptance"], res["problems"], findings(res)),
                         ("accepted", 1, {"rationale.pages_without_block": 1}))

    def test_read_only_root_and_a_record_elsewhere(self):
        before = tree_digest(self.root)
        reply = self.reply(TAX, "owner")
        self.assertIn("--read-only-root", self.refused("accept", "--reply", reply, "--author-model", "a",
                                                       "--reviewer-model", "b", "--read-only-root"))
        record = os.path.join(self.tmp, "acceptance.json")
        for lens in ("owner", "professional"):
            self.ok("accept", "--reply", self.reply(TAX, lens), "--author-model", "a", "--reviewer-model", "b",
                    "--read-only-root", "--out", record)
        self.assertEqual(tree_digest(self.root), before)
        self.assertEqual(len(self.records(record)), 2)
        self.assertEqual(self.state(self.check("--acceptance", record), TAX)[0], "accepted")
        self.assertEqual(self.state(self.check(), TAX)[0], "not recorded")

    def test_a_malformed_record_fails_loud(self):
        write(os.path.join(self.root, ACCEPTANCE), json.dumps({"version": 1, "records": [{"page": TAX}]}))
        self.assertIn("records[0] is not a record", self.refused("check"))
        self.assertIn("records[0] is not a record", self.refused("accept", "--reply", self.reply(TAX, "owner"),
                                                                 "--author-model", "a", "--reviewer-model", "b"))

    def test_prompts_to_acceptance(self):
        out = os.path.join(self.tmp, "p")
        self.ok("review-prompts", "--page", TAX, "--author-model", "model-a", "--reviewer-model", "model-b",
                "--out", out)
        for lens in ("owner", "professional"):
            prompt = read(os.path.join(out, "20 Finance", "Tax.%s.md" % lens))
            shape = re.search(r"```json\n(.*?)```", prompt, re.S).group(1)
            sha = re.search(r'"page_sha256": "([0-9a-f]{64})"', shape).group(1)
            self.accept(TAX, lens, page_sha256=sha, author="model-a", reviewer="model-b")
        self.assertEqual(self.state(self.check(), TAX)[0], "accepted")


if __name__ == "__main__":
    unittest.main()
