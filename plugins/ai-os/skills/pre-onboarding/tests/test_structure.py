"""`structure.py`: the measures and the judge's input, the documents listing and the record check, on three invented
folders (structure_folders.py): a tidy one, one with a single mixed catch-all folder, and a messy one.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests

The folders are laid out, audited with the real `audit.py` and carded by hand once for the module; a test that changes a
folder changes a copy.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.realpath(os.path.join(HERE, "..", "tools"))
TIMEOUT = 600  # seconds: a tool that hangs fails its test instead of the run
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import common  # noqa: E402
from shield_flag import with_terms_flag  # noqa: E402
import structure  # noqa: E402
import structure_folders as sf  # noqa: E402

TERMS = "# invented terms for the tests\nZarnwick Farm|Zarnwick\nExample Surgery\n"
VERDICTS = ("no re-org", "targeted", "tidy inside", "leave as it is", "restructure")
PLACEHOLDER = "[withheld name]"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def run(*args, raw=False):
    cmd = [sys.executable, os.path.join(TOOLS, "structure.py")] + (list(args) if raw else with_terms_flag(
        "structure.py", args))
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT,
                       env=dict(os.environ, PYTHONWARNINGS="error::ResourceWarning", PRE_ONBOARDING_NOW=sf.NOW))
    assert "Traceback" not in r.stderr, r.stderr
    return r.returncode, r.stdout, r.stderr


class Built(unittest.TestCase):
    """The three folders, built once, each measured once (the input and the measures kept)."""

    @classmethod
    def setUpClass(cls):
        cls.base = os.path.realpath(tempfile.mkdtemp(prefix="structure_test_"))
        cls.roots = sf.build(cls.base)
        cls.res, cls.input = {}, {}
        for name, root in cls.roots.items():
            out = os.path.join(cls.base, "out-" + name, "input.md")
            code, stdout, err = run("measure", "--root", root, "--work", os.path.join(cls.base, "w-" + name),
                                    "--out", out)
            assert code == 0, err
            cls.res[name], cls.input[name] = json.loads(stdout), read(out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, True)

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="structure_case_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def copy_of(self, name):
        root = os.path.join(self.tmp, os.path.basename(self.roots[name]))
        shutil.copytree(self.roots[name], root)
        return root

    def flagged(self, name):
        return {r["folder"]: r["stands_out"] for r in self.res[name]["folders"] if r["stands_out"]}

    def signal(self, name, key):
        return self.res[name]["signals"][key]


class MeasureTest(Built):
    def test_the_well_kept_folder_stands_out_nowhere(self):
        self.assertEqual(self.flagged("well_kept"), {})
        for key, sig in self.res["well_kept"]["signals"].items():
            self.assertEqual((sig["count"], sig["stands_out"], sig["where"]), (0, False, []), key)
        s = self.res["well_kept"]["summary"]
        self.assertEqual((s["documents"], s["copies"], s["without_card"], s["departed"]), (53, 0, 0, 0))

    def test_the_half_messy_folder_flags_only_its_catch_all_and_the_copies_of_one_year(self):
        flagged = self.flagged("half_messy")
        self.assertEqual(flagged, {"Health/2022": ["duplicate_subtree"], "Money/Misc": ["wide", "mixed",
                                                                                          "generic_folder_name"],
                                   "Money/Misc/old health": ["duplicate_subtree"]})
        # the structure signals other than the pair of copies are all in the one mixed folder
        self.assertEqual({f for f, flags in flagged.items() if set(flags) - {"duplicate_subtree"}}, {"Money/Misc"})
        # the catch-all's measures: 21 documents directly in it, five categories, the commonest at 10 of 21
        misc = {r["folder"]: r for r in self.res["half_messy"]["folders"]}["Money/Misc"]
        self.assertEqual((misc["documents_direct"], misc["categories_direct"], misc["top_category_direct"],
                          misc["top_share_direct"]), (21, 5, "Home & Household", 0.476))
        # the scanner names fall just under the generic-name threshold, and no folder crosses it
        self.assertEqual((misc["generic_documents"], misc["generic_share"]), (6, 0.286))
        self.assertEqual(self.signal("half_messy", "generic_name_folders")["count"], 0)
        self.assertEqual(self.signal("half_messy", "duplicate_subtrees")["where"], [
            {"folder": "Health/2022", "also_in": "Money/Misc/old health", "contents": 4},
            {"folder": "Money/Misc/old health", "also_in": "Health/2022", "contents": 4}])
        # one subject in three homes each: the home category, and the child
        self.assertEqual(self.signal("half_messy", "categories_in_many_homes")["where"],
                         [{"subject": "Home & Household", "homes": 3}])
        self.assertEqual(self.signal("half_messy", "parties_in_many_homes")["where"],
                         [{"subject": "Kit Example", "homes": 3}])

    def test_the_messy_folder_flags_its_dump_its_spread_and_its_duplicate_trees(self):
        flagged = self.flagged("messy")
        self.assertEqual(flagged["Downloads from phone"], ["wide", "flat_dump", "mixed", "generic_names",
                                                           "generic_folder_name"])
        self.assertEqual(flagged["(root)"], ["root_strays"])
        self.assertEqual(flagged["Old laptop backup"], ["single_child_chain"])
        self.assertEqual([f for f, flags in flagged.items() if "duplicate_subtree" in flags],
                         ["Bank", "Health stuff", "House", "Taxes"])
        sig = self.res["messy"]["signals"]
        self.assertEqual((sig["duplicate_subtrees"]["count"], sig["flat_dumps"]["where"], sig["wide_folders"]["where"]),
                         (8, ["Downloads from phone"], [{"folder": "Downloads from phone", "documents": 45}]))
        self.assertEqual(sig["single_child_chains"]["deepest_chain"], 3)
        self.assertEqual(sig["single_child_chains"]["deepest_chain_start"], "Old laptop backup")
        self.assertEqual(sig["root_strays"]["documents"], 3)
        self.assertEqual(sig["generic_folder_names"]["where"], ["Downloads from phone", "New folder (2)", "Stuff"])
        self.assertGreaterEqual(sig["categories_in_many_homes"]["count"], 3)
        self.assertGreaterEqual(sig["parties_in_many_homes"]["count"], 4)
        homes = {x["subject"]: x["homes"] for x in sig["parties_in_many_homes"]["where"]}
        self.assertIn("Example Revenue Service", homes)
        self.assertNotIn("Morgan Example", homes, "the main party is no spread subject")

    def test_the_signals_that_separate_the_three_folders_rise_with_the_mess(self):
        order = ("well_kept", "half_messy", "messy")
        for key in ("categories_in_many_homes", "parties_in_many_homes", "duplicate_subtrees", "mixed_folders"):
            counts = [self.signal(n, key)["count"] for n in order]
            self.assertEqual(counts, sorted(set(counts)), key)
        self.assertEqual([self.signal(n, "wide_folders")["largest_direct"] for n in order], [6, 21, 45])

    def test_a_distinct_folder_per_row_and_the_whole_folder_in_the_summary(self):
        s = self.res["messy"]["summary"]
        self.assertEqual((s["documents"], s["contents"], s["main_party"]), (91, 53 + 21, "Morgan Example"))
        self.assertEqual((s["copies"], s["held_for_another_project"], s["excluded"]), (91 - 74, 0, 0))
        rows = self.res["messy"]["folders"]
        self.assertEqual([r["folder"] for r in rows][:2], ["(root)", "Bank"])
        self.assertEqual(max(r["depth"] for r in rows), 3)
        self.assertEqual(self.res["messy"]["params"]["wide_documents"], 15)

    def test_the_input_names_no_verdict_and_is_the_same_every_time(self):
        for name, text in self.input.items():
            for word in VERDICTS:
                self.assertNotIn(word, text, (name, word))
            self.assertTrue(text.startswith("# Structure facts and a card sample"))
            self.assertNotIn("\u2014", text)
        again = os.path.join(self.tmp, "again", "input.md")
        code, stdout, err = run("measure", "--root", self.roots["messy"], "--work", os.path.join(self.tmp, "w"),
                                "--out", again)
        self.assertEqual(code, 0, err)
        self.assertEqual(read(again), self.input["messy"])
        self.assertEqual(json.loads(stdout), self.res["messy"])
        self.assertEqual(read(os.path.join(os.path.dirname(again), "measures.json")), stdout)

    def test_the_input_holds_the_tree_the_measures_and_a_sample_of_at_most_five_cards_a_folder(self):
        text = self.input["half_messy"]
        self.assertIn("- `Misc`: 21 / 25", text)
        self.assertIn("- documents: 78; distinct contents: 74, 74 of them with a card", text)
        self.assertIn("- categories on the cards: 5. Categories in at least 3", self.input["well_kept"],
                      "the number of categories on the cards, not of those held in two homes")
        self.assertEqual(self.res["well_kept"]["summary"]["categories"], 5)
        self.assertRegex(text, r"\| `Money/Misc` \| 21 \| 25 \| 1 \| 5 \| 0\.476 \|")
        self.assertIn("wide, mixed, generic_folder_name |", text)
        sections = re.split(r"(?m)^### ", text.split("## 4. Card sample")[1])[1:]
        self.assertTrue(sections)
        for section in sections:
            rows = [x for x in section.splitlines() if x.startswith("| `")]
            self.assertLessEqual(len(rows), 5, section.splitlines()[0])
        misc = next(x for x in sections if x.startswith("`Money/Misc` "))
        rows = [x.split("`")[1] for x in misc.splitlines() if x.startswith("| `")]
        every = sorted(r["path"] for r in self.documents("half_messy") if r["path"].startswith("Money/Misc/")
                       and r["path"].count("/") == 2)
        self.assertEqual((len(rows), rows[0], rows[-1]), (5, every[0], every[-1]), "evenly spaced over the sorted paths")
        self.assertEqual(rows, sorted(rows))

    def test_the_tree_stops_at_the_depth_and_a_folder_below_it_that_stands_out_is_still_named(self):
        text = self.input["messy"]
        tree = text.split("## 2.")[0]
        self.assertIn("- `morgan`: 0 / 17", tree)
        self.assertNotIn("Documents", tree, "the tree stops at depth 3")
        self.assertIn("Folders deeper than 3 are counted in the folder above them; one that stands out is named below.",
                      tree)
        deep = "Old laptop backup/Users/morgan/Documents/Bank"
        self.assertIn("`%s` (also in `Bank`)" % deep, text.split("## 2.")[1].split("## 3.")[0])
        self.assertNotIn("Folders deeper", self.input["well_kept"])
        again = os.path.join(self.tmp, "o", "input.md")
        code, stdout, err = run("measure", "--root", self.roots["messy"], "--work", os.path.join(self.tmp, "w"),
                                "--out", again, "--depth", "5")
        self.assertEqual(code, 0, err)
        self.assertIn("\n          - `Bank`: 5 / 5", read(again))
        self.assertEqual(max(r["depth"] for r in json.loads(stdout)["folders"]), 5)

    def documents(self, name):
        man = json.loads(read(os.path.join(self.roots[name], "_Audit", "manifest.json")))["entries"]
        return [{"path": p, "id": h} for h, e in man.items() for p in
                [c["path"] for c in e.get("copies") or []] or [e["current_path"]]]

    def test_a_content_with_no_card_is_counted_and_judged_by_nothing(self):
        root = self.copy_of("half_messy")
        misc = {r["id"]: r["path"] for r in self.documents("half_messy") if r["path"].startswith("Money/Misc/")
                and r["path"].count("/") == 2}
        gone = sorted(misc)[0]
        os.remove(os.path.join(root, "_Audit", "cards", gone + ".json"))
        code, stdout, err = run("measure", "--root", root, "--work", os.path.join(self.tmp, "w"),
                                "--out", os.path.join(self.tmp, "o", "input.md"))
        self.assertEqual(code, 0, err)
        res = json.loads(stdout)
        row = {r["folder"]: r for r in res["folders"]}["Money/Misc"]
        self.assertEqual((res["summary"]["without_card"], res["summary"]["carded"], row["without_card"],
                          row["carded_direct"], row["documents_direct"]), (1, 73, 1, 20, 21))
        self.assertIn("mixed", row["stands_out"])

    def test_thresholds_at_their_edges(self):
        def folder(n, share_of=None, generic=0, name="A", parent=""):
            docs, cards = [], {}
            for i in range(n):
                h = "%s%d" % (name, i)
                path = ("%s/" % parent if parent else "") + "%s/doc %d.txt" % (name, i)
                docs.append({"path": path, "id": h, "current": path, "canonical": True, "generic": i < generic})
                cards[h] = {"category": "X" if i < (share_of if share_of is not None else n) else "Y"}
            return docs, cards

        def flags(docs, cards, folder_name="A"):
            rows, _chain = structure.folder_rows(docs, cards)
            return {r["folder"]: r["stands_out"] for r in rows}.get(folder_name)
        self.assertNotIn("wide", flags(*folder(14)))
        self.assertIn("wide", flags(*folder(15)))
        self.assertIn("flat_dump", flags(*folder(15)))
        self.assertNotIn("mixed", flags(*folder(4, share_of=2)), "fewer than 5 contents are not judged")
        self.assertIn("mixed", flags(*folder(5, share_of=3)), "3 of 5 is 0.6, which stands out")
        self.assertNotIn("mixed", flags(*folder(6, share_of=4)), "4 of 6 is above 0.6")
        self.assertNotIn("generic_names", flags(*folder(5, generic=1)), "0.2")
        self.assertIn("generic_names", flags(*folder(10, generic=3)), "0.3")
        self.assertNotIn("generic_names", flags(*folder(4, generic=4)), "fewer than 5 documents are not judged")
        a = folder(3, name="A")
        b = folder(3, name="A", parent="")            # the same three contents, in a second folder
        twin = [dict(d, path=d["path"].replace("A/", "B/")) for d in b[0]]
        self.assertIn("duplicate_subtree", flags(a[0] + twin, a[1]))
        two = [dict(d, path=d["path"].replace("A/", "B/")) for d in a[0][:2]]
        self.assertNotIn("duplicate_subtree", flags(a[0][:2] + two, a[1]), "2 contents are too few")
        # a chain of one folder is not one; a chain of two is
        x = [{"path": "P/Q/doc.txt", "id": "q", "current": "P/Q/doc.txt", "canonical": True, "generic": False}]
        self.assertNotIn("single_child_chain", flags(x, {"q": {}}, "P"))
        y = [{"path": "P/Q/R/doc.txt", "id": "r", "current": "P/Q/R/doc.txt", "canonical": True, "generic": False}]
        self.assertIn("single_child_chain", flags(y, {"r": {}}, "P"))
        self.assertNotIn("single_child_chain", flags(y, {"r": {}}, "P/Q"), "only the start of a run is flagged")
        z = [{"path": "loose.txt", "id": "z", "current": "loose.txt", "canonical": True, "generic": False}]
        self.assertEqual(flags(z, {}, "(root)"), ["root_strays"])


class ShieldedTest(Built):
    def terms(self):
        path = os.path.join(self.tmp, "terms.txt")
        write(path, TERMS)
        return path

    def test_every_string_written_is_shielded_and_two_folders_that_shield_alike_stay_two(self):
        root = self.copy_of("well_kept")
        os.rename(os.path.join(root, "Kit"), os.path.join(root, "Zarnwick Farm"))
        os.rename(os.path.join(root, "Car"), os.path.join(root, "Zarnwick"))
        proc = subprocess.run([sys.executable, os.path.join(TOOLS, "audit.py"), "--root", root, "--work",
                               os.path.join(self.tmp, "wa")], capture_output=True, text=True,
                              env=dict(os.environ, PRE_ONBOARDING_NOW=sf.NOW))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = os.path.join(self.tmp, "o", "input.md")
        code, stdout, err = run("measure", "--root", root, "--work", os.path.join(self.tmp, "w"), "--out", out,
                                "--terms", self.terms())
        self.assertEqual(code, 0, err)
        written = {"input.md": read(out), "measures.json": read(os.path.join(os.path.dirname(out), "measures.json")),
                   "stdout": stdout}
        for name, text in written.items():
            for term in ("Zarnwick", "Example Surgery"):
                self.assertNotIn(term.lower(), text.lower(), (name, term))
            self.assertIn(PLACEHOLDER, text, name)
        self.assertRegex(err, r"shielded \d+ occurrence\(s\) of an isolation term in the structure input and measures")
        rows = json.loads(stdout)["folders"]
        self.assertEqual([r["folder"] for r in rows if "/" not in r["folder"] and r["folder"].startswith(PLACEHOLDER)],
                         [PLACEHOLDER, PLACEHOLDER], "two folders, however they read")
        self.assertIn("%s/School" % PLACEHOLDER, [r["folder"] for r in rows])

    def test_the_documents_listing_is_shielded_too(self):
        root = self.copy_of("well_kept")
        out = os.path.join(self.tmp, "o", "documents.md")
        code, stdout, err = run("documents", "--root", root, "--work", os.path.join(self.tmp, "w"), "--out", out,
                                "--folder", "Health/2022", "--terms", self.terms())
        self.assertEqual(code, 0, err)
        text = read(out)
        self.assertNotIn("example surgery", text.lower())
        self.assertIn("%s" % PLACEHOLDER, text)
        self.assertIn("1 folder(s), 4 document(s) ->", stdout)


class WithheldTest(Built):
    """A document the tools may not read is counted and never listed, and a working file goes when the withheld set
    changes."""

    def setUp(self):
        super().setUp()
        self.root = self.copy_of("well_kept")
        self.work = os.path.join(self.tmp, "w")
        os.makedirs(os.path.join(self.root, "_Migrations", "Other Project", "Work", "Employment"))
        shutil.move(os.path.join(self.root, "Work", "Employment", "Employment contract 2020-09-01.txt"),
                    os.path.join(self.root, "_Migrations", "Other Project", "Work", "Employment"))
        self.rulebook(exclude=["Money/Pension"])
        self.audit()

    def rulebook(self, exclude):
        write(os.path.join(self.root, "CLAUDE.md"), "# rulebook\n")
        write(os.path.join(self.root, "AGENTS.md"), "# rulebook\n")
        sha = hashlib.sha256(read(os.path.join(self.root, "CLAUDE.md")).encode()).hexdigest()
        write(os.path.join(self.root, ".familyai", "rulebook.json"), json.dumps(
            {"version": 1, "rulebook_sha256": sha, "exclude": exclude}))

    def audit(self):
        proc = subprocess.run([sys.executable, os.path.join(TOOLS, "audit.py"), "--root", self.root, "--work",
                               self.work], capture_output=True, text=True,
                              env=dict(os.environ, PRE_ONBOARDING_NOW=sf.NOW))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def measure(self, out):
        code, stdout, err = run("measure", "--root", self.root, "--work", self.work, "--out", out)
        self.assertEqual(code, 0, err)
        return json.loads(stdout)

    def test_counted_never_listed(self):
        out = os.path.join(self.tmp, "o", "input.md")
        res = self.measure(out)
        s = res["summary"]
        self.assertEqual((s["documents"], s["excluded"], s["held_for_another_project"]), (53 - 2 - 1, 2, 1))
        every = read(out) + json.dumps(res)
        for name in ("Pension", "Other Project", "Employment contract 2020", "_Migrations"):
            self.assertNotIn(name, every)
        self.assertIn("held for another project 1, excluded 2, departed 0", read(out))
        code, listing_out, err = run("documents", "--root", self.root, "--work", self.work,
                                     "--out", os.path.join(self.tmp, "o", "documents.md"), "--folder", "Money/Pension")
        self.assertEqual(code, 2, err)
        self.assertIn("is not a folder holding live documents", err)

    def test_the_files_are_registered_and_go_when_the_withheld_set_changes(self):
        out = os.path.join(self.tmp, "o", "input.md")
        self.measure(out)
        measures = os.path.join(os.path.dirname(out), "measures.json")
        self.assertTrue(os.path.exists(out) and os.path.exists(measures))
        registered = [i["path"] for i in json.loads(read(os.path.join(self.work, "state", "rendered.json")))]
        self.assertEqual(sorted(os.path.realpath(p) for p in registered),
                         sorted(os.path.realpath(p) for p in (out, measures)))
        self.rulebook(exclude=["Money/Pension", "Money/Bank"])
        code, _o, err = run("check", "--root", self.root, "--work", self.work, "--record", os.path.join(self.tmp, "r"))
        self.assertEqual(code, 2, err)
        self.assertRegex(err, r"purged what withheld documents left behind: .*2 rendered files")
        self.assertFalse(os.path.exists(out) or os.path.exists(measures))


class RefusalTest(Built):
    def args(self, root, **extra):
        out = os.path.join(self.tmp, "o", "input.md")
        return ["--root", root, "--work", os.path.join(self.tmp, "w"), "--out", out]

    def test_a_stated_choice_about_the_terms_is_required(self):
        root = self.roots["well_kept"]
        for extra, why in (([], "give --terms (the isolation list) or --no-isolation-terms"),
                           (["--no-isolation-terms", "--terms", "x"], "not both")):
            for cmd in ("measure", "documents"):
                args = ["--folder", "Car"] if cmd == "documents" else []
                code, out, err = run(cmd, *self.args(root), *extra, *args, raw=True)
                self.assertEqual(code, 2, err)
                self.assertIn(why, err)
                self.assertFalse(os.path.exists(os.path.join(self.tmp, "o")))

    def test_the_output_never_goes_inside_the_folder(self):
        root = self.copy_of("well_kept")
        for cmd, extra in (("measure", []), ("documents", ["--folder", "Car"])):
            code, _o, err = run(cmd, "--root", root, "--work", os.path.join(self.tmp, "w"),
                                "--out", os.path.join(root, "input.md"), *extra)
            self.assertEqual(code, 2, err)
            self.assertIn("structure files are working files, never written inside the folder", err)
        code, _o, err = run("measure", "--root", root, "--work", os.path.join(self.tmp, "w"),
                            "--out", os.path.join(self.tmp, "ok", "input.md"), "--measures",
                            os.path.join(root, "m.json"))
        self.assertEqual(code, 2, err)
        self.assertFalse(os.path.exists(os.path.join(root, "m.json")))

    def test_no_cards_no_assessment(self):
        root = self.copy_of("well_kept")
        shutil.rmtree(os.path.join(root, "_Audit", "cards"))
        code, _o, err = run("measure", *self.args(root))
        self.assertEqual(code, 2, err)
        self.assertIn("the structure is assessed after the cards", err)

    def test_a_malformed_card_is_refused_by_name(self):
        root = self.copy_of("well_kept")
        name = sorted(os.listdir(os.path.join(root, "_Audit", "cards")))[0]
        write(os.path.join(root, "_Audit", "cards", name), json.dumps([1]))
        code, _o, err = run("measure", *self.args(root))
        self.assertEqual(code, 2, err)
        self.assertIn("malformed card", err)

    def test_depth_and_sample_count_from_one(self):
        for flag in ("--depth", "--sample"):
            code, _o, err = run("measure", *self.args(self.roots["well_kept"]), flag, "0")
            self.assertEqual(code, 2, err)
            self.assertIn("count from 1", err)

    def test_a_folder_that_is_none_is_refused_by_documents(self):
        root = self.roots["well_kept"]
        for folder in ("Nowhere", "Car/Insurance/Car insurance renewal 2021-03-12.txt"):
            code, _o, err = run("documents", *self.args(root), "--folder", folder)
            self.assertEqual(code, 2, err)
            self.assertIn("is not a folder holding live documents", err)

    def test_an_input_over_the_limit_is_refused_saying_how_to_shrink_it(self):
        root = self.roots["well_kept"]
        ns = argparse.Namespace(root=root, settings_dir=None, work=os.path.join(self.tmp, "w"), manifest=None,
                                read_only_root=False, terms=None, no_isolation_terms=True, cards=None,
                                out=os.path.join(self.tmp, "o", "input.md"), measures=None, depth=3, sample=5)
        with unittest.mock.patch.object(structure, "MAX_BYTES", 500):
            with self.assertRaises(common.ToolError) as cm:
                structure.measure(ns)
        self.assertIn("over the 500 a model is given: lower --sample or --depth", str(cm.exception))
        self.assertFalse(os.path.exists(ns.out))
        ns.folder = ["Car"]
        with unittest.mock.patch.object(structure, "MAX_BYTES", 500):
            with self.assertRaises(common.ToolError) as cm:
                structure.documents(ns)
        self.assertIn("name fewer folders", str(cm.exception))

    def test_a_read_only_root_refuses_nothing_outside_the_folder(self):
        code, _o, err = run("measure", *self.args(self.roots["well_kept"]), "--read-only-root")
        self.assertEqual(code, 0, err)


class DocumentsTest(Built):
    def test_every_document_under_each_folder_with_its_card(self):
        out = os.path.join(self.tmp, "o", "documents.md")
        code, stdout, err = run("documents", "--root", self.roots["half_messy"], "--work", os.path.join(self.tmp, "w"),
                                "--out", out, "--folder", "Money/Misc/", "--folder", "Kit")
        self.assertEqual(code, 0, err)
        text = read(out)
        self.assertIn("## `Money/Misc` (25 documents)", text)
        self.assertIn("## `Kit` (4 documents)", text)
        self.assertEqual(len([x for x in text.splitlines() if x.startswith("| `")]), 29)
        self.assertIn("| `Money/Misc/old health/Hospital letter 2022-02-17.txt` | Hospital letter | Morgan Example | Health "
                      "| 2022-02-17 | Hospital letter, Example Health Trust, 2022-02 |", text)
        self.assertIn("2 folder(s), 29 document(s) ->", stdout)
        self.assertNotIn("(no card)", text)

    def test_a_document_with_no_card_is_listed_without_the_fields(self):
        root = self.copy_of("well_kept")
        man = json.loads(read(os.path.join(root, "_Audit", "manifest.json")))["entries"]
        h = next(h for h, e in man.items() if e["current_path"] == "Kit/School/School report 2022-07-20.txt")
        os.remove(os.path.join(root, "_Audit", "cards", h + ".json"))
        out = os.path.join(self.tmp, "o", "documents.md")
        code, _o, err = run("documents", "--root", root, "--work", os.path.join(self.tmp, "w"), "--out", out,
                            "--folder", "Kit")
        self.assertEqual(code, 0, err)
        self.assertIn("| `Kit/School/School report 2022-07-20.txt` | (no card) | | | | |", read(out))


class RecordTest(Built):
    """`structure.py check`: each refusal of the record's shape, on the half-messy folder (78 live documents)."""

    BLOCKS = [("Money/Misc", "restructure", "21 documents, 5 categories, top share 0.476.", "about 21 files leave it."),
              ("Car", "leave as it is", "7 documents in two single-category folders.", "none")]

    def record(self, overall="targeted", reason="One catch-all folder holds the cost.", moves="21 of 78",
               blocks=None, title="# Structure assessment", header=None):
        lines = [title, "", "Overall: %s" % overall, "Reason: %s" % reason, "Documents that would move: %s" % moves]
        lines = header if header is not None else lines
        for folder, verdict, evidence, relearn in (self.BLOCKS if blocks is None else blocks):
            lines += ["", "### %s" % folder, "- Verdict: %s" % verdict, "- Evidence: %s" % evidence,
                      "- What the owner would relearn: %s" % relearn]
        return "\n".join(lines) + "\n"

    def check(self, text, root=None, code=1):
        path = os.path.join(self.tmp, "record.md")
        write(path, text)
        got, out, err = run("check", "--root", root or self.roots["half_messy"], "--work", os.path.join(self.tmp, "w"),
                            "--record", path)
        self.assertEqual(got, code, out + err)
        return json.loads(out) if got in (0, 1) else err

    def problems(self, text, **kw):
        res = self.check(text, **kw)
        self.assertFalse(res["ok"])
        return res["problems"]

    def refused(self, text, why):
        found = self.problems(text)
        self.assertTrue(any(why in p for p in found), (why, found))
        return found

    def test_a_record_of_the_right_shape_passes_and_is_counted(self):
        res = self.check(self.record(), code=0)
        self.assertEqual(res, {"overall": "targeted", "documents": 78, "would_move": 21, "blocks": 2,
                               "verdicts": {"leave as it is": 1, "tidy inside": 0, "restructure": 1}, "problems": [],
                               "ok": True, "top_level_folders_without_block": 5})

    def test_the_default_record_is_the_one_in_the_audit_folder(self):
        root = self.copy_of("half_messy")
        write(os.path.join(root, "_Audit", "structure-assessment.md"), self.record())
        got, out, err = run("check", "--root", root, "--work", os.path.join(self.tmp, "w"))
        self.assertEqual(got, 0, out + err)

    def test_a_missing_or_unreadable_record_is_refused(self):
        got, _o, err = run("check", "--root", self.roots["half_messy"], "--work", os.path.join(self.tmp, "w"),
                           "--record", os.path.join(self.tmp, "none.md"))
        self.assertEqual(got, 2, err)
        self.assertIn("record missing", err)
        path = os.path.join(self.tmp, "binary.md")
        with open(path, "wb") as f:
            f.write(b"\xff\xfe")
        got, _o, err = run("check", "--root", self.roots["half_messy"], "--work", os.path.join(self.tmp, "w"),
                           "--record", path)
        self.assertEqual(got, 2, err)
        self.assertIn("is not valid UTF-8", err)

    def test_the_title_and_each_header_line_are_required_in_order(self):
        self.refused(self.record(title="# Assessment"), "does not open with '# Structure assessment'")
        for label in ("Overall", "Reason", "Documents that would move"):
            lines = [x for x in self.record().splitlines() if not x.startswith(label + ":")]
            self.refused("\n".join(lines), "no %r line" % (label + ":"))
        out_of_order = ["# Structure assessment", "", "Reason: r", "Overall: targeted",
                        "Documents that would move: 21 of 78"]
        self.refused(self.record(header=out_of_order), "Reason is out of order (the header is Overall, Reason, Documents "
                                                       "that would move)")
        self.refused(self.record(header=out_of_order[:1] + ["", "Overall: full", "Overall: full"]),
                     "Overall is given twice")
        self.refused(self.record(header=out_of_order[:2] + ["Verdict: x"]), "is outside the header and any block")
        self.refused(self.record(reason=""), "Reason has no text")

    def test_the_overall_verdict_is_one_of_three(self):
        for value in ("No re-org", "restructure", "partial", "targeted."):
            self.refused(self.record(overall=value), "Overall is %r, not one of no re-org | targeted | full" % value)

    def test_the_documents_that_would_move_line(self):
        for moves in ("21", "21 of", "twenty of 78", "21 of 78 documents", "1,000 of 78", "-1 of 78"):
            self.refused(self.record(moves=moves), 'not "Documents that would move: <N> of <M>"')
        self.refused(self.record(moves="21 of 77"), "M is 77, but the folder has 78 live documents")
        self.refused(self.record(moves="79 of 78"), "N (79) is more than M (78)")
        self.assertEqual(self.check(self.record(moves="78 of 78"), code=0)["would_move"], 78)

    def test_one_block_of_three_labelled_lines_for_each_folder(self):
        self.refused(self.record(blocks=[]), "no folder is assessed")
        self.refused(self.record(blocks=[("Car", "leave as it is", "x", "none")] * 2), "the folder is assessed twice")
        two = self.record().replace("- What the owner would relearn: about 21 files leave it.\n", "")
        self.refused(two, "2 line(s) under the heading, not 3")
        extra = self.record().replace("- What the owner would relearn: none\n", "- What the owner would relearn: none\n"
                                                                              "- Another: line\n")
        self.refused(extra, "4 line(s) under the heading, not 3")
        swapped = self.record().replace("- Verdict: restructure\n- Evidence:", "- Evidence:", 1).replace(
            "21 documents, 5 categories, top share 0.476.\n", "21 documents.\n- Verdict: restructure\n", 1)
        self.refused(swapped, 'not "- Verdict: <text>"')
        for label in ("Verdict", "Evidence", "What the owner would relearn"):
            empty = re.sub(r"(?m)^- %s: .*$" % label, "- %s: " % label, self.record(), count=1)
            self.refused(empty, 'not "- %s: <text>"' % label)
        blank_between = self.record().replace("- Verdict: restructure\n", "- Verdict: restructure\n\n", 1)
        self.refused(blank_between, "4 line(s) under the heading, not 3")

    def test_a_verdict_is_one_of_three(self):
        for value in ("Leave as it is", "move", "tidy inside the folder", "no re-org"):
            self.refused(self.record(blocks=[("Car", value, "x", "none")]),
                         "Verdict is %r, not one of leave as it is | tidy inside | restructure" % value)

    def test_a_folder_must_be_there(self):
        for heading in ("Money/Mizc", "Money/Misc/", "`Money/Misc`", "(root)", "Car/Insurance/Car insurance renewal "
                        "2021-03-12.txt"):
            self.refused(self.record(blocks=[(heading, "leave as it is", "x", "none")], overall="no re-org",
                                     moves="0 of 78"), "not a folder holding live documents")
        for heading in ("Money/Misc/old health", "Health/2022", "Money"):
            self.check(self.record(blocks=[(heading, "restructure", "x", "y")]), code=0)

    def test_a_folder_the_shield_hid_cannot_be_named(self):
        found = self.refused(self.record(blocks=[("[withheld name]/School", "restructure", "x", "y")]),
                             "a folder the shield hid, which no command can open; rename the folder or exclude it, then "
                             "measure again")
        self.assertFalse(any("not a folder holding live documents" in p for p in found), "one finding for one defect")

    def test_a_folder_the_owner_excluded_or_staged_is_no_folder_to_assess(self):
        root = self.copy_of("half_messy")
        write(os.path.join(root, "CLAUDE.md"), "# rulebook\n")
        write(os.path.join(root, "AGENTS.md"), "# rulebook\n")
        sha = hashlib.sha256(b"# rulebook\n").hexdigest()
        write(os.path.join(root, ".familyai", "rulebook.json"), json.dumps(
            {"version": 1, "rulebook_sha256": sha, "exclude": ["Kit"]}))
        proc = subprocess.run([sys.executable, os.path.join(TOOLS, "audit.py"), "--root", root, "--work",
                               os.path.join(self.tmp, "wa")], capture_output=True, text=True,
                              env=dict(os.environ, PRE_ONBOARDING_NOW=sf.NOW))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        found = self.problems(self.record(blocks=[("Kit", "leave as it is", "x", "none")], moves="21 of 74"), root=root)
        self.assertTrue(any("not a folder holding live documents" in p for p in found), found)
        self.assertFalse(any("M is" in p for p in found), "M counts the live documents the tools may read")
        self.check(self.record(moves="21 of 74"), root=root, code=0)

    def test_no_re_org_means_every_block_leaves_the_folder_and_nothing_moves(self):
        blocks = [("Car", "leave as it is", "x", "none"), ("Health", "leave as it is", "y", "none")]
        self.assertTrue(self.check(self.record(overall="no re-org", moves="0 of 78", blocks=blocks), code=0)["ok"])
        for verdict in ("tidy inside", "restructure"):
            self.refused(self.record(overall="no re-org", moves="0 of 78",
                                     blocks=blocks + [("Money/Misc", verdict, "z", "w")]),
                         "Overall is no re-org, but 1 folder(s) are tidy inside or restructure")
        self.refused(self.record(overall="no re-org", moves="3 of 78", blocks=blocks),
                     "Overall is no re-org, but 3 documents would move")

    def test_targeted_or_full_with_nothing_to_do_is_a_contradiction(self):
        blocks = [("Car", "leave as it is", "x", "none")]
        for overall in ("targeted", "full"):
            self.refused(self.record(overall=overall, moves="0 of 78", blocks=blocks),
                         "Overall is %s, but every folder is leave as it is" % overall)
        self.assertEqual(self.check(self.record(overall="full"), code=0)["overall"], "full")

    def test_the_report_never_names_a_folder_of_the_manifest(self):
        res = self.check(self.record(blocks=[("Car", "leave as it is", "x", "none")], overall="no re-org",
                                     moves="0 of 78"), code=0)
        self.assertEqual(res["top_level_folders_without_block"], 5)
        self.assertNotIn("Health", json.dumps(res))


if __name__ == "__main__":
    unittest.main()
