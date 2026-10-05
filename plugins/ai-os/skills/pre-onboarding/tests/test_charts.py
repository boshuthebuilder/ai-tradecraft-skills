"""`wiki.py chart`: golden output per chart kind, the refusals, the render probe page and the checker's chart pairing.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests
    python3 test_charts.py --update      rewrite golden/charts/<kind>.md and probe/render-probe.md (commit with why)

Golden inputs are in golden/charts/ and cite files in the fixture folder, which each chart is rendered against (the
tool refuses a source that does not exist). The fixture wiki carries the same charts, except the synthetic line
(golden/charts/README.md says why), so its pages are checked here to hold the tool's output verbatim.
"""
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
TIMEOUT = 600  # seconds: a tool that hangs fails its test instead of the run
FIXTURE = os.path.join(HERE, "fixture", "Alex Personal")
WIKI = os.path.join(FIXTURE, "Alex Personal Wiki")
GOLDEN = os.path.join(HERE, "golden", "charts")
PROBE = os.path.join(HERE, "probe", "render-probe.md")
sys.path.insert(0, TOOLS)
import common  # noqa: E402
import wiki  # noqa: E402

CASES = [  # kind, golden input, title, the fixture wiki page that carries the chart (None: synthetic input)
    ("bar", "bar.csv", "Current account, March 2024 (GBP)", "20 Finance/Bank accounts.md"),
    ("line", "line.json", "Synthetic line series (tool input, not fixture data)", None),
    ("pie", "pie.csv", "Planned monthly spending (GBP)", "20 Finance/Cash position.md"),
    ("gantt", "gantt.json", "Passport validity", "10 Identity/10 Identity.md"),
    ("timeline", "timeline.csv", "Home", "30 Home/30 Home.md"),
]
FIXTURE_CHARTS = len([c for c in CASES if c[3]])
PROBE_HEAD = """# Render probe

One chart of each kind `wiki.py chart` renders, each followed by its data table, and one callout, its marker alone on its line. Open
this page in each Markdown app the wiki will be read in. For every section, note whether the chart draws, whether
its labels, values and dates read as in the table under it, and anything clipped or misplaced. A kind that does not
draw in every app is taken out of the tool. The page is generated: `tests/test_charts.py --update` rewrites it from
the golden inputs in `tests/golden/charts/`, and a test fails when it differs from the tool's output.

> [!note]
> **Callout.** A box in Obsidian and in Typora. The marker stands alone on its line: Typora prints it as text when
> anything follows it there.
"""


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def run(tool, *args):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, tool)] + list(args), capture_output=True, text=True,
                       encoding="utf-8", timeout=TIMEOUT)
    return r.returncode, r.stdout, r.stderr


def probe_text(outputs):
    return PROBE_HEAD + "".join("\n## %s\n\n%s" % (kind, outputs[kind]) for kind, _data, _title, _page in CASES)


class Charts(unittest.TestCase):
    """One copy of the fixture for the class (the tool only reads it); each test writes its data in its own dir."""
    SRC = "02 Finance/Bank statement 2024-03.pdf"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="charts_test_")
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        cls.root = os.path.join(cls.tmp, "Alex Personal")
        shutil.copytree(FIXTURE, cls.root)
        cls.work = os.path.join(cls.tmp, "work")

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="data_", dir=self.tmp)

    def chart(self, kind, data, title, *extra, root=None):
        return run("wiki.py", "chart", "--root", root or self.root, "--work", self.work, "--read-only-root",
                   "--kind", kind, "--data", data, "--title", title, *extra)

    def rendered(self, kind, data, title, root=None):
        code, out, err = self.chart(kind, data, title, root=root)
        self.assertEqual((code, err), (0, ""), err)
        return out

    def data(self, name, rows):
        """A data file of `rows`: a list of dicts written as JSON, or a list of lists (header first) as CSV."""
        path = os.path.join(self.dir, name)
        if isinstance(rows, str):
            write(path, rows)
        elif name.endswith(".json"):
            write(path, json.dumps(rows, ensure_ascii=False))
        else:
            text = io.StringIO()
            csv.writer(text, lineterminator="\n").writerows(rows)
            write(path, text.getvalue())
        return path

    def rows(self, *points, unit="GBP", key="label", src=None):
        """CSV rows (header first, so data starts on line 2) of a series: `points` are (label or period, value)."""
        return [[key, "value", "unit", "source"]] + [[p, v, unit, src or self.SRC] for p, v in points]

    def raw_json(self, *values):
        """JSON text of a series labelled a, b, c..., each value written raw (a number as its literal)."""
        return "[%s]" % ", ".join('{"label": "%s", "value": %s, "unit": "GBP", "source": "%s"}'
                                  % (chr(97 + i), v, self.SRC) for i, v in enumerate(values))

    def refused(self, kind, name, rows, title, *expected, root=None):
        code, out, err = self.chart(kind, self.data(name, rows), title, root=root)
        self.assertEqual(code, 2, (out, err))
        self.assertEqual(out, "")
        for text in expected:
            self.assertIn(text, err)
        return err

    def own_copy(self):
        root = os.path.join(self.dir, "Alex Personal")
        shutil.copytree(FIXTURE, root)
        return root


class GoldenTest(Charts):
    def test_golden_per_kind(self):
        for kind, data, title, _page in CASES:
            with self.subTest(kind=kind):
                self.assertEqual(self.rendered(kind, os.path.join(GOLDEN, data), title),
                                 read(os.path.join(GOLDEN, kind + ".md")))

    def test_byte_identical_and_format_independent(self):
        """The same rows give the same bytes: run twice, and as CSV or as JSON."""
        for kind, data, title, _page in CASES:
            with self.subTest(kind=kind):
                path = os.path.join(GOLDEN, data)
                first = self.rendered(kind, path, title)
                self.assertEqual(self.rendered(kind, path, title), first)
                rows, _places = wiki.chart_rows(path)
                other = (self.data(kind + ".csv", [list(rows[0])] + [list(r.values()) for r in rows])
                         if data.endswith(".json") else self.data(kind + ".json", rows))
                self.assertEqual(self.rendered(kind, other, title), first)

    def test_byte_order_mark_is_not_data(self):
        for kind, data, title, _page in (CASES[0], CASES[1]):  # one CSV, one JSON
            with self.subTest(kind=kind):
                path = self.data("bom" + os.path.splitext(data)[1], "﻿" + read(os.path.join(GOLDEN, data)))
                self.assertEqual(read(path, "rb")[:3], b"\xef\xbb\xbf")
                self.assertEqual(self.rendered(kind, path, title), read(os.path.join(GOLDEN, kind + ".md")))

    def test_fixture_pages_carry_the_tool_output(self):
        for kind, _data, _title, page in CASES:
            if page:
                with self.subTest(kind=kind):
                    self.assertIn(read(os.path.join(GOLDEN, kind + ".md")), read(os.path.join(WIKI, page)))

    def test_probe_page_is_the_tool_output(self):
        outputs = {kind: self.rendered(kind, os.path.join(GOLDEN, data), title) for kind, data, title, _p in CASES}
        self.assertEqual(read(PROBE), probe_text(outputs))
        self.assertIn("\n> [!note]\n", read(PROBE))

    def test_out_writes_the_same_bytes_and_respects_read_only_root(self):
        kind, data, title, _page = CASES[0]
        out = os.path.join(self.dir, "chart.md")
        code, printed, err = self.chart(kind, os.path.join(GOLDEN, data), title, "--out", out)
        self.assertEqual(code, 0, err)
        self.assertEqual(read(out), printed)
        inside = os.path.join(self.root, "chart.md")
        code, _out, err = self.chart(kind, os.path.join(GOLDEN, data), title, "--out", inside)
        self.assertEqual(code, 2)
        self.assertIn("--read-only-root", err)
        self.assertFalse(os.path.exists(inside))


class ShapeTest(Charts):
    def test_values_and_row_order_kept_exactly(self):
        out = self.rendered("bar", self.data("v.json", self.raw_json("1450.50", "0.10", '"-3.000"', "7")), "t")
        self.assertIn('    y-axis "GBP"\n    bar [1450.50, 0.10, -3.000, 7]\n', out)  # a negative: no fixed range
        self.assertIn("| a | 1450.50 |", out)
        self.assertIn("| c | -3.000 |", out)

    def test_y_axis_from_zero_to_the_largest_value(self):
        out = self.rendered("line", self.data("l.csv", self.rows(("2024-01", "3"), ("2024-02", "12.5"),
                                                                ("2024-03", "12.50"), key="period")), "Line")
        self.assertIn('    y-axis "GBP" 0 --> 12.5\n    line [3, 12.5, 12.50]\n', out)
        self.assertIn("| Period | Value (GBP) | Source |\n| --- | ---: | --- |\n| 2024-01 | 3 |", out)

    def test_bar_by_period(self):
        out = self.rendered("bar", self.data("p.csv", self.rows(("2021-22", "36000"), ("2022-23", "38400"),
                                                               ("2023-24", "39100"), key="period")), "Income (GBP)")
        self.assertIn('x-axis ["2021-22", "2022-23", "2023-24"]', out)
        self.assertIn("| Period | Value (GBP) | Source |", out)

    def test_version_numbers_are_not_dates(self):
        out = self.rendered("bar", self.data("v.csv", self.rows(("v1.2.34", "1"), ("v1.3.0", "2"), ("40.50.60", "3"))),
                            "Releases, March 2024")
        self.assertIn('x-axis ["v1.2.34", "v1.3.0", "40.50.60"]', out)

    def test_gantt_sections_keep_row_order(self):
        rows = [["section", "label", "start", "end", "source"],
                ["Home", "Lease", "2024-05-01", "2025-04-30", "03 Home/Lease renewal.pdf"],
                ["Home", "Old lease", "2023-05-01", "2024-04-30", "03 Home/Lease renewal.pdf"],
                ["Identity", "Passport", "2021-07-15", "2031-07-15", "01 Identity/Passport scan.pdf"],
                ["Home", "Notes", "2024-06-01", "2024-06-01", "03 Home/Lease notes .txt"]]
        out = self.rendered("gantt", self.data("g.csv", rows), "Terms")
        self.assertEqual(out.split("\n```\n")[0], "\n".join([
            "```mermaid", "gantt", "    title Terms", "    dateFormat YYYY-MM-DD", "    section Home",
            "    Lease :2024-05-01, 2025-04-30", "    Old lease :2023-05-01, 2024-04-30", "    section Identity",
            "    Passport :2021-07-15, 2031-07-15", "    section Home", "    Notes :2024-06-01, 2024-06-01"]))
        self.assertIn("| Home | Notes | 2024-06-01 | 2024-06-01 | `03 Home/Lease notes .txt` |\n", out)
        plain = self.rendered("gantt", self.data("g2.csv", [r[1:] for r in rows]), "Terms")
        self.assertNotIn("section", plain)
        self.assertIn("| Label | Start | End | Source |", plain)

    def test_gantt_keywords_are_case_sensitive_and_folders_are_sources(self):
        rows = [["label", "start", "end", "source"],
                ["Title deed", "2021-05-02", "2021-05-02", "01 Identity/Passport renewal 2021/"],
                ["Section work", "2024-01-01", "2024-02-01", "04 Study"]]
        out = self.rendered("gantt", self.data("k.csv", rows), "Packs")
        self.assertIn("    Title deed :2021-05-02, 2021-05-02\n    Section work :2024-01-01, 2024-02-01\n", out)
        self.assertIn("`01 Identity/Passport renewal 2021/` |", out)

    def test_timeline_rows_with_one_date_share_a_line(self):
        rows = [["date", "label", "source"], ["2024-03-15", "Bill", "03 Home/Utilities /Electricity bill.pdf"],
                ["2024-03-15", "Meter read", "03 Home/Utilities /Electricity bill.pdf"],
                ["2024-05-01", "Lease renewed", "03 Home/Lease renewal.pdf"],
                ["2024-03-15", "Paid", "03 Home/Utilities /Electricity bill.pdf"]]
        out = self.rendered("timeline", self.data("t.csv", rows), "Home")
        self.assertIn("    2024-03-15 : Bill : Meter read\n    2024-05-01 : Lease renewed\n    2024-03-15 : Paid\n```\n",
                      out)
        self.assertEqual(out.count("| 2024-03-15 |"), 3)


class RefusalTest(Charts):
    """Every refusal exits 2, prints nothing on stdout and names the row (`line N` of a CSV file, the header on line
    1; `row N` of a JSON array) or the argument that broke the rule."""

    def test_no_source(self):
        self.refused("bar", "a.csv", [["label", "value", "unit"], ["a", "1", "GBP"], ["b", "2", "GBP"],
                                      ["c", "3", "GBP"]], "t", "a.csv: no source column")
        rows = self.rows(("a", "1"), ("b", "2"), ("c", "3"))
        rows[2][3] = ""
        self.refused("bar", "b.csv", rows, "t", "b.csv line 3: no source")
        self.refused("pie", "c.json", [{"label": "a", "value": "1", "unit": "GBP", "source": self.SRC},
                                       {"label": "b", "value": "2", "unit": "GBP"},
                                       {"label": "c", "value": "3", "unit": "GBP", "source": self.SRC}],
                     "t (GBP)", "c.json row 2: columns")

    def test_csv_lines_count_blank_lines(self):
        text = "label,value,unit,source\n\na,1,GBP,{0}\n\nb,,GBP,{0}\nc,3,GBP,{0}\n".format(self.SRC)
        self.refused("bar", "n.csv", text, "t", "n.csv line 5: value '' is not a plain decimal")

    def test_source_must_be_a_folder_file(self):
        for src, why in (("02 Finance/Missing.pdf", "does not exist"), ("/etc/hosts", "not a folder-relative"),
                         ("../Alex Personal/CLAUDE.md", "not a folder-relative"),
                         ("02 Finance//Bank statement 2024-03.pdf", "not a folder-relative")):
            with self.subTest(src=src):
                self.refused("bar", "s.csv", self.rows(("a", "1"), ("b", "2"), ("c", "3"), src=src), "t",
                             "s.csv line 2: source %r" % src, why)

    def test_source_stays_inside_the_folder_and_off_reserved_names(self):
        root = self.own_copy()
        outside = os.path.join(self.dir, "outside")
        write(os.path.join(outside, "hosts.txt"), "not the folder's\n")
        os.symlink(outside, os.path.join(root, "escape"))
        os.symlink(os.path.join(root, "_Audit"), os.path.join(root, "data"))
        write(os.path.join(root, "_Inbox", "scan.txt"), "waiting to be filed\n")
        for src, why in (("escape/hosts.txt", "outside"), ("data/wiki-rationale.md", "under _Audit"),
                         ("_Audit/wiki-rationale.md", "under _Audit"), (".familyai/rulebook.json", "under .familyai"),
                         ("Alex Personal Wiki/10 Identity/10 Identity.md", "under Alex Personal Wiki"),
                         ("_Migrations/Other Project/02 Finance/Old invoice.pdf", "under _Migrations"),
                         ("CLAUDE.md", "under CLAUDE.md"), ("_Inbox/scan.txt", "under _Inbox"),
                         ("_Inbox/", "under _Inbox")):
            with self.subTest(src=src):
                self.refused("bar", "r.csv", self.rows(("a", "1"), ("b", "2"), ("c", "3"), src=src), "t",
                             "r.csv line 2: source %r" % src, why, root=root)

    def test_a_source_the_owner_excluded_is_refused(self):
        root = self.own_copy()
        for sub in ("extract", "cards"):  # the tool runs read-only, and refuses to purge the records of excluded documents
            shutil.rmtree(os.path.join(root, "_Audit", sub))
        twin = os.path.join(root, ".familyai", "rulebook.json")
        write(twin, json.dumps(dict(json.loads(read(twin)), exclude=["02 Finance/Tax", "02 Finance/Bank statement 2024-03.pdf"]),
                               ensure_ascii=False, indent=1))
        for src in ("02 Finance/Tax", "02 Finance/Tax/", "02 Finance/Tax/Tax return 2023.pdf",
                    "02 Finance/Bank statement 2024-03.pdf"):
            with self.subTest(src=src):
                err = self.refused("bar", "x.csv", self.rows(("a", "1"), ("b", "2"), ("c", "3"), src=src), "t",
                                   "x.csv line 2: source %r" % src, "which the folder reserves or the owner excluded "
                                   "from reading", root=root)
                self.assertNotIn("Traceback", err)
        self.assertIn("(GBP)", self.rendered("bar", self.data("ok.csv", self.rows(
            ("a", "1"), ("b", "2"), ("c", "3"), src="02 Finance/Bank statement 2024-03 (1).pdf")), "t (GBP)", root=root))

    def test_a_source_is_compared_to_the_reserved_names_as_a_name_is_on_disk(self):
        """A reserved name and a source that differ only in letter case or in Unicode form are one path: as `common.fold`
        compares them, not by `casefold` alone, which leaves a composed and a decomposed accent apart."""
        root = os.path.realpath(self.own_copy())
        accented = "05 Archive/Cours de fran\u00e7ais.pdf"
        self.assertTrue(os.path.exists(os.path.join(root, accented)))
        for reserved in ("05 ARCHIVE/COURS DE FRAN\u00c7AIS.PDF", unicodedata.normalize("NFD", accented),
                         "05 archive/"):
            with self.subTest(reserved=reserved):
                with self.assertRaises(common.ToolError) as caught:
                    wiki.chart_source(root, accented, "x.csv line 2", [reserved])
                self.assertIn("which the folder reserves or the owner excluded from reading", str(caught.exception))
        wiki.chart_source(root, accented, "x.csv line 2", ["05 Archive/Cours de fran\u00e7ais.pdf2"])

    def test_a_series_needs_three_points(self):
        for kind, key in (("bar", "label"), ("line", "period"), ("pie", "label")):
            with self.subTest(kind=kind):
                self.refused(kind, "n.csv", self.rows(("a", "1"), ("b", "2"), key=key), "t (GBP)",
                             "a %s series needs at least three points, not 2" % kind)

    def test_units_labelled(self):
        self.refused("bar", "u.csv", [["label", "value", "source"], ["a", "1", self.SRC]], "t",
                     "a bar chart needs exactly one 'unit' column")
        self.refused("line", "u.csv", self.rows(("2024-01", "1"), ("2024-02", "2"), ("2024-03", "3"), unit="",
                                                key="period"), "t", "u.csv line 2: no unit")
        rows = self.rows(("a", "1"), ("b", "2"), ("c", "3"))
        rows[3][2] = "EUR"
        self.refused("bar", "u.csv", rows, "t", "u.csv line 4: unit 'EUR' differs from the first row's 'GBP'")
        for title in ("Spending", "Spending GBPX", "Spending (xGBP)"):
            with self.subTest(title=title):
                self.refused("pie", "u.csv", self.rows(("a", "1"), ("b", "2"), ("c", "3")), title,
                             "must name the unit 'GBP' as a word")
        self.rendered("pie", self.data("w.csv", self.rows(("a", "1"), ("b", "2"), ("c", "3"))), "Spending in GBP")

    def test_periods_labelled(self):
        self.refused("line", "p.csv", self.rows(("a", "1"), ("b", "2"), ("c", "3")), "t",
                     "a line chart needs exactly one 'period' column")
        self.refused("line", "p.csv", self.rows(("2024-01", "1"), ("", "2"), ("2024-03", "3"), key="period"), "t",
                     "p.csv line 3: no period")
        self.refused("bar", "p.csv", [["label", "period", "value", "unit", "source"]], "t",
                     "p.csv: no rows")
        self.refused("bar", "p.csv", [["label", "period", "value", "unit", "source"],
                                      ["a", "2024", "1", "GBP", self.SRC]], "t",
                     "a bar chart needs exactly one 'label' or 'period' column")

    def test_dates_are_iso(self):
        g = [["label", "start", "end", "source"]]
        src = "01 Identity/Passport scan.pdf"
        self.refused("gantt", "d.csv", g + [["P1", "15/07/2021", "2031-07-15", src]], "t",
                     "d.csv line 2: start '15/07/2021' is not a date written YYYY-MM-DD")
        self.refused("gantt", "d.csv", g + [["P1", "2021-07-15", "2031-02-30", src]], "t",
                     "d.csv line 2: end '2031-02-30' is not a date")
        self.refused("gantt", "d.csv", g + [["P1", "2031-07-15", "2021-07-15", src]], "t",
                     "d.csv line 2: ends 2021-07-15, before it starts 2031-07-15")
        self.refused("timeline", "d.csv", [["date", "label", "source"], ["2024-5-1", "Lease", src]], "t",
                     "d.csv line 2: date '2024-5-1' is not a date written YYYY-MM-DD")
        for text in ("1/2/24", "01.02.2024", "2 Mar 2024", "March 2, 2024", "12th of March 2024", "2024/03/01"):
            with self.subTest(text=text):
                self.refused("timeline", "d.csv", [["date", "label", "source"], ["2024-05-01", "Due " + text, src]],
                             "t", "d.csv line 2: label 'Due %s' holds the date %r" % (text, text))
        self.refused("line", "d.csv", self.rows(("01/03/2024", "1"), ("2024-03-15", "2"), ("2024-03-31", "3"),
                                                key="period"), "t",
                     "d.csv line 2: period '01/03/2024' holds the date '01/03/2024'; write dates YYYY-MM-DD")
        self.refused("line", "d.csv", self.rows(("2024-01", "1"), ("2024-02", "2"), ("2024-03", "3"), key="period",
                                                unit="GBP at 31.03.2024"), "t",
                     "d.csv line 2: unit 'GBP at 31.03.2024' holds the date '31.03.2024'")
        self.refused("gantt", "d.csv", [["section", "label", "start", "end", "source"],
                                        ["Due 1/2/24", "P1", "2021-07-15", "2031-07-15", src]], "t",
                     "d.csv line 2: section 'Due 1/2/24' holds the date '1/2/24'")
        self.refused("line", "d.csv", self.rows(("2024-01", "1"), ("2024-02", "2"), ("2024-03", "3"), key="period"),
                     "Balance to 31/03/2024", "--title: title 'Balance to 31/03/2024' holds the date")

    def test_values_exactly_as_given(self):
        for value in ("1,450", "£1450", "1450 ", "+5", "1e3", ".5", "5.", "12%", ""):
            with self.subTest(value=value):
                rows = [{"label": x, "value": v, "unit": "GBP", "source": self.SRC}
                        for x, v in (("a", "1"), ("b", value), ("c", "3"))]
                self.refused("bar", "v.json", rows, "t", "v.json row 2: value %r is not a plain decimal" % value)
        self.refused("bar", "v.json", self.raw_json("1", "1e3", "3"), "t",
                     "v.json row 2: value '1e3' is not a plain decimal")
        self.refused("bar", "v.json", self.raw_json("1", "NaN", "3"), "t", "NaN is not a value")
        self.refused("bar", "v.json", [{"label": "a", "value": True, "unit": "GBP", "source": self.SRC}], "t",
                     "v.json row 1: value must be text or a number, not true")
        self.refused("pie", "v.csv", self.rows(("a", "1"), ("b", "0"), ("c", "3")), "t (GBP)",
                     "v.csv line 3: pie value '0' is not positive")

    def test_text_the_chart_cannot_carry(self):
        for label, why in (('The "best"', "'\"'"), ("a | b", "'|'"), ("Item #1", "'#'"), ("a; b", "';'"),
                           ("`code`", "'`'"), ("a\nb", "'\\n'"), (" Rent", "spaces at its ends")):
            with self.subTest(label=label):
                rows = [{"label": x, "value": v, "unit": "GBP", "source": self.SRC}
                        for x, v in ((label, "1"), ("b", "2"), ("c", "3"))]
                self.refused("bar", "t.json", rows, "t", "t.json row 1: label %r" % label, why)
        self.refused("gantt", "c.csv", [["label", "start", "end", "source"],
                                        ["Lease: renewed", "2024-05-01", "2025-04-30", "03 Home/Lease renewal.pdf"]],
                     "t", "c.csv line 2: label 'Lease: renewed' holds ':'")
        self.refused("bar", "c.csv", self.rows(("a", "1"), ("a", "2"), ("c", "3")), "t",
                     "c.csv line 3: label 'a' repeats line 2's")

    def test_gantt_keywords(self):
        for keyword in wiki.GANTT_KEYWORDS:
            with self.subTest(keyword=keyword):
                self.refused("gantt", "k.csv", [["label", "start", "end", "source"],
                                                [keyword + " deed", "2024-01-01", "2024-02-01", self.SRC]], "t",
                             "k.csv line 2: label %r starts with the gantt keyword %r" % (keyword + " deed", keyword))
        self.refused("gantt", "k.csv", [["section", "label", "start", "end", "source"],
                                        ["todayMarker off", "Lease", "2024-01-01", "2024-02-01", self.SRC]], "t",
                     "k.csv line 2: section 'todayMarker off' starts with the gantt keyword 'todayMarker'")

    def test_mermaid_comments(self):
        src, why = self.SRC, "starts with %%, which Mermaid reads as a comment"
        cases = [("bar", self.rows(("%%a", "1"), ("b", "2"), ("c", "3")), "t", "line 2: label '%%a'"),
                 ("line", self.rows(("2024-01", "1"), ("%% x", "2"), ("2024-03", "3"), key="period"), "t",
                  "line 3: period '%% x'"),
                 ("pie", self.rows(("a", "1"), ("b", "2"), ("c", "3")), "%% (GBP)", "--title: title '%% (GBP)'"),
                 ("bar", self.rows(("a", "1"), ("b", "2"), ("c", "3"), unit="%%GBP"), "t", "line 2: unit '%%GBP'"),
                 ("gantt", [["label", "start", "end", "source"], ["%%x", "2024-01-01", "2024-02-01", src]], "t",
                  "line 2: label '%%x'"),
                 ("timeline", [["date", "label", "source"], ["2024-01-01", "%%x", src]], "t", "line 2: label '%%x'")]
        for kind, rows, title, where in cases:
            with self.subTest(kind=kind, where=where):
                self.refused(kind, "m.csv", rows, title, where, why)

    def test_malformed_input(self):
        self.refused("bar", "m.csv", "label,value,unit,source\na,1,GBP,%s,extra\n" % self.SRC, "t",
                     "m.csv line 2: 5 cells, but the header has 4")
        self.refused("bar", "m.csv", "label,label,unit,source\n", "t", "repeats a column")
        self.refused("bar", "m.json", '{"label": "a"}', "t", "expected a JSON array of objects")
        self.refused("bar", "m.json", '[{"label": "a", "label": "b"}]', "t", "an object repeats a key")
        self.refused("bar", "m.json", "[", "t", "not valid JSON")
        self.refused("bar", "m.txt", "x", "t", "--data must be a .csv or .json file")
        rows = [r + ["x"] for r in self.rows(("a", "1"), ("b", "2"), ("c", "3"))]
        rows[0][-1] = "colour"
        self.refused("bar", "m.csv", rows, "t", "unknown columns ['colour'] for a bar chart")
        code, _out, err = run("wiki.py", "chart", "--root", self.root, "--work", self.work, "--kind", "radar",
                              "--data", self.data("k.csv", "x\n"), "--title", "t")
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", err)


class CheckerTest(Charts):
    """Chart pairing: `check` counts the chart blocks and names every one not followed by its data table."""

    def page(self, *parts):
        return "\n".join(parts) + "\n"

    def test_pairing(self):
        golden = {kind: read(os.path.join(GOLDEN, kind + ".md")) for kind, _d, _t, _p in CASES}
        block = {kind: text.split("\n\n")[0] + "\n" for kind, text in golden.items()}
        flow = "```mermaid\nflowchart LR\n    a --> b\n```\n"
        for kind, text in golden.items():
            with self.subTest(kind=kind):
                mermaid_type = text.split("\n")[1].split()[0]
                self.assertEqual(wiki.chart_blocks(self.page("# P", "", text)), [(3, mermaid_type, True)])
                self.assertEqual(wiki.chart_blocks(self.page("# P", "", block[kind])), [(3, mermaid_type, False)])
                apart = self.page(block[kind], "Words between.", "", text.split("\n\n", 1)[1])
                self.assertEqual(wiki.chart_blocks(apart), [(1, mermaid_type, False)])
        table = golden["bar"].split("\n\n", 1)[1]
        self.assertFalse(wiki.chart_blocks(block["bar"] + "\n" + table.replace("| Label |", "| Item |"))[0][2])
        self.assertFalse(wiki.chart_blocks(block["bar"] + "\n" + table.replace("`02 Finance", "02 Finance", 1)
                                           .replace(".pdf` |", ".pdf |", 1))[0][2])
        self.assertTrue(wiki.chart_blocks(block["bar"] + "\n" + table.replace("| Label |", "| Period |"))[0][2])
        extra = table.replace("| Value (GBP) |", "| Value (GBP) | Extra (x) |", 1).replace("| --- | ---: |",
                                                                                            "| --- | ---: | --- |", 1)
        self.assertFalse(wiki.chart_blocks(block["bar"] + "\n" + extra)[0][2])
        self.assertEqual(wiki.chart_blocks(self.page(flow, golden["pie"])), [(6, "pie", True)])

    def test_directive_before_the_type(self):
        pie = read(os.path.join(GOLDEN, "pie.md"))
        directive = pie.replace("```mermaid\n", "```mermaid\n%%{init: {'theme': 'neutral'}}%%\n", 1)
        self.assertEqual(wiki.chart_blocks(directive), [(1, "pie", True)])

    def test_quoted_examples_are_not_charts(self):
        pie = read(os.path.join(GOLDEN, "pie.md"))
        bare = "```mermaid\npie title x\n```\n"
        indented = "".join("    " + x + "\n" for x in bare.splitlines())
        for text in ("# P\n\n````markdown\n" + bare + "````\n", "# P\n\n~~~\n" + bare + "~~~\n",
                     "# P\n\n" + indented, "~~~~ md\n" + bare + "~~~\nstill quoted\n~~~~\n"):
            with self.subTest(text=text):
                self.assertEqual(wiki.chart_blocks(text), [])
                self.assertEqual(wiki.chart_blocks(text + "\n" + pie)[0][1:], ("pie", True))
        self.assertEqual(wiki.chart_blocks("# P\n\n````markdown\n```mermaid\npie title x\n```\n````\n"), [])
        self.assertEqual(wiki.chart_blocks("``` mermaid\npie title x\n```\n"), [(1, "pie", False)])
        self.assertEqual(wiki.chart_blocks("~~~mermaid\npie title x\n```\n~~~\n"), [(1, "pie", False)])
        self.assertEqual(wiki.chart_blocks("````mermaid\npie title x\n```\n````\n\n" + pie.split("\n\n", 1)[1]),
                         [(1, "pie", True)])  # three backticks do not close a four-backtick fence

    def check(self, root):
        audit = os.path.join(os.path.dirname(root), "out", "_Audit")
        code, _out, err = run("audit.py", "--root", root, "--work", self.work, "--out", audit, "--read-only-root")
        self.assertEqual(code, 0, err)
        code, out, err = run("wiki.py", "check", "--root", root, "--work", self.work, "--manifest",
                             os.path.join(audit, "manifest.json"))
        self.assertIn(code, (0, 1), err)
        return code, json.loads(out)

    def test_fixture_charts_all_paired(self):
        code, res = self.check(self.root)
        self.assertEqual((code, res["chart_blocks"], res["charts_without_data_table"], res["problems"]),
                         (0, FIXTURE_CHARTS, [], 0))

    def test_chart_without_table_is_a_problem(self):
        root = self.own_copy()
        page = os.path.join(root, "Alex Personal Wiki", "30 Home", "30 Home.md")
        text = read(page)
        table = read(os.path.join(GOLDEN, "timeline.md")).split("\n\n", 1)[1]
        self.assertEqual(text.count(table), 1)
        write(page, text.replace("\n" + table, ""))
        line = read(page).split("\n").index("```mermaid") + 1
        code, res = self.check(root)
        self.assertEqual((code, res["chart_blocks"], res["charts_without_data_table"], res["problems"]),
                         (1, FIXTURE_CHARTS, [["30 Home/30 Home.md", line]], 1))


def update():
    """Rewrite the golden outputs and the probe page from the golden inputs, rendered against a fixture copy."""
    tmp = tempfile.mkdtemp(prefix="charts_update_")
    try:
        root = os.path.join(tmp, "Alex Personal")
        shutil.copytree(FIXTURE, root)
        outputs = {}
        for kind, data, title, _page in CASES:
            code, out, err = run("wiki.py", "chart", "--root", root, "--work", os.path.join(tmp, "work"),
                                 "--read-only-root", "--kind", kind, "--data", os.path.join(GOLDEN, data),
                                 "--title", title)
            if code:
                raise SystemExit("%s: %s" % (kind, err))
            outputs[kind] = out
            write(os.path.join(GOLDEN, kind + ".md"), out)
        write(PROBE, probe_text(outputs))
    finally:
        shutil.rmtree(tmp, True)
    print("updated")


if __name__ == "__main__":
    if sys.argv[1:] == ["--update"]:
        update()
    else:
        unittest.main()
