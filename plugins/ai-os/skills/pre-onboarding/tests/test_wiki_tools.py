"""`wiki.py profile`, `bundles`, `brief`, `move` and `drift`, and the stage templates, on fixture copies.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests
    python3 test_wiki_tools.py --update      rewrite golden/wiki/ (commit with why)

Each copy's cards and extracts are small synthetic records (RECORDS below, each card in the shape of
tools/schemas/card.json), written over the fixture's own in the copy's _Audit/, never into the committed fixture.
The copy's manifest is the frozen tests/expected/manifest.json, so the sha256 the bundles record is the same on
every machine. In the golden outputs (golden/wiki/), the paths that differ between machines are written <tmp> (the
test's temporary folder) and <skills> (this repository's skills folder).
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import string
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.realpath(os.path.join(HERE, "..", "tools"))
SKILLS = os.path.realpath(os.path.join(HERE, "..", ".."))
FIXTURE = os.path.join(HERE, "fixture", "Alex Personal")
MANIFEST = os.path.join(HERE, "expected", "manifest.json")
GOLDEN = os.path.join(HERE, "golden", "wiki")
WIKI = "Alex Personal Wiki"
BRIEF_PAGES = ("20 Finance/Tax.md", "20 Finance/Cash position.md")
TEMPLATES = ("readers-interview.md", "structure-brief.md", "contract-brief.md", "page-brief.md", "review-owner.md",
             "review-professional.md")
RULE = os.path.join(SKILLS, "wiki-maintenance", "SKILL.md")
ONBOARDING = os.path.join(SKILLS, "wiki-onboarding", "SKILL.md")
STEP_4A = {  # what wiki-onboarding step 4a says a drafting agent returns: where the brief's JSON shape carries each
    "the pages it wrote": ("page", "text"),
    "each page's rationale block": ("page", "rationale"),
    "its Index entry": ("page", "index_entry"),
    "its open questions": ("return", "open_questions"),
    "its check result": ("return", "check_result"),
}
sys.path.insert(0, TOOLS)
import common  # noqa: E402
import wiki  # noqa: E402

# path: doc_type, party, parties, doc_date, category, language, title, summary, reference numbers, text
RECORDS = {
    "01 Identity/Passport renewal 2021/Application form.docx": (
        "Form", "Alex Example", ["Example Passport Agency"], "2021-05-02", "Identity & Immigration", "en",
        "Passport renewal application", "The 2021 application to renew the passport.", ["passport P0987654"],
        "Passport renewal application for Alex Example\nSubmitted 2021-05-02\nPrevious passport P0987654"),
    "01 Identity/Passport scan.pdf": (
        "Passport Scan", "Alex", ["Example Passport Agency"], "2021-07-15", "Identity & Immigration", "en",
        "Passport scan", "The passport, valid to 2031-07-15.", ["passport P1234567"],
        "PASSPORT\nAlex Example\nP1234567\nIssued 15 JUL 2021\nExpires 15 JUL 2031"),
    "02 Finance/Bank statement 2024-03.pdf": (
        "Bank Statement", "Alex Example", ["Example Bank plc"], "2024-03-31", "Finance & Tax", "en",
        "Current account statement, March 2024", "The March 2024 statement, closing at GBP 4,160.00.",
        ["account 12345678 sort 01-02-03"],
        "Example Bank plc\nStatement for Alex Example\nOpening balance GBP 2,410.00\nClosing balance GBP 4,160.00"),
    "02 Finance/Tax/Budget final.xlsx": (
        "Spreadsheet", "Alex Example", [], "2024", "Finance & Tax", "en", "Household budget, final",
        "Planned monthly spending: rent, utilities and savings.", [], "Item\tMonthly\nRent\nUtilities\nSavings"),
    "02 Finance/Tax/Budget.numbers": (
        "Spreadsheet", "亚历克斯", ["Robin"], "2023", "Finance & Tax", "en", "Household budget, 2023",
        "The 2023 household budget.", [], "Household budget for 2023 prepared by Alex Example"),
    "02 Finance/Tax/Tax return 2023.pdf": (
        "Tax Return", "Alex Example", ["Example Tax Office", "Robin Trading Ltd"], "2023-12-12", "Finance & Tax",
        "en", "Tax return 2022 to 2023", "The 2022 to 2023 return, filed with nothing to pay.", ["UTR 1234567890"],
        "Tax return 2022-23\nUTR 1234567890\nEmployment income 38400\nTax paid 5160\nFiled 12 December 2023"),
    "03 Home/Lease notes .txt": (
        "Notes", "Alex Example", ["Example Lettings"], "", "Home & Household", "en", "Notes on the lease",
        "A reminder to ask the landlord about the boiler service.", [],
        "Notes on the lease: ask Example Lettings about the boiler service."),
    "03 Home/Lease renewal.pages": (
        "Tenancy Agreement", "Alex Example", ["Example Lettings"], "2024-05-01", "Home & Household", "en",
        "Lease renewal (Pages original)", "The lease renewed to 2025-04-30 at GBP 1,450 a month.", [],
        "Lease renewal for 3 Example Road, signed by Alex Example"),
    "03 Home/Lease renewal.pdf": (
        "Tenancy Agreement", "Alex Example", ["Example Lettings"], "2024-05-01", "Home & Household", "en",
        "Lease renewal", "The lease renewed to 2025-04-30 at GBP 1,450 a month.", [],
        "Lease renewal\nLandlord: Example Lettings\nTerm: 1 May 2024 to 30 April 2025"),
    "03 Home/Utilities /Electricity bill.pdf": (
        "Invoice", "Alex Example", ["Example Energy Ltd"], "2024-03-15", "Home & Household", "en",
        "Electricity bill, March 2024", "GBP 96.40 due by 2024-04-01.", ["account EE-5521"],
        "Example Energy Ltd\nElectricity bill for Alex Example\nBill date 15 March 2024"),
    "04 Study/Cours de français.pdf": (
        "Certificate", "Alex Example", ["Example Language School"], "2023-06", "Education", "fr",
        "French B1 certificate (Cours de français)", "French at B1: 16/20 written, 14/20 oral.", [],
        "Certificat de langue\nNiveau B1\nÉcrit 16/20, oral 14/20"),
    "04 Study/Notes.rtf": (
        "Lecture Notes", "Alex Example", ["Robin Example"], "", "Language Study", "en", "Class notes",
        "Irregular verbs and measure words.", [],
        "Class notes: irregular verbs and measure words, reviewed with Robin Example."),
    "04 Study/Slides.pptx": (
        "Presentation", "Alex Example", [], "2024", "Language Study", "en", "Language learning plan",
        "Targets for 2024: B2 French and HSK 4 Chinese.", [],
        "Language learning plan for 2024\nTargets: B2 French and HSK 4 Chinese"),
    "04 Study/中文课程.pdf": (
        "Certificate", "亚历克斯", ["Example Language School"], "2024-01-20", "Education", "zh",
        "Chinese intermediate certificate (中文课程)", "Intermediate Chinese, graded excellent.", [],
        "中文课程\n中级\n优秀"),
    "06 Work/Contract.docx": (
        "Contract", "Alex Example", ["Robin Trading Ltd"], "2022-05-01", "Work & Career", "en",
        "Employment contract", "Employment with Robin Trading Ltd from 2022-05-01, one month's notice.", [],
        "Employment contract between Robin Trading Ltd and Alex Example\nStart date 2022-05-01"),
    "06 Work/Essay.docx": (
        "Essay", "Alex Example", ["Example Evening College"], "2023-11", "Language Study", "en",
        "Essay: why learn a third language", "An essay for the evening class.", [],
        "Essay: why learn a third language\nWritten by Alex Example for the evening class"),
    "IMG_0001.jpg": (
        "Photo", "Unknown", [], "", "Photos", "none", "Beach photo", "A photo of a beach.", [], ""),
    "_Migrations/Other Project/02 Finance/Old invoice.pdf": (
        "Invoice", "Robin Trading Ltd", ["Alex Example"], "2022-02", "Business", "en", "Consulting invoice 2022-117",
        "An invoice for consulting in February 2022, paid.", ["invoice 2022-117"],
        "Invoice 2022-117 from Robin Trading Ltd to Alex Example"),
}


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


def card_and_extract(eid, entry):
    doc_type, party, parties, doc_date, category, language, title, summary, refs, text = RECORDS[entry["current_path"]]
    card = {"id": eid, "doc_type": doc_type, "party": party, "parties": parties, "doc_date": doc_date, "title": title,
            "summary": summary, "key_facts": {"dates": [doc_date] if doc_date else [], "amounts": [],
                                              "reference_numbers": refs},
            "category": category, "language": language, "sensitive": bool(refs), "confidence": "high", "look": "",
            "proposed_name": "", "card_meta": {"model": "synthetic", "via": "test", "batch": "synthetic",
                                               "created_at": "2024-06-30T12:00:00+0000"}}
    tier = "photo" if entry["class"] == "image" else "text_layer"
    extract = {"id": eid, "path": entry["current_path"], "class": entry["class"],
               "status": "photo" if tier == "photo" else "ok", "page_count": 1, "tiers": {tier: 1},
               "chars": len(text), "extractor": "synthetic", "extracted_at": "2024-06-30T12:00:00+0000",
               "pages": [{"n": 1, "tier": tier, "text": text}]}
    return card, extract


def make_copy(parent):
    """A fixture copy under `parent` with the frozen manifest, a compiled Schema twin and synthetic cards and
    extracts; returns its root."""
    root = os.path.join(parent, "Alex Personal")
    shutil.copytree(FIXTURE, root)
    audit = os.path.join(root, "_Audit")
    shutil.copy(MANIFEST, os.path.join(audit, "manifest.json"))
    code, _out, err = run("settings.py", "compile", "--root", root, "--work", os.path.join(parent, "work"))
    if code:
        raise AssertionError(err)
    for eid, entry in json.loads(read(MANIFEST))["entries"].items():
        card, extract = card_and_extract(eid, entry)
        write(os.path.join(audit, "cards", eid + ".json"), json.dumps(card, ensure_ascii=False, indent=1))
        write(os.path.join(audit, "extract", eid + ".json"), json.dumps(extract, ensure_ascii=False, indent=1))
    return root


def rule_labels(test):
    """The five line labels of the rationale block, from the fenced example in the core wiki rule's section "The
    rationale block" (`wiki-maintenance`); `test` fails, naming the rule file, when that section or example moves."""
    text = read(RULE)
    heading = "\n### The rationale block\n"
    test.assertIn(heading, text, "%s has no section headed 'The rationale block'" % RULE)
    example = re.search(r"(?ms)^```markdown\n(.*?)^```$", text.split(heading, 1)[1])  # the section's first fence
    test.assertIsNotNone(example, "%s: 'The rationale block' has no ```markdown example" % RULE)
    labels = re.findall(r"(?m)^- ([^:]+):", example.group(1))
    test.assertEqual(len(labels), 5, "%s: the rationale block example should have five labelled lines" % RULE)
    return labels


def step_4a_items(test):
    """The items of step 4a's sentence "An agent returns JSON, not prose: ...", in `wiki-onboarding`; `test` fails,
    naming the file, when the step or the sentence moves."""
    text = read(ONBOARDING)
    test.assertIn("\n### 4a. ", text, "%s has no step 4a" % ONBOARDING)
    step = " ".join(text.split("\n### 4a. ", 1)[1].split("\n### ", 1)[0].split())
    m = re.search(r"returns JSON, not prose: (.+?)\.(?:\s|$)", step)
    test.assertIsNotNone(m, "%s step 4a no longer says what a drafting agent returns as JSON" % ONBOARDING)
    return re.split(r",\s*|\s+and\s+", m.group(1))


def normalise(text, tmp):
    """`text` with the paths that differ between machines written as <tmp> and <skills>."""
    tool = os.path.join(TOOLS, "wiki.py")
    text = text.replace(shlex.quote(tool), tool)  # quoted only where the checkout's path needs it
    for real, name in ((tmp, "<tmp>"), (SKILLS, "<skills>")):
        text = text.replace(urllib.parse.quote(real, safe="/&"), name).replace(real, name)
    return text


class Copy(unittest.TestCase):
    """Each test works on its own fixture copy; the committed fixture is never touched."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="wiki_tools_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = make_copy(os.path.join(self.tmp, "a"))
        self.work = os.path.join(self.tmp, "a", "work")

    def wiki(self, cmd, *args, root=None, work=None):
        return run("wiki.py", cmd, "--root", root or self.root, "--work", work or self.work, *args)

    def ok(self, cmd, *args, code=0, **kw):
        got, out, err = self.wiki(cmd, *args, **kw)
        self.assertEqual(got, code, out + err)
        return out

    def refused(self, cmd, *args, **kw):
        code, out, err = self.wiki(cmd, *args, **kw)
        self.assertEqual(code, 2, out + err)
        self.assertNotIn("Traceback", err)
        return err

    def page(self, rel):
        return os.path.join(self.root, WIKI, *rel.split("/"))

    def edit(self, path, old, new):
        text = read(path)
        self.assertEqual(text.count(old), 1, "%r in %s" % (old, path))
        write(path, text.replace(old, new))

    def bundles_dir(self):
        return os.path.join(self.work, "bundles")

    def brief(self, *pages, code=0, **kw):
        args = [x for p in pages for x in ("--page", p)]
        return self.ok("brief", *args, code=code, **kw)


class RecordsTest(unittest.TestCase):
    def test_synthetic_cards_match_the_card_schema(self):
        schema = json.loads(read(os.path.join(TOOLS, "schemas", "card.json")))["properties"]["items"]["items"]
        types = {"string": str, "array": list, "object": dict, "boolean": bool}
        entries = json.loads(read(MANIFEST))["entries"]
        self.assertEqual(sorted(e["current_path"] for e in entries.values()), sorted(RECORDS))
        for eid, entry in entries.items():
            card, _x = card_and_extract(eid, entry)
            with self.subTest(path=entry["current_path"]):
                self.assertEqual(set(schema["required"]) - set(card), set())
                for key, spec in schema["properties"].items():
                    self.assertIsInstance(card[key], types[spec["type"]], key)
                self.assertEqual(set(schema["properties"]["key_facts"]["required"]), set(card["key_facts"]))


class ProfileTest(Copy):
    def profile(self, *args):
        return json.loads(self.ok("profile", *args))

    def test_golden(self):
        self.assertEqual(self.ok("profile"), read(os.path.join(GOLDEN, "profile.json")))

    def exclude(self, *paths):
        twin = os.path.join(self.root, ".familyai", "rulebook.json")
        write(twin, json.dumps(dict(json.loads(read(twin)), exclude=list(paths)), ensure_ascii=False, indent=1))

    def test_an_excluded_document_is_counted_and_never_profiled_or_named(self):
        self.exclude("06 Work")
        text = self.ok("profile")
        res = json.loads(text)
        self.assertEqual({k: res[k] for k in ("documents", "carded", "copies", "migrating", "excluded")},
                         {"documents": 15, "carded": 15, "copies": 5, "migrating": 1, "excluded": 2})
        self.assertNotIn("06 Work", text, "a folder, a path or a copy of an excluded document named in the profile")
        self.assertNotIn("06 Work", [r["folder"] for r in res["folders"]])
        archive = {r["folder"]: r for r in res["folders"]}["05 Archive"]
        self.assertEqual(archive["copies_of"], {"04 Study": 3}, "the copies of Essay.docx are not counted")
        self.exclude("05 Archive")  # a copy under an excluded path is named by no one's profile either
        text = self.ok("profile")
        self.assertNotIn("05 Archive", text)
        self.assertEqual(json.loads(text)["copies"], 7 - 4)

    def test_a_copy_under_the_migrations_folder_is_never_named(self):
        man = json.loads(read(os.path.join(self.root, "_Audit", "manifest.json")))
        entry = next(e for e in man["entries"].values() if e["current_path"] == "03 Home/Lease renewal.pdf")
        entry["copies"] = [{"path": entry["current_path"], "kind": "canonical"},
                           {"path": "_Migrations/Other Project/Lease renewal.pdf", "kind": "working_copy"}]
        write(os.path.join(self.root, "_Audit", "manifest.json"), json.dumps(man))
        text = self.ok("profile")
        self.assertNotIn("Other Project", text)
        self.assertEqual(json.loads(text)["copies"], 7)

    def test_folders_copies_dates_and_parties(self):
        res = self.profile()
        self.assertEqual({k: res[k] for k in ("documents", "carded", "uncarded", "copies", "migrating", "departed")},
                         {"documents": 17, "carded": 17, "uncarded": 0, "copies": 7, "migrating": 1, "departed": 0})
        rows = {r["folder"]: r for r in res["folders"]}
        self.assertEqual(sorted(rows), ["(root)", "01 Identity", "01 Identity/Passport renewal 2021", "02 Finance",
                                        "02 Finance/Tax", "03 Home", "03 Home/Utilities ", "04 Study", "05 Archive",
                                        "06 Work"])
        archive = rows["05 Archive"]
        self.assertEqual((archive["documents"], archive["copies"], archive["copies_of"], archive["carded"]),
                         (0, 4, {"04 Study": 3, "06 Work": 1}, 0))
        finance = rows["02 Finance"]
        self.assertEqual((finance["documents"], finance["copies"], finance["categories"]),
                         (4, 1, {"Finance & Tax": 4}))
        self.assertEqual((finance["dated"], finance["earliest"], finance["latest"]), (4, "2023", "2024-03-31"))
        home = rows["03 Home"]
        self.assertEqual((home["dated"], home["earliest"], home["latest"]), (3, "2024-03-15", "2024-05-01"))
        # aliases fold to the rulebook's canonical names; "Unknown" is no party
        self.assertEqual(finance["parties"][0], ["Alex Example", 4])
        self.assertIn(["Robin Example", 1], finance["parties"])
        self.assertEqual(rows["(root)"]["parties"], [])
        self.assertEqual(rows["04 Study"]["parties"][:2], [["Alex Example", 4], ["Example Language School", 2]])

    def test_depth_and_missing_cards(self):
        os.remove(os.path.join(self.root, "_Audit", "cards", sorted(os.listdir(
            os.path.join(self.root, "_Audit", "cards")))[0]))
        res = self.profile("--depth", "1", "--parties", "1")
        self.assertTrue(all("/" not in r["folder"] for r in res["folders"]))
        self.assertEqual((res["carded"], res["uncarded"]), (16, 1))
        self.assertTrue(all(len(r["parties"]) <= 1 for r in res["folders"]))
        shutil.rmtree(os.path.join(self.root, "_Audit", "cards"))
        res = self.profile()
        self.assertEqual((res["carded"], res["uncarded"], res["categories"]), (0, 17, {}))

    def test_out_and_read_only_root(self):
        out = os.path.join(self.tmp, "profile.json")
        printed = self.ok("profile", "--out", out)
        self.assertEqual((read(out), printed), (printed, read(os.path.join(GOLDEN, "profile.json"))))
        self.refused("profile", "--out", os.path.join(self.root, "profile.json"), "--read-only-root")
        self.assertFalse(os.path.exists(os.path.join(self.root, "profile.json")))


class BundlesTest(Copy):
    def build(self, *args, code=1, **kw):
        return json.loads(self.ok("bundles", *args, code=code, **kw))

    def test_golden_byte_stable_and_outside_the_folder(self):
        before = tree_digest(self.root)
        res = self.build()
        self.assertEqual(tree_digest(self.root), before, "bundles wrote inside the folder")
        self.assertEqual(res, {"routed": 16, "sections": {"10": 2, "20": 6, "30": 4, "40": 4}, "compact": {"40": 2},
                               "unrouted": ["IMG_0001.jpg"], "uncarded": [], "held_for_another_project": 1,
                               "excluded": 0})
        names = sorted(os.listdir(self.bundles_dir()))
        self.assertEqual(names, sorted(os.listdir(os.path.join(GOLDEN, "bundles"))))
        first = {n: read(os.path.join(self.bundles_dir(), n), "rb") for n in names}
        for n in names:
            self.assertEqual(first[n], read(os.path.join(GOLDEN, "bundles", n), "rb"), n)
        other = make_copy(os.path.join(self.tmp, "b"))
        out = os.path.join(self.tmp, "b", "elsewhere")
        self.build("--out", out, root=other, work=os.path.join(self.tmp, "b", "work"))
        self.assertEqual({n: read(os.path.join(out, n), "rb") for n in sorted(os.listdir(out))}, first)
        meta = json.loads(first["bundles.json"])
        self.assertEqual(meta["manifest_sha256"], hashlib.sha256(read(MANIFEST, "rb")).hexdigest())

    def test_records(self):
        self.build()
        rows = [json.loads(x) for x in read(os.path.join(self.bundles_dir(), "bundle_40.jsonl")).splitlines()]
        self.assertEqual([r["path"] for r in rows], ["04 Study/Cours de français.pdf", "04 Study/Notes.rtf",
                                                     "04 Study/Slides.pptx", "04 Study/中文课程.pdf"])
        slides = rows[2]
        self.assertTrue(slides["compact"])
        self.assertNotIn("summary", slides)
        self.assertNotIn("text", rows[0])  # a history section carries summaries, not text
        rows = [json.loads(x) for x in read(os.path.join(self.bundles_dir(), "bundle_20.jsonl")).splitlines()]
        bank = rows[0]
        self.assertEqual((bank["path"], bank["copies"]), ("02 Finance/Bank statement 2024-03.pdf",
                                                          ["02 Finance/Bank statement 2024-03 (1).pdf"]))
        self.assertTrue(bank["text"].startswith("[page 1]\nExample Bank plc"))
        self.assertEqual([r["path"] for r in rows][-2:], ["06 Work/Contract.docx", "06 Work/Essay.docx"])

    def test_inside_the_folder_is_refused(self):
        before = tree_digest(self.root)
        err = self.refused("bundles", "--out", os.path.join(self.root, "_Audit", "bundles"))
        self.assertIn("never written inside the folder", err)
        self.assertEqual(tree_digest(self.root), before)

    def test_unrouted_uncarded_and_note_rows(self):
        ids = {e["current_path"]: h for h, e in json.loads(read(MANIFEST))["entries"].items()}
        os.remove(os.path.join(self.root, "_Audit", "cards", ids["03 Home/Lease notes .txt"] + ".json"))
        res = self.build()
        self.assertEqual((res["unrouted"], res["uncarded"], res["sections"]["30"]),
                         (["IMG_0001.jpg"], ["03 Home/Lease notes .txt"], 3))
        ws = {"routing": [{"prefix": "02 Finance/", "section": "20"}, {"prefix": "02 Finance/Scratch/",
                                                                       "section": None}]}
        self.assertEqual([wiki.route(ws, p) for p in ("02 Finance/a.pdf", "02 Finance/Scratch/a.pdf", "a.pdf")],
                         ["20", None, None])

    def exclude(self, *paths):
        twin = os.path.join(self.root, ".familyai", "rulebook.json")
        write(twin, json.dumps(dict(json.loads(read(twin)), exclude=list(paths)), ensure_ascii=False, indent=1))

    def bundle_text(self):
        return "".join(read(os.path.join(self.bundles_dir(), n)) for n in sorted(os.listdir(self.bundles_dir())))

    def test_an_excluded_document_is_in_no_bundle_list_or_record_and_is_counted(self):
        ids = {e["current_path"]: h for h, e in json.loads(read(MANIFEST))["entries"].items()}
        os.remove(os.path.join(self.root, "_Audit", "cards", ids["06 Work/Contract.docx"] + ".json"))  # no card
        self.exclude("06 Work", "05 Archive")
        res = self.build()
        self.assertEqual((res["excluded"], res["held_for_another_project"], res["uncarded"], res["unrouted"]),
                         (2, 1, [], ["IMG_0001.jpg"]), "withheld is neither uncarded nor unrouted")
        self.assertEqual(res["sections"]["20"], 4)
        text = self.bundle_text()
        for named in ("06 Work", "05 Archive", "Contract", "Essay"):
            self.assertNotIn(named, text, "an excluded document, or a copy of one, is named in a bundle")
        rows = [json.loads(x) for x in read(os.path.join(self.bundles_dir(), "bundle_40.jsonl")).splitlines()]
        self.assertEqual({r["path"]: r["copies"] for r in rows if r["path"] == "04 Study/Slides.pptx"},
                         {"04 Study/Slides.pptx": []}, "the copy of Slides.pptx in the excluded 05 Archive is named")
        self.assertEqual(json.loads(read(os.path.join(self.bundles_dir(), "bundles.json")))["excluded"], 2)

    def test_a_copy_staged_for_another_project_is_in_no_bundle(self):
        man = json.loads(read(os.path.join(self.root, "_Audit", "manifest.json")))
        entry = next(e for e in man["entries"].values() if e["current_path"] == "03 Home/Lease renewal.pdf")
        entry["copies"] = [{"path": entry["current_path"], "kind": "canonical"},
                           {"path": "_Migrations/Other Project/Lease renewal.pdf", "kind": "working_copy"}]
        write(os.path.join(self.root, "_Audit", "manifest.json"), json.dumps(man))
        self.build()
        self.assertNotIn("Other Project", self.bundle_text())

    def test_bundles_built_before_an_exclusion_are_stale_and_a_rebuild_drops_the_document(self):
        self.build()
        self.assertIn("Contract.docx", self.bundle_text())
        self.exclude("06 Work")  # the owner excludes it; the manifest has not moved, so only the withheld set says so
        for cmd, args in (("bundles", ["--reuse"]), ("brief", ["--page", BRIEF_PAGES[0]])):
            with self.subTest(cmd=cmd):
                self.exclude()  # the bundles are rebuilt as they were, then the exclusion is made again
                self.build()
                self.exclude("06 Work")
                err = self.refused(cmd, *args)
                self.assertIn("stale bundles", err)
                self.assertIn("held for another project or excluded", err)
                self.assertIn("rebuild them: wiki.py bundles --root", err)
                self.assertEqual(sorted(os.listdir(self.bundles_dir())), [],
                                 "the bundles holding the excluded documents were left on disk")
        self.build()
        self.assertNotIn("Contract.docx", self.bundle_text())
        self.brief(BRIEF_PAGES[0])

    def test_a_brief_does_not_name_a_withheld_folder_in_its_routes(self):
        self.exclude("06 Work")
        self.build()
        brief = self.brief(BRIEF_PAGES[0])
        self.assertNotIn("06 Work", brief)
        self.assertIn("  - 1 route to a withheld folder, not shown", brief)
        self.assertIn("  - `02 Finance/`: 20 Bank accounts and Cash position", brief)

    def test_a_brief_embeds_the_schemas_tables_without_the_withheld_routes_and_never_names_the_schema_page(self):
        self.exclude("06 Work")
        self.build()
        brief = self.brief(BRIEF_PAGES[0])
        tables = brief.split("## The Schema's tables")[1].split("## What to do")[0]
        for heading in ("### Layout", "### Routing", "### Page contracts", "### Page professionals"):
            self.assertIn(heading, tables)
        self.assertIn("| `02 Finance/` | 20 Bank accounts and Cash position |", tables)
        self.assertIn("1 routing row into a withheld folder is not shown.", tables)
        self.assertIn("| 20 Finance/Tax.md | chartered tax adviser | annual tax position letter | exact, dated |", tables)
        self.assertNotIn(os.path.join(self.root, WIKI, "90 Schema", "90 Schema.md"), brief,
                         "the brief sends the author to the page that lists the routes")
        self.assertNotIn("Read the Schema page", brief)
        self.assertIn("do not open the Schema page", brief)
        self.assertIn("A path this brief marks withheld, any path under the migrations folder and any path the owner "
                      "excluded is never opened, read or cited", " ".join(brief.split()))
        self.assertNotIn("Open a source file itself when", brief)

    def test_a_brief_with_nothing_withheld_shows_every_route_and_no_note(self):
        self.build()
        tables = self.brief(BRIEF_PAGES[0]).split("## The Schema's tables")[1].split("## What to do")[0]
        self.assertIn("| `06 Work/` | 20 Tax (employment income) |", tables)
        self.assertNotIn("not shown", tables)

    def test_a_rebuild_leaves_only_its_own_files(self):
        write(os.path.join(self.bundles_dir(), "bundle_99.jsonl"), "{}\n")
        write(os.path.join(self.bundles_dir(), "notes.txt"), "kept\n")
        self.build()
        self.assertEqual(sorted(os.listdir(self.bundles_dir())), ["bundle_10.jsonl", "bundle_20.jsonl",
                                                                  "bundle_30.jsonl", "bundle_40.jsonl",
                                                                  "bundles.json", "notes.txt"])


class StaleTest(Copy):
    """Bundles record the manifest's sha256 and the routing's digest; a consumer refuses them once either moves."""

    def assert_stale(self, why):
        for cmd, args in (("bundles", ["--reuse"]), ("brief", ["--page", BRIEF_PAGES[0]])):
            with self.subTest(cmd=cmd):
                err = self.refused(cmd, *args)
                self.assertIn("stale bundles", err)
                self.assertIn(why, err)
                self.assertIn("rebuild them: wiki.py bundles --root", err)

    def test_fresh_bundles_are_reused(self):
        built = self.ok("bundles", code=1)
        self.assertEqual(self.ok("bundles", "--reuse", code=1), built)
        self.brief(BRIEF_PAGES[0])

    def test_a_migration_makes_bundles_stale(self):
        self.ok("bundles", code=1)
        os.renames(os.path.join(self.root, "06 Work", "Contract.docx"),
                   os.path.join(self.root, "_Migrations", "Other Project", "06 Work", "Contract.docx"))
        code, _out, err = run("audit.py", "--root", self.root, "--work", self.work)
        self.assertEqual(code, 0, err)
        self.assert_stale("after any migration or re-audit")
        self.ok("bundles", code=1)
        rows = read(os.path.join(self.bundles_dir(), "bundle_20.jsonl"))
        self.assertNotIn("06 Work/Contract.docx", rows)
        self.ok("bundles", "--reuse", code=1)
        self.brief(BRIEF_PAGES[0])

    def test_any_manifest_change_makes_bundles_stale(self):
        self.ok("bundles", code=1)
        path = os.path.join(self.root, "_Audit", "manifest.json")
        write(path, read(path) + "\n")
        self.assert_stale("records manifest sha256")

    def test_a_routing_change_makes_bundles_stale(self):
        self.ok("bundles", code=1)
        schema = os.path.join(self.root, WIKI, "90 Schema", "90 Schema.md")
        self.edit(schema, "| `06 Work/` | 20 Tax (employment income) |", "| `06 Work/` | 30 Home |")
        code, _out, err = run("settings.py", "compile", "--root", self.root, "--work", self.work)
        self.assertEqual(code, 0, err)
        self.assert_stale("another Schema routing")

    def test_missing_and_incomplete_bundles(self):
        err = self.refused("brief", "--page", BRIEF_PAGES[0])
        self.assertIn("no bundles in", err)
        self.assertIn("build them: wiki.py bundles", err)
        self.ok("bundles", code=1)
        os.remove(os.path.join(self.bundles_dir(), "bundle_20.jsonl"))
        self.assertIn("incomplete bundles", self.refused("bundles", "--reuse"))

    def test_a_stale_twin_is_refused_first(self):
        self.edit(os.path.join(self.root, WIKI, "90 Schema", "90 Schema.md"), "The constitution", "the constitution")
        for cmd, args in (("profile", []), ("bundles", []), ("brief", ["--page", BRIEF_PAGES[0]]), ("drift", []),
                          ("move", ["--map", os.path.join(self.tmp, "map.json")])):
            with self.subTest(cmd=cmd):
                self.assertIn("error: stale:", self.refused(cmd, *args))


class BriefTest(Copy):
    def setUp(self):
        super().setUp()
        self.ok("bundles", code=1)

    def test_golden_and_byte_stable(self):
        first = self.brief(*BRIEF_PAGES)
        self.assertEqual(self.brief(*reversed(BRIEF_PAGES)), first)
        self.assertEqual(normalise(first, self.tmp), read(os.path.join(GOLDEN, "brief.md")))
        other = make_copy(os.path.join(self.tmp, "b"))
        work = os.path.join(self.tmp, "b", "work")
        self.ok("bundles", code=1, root=other, work=work)
        again = self.brief(*BRIEF_PAGES, root=other, work=work)
        self.assertEqual(normalise(again, self.tmp).replace("<tmp>/b/", "<tmp>/a/"), normalise(first, self.tmp))

    def test_what_a_brief_carries(self):
        text = self.brief("20 Finance/Tax.md", "10 Identity/Visa.md")
        for part in ("- Professional: chartered tax adviser (the page's row in the Page professionals table)",
                     "- Deliverable: annual tax position letter", "- Tone: exact, dated", "- Reader: Alex",
                     "  3. What is the tax position?", "- Fields every page carries: account, period, balances",
                     "  - `06 Work/`: 20 Tax (employment income)",
                     "- Professional: immigration adviser (the section's one professional)",
                     "- Status: planned (write it)", "- Status: exists (revise it)",
                     "- Alex Example (also Alex, 亚历克斯): owner of this folder",
                     "Identifiers (`stated`): reference numbers written IN FULL",
                     "- `10 Identity/Visa.md` (planned, in this brief)", "- `20 Finance/Bank accounts.md` (exists)",
                     "- Changed from the previous page: first version",
                     "- Professional lens: chartered tax adviser; questions answered in order: 1. Is anything due? "
                     "2. What came in and went out? 3. What is the tax position?"):
            self.assertIn(part, text)
        self.assertIn("`%s` (6 documents)" % os.path.join(self.bundles_dir(), "bundle_20.jsonl"), text)
        self.assertNotIn("{", re.sub(r"```json\n.*?```", "", text, flags=re.S))

    def test_rationale_blocks_have_five_lines(self):
        text = self.brief(*BRIEF_PAGES)
        blocks = text.split("## The rationale blocks\n", 1)[1].strip().split("\n\n")[1:]
        self.assertEqual([b.split("\n")[0] for b in blocks], ["### " + p for p in sorted(BRIEF_PAGES)])
        labels = rule_labels(self)
        for b in blocks:
            self.assertEqual([x.split(":")[0] for x in b.split("\n")[1:]], ["- " + x for x in labels])

    def test_rationale_labels_follow_the_rule(self):
        """F5: the skeleton's labels are the rule's, read from its fenced example, so renaming one there fails."""
        for state, contract in (("planned", {"reader": "Alex", "questions": ["Is anything due?"]}), ("exists", None)):
            lines = wiki.rationale_skeleton("20 Finance/Tax.md", state, {"professional": "CFO"}, contract).split("\n")
            self.assertEqual(lines[0], "### 20 Finance/Tax.md")
            self.assertEqual([x[2:].split(":")[0] for x in lines[1:]], rule_labels(self))

    def test_return_shape_and_checker(self):
        text = self.brief(*BRIEF_PAGES)
        shape = json.loads(re.search(r"```json\n(.*?)```", text, re.S).group(1))
        self.assertEqual([p["path"] for p in shape["pages"]], sorted(BRIEF_PAGES))
        self.assertEqual(set(shape["pages"][0]), {"path", "text", "rationale", "index_entry"})
        self.assertEqual(set(shape), {"pages", "open_questions", "check_result"})
        line = next(x.strip() for x in text.splitlines() if " check --root " in x)
        cmd = shlex.split(line)
        self.assertEqual((cmd[0], cmd[1], cmd[2]), ("python3", os.path.join(TOOLS, "wiki.py"), "check"))
        r = subprocess.run([sys.executable] + cmd[1:], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["problems"], 0)

    def test_return_shape_carries_what_step_4a_names(self):
        """wiki-onboarding step 4a lists what a drafting agent returns; the brief's JSON shape carries each item."""
        items = step_4a_items(self)
        self.assertEqual(sorted(items), sorted(STEP_4A), "%s step 4a's return list changed: carry each item in "
                                                         "wiki.return_shape and map it in STEP_4A" % ONBOARDING)
        text = self.brief(*BRIEF_PAGES)
        shape = json.loads(re.search(r"```json\n(.*?)```", text, re.S).group(1))
        for item in items:
            where, key = STEP_4A[item]
            with self.subTest(item=item):
                for holder in (shape["pages"] if where == "page" else [shape]):
                    self.assertIn(key, holder)

    def test_links_resolve_where_the_brief_is_read(self):
        text = self.brief(*BRIEF_PAGES)
        links = re.findall(r"\]\((/[^)#]+)(#[^)]*)?\)", text)
        self.assertEqual([(urllib.parse.unquote(p), a) for p, a in links],
                         [(RULE, "#the-core-wiki-rule"), (RULE, "#one-professional-per-page")])
        self.assertTrue(all(os.path.exists(urllib.parse.unquote(p)) for p, _a in links))

    def test_page_map_adds_planned_pages(self):
        os.remove(self.page("40 Study/40 Study.md"))
        os.remove(self.page("20 Finance/Tax.md"))
        text = self.brief("30 Home/30 Home.md")
        self.assertIn("- `40 Study/40 Study.md` (planned)", text)
        self.assertIn("- `20 Finance/Tax.md` (planned)", text)
        self.assertIn("- `30 Home/30 Home.md` (exists, in this brief)", text)
        self.assertEqual(len(re.findall(r"^- `[^`]+\.md` \(", text, re.M)), 12)

    def test_fixed_pages_take_the_method_shape(self):
        text = self.brief("00 Index/00 Index.md")
        self.assertIn("- Contract: the method's own, as a fixed section", text)
        self.assertIn("- Files routed to the section: none", text)
        self.assertIn("- Bundle: none: no carded document routes to this section", text)
        self.assertIn("- Reader and use: <who reads the page>, <what they use the page for>", text)

    def test_refusals(self):
        for page, why in (("99 Other/x.md", "in no section"), ("20 Finance/Savings.md", "list the page"),
                          ("../x.md", "not a page path"), ("20 Finance/Tax.txt", "not a page path")):
            with self.subTest(page=page):
                self.assertIn(why, self.refused("brief", "--page", page))
        schema = os.path.join(self.root, WIKI, "90 Schema", "90 Schema.md")
        text = read(schema)
        write(schema, re.sub(r"(?m)^\| 40 Study \(academic registrar\) \|.*\n", "", text))
        code, _out, err = run("settings.py", "compile", "--root", self.root, "--work", self.work)
        self.assertEqual(code, 0, err)
        self.ok("bundles", code=1)
        self.assertIn("section 40 Study has no page contract", self.refused("brief", "--page", "40 Study/40 Study.md"))

    def test_out(self):
        out = os.path.join(self.tmp, "brief.md")
        printed = self.ok("brief", "--page", BRIEF_PAGES[0], "--out", out)
        self.assertEqual(read(out), printed)
        inside = os.path.join(self.root, "brief.md")
        self.assertIn("never written inside the folder", self.refused("brief", "--page", BRIEF_PAGES[0], "--out",
                                                                      inside))
        self.assertFalse(os.path.exists(inside))


class MoveTest(Copy):
    MOVES = {"20 Finance/Tax.md": "25 Tax & Duty/Tax & returns.md",
             "30 Home/30 Home.md": "30 Home & Garden/30 Home & Garden.md",
             "02 People/02 People.md": "02 People/Contacts (all) & 联系人.md"}

    def move(self, moves, code=0, *args):
        path = os.path.join(self.tmp, "map.json")
        write(path, json.dumps(moves, ensure_ascii=False))
        return json.loads(self.ok("move", "--map", path, *args, code=code))

    def check(self):
        code, out, err = self.wiki("check")
        self.assertIn(code, (0, 1), err)
        return json.loads(out)

    def test_fixture_moves_leave_no_dead_links(self):
        self.assertEqual(self.check()["dead_page_links"], [])
        res = self.move(self.MOVES, code=1)
        self.assertEqual(res, {"moved": 3, "pages_rewritten": 6, "links_rewritten": 4, "folders_removed": ["30 Home"],
                               "rationale_blocks_renamed": 3,
                               "schema_rows_to_update": [["20 Finance/Tax.md", "25 Tax & Duty/Tax & returns.md"]],
                               "layout_to_update": [
                                   ["02 People/02 People.md", "02 People/Contacts (all) & 联系人.md",
                                    "the old path was section 02 People's folder note"],
                                   ["20 Finance/Tax.md", "25 Tax & Duty/Tax & returns.md",
                                    "the new path is in no Layout section"],
                                   ["30 Home/30 Home.md", "30 Home & Garden/30 Home & Garden.md",
                                    "the new path is in no Layout section"],
                                   ["30 Home/30 Home.md", "30 Home & Garden/30 Home & Garden.md",
                                    "the old path was section 30 Home's folder note"]],
                               "dead_links": []})
        self.assertIn("- [Tax](../25%20Tax%20&%20Duty/Tax%20&%20returns.md): the 2022",
                      read(self.page("20 Finance/20 Finance.md")))
        index = read(self.page("00 Index/00 Index.md"))
        self.assertIn("[30 Home](../30%20Home%20&%20Garden/30%20Home%20&%20Garden.md)", index)
        self.assertIn("[02 People](../02%20People/Contacts%20%28all%29%20&%20%E8%81%94%E7%B3%BB%E4%BA%BA.md)", index)
        self.assertIn("[10 Identity](../10%20Identity/10%20Identity.md)", index)  # unmoved: left as written
        for old, new in self.MOVES.items():
            self.assertFalse(os.path.exists(self.page(old)))
            self.assertTrue(os.path.exists(self.page(new)))
        res = self.check()
        self.assertEqual((res["dead_page_links"], res["rationale"]["pages_without_block"], res["pages"]), ([], [], 12))

    def test_links_from_a_moved_page(self):
        res = self.move({"00 Index/00 Index.md": "00 Index/Dashboards/Home & Index.md",
                         "20 Finance/20 Finance.md": "20 Finance/Overview.md"}, code=1)
        self.assertEqual((res["dead_links"], res["folders_removed"], res["links_rewritten"]), ([], [], 6))
        self.assertEqual([x[0] for x in res["layout_to_update"]], ["00 Index/00 Index.md", "20 Finance/20 Finance.md"])
        self.assertEqual(res["schema_rows_to_update"], [["20 Finance/20 Finance.md", "20 Finance/Overview.md"]])
        index = read(self.page("00 Index/Dashboards/Home & Index.md"))
        self.assertIn("[20 Finance](../../20%20Finance/Overview.md)", index)
        self.assertIn("[40 Study](../../40%20Study/40%20Study.md)", index)
        self.assertIn("- [Tax](Tax.md): the 2022", read(self.page("20 Finance/Overview.md")))
        self.assertEqual(self.check()["dead_page_links"], [])

    def test_refusals_change_nothing(self):
        before = tree_digest(self.root)
        for moves, why in (({"20 Finance/None.md": "20 Finance/X.md"}, "page not found"),
                           ({"20 Finance/Tax.md": "20 Finance/Bank accounts.md"}, "destination exists"),
                           ({"20 Finance/Tax.md": "20 Finance/X.md", "30 Home/30 Home.md": "20 Finance/X.md"},
                            "two pages moved to one destination"),
                           ({"20 Finance/Tax.md": "../Tax.md"}, "not a page path inside the wiki folder"),
                           ({"20 Finance/Tax.md": "20 Finance/.hidden/Tax.md"}, "not a page path"),
                           ({"90 Schema/90 Schema.md": "90 Schema/Schema.md"}, "is the Schema page"),
                           (["20 Finance/Tax.md"], "must be a JSON object")):
            with self.subTest(why=why):
                path = os.path.join(self.tmp, "map.json")
                write(path, json.dumps(moves))
                self.assertIn(why, self.refused("move", "--map", path))
        path = os.path.join(self.tmp, "map.json")
        write(path, json.dumps({"10 Identity/10 Identity.md": "10 Identity/Passport.md"}))
        self.assertIn("--read-only-root", self.refused("move", "--map", path, "--read-only-root"))
        self.assertEqual(tree_digest(self.root), before)


class DriftTest(Copy):
    def drift(self, code=0):
        return json.loads(self.ok("drift", code=code))

    def test_fixture_has_none(self):
        self.assertEqual(self.drift(), {"wiki": WIKI, "pages_read": 11, "departed_paths": 0, "migrating_paths": 2,
                                        "citing_departed": 0, "citing_migrating": 0, "pages_citing": 0,
                                        "departed": [], "migrating": []})

    def test_departed_and_migrating_citations(self):
        os.remove(os.path.join(self.root, "03 Home", "Lease notes .txt"))
        code, _out, err = run("audit.py", "--root", self.root, "--work", self.work)
        self.assertEqual(code, 0, err)
        cash = self.page("20 Finance/Cash position.md")
        self.edit(cash, '  - "02 Finance/Tax/Budget final.xlsx"\n',
                  '  - "02 Finance/Tax/Budget final.xlsx"\n  - "02 Finance/Old invoice.pdf"\n')
        self.edit(cash, "Planned monthly spending from",
                  "An old invoice, `_Migrations/Other Project/02 Finance/Old\ninvoice.pdf`, is leaving.\n\n"
                  "```text\n`02 Finance/Old invoice.pdf`\n```\n\nPlanned monthly spending from")
        with open(self.page("91 Log/91 Log.md"), "a", encoding="utf-8") as f:
            f.write("\n## [2024-07-01] ingest | `03 Home/Lease notes .txt`\n")
        lines = read(cash).split("\n")
        at = lines.index("An old invoice, `_Migrations/Other Project/02 Finance/Old") + 1
        home = read(self.page("30 Home/30 Home.md")).split("\n")
        notes = next(i for i, x in enumerate(home, 1) if "`03 Home/Lease notes .txt`" in x)
        res = self.drift(code=1)
        self.assertEqual({k: res[k] for k in ("departed_paths", "migrating_paths", "citing_departed",
                                              "citing_migrating", "pages_citing")},
                         {"departed_paths": 1, "migrating_paths": 2, "citing_departed": 1, "citing_migrating": 2,
                          "pages_citing": 2})
        self.assertEqual(res["departed"], [["30 Home/30 Home.md", notes, "03 Home/Lease notes .txt"]])
        self.assertEqual(res["migrating"], [["20 Finance/Cash position.md", 8, "withheld (held for another project)"],
                                            ["20 Finance/Cash position.md", at,
                                             "withheld (held for another project)"]])
        report = self.ok("drift", code=1)
        for named in ("Old invoice", "Other Project", "_Migrations"):
            self.assertNotIn(named, report, "the report names a document held for another project")
        self.assertIn("03 Home/Lease notes .txt", report, "a departed document that is not withheld is still named")

    def test_a_departed_document_under_an_excluded_path_is_named_as_withheld(self):
        os.remove(os.path.join(self.root, "03 Home", "Lease notes .txt"))
        code, _out, err = run("audit.py", "--root", self.root, "--work", self.work)
        self.assertEqual(code, 0, err)
        with open(self.page("30 Home/30 Home.md"), "a", encoding="utf-8") as f:
            f.write("\nSee also `03 Home/Lease notes .txt`.\n")
        twin = os.path.join(self.root, ".familyai", "rulebook.json")
        write(twin, json.dumps(dict(json.loads(read(twin)), exclude=["03 Home"]), ensure_ascii=False, indent=1))
        res = self.drift(code=1)
        self.assertEqual([c[2] for c in res["departed"]], ["withheld (excluded)", "withheld (excluded)"])
        self.assertNotIn("Lease notes", json.dumps(res))

    def test_an_edited_file_is_not_departed(self):
        with open(os.path.join(self.root, "03 Home", "Lease notes .txt"), "a", encoding="utf-8") as f:
            f.write("And the gutters.\n")
        code, _out, err = run("audit.py", "--root", self.root, "--work", self.work)
        self.assertEqual(code, 0, err)
        entries = json.loads(read(os.path.join(self.root, "_Audit", "manifest.json")))["entries"]
        self.assertEqual(sum("departed" in e["flags"] for e in entries.values()), 1)
        self.assertEqual(self.drift()["departed_paths"], 0)


class MoveSafetyTest(Copy):
    """A move is refused whole before it changes anything, written so a late failure strands no link, and it
    reports the Layout it leaves wrong."""

    def map(self, moves):
        path = os.path.join(self.tmp, "map.json")
        write(path, json.dumps(moves, ensure_ascii=False))
        return path

    def test_a_destination_under_a_file_is_refused_before_any_change(self):
        """F1: a destination below an existing file, or below a page the same map moves there."""
        before = tree_digest(self.root)
        for moves, why in (({"20 Finance/Bank accounts.md": "20 Finance/Tax.md/x.md"},
                            "lies under 20 Finance/Tax.md, which is a file"),
                           ({"20 Finance/Bank accounts.md": "25 Money/Accounts.md",
                             "20 Finance/Cash position.md": "25 Money/Accounts.md/Cash.md"},
                            "lies under 25 Money/Accounts.md, which is a page this map moves there")):
            with self.subTest(why=why):
                self.assertIn(why, self.refused("move", "--map", self.map(moves)))
                self.assertEqual(tree_digest(self.root), before)

    def test_a_destination_under_a_symbolic_link_is_refused_before_any_change(self):
        """A folder in the wiki that is a link could lead outside it: the page would be written there."""
        outside = os.path.join(self.tmp, "elsewhere")
        os.makedirs(outside)
        os.symlink(outside, os.path.join(self.root, WIKI, "30 Home", "escape"))
        before = tree_digest(self.root)
        err = self.refused("move", "--map", self.map({"20 Finance/Tax.md": "30 Home/escape/Tax.md"}))
        self.assertIn("lies under 30 Home/escape, which is a symbolic link", err)
        self.assertEqual((tree_digest(self.root), os.listdir(outside)), (before, []))

    def test_a_wiki_folder_that_is_a_symbolic_link_is_refused(self):
        real = os.path.join(self.tmp, "real wiki")
        os.rename(os.path.join(self.root, WIKI), real)
        os.symlink(real, os.path.join(self.root, WIKI))
        before = tree_digest(real)
        err = self.refused("move", "--map", self.map({"20 Finance/Tax.md": "20 Finance/Tax 2.md"}))
        self.assertIn("is a symbolic link", err)
        self.assertEqual(tree_digest(real), before)

    def test_moved_pages_are_written_first(self):
        """F1: a run that fails after its first write leaves every link resolving, because the moved page is written
        before any page linking to it is rewritten."""
        written = []

        class FailSecond(common.Writer):
            def text(self, path, text):
                if path.endswith(".md") and len(written) == 1:
                    raise common.ToolError("injected failure")
                written.append(path)
                super().text(path, text)
        a = argparse.Namespace(root=self.root, settings_dir=None, work=self.work, manifest=None, read_only_root=False,
                               map=self.map({"20 Finance/Bank accounts.md": "25 Banking/Bank accounts.md"}))
        with unittest.mock.patch.object(wiki.common, "Writer", FailSecond):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(common.ToolError):
                wiki.move(a)
        wiki_dir = os.path.join(self.root, WIKI)
        self.assertEqual(written, [os.path.join(wiki_dir, "25 Banking", "Bank accounts.md")])
        self.assertEqual(wiki.dead_links(wiki_dir), [])
        self.assertTrue(os.path.exists(self.page("20 Finance/Bank accounts.md")))

    def test_a_layout_left_wrong_is_reported(self):
        """F2: a section's folder note moved away and a page moved out of every section are reported, exit 1."""
        code, out, err = self.wiki("move", "--map", self.map({"30 Home/30 Home.md":
                                                               "30 Home & Garden/30 Home & Garden.md"}))
        self.assertEqual(code, 1, out + err)
        self.assertEqual(json.loads(out)["layout_to_update"], [
            ["30 Home/30 Home.md", "30 Home & Garden/30 Home & Garden.md", "the new path is in no Layout section"],
            ["30 Home/30 Home.md", "30 Home & Garden/30 Home & Garden.md",
             "the old path was section 30 Home's folder note"]])
        self.assertIn("edit the Layout, then settings.py compile", err)

    def test_a_move_inside_its_section_is_clean(self):
        write(self.page("30 Home/Bills.md"), "---\nprovenance: derived\nlast-updated: 2024-06-30\nstatus: current\n"
                                             "---\n# Bills\n\nSee [Home](30%20Home.md).\n")
        res = json.loads(self.ok("move", "--map", self.map({"30 Home/Bills.md": "30 Home/Utility bills.md"})))
        self.assertEqual((res["layout_to_update"], res["schema_rows_to_update"], res["dead_links"]), ([], [], []))

    def test_control_characters_are_refused(self):
        """Re-review 2: a NUL, tab or newline in any part of a page path."""
        before = tree_digest(self.root)
        for new in ("20 Finance/Tax\u00002.md", "20 Finance/Tax\t2.md", "20 Fin\nance/Tax 2.md",
                    "20 Finance/Tax\x7f.md"):
            with self.subTest(new=repr(new)):
                err = self.refused("move", "--map", self.map({"20 Finance/Tax.md": new}))
                self.assertIn("holding a control character", err)
        self.assertEqual(tree_digest(self.root), before)
        self.ok("bundles", code=1)
        self.assertIn("not a page path", self.refused("brief", "--page", "20 Finance/Tax\t.md"))

    def test_a_swap_takes_three_runs(self):
        """Re-review 3: the tool reference's swap, A to T, then B to A, then T to B; the old two-run recipe is
        refused."""
        self.assertIn("(A to T, then B to A, then T to B)",
                      read(os.path.join(TOOLS, "..", "references", "tools.md")))
        head = "---\nprovenance: derived\nlast-updated: 2024-06-30\nstatus: current\n---\n"
        write(self.page("30 Home/Bills.md"), head + "# Bills\n\n[Repairs](Repairs.md)\n")
        write(self.page("30 Home/Repairs.md"), head + "# Repairs\n\n[Bills](Bills.md)\n")
        a, b, t = "30 Home/Bills.md", "30 Home/Repairs.md", "30 Home/Swap.md"
        self.assertIn("destination exists: %s" % b, self.refused("move", "--map", self.map({a: b, b: a})))
        self.assertIn("destination exists: %s" % a, self.refused("move", "--map", self.map({a: t, b: a})))
        for step in ({a: t}, {b: a}, {t: b}):
            res = json.loads(self.ok("move", "--map", self.map(step)))
            self.assertEqual(res["dead_links"], [])
        self.assertEqual((read(self.page(a)).split("---\n")[2], read(self.page(b)).split("---\n")[2]),
                         ("# Repairs\n\n[Bills](Repairs.md)\n", "# Bills\n\n[Repairs](Bills.md)\n"))
        self.assertFalse(os.path.exists(self.page(t)))

    def test_case_only_clashes_are_refused(self):
        """Re-review 4: a destination differing only in case from a page, another destination or a folder."""
        before = tree_digest(self.root)
        acc, cash = "20 Finance/Bank accounts.md", "20 Finance/Cash position.md"
        # on a case-insensitive file system (macOS by default) the name is taken outright
        taken = os.path.exists(self.page("20 Finance/tax.md"))
        for moves, why in (({acc: "20 Finance/tax.md"}, "destination exists: 20 Finance/tax.md" if taken else
                            "20 Finance/tax.md differs only in case from the page 20 Finance/Tax.md"),
                           ({acc: "25 Tax/A.md", cash: "25 Tax/a.md"}, "destinations 25 Tax/A.md and 25 Tax/a.md "
                                                                       "differ only in case"),
                           ({acc: "25 Tax/A.md", cash: "25 tax/B.md"}, "its folder 25 Tax differs only in case "
                                                                       "from the folder 25 tax"),
                           ({acc: "20 finance/Accounts.md"}, "its folder 20 finance differs only in case from the "
                                                             "folder 20 Finance")):
            with self.subTest(why=why):
                self.assertIn(why, self.refused("move", "--map", self.map(moves)))
        self.assertEqual(tree_digest(self.root), before)
        write(self.page("30 Home/Bills.md"), "---\nprovenance: derived\nlast-updated: 2024-06-30\nstatus: current\n"
                                             "---\n# Bills\n")
        if os.path.exists(self.page("30 Home/bills.md")):  # a case-insensitive file system: the name is taken
            self.assertIn("destination exists", self.refused("move", "--map", self.map(
                {"30 Home/Bills.md": "30 Home/bills.md"})))
        else:  # a case-only rename of the page itself stays possible
            self.ok("move", "--map", self.map({"30 Home/Bills.md": "30 Home/bills.md"}))
            self.assertEqual(sorted(os.listdir(self.page("30 Home"))), ["30 Home.md", "bills.md"])

    def test_spaces_at_either_end_of_a_part_are_refused(self):
        """F8: in a destination and in a briefed page."""
        for new in (" 20 Finance/Tax 2.md", "20 Finance /Tax 2.md", "20 Finance/ Tax 2.md"):
            with self.subTest(new=new):
                self.assertIn("not a page path", self.refused("move", "--map", self.map({"20 Finance/Tax.md": new})))
        self.ok("bundles", code=1)
        for page in ("20 Finance/ Tax.md", "20 Finance /Tax.md"):
            with self.subTest(page=page):
                self.assertIn("not a page path", self.refused("brief", "--page", page))


class MalformedInputTest(Copy):
    """F3: malformed input is refused by name (exit 2), never with a traceback."""

    def setUp(self):
        super().setUp()
        self.ok("bundles", code=1)
        self.meta = os.path.join(self.bundles_dir(), "bundles.json")
        self.ids = {e["current_path"]: h for h, e in json.loads(read(MANIFEST))["entries"].items()}

    def consumers(self, why):
        for cmd, args in (("brief", ["--page", BRIEF_PAGES[0]]), ("bundles", ["--reuse"])):
            with self.subTest(cmd=cmd, why=why):
                self.assertIn(why, self.refused(cmd, *args))

    def test_bundles_json(self):
        good = json.loads(read(self.meta))
        write(self.meta, "[]")
        self.consumers("expected a JSON object")
        for key in ("sections", "compact", "files", "withheld_sha256", "excluded", "held_for_another_project"):
            write(self.meta, json.dumps({k: v for k, v in good.items() if k != key}))
            self.consumers("not a bundles.json that wiki.py bundles wrote (%s missing or malformed)" % key)
        write(self.meta, json.dumps(dict(good, sections={"20": "six"})))
        self.consumers("(sections missing or malformed)")

    def test_bundles_json_is_a_directory(self):
        os.remove(self.meta)
        os.makedirs(self.meta)
        self.consumers("cannot read %s" % self.meta)
        self.assertIn("is a directory; bundles.json must be a file", self.refused("bundles"))

    def test_bundles_out_is_a_file(self):
        path = os.path.join(self.tmp, "a-file")
        write(path, "x\n")
        self.assertIn("is a file; bundles go in a directory", self.refused("bundles", "--out", path))

    def test_manifest(self):
        path = os.path.join(self.root, "_Audit", "manifest.json")
        entries = json.loads(read(MANIFEST))["entries"]
        entries[self.ids["06 Work/Contract.docx"]].pop("current_path")
        for text, why in (("{}", 'has no "entries" object'), ("[]", "expected a JSON object"),
                          (json.dumps({"entries": entries}), "is malformed: it needs a current_path")):
            write(path, text)
            for cmd, args in (("profile", []), ("bundles", []), ("brief", ["--page", BRIEF_PAGES[0]]),
                              ("drift", []), ("check", [])):
                with self.subTest(cmd=cmd, why=why):
                    self.assertIn(why, self.refused(cmd, *args))

    def test_a_card_that_is_not_an_object(self):
        card = os.path.join(self.root, "_Audit", "cards", self.ids["02 Finance/Bank statement 2024-03.pdf"] + ".json")
        for text, why in (("[]", "expected a JSON object"), ('{"parties": "Robin"}', "parties must be a list of text")):
            write(card, text)
            for cmd in ("profile", "bundles"):
                with self.subTest(cmd=cmd, why=why):
                    err = self.refused(cmd)
                    self.assertIn("malformed card: %s" % card, err)
                    self.assertIn(why, err)

    def test_an_extract_page_of_the_wrong_shape(self):
        """Re-review 1: a page whose n is not a whole number (null included: `full_text` would crash on it) or
        whose text is not text or null."""
        doc = self.ids["06 Work/Contract.docx"]
        path = os.path.join(self.root, "_Audit", "extract", doc + ".json")
        for page in ({"n": 1, "text": 123}, {"n": "1", "text": "hi"}, {"n": True, "text": "hi"},
                     {"n": None, "text": "hi"}, "page one"):
            with self.subTest(page=page):
                write(path, json.dumps({"id": doc, "pages": [{"n": 1, "text": "fine"}, page]}))
                err = self.refused("bundles")
                self.assertIn("malformed extract record %s: page 2 must be an object whose n is a whole number" % path,
                              err)
                self.assertIn("extract the document again", err)
        write(path, json.dumps({"id": doc, "pages": [{"text": None}, {"n": 2, "text": "Contract"}]}))
        self.ok("bundles", code=1)

    def test_an_extract_record_that_is_not_its_documents_is_refused(self):
        """A record is named by its document's hash and carries it as `id`: the rule `extract.py repath` holds it to."""
        doc = self.ids["06 Work/Contract.docx"]
        path = os.path.join(self.root, "_Audit", "extract", doc + ".json")
        for record, shown in (({"id": "x", "pages": []}, "'x'"), ({"pages": []}, "None"),
                              ({"id": 5, "pages": []}, "5")):
            with self.subTest(shown=shown):
                write(path, json.dumps(record))
                err = self.refused("bundles")
                self.assertIn("malformed extract record %s: its id is %s, not %s" % (path, shown, doc), err)
                self.assertIn("extract the document again", err)

    def test_cards_or_extract_naming_a_file(self):
        """Re-review 7."""
        path = os.path.join(self.tmp, "a-file")
        write(path, "x\n")
        for cmd, flag, kind in (("profile", "--cards", "card"), ("bundles", "--cards", "card"),
                                ("bundles", "--extract", "extract")):
            with self.subTest(cmd=cmd, flag=flag):
                self.assertIn("%s %s is a file, not a folder of %s records" % (flag, path, kind),
                              self.refused(cmd, flag, path))


class RebuildTest(Copy):
    def test_a_failed_rebuild_leaves_no_bundles_json(self):
        """F7: the rebuild removes bundles.json first, so one failing part way leaves none, and brief refuses."""
        self.ok("bundles", code=1)
        self.brief(BRIEF_PAGES[0])
        ids = {e["current_path"]: h for h, e in json.loads(read(MANIFEST))["entries"].items()}
        write(os.path.join(self.root, "_Audit", "cards", ids["06 Work/Essay.docx"] + ".json"), "[]")
        self.assertIn("malformed card", self.refused("bundles"))
        self.assertFalse(os.path.exists(os.path.join(self.bundles_dir(), "bundles.json")))
        self.assertIn("no bundles in", self.refused("brief", "--page", BRIEF_PAGES[0]))

    def test_the_rebuild_command_repeats_the_build_arguments(self):
        """F10: non-default arguments are recorded in bundles.json and echoed in the rebuild command."""
        audit = os.path.join(self.root, "_Audit")
        given = [("--settings-dir", os.path.join(self.root, ".familyai")),
                 ("--manifest", os.path.join(audit, "manifest.json")), ("--cards", os.path.join(audit, "cards")),
                 ("--extract", os.path.join(audit, "extract")), ("--text-cap", "500")]
        self.ok("bundles", *[x for kv in given for x in kv], code=1)
        meta = json.loads(read(os.path.join(self.bundles_dir(), "bundles.json")))
        self.assertEqual(list(meta["arguments"].items()), given)
        write(given[1][1], read(given[1][1]) + "\n")
        command = "rebuild them: wiki.py bundles " + " ".join(shlex.quote(x) for x in [
            "--root", self.root, "--out", self.bundles_dir()] + [x for kv in given for x in kv])
        for cmd, args in (("bundles", ["--reuse"]), ("brief", ["--page", BRIEF_PAGES[0]])):
            with self.subTest(cmd=cmd):
                self.assertIn(command, self.refused(cmd, *args))
        self.assertEqual(json.loads(read(os.path.join(GOLDEN, "bundles", "bundles.json")))["arguments"], {})

    def test_reuse_refuses_other_cards_extract_or_text_cap(self):
        """Re-review 6: bundles --reuse compares the caller's --cards, --extract and --text-cap with the build's."""
        self.ok("bundles", code=1)
        audit = os.path.join(self.root, "_Audit")
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        for args, why in ((["--text-cap", "500"], "built with --text-cap 12000, not 500"),
                          (["--cards", other], "built with --cards %s, not %s" % (os.path.join(audit, "cards"), other)),
                          (["--extract", other], "built with --extract %s, not %s"
                           % (os.path.join(audit, "extract"), other))):
            with self.subTest(args=args):
                err = self.refused("bundles", "--reuse", *args)
                self.assertIn(why, err)
                self.assertIn("rebuild them: wiki.py bundles", err)
        self.ok("bundles", "--reuse", "--cards", os.path.join(audit, "cards"), "--text-cap", "12000", code=1)


class FenceTest(unittest.TestCase):
    def test_inline_code_is_not_a_fence(self):
        """F6: citations opens a fence by the rule chart_blocks reads fences with, and reads code spans of any
        backtick run."""
        text = "\n".join([
            "---", "sources:", '  - "a"', "---", "# P", "",
            "```inline``` `03 Home/Lease notes .txt`", "",
            "Later: `03 Home/Lease notes .txt`", "",
            "````", "```", "`inside a fence`", "````", "",
            "After: `x/y.pdf`", "",
            "  ~~~ text", "`in a tilde fence`", "  ~~~", "",
            "End ``z `pdf` z`` and `z.pdf`", ""])
        self.assertEqual(wiki.citations(text), [
            (3, "a"), (7, "03 Home/Lease notes .txt"), (7, "inline"), (9, "03 Home/Lease notes .txt"),
            (16, "x/y.pdf"), (22, "z `pdf` z"), (22, "z.pdf")])


class TemplatesTest(unittest.TestCase):
    """Every stage template names its stage and pen, links the core wiki rule rather than restating it, fills as a
    format string, and holds no em dash and no line over 120 columns."""

    def test_templates(self):
        for name in TEMPLATES:
            with self.subTest(name=name):
                text = read(os.path.join(TOOLS, "templates", name))
                self.assertTrue(text.startswith("<!-- Stage"), name)
                self.assertIn("**Pen:**", text)
                self.assertIn("](../../../wiki-maintenance/SKILL.md#the-core-wiki-rule)", text)
                self.assertNotIn("\u2014", text)
                self.assertTrue(all(len(x) <= 120 for x in text.splitlines()))
                fields = {f for _l, f, _s, _c in string.Formatter().parse(text) if f}
                text.format(**{f: "x" for f in fields})
                for m in re.finditer(r"\]\((\.\.?/[^)#\s]+)(?:#([^)\s]+))?\)", text):
                    target = os.path.normpath(os.path.join(TOOLS, "templates", m.group(1)))
                    self.assertTrue(os.path.exists(target), target)
                    if m.group(2):
                        slugs = {re.sub(r"[^a-z0-9 -]", "", h.strip().lower()).replace(" ", "-")
                                 for h in re.findall(r"(?m)^#+ (.+)$", read(target))}
                        self.assertIn(m.group(2), slugs, target)
        self.assertEqual(sorted(TEMPLATES), sorted(n for n in os.listdir(os.path.join(TOOLS, "templates"))
                                                   if n != "card-instructions.md"))


def update():
    """Rewrite golden/wiki/ from a fresh fixture copy."""
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="wiki_tools_update_"))
    try:
        root = make_copy(os.path.join(tmp, "a"))
        work = os.path.join(tmp, "a", "work")
        folder = ["--root", root, "--work", work]
        code, profile, err = run("wiki.py", "profile", *folder)
        if code:
            raise SystemExit(err)
        write(os.path.join(GOLDEN, "profile.json"), profile)
        code, _out, err = run("wiki.py", "bundles", *folder)
        if code not in (0, 1):
            raise SystemExit(err)
        shutil.rmtree(os.path.join(GOLDEN, "bundles"), True)
        shutil.copytree(os.path.join(work, "bundles"), os.path.join(GOLDEN, "bundles"))
        code, brief, err = run("wiki.py", "brief", *folder, *[x for p in BRIEF_PAGES for x in ("--page", p)])
        if code:
            raise SystemExit(err)
        write(os.path.join(GOLDEN, "brief.md"), normalise(brief, tmp))
    finally:
        shutil.rmtree(tmp, True)
    print("updated")


if __name__ == "__main__":
    if sys.argv[1:] == ["--update"]:
        update()
    else:
        unittest.main()
