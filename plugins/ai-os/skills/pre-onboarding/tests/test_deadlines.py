"""`wiki.py deadlines` renders the derived Deadlines page, in exactly the form `readiness.py` reads.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests

The key property: for every wiki, the page the tool renders passes the readiness check of the Deadlines page, with no
finding beside the frontmatter's own. It is shown on the scenario wikis of `rollups/` (each rendered page also equals
the page the reference roll-up captured there, once the captured em dashes are written as the reference roll-up now
writes them, with colons) and on synthetic wikis, one for each shape the issue names: notes and none, a line merged
across pages, a yearly date in both spellings, an unreadable date, no dates at all. The rest pins the command: a dry
run prints and changes nothing, `--write` writes, and what it cannot render it refuses by name.
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
TIMEOUT = 600  # seconds: a tool that hangs fails its test instead of the run
ROLLUPS = os.path.join(HERE, "rollups")
FIXTURE = os.path.join(HERE, "fixture", "Alex Personal")
sys.path.insert(0, TOOLS)
import readiness  # noqa: E402

NOW = "1719748800"  # 2024-06-30T12:00:00Z, the day the roll-ups were rendered
TODAY = "2024-06-30"
EM = "\u2014"
PAGE = "01 Deadlines/01 Deadlines.md"
NOT_READ = {"coerced", "yaml-malformed"}  # pages the roll-up reads as YAML does, which the tool cannot: refused
FRONTMATTER_FINDING = re.compile(r"finding: [0-9]+ recurring: entr\(ies\) not \{date, note\} with a date as MM-DD "
                                 r"\(month first\) or a day and a month name, a day the month has \(.*\)")


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def run(*args, now=NOW):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "wiki.py"), "deadlines"] + list(args), capture_output=True,
                       text=True, encoding="utf-8", env=dict(os.environ, PRE_ONBOARDING_NOW=now), timeout=TIMEOUT)
    return r.returncode, r.stdout, r.stderr


def tree_digest(root):
    h = hashlib.sha256()
    for d, ds, fs in os.walk(root):
        ds.sort()
        for f in sorted(fs):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode() + b"\0" + read(p, "rb") + b"\n")
    return h.hexdigest()


def dashless(text):
    """A captured roll-up page as the reference roll-up now writes it: a colon where the older one wrote a spaced em
    dash, in the intro, the one-line banner and each entry (`- **<when>**: <titles>. <note> (<links>)`, or
    `- **<when>**: <titles> (<links>)` with no note)."""
    out = []
    for line in text.split("\n"):
        if line.startswith("_File-derived"):
            line = line.replace(" " + EM + " ", ": ")
        elif line.startswith("> **Roll-up found"):
            line = line.replace(" " + EM + " likely", ": likely")
        elif line.startswith("- **") and "** " + EM + " " in line:
            at = line.index("** " + EM + " ")
            when, rest = line[4:at], line[at + 5:]
            cut = rest.rindex(" ([")
            body, links = rest[:cut], rest[cut + 1:]
            if " " + EM + " " in body:
                titles, note = body.split(" " + EM + " ", 1)
                line = "- **%s**: %s. %s %s" % (when, titles, note, links)
            else:
                line = "- **%s**: %s %s" % (when, body, links)
        out.append(line)
    return "\n".join(out)


class Case(unittest.TestCase):
    """A folder `Case` with its wiki `Case Wiki`, the pages written into it, and `wiki.py deadlines` run on it."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="deadlines_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "Case")
        self.wiki = os.path.join(self.root, "Case Wiki")
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.wiki)

    def pages(self, files):
        """Write pages, {path relative to the wiki: frontmatter lines}; each has the keys the wiki's pages carry."""
        for rel, lines in files.items():
            write(os.path.join(self.wiki, *rel.split("/")),
                  "---\nprovenance: derived\nlast-updated: 2024-06-30\nstatus: current\n%s---\n# Page\n"
                  % "".join(line + "\n" for line in lines))

    def deadlines(self, *args, code=0, now=NOW):
        got, out, err = run("--root", self.root, "--work", self.work, *args, now=now)
        self.assertEqual(got, code, out + err)
        self.assertNotIn("Traceback", err)
        return out, err

    def render(self, code=0):
        """The page as `--write` writes it, which a dry run prints alike."""
        printed, _err = self.deadlines("--today", TODAY, code=code)
        self.deadlines("--today", TODAY, "--write", code=code)
        written = read(os.path.join(self.wiki, *PAGE.split("/")))
        self.assertEqual(printed, written, "a dry run prints the page --write writes")
        return written

    def readiness(self):
        """(derived, recurring, other derived pages) as readiness reports them for this wiki, at the frozen clock."""
        os.environ["PRE_ONBOARDING_NOW"] = NOW
        try:
            return readiness.deadline_items(self.wiki, readiness.W.wiki_pages(self.wiki), None)[:3]
        finally:
            del os.environ["PRE_ONBOARDING_NOW"]

    def accepted(self, recurring="ok", code=0):
        """Render (the tool exits `code`: 1 when it lists what it could not read), then assert readiness finds nothing
        on the rendered page: its own check is `ok`, and so is the recurring one unless it holds only the finding about
        a page's frontmatter, which no page can mend."""
        page = self.render(code=code if recurring == "ok" else 1)
        derived, yearly, other = self.readiness()
        self.assertEqual(derived, "ok")
        if recurring == "ok":
            self.assertEqual(yearly, "ok")
        else:
            self.assertRegex(yearly, "^" + FRONTMATTER_FINDING.pattern + "$")
        self.assertEqual(other, "ok")
        return page


class ScenarioTest(Case):
    """The wikis whose roll-ups the reference deployment rendered (`rollups/`)."""

    def scenario(self, name):
        shutil.rmtree(self.wiki)
        shutil.copytree(os.path.join(ROLLUPS, name), self.wiki)
        captured = os.path.join(self.wiki, *PAGE.split("/"))
        want = dashless(read(captured))
        os.remove(captured)
        return want

    def test_each_scenario_renders_the_page_the_reference_roll_up_captured(self):
        names = sorted(n for n in os.listdir(ROLLUPS) if os.path.isdir(os.path.join(ROLLUPS, n))
                       and n != "__pycache__" and n not in NOT_READ)
        self.assertGreaterEqual(len(names), 12)
        for name in names:
            with self.subTest(name):
                self.setUp()
                want = self.scenario(name)
                got = self.render(code=1 if "## Could not read" in want or name in ("refused", "typed-dates")
                                  else 0)
                self.assertEqual(got, want)

    def test_every_rendered_scenario_passes_the_readiness_check(self):
        recurring_findings = {"could-not-read", "refused", "typed-dates"}  # their pages' own `recurring` is not mendable
        for name in sorted(n for n in os.listdir(ROLLUPS) if os.path.isdir(os.path.join(ROLLUPS, n))
                           and n != "__pycache__" and n not in NOT_READ):
            with self.subTest(name):
                self.setUp()
                self.scenario(name)
                bad = name in recurring_findings
                self.render(code=1 if bad or name in ("only-errors", "directory", "derived-section") else 0)
                derived, yearly, other = self.readiness()
                self.assertEqual((derived, other), ("ok", "ok"))
                if bad:
                    self.assertRegex(yearly, "^" + FRONTMATTER_FINDING.pattern + "$")
                else:
                    self.assertEqual(yearly, "ok")

    def test_the_pages_the_tool_cannot_read_as_yaml_are_refused_by_name_and_nothing_is_written(self):
        """`coerced` holds notes the roll-up writes as YAML reads them (`yes` as `True`, `12:30` as `750`) and
        `yaml-malformed` pages YAML refuses that a read of the text takes for fine: what the roll-up would write is
        not known to the tool, so it refuses rather than render a page that omits or misstates them."""
        for name, pages in (("coerced", ["20 Finance/Date.md", "20 Finance/Null.md", "20 Finance/Number.md",
                                         "20 Finance/Tilde.md", "20 Finance/Time.md", "20 Finance/Yes.md",
                                         "20 Finance/Comment.md"]),
                            ("yaml-malformed", ["30 Home/Bracket.md", "30 Home/Control.md", "30 Home/Equals.md",
                                                "30 Home/Tab.md"])):
            with self.subTest(name):
                self.setUp()
                want = self.scenario(name)
                before = tree_digest(self.wiki)
                for extra in ([], ["--write"]):
                    out, err = self.deadlines("--today", TODAY, *extra, code=2)
                    self.assertEqual(out, "")
                    self.assertIn("cannot render", err)
                    for page in pages:
                        self.assertIn(page + " uses YAML this check does not read", err)
                    self.assertIn("references/tools.md", err)
                self.assertEqual(tree_digest(self.wiki), before, "a page was written")
                self.assertTrue(want)


class ShapeTest(Case):
    """One synthetic wiki for each shape of roll-up the issue names."""

    def test_a_deadline_with_a_note_and_one_without(self):
        self.pages({"20 Finance/Tax.md": ["deadlines:", "  - {date: 2030-01-31, note: Renew}", "  - 2030-02-01",
                                          "deadline: 2030-03-01", "deadline_note: Pay the second instalment"]})
        page = self.accepted()
        tax = "([20 Finance/Tax](../20%20Finance/Tax.md))"
        self.assertIn("- **2030-01-31**: Tax. Renew %s\n" % tax, page)
        self.assertIn("- **2030-02-01**: Tax %s\n" % tax, page, "no note: no full stop either")
        self.assertIn("- **2030-03-01**: Tax. Pay the second instalment %s\n" % tax, page)
        self.assertEqual(page.count("- **"), 3)

    def test_a_line_merged_across_pages_names_every_page_once_ordered_by_title(self):
        both = ["recurring:", "  - {date: 04-05, note: Tax year ends}", "deadlines:",
                "  - {date: 2030-06-01, note: Return due}"]
        self.pages({"30 Home/Home.md": both, "20 Finance/Tax.md": both, "40 Study/Notes.md": ["deadlines:",
                    "  - {date: 2030-06-01, note: Return due}"], "20 Finance/Notes.md": ["deadlines:",
                    "  - {date: 2030-06-01, note: Return due}"], "50 Work/Other.md": ["deadlines:",
                    "  - {date: 2030-06-01, note: Something else}"]})
        page = self.accepted()
        self.assertIn("- **5 April**: Home, Tax. Tax year ends ([30 Home/Home](../30%20Home/Home.md), "
                      "[20 Finance/Tax](../20%20Finance/Tax.md))\n", page)
        self.assertIn("- **2030-06-01**: Home, Notes, Tax. Return due ([30 Home/Home](../30%20Home/Home.md), "
                      "[20 Finance/Notes](../20%20Finance/Notes.md), [40 Study/Notes](../40%20Study/Notes.md), "
                      "[20 Finance/Tax](../20%20Finance/Tax.md))\n", page,
                      "two pages of one title share it once; the pages are ordered by title, then path")
        self.assertLess(page.index("Return due"), page.index("Something else"), "ordered by date, then note")

    def test_a_yearly_date_in_both_spellings_is_one_line_in_calendar_order(self):
        self.pages({"20 Finance/Tax.md": ["recurring:", "  - {date: 04-05, note: Tax year ends}",
                                          "  - {date: 31 January, note: Return due}", "  - {date: Sept 5, note: Fees}"],
                    "30 Home/Home.md": ["recurring:", "  - {date: 5 April, note: Tax year ends}",
                                        "  - {date: 1st May, note: Rent review}",
                                        "  - {date: 12-31, note: Year end}"]})
        page = self.accepted()
        self.assertEqual(re.findall(r"- \*\*([^*]+)\*\*", page),
                         ["31 January", "5 April", "1 May", "5 September", "31 December"])
        self.assertEqual(page.count("Tax year ends"), 1)
        self.assertIn("- **5 April**: Home, Tax. Tax year ends (", page)
        self.assertIn("## Upcoming\n\n_None._\n\n## Every year\n", page)

    def test_past_dates_go_under_past_and_a_date_on_the_day_is_upcoming(self):
        self.pages({"20 Finance/Tax.md": ["deadlines:", "  - {date: 2024-06-29, note: Yesterday}",
                                          "  - {date: 2024-06-30, note: Today}", "  - {date: 2024-01-01, note: Long ago}",
                                          "  - {date: 2024-07-01, note: Tomorrow}"]})
        page = self.accepted()
        upcoming, past = page.split("## Upcoming\n\n")[1].split("## Past\n\n")
        self.assertEqual(re.findall(r"- \*\*([^*]+)\*\*", upcoming), ["2024-06-30", "2024-07-01"])
        self.assertEqual(re.findall(r"- \*\*([^*]+)\*\*", past), ["2024-01-01", "2024-06-29"])

    def test_an_unreadable_date_is_listed_under_could_not_read_and_the_tool_exits_1(self):
        self.pages({"20 Finance/Tax.md": ["recurring:", "  - {date: 04-05, note: Tax year ends}"],
                    "30 Home/Bad.md": ["recurring:", "  - {date: 31 April, note: Nonsense}", "  - {date: 6/4, note: x}"]})
        page = self.accepted(recurring="finding")
        self.assertTrue(page.endswith(
            "## Could not read\n\n_These pages, or entries on them, were skipped. Fix their frontmatter so any deadline "
            "is picked up:_\n\n- 30 Home/Bad.md (unreadable recurring date: {'date': '31 April', 'note': 'Nonsense'}; "
            "write the date as MM-DD, month first, or as a day and a month name)\n- 30 Home/Bad.md (unreadable "
            "recurring date: {'date': '6/4', 'note': 'x'}; write the date as MM-DD, month first, or as a day and a "
            "month name)\n"), page)
        _out, err = self.deadlines("--today", TODAY, code=1)
        self.assertIn("0 upcoming, 1 every year, 0 past, 2 could not read", err)
        self.assertIn("fix in the pages' frontmatter, 2 recurring entries not {date, note}", err)

    def test_a_page_that_is_malformed_or_unreadable_is_listed_and_the_rest_rendered(self):
        self.pages({"20 Finance/Tax.md": ["recurring:", "  - {date: 04-05, note: Tax year ends}"]})
        write(os.path.join(self.wiki, "10 Identity", "Broken.md"), "---\nprovenance: derived\ndeadline: [2030\n# Broken\n")
        with open(os.path.join(self.wiki, "30 Home.md"), "wb") as f:
            f.write(b"---\nstatus: current\n---\n\xff\xfe not text\n")
        os.makedirs(os.path.join(self.wiki, "Archive.md"))
        page = self.accepted(code=1)
        self.assertTrue(page.endswith(
            "\n- 10 Identity/Broken.md (malformed frontmatter)\n- 30 Home.md (unreadable: UnicodeDecodeError)\n"
            "- Archive.md (unreadable: IsADirectoryError)\n"), page)

    def test_no_dates_at_all_says_so_in_the_banner(self):
        self.pages({"10 Identity/Identity.md": [], "20 Finance/Tax.md": [], "30 Home/Home.md": ["foo: bar"]})
        page = self.accepted()
        banner = "> **Roll-up found no frontmatter deadlines across 3 readable pages: likely a keying fault"
        self.assertEqual(page.count(banner), 1)
        self.assertIn("deadline-free wiki.**", page)
        self.assertNotIn(EM, page)
        self.assertTrue(page.endswith("## Upcoming\n\n_None._\n"), page)
        self.assertNotIn("## Every year", page)
        self.assertNotIn("## Past", page)

    def test_a_wiki_with_no_readable_page_has_no_banner_to_say(self):
        os.makedirs(os.path.join(self.wiki, "20 Finance"))
        page = self.accepted()
        self.assertNotIn("Roll-up found", page)
        self.assertTrue(page.endswith("## Upcoming\n\n_None._\n"))

    def test_only_past_dates_say_none_to_come_and_keep_the_past(self):
        self.pages({"20 Finance/Tax.md": ["deadlines:", "  - {date: 2020-01-01, note: Old}"]})
        page = self.accepted()
        self.assertIn("## Upcoming\n\n_None._\n\n## Past\n\n- **2020-01-01**: Tax. Old (", page)
        self.assertNotIn("Roll-up found", page, "a date is shown, only an old one")

    def test_a_superseded_page_and_the_siblings_the_roll_up_skips_give_nothing(self):
        self.pages({"20 Finance/Tax.md": ["deadlines:", "  - {date: 2030-01-01, note: Kept}"],
                    "20 Finance/Old.md": ["deadlines:", "  - {date: 2030-02-02, note: Gone}"]})
        write(os.path.join(self.wiki, "20 Finance", "Old.md"),
              "---\nprovenance: derived\nlast-updated: 2024-06-30\nstatus: superseded\ndeadlines:\n"
              "  - {date: 2030-02-02, note: Gone}\n---\n# Old\n")
        for sibling in ("Tax.proposed.md", "Tax.superseded.md"):
            self.pages({"20 Finance/" + sibling: ["deadlines:", "  - {date: 2030-03-03, note: Skipped}"]})
        page = self.accepted()
        self.assertEqual(re.findall(r"- \*\*([^*]+)\*\*", page), ["2030-01-01"])

    def test_a_note_holding_what_the_layout_does_reads_back(self):
        notes = ["Renew. Then pay", "pay (twice)", "x: y", "ends 2030-01-01", "Ask Alex & Sam", "100% done, 50% due"]
        self.pages({"20 Finance/Tax.md": ["deadlines:"] + ["  - {date: 2030-01-%02d, note: \"%s\"}" % (n, note)
                                                           for n, note in enumerate(notes, 1)]})
        page = self.accepted()
        for note in notes:
            self.assertIn(". %s ([20 Finance/Tax]" % note, page)

    def test_page_names_with_brackets_an_ampersand_a_percent_and_other_scripts_link_as_the_roll_up_links(self):
        names = ["Tax [Q1](final)", "x](y", "Fees & 100% done", "中文课程", "Bank statement (1)"]
        self.pages({"20 Finance/%s.md" % name: ["deadlines:", "  - {date: 2030-01-01, note: Due}"] for name in names})
        page = self.accepted()
        self.assertIn("[20 Finance/Fees & 100% done](../20%20Finance/Fees%20&%20100%25%20done.md)", page)
        self.assertIn("[20 Finance/x](y](../20%20Finance/x%5D%28y.md)", page)
        self.assertIn("[20 Finance/Bank statement (1)](../20%20Finance/Bank%20statement%20%281%29.md)", page)
        self.assertIn("(../20%20Finance/%E4%B8%AD%E6%96%87%E8%AF%BE%E7%A8%8B.md)", page)


class FixtureTest(unittest.TestCase):
    """The prepared fixture: rendered from its pages' frontmatter, its Deadlines page passes the whole of readiness."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="deadlines_fixture_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "Alex Personal")
        shutil.copytree(FIXTURE, self.root)
        self.work = os.path.join(self.tmp, "work")

    def test_the_rendered_page_is_clean_to_the_whole_readiness_check(self):
        page = os.path.join(self.root, "Alex Personal Wiki", *PAGE.split("/"))
        out, err = run("--root", self.root, "--work", self.work, "--today", TODAY)[1:]
        self.assertEqual(out,
                         "---\nprovenance: derived\nlast-updated: 2024-06-30\nstatus: current\n---\n\n# Deadlines\n\n"
                         + readiness.INTRO_FIXTURE + "\n\n## Upcoming\n\n"
                         "- **2025-04-30**: 30 Home. Lease ends ([30 Home/30 Home](../30%20Home/30%20Home.md))\n"
                         "- **2031-07-15**: 10 Identity. Passport P1234567 expires "
                         "([10 Identity/10 Identity](../10%20Identity/10%20Identity.md))\n")
        self.assertIn("2 upcoming, 0 every year, 0 past, 0 could not read", err)
        self.assertEqual(run("--root", self.root, "--work", self.work, "--today", TODAY, "--write")[0], 0)
        self.assertEqual(read(page), out)
        for tool, args in (("audit.py", []), ("settings.py", ["compile"])):
            got = subprocess.run([sys.executable, os.path.join(TOOLS, tool)] + args + ["--root", self.root, "--work",
                                 self.work], capture_output=True, text=True, env=dict(os.environ,
                                 PRE_ONBOARDING_NOW=NOW), timeout=TIMEOUT)
            self.assertEqual(got.returncode, 0, got.stderr)
        env = dict(os.environ, PRE_ONBOARDING_NOW=NOW)
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "readiness.py"), "--root", self.root, "--work",
                            self.work], capture_output=True, text=True, env=env, timeout=TIMEOUT)
        self.assertEqual([f[0] for f in json.loads(r.stdout)["findings"]],
                         ["wiki_handoff.pages_not_accepted", "handoff_contract.migrations_folder_cleared"],
                         "the page is new text, so its acceptance of an earlier version no longer stands")
        for lens in ("owner", "professional"):  # accepted again, as the rule asks of a changed page
            reply = os.path.join(self.tmp, "reply.json")
            write(reply, json.dumps({"page": PAGE, "lens": lens, "verdict": "accepted", "findings": []}))
            got = subprocess.run([sys.executable, os.path.join(TOOLS, "wiki.py"), "accept", "--root", self.root,
                                  "--work", self.work, "--reply", reply, "--author-model", "model-a",
                                  "--reviewer-model", "model-b", "--date", "2024-07-01"], capture_output=True,
                                 text=True, env=env, timeout=TIMEOUT)
            self.assertEqual(got.returncode, 0, got.stderr)
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "readiness.py"), "--root", self.root, "--work",
                            self.work], capture_output=True, text=True, env=env, timeout=TIMEOUT)
        report = json.loads(r.stdout)
        self.assertEqual(report["handoff_contract"]["derived_pages_hold_nothing_hand_written"], "ok")
        self.assertEqual(report["handoff_contract"]["recurring_dates_in_frontmatter"], "ok")
        self.assertEqual([f[0] for f in report["findings"]], ["handoff_contract.migrations_folder_cleared"],
                         "the fixture's staged file is the one finding, as before")
        self.assertEqual(report["wiki"]["em_dash_lines"], 0)
        self.assertEqual(report["wiki"]["dead_page_links"], [])


class CommandTest(Case):
    """What the command does and refuses."""

    def setUp(self):
        super().setUp()
        self.pages({"20 Finance/Tax.md": ["deadlines:", "  - {date: 2030-01-31, note: Renew}", "recurring:",
                                          "  - {date: 04-05, note: Tax year ends}"]})
        self.page = os.path.join(self.wiki, *PAGE.split("/"))

    def test_a_dry_run_prints_the_page_and_changes_nothing(self):
        before = tree_digest(self.root)
        out, err = self.deadlines("--today", TODAY)
        self.assertTrue(out.startswith("---\nprovenance: derived\nlast-updated: 2024-06-30\nstatus: current\n---\n"))
        self.assertIn("would write (a dry run: --write writes it) Case Wiki/01 Deadlines/01 Deadlines.md", err)
        self.assertEqual(tree_digest(self.root), before)
        self.assertFalse(os.path.exists(self.page))

    def test_write_puts_the_page_in_the_wiki_and_prints_none(self):
        out, err = self.deadlines("--today", TODAY, "--write")
        self.assertEqual(out, "")
        self.assertIn("1 upcoming, 1 every year, 0 past, 0 could not read; wrote Case Wiki/01 Deadlines/", err)
        self.assertEqual(read(self.page), self.deadlines("--today", TODAY)[0])

    def test_rendering_again_gives_the_same_bytes_and_never_reads_its_own_page_as_a_source(self):
        self.deadlines("--today", TODAY, "--write")
        first = read(self.page)
        self.deadlines("--today", TODAY, "--write")
        self.assertEqual(read(self.page), first)
        self.assertEqual(self.deadlines("--today", TODAY)[0], first)

    def test_out_is_where_write_puts_the_page_instead_of_the_wiki(self):
        out = os.path.join(self.tmp, "elsewhere", "Deadlines.md")
        self.deadlines("--today", TODAY, "--write", "--out", out)
        self.assertTrue(read(out).startswith("---\nprovenance: derived"))
        self.assertFalse(os.path.exists(self.page), "the wiki's own page was written")

    def test_out_without_write_is_refused_so_nothing_reads_as_written(self):
        out = os.path.join(self.tmp, "Deadlines.md")
        _o, err = self.deadlines("--today", TODAY, "--out", out, code=2)
        self.assertIn("--out names where --write puts the page; without --write nothing is written", err)
        self.assertFalse(os.path.exists(out))

    def test_read_only_root_refuses_to_write_inside_the_folder(self):
        _o, err = self.deadlines("--today", TODAY, "--write", "--read-only-root", code=2)
        self.assertIn("--read-only-root", err)
        self.assertFalse(os.path.exists(self.page))
        out = os.path.join(self.tmp, "Deadlines.md")
        self.deadlines("--today", TODAY, "--write", "--read-only-root", "--out", out)
        self.assertTrue(os.path.exists(out))

    def test_today_sets_the_stamp_and_the_split_between_upcoming_and_past(self):
        for today, section in (("2030-01-31", "## Upcoming"), ("2030-02-01", "## Past")):
            with self.subTest(today):
                out, _err = self.deadlines("--today", today, now="1900000000")  # the clock is 2030-03-17
                self.assertIn("last-updated: %s\n" % today, out)
                self.assertIn("%s\n\n- **2030-01-31**" % section, out)

    def test_the_default_day_is_the_local_date_by_the_tools_clock(self):
        out, _err = self.deadlines()
        self.assertIn("last-updated: 2024-06-30\n", out)
        out, _err = self.deadlines(now="1780000000")  # 2026-05-28
        self.assertIn("last-updated: 2026-05-28\n", out)

    def test_a_day_after_today_is_refused_because_readiness_reports_it(self):
        _o, err = self.deadlines("--today", "2024-07-01", code=2)
        self.assertIn("--today 2024-07-01 is after today (2024-06-30)", err)

    def test_a_day_that_is_not_a_day_is_refused(self):
        for text in ("2024-02-30", "30 June 2024", "2024-6-30", ""):
            with self.subTest(text):
                _o, err = self.deadlines("--today", text, code=2)
                self.assertIn("is not a day written YYYY-MM-DD", err)

    def test_no_wiki_folder_is_refused(self):
        shutil.rmtree(self.wiki)
        _o, err = self.deadlines("--today", TODAY, code=2)
        self.assertIn("no wiki folder", err)

    def test_a_stale_twin_is_refused_like_every_tool_refuses_it(self):
        write(os.path.join(self.root, "CLAUDE.md"), "# Rules\n")
        write(os.path.join(self.root, ".familyai", "rulebook.json"),
              '{"version": 1, "rulebook_sha256": "%s"}' % ("0" * 64))
        _o, err = self.deadlines("--today", TODAY, code=2)
        self.assertIn("error: stale:", err)

    def test_a_page_with_yaml_the_tool_cannot_read_is_named_and_stops_the_run(self):
        self.pages({"30 Home/Home.md": ["tags: [house, rent]", "deadlines:", "  - {date: 2030-05-05, note: Rent}"]})
        out, err = self.deadlines("--today", TODAY, "--write", code=2)
        self.assertEqual(out, "")
        self.assertIn("30 Home/Home.md uses YAML this check does not read (a flow sequence)", err)
        self.assertFalse(os.path.exists(self.page))

    def test_the_wiki_is_the_one_the_settings_name(self):
        shutil.move(self.wiki, os.path.join(self.root, "The Notes"))
        write(os.path.join(self.root, "CLAUDE.md"), "# Rules\n")
        pin = hashlib.sha256(read(os.path.join(self.root, "CLAUDE.md"), "rb")).hexdigest()
        write(os.path.join(self.root, ".familyai", "rulebook.json"),
              '{"version": 1, "rulebook_sha256": "%s", "wiki_dir": "The Notes"}' % pin)
        self.deadlines("--today", TODAY, "--write")
        self.assertTrue(read(os.path.join(self.root, "The Notes", *PAGE.split("/"))).startswith("---\nprovenance"))


if __name__ == "__main__":
    unittest.main()
