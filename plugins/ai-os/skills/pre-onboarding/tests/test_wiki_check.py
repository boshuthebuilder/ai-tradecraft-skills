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
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.realpath(os.path.join(HERE, "..", "tools"))
FIXTURE = os.path.join(HERE, "fixture", "Alex Personal")
MANIFEST = os.path.join(HERE, "expected", "manifest.json")
WIKI = "Alex Personal Wiki"
RATIONALE = os.path.join("_Audit", "wiki-rationale.md")
ACCEPTANCE = os.path.join("_Audit", "wiki-acceptance.json")
TAX = "20 Finance/Tax.md"
sys.path.insert(0, TOOLS)
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
PROBLEM_LISTS = ("frontmatter_bad", "dead_source_paths", "dead_page_links", "links_outside_page_map",
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
    r = subprocess.run([sys.executable, os.path.join(TOOLS, tool)] + list(args), capture_output=True, text=True,
                       encoding="utf-8")
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
                                           {"06 Work/Contract.docx": "h"}, "cards")[1],
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
            _out, err = r.communicate()
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
