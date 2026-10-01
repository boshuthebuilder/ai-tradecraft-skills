"""The deterministic audit on fixture copies and small synthetic folders: copy kinds, overlaps, generic names, the
unconverted iWork pairing, hygiene, root strays, migrating files, departed entries, drift, and a byte comparison
with the frozen outputs in expected/.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests
"""
import csv
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

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
FIXTURE = os.path.join(HERE, "fixture", "Alex Personal")
EXPECTED = os.path.join(HERE, "expected")
NOW = 1719748800            # 2024-06-30T12:00:00Z, the frozen clock of expected/
MTIME = 1717200000          # 2024-06-01T00:00:00Z, the fixed modification time of expected/
sys.path.insert(0, TOOLS)
import audit  # noqa: E402
import common  # noqa: E402

# audit.py shown one file under a long name: argv is tools dir, long name, the file's name on disk, audit arguments.
LONG_NAME = """
import builtins
import os
import sys
sys.path.insert(0, sys.argv[1])
import audit
import common
long_name, short_name = sys.argv[2], sys.argv[3]
real_walk, real_stat, real_open = os.walk, os.stat, builtins.open


def disk(p):
    return p[:-len(long_name)] + short_name if isinstance(p, str) and p.endswith(long_name) else p


def walk(top, *a, **k):
    for d, ds, fs in real_walk(top, *a, **k):
        yield d, ds, [long_name if f == short_name else f for f in fs]


os.walk = walk
os.stat = lambda p, *a, **k: real_stat(disk(p), *a, **k)
builtins.open = lambda p, *a, **k: real_open(disk(p), *a, **k)
sys.argv = ["audit.py"] + sys.argv[4:]
common.run_main(audit.main)
"""


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data.encode("utf-8") if isinstance(data, str) else data)


def run(tool, *args, now=NOW, script=None):
    """Run a tool (or a `script` driving it) with a frozen clock and every ResourceWarning an error; a file it leaves
    open fails the test."""
    env = dict(os.environ, PRE_ONBOARDING_NOW=str(now), PYTHONWARNINGS="error::ResourceWarning")
    cmd = [sys.executable, "-c", script, TOOLS] if script else [sys.executable, os.path.join(TOOLS, tool)]
    r = subprocess.run(cmd + list(args), capture_output=True, text=True, env=env)
    if "ResourceWarning" in r.stderr:
        raise AssertionError("%s left a file open:\n%s" % (tool, r.stderr[-2000:]))
    return r.returncode, r.stdout, r.stderr


def tree_digest(root):
    h = hashlib.sha256()
    for d, ds, fs in os.walk(root):
        ds.sort()
        for f in sorted(fs):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode() + b"\0" + read(p, "rb") + b"\n")
    return h.hexdigest()


def kinds(manifest):
    """path -> copy kind for every path in a duplicate group."""
    return {c["path"]: c["kind"] for e in manifest["entries"].values() for c in e.get("copies", [])}


def by_path(manifest):
    """current path -> live entry (a departed entry keeps the path it was last seen at)."""
    return {e["current_path"]: e for e in manifest["entries"].values() if "departed" not in e["flags"]}


def kinds_list(manifest):
    return [c for e in manifest["entries"].values() for c in e.get("copies", [])]


class AuditCase(unittest.TestCase):
    """Each test audits its own copies in a temp dir; the committed fixture is never touched."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="audit_test_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def fixture(self, parent="a"):
        """A copy of the fixture with the fixed modification times expected/ was made with."""
        root = os.path.join(self.tmp, parent, "Alex Personal")
        shutil.copytree(FIXTURE, root)
        for d, ds, fs in os.walk(root):
            for n in ds + fs:
                os.utime(os.path.join(d, n), (MTIME, MTIME), follow_symlinks=False)
        os.utime(root, (MTIME, MTIME))
        return root

    def folder(self, files, parent="s", name="Alex Papers"):
        """A synthetic folder with no settings twins (the defaults apply): {relative path: text or bytes}."""
        root = os.path.join(self.tmp, parent, name)
        os.makedirs(root)
        for rel, data in files.items():
            write(os.path.join(root, rel), data)
        return root

    def pinned(self, **settings):
        """A rulebook and its twin pinned to it, carrying `settings`, as files for folder()."""
        rulebook = "# Rules\n\nThe owner's rules for this folder.\n"
        twin = dict(settings, version=1, rulebook_sha256=hashlib.sha256(rulebook.encode()).hexdigest())
        return {"CLAUDE.md": rulebook, ".familyai/rulebook.json": json.dumps(twin)}

    def out(self, root):
        return os.path.join(os.path.dirname(root), "out")

    def audit(self, root, now=NOW):
        """Audit with the outputs beside the folder (never inside it); returns the manifest."""
        out = self.out(root)
        code, _o, err = run("audit.py", "--root", root, "--work", os.path.join(os.path.dirname(root), "work"),
                            "--out", out, "--read-only-root", now=now)
        self.assertEqual(code, 0, err)
        return json.loads(read(os.path.join(out, "manifest.json")))

    def summary(self, root):
        return json.loads(read(os.path.join(self.out(root), "summary.json")))

    def report(self, root):
        return read(os.path.join(self.out(root), "AUDIT.md"))


class ExpectedOutputTest(AuditCase):
    def test_byte_identical_to_expected(self):
        root = self.fixture()
        before = tree_digest(root)
        self.audit(root)
        for name in ("manifest.json", "AUDIT.md", "summary.json"):
            with self.subTest(name):
                self.assertEqual(read(os.path.join(self.out(root), name), "rb"),
                                 read(os.path.join(EXPECTED, name), "rb"))
        self.assertEqual(tree_digest(root), before, "the audit wrote inside the folder")

    def test_a_second_pass_keeps_the_manifest_and_reports_no_drift(self):
        """Same content; the bytes may differ, as a merged entry keeps its previous key order."""
        root = self.fixture()
        first = self.audit(root)
        self.assertEqual(self.audit(root), first)
        self.assertEqual(self.summary(root)["drift"], {"added": 0, "departed": 0, "moved": 0, "edited": 0})
        self.assertIn("Added 0, departed 0, moved 0, edited 0.", self.report(root))

    def test_read_only_root_refuses_the_default_out(self):
        root = self.fixture()
        before = tree_digest(root)
        code, _o, err = run("audit.py", "--root", root, "--work", os.path.join(self.tmp, "work"),
                            "--read-only-root")
        self.assertEqual(code, 2)
        self.assertIn("--read-only-root", err)
        self.assertEqual(tree_digest(root), before)

    def test_a_foreign_manifest_is_refused(self):
        root = self.fixture()
        write(os.path.join(self.out(root), "manifest.json"), json.dumps({"schema": "someone-else/1", "entries": {}}))
        code, _o, err = run("audit.py", "--root", root, "--work", os.path.join(self.tmp, "work"), "--out",
                            self.out(root), "--read-only-root")
        self.assertEqual(code, 2)
        self.assertIn("foreign manifest schema", err)


class CopyKindsTest(AuditCase):
    def test_the_fixture_copy_kinds(self):
        m = self.audit(self.fixture())
        self.assertEqual(kinds(m), {
            "02 Finance/Bank statement 2024-03.pdf": "canonical",
            "02 Finance/Bank statement 2024-03 (1).pdf": "redundant",        # same folder
            "04 Study/Cours de français.pdf": "canonical",
            "05 Archive/Cours de français.pdf": "redundant",                  # a parallel tree
            "04 Study/中文课程.pdf": "canonical",
            "05 Archive/中文课程.pdf": "redundant",
            "04 Study/Slides.pptx": "canonical",
            "05 Archive/Slides.pptx": "redundant",
            "06 Work/Essay.docx": "canonical",                                # the shortest path wins
            "04 Study/Essay.docx": "working_copy",
            "05 Archive/Essay.docx": "working_copy",
            "01 Identity/Passport scan.pdf": "canonical",
            "01 Identity/Passport renewal 2021/Passport scan.pdf": "pack",    # never a delete candidate
        })
        self.assertEqual(self.summary(os.path.join(self.tmp, "a", "Alex Personal"))["copy_kinds"],
                         {"canonical": 6, "pack": 1, "redundant": 4, "working_copy": 2})

    def test_the_canonical_copy(self):
        """A name marked as a copy loses, then the shallower path, then the shorter, then the first by name."""
        m = self.audit(self.folder({
            "Report copy.pdf": "one", "Deep/Deeper/Report.pdf": "one",
            "Top/Letter.pdf": "two", "Top/Sub/Letter.pdf": "two",
            "Longer name/Note.txt": "three", "Short/Note.txt": "three",
            "B/Same.txt": "four", "A/Same.txt": "four",
            "Scan (2).pdf": "five", "Folder/Scan.pdf": "five",
        }))
        canon = {c["path"] for c in kinds_list(m) if c["kind"] == "canonical"}
        self.assertEqual(canon, {"Deep/Deeper/Report.pdf", "Top/Letter.pdf", "Short/Note.txt", "A/Same.txt",
                                 "Folder/Scan.pdf"})
        self.assertEqual({e["current_path"] for e in m["entries"].values()}, canon)

    def test_redundant_by_folder_similarity(self):
        """A copy in another folder is redundant only when its folder holds 3 or more contents and 80% or more of
        them are also in the canonical copy's folder; otherwise it is a working copy."""
        m = self.audit(self.folder({
            "A/1.txt": "one", "A/2.txt": "two", "A/3.txt": "three", "A/4.txt": "four",
            "B/1.txt": "one", "B/2.txt": "two", "B/3.txt": "three",                          # 3 of 3
            "C/1.txt": "one", "C/2.txt": "two",                                               # only 2
            "D/1.txt": "one", "D/2.txt": "two", "D/3.txt": "three", "D/x.txt": "x", "D/y.txt": "y",  # 3 of 5
        }))
        k = kinds(m)
        self.assertEqual({p: k[p] for p in k if p.startswith("B/")}, {"B/1.txt": "redundant", "B/2.txt": "redundant",
                                                                      "B/3.txt": "redundant"})
        self.assertEqual({k[p] for p in k if p[0] in "CD"}, {"working_copy"})

    def test_a_pack_by_keyword(self):
        m = self.audit(self.folder({"Letters/Form.pdf": "form", "Letters/Visa application 2023/Form.pdf": "form",
                                    "Letters/Holiday 2023/Form.pdf": "form"}))
        k = kinds(m)
        self.assertEqual(k["Letters/Visa application 2023/Form.pdf"], "pack")
        self.assertEqual(k["Letters/Holiday 2023/Form.pdf"], "working_copy")

    def test_the_pack_keywords_are_generic_and_a_folder_can_add_its_own(self):
        self.assertEqual(common.DEFAULTS["pack_keywords"],
                         ["application", "passport", "renew", "visa", "submission", "evidence"])
        files = {"Letters/Form.pdf": "form", "Letters/Settlement 2020/Form.pdf": "form"}
        self.assertEqual(kinds(self.audit(self.folder(files, parent="plain")))["Letters/Settlement 2020/Form.pdf"],
                         "working_copy")
        own = dict(self.pinned(pack_keywords=["settlement"]), **files)
        self.assertEqual(kinds(self.audit(self.folder(own, parent="own")))["Letters/Settlement 2020/Form.pdf"], "pack")

    def loan_letters(self, parent, packs):
        """Three payslips, copied into a loan pack named without a keyword and into a folder named like it."""
        files = self.pinned(packs=packs)
        for n in (1, 2, 3):
            for folder in ("Letters", "Letters/Loan 2022", "Letters/Loan 2022 old"):
                files["%s/Payslip %d.pdf" % (folder, n)] = "payslip %d" % n
        root = self.folder(files, parent=parent)
        k = kinds(self.audit(root))
        plan_dir = os.path.join(self.tmp, parent, "plan")
        code, _o, err = run("plan.py", "light", "--root", root, "--manifest",
                            os.path.join(self.out(root), "manifest.json"), "--out", plan_dir)
        self.assertEqual(code, 0, err)
        with open(os.path.join(plan_dir, "move-plan.csv"), encoding="utf-8", newline="") as f:
            deletes = sorted(r["from"] for r in csv.DictReader(f) if r["action"] == "delete")
        return k, deletes

    def test_a_pack_the_rulebook_lists(self):
        """Listed, with or without a trailing /, its copies are packs and never proposed for deletion; a folder
        whose name only starts with the pack's name is not in it."""
        old = ["Letters/Loan 2022 old/Payslip %d.pdf" % n for n in (1, 2, 3)]
        for n, listed in enumerate(("Letters/Loan 2022", "Letters/Loan 2022/")):
            with self.subTest(listed=listed):
                k, deletes = self.loan_letters("listed%d" % n, [listed])
                self.assertEqual({p: k[p] for p in k if p.startswith("Letters/Loan 2022/")},
                                 {"Letters/Loan 2022/Payslip %d.pdf" % i: "pack" for i in (1, 2, 3)})
                self.assertEqual({k[p] for p in old}, {"redundant"})
                self.assertEqual(deletes, old)

    def test_the_same_copies_unlisted_are_redundant(self):
        k, deletes = self.loan_letters("unlisted", [])
        self.assertEqual({k["Letters/Loan 2022/Payslip %d.pdf" % n] for n in (1, 2, 3)}, {"redundant"})
        self.assertEqual(len(deletes), 6)

    def test_an_iwork_package_is_one_item_hashed_over_its_members(self):
        root = self.fixture()
        m = self.audit(root)
        pkg = os.path.join(root, "03 Home", "Lease renewal.pages")
        e = by_path(m)["03 Home/Lease renewal.pages"]
        self.assertEqual(e["id"], common.sha256_package(pkg))
        self.assertTrue(e["package"])
        self.assertEqual(e["size"], sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(pkg) for f in fs))
        self.assertFalse(any("Lease renewal.pages/" in p for p in by_path(m)))


class OverlapTest(AuditCase):
    def test_overlapping_homes_need_three_shared_contents(self):
        root = self.fixture()
        m = self.audit(root)
        self.assertEqual(self.summary(root)["overlaps"], {"04 Study <> 05 Archive": 4})
        overlapping = sorted(e["current_path"] for e in m["entries"].values() if e.get("overlap"))
        self.assertEqual(overlapping, ["04 Study/Cours de français.pdf", "04 Study/Slides.pptx",
                                       "04 Study/中文课程.pdf", "06 Work/Essay.docx"])
        self.assertIn("- 04 Study <> 05 Archive: 4 shared contents", self.report(root))

    def test_two_shared_contents_are_not_an_overlap(self):
        root = self.folder({"A/1.txt": "one", "A/2.txt": "two", "B/1.txt": "one", "B/2.txt": "two"})
        m = self.audit(root)
        self.assertEqual(self.summary(root)["overlaps"], {})
        self.assertFalse(any(e.get("overlap") for e in m["entries"].values()))


class GenericNameTest(AuditCase):
    def test_generic_stems(self):
        for stem in ("IMG_0001", "IMG_0001 (1)", "DSC01234", "Screenshot 2024-01-02 at 10.11.12",
                     "Screen Shot 2019-03-04 at 1.02.03 PM", "Scan", "Scanned Document 3", "Document (2)", "untitled",
                     "Photo 12 copy", "12345", "2024-01-02", "微信图片_20240101",
                     "WhatsApp Image 2024-01-02 at 10.11.12"):
            with self.subTest(stem):
                self.assertTrue(audit.is_generic(stem))
        for stem in ("Imagine", "Scanned tax return", "Photo of Robin", "Passport scan", "Document final",
                     "Bank statement 2024-03", "12"):
            with self.subTest(stem):
                self.assertFalse(audit.is_generic(stem))

    def test_the_fixture_camera_name(self):
        root = self.fixture()
        m = self.audit(root)
        self.assertEqual([e["current_path"] for e in m["entries"].values() if e.get("generic_name")],
                         ["IMG_0001.jpg"])
        self.assertEqual(self.summary(root)["generic_by_folder"], {"(root)": 1})


class UnconvertedTest(AuditCase):
    def test_stems(self):
        self.assertEqual(audit.norm_stem("Lease renewal"), "leaserenewal")
        self.assertEqual(audit.norm_stem("Café Notes"), "cafénotes")
        for stem in ("Budget final", "Budget", "Budget-Final", "Budget v2", "Budget signed 20240101"):
            with self.subTest(stem):
                self.assertEqual(audit.near_stem(stem), "budget")

    def test_the_fixture_pairs(self):
        root = self.fixture()
        e = by_path(self.audit(root))
        pages = e["03 Home/Lease renewal.pages"]
        self.assertEqual(pages["convert_candidate"], {"id": e["03 Home/Lease renewal.pdf"]["id"],
                                                      "path": "03 Home/Lease renewal.pdf", "match": "stem"})
        self.assertNotIn("unconverted", pages["flags"])
        numbers = e["02 Finance/Tax/Budget.numbers"]
        self.assertEqual(numbers["convert_candidate"], {"id": e["02 Finance/Tax/Budget final.xlsx"]["id"],
                                                        "path": "02 Finance/Tax/Budget final.xlsx",
                                                        "match": "stem_near"})
        self.assertIn("unconverted", numbers["flags"])
        s = self.summary(root)
        self.assertEqual((s["unconverted"], s["converted_pairs"]), (1, 1))
        self.assertIn("- `02 Finance/Tax/Budget.numbers` near `02 Finance/Tax/Budget final.xlsx`", self.report(root))

    def test_nearest_wins_and_each_export_is_claimed_once(self):
        e = by_path(self.audit(self.folder({
            "A/Plan.numbers": "numbers a", "A/Plan.xlsx": "xlsx a", "D/Plan.pages": "pages d",
            "B/C/Plan.pdf": "pdf bc",
            "M/Memo.pages": "memo m", "N/Memo.pages": "memo n", "M/Memo.pdf": "memo pdf",
        })))
        self.assertEqual(e["A/Plan.numbers"]["convert_candidate"]["path"], "A/Plan.xlsx")       # 0 hops
        self.assertEqual(e["D/Plan.pages"]["convert_candidate"]["path"], "B/C/Plan.pdf")        # the next nearest
        self.assertEqual(e["M/Memo.pages"]["convert_candidate"]["path"], "M/Memo.pdf")
        self.assertNotIn("convert_candidate", e["N/Memo.pages"])                                 # claimed already
        self.assertIn("unconverted", e["N/Memo.pages"]["flags"])
        self.assertEqual([p for p, x in e.items() if "unconverted" in x["flags"]], ["N/Memo.pages"])

    def test_an_exact_stem_beats_a_nearer_near_stem(self):
        e = by_path(self.audit(self.folder({"E/Budget.numbers": "numbers", "E/Budget final.xlsx": "near",
                                            "F/G/Budget.csv": "exact"})))
        self.assertEqual(e["E/Budget.numbers"]["convert_candidate"]["path"], "F/G/Budget.csv")
        self.assertEqual(e["E/Budget.numbers"]["convert_candidate"]["match"], "stem")
        self.assertEqual(e["E/Budget.numbers"]["flags"], [])


class HygieneTest(AuditCase):
    def test_the_fixture_defects(self):
        root = self.fixture()
        e = by_path(self.audit(root))
        self.assertEqual({p: (x["look_reason"], x["flags"]) for p, x in e.items() if x.get("look_reason")}, {
            "03 Home/Lease notes .txt": ("space_before_extension", ["hygiene"]),
            "03 Home/Utilities /Electricity bill.pdf": ("whitespace_in_name", ["hygiene"]),
        })
        self.assertEqual(self.summary(root)["hygiene"], {"space_before_extension": 1, "whitespace_in_name": 1})

    def test_synthetic_defects(self):
        files = {"A/Notes.txt ": "trailing", " B/Letter.txt": "leading", "C/Report .pdf": "before ext",
                 "D/Clean.txt": "clean"}
        root = self.folder(files)
        case_sensitive = not os.path.exists(os.path.join(root, "d", "clean.txt"))
        if case_sensitive:
            write(os.path.join(root, "D", "clean.txt"), "another")
        e = by_path(self.audit(root))
        self.assertEqual(e["A/Notes.txt "]["look_reason"], "whitespace_in_name")
        self.assertEqual(e[" B/Letter.txt"]["look_reason"], "whitespace_in_name")
        self.assertEqual(e["C/Report .pdf"]["look_reason"], "space_before_extension")
        if case_sensitive:
            self.assertEqual(e["D/Clean.txt"]["look_reason"], "case_only_name_clash")
            self.assertEqual(e["D/clean.txt"]["look_reason"], "case_only_name_clash")
        else:
            self.assertNotIn("look_reason", e["D/Clean.txt"])

    def test_a_name_over_255_bytes(self):
        """A Mac allows 255 characters in a name, so 90 Chinese characters (274 bytes) can arrive in a folder; no Linux
        filesystem stores that, so a driver shows the audit such a name for a file kept under a short one."""
        root = self.folder({"A/short.txt": "a letter filed under a very long name"})
        long_name = "中" * 90 + ".txt"
        self.assertGreater(len(long_name.encode()), 255)
        code, _o, err = run("audit.py", long_name, "short.txt", "--root", root, "--work",
                            os.path.join(os.path.dirname(root), "work"), "--out", self.out(root), "--read-only-root",
                            script=LONG_NAME)
        self.assertEqual(code, 0, err)
        e = by_path(json.loads(read(os.path.join(self.out(root), "manifest.json"))))
        self.assertEqual(list(e), ["A/" + long_name])
        self.assertEqual((e["A/" + long_name]["look_reason"], e["A/" + long_name]["flags"]),
                         ("component_over_255_bytes", ["hygiene"]))
        self.assertEqual(self.summary(root)["hygiene"], {"component_over_255_bytes": 1})


class PackSettingsTest(AuditCase):
    """A `packs` entry the audit could never match fails loud when the rulebook is read."""

    def loan(self, parent, packs):
        return self.folder(dict(self.pinned(packs=packs), **{"Letters/Loan 2022/Payslip.pdf": "payslip"}),
                           parent=parent)

    def test_malformed_entries_are_refused_by_name(self):
        entries = ("/Letters/Loan 2022", "./Letters/Loan 2022", "Letters/../Letters/Loan 2022", "Letters//Loan 2022",
                   "Letters/Loan 2022 ", " Letters/Loan 2022", ".", "/")
        for n, entry in enumerate(entries):
            with self.subTest(entry=entry):
                root = self.loan("bad%d" % n, [entry])
                with self.assertRaisesRegex(common.ToolError, re.escape("packs entry %r" % entry)):
                    common.load_rulebook(root, os.path.join(root, ".familyai"))
        code, _o, err = run("audit.py", "--root", root, "--work", os.path.join(self.tmp, "work"), "--out",
                            self.out(root), "--read-only-root")
        self.assertEqual(code, 2)
        self.assertIn("packs entry '/'", err)
        self.assertFalse(os.path.exists(os.path.join(self.out(root), "manifest.json")))

    def test_a_trailing_slash_is_dropped(self):
        root = self.loan("slash", ["Letters/Loan 2022/"])
        self.assertEqual(common.load_rulebook(root, os.path.join(root, ".familyai"))["packs"], ["Letters/Loan 2022"])

    def test_an_invalid_pack_keyword_is_refused_by_name(self):
        for n, keyword in enumerate(("(", "[a-", "a)(b", "*visa")):
            with self.subTest(keyword=keyword):
                root = self.folder(self.pinned(pack_keywords=["visa", keyword]), parent="kw%d" % n)
                with self.assertRaisesRegex(common.ToolError, re.escape("pack_keywords entry %r" % keyword)):
                    common.load_rulebook(root, os.path.join(root, ".familyai"))
        code, _o, err = run("audit.py", "--root", root, "--work", os.path.join(self.tmp, "work"), "--out",
                            self.out(root), "--read-only-root")
        self.assertEqual(code, 2)
        self.assertIn("pack_keywords entry '*visa'", err)
        self.assertNotIn("Traceback", err)
        root = self.folder(self.pinned(pack_keywords=["(?P<n>visa)", "(?P<n>renew)"]), parent="clash")
        with self.assertRaisesRegex(common.ToolError, "pack_keywords do not combine"):
            common.load_rulebook(root, os.path.join(root, ".familyai"))

    def test_a_pack_named_in_another_unicode_form(self):
        """A name stored decomposed (NFD) on disk and composed (NFC) in rulebook.json, or the other way round, is
        the same pack."""
        nfc, nfd = (unicodedata.normalize(form, "Letters/Café 2022") for form in ("NFC", "NFD"))
        self.assertNotEqual(nfc, nfd)
        for n, (on_disk, listed) in enumerate(((nfd, nfc), (nfc, nfd))):
            with self.subTest(on_disk=ascii(on_disk)):
                files = self.pinned(packs=[listed])
                for i in (1, 2, 3):
                    files["Letters/Payslip %d.pdf" % i] = files["%s/Payslip %d.pdf" % (on_disk, i)] = "slip %d" % i
                k = kinds(self.audit(self.folder(files, parent="form%d" % n)))
                self.assertEqual({k["%s/Payslip %d.pdf" % (on_disk, i)] for i in (1, 2, 3)}, {"pack"})


class WalkTest(AuditCase):
    def test_root_strays_and_reserved_names(self):
        root = self.folder({
            "loose.txt": "a stray", "CLAUDE.md": "rulebook", "AGENTS.md": "rulebook", "GEMINI.md": "rulebook",
            "Wiki/Page.md": "wiki", "Outbox/Sent.txt": "out", "Alex Papers Wiki/Home.md": "wiki page",
            "_Audit/AUDIT.md": "audit", "_Inbox/New.txt": "inbox", "_Private/Secret.txt": "kept out",
            "Filed/CLAUDE.md": "a rulebook below the top is a document",
        })
        e = by_path(self.audit(root))
        self.assertEqual(sorted(e), ["Filed/CLAUDE.md", "loose.txt"])
        self.assertEqual(e["loose.txt"]["flags"], ["root_stray"])
        self.assertEqual(e["Filed/CLAUDE.md"]["flags"], [])
        self.assertEqual(self.summary(root)["root_strays"], ["loose.txt"])

    def test_hidden_files_symlinks_and_placeholders_are_counted_not_audited(self):
        root = self.folder({".DS_Store": "finder", "A/.DS_Store": "finder", "A/.Report.pdf.icloud": "placeholder",
                            "A/Report.txt": "report", ".hidden/Note.txt": "hidden folder",
                            "A/Doc.pages/Index/Document.iwa": "iwa", "A/Doc.pages/preview.jpg": "jpg"})
        os.symlink(os.path.join(root, "A", "Report.txt"), os.path.join(root, "A", "link.txt"))
        os.symlink(os.path.join(root, "A"), os.path.join(root, "B"))
        e = by_path(self.audit(root))
        self.assertEqual(sorted(e), ["A/Doc.pages", "A/Report.txt"])
        s = self.summary(root)
        self.assertEqual((s["hidden"], s["symlinks"], s["placeholders"], s["items"]), (3, 2, 1, 2))
        self.assertIn("Hidden 3, symlinks 2, cloud-only placeholders 1, not downloaded 0.", self.report(root))


class MigratingTest(AuditCase):
    def test_the_fixture_staged_file(self):
        root = self.fixture()
        e = by_path(self.audit(root))["_Migrations/Other Project/02 Finance/Old invoice.pdf"]
        self.assertEqual((e["flags"], e["migration_target"]), (["migrating"], "Other Project"))
        self.assertEqual(self.summary(root)["migrating"], {"Other Project": 1})
        self.assertIn("- Other Project: `_Migrations/Other Project/02 Finance/Old invoice.pdf`", self.report(root))

    def test_the_settings_name_the_migrations_folder(self):
        root = self.folder(dict(self.pinned(migrations_dir="_Leaving"), **{
            "_Leaving/Robin Shared/Bills/Gas.pdf": "gas", "_Leaving/Loose.pdf": "not under a project",
            "_Migrations/Other/Water.pdf": "an ordinary underscore folder now, so skipped", "Bills/Gas.pdf": "gas",
        }))
        e = by_path(self.audit(root))
        self.assertEqual(sorted(e), ["Bills/Gas.pdf", "_Leaving/Loose.pdf"])
        gas = e["Bills/Gas.pdf"]                # the canonical copy stays; the entry is migrating all the same
        self.assertEqual((gas["flags"], gas["migration_target"]), (["migrating"], "Robin Shared"))
        self.assertEqual(e["_Leaving/Loose.pdf"]["flags"], [])
        self.assertNotIn("migration_target", e["_Leaving/Loose.pdf"])


class HistoryTest(AuditCase):
    """The manifest merges with the previous pass: renames are recorded, departures kept and stamped once."""

    def test_departed_entries_and_drift(self):
        root = self.fixture()
        t1, t2, t3, t4 = NOW, NOW + 86400, NOW + 2 * 86400, NOW + 3 * 86400
        m1 = by_path(self.audit(root, now=t1))
        contract, old_notes = m1["06 Work/Contract.docx"]["id"], m1["04 Study/Notes.rtf"]["id"]
        lease = m1["03 Home/Lease notes .txt"]["id"]
        os.remove(os.path.join(root, "06 Work", "Contract.docx"))                               # departs
        os.rename(os.path.join(root, "03 Home", "Lease notes .txt"), os.path.join(root, "03 Home", "Lease notes.txt"))
        with open(os.path.join(root, "04 Study", "Notes.rtf"), "a", encoding="utf-8") as f:     # edited
            f.write("{\\rtf1 more}\n")
        write(os.path.join(root, "03 Home", "Boiler.txt"), "Boiler serviced in May.")          # added

        m2 = self.audit(root, now=t2)
        e2 = m2["entries"]
        new_notes = by_path(m2)["04 Study/Notes.rtf"]["id"]
        boiler = by_path(m2)["03 Home/Boiler.txt"]["id"]
        self.assertEqual(self.summary(root)["drift"], {"added": 2, "departed": 2, "moved": 1, "edited": 1})
        self.assertEqual(self.summary(root)["departed"], 2)
        self.assertIn("Added 2, departed 2, moved 1, edited 1.", self.report(root))
        self.assertEqual(sorted(h for h, x in e2.items() if "departed" in x["flags"]), sorted([contract, old_notes]))
        self.assertEqual(e2[contract]["departed_at"], common.iso_utc(t2))
        self.assertEqual(e2[contract]["current_path"], "06 Work/Contract.docx")
        self.assertEqual(e2[lease]["current_path"], "03 Home/Lease notes.txt")
        self.assertEqual(e2[lease]["original_name"], "Lease notes .txt")
        self.assertEqual(e2[lease]["first_seen"], common.iso_utc(t1))
        self.assertEqual(e2[lease]["rename_history"], [{"path": "03 Home/Lease notes.txt", "at": common.iso_utc(t2),
                                                        "run_id": "audit"}])
        self.assertEqual(e2[lease]["flags"], [])                                                # the defect is gone
        self.assertNotIn("look_reason", e2[lease])
        self.assertEqual(e2[new_notes]["first_seen"], common.iso_utc(t2))
        self.assertIn(boiler, e2)

        e3 = self.audit(root, now=t3)["entries"]                                               # nothing changed
        self.assertEqual(e3[contract]["departed_at"], common.iso_utc(t2), "a departure is stamped once")
        self.assertEqual(self.summary(root)["drift"], {"added": 0, "departed": 0, "moved": 0, "edited": 0})
        self.assertEqual(self.summary(root)["departed"], 2)

        shutil.copy(os.path.join(FIXTURE, "06 Work", "Contract.docx"), os.path.join(root, "06 Work"))
        e4 = self.audit(root, now=t4)["entries"]                                               # it came back
        self.assertEqual(e4[contract]["flags"], [])
        self.assertNotIn("departed_at", e4[contract])
        self.assertEqual(e4[contract]["first_seen"], common.iso_utc(t1))
        self.assertEqual(self.summary(root)["departed"], 1)

    def test_a_copy_leaving_is_not_a_departure(self):
        root = self.fixture()
        self.audit(root)
        os.remove(os.path.join(root, "02 Finance", "Bank statement 2024-03 (1).pdf"))
        e = by_path(self.audit(root, now=NOW + 60))["02 Finance/Bank statement 2024-03.pdf"]
        self.assertNotIn("copies", e)
        self.assertEqual(e["flags"], [])
        self.assertEqual(self.summary(root)["drift"], {"added": 0, "departed": 0, "moved": 0, "edited": 0})


if __name__ == "__main__":
    unittest.main()
