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
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.realpath(os.path.join(HERE, "..", "tools"))
sys.path.insert(0, TOOLS)
import common  # noqa: E402
import extract  # noqa: E402
import readiness  # noqa: E402
FIXTURE = os.path.join(HERE, "fixture", "Alex Personal")
WIKI = "Alex Personal Wiki"
DEADLINES = "01 Deadlines/01 Deadlines.md"
GAP_CARD = "1; not verified for 3 document(s) whose card is malformed"
FIXTURE_INTRO = ("_File-derived deadlines, rolled up deterministically from page frontmatter: do not hand-edit, "
                 "regenerated each run. (Calendar events live in `Coming Events`.)_")
TAX = "20 Finance/Tax.md"
EM = "\u2014"
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


def clear_migrations(folder):
    """`folder` as the owner leaves it once the migrations folder is cleared by hand. The fixture stages one file in it
    for the audit, plan and wiki tools, so the readiness tests start from the folder without that file and without
    its extract record and card."""
    shutil.rmtree(os.path.join(folder, "_Migrations"))
    extracts = os.path.join(folder, "_Audit", "extract")
    for name in os.listdir(extracts):
        if json.loads(read(os.path.join(extracts, name)))["path"].startswith("_Migrations/"):
            os.remove(os.path.join(extracts, name))
            os.remove(os.path.join(folder, "_Audit", "cards", name))


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
        clear_migrations(cls.template)
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

    def refused_finding(self):
        """The recurring finding of a page with a recurring item the roll-up refuses. The roll-up lists that item
        under "Could not read", so a Deadlines page that lacks the line is an incomplete one, a finding beside it."""
        found = dict(self.readiness(code=1)["findings"])
        self.assertEqual(sorted(found), ["handoff_contract.derived_pages_hold_nothing_hand_written",
                                         "handoff_contract.recurring_dates_in_frontmatter"])
        self.assertIn("lacks 1 line(s) of the roll-up's \"Could not read\" list that the pages give (20 Finance/Tax.md "
                      "(unreadable recurring date: ", found["handoff_contract.derived_pages_hold_nothing_hand_written"])
        return found["handoff_contract.recurring_dates_in_frontmatter"]

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
    """`month_day` reads a yearly date as the reference roll-up's reader does, so both sides accept the same ones."""

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

    def test_a_full_stop_after_the_month_is_not_a_spelling_the_roll_up_reads(self):
        for text in ("5 Apr.", "Sept. 5", "5 Sept."):
            self.assertIsNone(readiness.month_day(text), text)

COLON_BANNER_TAIL = (" likely a keying fault, not a deadline-free wiki.** Dates recorded in prose are invisible to "
                     "this roll-up; record each forward date as a `deadline:`/`deadlines:` key, and each date that "
                     "falls every year as a `recurring:` key, on the page that owns it (the reconcile conformance "
                     "count names the pages to fix).")
ONE_LINE_BANNER = "> **Roll-up found no frontmatter deadlines across %d readable pages%s" + COLON_BANNER_TAIL


def link(page):
    """A roll-up's link to a wiki page: its path without `.md` as the text, its path from the Deadlines page as the
    target, percent-encoded as the roll-up encodes it."""
    return "[%s](../%s)" % (page[:-3], urllib.parse.quote(page, safe="/&"))


class RollUpFormsTest(unittest.TestCase):
    """The entry forms a roll-up writes, read by `parse_entry`: the reference roll-up's dashless form, the em-dash
    form it wrote before, and the note-only form of this suite's fixture."""

    LEASE, TAX_PAGE, HOME = "05 Home/Lease.md", "20 Finance/Tax.md", "30 Home/30 Home.md"
    BANK = "20 Finance/Bank statement (1).md"
    PAGES = {LEASE, TAX_PAGE, HOME, BANK, "20 Finance/Tax [Q1](final).md", "20 Finance/x](y.md",
             "10 Identity/Notes.md", "20 Finance/Notes.md"}

    def entry(self, line):
        return readiness.parse_entry(line, self.PAGES)

    def test_the_dashless_form_with_a_note(self):
        line = "- **2026-09-01**: Lease. renewal ([05 Home/Lease](../05%20Home/Lease.md))"
        self.assertEqual(self.entry(line), ("2026-09-01", "renewal", [self.LEASE]))
        self.assertEqual(self.entry("- **5 April**: Tax. Tax year ends (%s)" % link(self.TAX_PAGE)),
                         ("5 April", "Tax year ends", [self.TAX_PAGE]))

    def test_the_dashless_form_without_a_note(self):
        line = "- **2026-09-02**: Lease ([05 Home/Lease](../05%20Home/Lease.md))"
        self.assertEqual(self.entry(line), ("2026-09-02", "", [self.LEASE]))
        self.assertEqual(self.entry("- **5 April**: Tax (%s)" % link(self.TAX_PAGE)), ("5 April", "", [self.TAX_PAGE]))

    def test_a_merged_line_names_each_page_once_in_the_order_of_its_links(self):
        both = "%s, %s" % (link(self.HOME), link(self.BANK))
        pair = [self.HOME, self.BANK]
        self.assertEqual(self.entry("- **28 February**: 30 Home, Bank statement (1). Call (2 calls) (%s)" % both),
                         ("28 February", "Call (2 calls)", pair))
        self.assertEqual(self.entry("- **28 February**: 30 Home, Bank statement (1) (%s)" % both),
                         ("28 February", "", pair))
        same = "%s, %s" % (link("10 Identity/Notes.md"), link("20 Finance/Notes.md"))  # one title for two pages
        self.assertEqual(self.entry("- **5 April**: Notes. Review (%s)" % same),
                         ("5 April", "Review", ["10 Identity/Notes.md", "20 Finance/Notes.md"]))
        self.assertEqual(self.entry("- **5 April**: Notes (%s)" % same),
                         ("5 April", "", ["10 Identity/Notes.md", "20 Finance/Notes.md"]))
        self.assertEqual(self.entry("- **28 February**: Bank statement (1), 30 Home. Call (%s)" % both),
                         ("28 February", "Bank statement (1), 30 Home. Call", pair),
                         "the titles follow the links, so titles in another order are a note no page gives")

    def test_a_page_title_holding_brackets_is_read_by_its_own_text(self):
        for page in ("20 Finance/Tax [Q1](final).md", "20 Finance/x](y.md"):
            title = page[:-3].split("/")[1]
            with self.subTest(page=page):
                self.assertEqual(self.entry("- **5 April**: %s. Note (%s)" % (title, link(page))),
                                 ("5 April", "Note", [page]))
                self.assertEqual(self.entry("- **5 April**: %s (%s)" % (title, link(page))), ("5 April", "", [page]))

    def test_a_note_may_hold_what_the_layout_does(self):
        for note in ("Renew. Then pay", "Tax", "x: y", "pay (twice)", "Renew ([x](y)) soon", "([a](b)",
                     "ends 2030-01-01", ". x", "a %s b" % EM):
            with self.subTest(note=note):
                self.assertEqual(self.entry("- **5 April**: Tax. %s (%s)" % (note, link(self.TAX_PAGE))),
                                 ("5 April", note, [self.TAX_PAGE]))

    def test_the_em_dash_form_is_still_read(self):
        line = "- **2026-09-01** %s Lease %s renewal ([05 Home/Lease](../05%%20Home/Lease.md))" % (EM, EM)
        self.assertEqual(self.entry(line), ("2026-09-01", "renewal", [self.LEASE]))
        self.assertEqual(self.entry("- **2026-09-02** %s Lease (%s)" % (EM, link(self.LEASE))),
                         ("2026-09-02", "", [self.LEASE]))
        both = "%s, %s" % (link(self.HOME), link(self.BANK))
        self.assertEqual(self.entry("- **28 February** %s 30 Home, Bank statement (1) %s Call (2 calls) (%s)"
                                    % (EM, EM, both)), ("28 February", "Call (2 calls)", [self.HOME, self.BANK]))
        page = "20 Finance/Tax [Q1](final).md"
        self.assertEqual(self.entry("- **5 April** %s Tax [Q1](final) %s Note (%s)" % (EM, EM, link(page))),
                         ("5 April", "Note", [page]))

    def test_the_note_only_colon_form_is_still_read(self):
        self.assertEqual(self.entry("- **2025-04-30**: Lease ends ([30 Home](../30%20Home/30%20Home.md))"),
                         ("2025-04-30", "Lease ends", [self.HOME]))
        both = "%s, %s" % (link(self.HOME), link(self.BANK))
        self.assertEqual(self.entry("- **28 February**: Call (2 calls) (%s)" % both),
                         ("28 February", "Call (2 calls)", [self.HOME, self.BANK]))

    def test_a_colon_line_is_titled_when_its_middle_is_the_titles_or_starts_with_them_and_a_full_stop(self):
        """The two colon forms cannot always be told apart: `Lease. renewal` is a note in one and a title and a note in
        the other. The titled reading wins, since it is what the reference roll-up writes, so a note-only line whose
        note is a title, or starts with a title and `. `, is read as the titled form: the one such note it would
        misread. A note that only starts with the title, or a title and no space, stays a note."""
        page = "(%s)" % link(self.LEASE)
        self.assertEqual(self.entry("- **5 April**: Lease %s" % page), ("5 April", "", [self.LEASE]))
        self.assertEqual(self.entry("- **5 April**: Lease. renewal %s" % page), ("5 April", "renewal", [self.LEASE]))
        self.assertEqual(self.entry("- **5 April**: Lease renewal %s" % page),
                         ("5 April", "Lease renewal", [self.LEASE]))
        self.assertEqual(self.entry("- **5 April**: Lease.renewal %s" % page),
                         ("5 April", "Lease.renewal", [self.LEASE]))
        self.assertEqual(self.entry("- **5 April**: Lease.  %s" % page), ("5 April", "Lease. ", [self.LEASE]),
                         "a full stop and no note is not the titled form, which writes no full stop without a note")

    def test_a_line_that_is_not_laid_out_so_is_no_entry(self):
        good = "- **5 April**: Tax. Note (%s)" % link(self.TAX_PAGE)
        self.assertIsNotNone(self.entry(good))
        for line in (good[:-1], good + " x", good.replace("**:", "** :"), good.replace("**: ", "**:"),
                     good.replace("**: ", "**; "), good.replace("Note (", "Note("), good.replace("../", ""),
                     good.replace("Tax]", "Tax2]"), good.replace("Tax.md", "Tax.md#x"),
                     good.replace("- **", "* **"), "- **5 April**: Tax.", "- **5 April**:", ""):
            with self.subTest(line=line):
                self.assertIsNone(self.entry(line))

    def test_the_one_line_banner_is_read_with_a_dash_or_a_colon(self):
        self.assertEqual(readiness.banner(ONE_LINE_BANNER % (3, ":")), 1)
        self.assertEqual(readiness.banner(ONE_LINE_BANNER % (3, " " + EM)), 1)
        self.assertEqual(readiness.banner("> The roll-up found no frontmatter deadlines across 11 pages."), 0)
        for line in (ONE_LINE_BANNER % (3, ";"), ONE_LINE_BANNER % (3, " -"), ONE_LINE_BANNER % (3, ": "),
                     ONE_LINE_BANNER % (3, ":") + " Also 5 April.", (ONE_LINE_BANNER % (3, ":")).replace("3", "x", 1),
                     (ONE_LINE_BANNER % (3, ":")).replace("3 readable", " readable"),
                     (ONE_LINE_BANNER % (3, ":")).replace("likely", "unlikely")):
            with self.subTest(line=line):
                self.assertIsNone(readiness.banner(line))

    def test_the_intro_the_reference_roll_up_writes_now_is_the_one_this_suite_always_read(self):
        intro = ("_File-derived deadlines, rolled up deterministically from page frontmatter: do not hand-edit, "
                 "regenerated each run. (Calendar events live in `Coming Events`.)_")
        self.assertEqual(readiness.INTRO_FIXTURE, intro)
        self.assertIn(intro, readiness.ROLL_UP_LINES)
        self.assertEqual(readiness.INTRO, intro.replace(": do", " %s do" % EM), "the em-dash intro is still read")
        self.assertIn(readiness.INTRO, readiness.ROLL_UP_LINES)


class RoutesNewFilesOutTest(unittest.TestCase):
    """The rulebook check reads prose by keyword: a statement routes new files to the migrations folder when a clause
    names `_Migrations/` with "new file", "dropped", "goes to" or "go to", unless it negates that or only describes
    staging through an approved plan row."""

    NOT_ROUTING = (
        "New files never go to `_Migrations/`.",
        "New files never go to `_Migrations/`; one that seems to belong to another project is filed here like any other.",
        "No new file is dropped into `_Migrations/`.",
        "Do not send new files to `_Migrations/`.",
        "New files are not routed to `_Migrations/`.",
        "New files don't go to `_Migrations/`.",
        "New files don\u2019t go to `_Migrations/`.",
        "New files should never be dropped into `_Migrations/`, which only an approved plan row fills.",
        "`_Migrations/` never receives new files.",
        "Nothing is dropped into `_Migrations/` by the system.",
        "New files go to the inbox, not `_Migrations/`.",
        "New files are filed within the folder instead of going to `_Migrations/`.",
        "Files go to `_Migrations/<Project>/` only through an approved plan row (`plan.py migrate`).",
        "Files the owner approved for another project are dropped into `_Migrations/<Project>/` by an approved row.",
        "Approved files go to `_Migrations/<Project>/` when the owner approves the row in the plan.",
        "- New files never\n  go to `_Migrations/`.",
        "`_Migrations/<Project>/`: files the owner approved moving to another project.",
        "Files the owner approved wait in `_Migrations/<Project>/` until their project collects them.",
        "New files are filed by the wiki's routing. `_Migrations/` is only for staging.",
    )
    ROUTING = (
        "New files that belong to another project go to `_Migrations/<Project>/`.",
        "Files that may belong to another project are dropped into `_Migrations/`.",
        "A new file for another project goes to `_Migrations/<Project>/`.",
        "NEW FILES GO TO `_MIGRATIONS/`.".replace("_MIGRATIONS", "_Migrations"),
        "New files go to `_Migrations/`, not to the inbox.",
        "Never put new files in the inbox; they go to `_Migrations/<Project>/`.",
        "New files go to `_Migrations/`. Nothing else is filed there.",
        "New files go to `_Migrations/`; an approved row in the plan then moves them on.",
        "- New files that belong to another\n  project go to `_Migrations/<Project>/`.",
        "- A file that seems to belong to another project is not filed here:\n  it is dropped into `_Migrations/`.",
        "Do not file new files in the inbox, but let them go to `_Migrations/` by hand.",
    )

    def routing(self, text, folder="_Migrations"):
        return readiness.routes_new_files_out(text, folder)

    def test_a_negation_or_a_description_of_staging_does_not_route_new_files(self):
        for sentence in self.NOT_ROUTING:
            with self.subTest(sentence=sentence):
                self.assertEqual(self.routing(sentence), [])

    def test_a_statement_that_routes_new_files_there_does(self):
        for sentence in self.ROUTING:
            with self.subTest(sentence=sentence):
                self.assertEqual(len(self.routing(sentence)), 1)

    def test_a_negation_after_the_routing_does_not_negate_it(self):
        self.assertEqual(len(self.routing("New files go to `_Migrations/`, not to the inbox.")), 1)
        self.assertEqual(self.routing("New files go to the inbox, not `_Migrations/`."), [])

    def test_a_statement_not_naming_the_folder_is_not_read(self):
        self.assertEqual(self.routing("New files go to the migrations folder."), [])
        self.assertEqual(self.routing("New files go to `_Inbox/`."), [])

    def test_the_folder_is_the_one_given(self):
        text = "New files go to `_Leaving/`. Approved files wait in `_Migrations/`."
        self.assertEqual(self.routing(text, "_Leaving"), [text])
        self.assertEqual(self.routing(text), [])

    def test_a_wrapped_line_is_read_with_the_one_it_continues(self):
        text = ("- New files never\n  go to `_Migrations/`.\n- New files that belong to another\n  project go to "
                "`_Migrations/<Project>/`.\n\nA heading follows\n\n## Rules\ngo to `_Migrations/`\n")
        self.assertEqual(self.routing(text), ["New files that belong to another project go to `_Migrations/<Project>/`.",
                                              "go to `_Migrations/`"])

    def test_a_table_row_and_a_heading_stand_alone(self):
        text = "## New files\n| a | go to `_Migrations/` |\n| b | filed here |\n"
        self.assertEqual(self.routing(text), ["| a | go to `_Migrations/` |"])


class MigrationsClearedTest(unittest.TestCase):
    """`migrations_cleared`: the migrations folder holds no file. It lists names and never opens a file; `.DS_Store`
    and empty folders do not count, and anything else does, an iCloud placeholder included."""

    TAIL = "; a folder is onboarded only once its migrations folder is empty, so the owner clears it by hand"

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="readiness_migrations_"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def put(self, *rel, name="_Migrations"):
        write(os.path.join(self.root, name, *rel), "a staged file")

    def folder(self, *rel, name="_Migrations"):
        os.makedirs(os.path.join(self.root, name, *rel), exist_ok=True)

    def check(self, name="_Migrations"):
        return readiness.migrations_cleared(self.root, name)

    def finding(self, count, parts, name="_Migrations"):
        return "finding: %s/ holds %d file(s) (%s)%s" % (name, count, parts, self.TAIL)

    def test_no_migrations_folder_is_cleared(self):
        self.assertEqual(self.check(), "ok")

    def test_an_empty_folder_is_cleared(self):
        self.folder()
        self.assertEqual(self.check(), "ok")

    def test_ds_store_does_not_count(self):
        self.put(".DS_Store")
        self.put("Other Project", ".DS_Store")
        self.put("Other Project", "02 Finance", ".DS_Store")
        self.assertEqual(self.check(), "ok")

    def test_empty_subfolders_do_not_count(self):
        self.folder("Other Project", "02 Finance")
        self.folder("Household")
        self.assertEqual(self.check(), "ok")

    def test_one_file_is_a_finding_naming_its_project(self):
        self.put("Other Project", "02 Finance", "Old invoice.pdf")
        self.assertEqual(self.check(), self.finding(1, "Other Project: 1"))

    def test_the_count_is_per_first_level_subfolder_at_any_depth(self):
        self.put("Other Project", "Old invoice.pdf")
        self.put("Other Project", "02 Finance", "Gas.pdf")
        self.put("Other Project", "02 Finance", ".DS_Store")
        self.put("Household", "Water.pdf")
        self.put("Loose.pdf")
        self.put(".DS_Store")
        self.folder("Empty Project", "Nothing")
        self.assertEqual(self.check(), self.finding(4, "Household: 1; Other Project: 2; directly in the folder: 1"))

    def test_an_icloud_placeholder_counts(self):
        self.put("Other Project", ".Old invoice.pdf.icloud")
        self.assertEqual(self.check(), self.finding(1, "Other Project: 1"))
        self.put(".Loose.pdf.icloud")
        self.assertEqual(self.check(), self.finding(2, "Other Project: 1; directly in the folder: 1"))

    def test_only_ds_store_is_excused(self):
        for name in (".gitkeep", ".hidden", "._Old invoice.pdf", ".DS_Store.bak", ".ds_store", "Thumbs.db"):
            with self.subTest(name=name):
                shutil.rmtree(os.path.join(self.root, "_Migrations"), True)
                self.put("Other Project", name)
                self.assertEqual(self.check(), self.finding(1, "Other Project: 1"))

    def test_the_folder_is_the_one_the_settings_name(self):
        self.put("Other Project", "Old invoice.pdf")  # the default name, not this folder's migrations folder
        self.folder(name="_Leaving")
        self.assertEqual(self.check("_Leaving"), "ok")
        self.put("Household", "Water.pdf", name="_Leaving")
        self.assertEqual(self.check("_Leaving"), self.finding(1, "Household: 1", name="_Leaving"))
        self.assertEqual(self.check(), self.finding(1, "Other Project: 1"))

    def test_the_fixture_folder_stages_a_file_so_it_fails(self):
        self.assertEqual(readiness.migrations_cleared(FIXTURE, "_Migrations"), self.finding(1, "Other Project: 1"))

    def test_a_long_list_of_projects_is_cut(self):
        for n in range(8):
            self.put("Project %d" % n, "File.pdf")
        found = self.check()
        self.assertIn("holds 8 file(s) (Project 0: 1; Project 1: 1; Project 2: 1; Project 3: 1; Project 4: 1 and 3 "
                      "more)", found)

    def test_a_link_counts_and_is_never_followed(self):
        target = os.path.join(self.root, "elsewhere")
        write(os.path.join(target, "A.pdf"), "a")
        write(os.path.join(target, "B.pdf"), "b")
        self.folder("Other Project")
        try:
            os.symlink(target, os.path.join(self.root, "_Migrations", "Other Project", "link"))
        except (OSError, NotImplementedError) as e:
            self.skipTest("no symbolic links here: %s" % e)
        self.assertEqual(self.check(), self.finding(1, "Other Project: 1"))

    def test_a_file_or_a_link_in_place_of_the_folder_is_a_finding(self):
        write(os.path.join(self.root, "_Migrations"), "not a folder")
        self.assertEqual(self.check(), "finding: _Migrations is not a plain folder (a file or a link)" + self.TAIL)

    def test_a_folder_it_cannot_list_is_not_verified_and_never_a_pass(self):
        if not hasattr(os, "geteuid") or os.geteuid() == 0:
            self.skipTest("a folder cannot be made unreadable here")
        self.folder("Other Project", "02 Finance")
        locked = os.path.join(self.root, "_Migrations", "Other Project")
        os.chmod(locked, 0)
        self.addCleanup(os.chmod, locked, 0o700)
        found = self.check()
        self.assertEqual(found, "not verified: could not list _Migrations/Other Project (PermissionError)")
        self.put("Household", "Water.pdf")  # a file is still a finding, and the count is a floor
        self.assertEqual(self.check(), "finding: _Migrations/ holds 1 file(s) (Household: 1) and 1 folder(s) could "
                                       "not be listed, so the count may be low" + self.TAIL)

    def test_it_never_opens_a_file(self):
        self.put("Other Project", "Old invoice.pdf")
        self.put("Loose.pdf")
        with unittest.mock.patch("builtins.open", side_effect=AssertionError("opened a file")), \
                unittest.mock.patch("io.open", side_effect=AssertionError("opened a file")):
            self.assertEqual(self.check(), self.finding(2, "Other Project: 1; directly in the folder: 1"))


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
        self.assertEqual(res["handoff_contract"]["migrations_folder_cleared"], "ok")

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
        self.assertEqual((res["manifest"]["live_entries"], res["manifest"]["departed_entries"]), (17, 1))

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
        self.edit_page(DEADLINES, "Passport P1234567 expires ([10 Identity](../10%20Identity/10%20Identity.md))\n",
                       "Passport P1234567 expires ([10 Identity](../10%20Identity/10%20Identity.md))\n"
                       "- **2026-01-31**: renew the parking permit\n")
        detail = self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written")
        self.assertIn("1 date(s) no current page's frontmatter carries (line 14: 2026-01-31)", detail)
        self.assertIn("hand-written content in a derived page, 1 line(s) (line 14: - **2026-01-31**: renew the",
                      detail)

    def test_a_page_deadline_missing_from_the_roll_up(self):
        self.edit_page(DEADLINES, "- **2031-07-15**: Passport P1234567 expires "
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
        banner = "> [!warning]\n> The roll-up found no frontmatter deadlines across 11 pages.\n"
        self.edit_page(DEADLINES, "None\n", "%s\n\n%s\n## Upcoming\n\n_None._\n" % (FIXTURE_INTRO, banner))
        self.readiness(code=0)

    def test_a_recurring_date_kept_by_hand(self):
        p = self.page(DEADLINES)
        write(p, read(p) + "\n## Every year\n\n"
                           "- **31 January**: Self assessment return due ([Tax](../20%20Finance/Tax.md))\n")
        self.accept_again(DEADLINES)
        self.assertIn("1 yearly date(s) no page's recurring: list carries (line 17: 01-31)",
                      self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))

    def add_recurring(self, entry):
        self.edit_page(TAX, "status: current\n", "status: current\nrecurring:\n  - %s\n" % entry)

    def test_a_recurring_date_from_page_frontmatter(self):
        self.add_recurring("{date: 01-31, note: Self assessment return due}")
        p = self.page(DEADLINES)
        write(p, read(p) + "\n## Every year\n\n"
                           "- **31 January**: Self assessment return due ([Tax](../20%20Finance/Tax.md))\n")
        self.accept_again(DEADLINES)
        self.readiness(code=0)

    def test_a_recurring_date_missing_from_the_roll_up(self):
        self.add_recurring("{date: 01-31, note: Self assessment return due}")
        self.assertIn("lacks 1 recurring date(s) (01-31 (20 Finance/Tax.md))",
                      self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))

    def test_a_recurring_entry_not_month_and_day(self):
        self.add_recurring("{date: 2025-01-31, note: Self assessment return due}")
        self.assertIn("1 recurring: entr(ies) not {date, note} with a date as MM-DD (month first)",
                      self.refused_finding())

    def test_a_recurring_date_in_words_shown_in_words(self):
        self.add_recurring("{date: 31 January, note: Self assessment return due}")
        p = self.page(DEADLINES)
        write(p, read(p) + "\n## Every year\n\n"
                           "- **31 January**: Self assessment return due ([Tax](../20%20Finance/Tax.md))\n")
        self.accept_again(DEADLINES)
        self.readiness(code=0)

    def test_a_recurring_date_written_sept_matches_the_roll_up(self):
        self.add_recurring("{date: 5 Sept, note: School fees due}")
        p = self.page(DEADLINES)
        write(p, read(p) + "\n## Every year\n\n- **5 September**: School fees due ([Tax](../20%20Finance/Tax.md))\n")
        self.accept_again(DEADLINES)
        self.readiness(code=0)

    def test_a_recurring_date_with_a_full_stop_is_refused(self):
        self.add_recurring("{date: 5 Sept., note: School fees due}")
        self.assertIn("1 recurring: entr(ies) not {date, note} with a date as MM-DD", self.refused_finding())

    def test_an_ambiguous_numeric_yearly_date_is_refused(self):
        self.add_recurring("{date: 31/1, note: Self assessment return due}")
        self.assertIn("not {date, note} with a date as MM-DD", self.refused_finding())

    def test_gemini_md_reserved(self):
        self.edit_rulebook("`GEMINI.md`, ", "")
        self.assertEqual(self.one_finding("handoff_contract.rulebook_reserves_rulebook_filenames"),
                         "finding: the rulebook does not reserve GEMINI.md")

    def test_new_files_routed_within_the_folder(self):
        self.edit_rulebook("\n## Formats and packs", "- New files that belong to another project go to "
                           "`_Migrations/<Project>/`.\n\n## Formats and packs")
        self.assertIn("routes new files to _Migrations/ (1 line(s))",
                      self.one_finding("handoff_contract.new_files_routed_within_folder"))

    def test_a_rulebook_that_says_where_new_files_never_go_passes(self):
        self.edit_rulebook("\n## Formats and packs",
                           "- New files never go to `_Migrations/`; one that seems to belong to another project is\n"
                           "  filed here like any other.\n"
                           "- Files the owner approved for another project wait in `_Migrations/<Project>/`, put\n"
                           "  there only by an approved row in a plan.\n\n## Formats and packs")
        res = self.readiness(code=0)
        self.assertEqual(res["handoff_contract"]["new_files_routed_within_folder"], "ok")

    def test_a_rulebook_that_routes_new_files_to_the_migrations_folder_fails_wherever_it_wraps(self):
        self.edit_rulebook("\n## Formats and packs",
                           "- A new file that belongs to another project\n  goes to `_Migrations/<Project>/`.\n\n"
                           "## Formats and packs")
        self.assertIn("routes new files to _Migrations/ (1 line(s))",
                      self.one_finding("handoff_contract.new_files_routed_within_folder"))

    MIGRATIONS = ("_Migrations", "Other Project", "02 Finance", "Old invoice.pdf")
    UNCLEARED = ("finding: _Migrations/ holds 1 file(s) (Other Project: 1); a folder is onboarded only once its "
                 "migrations folder is empty, so the owner clears it by hand")

    def test_a_file_in_the_migrations_folder(self):
        write(self.path(*self.MIGRATIONS), "staged for another project")
        self.assertEqual(self.one_finding("handoff_contract.migrations_folder_cleared"), self.UNCLEARED)

    def stage_and_audit(self):
        """The staged file written, the folder audited again: the manifest now holds it, flagged `migrating`."""
        write(self.path(*self.MIGRATIONS), "Invoice for the other project.")
        self.tool("audit.py")
        entry, = [e for e in self.json_file("_Audit", "manifest.json")["entries"].values()
                  if e["current_path"].startswith("_Migrations/")]
        self.assertEqual(entry["flags"], ["migrating"])
        return entry["id"]

    def test_a_staged_document_needs_no_extract_record_or_card(self):
        """Held for another project, it is read by no tool: only the clearance of the migrations folder blocks."""
        self.stage_and_audit()
        res = self.readiness()
        self.assertEqual(res["manifest"]["migrating"], 1)
        self.assertEqual((res["records"]["missing_extracts"], res["records"]["missing_cards"]), (0, 0))
        self.assertEqual([f[0] for f in res["findings"]], ["handoff_contract.migrations_folder_cleared"])

    def exclude(self, *paths):
        twin = self.path(".familyai", "rulebook.json")
        write(twin, json.dumps(dict(self.json_file(".familyai", "rulebook.json"), exclude=list(paths)),
                               ensure_ascii=False, indent=1))

    def test_an_excluded_document_needs_no_extract_record_or_card(self):
        """Excluded by the owner, it is read by no tool: no record or card is expected, and none was made."""
        eid = self.ids()["06 Work/Contract.docx"]
        for sub in ("extract", "cards"):
            os.remove(self.path("_Audit", sub, eid + ".json"))
        self.exclude("06 Work")
        self.tool("audit.py")
        entry, = [e for e in self.json_file("_Audit", "manifest.json")["entries"].values()
                  if e["current_path"] == "06 Work/Contract.docx" and "departed" not in e["flags"]]
        self.assertEqual((entry["hashed"], entry["synthetic_id"]), (False, True))
        res = self.readiness()
        self.assertEqual((res["records"]["missing_extracts"], res["records"]["missing_cards"]), (0, 0))
        self.assertNotIn("records.missing_extracts", [f[0] for f in res["findings"]])

    def test_an_excluded_document_a_manifest_still_hashes_needs_no_record_either(self):
        """A manifest an earlier audit made, which read the file: the path decides, not whether it was hashed."""
        eid = self.ids()["06 Work/Contract.docx"]
        for sub in ("extract", "cards"):
            os.remove(self.path("_Audit", sub, eid + ".json"))
        self.exclude("06 Work/Contract.docx")
        self.assertEqual(self.readiness()["records"]["missing_extracts"], 0)

    def test_a_record_kept_at_the_path_a_staged_document_had_is_not_stale(self):
        eid = self.stage_and_audit()
        write(self.path("_Audit", "extract", eid + ".json"),
              json.dumps({"id": eid, "path": "02 Finance/Old invoice.pdf", "class": "document", "status": "ok",
                          "page_count": 1, "tiers": {"text_layer": 1}, "chars": 5, "extractor": "x",
                          "pages": [{"n": 1, "tier": "text_layer", "text": "Hello"}]}))
        res = self.readiness()
        self.assertEqual(res["records"]["extract_paths_stale"], 0)
        self.assertEqual([f[0] for f in res["findings"]], ["handoff_contract.migrations_folder_cleared"])

    def test_an_evicted_placeholder_in_the_migrations_folder_is_a_finding(self):
        write(self.path("_Migrations", "Other Project", ".Old invoice.pdf.icloud"), "")
        self.assertEqual(self.one_finding("handoff_contract.migrations_folder_cleared"), self.UNCLEARED)

    def test_a_migrations_folder_holding_only_ds_store_and_empty_folders_is_cleared(self):
        write(self.path("_Migrations", ".DS_Store"), "")
        write(self.path("_Migrations", "Other Project", ".DS_Store"), "")
        os.makedirs(self.path("_Migrations", "Household", "06 Work"))
        res = self.readiness(code=0)
        self.assertEqual(res["handoff_contract"]["migrations_folder_cleared"], "ok")

    def test_the_migrations_folder_is_the_one_the_settings_name(self):
        twin = self.path(".familyai", "rulebook.json")
        write(twin, json.dumps(dict(self.json_file(".familyai", "rulebook.json"), migrations_dir="_Leaving"),
                               ensure_ascii=False, indent=1))
        write(self.path("_Migrations", "Stray.pdf"), "an ordinary folder now")
        self.readiness(code=0)
        write(self.path("_Leaving", "Other Project", "Old invoice.pdf"), "staged for another project")
        self.assertEqual(self.one_finding("handoff_contract.migrations_folder_cleared"),
                         self.UNCLEARED.replace("_Migrations/", "_Leaving/"))

    def test_the_committed_fixture_fails_it_and_nothing_else(self):
        """The fixture stages a file in its migrations folder for the other tools: readiness reports that one item."""
        root = os.path.join(self.tmp, "staged", "Alex Personal")
        shutil.copytree(FIXTURE, root)
        work = os.path.join(self.tmp, "staged", "work")
        for tool, args in (("audit.py", []), ("settings.py", ["compile"])):
            code, _out, err = run(tool, *args, "--root", root, "--work", work)
            self.assertEqual(code, 0, err)
        code, out, err = run("readiness.py", "--root", root, "--work", work)
        self.assertEqual(code, 1, out + err)
        res = json.loads(out)
        self.assertEqual(res["findings"], [["handoff_contract.migrations_folder_cleared", self.UNCLEARED]])
        self.assertEqual(res["manifest"]["migrating"], 1)

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
        self.edit_page(DEADLINES, "None\n", "%s\n\n## Upcoming\n\n_None._\n\n## Past\n\n"
                       "- **2024-01-31**: Self assessment paid ([Tax](../20%%20Finance/Tax.md))\n"
                       % FIXTURE_INTRO)
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
        for entry in ("20250131", "2025-1-5", "{date: 20250131, note: No such day}"):
            with self.subTest(entry=entry):
                self.add_frontmatter(TAX, "deadline: %s\n" % entry)
                self.assertIn("1 deadline entr(ies) not a real YYYY-MM-DD or {date, note} (20 Finance/Tax.md: "
                              "deadline: %s)" % entry,
                              self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))
                self.edit_page(TAX, "deadline: %s\n" % entry, "")

    def test_a_day_the_calendar_does_not_have_is_a_frontmatter_the_roll_up_cannot_read(self):
        """PyYAML cannot build `2025-02-30`, so the roll-up lists the page as malformed and reads none of it; the
        Deadlines page that lacks that line is an incomplete one."""
        for entry in ("2025-02-30", "{date: 2025-02-30, note: No such day}"):
            with self.subTest(entry=entry):
                self.add_frontmatter(TAX, "deadline: %s\n" % entry)
                self.assertIn("lacks 1 line(s) of the roll-up's \"Could not read\" list that the pages give "
                              "(20 Finance/Tax.md (malformed frontmatter))",
                              self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))
                self.edit_page(TAX, "deadline: %s\n" % entry, "")

    def test_a_deadline_written_as_a_flow_sequence_is_not_read(self):
        """The reader reads a defined subset of YAML; `[2025-01-31]` is outside it, so it is named, not judged."""
        self.add_frontmatter(TAX, "deadline: [2025-01-31]\n")
        res = self.readiness(code=0)
        self.assertIn(["handoff_contract.frontmatter_read", "not verified: 20 Finance/Tax.md uses YAML this check does "
                       "not read (a flow sequence)"], res["not_verified"])
        self.assertEqual(res["findings"], [])

    def test_a_page_with_yaml_outside_the_subset_is_not_verified_never_failed_or_passed(self):
        """The Tax page uses an anchor: named in `not_verified`, no finding, the exit code the findings alone give."""
        self.add_frontmatter(TAX, "recurring:\n  - &first {date: 5 April, note: Tax year ends}\n")
        res = self.readiness(code=0)
        self.assertIn(["handoff_contract.frontmatter_read", "not verified: 20 Finance/Tax.md uses YAML this check does "
                       "not read (an anchor)"], res["not_verified"])
        self.assertEqual(res["findings"], [])
        self.assertEqual(res["summary"], {"findings": 0, "not_verified": len(res["not_verified"])})
        self.assertNotIn("frontmatter_read", res["handoff_contract"])  # no key of its own: the report keeps its shape

    def test_numbers_joined_by_a_dash_are_hand_written_content(self):
        """Only what the roll-up renders is on the page, so a line of numbers is reported whatever it is."""
        self.add_to_roll_up("- 13-45 units of electricity\n- 01-31-2025 is not a month and day\n"
                            "- 01-3122 is a meter reading\n")
        detail = self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written")
        self.assertIn("hand-written content in a derived page, 3 line(s) (line 14: - 13-45 units of electricity; "
                      "line 15: - 01-31-2025 is not a month and day; line 16: - 01-3122 is a meter reading)", detail)

    def test_a_single_deadline_with_a_note(self):
        """wiki-maintenance's frontmatter table allows `deadline: {date, note}` as well as a bare date."""
        self.add_frontmatter(TAX, "deadline: {date: 2026-01-31, note: Self assessment payment}\n")
        self.assertIn("lacks 1 page deadline(s) (2026-01-31 (20 Finance/Tax.md))",
                      self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))
        self.add_to_roll_up("- **2026-01-31**: Self assessment payment ([Tax](../20%20Finance/Tax.md))\n")
        self.readiness(code=0)

    def test_a_past_deadline_need_not_be_shown_but_a_date_added_to_the_page_is_reported(self):
        """The roll-up lists forward dates: a deadline before its last-updated need not be shown."""
        self.add_frontmatter(TAX, "deadlines:\n  - {date: 2024-01-31, note: Self assessment paid}\n")
        self.readiness(code=0)
        self.add_to_roll_up("Checked again on 2024-07-01.\n")
        detail = self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written")
        self.assertIn("1 date(s) no current page's frontmatter carries (line 14: 2024-07-01)", detail)
        self.assertIn("hand-written content in a derived page, 1 line(s) (line 14: Checked again on 2024-07-01.)",
                      detail)

    def test_a_page_range_in_prose_is_hand_written_content(self):
        self.add_to_roll_up("\nSee pages 10-12 of the lease.\n\n- See pages 10-12 of the lease too.\n")
        self.assertIn("hand-written content in a derived page, 2 line(s) (line 15: See pages 10-12 of the lease.; "
                      "line 17: - See pages 10-12 of the lease too.)",
                      self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))

    def test_a_recurring_date_in_a_table_is_hand_written_content(self):
        self.add_to_roll_up("\n| Every year | What |\n| --- | --- |\n| **01-31** | self assessment return due |\n")
        self.assertIn("hand-written content in a derived page, 3 line(s) (line 15: | Every year | What |; "
                      "line 16: | --- | --- |; line 17: | **01-31** | self assessment return due...)",
                      self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))

    def test_a_recurring_entry_needs_a_real_day_and_a_note(self):
        self.add_frontmatter(TAX, "recurring:\n  - {date: 02-30, note: No such day}\n")
        self.assertIn("(20 Finance/Tax.md: {date: 02-30, note: No such day})", self.refused_finding())
        self.edit_page(TAX, "{date: 02-30, note: No such day}", "{date: 02-28}")
        self.assertIn("{date: 02-28}", self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))
        self.edit_page(TAX, "{date: 02-28}", "{date: 02-29, note: Leap day review}")
        self.add_to_roll_up("\n## Every year\n\n- **29 February**: Leap day review ([Tax](../20%20Finance/Tax.md))\n")
        self.readiness(code=0)

    def test_a_recurring_date_is_shown_only_by_its_own_month_and_day(self):
        self.add_frontmatter(TAX, "deadline: 2026-01-31\ndeadline_note: Self assessment return due\n"
                                  "recurring:\n  - {date: 01-31, note: Return due}\n")
        self.add_to_roll_up("- **2026-01-31**: Self assessment return due ([Tax](../20%20Finance/Tax.md))\n")
        self.assertIn("lacks 1 recurring date(s) (01-31 (20 Finance/Tax.md))",
                      self.one_finding("handoff_contract.recurring_dates_in_frontmatter"))

    def test_a_superseded_page_has_no_deadline_on_the_roll_up(self):
        home = "30 Home/30 Home.md"
        self.edit_page(home, "status: current", "status: superseded")
        self.assertIn("no current page's frontmatter carries (line 12: 2025-04-30)",
                      self.one_finding("handoff_contract.derived_pages_hold_nothing_hand_written"))
        self.edit_page(DEADLINES, "- **2025-04-30**: Lease ends ([30 Home](../30%20Home/30%20Home.md))\n", "")
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


class DashlessRollUpTest(Prepared):
    """The Deadlines page as the reference roll-up now writes it, `- **<when>**: <titles>. <note> (<links>)` or, with no
    note, `- **<when>**: <titles> (<links>)`, passes the whitelist and the em-dash check. The form it wrote before,
    with spaced em dashes, still passes the whitelist: a deployment that has not re-rendered still writes it."""

    HOME_LINK = "[30 Home/30 Home](../30%20Home/30%20Home.md)"
    IDENTITY_LINK = "[10 Identity/10 Identity](../10%20Identity/10%20Identity.md)"
    TAX_LINK = "[20 Finance/Tax](../20%20Finance/Tax.md)"
    NOTE_ONLY = ("- **2025-04-30**: Lease ends ([30 Home](../30%20Home/30%20Home.md))\n"
                 "- **2031-07-15**: Passport P1234567 expires ([10 Identity](../10%20Identity/10%20Identity.md))\n")
    DASHLESS = ("- **2025-04-30**: 30 Home. Lease ends (%s)\n"
                "- **2031-07-15**: 10 Identity. Passport P1234567 expires (%s)\n" % (HOME_LINK, IDENTITY_LINK))
    EM_DASH = ("- **2025-04-30** %s 30 Home %s Lease ends (%s)\n"
               "- **2031-07-15** %s 10 Identity %s Passport P1234567 expires (%s)\n"
               % (EM, EM, HOME_LINK, EM, EM, IDENTITY_LINK))
    INTRO = "_File-derived deadlines, rolled up deterministically from page frontmatter %s do not hand-edit, " \
            "regenerated each run. (Calendar events live in `Coming Events`.)_" % EM
    DERIVED_KEY = "derived_pages_hold_nothing_hand_written"
    DERIVED = "handoff_contract." + DERIVED_KEY

    def roll_up(self, old, new):
        self.edit_page(DEADLINES, old, new)

    def test_the_new_form_is_clean(self):
        self.roll_up(self.NOTE_ONLY, self.DASHLESS)
        res = self.readiness(code=0)
        self.assertEqual((res["handoff_contract"][self.DERIVED_KEY], res["wiki"]["em_dash_lines"]), ("ok", 0))

    def test_an_entry_with_no_note_and_a_yearly_entry_naming_two_pages(self):
        self.edit_page(TAX, "status: current\n", "status: current\nrecurring:\n  - {date: 04-05, note: Tax year ends}\n"
                                                 "deadlines:\n  - 2031-02-01\n")
        self.edit_page("30 Home/30 Home.md", "deadlines:\n", "recurring:\n  - {date: 04-05, note: Tax year ends}\n"
                                                             "deadlines:\n")
        yearly = ("\n## Every year\n\n- **5 April**: 30 Home, Tax. Tax year ends (%s, %s)\n"
                  % (self.HOME_LINK, self.TAX_LINK))
        p = self.page(DEADLINES)
        write(p, read(p).replace(self.NOTE_ONLY, self.DASHLESS.replace(
            "- **2031-07-15**", "- **2031-02-01**: Tax (%s)\n- **2031-07-15**" % self.TAX_LINK)) + yearly)
        self.accept_again(DEADLINES)
        res = self.readiness(code=0)
        self.assertEqual(res["handoff_contract"]["recurring_dates_in_frontmatter"], "ok")

    def test_the_note_only_form_is_still_clean(self):
        self.assertIn(self.NOTE_ONLY, read(self.page(DEADLINES)), "the fixture's own roll-up")
        self.readiness(code=0)

    def test_the_em_dash_form_is_still_read(self):
        self.edit(WIKI + "/" + DEADLINES, FIXTURE_INTRO, self.INTRO)
        self.edit(WIKI + "/" + DEADLINES, self.NOTE_ONLY, self.EM_DASH)
        self.accept_again(DEADLINES)
        res = self.readiness()
        self.assertEqual(res["handoff_contract"][self.DERIVED_KEY], "ok")
        self.assertEqual([f[0] for f in res["findings"]], ["wiki.problems"], "only the em dashes the wiki check counts")
        self.assertEqual(res["wiki"]["em_dash_lines"], 3)

    def reported(self, home_entry):
        """The Deadlines page with its first entry replaced by `home_entry`, the one line that is hand-written."""
        self.roll_up(self.NOTE_ONLY, home_entry + self.NOTE_ONLY.splitlines(True)[1])
        self.assertIn("hand-written content in a derived page, 1 line(s)", self.one_finding(self.DERIVED))

    def test_a_note_the_pages_do_not_give_is_reported_in_the_new_form(self):
        self.reported("- **2025-04-30**: 30 Home. Lease ended (%s)\n" % self.HOME_LINK)

    def test_titles_that_are_not_the_linked_pages_are_reported_in_the_new_form(self):
        self.reported("- **2025-04-30**: 10 Identity. Lease ends (%s)\n" % self.HOME_LINK)

    def test_a_note_before_the_titles_is_reported_in_the_new_form(self):
        self.reported("- **2025-04-30**: Lease ends. 30 Home (%s)\n" % self.HOME_LINK)

    def test_a_stray_full_stop_after_the_note_is_reported_in_the_new_form(self):
        self.reported("- **2025-04-30**: 30 Home. Lease ends. (%s)\n" % self.HOME_LINK)

    def test_the_one_line_banner_of_an_empty_roll_up_is_read_with_a_colon_or_a_dash(self):
        for page in ("10 Identity/10 Identity.md", "30 Home/30 Home.md"):
            p = self.page(page)
            write(p, re.sub(r"deadlines:\n(  - .*\n)+", "", read(p)))
            self.accept_again(page)
        p = self.page(DEADLINES)
        write(p, read(p).split("# Deadlines")[0] + "# Deadlines\n\nNone\n")
        self.accept_again(DEADLINES)
        colon, dash = ONE_LINE_BANNER % (11, ":"), ONE_LINE_BANNER % (11, " " + EM)
        self.edit_page(DEADLINES, "None\n", "%s\n\n%s\n\n## Upcoming\n\n_None._\n" % (FIXTURE_INTRO, colon))
        res = self.readiness(code=0)
        self.assertEqual((res["handoff_contract"][self.DERIVED_KEY], res["wiki"]["em_dash_lines"]), ("ok", 0))
        self.edit_page(DEADLINES, colon, dash)
        res = self.readiness()
        self.assertEqual(res["handoff_contract"][self.DERIVED_KEY], "ok")
        self.assertEqual([f[0] for f in res["findings"]], ["wiki.problems"], "only the em dash the wiki check counts")


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
                         {"malformed_cards": 3, "bad_category": GAP_CARD, "missing_extracts": 1})
        detail = dict(res["findings"])["records.malformed_cards"]
        self.assertTrue(detail.startswith("3 card(s) not in the card format"), detail)
        for doc in ("04 Study/Notes.rtf", "02 Finance/Bank statement 2024-03.pdf", "03 Home/Lease notes .txt"):
            self.assertIn(doc, detail)
        self.assertIn("04 Study/Cours de fran\u00e7ais.pdf: 'Hobbies'", dict(res["findings"])["records.bad_category"])
        self.assertIn("03 Home/Lease notes .txt", dict(res["findings"])["records.missing_extracts"])

    def test_a_card_malformed_in_an_unrelated_field_leaves_its_category_not_verified(self):
        """`sensitive` as a string fails the whole card, so its category was never looked at: a clean 0 was wrong."""
        p = self.card("04 Study/Notes.rtf")
        write(p, json.dumps(dict(json.loads(read(p)), sensitive="yes")))
        res = self.readiness(code=1)
        gap = "not verified for 1 document(s) whose card is malformed"
        self.assertEqual((res["records"]["malformed_cards"], res["records"]["bad_category"]), (1, gap))
        self.assertIn(["records.bad_category", gap], res["not_verified"])
        self.assertEqual([k for k, _v in res["findings"]], ["records.malformed_cards"])
        p = self.card("04 Study/Cours de fran\u00e7ais.pdf")  # a readable card whose category is wrong is still found
        write(p, json.dumps(dict(json.loads(read(p)), category="Hobbies"), indent=1))
        res = self.readiness(code=1)
        self.assertEqual(res["records"]["bad_category"], "1; " + gap)
        self.assertIn("records.bad_category", [k for k, _v in res["findings"]])

    def test_an_extract_record_whose_id_is_not_its_documents_is_malformed(self):
        """`extract.py repath` refuses such a record, so the readiness count must not read it clean."""
        for change, shown in ((lambda r: dict(r, id="0" * 64), "'%s'" % ("0" * 64)),
                              (lambda r: {k: v for k, v in r.items() if k != "id"}, "None"),
                              (lambda r: dict(r, id=5), "5")):
            with self.subTest(shown=shown):
                p = self.path("_Audit", "extract", self.ids()["06 Work/Contract.docx"] + ".json")
                original = read(p)
                write(p, json.dumps(change(json.loads(original))))
                res = self.readiness(code=1)
                self.assertEqual(res["records"]["malformed_extracts"], 1)
                detail = dict(res["findings"])["records.malformed_extracts"]
                self.assertIn("06 Work/Contract.docx: ", detail)
                self.assertIn("its id is %s" % shown, detail)
                write(p, original)

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
        self.assertEqual(res["records"]["bad_category"], GAP_CARD)  # the check after the bad records still ran
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

    def test_contamination_is_not_verified_for_a_document_with_no_card_and_a_malformed_extract(self):
        """No card is a finding of its own, and the terms check needed the card and the extract: a clean 0 was wrong."""
        terms = os.path.join(self.tmp, "terms.txt")
        write(terms, TERMS)
        os.remove(self.card("06 Work/Essay.docx"))
        write(self.path("_Audit", "extract", self.ids()["06 Work/Essay.docx"] + ".json"), "{")
        res = self.readiness("--terms", terms, code=1)
        self.assertEqual(res["records"]["contamination"],
                         "not verified for 1 document(s) whose card or extract record is malformed")
        self.assertEqual((res["records"]["missing_cards"], res["records"]["malformed_extracts"]), (1, 1))

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
        """Exit 1 means findings, so an unforeseen failure (here a terms file that is not UTF-8) is a tool error."""
        terms = os.path.join(self.tmp, "terms.txt")
        with open(terms, "wb") as f:
            f.write(b"\xff\xfe")
        got, _out, err = run("readiness.py", "--root", self.root, "--work", self.work, "--terms", terms)
        self.assertEqual(got, 2, err)
        self.assertIn("UnicodeDecodeError", err)

    def test_a_deadlines_page_that_is_not_utf8_is_a_finding_not_a_crash(self):
        """A hand-kept table saved by another editor, as UTF-16 or as Latin-1: through the real CLI every other check
        still runs and the report names the page."""
        page = self.page(DEADLINES)
        text = read(page)
        for encoding in ("utf-16", "latin-1"):
            with self.subTest(encoding=encoding):
                with open(page, "wb") as f:
                    f.write((text + "\n| Fees | caf\u00e9 |\n").encode(encoding))
                res = self.readiness(code=1)
                found = dict(res["findings"])
                self.assertIn("01 Deadlines/01 Deadlines.md cannot be read as UTF-8 text (UnicodeDecodeError)",
                              found["handoff_contract.derived_pages_hold_nothing_hand_written"])
                self.assertIn(DEADLINES, res["wiki"]["frontmatter_bad"])  # `wiki.py check` counted it too
                self.assertEqual(res["records"]["missing_cards"], 0)  # the other checks ran
                self.assertEqual(res["wiki"]["pages"], 12)
                self.assertIn(["handoff_contract.recurring_dates_in_frontmatter",
                               "not verified: 01 Deadlines/01 Deadlines.md cannot be read"], res["not_verified"])

    def test_a_wiki_page_that_is_not_utf8_is_a_malformed_page_not_a_crash(self):
        """The roll-up lists such a page as unreadable and `wiki.py check` counts it as one that does not conform:
        readiness reports it and goes on, with every other check run."""
        with open(self.page(TAX), "ab") as f:
            f.write(b"\xff\xfe")
        res = self.readiness(code=1)
        self.assertIn(TAX, res["wiki"]["frontmatter_bad"])
        self.assertEqual([k for k, _v in res["findings"]],
                         ["wiki.problems", "wiki_handoff.pages_not_accepted",
                          "handoff_contract.derived_pages_hold_nothing_hand_written"])
        self.assertIn("(20 Finance/Tax.md (unreadable: UnicodeDecodeError))", res["findings"][-1][1])


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
        self.assertEqual(res, {"records": 17, "applied": False, "paths_changed": 1, "already_current": 16,
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
