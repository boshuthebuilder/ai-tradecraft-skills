"""The Deadlines roll-up is read against the roll-up's own output grammar: the page may hold only what the roll-up
renders from the pages' frontmatter, and every other line is reported.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests

`rollups/<scenario>/` is a small wiki whose `01 Deadlines/01 Deadlines.md` is the page family-ai-os's roll-up rendered
from the other pages (`rollups/capture.py` refreshes it by hand; the suite never imports family-ai-os). Those bytes
must read clean, every change to them must be reported, and so must every shape of a hand-kept date that a round of
review found.
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
import unittest.mock
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.realpath(os.path.join(HERE, "..", "tools"))
sys.path.insert(0, TOOLS)
import readiness  # noqa: E402

ROLLUPS = os.path.join(HERE, "rollups")
FIXTURE_WIKI = os.path.join(HERE, "fixture", "Alex Personal", "Alex Personal Wiki")
PAGE = os.path.join("01 Deadlines", "01 Deadlines.md")
NOW = "1719748800"  # 2024-06-30T12:00:00Z, the day the roll-ups were rendered
EM = "\u2014"
HAND = "hand-written content in a derived page"
TAX, HOME = "[20 Finance/Tax](../20%20Finance/Tax.md)", "[30 Home/30 Home](../30%20Home/30%20Home.md)"
INSURANCE = "[30 Home/Insurance](../30%20Home/Insurance.md)"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def line_of(text, needle):
    """The number of the line of `text` that holds `needle`, as readiness counts them (the frontmatter included)."""
    return next(n for n, line in enumerate(text.split("\n"), 1) if needle in line)


class Scenario(unittest.TestCase):
    """A copy of one scenario's wiki, its roll-up page changeable, read through `deadline_items`."""

    def setUp(self):
        patch = unittest.mock.patch.dict(os.environ, {"PRE_ONBOARDING_NOW": NOW})
        patch.start()
        self.addCleanup(patch.stop)
        self.tmp = tempfile.mkdtemp(prefix="rollup_test_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def wiki(self, scenario):
        wiki = os.path.join(tempfile.mkdtemp(dir=self.tmp), scenario)
        shutil.copytree(os.path.join(ROLLUPS, scenario), wiki)
        return wiki

    def check(self, wiki):
        """(dated, recurring, other derived pages) as readiness reports them for this wiki."""
        return readiness.deadline_items(wiki, readiness.W.wiki_pages(wiki), None)

    def page(self, scenario="plain", change=None):
        """What readiness reports for the scenario's roll-up page after `change(text)`."""
        wiki = self.wiki(scenario)
        path = os.path.join(wiki, PAGE)
        if change:
            write(path, change(read(path)))
        return self.check(wiki)

    def reported(self, change, scenario="plain"):
        """The dated and the recurring result of a changed page, which must not both be ok."""
        dated, recurring, _other = self.page(scenario, change)
        self.assertFalse(dated == recurring == "ok", "nothing was reported")
        return dated, recurring

    @staticmethod
    def replace(old, new):
        """A change that swaps `old` for `new` once, and fails when `old` is not in the page."""
        def change(text):
            assert old in text, old
            return text.replace(old, new, 1)
        return change

    @staticmethod
    def append(text):
        return lambda page: page + "\n" + text + "\n"


class RealOutputTest(Scenario):
    """What the real roll-up renders reads clean, whatever it holds."""

    def test_the_scenarios_hold_the_shapes_the_review_named(self):
        plain = read(os.path.join(ROLLUPS, "plain", PAGE))
        for text in ("Renew: 2 weeks before", "Self assessment: due in 2 weeks",  # (a) a quoted note holding a colon
                     "%s Pay 2 instalments (" % EM,  # (b) a `deadline_note`
                     "%s Insurance %s Insurance (" % (EM, EM),  # (c) a note that is a word of its page's name
                     "30 Home, Bank statement (1)",  # two pages on one line, a title with digits and brackets
                     "Bank%20statement%20%281%29.md", "%E4%B8%AD%E6%96%87", "Call (2 calls) about the lease",
                     "Renew before 2030-06-01", "Ask Alex & Sam about 3 policies", "## Past",
                     "- **2031-02-01** %s Tax (" % EM):
            self.assertIn(text, plain)
        self.assertIn("## Could not read", read(os.path.join(ROLLUPS, "could-not-read", PAGE)))  # (d)
        self.assertIn("Roll-up found no frontmatter deadlines across 3 readable pages",
                      read(os.path.join(ROLLUPS, "banner", PAGE)))
        self.assertIn("_None._", read(os.path.join(ROLLUPS, "recurring-only", PAGE)))
        paths = read(os.path.join(ROLLUPS, "paths", PAGE))
        for text in ("Tax [Q1](final) %s Quarter one" % EM, "[20 Finance/x](y](../20%20Finance/x%5D%28y.md)",
                     "Fees%20&%20100%25%20done.md"):  # page names holding brackets, `](` and `%`
            self.assertIn(text, paths)
        self.assertGreater(max(len(x) for x in paths.split("(../")), 300)  # a target over 300 characters
        yaml = read(os.path.join(ROLLUPS, "yaml", PAGE))
        # a comment ends a plain scalar, a comma ends a flow value, a quoted comma and a doubled quote stay
        for text in ("%s Invoice (" % EM, "%s Pay tax (" % EM, "%s Pay tax, file the return (" % EM,
                     "%s It's due (" % EM, "- **2030-08-01** %s Tax (" % EM):
            self.assertIn(text, yaml)

    def test_a_plain_page_and_the_empty_forms_are_clean(self):
        for scenario in ("plain", "recurring-only", "banner", "paths", "yaml"):
            with self.subTest(scenario=scenario):
                self.assertEqual(self.page(scenario), ("ok", "ok", "ok"))

    def test_the_could_not_read_list_is_clean_and_only_the_pages_own_fault_is_reported(self):
        dated, recurring, _other = self.page("could-not-read")
        self.assertEqual(dated, "ok")
        self.assertTrue(recurring.startswith("finding: 3 recurring: entr(ies) not {date, note}"), recurring)
        self.assertNotIn(HAND, recurring)

    def test_the_fixture_renderers_output_is_clean(self):
        """The fixture's roll-up writes `: <note>` where family-ai-os writes the dash, and the pages' own notes."""
        self.assertEqual(readiness.deadline_items(FIXTURE_WIKI, readiness.W.wiki_pages(FIXTURE_WIKI), None),
                         ("ok", "ok", "ok"))


class ChangedOutputTest(Scenario):
    """Every change to what the roll-up rendered is reported: as hand-written content, or as a date when it is one."""

    def assert_hand(self, change, scenario="plain"):
        dated, _recurring = self.reported(change, scenario)
        self.assertIn(HAND, dated)

    PAID = "Pay 2 instalments (%s)" % TAX  # an entry as the roll-up renders it

    def test_text_appended_to_an_entry_is_reported(self):
        for extra in (" and 3 weeks later", " x", ".", " (see 5 April)"):
            with self.subTest(extra=extra):
                self.assert_hand(self.replace(self.PAID, self.PAID + extra))

    def test_a_link_appended_to_an_entry_is_reported(self):
        for extra in ("; [renew 12 May](../20%20Finance/Tax.md)", ", [renew 12 May](../20%20Finance/Tax.md)",
                      ", %s, [x](x.md)" % TAX, " %s" % TAX, ", " + TAX):
            with self.subTest(extra=extra):
                self.assert_hand(self.replace(self.PAID, "Pay 2 instalments (%s%s)" % (TAX, extra)))

    def test_a_link_whose_text_is_a_date_is_reported(self):
        self.assert_hand(self.replace(self.PAID, "Pay 2 instalments ([renew 12 May](../20%20Finance/Tax.md))"))
        self.assert_hand(self.append("- [5 Sept](../20%20Finance/Tax.md)"))
        self.assert_hand(self.append("[5 Sept](../20%20Finance/Tax.md)"))

    def test_a_note_or_a_page_the_frontmatter_does_not_give_is_reported(self):
        for old, new in (("Pay 2 instalments", "Pay 3 instalments"), ("Pay 2 instalments", "pay 2 instalments"),
                         ("Pay 2 instalments (", "Pay 2  instalments ("), ("Paid", "Paid early"),
                         ("- **2031-02-01** %s Tax (" % EM, "- **2031-02-01** %s Tax %s note (" % (EM, EM)),
                         ("Statement due (", "Statement (")):
            with self.subTest(new=new):
                self.assert_hand(self.replace(old, new))
        self.assert_hand(self.replace("%s Statement due ([20 Finance/Bank statement (1)]" % EM,
                                      "%s Statement due ([20 Finance/Tax]" % EM))
        self.assert_hand(self.replace("%s Statement due ([20 Finance/Bank statement (1)](../20%%20Finance/Bank%%20"
                                      "statement%%20%%281%%29.md))" % EM,
                                      "%s Statement due (%s)" % (EM, TAX)))

    def test_a_date_no_page_carries_is_reported_as_one(self):
        text = read(os.path.join(ROLLUPS, "plain", PAGE))
        _dated, recurring = self.reported(self.replace("**12 May**", "**13 May**"))
        self.assertIn("1 yearly date(s) no page's recurring: list carries (line %d: 05-13)" % line_of(text, "12 May"),
                      recurring)
        dated, _recurring = self.reported(self.replace("**2030-05-01**", "**2030-05-02**"))
        self.assertIn("1 date(s) no current page's frontmatter carries (line %d: 2030-05-02)"
                      % line_of(text, "2030-05-01"), dated)

    def test_a_date_that_is_a_date_but_another_entrys_is_hand_written_content(self):
        """12 May is carried, but not with this note."""
        self.assert_hand(self.replace("**12 May** %s Insurance %s Ask Alex" % (EM, EM),
                                      "**12 May** %s Insurance %s Ask Robin" % (EM, EM)))

    def test_a_date_the_contract_cannot_read_is_reported_as_unreadable(self):
        text = read(os.path.join(ROLLUPS, "plain", PAGE))
        for lead in ("5-Apr", "5/Apr", "Apr/5", "05-Apr-2026", "5 - Apr", "5 %s Apr" % EM, "5 Septmber", "5 Sept 26",
                     "6/4", "31-12", "5.4", "4月15日"):
            with self.subTest(lead=lead):
                _dated, recurring = self.reported(self.replace("**12 May**", "**%s**" % lead))
                self.assertIn("1 unreadable yearly date(s) (line %d: %s)" % (line_of(text, "12 May"), lead), recurring)

    def test_an_entry_missing_from_the_roll_up_is_reported_as_missing(self):
        _dated, recurring = self.reported(self.replace(
            "- **12 May** %s Insurance %s Ask Alex & Sam about 3 policies (%s)\n" % (EM, EM, INSURANCE), ""))
        self.assertIn("lacks 1 recurring date(s) (05-12 (30 Home/Insurance.md))", recurring)


class HandKeptTest(Scenario):
    """Every shape of a hand-kept date from every round of review, added to the real output, is reported."""

    SHAPES = (
        "| 31-12 | year end |", "- 31-12: year end", "| 13-01 |", "| 02-30 |", "| 00-10 |", "| 12-32 |", "| 6/4 |",
        "| 31/12 |", "| 5.4 |", "| 5 / 4 |", "| 04 - 05 |", "| 5th of April |", "| April the 5th |", "| 5. September |",
        "| 5 Setpember |", "| 5 Septmber |", "| 5 Sept 26 |", "| 5 Sept '26 |", "| 5 Sept 2026 |",
        "| September 5, 2026 |", "| 31 Sept |", "| 31 April |", "| 32 Jan |", "| Sept 31 |", "| 12 Decisions |",
        "| 5 items | none |", "| 5-Apr |", "| Apr-5 |", "| 5/Apr |", "| Apr/5 |", "| 05-Apr-2026 |", "| 5 - Apr |",
        "| 5 %s Apr |" % EM, "| 5 | April |", "| April | 5 |", "| 5 | Apr |", "| 5Sept |", "| 5thApr |",
        "<5 April>", "<April 5>", "5​April", "5 April​", "| 5 ​April |", "4月15日",
        "| 4月5日 |", "| 5 Sept (fees) |", "| 5 Sept |", "| <b>5 Sept</b> |", "| [5 Sept](x.md) |",
        "| **5** Sept |", "- 5 Sept", "> - 5 Sept", "> 5 Sept", "- [ ] 5 Sept", "- [5 Sept](x.md)", "1) 5 Sept",
        "<td>5 Sept</td>", "- 5th Apr: tax year ends", "- **9 sept**: fees", "| 5 Apr. | tax year ends |",
        "- **01-31**: self assessment", "Fees are due on 5 Sept each year.", "See pages 10-12 of the lease.",
        "- See pages 10-12 of the lease too.", "- 13-45 units of electricity", "- 01-31-2025 is not a month and day",
        "- 01-3122 is a meter reading", "| Date | What |", "| --- | --- |", "## Dates", "# 5 April", "Nothing is due.",
        "None", "---", "_File-derived deadlines, rolled up by hand._", "_None_",
        "> [!warning] Check the dates by hand.",
        "- **5 April** %s Tax" % EM, "- **5 April**: tax year ends", "- **2030-05-01**: Pay 2 instalments",
        "- **5 April** %s Tax %s tax year ends ([Tax](../20%%20Finance/Tax.md)); [renew 12 May](x.md)" % (EM, EM))

    def test_every_shape_is_reported_as_hand_written_content(self):
        for shape in self.SHAPES:
            with self.subTest(shape=shape):
                dated, _recurring = self.reported(self.append(shape))
                self.assertIn(HAND, dated)

    def test_a_shape_is_named_by_its_line(self):
        text = read(os.path.join(ROLLUPS, "plain", PAGE))
        dated, _recurring = self.reported(self.append("| 5 | April |"))
        self.assertIn("%s holds %s, 1 line(s) (line %d: | 5 | April |)"
                      % (readiness.DEADLINES, HAND, len(text.split("\n")) + 1), dated)

    def test_a_shape_in_an_empty_roll_up_is_reported_too(self):
        dated, _recurring, _other = self.page("banner", self.append("| 5-Apr | tax year ends |"))
        self.assertIn(HAND, dated)

    def test_an_invisible_character_is_shown_by_its_code(self):
        dated, _recurring = self.reported(self.append("5​April"))
        self.assertIn("5\\u200bApril", dated)

    def test_a_long_excerpt_is_cut(self):
        dated, _recurring = self.reported(self.append("x" * 300))
        self.assertIn("x" * 40 + "...)", dated)
        self.assertNotIn("x" * 41, dated)


class GrammarTest(unittest.TestCase):
    """The parsing helpers, on lines as written."""

    PAGES = {"20 Finance/Tax.md", "30 Home/30 Home.md", "20 Finance/Bank statement (1).md"}

    def entry(self, line):
        return readiness.parse_entry(line, self.PAGES)

    def test_an_entry_is_its_date_its_note_and_its_pages(self):
        self.assertEqual(self.entry("- **5 April** %s Tax %s Pay 2 instalments (%s)" % (EM, EM, TAX)),
                         ("5 April", "Pay 2 instalments", ["20 Finance/Tax.md"]))
        self.assertEqual(self.entry("- **5 April** %s Tax (%s)" % (EM, TAX)), ("5 April", "", ["20 Finance/Tax.md"]))
        self.assertEqual(self.entry("- **2025-04-30**: Lease ends ([30 Home](../30%20Home/30%20Home.md))"),
                         ("2025-04-30", "Lease ends", ["30 Home/30 Home.md"]))
        both = "(%s, [20 Finance/Bank statement (1)](../20%%20Finance/Bank%%20statement%%20%%281%%29.md))" % HOME
        two = "- **28 February** %s 30 Home, Bank statement (1) %s Call (2 calls) %s" % (EM, EM, both)
        self.assertEqual(self.entry(two), ("28 February", "Call (2 calls)",
                                           ["30 Home/30 Home.md", "20 Finance/Bank statement (1).md"]))

    def test_a_note_may_hold_what_the_layout_does(self):
        for note in ("Renew ([x](y)) soon", "a %s b" % EM, "Insurance", "x: y", "2030-01-01 or 3 weeks", "([a](b)"):
            with self.subTest(note=note):
                self.assertEqual(self.entry("- **5 April** %s Tax %s %s (%s)" % (EM, EM, note, TAX)),
                                 ("5 April", note, ["20 Finance/Tax.md"]))

    def test_a_line_that_is_not_laid_out_so_is_no_entry(self):
        good = "- **5 April** %s Tax (%s)" % (EM, TAX)
        self.assertIsNotNone(self.entry(good))
        for line in (good[:-1], good + " x", good + ")", good.replace("Tax (", "Tax(", 1),
                     good.replace("%s Tax" % EM, "Tax"), good.replace("Tax (", "Home ("),
                     good.replace("** %s" % EM, "**%s" % EM),
                     good.replace("- **", "* **"), good.replace("- **5 April**", "- 5 April"),
                     good.replace("Tax]", "Tax2]"), good.replace("../", ""), good.replace("Tax.md", "Tax.md#x"),
                     good.replace("20%20Finance", "20%20Finance/../20%20Finance"),
                     good.replace("[20 Finance/Tax]", "[renew 12 May]"), good[:-1] + ";" + TAX + ")",
                     "- **5 April**", "- **", "", "-"):
            with self.subTest(line=line):
                self.assertIsNone(self.entry(line))

    def test_a_page_name_holding_brackets_or_a_long_target_is_read_by_its_own_text(self):
        pages = {"20 Finance/Tax [Q1](final).md", "20 Finance/x](y.md", "20 Finance/" + "\u4e2d" * 80 + ".md"}
        for page in sorted(pages):
            target = "../" + urllib.parse.quote(page, safe="/&")
            title = page[:-3].split("/")[1]
            line = "- **5 April** %s %s %s Note ([%s](%s))" % (EM, title, EM, page[:-3], target)
            self.assertEqual(readiness.parse_entry(line, pages), ("5 April", "Note", [page]), line)

    def test_the_banner_is_the_roll_ups_with_a_count(self):
        self.assertEqual(readiness.banner("> The roll-up found no frontmatter deadlines across 11 pages."), 0)
        for line in ("> The roll-up found no frontmatter deadlines across x pages.",
                     "> The roll-up found no frontmatter deadlines across 11 May pages.",
                     "> The roll-up found no frontmatter deadlines across 11 pages. Also 5 April.",
                     "> The roll-up found no frontmatter deadlines across \u0661\u0661 pages.",
                     "> The roll-up found no frontmatter deadlines across  pages.",
                     "> [!warning] The roll-up found no frontmatter deadlines across 11 pages.", ""):
            with self.subTest(line=line):
                self.assertIsNone(readiness.banner(line))

    def test_a_line_of_nothing_says_nothing(self):
        for line in ("", "---", "* * *", "> - none", "_None_", "**N/A**", "| nothing |", "- na.", "  None.  "):
            with self.subTest(line=line):
                self.assertTrue(readiness.says_nothing(line))
        for line in ("None of this", "Nothing is due", "- x", "none x", "5 April", "> note"):
            with self.subTest(line=line):
                self.assertFalse(readiness.says_nothing(line))

    def test_a_note_is_read_as_yaml_reads_it(self):
        """A quoted scalar without its quotes; a plain one ends at ` #`; in a flow mapping a comma ends the value and
        what follows is a key of its own."""
        for text, want in (('"Renew: 2 weeks"', "Renew: 2 weeks"), ("'It''s due'", "It's due"),
                           ('"say \\"hi\\""', 'say "hi"'), ("plain", "plain"), ("  spaced  ", "spaced"),
                           ("Invoice #42 due", "Invoice"), ("#42", ""), ("a#b", "a#b"), ('"half', '"half'), ("", "")):
            self.assertEqual(readiness.block_value(text), want, text)
        self.assertEqual(readiness.flow_pairs("date: 04-05, note: Pay tax, file the return"),
                         [("date", "04-05", False), ("note", "Pay tax", False), ("file the return", None, False)])
        self.assertEqual(readiness.flow_pairs("note: \"Pay tax, file the return\", date: 7 July"),
                         [("note", "Pay tax, file the return", True), ("date", "7 July", False)])
        self.assertEqual(readiness.flow_pairs("date: 1 May, note: 'a, b'"),
                         [("date", "1 May", False), ("note", "a, b", True)])
        self.assertEqual(readiness.date_entry("{date: 04-05, note: Pay tax, file the return}"), ("04-05", "Pay tax"))
        self.assertEqual(readiness.date_entry({"date": "04-05", "note": "Pay tax, file the return"}),
                         ("04-05", "Pay tax"))
        self.assertEqual(readiness.date_entry("2030-08-01 # the cutoff"), ("2030-08-01", None))

    def test_a_refused_recurring_item_is_written_as_the_roll_up_writes_it(self):
        hint = readiness.DATE_HINT
        for item, want in (("{date: 31 April, note: nonsense}", "{'date': '31 April', 'note': 'nonsense'}" + hint),
                           ("6/4", "'6/4'" + hint),
                           ("{note: no date key}", "{'note': 'no date key'}" + readiness.KEY_HINT),
                           ("{date: 2025-01-31, note: Self}",
                            "{'date': datetime.date(2025, 1, 31), 'note': 'Self'}" + hint),
                           ("{date: 04-31, note: a, b}", "{'date': '04-31', 'note': 'a', 'b': None}" + hint),
                           ("{date: 6.4}", "{'date': 6.4}" + hint)):
            self.assertEqual(readiness.refused_item(item), want, item)
        self.assertEqual(len(readiness.refused_item("{date: 31 April, note: %s}" % ("x" * 100)).split(";")[0]), 60)
        for item in ("{date: 04-05, note: x}", "{date: 5 April}", "5 April", "{date: '04-05'}"):
            self.assertIsNone(readiness.refused_item(item), item)


class FrontmatterTest(Scenario):
    """The page's own frontmatter holds the three keys the roll-up writes, once each, with the values it writes."""

    def test_any_other_line_is_hand_written_content(self):
        for extra in ("fees: due 5 April", "deadline: 2031-01-01", "| a | b |", "recurring:",
                      "  - {date: 5 April, note: x}",
                      "status: current", "last-updated: soon", "last-updated: 2024-02-30", "provenance: manual",
                      "status: superseded", "provenance: derived", "tags: [a]"):
            with self.subTest(extra=extra):
                dated, _recurring = self.reported(
                    self.replace("status: current\n---", "status: current\n%s\n---" % extra))
                self.assertIn(HAND, dated)
                self.assertIn("line 5: %s" % extra[:40], dated)

    def test_a_value_the_roll_up_does_not_write_is_reported(self):
        dated, _recurring = self.reported(self.replace("provenance: derived", "provenance: manual"))
        self.assertIn("line 2: provenance: manual", dated)
        dated, _recurring = self.reported(self.replace("last-updated: 2024-06-30", "last-updated: soon"))
        self.assertIn("line 3: last-updated: soon", dated)

    def test_a_page_with_no_frontmatter_has_no_frontmatter_line_to_report(self):
        """`wiki.py check` reports the keys a page lacks; this reads the lines it has."""
        self.assertEqual(self.page("plain", lambda t: t.split("---\n", 2)[2]), ("ok", "ok", "ok"))


class CouldNotReadTest(Scenario):
    """The roll-up's list of what it could not read is clean only as the pages themselves give it."""

    ITEM = ("- 30 Home/Bad.md (unreadable recurring date: {'date': '31 April', 'note': 'nonsense'}%s)"
            % readiness.DATE_HINT)

    def test_the_lines_of_a_real_list_are_the_expected_ones(self):
        self.assertIn(self.ITEM, read(os.path.join(ROLLUPS, "could-not-read", PAGE)))

    def assert_hand(self, change, scenario="could-not-read"):
        dated, _recurring = self.reported(change, scenario)
        self.assertIn(HAND, dated)
        return dated

    def test_text_the_roll_up_never_writes_is_reported(self):
        self.assert_hand(self.append("- 20 Finance/Tax.md (unreadable: Fees_due_April5)"))
        self.assert_hand(self.append("- 20 Finance/Tax.md (malformed frontmatter)"))  # a page that reads fine
        self.assert_hand(self.append("- 10 Identity/Broken.md (malformed frontmatter) and more"))
        self.assert_hand(self.append("- 30 Home/Bad.md (unreadable recurring date: {'date': '5 Sept'}%s)"
                                     % readiness.DATE_HINT))
        self.assert_hand(self.replace("'nonsense'", "'nonsense, 5 April'"))
        self.assert_hand(self.replace("{'date': '6/4', 'note': 'slashes'}", "{'date': '6/4'}"))
        self.assert_hand(self.replace("(malformed frontmatter)", "(unreadable: Fees_due_April5)"))
        self.assert_hand(self.replace(readiness.KEY_HINT + ")", readiness.DATE_HINT + ")"))

    def test_a_line_written_twice_is_reported(self):
        self.assert_hand(self.replace(self.ITEM + "\n", self.ITEM + "\n" + self.ITEM + "\n"))

    def test_the_heading_above_the_roll_up_makes_nothing_clean(self):
        """`## Could not read` placed first, with date-shaped text under it: none of it is the roll-up's."""
        self.assert_hand(self.replace("## Upcoming", "## Could not read\n\n- 20 Finance/Tax.md (unreadable: Due5April)"
                                      "\n\n## Upcoming"), "plain")

    def test_a_page_that_is_not_utf8_is_listed_as_the_roll_up_lists_it(self):
        wiki = self.wiki("plain")
        with open(os.path.join(wiki, "20 Finance", "Binary.md"), "wb") as f:
            f.write(b"---\nprovenance: derived\n---\n\xff\xfe not text\n")
        path = os.path.join(wiki, PAGE)
        listed = ("\n## Could not read\n\n%s\n\n- 20 Finance/Binary.md (unreadable: UnicodeDecodeError)\n"
                  % readiness.UNREAD_INTRO)
        write(path, read(path) + listed)
        self.assertEqual(self.check(wiki), ("ok", "ok", "ok"))
        write(path, read(path).replace("(unreadable: UnicodeDecodeError)", "(unreadable: PermissionError)"))
        self.assertIn(HAND, self.check(wiki)[0])
        write(path, read(path).replace("20 Finance/Binary.md (unreadable: PermissionError)",
                                       "20 Finance/Tax.md (unreadable: UnicodeDecodeError)"))
        self.assertIn(HAND, self.check(wiki)[0])

    def test_a_malformed_frontmatter_is_the_one_the_roll_up_cannot_read(self):
        for text, bad in (("---\nkey: v\nno fence closes", True), ("---\n- a\n- b\n---\n", True),
                          ("---\njust text\n---\n", True), ("---\n---\n# x", False), ("---\nkey: v\n---\n", False),
                          ("# no frontmatter", False), ("---\n# only a comment\n---\n", False)):
            self.assertEqual(readiness.malformed(text), bad, text)


class EntryFormTest(Scenario):
    """An entry is in the form the roll-up writes, once, and in its place."""

    def assert_hand(self, change, scenario="plain"):
        dated, _recurring = self.reported(change, scenario)
        self.assertIn(HAND, dated)

    def test_a_date_spelt_another_way_is_hand_edited(self):
        for lead in ("05-12", "May 12th", "12th May", "12 may", "12 MAY", "12  May", "12 May "):
            with self.subTest(lead=lead):
                self.assert_hand(self.replace("**12 May**", "**%s**" % lead))

    def test_an_entry_written_twice_is_reported(self):
        line = "- **12 May** %s Insurance %s Ask Alex & Sam about 3 policies (%s)\n" % (EM, EM, INSURANCE)
        self.assert_hand(self.replace(line, line + line))
        self.assert_hand(self.replace("## Past\n", "## Past\n\n## Past\n"))
        self.assert_hand(self.replace("_File-derived", "_File-derived deadlines, rolled up deterministically from page "
                                      "frontmatter %s do not hand-edit, regenerated each run. (Calendar events live in "
                                      "`Coming Events`.)_\n\n_File-derived" % EM))

    def test_the_banner_is_accepted_only_where_the_roll_up_puts_it(self):
        text = read(os.path.join(ROLLUPS, "banner", PAGE))
        banner_line = next(x for x in text.split("\n") if x.startswith("> **Roll-up"))
        self.assertEqual(self.page("banner"), ("ok", "ok", "ok"))
        for count in ("3", "99"):  # any count of pages
            self.assertEqual(self.page("banner", self.replace("across 3 readable", "across %s readable" % count)),
                             ("ok", "ok", "ok"))
        self.assert_hand(lambda t: t.replace(banner_line + "\n\n", "").replace("_None._", "_None._\n\n" + banner_line),
                         "banner")  # below the section
        self.assert_hand(self.replace("## Upcoming", banner_line + "\n\n## Upcoming"), "plain")  # over entries
        self.assert_hand(self.replace(banner_line + "\n", banner_line + "\n\n" + banner_line + "\n"), "banner")
        self.assert_hand(self.append("> [!warning]"), "plain")
        self.assert_hand(self.append("> The roll-up found no frontmatter deadlines across 3 pages."), "banner")

    def test_the_two_line_callout_is_accepted_in_the_banners_place(self):
        callout = "> [!warning]\n> The roll-up found no frontmatter deadlines across 3 pages."
        text = read(os.path.join(ROLLUPS, "banner", PAGE))
        banner_line = next(x for x in text.split("\n") if x.startswith("> **Roll-up"))
        self.assertEqual(self.page("banner", self.replace(banner_line, callout)), ("ok", "ok", "ok"))
        self.assert_hand(self.replace(banner_line, "> [!warning]\n\n> The roll-up found no frontmatter deadlines "
                                                   "across 3 pages.\n> [!warning]"), "banner")
        self.assert_hand(self.replace(banner_line, "> The roll-up found no frontmatter deadlines across 3 pages."),
                         "banner")


class YamlRuleTest(Scenario):
    """A note is what YAML reads, so the roll-up's own output for the plain-scalar rules reads clean and any other
    reading of it is reported."""

    def test_the_text_a_comma_or_a_comment_cuts_off_is_not_the_note(self):
        yaml = read(os.path.join(ROLLUPS, "yaml", PAGE))
        for old, new in (("Pay tax (", "Pay tax, file the return ("), ("Invoice (", "Invoice #42 due ("),
                         ("2030-08-01** %s Tax (" % EM, "2030-08-01** %s Tax %s the cutoff (" % (EM, EM)),
                         ("It's due (", "'It''s due' ("), ("Pay tax, file the return (", "Pay tax (")):
            with self.subTest(old=old):
                self.assertIn(old, yaml)
                dated, recurring, _other = self.page("yaml", self.replace(old, new))
                self.assertIn(HAND, dated)

    def test_the_two_rules_through_the_whole_check(self):
        wiki = self.wiki("yaml")
        self.assertEqual(self.check(wiki), ("ok", "ok", "ok"))


class UnreadablePageTest(Scenario):
    """One page that cannot be read does not stop the check."""

    def test_the_check_goes_on(self):
        wiki = self.wiki("plain")
        with open(os.path.join(wiki, "20 Finance", "Binary.md"), "wb") as f:
            f.write(b"\xff\xfe")
        dated, recurring, other = self.check(wiki)
        self.assertEqual((dated, recurring, other), ("ok", "ok", "ok"))


class SpeedTest(Scenario):
    """A line of 100,000 characters costs a pass over it and no more: each shape below is read in under a second."""

    def test_a_long_line_of_any_shape_is_read_in_a_second(self):
        for name, line in (("<", "<" * 100000), ("[", "[" * 100000), ("](", "](" * 50000), (" ([", " ([" * 33000),
                           ("<td", "<td" * 33000), ("- **", "- **" * 25000), ("links", "[x](" * 25000),
                           ("entry", "- **5 April** %s Tax %s %s ([" % (EM, EM, "x" * 100000)),
                           ("candidates", "- **5 April** %s Tax %s%s)" % (EM, EM, " ([x](y)" * 20000)),
                           ("mixed", ("- **5 April** %s [a](b) <b ([ " % EM) * 3000), ("letters", "a" * 100000),
                           ("digits", "5" * 100000), ("dots", "5." * 50000), ("quoted", "> " * 50000),
                           ("unread", "- x (" * 20000), ("stars", "*" * 100000 + "x"), ("dashes", "- " * 50000 + "x"),
                           ("spaces", " " * 100000 + "x"), ("stars and spaces", "** " * 33333 + "x"),
                           ("quotes and bars", ">|" * 50000 + "x"), ("underscores", "_" * 100000 + "x"),
                           ("dots and stars", ".*" * 50000 + "x")):
            for heading in ("", "\n## Could not read\n\n"):
                with self.subTest(line=name, under_could_not_read=bool(heading)):
                    wiki = self.wiki("plain")
                    path = os.path.join(wiki, PAGE)
                    write(path, read(path) + heading + line + "\n")
                    start = time.perf_counter()
                    dated, _recurring, _other = self.check(wiki)
                    self.assertLess(time.perf_counter() - start, 1.0)
                    self.assertIn(HAND, dated)

    SHAPES = ("{date: a" + " " * 100000 + "b}", "{date: 04-05, note: " + "x" * 100000 + "}",
              "{date: " + "5 " * 50000 + "}",
              "a" + " " * 100000 + "b", "{" + "," * 100000 + "}", "{" + ":" * 100000 + "}", "{" + "'" * 100000 + "}",
              "{date: \"" + "\\" * 100000 + "}", "{" + "a: " * 33000 + "}", "x #" * 33000, "#" + "x" * 100000,
              "\"" + "x" * 100000, "{date: 04-05, note: " + "'" * 100000 + "}", "5" * 100000, "5." * 50000,
              "5 April" + " " * 100000 + "x", "{note: " + ", " * 50000 + "}")

    def test_a_long_frontmatter_item_is_read_in_a_second(self):
        for shape in self.SHAPES:
            for lines in ("recurring:\n  - %s\n", "deadlines:\n  - %s\n", "deadline: %s\n",
                          "deadline: 2030-01-01\ndeadline_note: %s\n"):
                with self.subTest(shape=shape[:30], lines=lines.split(":")[0]):
                    wiki = self.wiki("plain")
                    write(os.path.join(wiki, "20 Finance", "Long.md"),
                          "---\nstatus: current\n" + lines % shape + "---\n")
                    start = time.perf_counter()
                    self.check(wiki)
                    self.assertLess(time.perf_counter() - start, 1.0)


if __name__ == "__main__":
    unittest.main()
