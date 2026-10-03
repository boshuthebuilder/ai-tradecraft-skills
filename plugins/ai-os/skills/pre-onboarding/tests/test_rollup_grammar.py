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

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.realpath(os.path.join(HERE, "..", "tools"))
sys.path.insert(0, TOOLS)
import readiness  # noqa: E402

ROLLUPS = os.path.join(HERE, "rollups")
FIXTURE_WIKI = os.path.join(HERE, "fixture", "Alex Personal", "Alex Personal Wiki")
PAGE = os.path.join("01 Deadlines", "01 Deadlines.md")
NOW = "1719748800"  # 2024-06-30T12:00:00Z, the day the roll-ups were rendered
EM = "—"
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

    def test_a_plain_page_and_the_empty_forms_are_clean(self):
        for scenario in ("plain", "recurring-only", "banner"):
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
                     "- **" + "x" * 100 + "**: n (%s)" % TAX, "- **5 April**", "- **", "", "-"):
            with self.subTest(line=line):
                self.assertIsNone(self.entry(line))

    def test_the_banner_is_the_roll_ups_with_a_count(self):
        self.assertTrue(readiness.banner("> The roll-up found no frontmatter deadlines across 11 pages."))
        for line in ("> The roll-up found no frontmatter deadlines across x pages.",
                     "> The roll-up found no frontmatter deadlines across 11 May pages.",
                     "> The roll-up found no frontmatter deadlines across 11 pages. Also 5 April.",
                     "> The roll-up found no frontmatter deadlines across \u0661\u0661 pages.",
                     "> The roll-up found no frontmatter deadlines across  pages.",
                     "> [!warning] The roll-up found no frontmatter deadlines across 11 pages.", ""):
            with self.subTest(line=line):
                self.assertFalse(readiness.banner(line))

    def test_a_could_not_read_line_names_a_page_and_a_reason_the_roll_up_writes(self):
        pages, refusing = {"30 Home/Bad.md", "10 Identity/Broken.md"}, {"30 Home/Bad.md"}
        hint = readiness.UNREAD_HINTS[0]
        for line in ("- 10 Identity/Broken.md (malformed frontmatter)",
                     "- 30 Home/Bad.md (unreadable: UnicodeDecodeError)",
                     "- 30 Home/Bad.md (unreadable recurring date: {'date': '31 April'}%s)" % hint):
            with self.subTest(line=line):
                self.assertTrue(readiness.unread_line(line, pages, refusing))
        for line in ("- 10 Identity/Other.md (malformed frontmatter)",
                     "- 10 Identity/Broken.md (malformed frontmatter) x",
                     "- 10 Identity/Broken.md (unreadable recurring date: x%s)" % hint,
                     "- 30 Home/Bad.md (unreadable recurring date: %s%s)" % ("x" * 100, hint),
                     "- 30 Home/Bad.md (unreadable recurring date: {'date': '5 Sept'})",
                     "30 Home/Bad.md (malformed frontmatter)", "- 30 Home/Bad.md (unreadable: a b)",
                     "- 30 Home/Bad.md (renew 12 May)", ""):
            with self.subTest(line=line):
                self.assertFalse(readiness.unread_line(line, pages, refusing))

    def test_a_note_is_read_as_yaml_reads_a_scalar(self):
        for text, want in (('"Renew: 2 weeks"', "Renew: 2 weeks"), ("'It''s due'", "It's due"),
                           ('"say \\"hi\\""', 'say "hi"'), ("plain", "plain"), ("  spaced  ", "spaced"),
                           ('"half', '"half'), ("", ""), (None, "")):
            self.assertEqual(readiness.scalar(text), want)


class SpeedTest(Scenario):
    """A line of 100,000 characters costs a pass over it and no more: each shape below is read in under a second."""

    def test_a_long_line_of_any_shape_is_read_in_a_second(self):
        for name, line in (("<", "<" * 100000), ("[", "[" * 100000), ("](", "](" * 50000), (" ([", " ([" * 33000),
                           ("<td", "<td" * 33000), ("- **", "- **" * 25000), ("links", "[x](" * 25000),
                           ("entry", "- **5 April** %s Tax %s %s ([" % (EM, EM, "x" * 100000)),
                           ("candidates", "- **5 April** %s Tax %s%s)" % (EM, EM, " ([x](y)" * 20000)),
                           ("mixed", ("- **5 April** %s [a](b) <b ([ " % EM) * 3000), ("letters", "a" * 100000),
                           ("digits", "5" * 100000), ("dots", "5." * 50000), ("quoted", "> " * 50000),
                           ("unread", "- x (" * 20000)):
            for heading in ("", "\n## Could not read\n\n"):
                with self.subTest(line=name, under_could_not_read=bool(heading)):
                    wiki = self.wiki("plain")
                    path = os.path.join(wiki, PAGE)
                    write(path, read(path) + heading + line + "\n")
                    start = time.perf_counter()
                    dated, _recurring, _other = self.check(wiki)
                    self.assertLess(time.perf_counter() - start, 1.0)
                    self.assertIn(HAND, dated)


if __name__ == "__main__":
    unittest.main()
