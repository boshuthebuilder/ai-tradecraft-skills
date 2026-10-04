"""The Deadlines roll-up is read against the roll-up's own output grammar: the page may hold only what the roll-up
renders from the pages' frontmatter, and every other line is reported.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests

`rollups/<scenario>/` is a small wiki whose `01 Deadlines/01 Deadlines.md` is the page the reference roll-up rendered
from the other pages (`rollups/capture.py` refreshes it by hand; the suite never imports the deployment). Those bytes
must read clean, every change to them must be reported, and so must every shape of a hand-kept date that a round of
review found.
"""
import itertools
import os
import re
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
        return self.full(wiki)[:3]

    def full(self, wiki):
        """The same and, last, the pages whose frontmatter the check does not read, each named as not verified."""
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
        for scenario in ("plain", "recurring-only", "banner", "paths", "yaml", "hidden"):
            with self.subTest(scenario=scenario):
                self.assertEqual(self.page(scenario), ("ok", "ok", "ok"))

    def test_the_scenarios_hold_the_shapes_the_last_review_named(self):
        yaml = read(os.path.join(ROLLUPS, "yaml", PAGE))
        for text in ("Annual return (", "Block item (", "Block deadline ("):  # a comment after `}`, block mapping items
            self.assertIn(text, yaml)
        refused = read(os.path.join(ROLLUPS, "refused", PAGE))
        for text in ("{'date': '6/4', 'note': ''}", "{'date': '', 'note': 'x'}", "(unreadable recurring date: '5';",
                     "datetime.date(2025, 1, 31)", "'2025-01-31'"):  # quoted empties, bare quoted items
            self.assertIn(text, refused)
        self.assertEqual(refused.count("{'date': '31 April', 'note': 'nonsense'}"), 2)  # the same item twice
        hidden = read(os.path.join(ROLLUPS, "hidden", PAGE))
        for text in ("[.trash/Old](../.trash/Old.md)", "[20 Finance/.Draft](../20%20Finance/.Draft.md)"):
            self.assertIn(text, hidden)  # pages under a dot folder, and a dot file
        for text in ("Before the edit", "A proposal", "2031-01-01", "2032-01-01"):
            self.assertNotIn(text, hidden)  # a .superseded.md or .proposed.md sibling

    def test_the_could_not_read_list_is_clean_and_only_the_pages_own_fault_is_reported(self):
        dated, recurring, _other = self.page("could-not-read")
        self.assertEqual(dated, "ok")
        self.assertTrue(recurring.startswith("finding: 3 recurring: entr(ies) not {date, note}"), recurring)
        self.assertNotIn(HAND, recurring)

    def test_the_refused_items_read_clean_and_only_the_pages_own_fault_is_reported(self):
        dated, recurring, _other, outside = self.full(self.wiki("refused"))
        self.assertEqual((dated, outside), ("ok", []))
        self.assertTrue(recurring.startswith("finding: 8 recurring: entr(ies) not {date, note}"), recurring)
        self.assertNotIn(HAND, recurring)

    def test_a_value_the_roll_up_coerced_is_not_verified_never_a_finding(self):
        """`yes` is written `True`, `12:30` is written 750: the check does not read what it cannot give back."""
        page = read(os.path.join(ROLLUPS, "coerced", PAGE))
        for text in ("Yes %s True (" % EM, "Number %s 5 (" % EM, "Time %s 750 (" % EM, "Date %s 2025-01-31 (" % EM,
                     "- **6 April** %s Null (" % EM, "- **10 April** %s Tilde (" % EM):
            self.assertIn(text, page)
        dated, recurring, other, outside = self.full(self.wiki("coerced"))
        self.assertEqual((dated, recurring, other), ("ok", "ok", "ok"))
        kinds = (("Comment", "bool"), ("Date", "date"), ("Null", "null"), ("Number", "number"), ("Tilde", "null"),
                 ("Time", "time"), ("Yes", "bool"))
        self.assertEqual(outside, ["not verified: 20 Finance/%s.md uses YAML this check does not read "
                                   "(a plain value YAML reads as %s)" % item for item in kinds])

    def test_a_page_beside_a_coerced_value_is_still_read(self):
        wiki = self.wiki("coerced")
        path = os.path.join(wiki, PAGE)
        write(path, read(path).replace("A plain note", "Another note"))
        dated, _recurring, _other, outside = self.full(wiki)
        self.assertEqual(len(outside), 7)
        self.assertEqual(dated, "ok")  # whether an entry is backed needs the pages, so it is withheld
        write(path, read(path) + "| 5 | April |\n")
        self.assertIn(HAND, self.full(wiki)[0])  # the lines the roll-up does not write are still reported

    def test_a_date_that_is_a_value_yaml_reads_otherwise_is_the_pages_own_fault(self):
        page = read(os.path.join(ROLLUPS, "typed-dates", PAGE))
        for text in ("{'date': True, 'note': 'x'}", "{'date': None, 'note': 'why'}", "{'date': 5, 'note': 'z'}",
                     "{'date': 6.4}", "unreadable recurring date: False;", "unreadable recurring date: None;",
                     "datetime.date(2025, 1, 31); write", "{'date': datetime.date(2025, 1, 31), 'note': 'w'}"):
            self.assertIn(text, page)
        dated, recurring, other, outside = self.full(self.wiki("typed-dates"))
        self.assertEqual((dated, other, outside), ("ok", "ok", []))
        self.assertTrue(recurring.startswith("finding: 8 recurring: entr(ies) not {date, note}"), recurring)
        self.assertNotIn(HAND, recurring)

    def test_a_page_of_any_provenance_is_a_source(self):
        """The roll-up skips no provenance: a calendar page's and a manual page's dates are on the page."""
        self.assertEqual(self.full(self.wiki("provenance")), ("ok", "ok", "ok", []))
        page = read(os.path.join(ROLLUPS, "provenance", PAGE))
        for text in ("Manual %s Owner asserted (" % EM, "Calendar %s From the calendar (" % EM,
                     "- **2030-02-02** %s Manual (" % EM):
            self.assertIn(text, page)

    def test_a_date_only_a_page_of_another_provenance_holds_is_expected(self):
        for old, want in (("- **6 April** %s Manual %s Owner asserted ([30 Home/Manual](../30%%20Home/Manual.md))\n"
                           % (EM, EM), "lacks 1 recurring date(s) (04-06 (30 Home/Manual.md))"),
                          ("- **7 April** %s Calendar %s From the calendar "
                           "([30 Home/Calendar](../30%%20Home/Calendar.md))\n" % (EM, EM),
                           "lacks 1 recurring date(s) (04-07 (30 Home/Calendar.md))")):
            with self.subTest(want=want):
                _dated, recurring = self.reported(self.replace(old, ""), "provenance")
                self.assertIn(want, recurring)
        dated, _recurring = self.reported(self.replace(
            "- **2030-02-02** %s Manual ([30 Home/Manual](../30%%20Home/Manual.md))\n" % EM, ""), "provenance")
        self.assertIn("lacks 1 page deadline(s) (2030-02-02 (30 Home/Manual.md))", dated)

    def test_the_fixture_renderers_output_is_clean(self):
        """The fixture's roll-up writes `: <note>` where the reference roll-up writes the dash, and the pages' notes."""
        self.assertEqual(readiness.deadline_items(FIXTURE_WIKI, readiness.W.wiki_pages(FIXTURE_WIKI), None),
                         ("ok", "ok", "ok", []))


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

    def test_a_link_to_a_wiki_page_added_after_an_entry_is_reported(self):
        """The link is real and the page exists; the roll-up still did not write it."""
        for link in ("[7 June](../30%20Home/30%20Home.md)", "[Home](../30%20Home/30%20Home.md)", HOME):
            for lead in (" ", ", ", "; "):
                with self.subTest(link=link, lead=lead):
                    self.assert_hand(self.replace(self.PAID, self.PAID + lead + link))
        self.assert_hand(self.replace(self.PAID, "Pay 2 instalments (%s [7 June](../30%%20Home/30%%20Home.md))" % TAX))

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
        "| **5** Sept |", "- 5 Sept", "> - 5 Sept", "> 5 Sept", "- [ ] 5 Sept", "- [ ] 5 April: pay fee",
        "- [x] 5 April: pay fee", "- [5 Sept](x.md)", "1) 5 Sept",
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

    @staticmethod
    def frontmatter(block):
        return readiness.read_frontmatter("---\n%s\n---\n# Page\n" % block)

    def item(self, text, key="recurring"):
        """The one list item the key holds, written `text`."""
        return self.frontmatter("%s:\n  - %s" % (key, text))[key][0]

    def test_a_note_is_read_as_yaml_reads_it(self):
        """A quoted scalar without its quotes; a plain one ends at ` #`; in a flow mapping an unquoted comma ends the
        value and what follows is a key of its own; a comment may follow a scalar or a closing brace."""
        for text, want in (("{date: 04-05, note: Pay tax, file the return}", ("04-05", "Pay tax")),
                           ('{date: 04-05, note: "Pay tax, file the return"}', ("04-05", "Pay tax, file the return")),
                           ("{date: 1 May, note: 'a, b'}", ("1 May", "a, b")),
                           ("{date: 1 May, note: 'It''s'}", ("1 May", "It's")),
                           ('{date: 1 May, note: "say \\"hi\\""}', ("1 May", 'say "hi"')),
                           ("{note: x, date: 7 July}", ("7 July", "x")),
                           ("{date: 04-05, note: Annual}  # yearly", ("04-05", "Annual")),
                           ("{date: 2026-04-05, note: a} # b}", ("2026-04-05", "a")),
                           ("{date: 04-05}", ("04-05", None)), ("{date: 04-05, note: }", ("04-05", None)),
                           ("{date: 04-05, note: \"\"}", ("04-05", None)),
                           ("{date: 04-05, note: a:b}", ("04-05", "a:b")),
                           ("5 April", ("5 April", None)), ("2030-08-01 # the cutoff", ("2030-08-01", None)),
                           ('"2025-01-31"', ("2025-01-31", None)), ("  5 April  ", ("5 April", None))):
            self.assertEqual(readiness.date_entry(self.item(text)), want, text)
        self.assertEqual(self.frontmatter("deadline_note: Invoice #42 due")["deadline_note"].text, "Invoice")
        self.assertEqual(self.frontmatter("deadline_note: a#b")["deadline_note"].text, "a#b")
        self.assertEqual(self.frontmatter("deadline_note: \"Invoice #42 due\" # c")["deadline_note"].text,
                         "Invoice #42 due")
        self.assertEqual(self.frontmatter("a: b\na: c")["a"].text, "c")  # a repeated key: the last one

    def test_the_subset_reads_blocks_of_every_shape_it_names(self):
        fm = self.frontmatter("provenance: derived # c\nrecurring:\n- {date: 5 April, note: A}\n"
                              "- date: 6 April\n  note: B\n- 7 April # bare\ndeadlines: []\n"
                              "deadline:\nlist:\n    - x\n    - \"y\"\n# a comment\nempty:   # none\nflow: {a: 1}")
        self.assertEqual(fm["provenance"].text, "derived")
        self.assertEqual([readiness.date_entry(it) for it in fm["recurring"]],
                         [("5 April", "A"), ("6 April", "B"), ("7 April", None)])
        self.assertEqual((fm["deadlines"], fm["deadline"], fm["empty"]), ([], None, None))
        self.assertEqual([x.text for x in fm["list"]], ["x", "y"])
        self.assertEqual(fm["flow"]["a"].text, "1")
        self.assertEqual(readiness.read_frontmatter("# no frontmatter"), {})
        self.assertEqual(readiness.read_frontmatter("---\n---\n# x"), {})

    def test_a_refused_recurring_item_is_written_as_the_roll_up_writes_it(self):
        hint = readiness.DATE_HINT
        for item, want in (("{date: 31 April, note: nonsense}", "{'date': '31 April', 'note': 'nonsense'}" + hint),
                           ("6/4", "'6/4'" + hint), ("{date: 6/4, note: \"\"}", "{'date': '6/4', 'note': ''}" + hint),
                           ("{date: '', note: x}", "{'date': '', 'note': 'x'}" + hint),
                           ('"2025-01-31"', "'2025-01-31'" + hint), ("2025-01-31", "datetime.date(2025, 1, 31)" + hint),
                           ('"5"', "'5'" + hint), ("5", "5" + hint),
                           ("{note: no date key}", "{'note': 'no date key'}" + readiness.KEY_HINT),
                           ("{date: 2025-01-31, note: Self}",
                            "{'date': datetime.date(2025, 1, 31), 'note': 'Self'}" + hint),
                           ("{date: 04-31, note: a, b}", "{'date': '04-31', 'note': 'a', 'b': None}" + hint),
                           ("{date: 6.4}", "{'date': 6.4}" + hint)):
            self.assertEqual(readiness.refused_item(self.item(item)), want, item)
        long_item = self.item("{date: 31 April, note: %s}" % ("x" * 100))
        self.assertEqual(len(readiness.refused_item(long_item).split(";")[0]), 60)
        for item in ("{date: 04-05, note: x}", "{date: 5 April}", "5 April", "{date: '04-05'}", '"04-05"'):
            self.assertIsNone(readiness.refused_item(self.item(item)), item)

    def test_a_date_is_its_first_ten_characters(self):
        days, _y, bad_days, _b, rendered, _r = readiness.frontmatter_dates(self.frontmatter(
            "deadline: 2030-05-01 (approx)\ndeadlines:\n  - 20250131\n  - \"2030-01-02\""))
        self.assertEqual((sorted(days), len(bad_days), sorted(rendered)),
                         (["2030-01-02", "2030-05-01"], 1, [("2030-01-02", ""), ("2030-05-01", "")]))

    OUT_OF_SCOPE = (
        ('  title: Tax\n  status: current', 'indented frontmatter'),
        ('a: b\n  c: d', 'a multi-line scalar or an indented block'),
        ('? complex\n: key', 'a `? ` key'),
        ('a: b\n...', 'a document end marker'),
        ('a: &x b', 'an anchor'),
        ('a: *x', 'an alias'),
        ('a: !!str b', 'a tag'),
        ('a: |\n  b', 'a block scalar'),
        ('a: >\n  b', 'a folded scalar'),
        ('a: b\n  c', 'a multi-line scalar or an indented block'),
        ('recurring:\n  - {date: 5 April,\n    note: x}', 'a flow mapping that does not close on its line'),
        ('recurring:\n  - {date: 5 April, note: a # b}', 'a comment inside a flow mapping'),
        ('status: "superseded"', 'a quoted status'),
        ('a: [b, c]', 'a flow sequence'),
        ('recurring:\n  - [a]', 'a flow sequence'),
        ('recurring:\n  - {a: {b: 1}}', 'a nested flow collection'),
        ('recurring:\n  - {a: [1]}', 'a nested flow collection'),
        ('recurring:\n  - {a: b [c]}', 'brackets in a plain scalar of a flow mapping'),
        ('a: b\n\tc: d', 'a tab for indentation'),
        ('%YAML 1.2\na: b', 'a directive'),
        ('"a": b', 'a key that is not a plain word'),
        ('my key: b', 'a line that is not a plain `key: value` pair'),
        ('a: b: c', 'a colon and space inside a plain scalar'),
        ('a: "b', 'an unclosed quote'),
        ('a: "b" c', 'text after a quoted scalar'),
        ('a: "b\\n"', 'an escape in a double-quoted scalar'),
        ('a: b\n- c', 'a block sequence that is not under a key'),
        ('a:\n  - b\n    - c', 'list items at different indents'),
        ('a:\n  - b\n - c', 'list items at different indents'),
        ('a:\n  -\n    b', 'an item on the lines after its dash'),
        ('a:\n  - - b', 'a nested list'),
        ('a:\n  - k: v\n      w: x', 'a nested block in a list item'),
        ('a:\n  - k:\n      v', 'a nested block in a list item'),
        ('a: - b', 'a block indicator inside a value'),
        ('a: b # c\nd: {e: f} g', 'text after a flow mapping'),
        ("a: " + "x" * 20001, "a line over 20000 characters"),
        ("a:\n  - {" + "''," * 7000 + "}", "a line over 20000 characters"),
        ('{a: b}', 'a key that is not a plain word'),
        ("a: b\n" + "c: d\n" * 40000, "frontmatter over 200000 characters"),
        ('a: {b: c', 'a flow mapping that does not close on its line'),
        ('a: {,}', 'an empty key in a flow mapping'),
        ('a: {b: c} d', 'text after a flow mapping'),
    ) + tuple(
        (block, "a plain value YAML reads as %s" % kind) for block, kind in (
            # a plain note, a block item's note, an extra key, the deadline note: YAML reads these as other than text
            ('recurring:\n  - {date: 04-05, note: yes}', 'bool'),
            ('recurring:\n  - {date: 04-05, note: Off}', 'bool'),
            ('recurring:\n  - {date: 04-05, note: n}', 'bool'),
            ('recurring:\n  - {date: 04-05, note: TRUE}', 'bool'),
            ('recurring:\n  - {date: 04-05, note: null}', 'null'),
            ('recurring:\n  - {date: 04-05, note: ~}', 'null'),
            ('recurring:\n  - {date: 04-05, note: 12}', 'number'),
            ('recurring:\n  - {date: 04-05, note: -3}', 'number'),
            ('recurring:\n  - {date: 04-05, note: 0x1F}', 'number'),
            ('recurring:\n  - {date: 04-05, note: 0b11}', 'number'),
            ('recurring:\n  - {date: 04-05, note: 0405}', 'number'),
            ('recurring:\n  - {date: 04-05, note: 1_000}', 'number'),
            ('recurring:\n  - {date: 04-05, note: 1.5}', 'number'),
            ('recurring:\n  - {date: 04-05, note: .5}', 'number'),
            ('recurring:\n  - {date: 04-05, note: .inf}', 'number'),
            ('recurring:\n  - {date: 04-05, note: 12:30}', 'time'),
            ('recurring:\n  - {date: 04-05, note: 1:20:30}', 'time'),
            ('recurring:\n  - {date: 04-05, note: 1:30.5}', 'time'),
            ('recurring:\n  - {date: 04-05, note: 2025-01-31}', 'date'),
            ('recurring:\n  - {date: 04-05, note: 2025-01-31 10:00:00}', 'date'),
            ('recurring:\n  - {date: 04-05, note: 2025-02-30}', 'date'),
            ('recurring:\n  - {date: 04-05, note: <<}', 'merge key'),
            ('recurring:\n  - {date: 04-05, note: =}', 'value'),
            ('recurring:\n  - date: 04-05\n    note: yes', 'bool'),
            ('recurring:\n  - {date: 04-05, note: x, extra: on}', 'bool'),
            ('deadline_note: 12:30', 'time'),
            ('deadline_note: no', 'bool'),
            ('deadlines:\n  - {date: 2030-01-01, note: 5}', 'number'),
            # a date field is read for the values it can be exactly; the rest is out of scope too
            ('recurring:\n  - {date: 0405}', 'number'),
            ('recurring:\n  - 12:30', 'time'),
            ('recurring:\n  - {date: .inf}', 'number'),
            ('recurring:\n  - {date: 2025-01-31 10:00:00}', 'date'),
            ('recurring:\n  - {date: y}', 'bool'),
            ('recurring:\n  - 0x1F', 'number'),
            ('deadline: 2030-01-01T10:00:00', 'date'),
            ('deadlines:\n  - 1_000', 'number'),
        ))

    def test_anything_outside_the_subset_is_named(self):
        for block, construct in self.OUT_OF_SCOPE:
            with self.subTest(block=block[:40]):
                with self.assertRaises(readiness.OutOfScope) as got:
                    self.frontmatter(block)
                self.assertEqual(str(got.exception), construct)

    def test_text_after_the_opening_fence_is_outside_the_subset(self):
        with self.assertRaises(readiness.OutOfScope) as got:
            readiness.read_frontmatter("--- text\na: b\n---\n")
        self.assertEqual(str(got.exception), "text after the opening fence")

    def test_a_frontmatter_the_roll_up_cannot_read_as_a_mapping_is_malformed(self):
        for text in ("---\nkey: v\nno fence closes", "---\n- a\n- b\n---\n", "---\n  - a\n---\n",
                     "---\njust text\n---\n", "---\nplain words\nmore words\n---\n"):
            with self.subTest(text=text[:30]):
                with self.assertRaises(readiness.Malformed):
                    readiness.read_frontmatter(text)

    def test_a_frontmatter_pyyaml_reads_is_never_malformed_here(self):
        """Whatever the subset does not read is outside it, never called malformed: the roll-up writes nothing for
        these pages, and a line saying it did would not be the roll-up's."""
        for text in ("---\n  title: Tax\n---\n", "---\n? a\n: b\n---\n", "---\na: b\n...\n---\n",
                     "---\n{a: b,\n c: d}\n---\n", "---\n\"a\": b\n---\n", "---\n&x a: b\n---\n",
                     "---\n!!map\na: b\n---\n",
                     "---\na: b\n---\n", "---\n# only a comment\n---\n", "---\n---\n# x"):
            with self.subTest(text=text[:30]):
                try:
                    readiness.read_frontmatter(text)
                except readiness.OutOfScope:
                    pass


class PlainScalarTest(unittest.TestCase):
    """A plain scalar PyYAML reads as anything but text is outside what the check reads: the roll-up writes the value
    it gives (`yes` is `True`), and the check has only the text."""

    # PyYAML's implicit resolvers, copied from `yaml/resolver.py` with their first characters, in its order; the
    # check's own patterns are not used, so this is a second reading of the same rule.
    PYYAML = (
        ("bool", "yYnNtTfFoO", r'''^(?:yes|Yes|YES|no|No|NO
                    |true|True|TRUE|false|False|FALSE
                    |on|On|ON|off|Off|OFF)$'''),
        ("float", "-+0123456789.", r'''^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?
                    |\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?
                    |[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*
                    |[-+]?\.(?:inf|Inf|INF)
                    |\.(?:nan|NaN|NAN))$'''),
        ("int", "-+0123456789", r'''^(?:[-+]?0b[0-1_]+
                    |[-+]?0[0-7_]+
                    |[-+]?(?:0|[1-9][0-9_]*)
                    |[-+]?0x[0-9a-fA-F_]+
                    |[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$'''),
        ("merge key", "<", r"^(?:<<)$"),
        ("null", "~nN", r'''^(?: ~
                    |null|Null|NULL
                    | )$'''),
        ("timestamp", "0123456789", r'''^(?:[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]
                    |[0-9][0-9][0-9][0-9] -[0-9][0-9]? -[0-9][0-9]?
                     (?:[Tt]|[ \t]+)[0-9][0-9]?
                     :[0-9][0-9] :[0-9][0-9] (?:\.[0-9]*)?
                     (?:[ \t]*(?:Z|[-+][0-9][0-9]?(?::[0-9][0-9])?))?)$'''),
        ("value", "=", r"^(?:=)$"),
    )
    NAMED = {"float": "number", "int": "number", "timestamp": "date"}

    @classmethod
    def pyyaml_kind(cls, text):
        """What PyYAML reads `text` as, in the check's words, None for text."""
        for tag, first, pattern in cls.PYYAML:
            if (text[:1] or "") in first + ("" if text else "~nN") and re.match(pattern, text, re.X):
                kind = cls.NAMED.get(tag, tag)
                return "time" if kind == "number" and ":" in text else kind

    @staticmethod
    def frontmatter(block):
        return readiness.read_frontmatter("---\n%s\n---\n# Page\n" % block)

    def scalar(self, text, own=False):
        """Raises what `check_plain` raises for the plain scalar `text`."""
        return readiness.check_plain(readiness.Scalar(text, False, text), own)

    def test_each_kind_is_the_one_pyyaml_resolves(self):
        for kind, texts in (("bool", ("yes", "No", "TRUE", "false", "On", "OFF", "y", "N", "Y", "n")),
                            ("null", ("null", "Null", "NULL", "~")),
                            ("number", ("12", "-3", "+4", "0", "007", "0405", "0x1F", "0b1", "1_000", "1.5", ".5",
                                        "5.", "-.inf", ".NaN", "1.0e+3")),
                            ("time", ("12:30", "1:20:30", "1:30.5", "-1:05")),
                            ("date", ("2025-01-31", "2025-1-5 1:02:03", "2025-01-31T10:00:00Z",
                                      "2025-01-31 10:00:00 +5")),
                            ("merge key", ("<<",)), ("value", ("=",))):
            for text in texts:
                with self.subTest(kind=kind, text=text):
                    self.assertEqual(readiness.plain_kind(text), kind)
                    self.assertEqual(self.pyyaml_kind(text) if text not in ("y", "N", "Y", "n") else "bool", kind)

    def test_text_pyyaml_keeps_as_text_is_not_a_kind(self):
        for text in ("04-05", "5 April", "1e3", "0o17", "Pay tax", "yes please", "12:30 sharp", "Null and void",
                     "2025-01-31 or later", "1:60", "08", "0x", "1.5.2", "-", "+", "..", "a=b", "<<x", "nope",
                     "Yesterday",
                     "ye", "tru", "5 %", "1,000", "June 1", "2025-01", "12:345"):
            with self.subTest(text=text):
                self.assertIsNone(readiness.plain_kind(text))
                self.assertIsNone(self.pyyaml_kind(text))

    def test_the_kind_is_pyyamls_over_every_short_string_of_the_characters_that_matter(self):
        pieces = ("0", "1", "7", "9", "-", "+", ".", ":", "_", "e", "E", "x", "b", "o", "T", "Z", " ", "n", "u", "l",
                  "y", "s", "f", "<", "=", "~", "2025", "-01", "-1", ":30", "yes", "No", "null", "ON")
        seen = set()
        for count in (1, 2, 3):
            for combo in itertools.product(pieces, repeat=count):
                text = "".join(combo)
                if text != text.strip():
                    continue
                want = self.pyyaml_kind(text)
                got = readiness.plain_kind(text)
                if got == "bool" and want is None and re.fullmatch(r"(?i:yes|no|true|false|on|off|y|n)", text):
                    got = None  # YAML 1.1's other spellings (`oN`, `y`): out of scope though PyYAML keeps text
                self.assertEqual(got, want, text)
                seen.add(want)
        self.assertEqual(seen, {None, "bool", "null", "number", "time", "date", "merge key", "value"})

    def test_the_other_spellings_of_yaml_one_one_are_out_of_scope_too(self):
        for text in ("y", "Y", "n", "N", "oN", "yES", "nO", "oFF", "TrUe"):
            with self.subTest(text=text):
                with self.assertRaises(readiness.OutOfScope):
                    self.frontmatter("recurring:\n  - {date: 04-05, note: %s}" % text)

    def test_a_note_that_is_not_text_is_out_of_scope_in_every_place_the_roll_up_writes_one(self):
        for block, kind in (("recurring:\n  - {date: 04-05, note: yes}", "bool"),
                            ("recurring:\n  - date: 04-05\n    note: ~", "null"),
                            ("recurring:\n  - {note: 5, date: 04-05}", "number"),
                            ("deadlines:\n  - {date: 2030-01-01, note: 12:30}", "time"),
                            ("deadline: 2030-01-01\ndeadline_note: 2025-01-31", "date"),
                            ("deadline: 2030-01-01\ndeadline_note: off", "bool"),
                            ("recurring:\n  - {date: 04-05, note: Annual, extra: yes}", "bool")):
            with self.subTest(block=block):
                with self.assertRaises(readiness.OutOfScope) as got:
                    self.frontmatter(block)
                self.assertEqual(str(got.exception), "a plain value YAML reads as %s" % kind)

    def test_a_quoted_scalar_is_text_whatever_it_holds(self):
        for text in ('"yes"', "'12:30'", '"null"', "'2025-01-31'", '"5"', '"~"', '""', "'<<'", "'y'"):
            with self.subTest(text=text):
                fm = self.frontmatter("recurring:\n  - {date: 04-05, note: %s}" % text)
                note = readiness.date_entry(fm["recurring"][0])[1]
                self.assertEqual(note, text[1:-1] or None)

    def test_a_plain_note_that_only_begins_like_one_is_text(self):
        for text in ("yes please", "12:30 sharp", "Null and void", "No, thanks", "5 instalments", "~tilde", "on time"):
            with self.subTest(text=text):
                fm = self.frontmatter("recurring:\n  - {date: 04-05, note: %s}" % text.replace(",", "\\,"))
                self.assertIsNotNone(readiness.date_entry(fm["recurring"][0])[1])

    def test_a_frontmatter_the_roll_up_does_not_write_is_not_judged(self):
        for line in ("title: yes", "owner: null", "count: 5", "when: 12:30", "status: current", "on: off"):
            with self.subTest(line=line):
                self.assertIn(line.split(":")[0], self.frontmatter("%s\nrecurring:\n  - {date: 04-05, note: A}" % line))

    def test_a_date_keeps_its_own_reading_for_what_it_can_give_exactly(self):
        """The roll-up refuses these as a recurring date, and says the value it read: so does the check."""
        hint = readiness.DATE_HINT
        for item, shown in (("{date: yes, note: x}", "{'date': True, 'note': 'x'}"),
                            ("{date: no}", "{'date': False}"),
                            ("{date: null, note: why}", "{'date': None, 'note': 'why'}"),
                            ("{date: 5, note: z}", "{'date': 5, 'note': 'z'}"), ("{date: 6.4}", "{'date': 6.4}"),
                            ("~", "None"), ("no", "False"), ("2025-01-31", "datetime.date(2025, 1, 31)"),
                            ("{date: 2025-01-31, note: w}", "{'date': datetime.date(2025, 1, 31), 'note': 'w'}")):
            with self.subTest(item=item):
                fm = self.frontmatter("recurring:\n  - %s" % item)
                self.assertEqual(readiness.refused_item(fm["recurring"][0]), shown + hint)
        fm = self.frontmatter("deadline: 2030-05-01\ndeadlines:\n  - 2030-06-01\n  - ~")
        self.assertEqual((fm["deadline"].text, [x.text for x in fm["deadlines"]]), ("2030-05-01", ["2030-06-01", "~"]))

    def test_a_date_pyyaml_cannot_build_is_malformed_wherever_a_date_is_read(self):
        for block in ("recurring:\n  - {date: 2025-02-30, note: x}", "recurring:\n  - 2025-02-30",
                      "deadline: 2025-02-30", "deadlines:\n  - 2025-13-01", "recurring:\n  - {date: 2025-00-10}"):
            with self.subTest(block=block):
                with self.assertRaises(readiness.Malformed):
                    self.frontmatter(block)

    def test_a_date_in_a_form_the_check_cannot_give_exactly_is_still_out_of_scope(self):
        for block, kind in (("recurring:\n  - {date: 0x1F}", "number"), ("recurring:\n  - {date: 12:30}", "time"),
                            ("recurring:\n  - {date: 2025-01-31 10:00:00}", "date"), ("deadline: 1_000", "number"),
                            ("recurring:\n  - .inf", "number"), ("deadlines:\n  - <<", "merge key")):
            with self.subTest(block=block):
                with self.assertRaises(readiness.OutOfScope) as got:
                    self.frontmatter(block)
                self.assertEqual(str(got.exception), "a plain value YAML reads as %s" % kind)

    def test_an_empty_plain_value_is_no_value(self):
        fm = self.frontmatter("recurring:\n  - {date: 04-05, note: }\ndeadline_note:\ndeadline:")
        self.assertEqual(readiness.date_entry(fm["recurring"][0]), ("04-05", None))
        self.assertIsNone(fm["deadline"])


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

    def test_a_line_is_expected_as_many_times_as_the_roll_up_writes_it(self):
        """The same refused item twice on a page is two lines, so a third is hand-written."""
        item = ("- 30 Home/Bad.md (unreadable recurring date: {'date': '31 April', 'note': 'nonsense'}%s)"
                % readiness.DATE_HINT)
        self.assertEqual(self.page("refused")[0], "ok")
        dated, _recurring = self.reported(self.replace(item + "\n", item + "\n" + item + "\n"), "refused")
        self.assertIn(HAND, dated)
        self.assertIn("1 line(s)", dated)

    BROKEN = "- 10 Identity/Broken.md (malformed frontmatter)"
    FIXED = "---\nprovenance: derived\nlast-updated: 2024-06-30\nstatus: current\n---\n# Broken\n"

    def test_a_line_for_a_page_since_repaired_is_reported(self):
        """The page now reads, so the roll-up would not list it: the old line is hand-kept, not the roll-up's."""
        wiki = self.wiki("could-not-read")
        write(os.path.join(wiki, "10 Identity", "Broken.md"), self.FIXED)
        self.assertIn(self.BROKEN, read(os.path.join(wiki, PAGE)))
        self.assertIn(HAND, self.check(wiki)[0])
        wiki = self.wiki("could-not-read")
        write(os.path.join(wiki, "30 Home", "Bad.md"), "---\nrecurring:\n  - {date: 04-06, note: Fixed}\n---\n# Page\n")
        dated, recurring, _other = self.check(wiki)
        self.assertIn(HAND, dated)
        self.assertIn("lacks 1 recurring date(s) (04-06 (30 Home/Bad.md))", recurring)

    def test_a_listed_page_the_roll_up_page_does_not_list_is_an_incomplete_page(self):
        """The page cannot be read, the roll-up would say so, and the page was never regenerated."""
        wiki = self.wiki("could-not-read")
        path = os.path.join(wiki, PAGE)
        write(path, read(path).replace(self.BROKEN + "\n", ""))
        dated, recurring, _other = self.check(wiki)
        self.assertIn("%s lacks 1 line(s) of the roll-up's \"Could not read\" list that the pages give "
                      "(10 Identity/Broken.md (malformed frontmatter))" % readiness.DEADLINES, dated)
        self.assertNotIn(HAND, dated)
        self.assertTrue(recurring.startswith("finding: 3 recurring"), recurring)

    def test_a_page_under_a_dot_folder_the_roll_up_cannot_read_is_expected_in_the_list(self):
        wiki = self.wiki("plain")
        os.makedirs(os.path.join(wiki, ".trash"))
        with open(os.path.join(wiki, ".trash", "Broken.md"), "wb") as f:
            f.write(b"\xff\xfe")
        line = ".trash/Broken.md (unreadable: UnicodeDecodeError)"
        self.assertIn("lacks 1 line(s) of the roll-up's \"Could not read\" list that the pages give (%s)" % line,
                      self.check(wiki)[0])
        path = os.path.join(wiki, PAGE)
        write(path, read(path) + "\n## Could not read\n\n%s\n\n- %s\n" % (readiness.UNREAD_INTRO, line))
        self.assertEqual(self.check(wiki), ("ok", "ok", "ok"))

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


class OutOfScopeTest(Scenario):
    """A page whose frontmatter uses YAML outside the subset is named as not verified: never a finding, never clean."""

    PAGE_NAME = "30 Home/Insurance.md"

    def outside(self, block, scenario="plain", change=None):
        """The result for the scenario's wiki with the page's frontmatter replaced by `block`."""
        wiki = self.wiki(scenario)
        write(os.path.join(wiki, *self.PAGE_NAME.split("/")), "---\n%s\n---\n# Insurance\n" % block)
        if change:
            path = os.path.join(wiki, PAGE)
            write(path, change(read(path)))
        return self.full(wiki)

    def named(self, construct):
        return ["not verified: %s uses YAML this check does not read (%s)" % (self.PAGE_NAME, construct)]

    def test_each_construct_is_named_and_the_roll_up_is_neither_failed_nor_passed(self):
        for block, construct in GrammarTest.OUT_OF_SCOPE:
            with self.subTest(construct=construct, block=block[:30]):
                dated, recurring, other, outside = self.outside(block)
                self.assertEqual(outside, self.named(construct))
                self.assertEqual((dated, recurring, other), ("ok", "ok", "ok"))  # not a finding

    def test_the_lines_outside_the_roll_ups_grammar_are_still_reported(self):
        _dated, _recurring, _other, outside = self.outside("a: &x b", change=self.append("| 5 | April |"))
        self.assertEqual(outside, self.named("an anchor"))
        dated = self.outside("a: &x b", change=self.append("| 5 | April |"))[0]
        self.assertIn("hand-written content in a derived page, 1 line(s)", dated)
        dated = self.outside("a: &x b", change=self.replace("**12 May** %s Insurance %s Ask Alex" % (EM, EM),
                                                          "**12 May** %s Insurance %s Ask Robin" % (EM, EM)))[0]
        self.assertEqual(dated, "ok")  # whether an entry is backed needs the page, so it is withheld
        _d, recurring, _o, _out = self.outside("a: &x b", change=self.replace("**12 May**", "**13 May**"))
        self.assertEqual(recurring, "ok")
        dated = self.outside("a: &x b", change=self.replace("**2030-05-01**", "**2030-05-02**"))[0]
        self.assertNotIn("no current page's frontmatter carries", dated)  # which pages carry it is not known
        self.assertIn("lacks 1 page deadline(s) (2030-05-01 (20 Finance/Tax.md))", dated)  # a page that is read
        dated = self.outside("a: &x b", change=self.replace("**12 May**", "**05-12**"))[0]
        self.assertIn(HAND, dated)  # a date in a form the roll-up does not write needs no page
        _d, recurring, _o, _out = self.outside("a: &x b", change=self.replace("**12 May**", "**5-May**"))
        self.assertIn("unreadable yearly date", recurring)

    def test_the_could_not_read_list_is_not_judged_while_a_page_is_unread(self):
        change = self.replace("## Past\n", "## Past\n\n## Could not read\n\n"
                              "- 20 Finance/Tax.md (unreadable: Whatever)\n")
        dated, _recurring, _other, outside = self.outside("a: &x b", change=change)
        self.assertEqual((dated, len(outside)), ("ok", 1))
        dated = self.outside("a: b", change=change)[0]  # every page read: the line is not the roll-up's
        self.assertIn(HAND, dated)

    def test_a_page_named_once_for_the_first_construct_it_uses(self):
        _d, _r, _o, outside = self.outside("a: &x b\nc: *x\nd: !!str e")
        self.assertEqual(outside, self.named("an anchor"))

    def test_a_banner_is_judged_by_its_place_alone_while_a_page_is_unread(self):
        text = read(os.path.join(ROLLUPS, "banner", PAGE))
        banner_line = next(x for x in text.split("\n") if x.startswith("> **Roll-up"))
        change = self.replace("_File-derived deadlines", banner_line + "\n\n_File-derived deadlines")
        self.assertEqual(self.outside("a: &x b", "plain", change)[0], "ok")  # the entries it needs are not known
        self.assertIn(HAND, self.outside("a: b", "plain", change)[0])  # every page read: entries exist
        below = self.replace("## Upcoming\n\n", "## Upcoming\n\n" + banner_line + "\n\n")
        self.assertIn(HAND, self.outside("a: &x b", "plain", below)[0])  # below a heading: not its place

    def test_a_page_the_roll_up_never_reads_is_not_named(self):
        for name in ("30 Home/Insurance.superseded.md", "30 Home/Insurance.proposed.md", "02 Home/Index.md",
                     "01 Deadlines/Log.md"):
            wiki = self.wiki("plain")
            os.makedirs(os.path.dirname(os.path.join(wiki, *name.split("/"))), exist_ok=True)
            write(os.path.join(wiki, *name.split("/")), "---\na: &x b\n---\n")
            self.assertEqual(self.full(wiki), ("ok", "ok", "ok", []), name)


class HiddenPageTest(Scenario):
    """The roll-up reads every `.md` under the wiki folder, dot folders and dot files included, and no `.superseded.md`
    or `.proposed.md` sibling."""

    def test_a_page_under_a_dot_folder_is_a_source(self):
        dated, recurring = self.reported(self.replace(
            "- **6 April** %s Old %s Deleted note ([.trash/Old](../.trash/Old.md))\n" % (EM, EM), ""), "hidden")
        self.assertIn("lacks 1 recurring date(s) (04-06 (.trash/Old.md))", recurring)

    def test_a_sibling_is_not_a_source(self):
        entry = "- **9 September** %s Tax %s Before the edit ([20 Finance/Tax](../20%%20Finance/Tax.md))\n" % (EM, EM)
        _dated, recurring = self.reported(self.replace("## Every year\n\n", "## Every year\n\n" + entry), "hidden")
        self.assertIn("no page's recurring: list carries (line", recurring)

    def test_a_date_only_a_sibling_holds_is_not_a_page_deadline(self):
        dated, recurring, _other, _outside = self.full(self.wiki("hidden"))
        self.assertEqual((dated, recurring), ("ok", "ok"))  # 2031-01-01 and 2032-01-01 are not required of the roll-up


class UnreadablePageTest(Scenario):
    """One page that cannot be read does not stop the check."""

    def test_the_check_goes_on(self):
        wiki = self.wiki("plain")
        with open(os.path.join(wiki, "20 Finance", "Binary.md"), "wb") as f:
            f.write(b"\xff\xfe")
        dated, recurring, other = self.check(wiki)
        self.assertIn("lacks 1 line(s) of the roll-up's \"Could not read\" list that the pages give "
                      "(20 Finance/Binary.md (unreadable: UnicodeDecodeError))", dated)
        self.assertEqual((recurring, other), ("ok", "ok"))  # the other checks ran


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
              "5 April" + " " * 100000 + "x", "{note: " + ", " * 50000 + "}",
              "{" + "'', " * 400000 + "}", "{" + '"", ' * 400000 + "}", "{date: 04-05, note: " + "'x', " * 320000 + "}",
              "'" + "''" * 800000 + "'", "{" + "'a': 'b', " * 160000 + "}")

    def test_many_quoted_scalars_within_the_cap_are_read_in_one_pass(self):
        """The reader scans in place: a flow mapping of 4,000 quoted scalars is read, not copied 4,000 times."""
        item = "{" + "'', " * 4000 + "'a': \"b\"}"
        start = time.perf_counter()
        got = readiness.read_frontmatter("---\nrecurring:\n  - %s\n---\n" % item)
        self.assertLess(time.perf_counter() - start, 0.2)
        self.assertEqual(list(got["recurring"][0]), ["", "a"])
        start = time.perf_counter()
        value, end = readiness.quoted("'" + "''" * 9000 + "'", 0)
        self.assertLess(time.perf_counter() - start, 0.2)
        self.assertEqual((value, end), ("'" * 9000, 18002))

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
