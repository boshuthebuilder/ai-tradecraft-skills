"""`readiness.py`, the hand-off contract, and `extract.py repath`, on copies of the prepared fixture.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests

The fixture is a prepared folder: its extract records, cards and acceptance record are committed with it (written
by fixture/build.py). Once per class a template copy is audited into its own _Audit/ and its Schema compiled; each
test copies the template, plants one defect and asserts it is the one finding. A page a test edits is accepted again
(`wiki.py accept`, by a model other than its author), so the edit is the only thing that changed. The committed
fixture is never touched.
"""
import contextlib
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.realpath(os.path.join(HERE, "..", "tools"))
sys.path.insert(0, TOOLS)
import common  # noqa: E402
import extract  # noqa: E402
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
        self.assertEqual(res["records"], {"missing_extracts": 0, "missing_cards": 0, "malformed_cards": 0,
                                          "bad_category": 0,
                                          "extract_paths_stale": 0, "contamination": "not verified: no --terms"})
        self.assertEqual(res["wiki_handoff"], {"rationale_file": "ok", "pages_accepted": "12/12",
                                               "pages_not_accepted": 0, "pages_not_verified": 0,
                                               "records_for_no_page": []})
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
        self.assertIn("1 date(s) no current page's frontmatter carries (line 12: 2026-01-31)", detail)

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


class RollUpTest(Prepared):
    """How the Deadlines roll-up's dates are read: what passes, and what is the one finding."""

    def add_frontmatter(self, page, lines):
        self.edit_page(page, "status: current\n", "status: current\n" + lines)

    def add_to_roll_up(self, text):
        p = self.page(DEADLINES)
        write(p, read(p) + text)
        self.accept_again(DEADLINES)

    def set_roll_up_stamp(self, value):
        self.edit_page(DEADLINES, "last-updated: 2024-06-30\n", "last-updated: %s\n" % value)

    def test_a_future_last_updated_is_a_finding_and_forward_is_judged_from_today(self):
        self.set_roll_up_stamp("2099-01-01")
        self.assertEqual(self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"),
                         "finding: 01 Deadlines/01 Deadlines.md is last-updated 2099-01-01, after today (2024-06-30)")
        p = self.page(DEADLINES)
        write(p, read(p).split("# Deadlines")[0] + "# Deadlines\n")  # emptied, the pages' deadlines still forward
        self.accept_again(DEADLINES)
        detail = self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written")
        self.assertIn("after today (2024-06-30)", detail)
        self.assertIn("lacks 2 page deadline(s) (2025-04-30 (30 Home/30 Home.md); 2031-07-15 (10 Identity/10 "
                      "Identity.md))", detail)

    def test_an_empty_roll_up_with_only_past_deadlines_says_why(self):
        for page in ("10 Identity/10 Identity.md", "30 Home/30 Home.md"):
            p = self.page(page)
            write(p, re.sub(r"deadlines:\n(  - .*\n)+", "", read(p)))
            self.accept_again(page)
        self.add_frontmatter(TAX, "deadlines:\n  - {date: 2024-01-31, note: Self assessment paid}\n")
        p = self.page(DEADLINES)
        write(p, read(p).split("# Deadlines")[0] + "# Deadlines\n\nNone\n")
        self.accept_again(DEADLINES)
        self.assertIn("an empty roll-up that does not say why",
                      self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))
        self.edit_page(DEADLINES, "None\n", "Nothing forward: the one page deadline, 2024-01-31, is past.\n")
        self.readiness(code=0)

    def test_a_deadline_on_the_stamp_day_must_show(self):
        self.add_frontmatter(TAX, "deadline: 2024-06-30\n")
        self.assertIn("lacks 1 page deadline(s) (2024-06-30 (20 Finance/Tax.md))",
                      self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))

    def test_a_stamp_that_is_no_date_exempts_nothing(self):
        for stamp in ("soon", "2024-02-30"):
            with self.subTest(stamp=stamp):
                self.set_roll_up_stamp(stamp)
                self.edit_page(TAX, "status: current\n", "status: current\ndeadline: 2024-01-31\n")
                self.assertIn("lacks 1 page deadline(s) (2024-01-31 (20 Finance/Tax.md))",
                              self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))
                self.edit_page(TAX, "deadline: 2024-01-31\n", "")
                self.set_roll_up_stamp_back(stamp)

    def set_roll_up_stamp_back(self, value):
        self.edit_page(DEADLINES, "last-updated: %s\n" % value, "last-updated: 2024-06-30\n")

    def test_a_deadline_entry_that_cannot_be_read(self):
        for entry in ("20250131", "[2025-01-31]", "2025-02-30", "{date: 2025-02-30, note: No such day}"):
            with self.subTest(entry=entry):
                self.add_frontmatter(TAX, "deadline: %s\n" % entry)
                self.assertIn("1 deadline entr(ies) not a real YYYY-MM-DD or {date, note} (20 Finance/Tax.md: "
                              "deadline: %s)" % entry,
                              self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))
                self.edit_page(TAX, "deadline: %s\n" % entry, "")

    def test_list_items_that_open_with_no_month_and_day(self):
        self.add_to_roll_up("- 13-45 units of electricity\n- 01-31-2025 is not a month and day\n"
                            "- 01-3122 is a meter reading\n")
        self.readiness(code=0)

    def test_a_single_deadline_with_a_note(self):
        """wiki-maintenance's frontmatter table allows `deadline: {date, note}` as well as a bare date."""
        self.add_frontmatter(TAX, "deadline: {date: 2026-01-31, note: Self assessment payment}\n")
        self.assertIn("lacks 1 page deadline(s) (2026-01-31 (20 Finance/Tax.md))",
                      self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))
        self.add_to_roll_up("- **2026-01-31**: self assessment payment ([Tax](../20%20Finance/Tax.md))\n")
        self.readiness(code=0)

    def test_a_past_deadline_and_a_build_stamp(self):
        """The roll-up lists forward dates: a deadline before its last-updated need not be shown, and its
        last-updated written on it is a build stamp, not a hand-written date."""
        self.add_frontmatter(TAX, "deadlines:\n  - {date: 2024-01-31, note: Self assessment paid}\n")
        self.add_to_roll_up("\nBuilt from the pages' frontmatter on 2024-06-30.\n")
        self.readiness(code=0)
        self.add_to_roll_up("Checked again on 2024-07-01.\n")
        self.assertIn("(line 14: 2024-07-01)",
                      self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))

    def test_month_and_day_in_prose_is_not_a_date(self):
        self.add_to_roll_up("\nSee pages 10-12 of the lease.\n\n- See pages 10-12 of the lease too.\n")
        self.readiness(code=0)

    def test_a_recurring_date_in_a_table_cell(self):
        self.add_to_roll_up("\n| Every year | What |\n| --- | --- |\n| **01-31** | self assessment return due |\n")
        self.assertIn("(line 15: 01-31)", self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))

    def test_a_recurring_entry_needs_a_real_day_and_a_note(self):
        self.add_frontmatter(TAX, "recurring:\n  - {date: 02-30, note: No such day}\n")
        self.assertIn('{"date": "02-30", "note": "No such day"}',
                      self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))
        self.edit_page(TAX, "{date: 02-30, note: No such day}", "{date: 02-28}")
        self.assertIn("{date: 02-28}", self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))
        self.edit_page(TAX, "{date: 02-28}", "{date: 02-29, note: Leap day review}")
        self.add_to_roll_up("\n## Every year\n\n- **02-29**: leap day review ([Tax](../20%20Finance/Tax.md))\n")
        self.readiness(code=0)

    def test_a_recurring_date_is_shown_only_by_its_own_month_and_day(self):
        self.add_frontmatter(TAX, "deadline: 2026-01-31\nrecurring:\n  - {date: 01-31, note: Return due}\n")
        self.add_to_roll_up("- **2026-01-31**: self assessment return due ([Tax](../20%20Finance/Tax.md))\n")
        self.assertIn("lacks 1 recurring date(s) (01-31 (20 Finance/Tax.md))",
                      self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))

    def test_a_superseded_page_has_no_deadline_on_the_roll_up(self):
        home = "30 Home/30 Home.md"
        self.edit_page(home, "status: current", "status: superseded")
        self.assertIn("no current page's frontmatter carries (line 10: 2025-04-30)",
                      self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))
        self.edit_page(DEADLINES, "- **2025-04-30**: lease ends ([30 Home](../30%20Home/30%20Home.md))\n", "")
        self.readiness(code=0)

    def test_another_derived_page_is_reported_apart(self):
        schema = "90 Schema/90 Schema.md"
        self.edit("%s/%s" % (WIKI, schema), "| 02 People | everyone who appears | personal assistant | fixed |",
                  "| 02 People | everyone who appears | personal assistant | fixed, derived |")
        self.tool("settings.py", "compile")
        self.accept_again(schema)
        res = self.readiness(code=0)
        self.assertEqual(res["handoff_contract"]["derived_pages_hold_nothing_hand_written"], "ok")
        self.assertIn(["handoff_contract.other_derived_pages", "not verified: 02 People/02 People.md (derived, built "
                       "from the pages in a way no date shows)"], res["not_verified"])
        self.add_to_roll_up("- **2026-01-31**: renew the parking permit\n")
        self.assertIn("2026-01-31", self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))


class FindingTest(Prepared):
    """Every other check, planted once, is the one finding and sets the exit code."""

    def test_rulebook_copies_differ(self):
        self.edit("AGENTS.md", "Nobody else.", "Nobody else!")
        self.assertIn("differ", self.one_finding("rulebook.copies_identical"))

    def test_a_scratch_folder_left_in_audit(self):
        os.makedirs(self.path("_Audit", "_wikibuild"))
        self.assertIn("_wikibuild", self.one_finding("scratch.left_in_audit"))

    def test_any_other_folder_in_audit_is_scratch(self):
        os.makedirs(self.path("_Audit", "drafts"))
        write(self.path("_Audit", "notes.txt"), "a file is not a scratch folder\n")
        self.assertEqual(self.one_finding("scratch.left_in_audit"), "folders left in _Audit/: drafts")

    def test_the_rulebook_does_not_name_the_wiki_folder(self):
        self.edit_rulebook("- `Alex Personal Wiki/`: the wiki.", "- The wiki folder: the wiki.")
        self.edit_rulebook("`Alex Personal Wiki`, ", "")
        self.assertIn("'Alex Personal Wiki'", self.one_finding("rulebook.names_wiki_folder"))

    def test_a_rulebook_copy_missing(self):
        os.remove(self.path("AGENTS.md"))
        res = self.readiness(code=1)
        self.assertEqual(res["findings"], [["rulebook.present", "finding: missing AGENTS.md"]])
        self.assertIn(["rulebook.copies_identical", "not verified: AGENTS.md missing"], res["not_verified"])

    def test_a_rulebook_not_utf8(self):
        for name in ("CLAUDE.md", "AGENTS.md"):
            with open(self.path(name), "ab") as f:
                f.write(b"\xff")
        p = self.path(".familyai", "rulebook.json")
        data = json.loads(read(p))
        write(p, json.dumps(dict(data, rulebook_sha256=common.sha256_file(self.path("CLAUDE.md"))), indent=1))
        self.assertEqual(self.one_finding("rulebook.valid_utf8"),
                         "finding: not valid UTF-8: CLAUDE.md (byte %d), AGENTS.md (byte %d)"
                         % ((os.path.getsize(self.path("CLAUDE.md")) - 1,) * 2))

    def test_items_on_disk_not_verified_without_a_summary(self):
        os.remove(self.path("_Audit", "summary.json"))
        res = self.readiness(code=0)
        self.assertIn(["manifest.items_on_disk", "not verified: no summary.json beside the manifest"],
                      res["not_verified"])

    def test_records_for_a_page_no_longer_in_the_wiki_are_information(self):
        p = self.path("_Audit", "wiki-acceptance.json")
        acc = json.loads(read(p))
        acc["records"].append(dict(acc["records"][-1], page="20 Finance/Old tax.md"))
        write(p, json.dumps(acc, ensure_ascii=False, indent=1) + "\n")
        res = self.readiness(code=0)
        self.assertEqual(res["wiki_handoff"]["records_for_no_page"], ["20 Finance/Old tax.md"])
        self.assertEqual([k for k, _v in res["not_verified"]], GREEN_UNVERIFIED)

    def test_a_manifest_entry_without_hashed_is_refused(self):
        p = self.path("_Audit", "manifest.json")
        good = read(p)
        for hashed in (None, "yes"):
            with self.subTest(hashed=hashed):
                man = json.loads(good)
                for e in man["entries"].values():
                    e.pop("hashed") if hashed is None else e.__setitem__("hashed", hashed)
                write(p, json.dumps(man, ensure_ascii=False, indent=1))
                self.assertIn("records no hashed true or false", self.refused())

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

    def test_a_malformed_card_is_a_counted_finding_not_the_end(self):
        """Every malformed card is counted and named, and the other checks still run: stopping at the first one
        hid how many a folder held (a real prepared folder had 67)."""
        write(self.card("06 Work/Contract.docx"), "[]")
        self.assertIn("1 card(s) not in the card format", self.one_finding("records.malformed_cards"))

    def test_tool_errors_exit_2(self):
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

    def test_a_manifest_older_than_the_move_is_refused(self):
        """The record is right and the manifest stale: repathing would send the record where nothing is."""
        old = read(self.path("_Audit", "manifest.json"))
        self.move_and_audit(*self.MOVED)
        self.repath("--apply")
        write(self.path("_Audit", "manifest.json"), old)
        before = read(self.record, "rb")
        for args in ([], ["--apply"]):
            err = self.repath(*args, code=2)
            self.assertIn("refused, nothing written: 1 record(s) would move to a path that is not in the folder "
                          "(%s to '%s')" % (self.eid, self.MOVED[0]), err)
            self.assertIn("re-audit (audit.py) first", err)
        self.assertEqual(read(self.record, "rb"), before)

    def test_a_malformed_manifest_is_refused_by_name(self):
        p = self.path("_Audit", "manifest.json")
        man = json.loads(read(p))
        man["entries"][self.eid] = "not an entry"
        for text, why in ((json.dumps(man), "entry %s is malformed" % self.eid), ("[]", "expected a JSON object")):
            with self.subTest(why=why):
                write(p, text)
                self.assertIn(why, self.repath(code=2))

    def two_moves(self):
        """Two documents moved and re-audited: (id, record path, its new path) for each, in the order repath
        writes them (by id)."""
        moves = [self.MOVED, ("06 Work/Contract.docx", "06 Work/Employment contract.docx")]
        ids = self.ids()
        for old, new in moves:
            shutil.move(self.path(*old.split("/")), self.path(*new.split("/")))
        self.tool("audit.py")
        return sorted((ids[old], self.path("_Audit", "extract", ids[old] + ".json"), new) for old, new in moves)

    def apply_in_process(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return extract.repath(["--root", self.root, "--work", self.work, "--apply"])

    def leftovers(self):
        return [n for n in os.listdir(self.path("_Audit", "extract")) if ".repath" in n]

    def test_a_failure_writing_the_second_record_replaces_none(self):
        """The disk fills while the second record's temporary file is written: that file is removed too."""
        (_id1, p1, _n1), (_id2, p2, _n2) = moves = self.two_moves()
        before = [read(p, "rb") for _i, p, _n in moves]
        real, calls, seen = os.fsync, [], []

        def fsync(fd):
            calls.append(fd)
            if len(calls) == 2:
                seen.extend(self.leftovers())  # both temporary files exist when it fails
                raise OSError(28, "No space left on device")
            return real(fd)
        with unittest.mock.patch.object(extract.os, "fsync", fsync):
            with self.assertRaises(common.ToolError) as cm:
                self.apply_in_process()
        self.assertEqual(len(seen), 2)
        self.assertIn("repath stopped, no record replaced: [Errno 28] No space left on device", str(cm.exception))
        self.assertEqual([read(p1, "rb"), read(p2, "rb")], before)
        self.assertEqual(self.leftovers(), [])

    def test_an_interrupt_replacing_the_second_record_leaves_no_temporary_file(self):
        (_id1, p1, n1), (_id2, p2, _n2) = self.two_moves()
        before2 = read(p2, "rb")
        real, calls = os.replace, []

        def replace(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise KeyboardInterrupt()
            return real(src, dst)
        with unittest.mock.patch.object(extract.os, "replace", replace):
            with self.assertRaises(KeyboardInterrupt):
                self.apply_in_process()
        self.assertEqual((json.loads(read(p1))["path"], read(p2, "rb")), (n1, before2))
        self.assertEqual(self.leftovers(), [])

    def test_a_failure_replacing_the_second_record_names_the_first(self):
        (id1, p1, n1), (_id2, p2, _n2) = self.two_moves()
        before2 = read(p2, "rb")
        real, calls = os.replace, []

        def replace(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError(13, "Permission denied")
            return real(src, dst)
        with unittest.mock.patch.object(extract.os, "replace", replace):
            with self.assertRaises(common.ToolError) as cm:
                self.apply_in_process()
        self.assertIn("repath stopped, 1 record(s) already replaced (%s.json): [Errno 13] Permission denied" % id1,
                      str(cm.exception))
        self.assertEqual((json.loads(read(p1))["path"], read(p2, "rb")), (n1, before2))
        self.assertEqual(self.leftovers(), [])

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
