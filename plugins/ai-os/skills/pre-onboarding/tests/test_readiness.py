"""`readiness.py`, the hand-off contract, and `extract.py repath`, on copies of the prepared fixture.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests

The fixture is a prepared folder: its extract records, cards and acceptance record are committed with it (written
by fixture/build.py). Once per class a template copy is audited into its own _Audit/ and its Schema compiled; each
test copies the template, plants one defect and asserts it is the one finding. A page a test edits is accepted again
(`wiki.py accept`, by a model other than its author), so the edit is the only thing that changed. The committed
fixture is never touched.
"""
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.realpath(os.path.join(HERE, "..", "tools"))
FIXTURE = os.path.join(HERE, "fixture", "Alex Personal")
WIKI = "Alex Personal Wiki"
DEADLINES = "01 Deadlines/01 Deadlines.md"
TAX = "20 Finance/Tax.md"
NOW = "1719748800"  # 2024-06-30T12:00:00Z, as regen_expected.py freezes it
TERMS = "# fictional terms for the tests\nZarnwick Farm|Zarnwick\n"
GREEN_UNVERIFIED = ["records.contamination", "isolation.canary.agy", "isolation.canary.codex"]
PREPARED = (os.path.join("_Audit", "extract"), os.path.join("_Audit", "cards"),
            os.path.join("_Audit", "wiki-acceptance.json"))


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def run(tool, *args):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, tool)] + list(args), capture_output=True, text=True,
                       encoding="utf-8", env=dict(os.environ, PRE_ONBOARDING_NOW=NOW))
    return r.returncode, r.stdout, r.stderr


def tree_digest(root):
    h = hashlib.sha256()
    for d, ds, fs in os.walk(root):
        ds.sort()
        for f in sorted(fs):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode() + b"\0" + read(p, "rb") + b"\n")
    return h.hexdigest()


class Prepared(unittest.TestCase):
    """A fresh copy of the audited, compiled fixture per test, its work directory beside it."""

    @classmethod
    def setUpClass(cls):
        cls.base = os.path.realpath(tempfile.mkdtemp(prefix="readiness_template_"))
        cls.template = os.path.join(cls.base, "Alex Personal")
        shutil.copytree(FIXTURE, cls.template)
        work = os.path.join(cls.base, "work")
        for tool, args in (("audit.py", []), ("settings.py", ["compile"])):
            code, _out, err = run(tool, *args, "--root", cls.template, "--work", work)
            assert code == 0, err

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, True)

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="readiness_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "a", "Alex Personal")
        shutil.copytree(self.template, self.root)
        self.work = os.path.join(self.tmp, "a", "work")

    def path(self, *rel):
        return os.path.join(self.root, *rel)

    def page(self, rel):
        return self.path(WIKI, *rel.split("/"))

    def tool(self, tool, *args, code=0):
        got, out, err = run(tool, *args, "--root", self.root, "--work", self.work)
        self.assertEqual(got, code, out + err)
        self.assertNotIn("Traceback", err)
        return out, err

    def readiness(self, *args, code=None):
        got, out, err = run("readiness.py", "--root", self.root, "--work", self.work, *args)
        self.assertNotIn("Traceback", err)
        self.assertIn(got, (0, 1), out + err)
        res = json.loads(out)
        self.assertEqual(got, 1 if res["findings"] else 0, "exit 1 exactly when there is a finding")
        self.assertEqual(res["summary"], {"findings": len(res["findings"]), "not_verified": len(res["not_verified"])})
        if code is not None:
            self.assertEqual(got, code, json.dumps(res["findings"], indent=1))
        return res

    def refused(self, *args):
        got, out, err = run("readiness.py", "--root", self.root, "--work", self.work, *args)
        self.assertEqual(got, 2, out + err)
        self.assertNotIn("Traceback", err)
        return err

    def one_finding(self, check, *args):
        """The detail of the run's one finding, which must be `check`'s."""
        res = self.readiness(*args)
        self.assertEqual([f[0] for f in res["findings"]], [check], json.dumps(res["findings"], indent=1))
        return res["findings"][0][1]

    def edit(self, rel, old, new, count=1):
        p = self.path(*rel.split("/"))
        text = read(p)
        self.assertEqual(text.count(old), count, "%r in %s" % (old, rel))
        write(p, text.replace(old, new))

    def edit_page(self, page, old, new, count=1):
        """Edit a wiki page, then accept the new version in both lenses, as a review of the change would."""
        self.edit("%s/%s" % (WIKI, page), old, new, count)
        self.accept_again(page)

    def accept_again(self, page, author="model-a", reviewer="model-b", code=0):
        for lens in ("owner", "professional"):
            reply = os.path.join(self.tmp, "reply.json")
            write(reply, json.dumps({"page": page, "lens": lens, "verdict": "accepted", "findings": []}))
            self.tool("wiki.py", "accept", "--reply", reply, "--author-model", author, "--reviewer-model", reviewer,
                      "--date", "2024-07-01", code=code)
            if code:
                return

    def edit_rulebook(self, old, new, pin=True, count=1):
        """Edit the rulebook and its copy alike, and re-pin the twin unless `pin` is off."""
        for name in ("CLAUDE.md", "AGENTS.md"):
            self.edit(name, old, new, count)
        if pin:
            p = self.path(".familyai", "rulebook.json")
            data = json.loads(read(p))
            data["rulebook_sha256"] = hashlib.sha256(read(self.path("CLAUDE.md"), "rb")).hexdigest()
            write(p, json.dumps(data, ensure_ascii=False, indent=1))

    def ids(self):
        man = json.loads(read(self.path("_Audit", "manifest.json")))["entries"]
        return {e["current_path"]: h for h, e in man.items() if "departed" not in e["flags"]}

    def json_file(self, *rel):
        return json.loads(read(self.path(*rel)))

    def canary(self, engine, **res):
        write(os.path.join(self.work, "state", "canary-%s.json" % engine),
              json.dumps(dict({"engine": engine, "checked_at": "2024-06-30T12:00:00+0000", "terms": 1}, **res)))


class GreenTest(Prepared):
    def test_the_fixture_is_green(self):
        res = self.readiness(code=0)
        self.assertEqual(res["findings"], [])
        self.assertEqual([k for k, _v in res["not_verified"]], GREEN_UNVERIFIED)
        self.assertEqual(res["records"], {"missing_extracts": 0, "missing_cards": 0, "bad_category": 0,
                                          "extract_paths_stale": 0, "contamination": "not verified: no --terms"})
        self.assertEqual(res["wiki_handoff"], {"rationale_file": "ok", "pages_accepted": "12/12",
                                               "pages_not_accepted": 0, "pages_not_verified": 0})
        self.assertEqual(set(res["handoff_contract"].values()), {"ok"})

    def test_terms_and_passing_canaries_leave_nothing_unverified(self):
        terms = os.path.join(self.tmp, "terms.txt")
        write(terms, TERMS)
        for engine in ("agy", "codex"):
            self.canary(engine, reply="NONE", hits=0, usage={}, **{"pass": True})
        res = self.readiness("--terms", terms, code=0)
        self.assertEqual((res["not_verified"], res["records"]["contamination"]), ([], 0))
        self.assertEqual(res["isolation"], {"canary": {"agy": "passed", "codex": "passed"}})

    def test_settings_outside_the_folder(self):
        """The wiki check reads the Schema from --settings-dir too, so its professional checks are verified."""
        elsewhere = os.path.join(self.tmp, "settings")
        shutil.move(self.path(".familyai"), elsewhere)
        res = self.readiness("--settings-dir", elsewhere, code=0)
        self.assertEqual([k for k, _v in res["not_verified"]], GREEN_UNVERIFIED)
        self.assertEqual(res["wiki"]["pages_without_single_professional"], [])
        self.assertEqual(res["wiki"]["rationale"]["professional_not_named"], [])
        self.assertEqual(res["handoff_contract"]["settings_wiki_schema_json"], "ok")

    def test_an_item_counted_only_needs_no_record(self):
        """An image over the rulebook's cap is counted, not hashed, and extract.py never reads it."""
        p = self.path(".familyai", "rulebook.json")
        write(p, json.dumps(dict(json.loads(read(p)), image_cap_mb=0.001), ensure_ascii=False, indent=1))
        self.tool("audit.py")
        man = json.loads(read(self.path("_Audit", "manifest.json")))["entries"]
        self.assertEqual([e["current_path"] for e in man.values() if not e["hashed"]], ["IMG_0001.jpg"])
        res = self.readiness(code=0)
        self.assertEqual((res["manifest"]["live_entries"], res["manifest"]["departed_entries"]), (18, 1))

    def test_out_is_refused_inside_a_read_only_root(self):
        self.assertIn("--read-only-root", self.refused("--out", self.path("readiness.json"), "--read-only-root"))
        out = os.path.join(self.tmp, "readiness.json")
        self.readiness("--out", out, "--read-only-root", code=0)
        self.assertEqual(json.loads(read(out))["findings"], [])


class ContractTest(Prepared):
    """Each hand-off contract item, planted once as a defect, is the one finding."""

    def test_wiki_folder_named_after_the_folder(self):
        shutil.move(self.path(WIKI), self.path("Alex Wiki"))
        self.edit_rulebook(WIKI, "Alex Wiki", count=2)  # the rulebook names and reserves the folder it has
        data = self.json_file(".familyai", "rulebook.json")
        write(self.path(".familyai", "rulebook.json"), json.dumps(dict(data, wiki_dir="Alex Wiki"), indent=1))
        self.tool("settings.py", "compile")
        self.assertIn("'Alex Wiki', not 'Alex Personal Wiki'",
                      self.one_finding("handoff_contract.wiki_folder_named_after_folder"))

    def test_fixed_pages(self):
        os.remove(self.page("91 Log/91 Log.md"))
        rat = self.path("_Audit", "wiki-rationale.md")
        write(rat, re.sub(r"\n### 91 Log/91 Log\.md\n(- .*(\n|\Z)){5}", "", read(rat)))
        acc = self.json_file("_Audit", "wiki-acceptance.json")
        acc["records"] = [r for r in acc["records"] if r["page"] != "91 Log/91 Log.md"]
        write(self.path("_Audit", "wiki-acceptance.json"), json.dumps(acc, indent=1) + "\n")
        self.assertEqual(self.one_finding("handoff_contract.fixed_pages"), "finding: missing 91 Log/91 Log.md")

    def test_a_date_written_by_hand_on_the_deadlines_page(self):
        self.edit_page(DEADLINES, "passport expires ([10 Identity](../10%20Identity/10%20Identity.md))\n",
                       "passport expires ([10 Identity](../10%20Identity/10%20Identity.md))\n"
                       "- **2026-01-31**: renew the parking permit\n")
        detail = self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written")
        self.assertIn("1 date(s) no page's frontmatter carries (line 12: 2026-01-31)", detail)

    def test_a_page_deadline_missing_from_the_roll_up(self):
        self.edit_page(DEADLINES, "- **2031-07-15**: passport expires "
                       "([10 Identity](../10%20Identity/10%20Identity.md))\n", "")
        self.assertIn("lacks 1 page deadline(s) (2031-07-15 (10 Identity/10 Identity.md))",
                      self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))

    def test_an_empty_roll_up_says_why(self):
        for page in ("10 Identity/10 Identity.md", "30 Home/30 Home.md"):
            p = self.page(page)
            write(p, re.sub(r"deadlines:\n(  - .*\n)+", "", read(p)))
            self.accept_again(page)
        p = self.page(DEADLINES)
        write(p, read(p).split("# Deadlines")[0] + "# Deadlines\n\nNone\n")
        self.accept_again(DEADLINES)
        self.assertIn("an empty roll-up that does not say why",
                      self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))
        self.edit_page(DEADLINES, "None\n",
                       "> [!warning] The roll-up found no frontmatter deadlines across 11 pages.\n")
        self.readiness(code=0)

    def test_a_recurring_date_kept_by_hand(self):
        p = self.page(DEADLINES)
        write(p, read(p) + "\n## Every year\n\n- **01-31**: self assessment return due\n")
        self.accept_again(DEADLINES)
        self.assertIn("1 yearly date(s) no page's recurring: list carries (line 15: 01-31)",
                      self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))

    def add_recurring(self, entry):
        self.edit_page(TAX, "status: current\n", "status: current\nrecurring:\n  - %s\n" % entry)

    def test_a_recurring_date_from_page_frontmatter(self):
        self.add_recurring("{date: 01-31, note: Self assessment return due}")
        p = self.page(DEADLINES)
        write(p, read(p) + "\n## Every year\n\n"
                           "- **01-31**: self assessment return due ([Tax](../20%20Finance/Tax.md))\n")
        self.accept_again(DEADLINES)
        self.readiness(code=0)

    def test_a_recurring_date_missing_from_the_roll_up(self):
        self.add_recurring("{date: 01-31, note: Self assessment return due}")
        self.assertIn("lacks 1 recurring date(s) (01-31 (20 Finance/Tax.md))",
                      self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))

    def test_a_recurring_entry_not_month_and_day(self):
        self.add_recurring("{date: 2025-01-31, note: Self assessment return due}")
        self.assertIn("1 recurring: entr(ies) not {date: MM-DD, note}",
                      self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))

    def test_gemini_md_reserved(self):
        self.edit_rulebook("`GEMINI.md`, ", "")
        self.assertEqual(self.one_finding("handoff_contract.rulebook_reserves_rulebook_filenames"),
                         "finding: the rulebook does not reserve GEMINI.md")

    def test_new_files_routed_within_the_folder(self):
        self.edit_rulebook("\n## Formats and packs", "- New files that belong to another project go to "
                           "`_Migrations/<Project>/`.\n\n## Formats and packs")
        self.assertIn("routes new files to _Migrations/ (1 line(s))",
                      self.one_finding("handoff_contract.new_files_routed_within_folder"))

    def test_rulebook_json_fresh(self):
        self.edit_rulebook("Nobody else.", "Nobody else!", pin=False)
        self.assertIn("finding: stale:", self.one_finding("handoff_contract.settings_rulebook_json"))

    def test_wiki_schema_json_present(self):
        twin = self.path(".familyai", "wiki-schema.json")
        kept = read(twin)
        os.remove(twin)
        self.assertIn("missing", self.one_finding("handoff_contract.settings_wiki_schema_json"))
        res = self.readiness()
        unverified = [k for k, _v in res["not_verified"]]
        self.assertIn("wiki.pages_without_single_professional", unverified)
        self.assertIn("wiki.rationale.professional_not_named", unverified)
        self.assertIn("wiki_handoff.pages_not_verified", unverified)  # check's acceptance_not_verified, not findings
        self.assertEqual((res["wiki_handoff"]["pages_accepted"], res["wiki_handoff"]["pages_not_verified"]),
                         ("0/12", 12))
        write(twin, kept)  # a refusal stands whatever the Schema: it is still a finding without the twin
        self.accept_again(TAX, author="model-a", reviewer="Model-A", code=2)
        os.remove(twin)
        res = self.readiness(code=1)
        self.assertEqual([f[0] for f in res["findings"]], ["wiki_handoff.pages_not_accepted",
                                                           "handoff_contract.settings_wiki_schema_json"])
        self.assertTrue(res["findings"][0][1].startswith("20 Finance/Tax.md: refused"), res["findings"][0][1])
        self.assertEqual((res["wiki_handoff"]["pages_not_accepted"], res["wiki_handoff"]["pages_not_verified"]),
                         (1, 11))


class FindingTest(Prepared):
    """Every other check, planted once, is the one finding and sets the exit code."""

    def test_rulebook_copies_differ(self):
        self.edit("AGENTS.md", "Nobody else.", "Nobody else!")
        self.assertIn("differ", self.one_finding("rulebook.copies_identical"))

    def test_a_scratch_folder_left_in_audit(self):
        os.makedirs(self.path("_Audit", "_wikibuild"))
        self.assertIn("_wikibuild", self.one_finding("scratch.left_in_audit"))

    def card(self, rel):
        return self.path("_Audit", "cards", self.ids()[rel] + ".json")

    def test_a_card_category_the_rulebook_does_not_allow(self):
        p = self.card("04 Study/Notes.rtf")
        write(p, json.dumps(dict(json.loads(read(p)), category="Hobbies"), indent=1))
        self.assertIn("04 Study/Notes.rtf: 'Hobbies'", self.one_finding("records.bad_category"))

    def test_contamination(self):
        terms = os.path.join(self.tmp, "terms.txt")
        write(terms, TERMS)
        p = self.card("04 Study/Notes.rtf")
        card = json.loads(read(p))
        write(p, json.dumps(dict(card, summary=card["summary"] + " Reviewed at Zarnwick Farm."), indent=1))
        detail = self.one_finding("records.contamination", "--terms", terms)
        self.assertIn("04 Study/Notes.rtf", detail)
        self.assertNotIn("Zarnwick", detail, "a term is never written out")

    def test_an_extract_path_the_manifest_does_not_hold_names_the_repair(self):
        p = self.path("_Audit", "extract", self.ids()["04 Study/Notes.rtf"] + ".json")
        write(p, json.dumps(dict(json.loads(read(p)), path="04 Study/Old notes.rtf")))
        detail = self.one_finding("records.extract_paths_stale")
        self.assertIn("'04 Study/Old notes.rtf' is now '04 Study/Notes.rtf'", detail)
        self.assertIn("repath them: extract.py repath --root %s --work %s --apply"
                      % (shlex.quote(self.root), shlex.quote(self.work)), detail)

    def test_a_missing_extract_record(self):
        os.remove(self.path("_Audit", "extract", self.ids()["06 Work/Contract.docx"] + ".json"))
        self.assertIn("06 Work/Contract.docx", self.one_finding("records.missing_extracts"))

    def test_a_missing_card(self):
        os.remove(self.card("06 Work/Contract.docx"))
        self.assertIn("06 Work/Contract.docx", self.one_finding("records.missing_cards"))

    def test_a_manifest_that_is_not_current(self):
        shutil.move(self.path("04 Study", "Notes.rtf"), self.path("04 Study", "Class notes.rtf"))
        self.assertIn("04 Study/Notes.rtf", self.one_finding("manifest.live_paths_missing"))

    def test_a_failed_canary(self):
        self.canary("codex", reply="<term>", hits=1, usage={}, **{"pass": False})
        res = self.readiness(code=1)
        self.assertEqual(res["findings"], [["isolation.canary.codex", "failed: 1 isolation term(s) in the engine's "
                                            "reply, checked 2024-06-30T12:00:00+0000"]])
        self.assertIn(["isolation.canary.agy", res["isolation"]["canary"]["agy"]], res["not_verified"])
        self.canary("codex", error="timeout", **{"pass": False})
        self.assertIn("the engine gave no answer (timeout)", self.one_finding("isolation.canary.codex"))

    def test_the_rationale_file_missing(self):
        os.remove(self.path("_Audit", "wiki-rationale.md"))
        self.assertIn("wiki-rationale.md is missing", self.one_finding("wiki_handoff.rationale_file"))

    def test_a_page_not_accepted(self):
        acc = self.json_file("_Audit", "wiki-acceptance.json")
        acc["records"] = [r for r in acc["records"] if (r["page"], r["lens"]) != (TAX, "professional")]
        write(self.path("_Audit", "wiki-acceptance.json"), json.dumps(acc, indent=1) + "\n")
        self.assertEqual(self.one_finding("wiki_handoff.pages_not_accepted"),
                         "20 Finance/Tax.md: not recorded (professional lens: no verdict)")
        self.assertEqual(self.readiness()["wiki_handoff"]["pages_accepted"], "11/12")

    def test_a_refused_page_is_named(self):
        self.accept_again(TAX, author="model-a", reviewer="Model-A", code=2)
        detail = self.one_finding("wiki_handoff.pages_not_accepted")
        self.assertTrue(detail.startswith("20 Finance/Tax.md: refused (owner lens: the reviewer model"), detail)

    def test_a_wiki_check_problem(self):
        self.edit_page(TAX, "Nothing is due:", "Nothing is due \u2014")
        self.assertEqual(self.one_finding("wiki.problems"), "wiki.py check reports 1 problem(s)")

    def test_tool_errors_exit_2(self):
        p = self.card("06 Work/Contract.docx")
        write(p, "[]")
        self.assertIn("malformed card", self.refused())
        os.remove(p)
        self.canary("agy", reply="NONE")  # no pass recorded
        self.assertIn("is not a canary result for agy", self.refused())
        os.remove(self.path("_Audit", "manifest.json"))
        self.assertIn("manifest missing", self.refused())

    def test_a_crash_exits_2_never_1(self):
        """Exit 1 means findings, so an unforeseen failure (here a page that is not UTF-8) is a tool error."""
        with open(self.page(TAX), "ab") as f:
            f.write(b"\xff\xfe")
        got, _out, err = run("readiness.py", "--root", self.root, "--work", self.work)
        self.assertEqual(got, 2, err)
        self.assertIn("UnicodeDecodeError", err)


class RepathTest(Prepared):
    """`extract.py repath`: after a round moves a document, its record's path is rewritten from the manifest by
    content hash, with nothing read again."""

    MOVED = ("04 Study/Notes.rtf", "04 Study/Class notes.rtf")  # cited by no page by path, so the wiki holds

    def setUp(self):
        super().setUp()
        self.eid = self.ids()[self.MOVED[0]]
        self.record = self.path("_Audit", "extract", self.eid + ".json")

    def move_and_audit(self, old, new):
        shutil.move(self.path(*old.split("/")), self.path(*new.split("/")))
        self.tool("audit.py")

    def repath(self, *args, code=0):
        out, err = self.tool("extract.py", "repath", *args, code=code)
        return json.loads(out) if code == 0 else err

    def test_dry_run_then_apply(self):
        before = read(self.record, "rb")
        self.move_and_audit(*self.MOVED)
        command = shlex.split(self.one_finding("records.extract_paths_stale").split("repath them: ", 1)[1])
        res = self.repath()
        self.assertEqual(res, {"records": 18, "applied": False, "paths_changed": 1, "already_current": 17,
                               "moves": [[self.eid, self.MOVED[0], self.MOVED[1]]], "departed_left": [],
                               "not_in_manifest": []})
        self.assertEqual(read(self.record, "rb"), before, "a dry run writes nothing")
        code, out, err = run(*command)  # the repair, as readiness names it
        self.assertEqual(code, 0, err)
        res = json.loads(out)
        self.assertEqual((res["applied"], res["paths_changed"], res["moves"]),
                         (True, 1, [[self.eid, self.MOVED[0], self.MOVED[1]]]))
        old, new = json.loads(before), json.loads(read(self.record))
        self.assertEqual(new, dict(old, path=self.MOVED[1]), "only the path changes")
        self.assertEqual(list(new), list(old), "the record keeps its key order")
        self.readiness(code=0)
        self.assertEqual(self.repath()["paths_changed"], 0)

    def test_departed_and_unknown_records_are_left_and_listed(self):
        os.remove(self.path(*self.MOVED[0].split("/")))
        self.tool("audit.py")
        stray = self.path("_Audit", "extract", "0" * 64 + ".json")
        write(stray, json.dumps({"id": "0" * 64, "path": "Nowhere/Lost.pdf", "pages": []}))
        res = self.repath("--apply")
        self.assertEqual((res["paths_changed"], res["departed_left"], res["not_in_manifest"]),
                         (0, [[self.eid, self.MOVED[0]]], [["0" * 64, "Nowhere/Lost.pdf"]]))
        self.assertEqual(json.loads(read(self.record))["path"], self.MOVED[0])

    def unsettle(self, change):
        p = self.path("_Audit", "manifest.json")
        man = json.loads(read(p))
        change(man["entries"])
        write(p, json.dumps(man, ensure_ascii=False, indent=1))

    def test_an_unsettled_canonical_choice_is_refused(self):
        self.move_and_audit(*self.MOVED)
        essay = self.ids()["06 Work/Essay.docx"]

        def two_canonical(entries):
            for c in entries[essay]["copies"]:
                c["kind"] = "canonical"
        before = tree_digest(self.path("_Audit", "extract"))
        for change, why in ((two_canonical, "3 live paths, canonical ['06 Work/Essay.docx', '04 Study/Essay.docx', "
                                            "'05 Archive/Essay.docx']"),
                            (lambda en: en[essay].__setitem__("current_path", "04 Study/Essay.docx"),
                             "canonical ['06 Work/Essay.docx'], current path '04 Study/Essay.docx'"),
                            (lambda en: en[self.ids()["06 Work/Contract.docx"]].__setitem__(
                                "current_path", "06 Work/Essay.docx"), "is also held by")):
            with self.subTest(why=why):
                self.tool("audit.py")
                self.unsettle(change)
                for args in ([], ["--apply"]):
                    err = self.repath(*args, code=2)
                    self.assertIn("refused, nothing written", err)
                    self.assertIn(essay, err)
                    self.assertIn(why, err)
                self.assertEqual(tree_digest(self.path("_Audit", "extract")), before)

    def test_read_only_root(self):
        self.move_and_audit(*self.MOVED)
        before = read(self.record, "rb")
        self.assertEqual(self.repath("--read-only-root")["paths_changed"], 1)
        self.assertIn("--read-only-root", self.repath("--apply", "--read-only-root", code=2))
        self.assertEqual(read(self.record, "rb"), before)
        elsewhere = os.path.join(self.tmp, "extract")
        shutil.copytree(self.path("_Audit", "extract"), elsewhere)
        self.repath("--apply", "--read-only-root", "--out", elsewhere)
        self.assertEqual(json.loads(read(os.path.join(elsewhere, self.eid + ".json")))["path"], self.MOVED[1])
        self.assertEqual(read(self.record, "rb"), before)

    def test_a_malformed_record_is_refused(self):
        write(self.record, json.dumps({"id": "another", "path": self.MOVED[0]}))
        self.assertIn("is not an extract record for %s" % self.eid, self.repath(code=2))


class FixtureBuildTest(unittest.TestCase):
    """The committed prepared records are what fixture/build.py writes (`--prepared-only`)."""

    def test_build_and_committed_records_agree(self):
        tmp = os.path.realpath(tempfile.mkdtemp(prefix="readiness_build_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        root = os.path.join(tmp, "Alex Personal")
        shutil.copytree(FIXTURE, root)
        for rel in PREPARED:
            (shutil.rmtree if os.path.isdir(os.path.join(root, rel)) else os.remove)(os.path.join(root, rel))
        r = subprocess.run([sys.executable, os.path.join(HERE, "fixture", "build.py"), "--prepared-only", "--out", tmp],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(tree_digest(root), tree_digest(FIXTURE), "run build.py --prepared-only and commit the result")


if __name__ == "__main__":
    unittest.main()
