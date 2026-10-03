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
import readiness  # noqa: E402
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


ENGLISH_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                  "November", "December")


class MonthDayTest(unittest.TestCase):
    """`month_day` reads a yearly date as family-ai-os's roll-up reader does, so both sides accept the same ones."""

    def test_every_month_by_its_full_name_and_its_first_three_letters(self):
        for number, name in enumerate(ENGLISH_MONTHS, 1):
            for spelling in (name, name[:3], name.upper(), name.lower()):
                self.assertEqual(readiness.month_day("5 " + spelling), "%02d-05" % number, spelling)
                self.assertEqual(readiness.month_day(spelling + " 5"), "%02d-05" % number, spelling)

    def test_the_spellings_a_person_writes(self):
        for text, want in (("5 April", "04-05"), ("5th April", "04-05"), ("April 5", "04-05"), ("april 5th", "04-05"),
                           ("5 Apr", "04-05"), ("1st Jan", "01-01"), ("2nd Feb", "02-02"), ("3rd March", "03-03"),
                           ("4th May", "05-04"), ("Sept 9", "09-09"), ("9 Sept", "09-09"), ("9 sept", "09-09"),
                           ("9 SEPT", "09-09"), ("9 Sep", "09-09"), ("  31 December ", "12-31"),
                           ("29 February", "02-29"), ("Feb 29th", "02-29"), ("5   April", "04-05")):
            self.assertEqual(readiness.month_day(text), want, text)

    def test_mm_dd_is_month_first_with_two_digits_each(self):
        for text in ("04-05", "06-04", "02-29", "12-31", " 01-31 "):
            self.assertEqual(readiness.month_day(text), text.strip())
        self.assertEqual(readiness.month_day("06-04"), "06-04", "month first: 4 June, not 6 April")

    def test_any_other_numeric_form_is_refused(self):
        for text in ("4-5", "6-4", "04-5", "4-05", "6/4", "06/04", "6.4", "06.04", "0405", "--04-05", "2026-04-05",
                     "5 April 2026", "5", "April", "", "5 4"):
            self.assertIsNone(readiness.month_day(text), text)

    def test_a_day_the_month_cannot_have_is_refused(self):
        for text in ("13-01", "00-10", "02-30", "04-31", "31 April", "30 February", "0 April", "April 32",
                     "5 Smarch", "5 Sepember"):
            self.assertIsNone(readiness.month_day(text), text)

    def test_a_full_stop_after_the_month_is_not_a_spelling_family_ai_os_reads(self):
        for text in ("5 Apr.", "Sept. 5", "5 Sept."):
            self.assertIsNone(readiness.month_day(text), text)

    def test_a_run_is_read_whole_and_a_date_beside_a_note_is_still_a_date(self):
        for line, want in (("- 5th Apr: tax year ends", [("5th Apr", "04-05")]), ("| Sept 5 |", [("Sept 5", "09-05")]),
                           ("| 5 Sept | school fees |", [("5 Sept", "09-05")]),
                           ("- **9 sept**: fees", [("9 sept", "09-09")]),
                           ("| 5 Apr. | tax year ends |", [("5 Apr", "04-05")]),
                           ("| 5 Sept (fees) |", [("5 Sept", "09-05")]),  # a bracket ends the run
                           ("| 5 April | 6 April |", [("5 April", "04-05"), ("6 April", "04-06")]),
                           ("| <b>5 Sept</b> |", [("5 Sept", "09-05")]), ("1) 5 Sept", [("5 Sept", "09-05")]),
                           ("- [ ] 5 Sept", [("5 Sept", "09-05")]), ("- [5 Sept](x.md)", [("5 Sept", "09-05")]),
                           ("> - 5 Sept", [("5 Sept", "09-05")]), ("> 5 Sept", [("5 Sept", "09-05")]),
                           ("- **01-31**: self assessment", [("01-31", "01-31")])):
            self.assertEqual(readiness.hand_kept(line), want, line)

    def test_a_run_the_contract_does_not_read_whole_is_unreadable_whatever_it_holds(self):
        """The rule: a number of one or two digits (with or without an ordinal) beside a word of three letters or more,
        with at most one short joining word between, or two numbers of one to four digits joined by - / or ., is a
        hand-kept date; one the contract does not read is reported as written. A year makes the run longer than a
        date, so a day and month with a year is never a yearly one, `5 Sept 26` as much as `5 Sept 2026`."""
        for line, run in (("| 31-12 | year end |", "31-12"), ("- 31-12: year end", "31-12"), ("| 13-01 |", "13-01"),
                          ("| 02-30 |", "02-30"), ("| 00-10 |", "00-10"), ("| 12-32 |", "12-32"),
                          ("| 6/4 |", "6/4"), ("| 31/12 |", "31/12"), ("| 5.4 |", "5.4"),
                          ("| 5th of April |", "5th of April"), ("| April the 5th |", "April the 5th"),
                          ("| 5. September |", "5. September"), ("| 5 Setpember |", "5 Setpember"),
                          ("| 5 Septmber |", "5 Septmber"), ("| 5 Sept 26 |", "5 Sept 26"),
                          ("| 5 Sept '26 |", "5 Sept '26"), ("| 5 Sept 2026 |", "5 Sept 2026"),
                          ("| September 5, 2026 |", "September 5, 2026"), ("- 5 April 2026: fees", "5 April 2026"),
                          ("| 31 Sept |", "31 Sept"), ("| 31 April | nonsense |", "31 April"),
                          ("| 32 Jan |", "32 Jan"), ("| Sept 31 |", "Sept 31"), ("> - 5 Septmber", "5 Septmber"),
                          ("| 12 Decisions |", "12 Decisions"), ("| 5 items | none |", "5 items"),
                          ("- 5 April tax year ends", "5 April tax year ends"), ("| 5Sept |", "5Sept"),
                          ("| Sept. 5 |", "Sept. 5"), ("pages 10-12", "pages 10-12")):
            self.assertEqual(readiness.hand_kept(line), [(run, None)], line)

    def test_a_line_that_is_no_date_is_no_candidate(self):
        for line in ("| Date | What |", "| --- | --- |", "| April 2026 |", "# Deadlines", "## Every year", "Alex rents",
                     "- **2025-04-30**: lease ends", "_File-derived deadlines, rolled up from page frontmatter._",
                     "> [!warning] The roll-up found no frontmatter deadlines across 11 pages.",
                     "> **Roll-up found no frontmatter deadlines across 11 readable pages.**", "- 5 of", ""):
            self.assertEqual(readiness.hand_kept(line), [], line)


class GreenTest(Prepared):
    def test_the_fixture_is_green(self):
        res = self.readiness(code=0)
        self.assertEqual(res["findings"], [])
        self.assertEqual([k for k, _v in res["not_verified"]], GREEN_UNVERIFIED)
        self.assertEqual(res["records"], {"missing_extracts": 0, "missing_cards": 0, "malformed_cards": 0,
                                          "malformed_extracts": 0, "bad_category": 0,
                                          "extract_paths_stale": 0, "contamination": "not verified: no --terms"})
        self.assertEqual(res["wiki_handoff"], {"rationale_file": "ok", "pages_accepted": "12/12",
                                               "pages_not_accepted": 0, "pages_not_verified": 0,
                                               "records_for_no_page": []})
        self.assertEqual(set(res["handoff_contract"].values()), {"ok"})

    def test_terms_and_passing_canaries_leave_nothing_unverified(self):
        terms = os.path.join(self.tmp, "terms.txt")
        write(terms, TERMS)
        self.canary("agy", reply="NAMES: Kobelumi", hits=0, usage={}, answered=True, marker="Kobelumi",
                    model="gemini-fake-high", effort=None, **{"pass": True})
        self.canary("codex", reply="NAMES: Kobelumi", hits=0, usage={}, answered=True, marker="Kobelumi",
                    model="gpt-fake", effort="low", **{"pass": True})
        res = self.readiness("--terms", terms, code=0)
        self.assertEqual((res["not_verified"], res["records"]["contamination"]), ([], 0))
        self.assertEqual(res["isolation"], {"canary": {"agy": "passed (model gemini-fake-high)",
                                                       "codex": "passed (model gpt-fake, effort low)"}})
        self.canary("agy", reply="NAMES: Kobelumi", hits=0, usage={}, answered=True, marker="Kobelumi",
                    **{"pass": True})  # from a canary that recorded no model
        self.assertEqual(self.readiness("--terms", terms, code=0)["isolation"]["canary"]["agy"],
                         "passed (model not recorded)")

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
                       "> [!warning]\n> The roll-up found no frontmatter deadlines across 11 pages.\n")
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
        self.assertIn("1 recurring: entr(ies) not {date, note} with a date as MM-DD (month first)",
                      self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))

    def test_a_hand_kept_table_of_yearly_dates_in_words(self):
        """The shape a real prepared folder held: a table on the roll-up, the dates written as a day and a month."""
        p = self.page(DEADLINES)
        write(p, read(p) + "\n## Every year\n\n| Date | What |\n| --- | --- |\n| 31 January | self assessment |\n"
                           "| 5 April | the tax year ends |\n")
        self.accept_again(DEADLINES)
        self.assertIn("2 yearly date(s) no page's recurring: list carries (line 17: 01-31; line 18: 04-05)",
                      self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))

    def test_a_recurring_date_in_words_shown_in_words(self):
        self.add_recurring("{date: 31 January, note: Self assessment return due}")
        p = self.page(DEADLINES)
        write(p, read(p) + "\n## Every year\n\n"
                           "- **31 January**: self assessment return due ([Tax](../20%20Finance/Tax.md))\n")
        self.accept_again(DEADLINES)
        self.readiness(code=0)

    def test_a_hand_kept_row_in_the_british_abbreviation_is_flagged_like_the_others(self):
        """`Sept` was read as no month, so a hand-kept row written `5 Sept` passed while `5 Sep` and `5 September`
        were flagged."""
        p = self.page(DEADLINES)
        write(p, read(p) + "\n## Every year\n\n| Date | What |\n| --- | --- |\n| 5 Sept | school fees |\n"
                           "| Sept 7th | school trip |\n| 5 Sep | school books |\n"
                           "| 5 September | school fees again |\n")
        self.accept_again(DEADLINES)
        self.assertIn("4 yearly date(s) no page's recurring: list carries (line 17: 09-05; line 18: 09-07; "
                      "line 19: 09-05; line 20: 09-05)",
                      self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))

    def roll_up_with(self, text):
        """The roll-up page with `text` after an "Every year" heading (not accepted again, so only the roll-up's own
        check is read back)."""
        p = self.page(DEADLINES)
        shutil.copy(os.path.join(self.template, WIKI, *DEADLINES.split("/")), p)
        write(p, read(p) + "\n## Every year\n\n" + text)
        return self.readiness()["handoff_contract"]["recurring_dates_in_frontmatter"]

    TABLE = "| Date | What |\n| --- | --- |\n| %s | school fees |\n"

    def test_a_hand_kept_date_in_any_shape_is_a_finding_never_dropped(self):
        """Each of these read as ok: the one rule is a number beside a word, or two numbers joined by - / or ., on
        any line of the roll-up, in a cell, a list item, a quote, a checkbox, a link or HTML."""
        unreadable = ("31-12", "13-01", "02-30", "00-10", "12-32", "6/4", "31/12", "5.4", "5th of April",
                      "April the 5th", "5. September", "5 Setpember", "5 Septmber", "5 Sept 26", "5 Sept '26",
                      "5 Sept 2026", "31 Sept", "31 April", "12 Decisions")
        for cell in unreadable:
            with self.subTest(cell=cell):
                self.assertIn("1 unreadable yearly date(s) (line 17: %s)" % cell, self.roll_up_with(self.TABLE % cell))
        for cell in ("5 Sept (fees)", "<b>5 Sept</b>", "[5 Sept](x.md)", "**5** Sept"):
            with self.subTest(cell=cell):
                self.assertIn("1 yearly date(s) no page's recurring: list carries (line 17: 09-05)",
                              self.roll_up_with(self.TABLE % cell))
        for line, want in (("- 31-12: year end\n", "1 unreadable yearly date(s) (line 15: 31-12)"),
                           ("- 5th of April: fees\n", "1 unreadable yearly date(s) (line 15: 5th of April)"),
                           ("> - 31 Sept\n", "1 unreadable yearly date(s) (line 15: 31 Sept)"),
                           ("> - 5 Sept\n", "1 yearly date(s) no page's recurring: list carries (line 15: 09-05)"),
                           ("- [ ] 5 Sept\n", "1 yearly date(s) no page's recurring: list carries (line 15: 09-05)"),
                           ("- [5 Sept](x.md)\n", "1 yearly date(s) no page's recurring: list carries "
                                                   "(line 15: 09-05)"),
                           ("1) 5 Sept\n", "1 yearly date(s) no page's recurring: list carries (line 15: 09-05)"),
                           ("<td>5 Sept</td>\n", "1 yearly date(s) no page's recurring: list carries "
                                                  "(line 15: 09-05)"),
                           ("Fees are due on 5 Sept each year.\n", "1 unreadable yearly date(s)")):
            with self.subTest(line=line):
                self.assertIn(want, self.roll_up_with(line))

    def test_a_date_a_page_carries_but_the_roll_up_does_not_render_is_kept_by_hand(self):
        """The date is backed, but a table row is not an entry the roll-up renders from the list."""
        self.add_recurring("{date: 5 Sept, note: School fees due}")
        found = self.roll_up_with(self.TABLE % "5 Sept (school fees)")
        self.assertIn("1 yearly date(s) a page's recurring: list carries, kept by hand beside the roll-up's entries "
                      "rather than rolled up from the list (line 17: 09-05)", found)

    def rendered_checks(self, body):
        """`readiness.deadline_items` on the roll-up page holding `body`: (dated, recurring, other derived)."""
        p = self.page(DEADLINES)
        write(p, read(os.path.join(self.template, WIKI, *DEADLINES.split("/"))).split("# Deadlines")[0]
              + "# Deadlines\n\n" + body)
        wiki = self.path(WIKI)
        return readiness.deadline_items(wiki, readiness.W.wiki_pages(wiki), None)

    def test_a_page_of_exactly_what_the_roll_up_renders_is_clean(self):
        """The roll-up renders `- **<day> <Month name>** \u2014 <page titles> \u2014 <note> (<links>)`: titles and
        links hold digits (`30 Home`), and a note may hold a number; none is a hand-kept date. Read through
        `deadline_items` itself, since the roll-up's em dash is a problem of `wiki.py check`, not of this scan."""
        self.add_recurring("{date: 04-05, note: Pay 2 instalments}")
        self.edit_page("30 Home/30 Home.md", "status: current\n",
                       "status: current\nrecurring:\n  - {date: 5 April, note: Pay 2 instalments}\n"
                       "  - {date: 31 January, note: Return due in 2 weeks}\n")
        def link(rel):
            return "[%s](../%s.md)" % (rel, rel.replace(" ", "%20"))

        def entry(when, titles, note, *rels):
            return "- **%s** \u2014 %s \u2014 %s (%s)\n" % (when, titles, note, ", ".join(link(r) for r in rels))
        body = ("_File-derived deadlines, rolled up deterministically from page frontmatter \u2014 do not hand-edit._"
                "\n\n## Upcoming\n\n" + entry("2025-04-30", "30 Home", "Lease ends", "30 Home/30 Home")
                + entry("2031-07-15", "10 Identity", "passport expires", "10 Identity/10 Identity")
                + "\n## Every year\n\n"
                + entry("31 January", "30 Home", "Return due in 2 weeks", "30 Home/30 Home")
                + entry("5 April", "Tax, 30 Home", "Pay 2 instalments", "20 Finance/Tax", "30 Home/30 Home"))
        dated, yearly, _other = self.rendered_checks(body)
        self.assertEqual((dated, yearly), ("ok", "ok"))
        added = entry("5 April", "Tax", "Pay 2 instalments, and 3 weeks later", "20 Finance/Tax")
        _dated, yearly, _other = self.rendered_checks(body + added)
        self.assertIn("1 unreadable yearly date(s) (line 19: and 3 weeks later)", yearly)

    def test_the_empty_roll_up_banner_the_roll_up_renders_is_clean(self):
        """Its own count of pages read is no date."""
        dash = " \u2014 "
        _dated, yearly, _other = self.rendered_checks(
            "> **Roll-up found no frontmatter deadlines across 11 readable pages" + dash + "likely a keying fault, "
            "not a deadline-free wiki.** Record each forward date as a `deadline:` key, and each date that falls "
            "every year as a `recurring:` key.\n")
        self.assertEqual(yearly, "ok")

    def test_a_recurring_date_written_sept_matches_the_roll_up(self):
        self.add_recurring("{date: 5 Sept, note: School fees due}")
        p = self.page(DEADLINES)
        write(p, read(p) + "\n## Every year\n\n- **5 September**: school fees due ([Tax](../20%20Finance/Tax.md))\n")
        self.accept_again(DEADLINES)
        self.readiness(code=0)

    def test_a_recurring_date_with_a_full_stop_is_refused(self):
        self.add_recurring("{date: 5 Sept., note: School fees due}")
        self.assertIn("1 recurring: entr(ies) not {date, note} with a date as MM-DD",
                      self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))

    def test_an_ambiguous_numeric_yearly_date_is_refused(self):
        self.add_recurring("{date: 31/1, note: Self assessment return due}")
        self.assertIn("not {date, note} with a date as MM-DD",
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

    def test_numbers_joined_by_a_dash_that_are_no_month_and_day_are_reported(self):
        """These read as ok while only a month and day were looked for; the one rule reports two numbers joined by
        - / or ., since a hand-kept date can be written that way round (`31-12`) and over-reporting is the safe side."""
        self.add_to_roll_up("- 13-45 units of electricity\n- 01-31-2025 is not a month and day\n"
                            "- 01-3122 is a meter reading\n")
        detail = self.one_finding("handoff_contract.recurring_dates_in_frontmatter")
        self.assertIn("3 unreadable yearly date(s) (line 12: 13-45 units of electricity; line 13: 01-31-2025 is not a "
                      "month and day; line 14: 01-3122 is a meter reading)", detail)

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

    def test_a_page_range_in_prose_is_reported_too(self):
        """"pages 10-12" was prose when only a month and day were looked for; it is two numbers joined by a dash, so
        the one rule reports it, on any line of the roll-up."""
        self.add_to_roll_up("\nSee pages 10-12 of the lease.\n\n- See pages 10-12 of the lease too.\n")
        self.assertIn("2 unreadable yearly date(s) (line 13: See pages 10-12 of the lease; line 15: See pages 10-12 of "
                      "the lease too)", self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))

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
        self.assertIn("repath them: extract.py repath --root <root> --work <work> --apply", detail)

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
        self.assertIn("the engine gave no usable answer (timeout)", self.one_finding("isolation.canary.codex"))
        self.canary("codex", reply="I cannot list that.", hits=0, answered=False, usage={}, marker="Kobelumi",
                    error="the reply did not repeat the test name Kobelumi", **{"pass": False})
        finding = self.one_finding("isolation.canary.codex")
        self.assertIn("no usable answer (the reply did not repeat the test name Kobelumi", finding)
        self.assertNotIn("0 isolation term(s)", finding)

    def test_a_pass_without_the_marker_is_not_verified_never_passed(self):
        """A result from the canary that a refusal could pass (no marker, or no `answered`), or one edited to claim a
        pass, is a named not-verified state: not a pass, and not a finding either."""
        cases = {"the old canary": dict(reply="NONE", hits=0, usage={}),
                 "answered but no marker": dict(reply="NAMES: x", hits=0, usage={}, answered=True),
                 "an empty marker": dict(reply="NAMES: x", hits=0, usage={}, answered=True, marker=""),
                 "a marker but not answered": dict(reply="NAMES: x", hits=0, usage={}, answered=False,
                                                   marker="Kobelumi")}
        for name, fields in cases.items():
            with self.subTest(name):
                self.canary("agy", **dict(fields, **{"pass": True}))
                res = self.readiness(code=0)
                state = res["isolation"]["canary"]["agy"]
                self.assertTrue(state.startswith("not verified: state/canary-agy.json records a pass without the "
                                                 "invented name"), state)
                self.assertIn(["isolation.canary.agy", state], res["not_verified"])
                self.assertNotIn("isolation.canary.agy", [k for k, _v in res["findings"]])

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
        self.assertEqual(self.one_finding("wiki.problems"), "wiki.py check reports 1 problem(s); 1 backticked "
                         "path(s) were not checked against the folder (a pattern, or outside the live folders)")

    def test_a_dead_path_with_brackets_is_a_problem_beside_the_unchecked_count(self):
        """A missing path is a problem even when its name holds `[` or `?`; the paths a run could not check are
        counted next to the problems, in the finding and in the wiki block, not only as a not-verified string."""
        self.edit_page(TAX, "Nothing is due:", "Nothing is due (see `02 Finance/Statement [final].pdf` and "
                       "`02 Finance/Statement*/`):")
        res = self.readiness(code=1)
        self.assertEqual(res["findings"], [["wiki.problems", "wiki.py check reports 1 problem(s); 2 backticked "
                                            "path(s) were not checked against the folder (a pattern, or outside the "
                                            "live folders)"]])
        self.assertEqual((res["wiki"]["problems"], res["wiki"]["backticked_paths_unchecked"]), (1, 2))

    def plant_bad_records(self):
        """Four extract records of four kinds (not JSON, not UTF-8, pages not a list, not an object) and three
        cards of three kinds, with a bad category and a stale path planted among the readable ones."""
        ids = self.ids()
        for doc, raw in (("06 Work/Essay.docx", b"{"), ("06 Work/Contract.docx", b"\xff\xfe\x00"),
                         ("03 Home/Lease renewal.pdf", None), ("04 Study/Slides.pptx", b"[]")):
            p = self.path("_Audit", "extract", ids[doc] + ".json")
            if raw is None:
                raw = json.dumps(dict(json.loads(read(p)), pages="none")).encode()
            with open(p, "wb") as f:
                f.write(raw)
        for doc, change in (("04 Study/Notes.rtf", "["), ("02 Finance/Bank statement 2024-03.pdf", "[]"),
                            ("03 Home/Lease notes .txt", "sensitive")):
            p = self.card(doc)
            write(p, json.dumps(dict(json.loads(read(p)), sensitive="yes")) if change == "sensitive" else change)
        p = self.card("04 Study/Cours de fran\u00e7ais.pdf")
        write(p, json.dumps(dict(json.loads(read(p)), category="Hobbies"), indent=1))
        p = self.path("_Audit", "extract", ids["01 Identity/Passport scan.pdf"] + ".json")
        write(p, json.dumps(dict(json.loads(read(p)), path="01 Identity/Old scan.pdf")))

    def test_every_malformed_card_is_counted_and_the_other_checks_still_run(self):
        """Every malformed card is counted and named, and the other checks still run: stopping at the first one
        hid how many a folder held (a real prepared folder had 67)."""
        self.plant_bad_records()
        os.remove(self.path("_Audit", "extract", self.ids()["03 Home/Lease notes .txt"] + ".json"))  # card and extract
        res = self.readiness(code=1)
        self.assertEqual({k: res["records"][k] for k in ("malformed_cards", "bad_category", "missing_extracts")},
                         {"malformed_cards": 3, "bad_category": 1, "missing_extracts": 1})
        detail = dict(res["findings"])["records.malformed_cards"]
        self.assertTrue(detail.startswith("3 card(s) not in the card format"), detail)
        for doc in ("04 Study/Notes.rtf", "02 Finance/Bank statement 2024-03.pdf", "03 Home/Lease notes .txt"):
            self.assertIn(doc, detail)
        self.assertIn("04 Study/Cours de fran\u00e7ais.pdf: 'Hobbies'", dict(res["findings"])["records.bad_category"])
        self.assertIn("03 Home/Lease notes .txt", dict(res["findings"])["records.missing_extracts"])

    def test_every_malformed_extract_record_is_counted_and_the_other_checks_still_run(self):
        """An extract record that is not JSON, not UTF-8, not an object or holds pages that are not a list ends no
        check: each is counted and named, and the checks after it still run."""
        self.plant_bad_records()
        res = self.readiness(code=1)
        self.assertEqual(res["records"]["malformed_extracts"], 4)
        detail = dict(res["findings"])["records.malformed_extracts"]
        self.assertTrue(detail.startswith("4 extract record(s) not in the extract format; remove each and run "
                                          "extract.py again ("), detail)
        self.assertNotIn(self.root, detail, "a document is named by its path in the folder, never an absolute path")
        for doc, why in (("06 Work/Essay.docx", "not valid JSON"), ("06 Work/Contract.docx", "not valid JSON"),
                         ("03 Home/Lease renewal.pdf", "pages must be a list"),
                         ("04 Study/Slides.pptx", "expected a JSON object")):
            self.assertIn("%s: %s" % (doc, why), detail)
        self.assertEqual(res["records"]["bad_category"], 1)  # the checks after the bad records still ran
        self.assertEqual(res["records"]["malformed_cards"], 3)
        self.assertEqual(res["records"]["missing_extracts"], 0, "a record that is there is not missing")
        self.assertEqual(sorted(k for k, _v in res["findings"]),
                         ["records.bad_category", "records.extract_paths_stale", "records.malformed_cards",
                          "records.malformed_extracts"])

    def test_an_extract_page_with_a_null_number_is_counted_not_a_crash(self):
        """`full_text` formats the page number, so a null one ended a `--terms` run (exit 2) before anything was
        counted; the loader refuses it, and it is counted like any malformed record."""
        terms = os.path.join(self.tmp, "terms.txt")
        write(terms, TERMS)
        p = self.path("_Audit", "extract", self.ids()["06 Work/Contract.docx"] + ".json")
        write(p, json.dumps(dict(json.loads(read(p)), pages=[{"n": None, "text": "x"}])))
        res = self.readiness("--terms", terms, code=1)
        self.assertEqual(res["records"]["malformed_extracts"], 1)
        self.assertIn("06 Work/Contract.docx: page 1 must be an object whose n is a whole number",
                      dict(res["findings"])["records.malformed_extracts"])

    def test_an_unreadable_record_is_named_by_its_path_in_the_folder(self):
        """A record that is a folder, or has no read permission, names the file as the folder holds it: no finding
        carries the absolute path of the machine it was run on."""
        ids = self.ids()
        extract = self.path("_Audit", "extract", ids["06 Work/Contract.docx"] + ".json")
        card = self.card("04 Study/Notes.rtf")
        for p in (extract, card):
            os.remove(p)
            os.mkdir(p)
        locked = self.path("_Audit", "extract", ids["04 Study/Slides.pptx"] + ".json")
        os.chmod(locked, 0)
        self.addCleanup(os.chmod, locked, 0o644)
        res = self.readiness(code=1)
        found = dict(res["findings"])
        self.assertIn("06 Work/Contract.docx: cannot read _Audit/extract/", found["records.malformed_extracts"])
        self.assertIn("04 Study/Notes.rtf: cannot read _Audit/cards/", found["records.malformed_cards"])
        self.assertEqual(res["records"]["malformed_extracts"], 1 if os.access(locked, os.R_OK) else 2)
        self.assertNotIn(self.root, json.dumps(res["findings"]))

    def test_the_repath_advice_says_what_repath_refuses(self):
        """`extract.py repath` refuses a record that is not valid JSON, not an object or without its id and path; it
        runs beside one whose pages are the wrong shape. The advice says exactly that, and puts those first."""
        ids = self.ids()
        p = self.path("_Audit", "extract", ids["04 Study/Notes.rtf"] + ".json")
        write(p, json.dumps(dict(json.loads(read(p)), path="04 Study/Old notes.rtf")))
        self.assertIn("; repath them: extract.py repath", dict(self.readiness(code=1)["findings"])[
            "records.extract_paths_stale"])
        shape = self.path("_Audit", "extract", ids["03 Home/Lease renewal.pdf"] + ".json")
        write(shape, json.dumps(dict(json.loads(read(shape)), pages="none")))
        code, _out, _err = run("extract.py", "repath", "--root", self.root, "--work", self.work)
        self.assertEqual(code, 0, "a record whose pages are the wrong shape does not stop repath")
        broken = self.path("_Audit", "extract", ids["06 Work/Contract.docx"] + ".json")
        write(broken, "{")
        detail = dict(self.readiness(code=1)["findings"])["records.extract_paths_stale"]
        self.assertIn("; repath refuses a record that is not valid JSON, not a JSON object, or without its id and "
                      "path, so remove or redo any such malformed extract record first, then repath them: "
                      "extract.py repath", detail)
        code, _out, err = run("extract.py", "repath", "--root", self.root, "--work", self.work, "--apply")
        self.assertEqual(code, 2, "the advice is right: repath refuses beside a record that is not JSON")
        self.assertIn("cannot repath", err)

    def test_a_record_nested_too_deeply_is_counted_not_a_crash(self):
        """200,000 opening brackets raise RecursionError in the JSON reader; readiness exited 2 having counted
        nothing, for an extract record and for a card alike."""
        ids = self.ids()
        write(self.path("_Audit", "extract", ids["06 Work/Contract.docx"] + ".json"), "[" * 200000)
        write(self.card("04 Study/Notes.rtf"), "[" * 200000)
        res = self.readiness(code=1)
        self.assertEqual((res["records"]["malformed_extracts"], res["records"]["malformed_cards"]), (1, 1))
        found = dict(res["findings"])
        self.assertIn("06 Work/Contract.docx: not valid JSON (", found["records.malformed_extracts"])
        self.assertIn("04 Study/Notes.rtf: ", found["records.malformed_cards"])

    def test_no_finding_carries_a_path_of_this_machine(self):
        """Every finding and every not-verified state of a run that raises most of them, with an explicit manifest."""
        terms = os.path.join(self.tmp, "terms.txt")
        write(terms, TERMS)
        self.plant_bad_records()
        self.canary("codex", reply="<term>", hits=1, usage={}, **{"pass": False})
        shutil.move(self.path("04 Study", "Slides.pptx"), self.path("04 Study", "Gone.pptx"))
        os.remove(self.path("_Audit", "wiki-rationale.md"))
        os.makedirs(self.path("_Audit", "scratch"))
        self.edit_rulebook("`GEMINI.md`, ", "")
        self.edit_page(TAX, "Nothing is due:", "Nothing is due \u2014")
        self.edit_page(TAX, "status: current\n", "status: current\nrecurring:\n"
                       "  - {date: 2025-01-31, note: Self assessment return due}\n")
        res = self.readiness("--terms", terms, "--manifest", self.path("_Audit", "manifest.json"), code=1)
        keys = {k for k, _v in res["findings"]}
        self.assertTrue({"records.extract_paths_stale", "records.malformed_extracts", "records.malformed_cards",
                         "isolation.canary.codex", "manifest.live_paths_missing", "wiki.problems",
                         "wiki_handoff.rationale_file", "scratch.left_in_audit",
                         "handoff_contract.recurring_dates_in_frontmatter",
                         "handoff_contract.rulebook_reserves_rulebook_filenames"} <= keys, keys)
        text = json.dumps(res["findings"] + res["not_verified"], ensure_ascii=False)
        for here in {self.root, self.work, self.tmp, os.path.realpath(self.root), os.path.realpath(self.work)}:
            self.assertNotIn(here, text)
        self.assertIn("--manifest <manifest>", dict(res["findings"])["records.extract_paths_stale"])

    def test_a_check_that_needed_a_malformed_extract_record_is_not_verified(self):
        """The stale-path check reads each record's path, so a record it could not read is not verified, never a
        clean count; the paths it could read still count."""
        self.plant_bad_records()
        res = self.readiness(code=1)
        gap = "not verified for 4 document(s) whose extract record is malformed"
        self.assertEqual(res["records"]["extract_paths_stale"], "1; " + gap)
        self.assertIn(["records.extract_paths_stale", "1; " + gap], res["not_verified"])
        self.assertIn("1 extract record(s) whose path the manifest no longer holds",
                      dict(res["findings"])["records.extract_paths_stale"])
        p = self.path("_Audit", "extract", self.ids()["01 Identity/Passport scan.pdf"] + ".json")
        write(p, json.dumps(dict(json.loads(read(p)), path="01 Identity/Passport scan.pdf")))  # none stale now
        res = self.readiness(code=1)
        self.assertEqual(res["records"]["extract_paths_stale"], gap)
        self.assertIn(["records.extract_paths_stale", gap], res["not_verified"])

    def test_contamination_is_not_verified_for_a_document_with_a_malformed_card_or_extract(self):
        """A malformed card, or one whose extract record is malformed, cannot be checked for a term its source
        lacks: its count reads not verified, not a clean 0."""
        terms = os.path.join(self.tmp, "terms.txt")
        write(terms, TERMS)
        self.plant_bad_records()  # 3 malformed cards and 4 malformed extract records, on 7 different documents
        res = self.readiness("--terms", terms, code=1)
        gap = "not verified for 7 document(s) whose card or extract record is malformed"
        self.assertEqual(res["records"]["contamination"], gap)
        self.assertIn(["records.contamination", gap], res["not_verified"])

    def test_a_contamination_found_beside_a_document_not_verified(self):
        terms = os.path.join(self.tmp, "terms.txt")
        write(terms, TERMS)
        p = self.card("02 Finance/Tax/Tax return 2023.pdf")
        card = json.loads(read(p))
        write(p, json.dumps(dict(card, summary=card["summary"] + " Reviewed at Zarnwick Farm."), indent=1))
        write(self.card("06 Work/Contract.docx"), "[]")
        res = self.readiness("--terms", terms, code=1)
        self.assertEqual(res["records"]["contamination"],
                         "1; not verified for 1 document(s) whose card or extract record is malformed")
        self.assertIn("02 Finance/Tax/Tax return 2023.pdf", dict(res["findings"])["records.contamination"])

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
        command = [x.replace("<root>", self.root).replace("<work>", self.work) for x in shlex.split(
            self.one_finding("records.extract_paths_stale").split("repath them: ", 1)[1])]
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
