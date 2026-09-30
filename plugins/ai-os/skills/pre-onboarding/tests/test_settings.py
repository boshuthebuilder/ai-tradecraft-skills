"""The settings twins: compiling wiki-schema.json, refusing stale twins, and `settings.py check`, on fixture copies.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests
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
TOOLS = os.path.join(HERE, "..", "tools")
FIXTURE = os.path.join(HERE, "fixture", "Alex Personal")
EXPECTED_SCHEMA = os.path.join(HERE, "expected", "wiki-schema.json")
SCHEMA = os.path.join("Alex Personal Wiki", "90 Schema", "90 Schema.md")
sys.path.insert(0, TOOLS)
import common  # noqa: E402
import settings  # noqa: E402


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def run(tool, *args):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, tool)] + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def tree_digest(root):
    h = hashlib.sha256()
    for d, ds, fs in os.walk(root):
        ds.sort()
        for f in sorted(fs):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode() + b"\0" + read(p, "rb") + b"\n")
    return h.hexdigest()


def drop_section(text, heading):
    """The text without the `## <heading>` section (up to the next `## `)."""
    return re.sub(r"(?ms)^## %s\n.*?(?=^## )" % re.escape(heading), "", text)


def legacy_contracts(text):
    """The Schema text with its Page contracts table as written before the Reader column."""
    text = text.replace("| Section (professional) | Reader | Questions, most important first | Fields every page "
                        "carries |\n| --- | --- | --- | --- |",
                        "| Section (professional) | Questions, most important first | Fields every page carries |\n"
                        "| --- | --- | --- |")
    return text.replace(") | Alex | 1.", ") | 1.")


class FixtureCopy(unittest.TestCase):
    """Each test works on its own copies of the fixture folder; the committed fixture is never touched."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="settings_test_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.copy("a")

    def copy(self, parent):
        root = os.path.join(self.tmp, parent, "Alex Personal")
        shutil.copytree(FIXTURE, root)
        return root

    def work(self, root):
        return os.path.join(os.path.dirname(root), "work")

    def edit(self, root, rel, old, new, count=1):
        p = os.path.join(root, rel)
        text = read(p)
        self.assertEqual(text.count(old), count, "%r in %s" % (old, rel))
        with open(p, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new))

    def rulebook_json(self, root, **changes):
        p = os.path.join(root, ".familyai", "rulebook.json")
        data = json.loads(read(p))
        for k, v in changes.items():
            if v is None:
                data.pop(k, None)
            else:
                data[k] = v
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=1))

    def schema_json(self, root, change):
        p = os.path.join(root, ".familyai", "wiki-schema.json")
        data = json.loads(read(p))
        change(data)
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=1))

    def audit(self, root):
        return run("audit.py", "--root", root, "--work", self.work(root), "--out", os.path.join(self.tmp, "out"),
                   "--read-only-root")

    def edit_rulebook(self, root, old, new):
        """Edit the rulebook and its copy the same way and re-pin the twin, as a preparing agent would."""
        for name in ("CLAUDE.md", "AGENTS.md"):
            self.edit(root, name, old, new)
        self.rulebook_json(root, rulebook_sha256=common.sha256_file(os.path.join(root, "CLAUDE.md")))

    def compile(self, root):
        code, out, err = run("settings.py", "compile", "--root", root, "--work", self.work(root))
        self.assertEqual(code, 0, err)
        return read(os.path.join(root, ".familyai", "wiki-schema.json"), "rb")

    def check(self, root):
        code, out, err = run("settings.py", "check", "--root", root, "--work", self.work(root))
        self.assertIn(code, (0, 1), err)
        result = json.loads(out)
        self.assertEqual(code, 1 if result["findings"] else 0)
        return result

    def ws(self, root):
        return common.load_wiki_schema(root, os.path.join(root, ".familyai"))


class CompileTest(FixtureCopy):
    def test_byte_stable(self):
        first = self.compile(self.root)
        self.assertEqual(self.compile(self.root), first)
        self.assertEqual(self.compile(self.copy("elsewhere")), first)
        self.assertEqual(read(EXPECTED_SCHEMA, "rb"), first)

    def test_format(self):
        self.compile(self.root)
        ws = self.ws(self.root)
        self.assertEqual(list(ws), list(common.WIKI_SCHEMA_KEYS))
        self.assertEqual(ws["schema_path"], "Alex Personal Wiki/90 Schema/90 Schema.md")
        deadlines = ws["sections"][1]
        self.assertEqual((deadlines["number"], deadlines["name"], deadlines["kind"], deadlines["derived"]),
                         ("01", "Deadlines", "fixed", True))
        self.assertEqual(ws["sections"][4]["professionals"], ["private banker", "CFO", "chartered tax adviser"])
        self.assertEqual({s["kind"] for s in ws["sections"]}, {"fixed", "active", "history"})
        self.assertEqual([(r["prefix"], r["section"]) for r in ws["routing"] if r["target"] == "40 Study"],
                         [("04 Study/", "40"), ("05 Archive/", "40")])
        self.assertIsNone(ws["routing"][-1]["section"])
        finance = ws["contracts"][1]
        self.assertEqual(finance["reader"], "Alex")
        self.assertEqual(finance["questions"], ["Is anything due?", "What came in and went out?",
                                                "What is the tax position?"])
        self.assertEqual(finance["fields"], ["account", "period", "balances", "tax year", "amounts"])
        self.assertEqual(ws["pages"]["20 Finance/Cash position.md"],
                         {"professional": "CFO", "deliverable": "cash note", "tone": "numerate, brief"})

    def test_page_voice_falls_back_to_the_section(self):
        self.compile(self.root)
        ws = self.ws(self.root)
        self.assertEqual(common.page_voice(ws, "20 Finance/Tax.md")["professional"], "chartered tax adviser")
        self.assertEqual(common.page_voice(ws, "20 Finance/Tax.md")["source"], "page")
        self.assertEqual(common.page_voice(ws, "30 Home/30 Home.md"),
                         {"professional": "household manager", "deliverable": None, "tone": None,
                          "source": "section"})
        with self.assertRaisesRegex(common.ToolError, "names 3 professionals"):
            common.page_voice(ws, "20 Finance/20 Finance.md")
        with self.assertRaisesRegex(common.ToolError, "no section"):
            common.page_voice(ws, "50 Travel/Trips.md")

    def test_without_the_optional_page_professionals_table(self):
        p = os.path.join(self.root, SCHEMA)
        text = read(p)
        with open(p, "w", encoding="utf-8") as f:
            f.write(drop_section(text, "Page professionals"))
        self.compile(self.root)
        ws = self.ws(self.root)
        self.assertEqual(ws["pages"], {})
        self.assertEqual(len(ws["sections"]), 9)
        self.assertEqual(common.page_voice(ws, "10 Identity/10 Identity.md")["professional"], "immigration adviser")
        with self.assertRaises(common.ToolError):
            common.page_voice(ws, "20 Finance/Tax.md")

    def test_read_only_root_refuses_the_default_settings_dir(self):
        code, _out, err = run("settings.py", "compile", "--root", self.root, "--work", self.work(self.root),
                              "--read-only-root")
        self.assertEqual(code, 2)
        self.assertIn("--read-only-root", err)
        elsewhere = os.path.join(self.tmp, "settings")
        shutil.copytree(os.path.join(self.root, ".familyai"), elsewhere)
        before = tree_digest(self.root)
        code, _out, err = run("settings.py", "compile", "--root", self.root, "--work", self.work(self.root),
                              "--settings-dir", elsewhere, "--read-only-root")
        self.assertEqual(code, 0, err)
        self.assertEqual(tree_digest(self.root), before)
        self.assertEqual(read(os.path.join(elsewhere, "wiki-schema.json"), "rb"), read(EXPECTED_SCHEMA, "rb"))


class MalformedSchemaTest(unittest.TestCase):
    """Unknown headers and unreadable rows fail loud; nothing is guessed."""

    TEXT = read(os.path.join(FIXTURE, SCHEMA))

    def fails(self, text, pattern):
        with self.assertRaisesRegex(common.ToolError, pattern):
            settings.compile_text(text, "x")

    def swap(self, old, new):
        self.assertEqual(self.TEXT.count(old), 1, old)
        return self.TEXT.replace(old, new)

    def test_fixture_compiles(self):
        self.assertEqual(len(settings.compile_text(self.TEXT, "x")["contracts"]), 4)

    def test_unknown_headers(self):
        cases = {
            "an extra Layout column": ("| Section | Pages | Professional lens | Kind |",
                                       "| Section | Pages | Professional lens | Kind | Notes |"),
            "contracts with a renamed Reader": ("| Section (professional) | Reader | Questions",
                                                "| Section (professional) | Audience | Questions"),
            "a renamed optional column": ("| Page | Professional | Deliverable | Tone |",
                                          "| Page | Professional | Deliverable | Voice |"),
            "a renamed Routing column": ("| Files under | Section and page |", "| Folder | Section and page |"),
        }
        for name, (old, new) in cases.items():
            with self.subTest(name):
                self.fails(self.swap(old, new), "expected exactly")

    def test_missing_required_tables(self):
        for heading in ("Layout", "Routing", "Page contracts"):
            with self.subTest(heading):
                self.fails(drop_section(self.TEXT, heading), "no %s table" % heading)

    def test_unreadable_rows(self):
        cases = {
            "a duplicate section": ("| 91 Log | append", "| 90 Log | append", "listed twice"),
            "an unknown kind": ("| academic registrar | history |", "| academic registrar | ongoing |",
                                "kind 'ongoing'"),
            "an unnumbered section": ("| 30 Home | lease", "| Home | lease", "two-digit section number"),
            "a section without a professional": ("| household manager | active |", "|  | active |",
                                                 "no professional"),
            "a missing cell": ("| 30 Home | lease, bills | household manager | active |",
                               "| 30 Home | lease, bills | active |", "has 3 cells"),
            "questions out of order": ("1. Is anything due? 2. What came in", "1. Is anything due? 3. What came in",
                                       "numbered 1., 2., 3."),
            "a contract without a reader": ("| 30 Home (household manager) | Alex |",
                                            "| 30 Home (household manager) |  |", "no reader"),
            "a contract for an unknown section": ("| 40 Study (academic registrar) |",
                                                  "| 50 Study (academic registrar) |", "not in the Layout"),
            "two contracts for a section": ("| 40 Study (academic registrar) |", "| 30 Home (academic registrar) |",
                                            "two contracts"),
            "an unquoted routing prefix": ("| `03 Home/` |", "| 03 Home/ |", "backticks"),
            "a routing prefix without /": ("| `03 Home/` |", "| `03 Home` |", "ending in /"),
            "a prefix routed twice": ("| `06 Work/` |", "| `03 Home/` |", "routed twice"),
            "routing to an unknown section": ("| `03 Home/` | 30 Home |", "| `03 Home/` | 50 Home |",
                                              "not in the Layout"),
            "a page under an unknown section": ("| 20 Finance/Tax.md |", "| 25 Tax/Tax.md |", "not a page path"),
            "a page listed twice": ("| 20 Finance/Tax.md |", "| 20 Finance/Cash position.md |", "listed twice"),
            "questions not starting at 1.": ("| Alex | 1. Where does Alex live", "| Alex | Where does Alex live",
                                             "numbered 1., 2., 3."),
            "text before the first question": ("| Alex | 1. Where does Alex live",
                                               "| Alex | Home: 1. Where does Alex live", "numbered 1., 2., 3."),
            "an unnumbered question": ("| Alex | 1. Where does Alex live and on what terms? 2. What bills are due? |",
                                       "| Alex | Where does Alex live? |", "numbered 1., 2., 3."),
            "an empty last question": ("2. What bills are due? |", "2. What bills are due? 3. |",
                                       "question 3 is empty"),
            "a three-digit section": ("| 30 Home | lease", "| 300 Home | lease", "two-digit section number"),
            "a one-digit section": ("| 30 Home | lease", "| 3 Home | lease", "two-digit section number"),
            "a contract named unlike its section": ("| 40 Study (academic registrar) |",
                                                    "| 40 Studies (academic registrar) |", "not in the Layout"),
            "a routing target without a space": ("| `03 Home/` | 30 Home |", "| `03 Home/` | 30Home |",
                                                 "two-digit section number and a name"),
            "a one-digit routing target": ("| `03 Home/` | 30 Home |", "| `03 Home/` | 3 Home |",
                                           "two-digit section number and a name"),
        }
        for name, (old, new, pattern) in cases.items():
            with self.subTest(name):
                self.fails(self.swap(old, new), pattern)

    def test_one_table_per_section(self):
        self.fails(self.swap("## Routing\n", "## Routing\n\n| a | b |\n| --- | --- |\n| c | d |\n"),
                   "holds 2 tables")
        self.fails(self.swap("## Writing rules", "## Routing (old)"), "2 sections headed Routing")
        renamed = settings.compile_text(self.swap("## Writing rules", "## Routing notes"), "x")
        self.assertEqual(renamed, settings.compile_text(self.TEXT, "x"))
        self.assertEqual(settings.compile_text(self.swap("## Layout\n", "## Layout (sections)\n"), "x"),
                         settings.compile_text(self.TEXT, "x"))

    def test_markdown_variants(self):
        same = settings.compile_text(self.TEXT, "x")
        self.assertEqual(settings.compile_text(self.swap("## Layout\n", "## Layout ##\n"), "x"), same)
        self.assertEqual(settings.compile_text(self.swap("| Section | Pages | Professional lens | Kind |\n"
                                                         "| --- | --- | --- | --- |",
                                                         "| Section | Pages | Professional lens | Kind |\n"
                                                         "| - | :-: | -: | :- |"), "x"), same)

    def test_contracts_written_before_the_reader_column(self):
        legacy = settings.compile_text(legacy_contracts(self.TEXT), "x")
        current = settings.compile_text(self.TEXT, "x")
        self.assertEqual([c["reader"] for c in legacy["contracts"]], [None] * 4)
        for c in current["contracts"]:
            c["reader"] = None
        self.assertEqual(legacy, current)

    def test_fenced_tables_are_ignored(self):
        fenced = "## Routing\n\n```\n| Folder | Where |\n| --- | --- |\n```\n"
        self.assertEqual(settings.compile_text(self.swap("## Routing\n", fenced), "x"),
                         settings.compile_text(self.TEXT, "x"))


class StaleTest(FixtureCopy):
    """Editing one character of a twin's source makes every tool refuse, before it reads or writes anything; the
    two diagnoses (settings.py check, readiness.py) report it instead."""

    def setUp(self):
        super().setUp()
        self.manifest = os.path.join(self.tmp, "audit", "manifest.json")
        code, _out, err = run("audit.py", "--root", self.root, "--work", self.work(self.root), "--out",
                              os.path.dirname(self.manifest), "--read-only-root")
        self.assertEqual(code, 0, err)

    def commands(self, root):
        out, work = os.path.join(self.tmp, "out"), self.work(root)
        manifest, plan = self.manifest, os.path.join(self.tmp, "move-plan.csv")
        folder = ["--root", root, "--work", work]
        plan_root = ["--root", root]
        return [
            ("audit.py", folder + ["--out", out, "--read-only-root"]),
            ("extract.py", folder + ["--manifest", manifest, "--out", out]),
            ("vision.py", folder + ["--model", "a-model", "--out", out]),
            ("cards.py", ["build"] + folder + ["--out", out]),
            ("refs.py", folder),
            ("wiki.py", ["bundles"] + folder + ["--out", out]),
            ("wiki.py", ["check"] + folder + ["--manifest", manifest]),
            ("wiki.py", ["move"] + folder + ["--map", os.path.join(self.tmp, "map.json")]),
            ("readiness.py", folder + ["--manifest", manifest]),
            ("plan.py", ["light"] + plan_root + ["--manifest", manifest, "--out", out]),
            ("plan.py", ["migrate"] + plan_root + ["--project", "P", "--paths-file", plan, "--out", out]),
            ("plan.py", ["return"] + plan_root + ["--project", "P", "--paths-file", plan, "--out", out]),
            ("plan.py", ["rmdirs"] + plan_root + ["--plan", plan]),
            ("plan.py", ["check"] + plan_root + ["--plan", plan]),
            ("plan.py", ["execute"] + plan_root + ["--plan", plan]),
        ]

    def assert_every_tool_refuses(self, root, source, state="stale", reported_by=()):
        before = tree_digest(root)
        for tool, args in self.commands(root):
            with self.subTest(tool=tool, cmd=args[0]):
                code, out, err = run(tool, *args)
                if tool in reported_by:
                    self.assertEqual(code, 1, out + err)
                    self.assertIn("finding: %s:" % state, out)
                    self.assertIn(source, out)
                else:
                    self.assertEqual(code, 2, out + err)
                    self.assertIn("error: %s:" % state, err)
                    self.assertIn(source, err)
        result = self.check(root)
        self.assertTrue(any(f.startswith(state + ":") and source in f for f in result["findings"]), result)
        self.assertEqual(tree_digest(root), before, "a refusing tool wrote inside the folder")

    def test_one_character_of_the_schema(self):
        self.compile(self.root)
        self.edit(self.root, SCHEMA, "The constitution", "the constitution")
        self.assert_every_tool_refuses(self.root, SCHEMA.replace(os.sep, "/"), reported_by=("readiness.py",))
        self.assertEqual(self.check(self.root)["status"]["wiki_schema_json"], "stale")
        self.compile(self.root)
        self.assertEqual(self.check(self.root)["count"], 0)

    def test_one_character_of_the_rulebook(self):
        self.compile(self.root)
        self.edit(self.root, "CLAUDE.md", "Nobody else.", "Nobody else!")
        self.edit(self.root, "AGENTS.md", "Nobody else.", "Nobody else!")
        self.assert_every_tool_refuses(self.root, "CLAUDE.md", reported_by=("readiness.py",))
        code, _out, err = run("settings.py", "compile", "--root", self.root, "--work", self.work(self.root))
        self.assertEqual(code, 2)
        self.assertIn("stale:", err)
        self.assertEqual(self.check(self.root)["status"]["rulebook_json"], "stale")

    def test_a_missing_schema_page_is_stale(self):
        self.compile(self.root)
        os.rename(os.path.join(self.root, SCHEMA), os.path.join(self.tmp, "Schema.md"))
        code, _out, err = run("audit.py", "--root", self.root, "--work", self.work(self.root), "--out",
                              os.path.join(self.tmp, "out"), "--read-only-root")
        self.assertEqual(code, 2)
        self.assertIn("which is missing", err)

    def test_an_unpinned_rulebook_json_is_refused(self):
        for n, pin in enumerate((None, "")):
            with self.subTest(pin=pin):
                root = self.copy("unpinned%d" % n)
                self.rulebook_json(root, rulebook_sha256=pin)
                code, _out, err = self.audit(root)
                self.assertEqual(code, 2)
                self.assertIn("error: unpinned:", err)
                self.assertEqual(self.check(root)["status"]["rulebook_json"], "unpinned")

    def test_a_missing_rulebook_is_stale(self):
        self.compile(self.root)
        os.remove(os.path.join(self.root, "CLAUDE.md"))
        code, _out, err = self.audit(self.root)
        self.assertEqual(code, 2)
        self.assertIn("error: stale:", err)
        self.assertIn("CLAUDE.md, which is missing", err)
        result = self.check(self.root)
        self.assertEqual(result["status"]["rulebook_json"], "stale")
        self.assertEqual(sum("CLAUDE.md" in f for f in result["findings"]), 1, result)

    def test_a_superseded_schema_page_is_stale(self):
        wiki = os.path.join(self.root, "Alex Personal Wiki")
        os.rename(os.path.join(wiki, "90 Schema"), os.path.join(wiki, "09 Schema"))
        os.rename(os.path.join(wiki, "09 Schema", "90 Schema.md"), os.path.join(wiki, "09 Schema", "09 Schema.md"))
        self.compile(self.root)
        self.assertEqual(self.ws(self.root)["schema_path"], "Alex Personal Wiki/09 Schema/09 Schema.md")
        os.makedirs(os.path.join(wiki, "90 Schema"))
        shutil.copy(os.path.join(wiki, "09 Schema", "09 Schema.md"), os.path.join(wiki, "90 Schema", "90 Schema.md"))
        code, _out, err = self.audit(self.root)
        self.assertEqual(code, 2)
        self.assertIn("90 Schema.md now takes precedence", err)

    def test_an_old_or_malformed_schema_twin_is_refused_by_name(self):
        def old_format(ws):
            ws["version"] = 1
            for r in ws["routing"]:
                r["prefixes"] = [r.pop("prefix")]

        def old_shape_new_version(ws):
            for r in ws["routing"]:
                r["prefixes"] = [r.pop("prefix")]

        cases = [
            ("the format before version 2", old_format, "unsupported version 1"),
            ("an old shape under the new version", old_shape_new_version, "routing is not a list"),
            ("a null schema_sha256", lambda ws: ws.update(schema_sha256=None), "schema_sha256 is not"),
            ("a null schema_path", lambda ws: ws.update(schema_path=None), "schema_path None"),
            ("a path outside the folder", lambda ws: ws.update(schema_path="../x/90 Schema/90 Schema.md"),
             "not a Schema page inside the folder"),
            ("a missing key", lambda ws: ws.pop("pages"), "keys"),
            ("sections as a number", lambda ws: ws.update(sections=5), "sections is not a list"),
            ("a page row without a tone", lambda ws: ws["pages"]["20 Finance/Tax.md"].pop("tone"),
             "pages is not a map"),
        ]
        for n, (name, change, pattern) in enumerate(cases):
            with self.subTest(name):
                root = self.copy("twin%d" % n)
                self.compile(root)
                self.schema_json(root, change)
                out = os.path.join(self.tmp, "out")
                for tool, sub, args in (("audit.py", [], ["--out", out, "--read-only-root"]),
                                        ("wiki.py", ["bundles"], ["--out", out])):
                    code, _out, err = run(tool, *sub, "--root", root, "--work", self.work(root), *args)
                    self.assertEqual(code, 2, err)
                    self.assertIn(pattern, err)
                    self.assertNotIn("Traceback", err)
                result = self.check(root)
                self.assertEqual(result["status"]["wiki_schema_json"], "invalid")
                self.assertEqual(result["count"], 1, result)

    def test_a_missing_root_is_named(self):
        code, _out, err = run("plan.py", "light", "--root", os.path.join(self.tmp, "nowhere"), "--manifest",
                              self.manifest, "--out", os.path.join(self.tmp, "out"))
        self.assertEqual(code, 2)
        self.assertIn("root missing", err)

    def test_fresh_twins_are_not_refused(self):
        self.compile(self.root)
        code, _out, err = run("audit.py", "--root", self.root, "--work", self.work(self.root), "--out",
                              os.path.join(self.tmp, "out"), "--read-only-root")
        self.assertEqual(code, 0, err)


class CheckTest(FixtureCopy):
    def test_the_fixture_is_clean(self):
        self.compile(self.root)
        result = self.check(self.root)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["status"], {"rulebook_json": "fresh", "rulebook_facts": "checked",
                                            "rulebook_copies_identical": True, "wiki_schema_json": "fresh"})
        out = os.path.join(self.tmp, "check.json")
        code, stdout, err = run("settings.py", "check", "--root", self.root, "--work", self.work(self.root),
                                "--out", out)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(read(out)), json.loads(stdout))

    def test_absent_twins_are_missing(self):
        os.remove(os.path.join(self.root, ".familyai", "rulebook.json"))
        status = self.check(self.root)["status"]
        self.assertEqual((status["rulebook_json"], status["wiki_schema_json"]), ("missing", "missing"))

    def test_each_planted_defect_is_reported_once(self):
        def agents_differ(root):
            with open(os.path.join(root, "AGENTS.md"), "a", encoding="utf-8") as f:
                f.write("\nA local note.\n")

        def not_utf8(root):
            for name in ("CLAUDE.md", "AGENTS.md"):
                with open(os.path.join(root, name), "ab") as f:
                    f.write(b"\xff\n")
            self.rulebook_json(root, rulebook_sha256=common.sha256_file(os.path.join(root, "CLAUDE.md")))

        def no_reader(root):
            p = os.path.join(root, SCHEMA)
            text = read(p)
            with open(p, "w", encoding="utf-8") as f:
                f.write(legacy_contracts(text))
            self.compile(root)

        def contract_dropped(root):
            self.edit(root, SCHEMA, "| 30 Home (household manager) | Alex | 1. Where does Alex live and on what "
                                    "terms? 2. What bills are due? | address, landlord, term, rent, bills |\n", "")
            self.compile(root)

        cases = [
            ("AGENTS.md differs", agents_differ, "CLAUDE.md and AGENTS.md differ"),
            ("an extra reserved name", lambda r: self.rulebook_json(r, reserved=["Private"]),
             "reserved name 'Private'"),
            ("GEMINI.md not reserved", lambda r: self.edit_rulebook(r, "`GEMINI.md`, ", ""),
             "reserved name 'GEMINI.md'"),
            ("the settings folder not named", lambda r: self.edit_rulebook(r, ", `.familyai`.", "."),
             "reserved name '.familyai'"),
            ("a pack not named", lambda r: self.rulebook_json(r, packs=["01 Identity/Passport renewal 2021",
                                                                         "02 Finance/Loan 2022"]),
             "pack '02 Finance/Loan 2022'"),
            ("a wiki folder not named after the folder",
             lambda r: self.rulebook_json(r, wiki_dir="Alex Personal Vault"), "wiki_dir 'Alex Personal Vault'"),
            ("a section without a contract", contract_dropped, "section 30 Home has no page contract"),
            ("no rulebook.json", lambda r: os.remove(os.path.join(r, ".familyai", "rulebook.json")),
             "missing folder settings"),
            ("no CLAUDE.md", lambda r: os.remove(os.path.join(r, "CLAUDE.md")), "CLAUDE.md, which is missing"),
            ("no AGENTS.md", lambda r: os.remove(os.path.join(r, "AGENTS.md")), "rulebook file missing: AGENTS.md"),
            ("a rulebook that is not UTF-8", not_utf8, "not valid UTF-8"),
            ("contracts written before the Reader column", no_reader, settings.NO_READER),
        ]
        for n, (name, plant, finding) in enumerate(cases):
            with self.subTest(name):
                root = self.copy("case%d" % n)
                self.compile(root)
                plant(root)
                found = self.check(root)["findings"]
                self.assertEqual(len(found), 1, found)
                self.assertIn(finding, found[0])


class RulebookValidationTest(FixtureCopy):
    def load(self, **changes):
        self.rulebook_json(self.root, **changes)
        return common.load_rulebook(self.root, os.path.join(self.root, ".familyai"))

    def test_the_fixture_loads(self):
        rb = self.load()
        self.assertEqual(rb["wiki_dir"], "Alex Personal Wiki")
        self.assertEqual(rb["people"][1]["also"], ["Robin"])
        self.assertIn("GEMINI.md", common.reserved_names(rb))

    def test_malformed_values_fail_loud(self):
        cases = {
            "unknown key": ({"colour": "blue"}, "unknown keys"),
            "version": ({"version": 2}, "unsupported version"),
            "identifiers": ({"identifiers": "masked"}, "identifiers must be one of"),
            "depth": ({"depth": "deep"}, "depth must be one of"),
            "person without a name": ({"people": [{"also": ["Robin"], "who": "partner"}]}, r"people\[0\]"),
            "person with a stray key": ({"people": [{"name": "Robin", "role": "partner"}]}, r"people\[0\]"),
            "packs as text": ({"packs": "01 Identity"}, "packs must be a list"),
            "keep_empty_folders as text": ({"keep_empty_folders": "yes"}, "true or false"),
            "a short sha": ({"rulebook_sha256": "abc"}, "sha256 hex digest"),
        }
        for name, (changes, pattern) in cases.items():
            with self.subTest(name):
                root = self.copy(name.replace(" ", "-"))
                self.rulebook_json(root, **changes)
                with self.assertRaisesRegex(common.ToolError, pattern):
                    common.load_rulebook(root, os.path.join(root, ".familyai"))

    def test_absent_twin(self):
        os.remove(os.path.join(self.root, ".familyai", "rulebook.json"))
        settings_dir = os.path.join(self.root, ".familyai")
        self.assertEqual(common.load_rulebook(self.root, settings_dir)["depth"], "light")
        with self.assertRaisesRegex(common.ToolError, "missing folder settings"):
            common.load_rulebook(self.root, settings_dir, required=True)


if __name__ == "__main__":
    unittest.main()
