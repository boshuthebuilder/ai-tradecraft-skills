"""The isolation gate: the operator's terms file, the scan of model-facing files, the canary per engine and its
liveness artefact, and the contamination rule, with fake engines. The terms here are invented for the tests; a real
terms file is supplied at run time and never committed.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
TIMEOUT = 600  # seconds: a tool that hangs fails its test instead of the run
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import common  # noqa: E402
import isolation  # noqa: E402
from fake_engines import Fakes, tool_env  # noqa: E402

TERMS = "# terms for the tests (fictional)\n\nZarnwick Farm|Zarnwick\nOther Project\n青石湾\n"
# how the fake engine finds the invented name in the canary prompt: the prompt itself, with each {marker} one group
MARKER_RE = re.escape(isolation.CANARY).replace(re.escape("{marker}"), r"(\w+)")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="isolation_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.terms = os.path.join(self.tmp, "terms.txt")
        write(self.terms, TERMS)
        self.fakes = Fakes(self.tmp)
        self.env = tool_env(self.tmp, self.fakes)

    def iso(self, *args):
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "isolation.py")] + list(args), capture_output=True,
                           text=True, env=self.env, timeout=TIMEOUT)
        self.assertNotIn("ResourceWarning", r.stderr, "isolation.py left a file or process open")
        return r.returncode, r.stdout, r.stderr


class TermsTest(Case):
    def test_terms_and_markers(self):
        self.assertEqual(isolation.load_terms(self.terms), {"Zarnwick Farm": ["Zarnwick Farm", "Zarnwick"],
                                                             "Other Project": ["Other Project"],
                                                             "青石湾": ["青石湾"]})

    def test_a_missing_or_empty_terms_file_is_an_error(self):
        with self.assertRaisesRegex(common.ToolError, "missing"):
            isolation.load_terms(os.path.join(self.tmp, "nowhere.txt"))
        empty = os.path.join(self.tmp, "empty.txt")
        write(empty, "# only a comment\n\n")
        with self.assertRaisesRegex(common.ToolError, "empty"):
            isolation.load_terms(empty)

    def test_a_term_is_an_alert_only_when_the_cards_own_source_lacks_it(self):
        ev = isolation.load_terms(self.terms)
        card = '{"summary": "Rent for the flat at zarnwick farm."}'
        cases = {
            "absent from the source": ("Rent for the flat.", ["Zarnwick Farm"]),
            "in the source, another case": ("Paid to ZARNWICK FARM.", []),
            "only its marker in the source": ("Paid to Zarnwick, the farm.", []),
            "the marker inside a longer word": ("Paid to Zarnwickshire.", ["Zarnwick Farm"]),
        }
        for name, (source, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(isolation.contamination(card, source, ev), want)
        self.assertEqual(isolation.contamination('{"summary": "青石湾 rent"}', "租金 青石湾 1号", ev), [])
        self.assertEqual(isolation.contamination('{"summary": "青石湾 rent"}', "租金", ev), ["青石湾"])
        self.assertEqual(isolation.contamination('{"summary": "Council tax."}', "", ev), [])


class ShieldTest(Case):
    """`isolation.shield`: every term and marker replaced, by the match `hits` and `masked` use, and counted."""

    def setUp(self):
        super().setUp()
        self.ev = isolation.load_terms(self.terms)

    def test_every_term_and_marker_is_replaced_whatever_its_case_and_counted(self):
        text = "Rent to Zarnwick Farm; ZARNWICK too, zarnwick farm again, Other Project, and 青石湾 1号."
        got, n = isolation.shield(text, self.ev)
        self.assertEqual(got, "Rent to [withheld name]; [withheld name] too, [withheld name] again, [withheld name], "
                              "and [withheld name] 1号.")
        self.assertEqual(n, 5)
        self.assertEqual(isolation.hits(got, self.ev), [], "the scan finds nothing in what the shield made")

    def test_the_longest_form_goes_first_and_a_form_is_never_replaced_inside_the_placeholder(self):
        ev = {"Zarnwick Farm": ["Zarnwick Farm", "Zarnwick"], "withheld": ["withheld"], "name": ["name"]}
        got, n = isolation.shield("Zarnwick Farm, Zarnwick and the farm", ev)
        self.assertEqual((got, n), ("[withheld name], [withheld name] and the farm", 2))
        self.assertEqual(isolation.shield("[withheld name]", {"x": ["Zarnwick"]}), ("[withheld name]", 0))

    def test_a_short_term_masks_inside_a_longer_word_and_never_leaks(self):
        got, n = isolation.shield("Zarnwickshire and a Ziggurat", {"Zarn": ["Zarn"]})
        self.assertEqual((got, n), ("[withheld name]wickshire and a Ziggurat", 1))

    def test_regex_characters_in_a_term_are_literal(self):
        ev = {"A.B (C)": ["A.B (C)"]}
        self.assertEqual(isolation.shield("a.b (c) and AXB (C)", ev), ("[withheld name] and AXB (C)", 1))

    WRAPPED = ("Zarnwick\nFarm", "Zarnwick\r\nFarm", "Zarnwick\u00a0Farm", "Zarnwick\u202fFarm", "Zarnwick\u2009Farm",
               "ZARNWICK  \t Farm", "zarnwick\n    farm", "Zarnwick\u3000Farm")

    def test_a_name_wrapped_at_a_line_end_or_set_with_another_space_is_the_name(self):
        for form in self.WRAPPED:
            with self.subTest(form=form):
                text = "Lease between Alex and %s for the flat." % form
                got, n = isolation.shield(text, self.ev)
                self.assertEqual((got, n), ("Lease between Alex and [withheld name] for the flat.", 1))
                self.assertTrue(isolation.carries(text, self.ev))
                self.assertEqual(isolation.hits(text, self.ev), ["Zarnwick Farm"], "the scan reads it the same way")
                self.assertEqual(isolation.masked(text, self.ev), "Lease between Alex and <term> for the flat.")

    def test_a_name_in_either_unicode_form_is_the_name(self):
        nfd, nfc = "Jose\u0301 Quorvane", "Jos\u00e9 Quorvane"
        for term, text in ((nfc, "Letter from %s.pdf" % nfd), (nfd, "Letter from %s.pdf" % nfc)):
            with self.subTest(term=term):
                ev = {term: [term]}
                self.assertEqual(isolation.shield(text, ev), ("Letter from [withheld name].pdf", 1))
                self.assertTrue(isolation.carries(text, ev))
                self.assertEqual(isolation.hits(text, ev), [term])
                self.assertEqual(isolation.masked(text, ev), "Letter from <term>.pdf")

    def test_the_matcher_is_one_whatever_asks(self):
        """The scan, the contamination check and the shield read a text alike: a text the shield leaves is a text the scan
        finds nothing in."""
        cases = list(self.WRAPPED) + ["Zarnwick", "Zarnwick-Farm", "Zarnwick Far", "Other\nProject", "青石湾"]
        for form in cases:
            with self.subTest(form=form):
                text = "a %s b" % form
                shielded, n = isolation.shield(text, self.ev)
                self.assertEqual(n > 0, isolation.carries(text, self.ev))
                self.assertEqual(isolation.hits(shielded, isolation.forms(self.ev)), [], shielded)

    def test_what_still_does_not_match_is_the_settled_residual(self):
        """A name split by a hyphen at a line end, or by a zero-width character or a soft hyphen, is not matched."""
        for form in ("Zarn-\nwick Farm", "Zarn\u200bwick Farm", "Zarn\u00adwick Farm", "ZarnwickFarm"):
            with self.subTest(form=form):
                self.assertEqual(isolation.shield("a %s b" % form, {"Zarnwick Farm": ["Zarnwick Farm"]}),
                                 ("a %s b" % form, 0))

    def test_the_shield_is_idempotent_and_never_finds_a_term_inside_its_placeholder(self):
        ev = {"Held": ["Held"], "Zarnwick Farm": ["Zarnwick Farm"]}
        once = isolation.shield("Held Zarnwick\nFarm and a held letter", ev)
        self.assertEqual(once, ("[withheld name] [withheld name] and a [withheld name] letter", 3))
        self.assertEqual(isolation.shield(once[0], ev), (once[0], 0))
        self.assertEqual(isolation.shield("[withheld name]", ev), ("[withheld name]", 0))
        self.assertFalse(isolation.carries(once[0].replace("[withheld name]", ""), ev))

    PLACEHOLDERS = ("[withheld name]", "[Withheld Name]", "[WITHHELD NAME]", "[withheld  name]", "[ withheld name ]",
                    "[withheld\nname]", "[withheld\u00a0name]")

    def test_the_placeholder_is_taken_out_whatever_its_case_or_spacing(self):
        for form in self.PLACEHOLDERS:
            with self.subTest(form=form):
                self.assertEqual(isolation.without_placeholder("a %s b" % form), "a \x00 b")
        self.assertEqual(isolation.without_placeholder("a [withheld names] b"), "a [withheld names] b")

    def test_a_term_inside_the_placeholder_is_no_contamination_and_one_outside_it_still_is(self):
        ev = {"Held": ["Held"]}  # as evidence only: `load_terms` refuses a file that holds it
        for form in self.PLACEHOLDERS:
            with self.subTest(form=form):
                self.assertEqual(isolation.contamination('{"summary": "Filed under %s letter.pdf"}' % form, "", ev), [])
        self.assertEqual(isolation.contamination('{"summary": "[withheld name] and Held."}', "", ev), ["Held"])
        self.assertEqual(isolation.contamination('{"summary": "Hel[withheld name]d"}', "", ev), [],
                         "taking the placeholder out never joins what stood round it into a term")

    def test_the_shield_leaves_the_placeholder_as_it_stands_in_any_case(self):
        ev = {"Quorvane": ["Quorvane"]}
        self.assertEqual(isolation.shield("a [Withheld  Name] b Quorvane", ev), ("a [withheld name] b [withheld name]", 1))

    def test_carries_is_whether_the_shield_would_replace_anything(self):
        for text, want in (("Rent to Zarnwick Farm", True), ("only the marker, ZARNWICK", True), ("Council tax", False),
                           ("青石湾 1号", True)):
            with self.subTest(text):
                self.assertEqual(isolation.carries(text, self.ev), want)
                self.assertEqual(isolation.shield(text, self.ev)[1] > 0, want)
        self.assertFalse(isolation.carries("Zarnwick Farm", {}))

    def test_no_terms_returns_the_text_as_it_was(self):
        self.assertEqual(isolation.shield("Zarnwick Farm", {}), ("Zarnwick Farm", 0))
        self.assertEqual(isolation.shield_value({"a": ["Zarnwick"]}, {}), ({"a": ["Zarnwick"]}, 0))

    def test_a_json_value_is_shielded_in_every_string_and_key(self):
        value = {"path": "Zarnwick Farm/lease.pdf", "Other Project": ["x Zarnwick", 3, None, True],
                 "nested": {"k": "青石湾"}}
        got, n = isolation.shield_value(value, self.ev)
        self.assertEqual(got, {"path": "[withheld name]/lease.pdf", "[withheld name]": ["x [withheld name]", 3, None, True],
                               "nested": {"k": "[withheld name]"}})
        self.assertEqual(n, 4)
        self.assertEqual(value["path"], "Zarnwick Farm/lease.pdf", "the value given is not changed")

    def test_the_digest_is_of_the_sorted_forms_and_never_holds_them(self):
        a = isolation.shield_digest(self.ev)
        self.assertRegex(a, r"^[0-9a-f]{64}$")
        reordered = {k: self.ev[k] for k in reversed(list(self.ev))}
        self.assertEqual(isolation.shield_digest(reordered), a)
        self.assertNotEqual(isolation.shield_digest({"Zarnwick Farm": ["Zarnwick Farm"]}), a)
        self.assertNotEqual(isolation.shield_digest({}), a)
        for form in ("Zarnwick", "Other Project"):
            self.assertNotIn(form, a)

    def test_neither_flag_and_both_flags_are_refused_and_no_terms_means_no_evidence(self):
        ns = lambda **kw: type("A", (), dict({"terms": None, "no_isolation_terms": False}, **kw))  # noqa: E731
        with self.assertRaisesRegex(common.ToolError, "give --terms .* or --no-isolation-terms$"):
            isolation.evidence_of(ns())
        with self.assertRaisesRegex(common.ToolError, "not both"):
            isolation.evidence_of(ns(terms=self.terms, no_isolation_terms=True))
        self.assertEqual(isolation.evidence_of(ns(no_isolation_terms=True)), {})
        self.assertEqual(isolation.evidence_of(ns(terms=self.terms)), self.ev)


class StringsTest(Case):
    def test_strings_are_the_values_of_a_json_value_never_its_keys(self):
        card = {"proposed_name": "", "title": "A lease", "key_facts": {"dates": ["2024-01-01"], "amounts": []}, "n": 3,
                "parties": ["Alex", {"party_name": "Robin"}]}
        self.assertEqual(sorted(isolation.strings(card)), sorted(["", "A lease", "2024-01-01", "Alex", "Robin"]))
        self.assertEqual(isolation.strings(None), [])

    def test_a_short_term_is_not_a_contamination_in_a_field_name_only_in_a_value(self):
        ev = {"Nam": ["Nam"]}
        card = {"proposed_name": "", "title": "A lease"}
        self.assertEqual(isolation.contamination("\n".join(isolation.strings(card)), "", ev), [])
        self.assertEqual(isolation.contamination("\n".join(isolation.strings(dict(card, title="Nam lease"))), "", ev),
                         ["Nam"])


class PlaceholderMatcherTest(Case):
    """No form is ever found inside the placeholder, so a short name is never refused and never read in a shielded text."""

    SHORT = ("Nam", "Na", "He", "Held", "Wit", "Hel", "name", "with", "withheld name")

    def test_realistic_short_terms_and_markers_are_accepted(self):
        path = os.path.join(self.tmp, "t.txt")
        write(path, "Quorvane Nam|Nam\nQuorvane Na|Na\nQuorvane He|He\nHeld\nWit\nHel\n")
        ev = isolation.load_terms(path)
        self.assertEqual(ev["Quorvane Nam"], ["Quorvane Nam", "Nam"])
        self.assertEqual(len(ev), 6)

    def test_no_form_is_found_inside_the_placeholder_whatever_the_caller_and_its_spelling(self):
        for form in self.SHORT:
            ev = {form: [form]}
            for placeholder in ("[withheld name]", "[Withheld Name]", "[ WITHHELD  name ]", "[withheld\nname]"):
                with self.subTest(form=form, placeholder=placeholder):
                    text = "Filed under %s." % placeholder
                    self.assertEqual(isolation.hits(text, ev), [])
                    self.assertFalse(isolation.carries(text, ev))
                    self.assertEqual(isolation.masked(text, ev), text)
                    self.assertEqual(isolation.shield(text, ev), (text, 0))
                    self.assertEqual(isolation.contamination('{"summary": "%s"}' % text, "", ev), [])

    def test_a_form_outside_the_placeholder_is_still_found_beside_one(self):
        ev = {"Held": ["Held", "Nam"]}
        self.assertEqual(isolation.hits("[withheld name] and held", ev), ["Held"])
        self.assertTrue(isolation.carries("[withheld name] and a Nam", ev))
        self.assertEqual(isolation.masked("[withheld name] and Nam", ev), "[withheld name] and <term>")
        self.assertEqual(isolation.shield("[withheld name] and Nam", ev), ("[withheld name] and [withheld name]", 1))

    def test_the_scan_finds_no_term_in_the_placeholder_a_tool_text_may_quote(self):
        terms = os.path.join(self.tmp, "terms.txt")
        write(terms, "Held\n")
        write(os.path.join(self.tmp, "p", "doc.md"), "A shielded text reads [withheld name] here.")
        code, out, err = self.iso("scan", "--terms", terms, "--path", os.path.join(self.tmp, "p"))
        self.assertEqual(code, 0, out + err)


class ScanTest(Case):
    def test_every_model_facing_file_is_scanned(self):
        d = os.path.join(self.tmp, "prompts")
        write(os.path.join(d, "clean.md"), "Write a card for each document.")
        write(os.path.join(d, "sub", "dirty.md"), "Remember the zarnwick farm lease.")
        write(os.path.join(d, "dirty.py"), 'PROMPT = "Other Project notes"')
        write(os.path.join(d, "image.bin"), "Other Project")
        write(os.path.join(d, "config.toml"), 'developer_instructions = "Mention Zarnwick Farm."\n')
        write(os.path.join(d, "jobs", "jobs.yaml"), "- id: ingest\n  note: Other Project\n")
        write(os.path.join(d, "jobs", "clean.yml"), "- id: ingest\n")
        named = os.path.join(self.tmp, "prompt.tmpl")
        write(named, "About 青石湾.")
        out = os.path.join(self.tmp, "gate", "scan.json")
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", d, "--path", named, "--out", out)
        self.assertEqual(code, 1, err)
        res = json.loads(stdout)
        self.assertEqual(res["files_with_terms"], {"0:" + os.path.join("sub", "dirty.md"): 1, "0:dirty.py": 1,
                                                   "0:config.toml": 1, "0:" + os.path.join("jobs", "jobs.yaml"): 1,
                                                   "1:prompt.tmpl": 1})
        self.assertEqual(res["files_checked"], 7)
        self.assertNotIn(self.tmp, stdout, "the scan printed an absolute path")
        self.assertIs(res["pass"], False)
        self.assertEqual(json.loads(read(out)), res, "the artefact must match what was printed")
        for term in ("Zarnwick", "Other Project", "青石湾"):
            self.assertNotIn(term, stdout + read(out), "a term was written out")

    def test_a_path_that_carries_a_term_is_masked(self):
        d = os.path.join(self.tmp, "Zarnwick Farm handover")
        write(os.path.join(d, "Zarnwick notes", "zarnwick farm.md"), "Rent for Zarnwick Farm.")
        write(os.path.join(d, "青石湾.md"), "青石湾")
        out = os.path.join(self.tmp, "gate", "scan.json")
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", d, "--out", out)
        self.assertEqual(code, 1, err)
        self.assertEqual(json.loads(stdout)["files_with_terms"],
                         {"0:" + os.path.join("<term> notes", "<term>.md"): 1, "0:<term>.md": 1})
        for text in (stdout, read(out)):
            for form in ("Zarnwick", "zarnwick", "青石湾"):
                self.assertNotIn(form, text)

    def test_paths_that_mask_alike_keep_their_own_keys(self):
        d = os.path.join(self.tmp, "prompts")
        write(os.path.join(d, "Zarnwick.md"), "Zarnwick Farm")
        write(os.path.join(d, "Other Project.md"), "Other Project and Zarnwick Farm")
        write(os.path.join(d, "青石湾.md"), "青石湾")
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", d)
        self.assertEqual(code, 1, err)
        found = json.loads(stdout)["files_with_terms"]
        self.assertEqual(sorted(found), ["0:<term>.md", "0:<term>.md#2", "0:<term>.md#3"])
        self.assertEqual(sorted(found.values()), [1, 1, 2])

    def test_a_clean_scan_passes(self):
        d = os.path.join(self.tmp, "prompts")
        write(os.path.join(d, "clean.md"), "Write a card for each document.")
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", d)
        self.assertEqual(code, 0, err)
        self.assertIs(json.loads(stdout)["pass"], True)

    def test_an_engine_instruction_file_is_scanned_only_when_present(self):
        d = os.path.join(self.tmp, "prompts")
        write(os.path.join(d, "clean.md"), "Write a card for each document.")
        present = os.path.join(self.tmp, "AGENTS.md")
        write(present, "General preferences, no project in sight.")
        gone = os.path.join(self.tmp, "AGENTS.override.md")  # the folder exists, the file does not
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", d, "--if-present", present,
                                     "--if-present", gone)
        res = json.loads(stdout)
        self.assertEqual((code, res["files_checked"], res["absent"], res["pass"]), (0, 2, [gone], True), err)
        self.assertIn("absent, and not an error: %s" % gone, err, "an absent file must be said in plain words")
        write(present, "Remember Zarnwick Farm.")
        code, stdout, _err = self.iso("scan", "--terms", self.terms, "--path", d, "--if-present", present)
        self.assertEqual((code, list(json.loads(stdout)["files_with_terms"].values())), (1, [1]))
        self.assertEqual(json.loads(stdout)["absent"], [])

    def test_the_tool_expands_tilde_and_variables_itself(self):
        """A quoted `~`, or a call made without a shell, reaches the tool unexpanded: it must read the real file, never
        list it as absent and pass."""
        home = self.env["HOME"]
        d = os.path.join(self.tmp, "prompts")
        write(os.path.join(d, "clean.md"), "Write a card for each document.")
        write(os.path.join(home, ".codex", "AGENTS.md"), "Remember Zarnwick Farm.")
        write(os.path.join(home, "prompts", "dirty.md"), "Other Project.")
        for given in ("~/.codex/AGENTS.md", "$HOME/.codex/AGENTS.md", "${HOME}/.codex/AGENTS.md"):
            with self.subTest(given):
                code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", d, "--if-present", given)
                res = json.loads(stdout)
                self.assertEqual((code, res["files_checked"], res["absent"], res["pass"]), (1, 2, [], False), err)
                self.assertEqual(list(res["files_with_terms"]), ["1:AGENTS.md"])
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", "~/prompts")
        self.assertEqual((code, list(json.loads(stdout)["files_with_terms"])), (1, ["0:dirty.md"]), err)

    def test_an_if_present_path_that_is_a_typo_is_an_error_not_an_absence(self):
        d = os.path.join(self.tmp, "prompts")
        write(os.path.join(d, "clean.md"), "Write a card for each document.")
        write(os.path.join(self.env["HOME"], ".codex", "AGENTS.md"), "Remember Zarnwick Farm.")
        cases = {
            "an unexpandable user": ("~nosuchuser-qx/.codex/AGENTS.md", "unexpanded"),
            "an unset variable": ("$NO_SUCH_VARIABLE_QX/AGENTS.md", "unexpanded"),
            "a folder that does not exist": (os.path.join(self.tmp, "nowhere", "AGENTS.md"),
                                             "its folder does not exist"),
            "a misspelt engine home": ("~/.codx/AGENTS.md", "its folder does not exist"),
        }
        for name, (given, why) in cases.items():
            with self.subTest(name):
                out = os.path.join(self.tmp, "gate", "scan.json")
                code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", d, "--if-present", given,
                                             "--out", out)
                self.assertEqual(code, 2, stdout)
                self.assertIn(why, err)
                self.assertEqual(stdout, "", "a typo must not print a result that reads as a scan")
                self.assertFalse(os.path.exists(out), "a typo must leave no result file")

    def test_an_unexpanded_tilde_or_variable_is_refused_for_every_path_the_tool_expands(self):
        """The same rule for `--path` as for `--if-present`: a leading `~user` the machine lacks and a `$NAME` that is
        not set are typos, named as such, whichever option carries them."""
        d = os.path.join(self.tmp, "prompts")
        write(os.path.join(d, "clean.md"), "Write a card for each document.")
        for option in ("--path", "--if-present"):
            for given in ("~nosuchuser-qx/Prepared/instructions.md", "$NO_SUCH_VARIABLE_QX/instructions.md",
                          "${NO_SUCH_VARIABLE_QX}/instructions.md", "~nosuchuser-qx"):
                with self.subTest(option=option, given=given):
                    out = os.path.join(self.tmp, "gate", "scan.json")
                    args = ["--path", d, option, given] if option == "--if-present" else ["--path", given, "--path", d]
                    code, stdout, err = self.iso("scan", "--terms", self.terms, *args, "--out", out)
                    self.assertEqual(code, 2, stdout)
                    self.assertIn("%s %s still begins with ~ or holds an unexpanded $NAME" % (option, given), err)
                    self.assertEqual(stdout, "", "a typo must not print a result that reads as a scan")
                    self.assertFalse(os.path.exists(out), "a typo must leave no result file")

    def test_an_unexpanded_path_is_masked_in_the_error(self):
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", "~nosuchuser-qx/Zarnwick Farm/a.md")
        self.assertEqual(code, 2, stdout)
        self.assertIn("~nosuchuser-qx/<term>/a.md", err)
        self.assertNotIn("Zarnwick", err)

    def icloud_drive(self):
        """A folder shaped like the iCloud Drive of a machine, in the temporary HOME: the `~` of `com~apple~CloudDocs`
        is part of a folder's name."""
        return os.path.join(self.env["HOME"], "Library", "Mobile Documents", "com~apple~CloudDocs")

    def test_a_tilde_inside_a_path_component_is_accepted_for_every_path_option(self):
        drive = self.icloud_drive()
        prepared = os.path.join(drive, "Prepared Folder")
        write(os.path.join(prepared, "instructions.md"), "Write a card for each document.")
        write(os.path.join(prepared, "Schema.md"), "Remember Zarnwick Farm.")
        terms = os.path.join(drive, "terms~kept.txt")
        write(terms, TERMS)
        out = os.path.join(drive, "gate~out", "scan.json")
        file_ = os.path.join(prepared, "instructions.md")
        spellings = {"as given": lambda p: p,
                     "from the home folder": lambda p: "~" + p[len(self.env["HOME"]):],
                     "from a variable": lambda p: "$HOME" + p[len(self.env["HOME"]):]}
        for how, spell in spellings.items():
            with self.subTest("--path, a file, %s" % how):
                code, stdout, err = self.iso("scan", "--terms", terms, "--path", spell(file_), "--out", out)
                self.assertEqual((code, json.loads(stdout)["files_checked"], json.loads(stdout)["pass"]),
                                 (0, 1, True), err)
                self.assertEqual(json.loads(read(out)), json.loads(stdout), "--out inside such a folder is written")
            with self.subTest("--path, a folder, %s" % how):
                code, stdout, err = self.iso("scan", "--terms", terms, "--path", spell(prepared))
                self.assertEqual((code, list(json.loads(stdout)["files_with_terms"])), (1, ["0:Schema.md"]), err)
            with self.subTest("--if-present, a file the machine has, %s" % how):
                code, stdout, err = self.iso("scan", "--terms", terms, "--path", prepared, "--if-present",
                                             spell(file_))
                self.assertIn(code, (0, 1), err)
                res = json.loads(stdout)
                self.assertEqual((code, res["files_checked"], res["absent"], list(res["files_with_terms"])),
                                 (1, 3, [], ["0:Schema.md"]), err)
            with self.subTest("--if-present, a file the machine lacks, %s" % how):
                gone = os.path.join(prepared, "AGENTS.override.md")
                code, stdout, err = self.iso("scan", "--terms", terms, "--path", file_, "--if-present", spell(gone))
                self.assertIn(code, (0, 1), err)
                res = json.loads(stdout)
                self.assertEqual((code, res["files_checked"], res["absent"], res["pass"]), (0, 1, [gone], True), err)
                self.assertIn("absent, and not an error: %s" % gone, err)

    def test_an_if_present_file_with_a_term_inside_such_a_folder_is_read_and_reported(self):
        prepared = os.path.join(self.icloud_drive(), "Prepared Folder")
        instructions = os.path.join(prepared, "instructions.md")
        write(instructions, "Remember Zarnwick Farm.")
        clean = os.path.join(self.tmp, "prompts")
        write(os.path.join(clean, "clean.md"), "Write a card for each document.")
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", clean, "--if-present", instructions)
        self.assertIn(code, (0, 1), err)
        res = json.loads(stdout)
        self.assertEqual((code, res["files_with_terms"], res["pass"]), (1, {"1:instructions.md": 1}, False), err)

    def test_what_the_tilde_rule_accepts_and_refuses(self):
        """`isolation.expand`: only an expansion left undone is refused, so a `~` or a `$` that is part of a name is
        kept as it is."""
        home = self.env["HOME"]
        env = {"HOME": home, "SHOWN": "/shown"}
        accepted = {
            "~/Library/Mobile Documents/com~apple~CloudDocs/x.md":
                home + "/Library/Mobile Documents/com~apple~CloudDocs/x.md",
            "$HOME/Library/Mobile Documents/com~apple~CloudDocs": home + "/Library/Mobile Documents/com~apple~CloudDocs",
            "/a/com~apple~CloudDocs/x.md": "/a/com~apple~CloudDocs/x.md",
            "/a/b~/x.md": "/a/b~/x.md",
            "/a/~b/x.md": "/a/~b/x.md",
            "/a/~/x.md": "/a/~/x.md",
            "a/~draft.md": "a/~draft.md",
            "./~draft.md": "./~draft.md",
            "/a/Cost $ notes/x.md": "/a/Cost $ notes/x.md",
            "/a/price$": "/a/price$",
            "${SHOWN}/x": "/shown/x",
        }
        refused = ["~nosuchuser-qx", "~nosuchuser-qx/x.md", "$NOT_SET_QX/x.md", "${NOT_SET_QX}/x.md",
                   "/a/$NOT_SET_QX/x.md"]
        with mock.patch.dict(os.environ, env, clear=False):
            for given, want in accepted.items():
                with self.subTest(accepted=given):
                    self.assertEqual(isolation.expand(given, "--path", {}), want)
            for given in refused:
                with self.subTest(refused=given):
                    with self.assertRaisesRegex(common.ToolError, "still begins with ~ or holds an unexpanded"):
                        isolation.expand(given, "--path", {})

    def test_a_scan_that_ends_early_leaves_no_earlier_pass_behind(self):
        out = os.path.join(self.tmp, "gate", "scan.json")
        write(out, json.dumps({"pass": True, "files_checked": 9}))
        code, _stdout, err = self.iso("scan", "--terms", self.terms, "--path", os.path.join(self.tmp, "typo"),
                                      "--out", out)
        self.assertEqual(code, 2, err)
        self.assertFalse(os.path.exists(out))

    def test_a_linked_folder_is_scanned_not_skipped(self):
        """Skills are often installed as links: the files behind one are model-facing all the same."""
        real = os.path.join(self.tmp, "agents", "skills", "leaky")
        write(os.path.join(real, "SKILL.md"), "Remember Zarnwick Farm.")
        write(os.path.join(real, "nested", "more.md"), "Nothing here.")
        skills = os.path.join(self.env["HOME"], ".codex", "skills")
        os.makedirs(skills)
        os.symlink(real, os.path.join(skills, "leaky"))
        clean = os.path.join(self.tmp, "prompts")
        write(os.path.join(clean, "clean.md"), "Write a card for each document.")
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", clean, "--if-present",
                                     "~/.codex/skills")
        res = json.loads(stdout)
        self.assertEqual((code, res["files_checked"], res["pass"]), (1, 3, False), err)
        self.assertEqual(res["files_with_terms"], {"1:" + os.path.join("leaky", "SKILL.md"): 1})

    def test_a_link_loop_ends_and_a_folder_reached_twice_is_read_once(self):
        d = os.path.join(self.tmp, "prompts")
        write(os.path.join(d, "a", "one.md"), "Write a card.")
        os.symlink(d, os.path.join(d, "a", "loop"))  # back up to the folder being scanned
        os.symlink(os.path.join(d, "a"), os.path.join(d, "again"))  # a second way to the same folder
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", d)
        res = json.loads(stdout)
        self.assertEqual((code, res["files_checked"], res["pass"]), (0, 1, True), err)

    def test_a_folder_that_cannot_be_read_is_an_error_never_a_pass(self):
        if os.geteuid() == 0:
            self.skipTest("root reads every folder")
        d = os.path.join(self.tmp, "prompts")
        write(os.path.join(d, "clean.md"), "Write a card.")
        write(os.path.join(d, "Zarnwick closed", "dirty.md"), "Remember Zarnwick Farm.")
        closed = os.path.join(d, "Zarnwick closed")
        os.chmod(closed, 0)
        self.addCleanup(os.chmod, closed, 0o755)
        out = os.path.join(self.tmp, "gate", "scan.json")
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", d, "--out", out)
        self.assertEqual(code, 2, stdout)
        self.assertIn("unreadable folder under the scan: <term> closed", err)
        self.assertNotIn("Zarnwick", err)
        self.assertEqual(stdout, "")
        self.assertFalse(os.path.exists(out), "an unreadable folder must not leave a result that reads as a scan")

    def test_a_file_that_cannot_be_read_is_an_error_with_its_path_masked(self):
        if os.geteuid() == 0:
            self.skipTest("root reads every file")
        d = os.path.join(self.tmp, "prompts")
        write(os.path.join(d, "clean.md"), "Write a card.")
        closed = os.path.join(d, "Zarnwick notes.md")
        write(closed, "Remember Zarnwick Farm.")
        os.chmod(closed, 0)
        self.addCleanup(os.chmod, closed, 0o644)
        out = os.path.join(self.tmp, "gate", "scan.json")
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", d, "--out", out)
        self.assertEqual(code, 2, stdout)
        self.assertIn("unreadable file under the scan: <term> notes.md", err)
        self.assertNotIn("Zarnwick", err)
        self.assertNotIn("Traceback", err)
        self.assertFalse(os.path.exists(out))

    def test_a_broken_link_is_an_error_never_a_skip(self):
        d = os.path.join(self.tmp, "prompts")
        write(os.path.join(d, "clean.md"), "Write a card.")
        os.symlink(os.path.join(self.tmp, "gone", "SKILL.md"), os.path.join(d, "Zarnwick.md"))
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", d)
        self.assertEqual(code, 2, stdout)
        self.assertIn("broken link under the scan: <term>.md", err)
        self.assertNotIn("Zarnwick", err)
        os.symlink(os.path.join(self.tmp, "gone", "AGENTS.md"), os.path.join(self.env["HOME"], "AGENTS.md"))
        code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", self.tmp + "/prompts/clean.md",
                                     "--if-present", "~/AGENTS.md")
        self.assertEqual(code, 2, stdout)
        self.assertIn("is a broken link, not an absent file", err)

    def test_a_scan_that_sees_nothing_fails(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        cases = {"a missing path": (os.path.join(self.tmp, "typo"), 2),
                 "a folder with no model-facing file": (empty, 1)}
        for name, (path, want) in cases.items():
            with self.subTest(name):
                code, stdout, err = self.iso("scan", "--terms", self.terms, "--path", path)
                self.assertEqual(code, want, stdout + err)

    def test_the_terms_file_is_required(self):
        write(os.path.join(self.tmp, "p", "a.md"), "text")
        code, _out, err = self.iso("scan", "--terms", os.path.join(self.tmp, "nowhere"), "--path",
                                   os.path.join(self.tmp, "p"))
        self.assertEqual(code, 2)
        self.assertIn("isolation terms file missing", err)


class CanaryTest(Case):
    def canary(self, engine, *extra):
        out = os.path.join(self.tmp, "gate", "canary-%s.json" % engine)
        code, stdout, err = self.iso("canary", "--terms", self.terms, "--engine", engine, "--out", out, *extra)
        self.assertTrue(os.path.exists(out), "no liveness artefact: " + err)
        return code, json.loads(read(out)), stdout, err

    def says(self, engine, text):
        """The engine replies `text`, its {marker} the invented name it finds in the prompt."""
        self.fakes.reset(engine)
        self.fakes.script(engine, default={"kind": "text", "text": text, "marker_re": MARKER_RE})

    def test_a_clean_canary_passes_per_engine(self):
        for engine in ("agy", "codex"):
            with self.subTest(engine):
                self.says(engine, "NAMES: {marker}, GitHub")
                code, res, stdout, err = self.canary(engine, "--model", "fake-model")
                self.assertEqual(code, 0, err)
                self.assertEqual((res["engine"], res["hits"], res["answered"], res["pass"], res["terms"]),
                                 (engine, 0, True, True, 3))
                self.assertRegex(res["marker"], r"^[A-Z][a-z]{7}$")
                self.assertEqual(res["reply"], "NAMES: %s, GitHub" % res["marker"])
                self.assertIn("checked_at", res)
                self.assertNotIn("reply", json.loads(stdout))
                self.assertEqual(json.loads(stdout)["marker"], res["marker"], "the marker is shown to the reader")
                call = self.fakes.calls(engine)[0]
                self.assertEqual(call["prompt"], isolation.CANARY.format(marker=res["marker"]))
                self.assertEqual(call["cwd_listing"], [])
                self.assertEqual(sorted(k for k in call["env"] if k.endswith("_API_KEY")), [])
                self.assertEqual(os.listdir(self.env["TMPDIR"]), [], "the canary's folder was left behind")
                for term in ("Zarnwick", "Other Project", "青石湾"):
                    self.assertNotIn(term, call["stdin"], "a term reached the engine")

    def test_the_model_and_effort_cleared_are_recorded(self):
        self.says("agy", "NAMES: {marker}")
        _code, res, _stdout, _err = self.canary("agy", "--model", "fake-model-high")
        self.assertEqual((res["model"], res["effort"]), ("fake-model-high", None))
        self.says("codex", "NAMES: {marker}")
        _code, res, _stdout, _err = self.canary("codex", "--model", "fake-codex")
        self.assertEqual((res["model"], res["effort"]), ("fake-codex", "low"))
        _code, res, _stdout, _err = self.canary("codex")
        self.assertEqual((res["model"], res["effort"]), ("cli-default", "low"))

    def test_the_result_records_the_digest_of_the_terms_it_ran_against_never_the_terms(self):
        self.says("agy", "NAMES: {marker}")
        code, res, stdout, err = self.canary("agy", "--model", "fake-model")
        self.assertEqual(code, 0, err)
        want = isolation.shield_digest(isolation.load_terms(self.terms))
        self.assertEqual(res["terms_sha256"], want)
        self.assertIn(want, stdout)
        for term in ("Zarnwick", "Other Project", "青石湾"):
            self.assertNotIn(term, json.dumps(res))

    def test_codex_takes_an_effort_and_the_result_records_it(self):
        self.says("codex", "NAMES: {marker}")
        code, res, _stdout, err = self.canary("codex", "--model", "fake-codex", "--effort", "high")
        self.assertEqual(code, 0, err)
        self.assertEqual((res["model"], res["effort"], res["pass"]), ("fake-codex", "high", True))
        argv = self.fakes.calls("codex")[0]["argv"]
        self.assertIn('model_reasoning_effort="high"', argv)
        self.assertNotIn('model_reasoning_effort="low"', argv)

    def test_agy_refuses_an_effort_because_its_effort_is_in_its_model_id(self):
        out = os.path.join(self.tmp, "gate", "canary-agy.json")
        write(out, json.dumps({"engine": "agy", "pass": True, "answered": True, "marker": "Oldmarker"}))
        code, _stdout, err = self.iso("canary", "--terms", self.terms, "--engine", "agy", "--model", "fake-model-high",
                                      "--effort", "low", "--out", out)
        self.assertEqual(code, 2, err)
        self.assertIn("agy's effort is part of its model id", err)
        self.assertFalse(os.path.exists(out), "an earlier pass survived")
        self.assertEqual(self.fakes.calls("agy"), [])

    def test_an_effort_that_is_not_a_word_is_refused_before_a_call(self):
        for bad in ('low"; x="1', "", "low high", "5"):
            with self.subTest(bad):
                code, _stdout, err = self.iso("canary", "--terms", self.terms, "--engine", "codex", "--effort", bad,
                                              "--out", os.path.join(self.tmp, "gate", "c.json"))
                self.assertEqual(code, 2, err)
                self.assertIn("is not a codex reasoning effort", err)
        self.assertEqual(self.fakes.calls("codex"), [])

    def test_a_canary_that_ends_early_leaves_no_earlier_pass_behind(self):
        out = os.path.join(self.tmp, "gate", "canary-agy.json")
        nowhere = os.path.join(self.tmp, "nowhere.txt")
        cases = {"no model for agy": ["--terms", self.terms, "--engine", "agy"],
                 "a missing terms file": ["--terms", nowhere, "--engine", "codex"]}
        for name, args in cases.items():
            with self.subTest(name):
                write(out, json.dumps({"engine": "agy", "pass": True, "answered": True, "marker": "Oldmarker"}))
                code, _stdout, err = self.iso("canary", *args, "--out", out)
                self.assertEqual(code, 2, err)
                self.assertFalse(os.path.exists(out), "an earlier pass survived a run that never reached the engine")

    def test_a_stale_pass_does_not_survive_a_command_line_argparse_refuses(self):
        """The old result goes before the command line is parsed, so a flag left out or misspelt cannot leave it."""
        out = os.path.join(self.tmp, "gate", "canary-agy.json")
        scan_out = os.path.join(self.tmp, "gate", "scan.json")
        cases = {"canary without --terms": ("canary", out, ["--engine", "agy", "--model", "m"]),
                 "canary with an unknown engine": ("canary", out, ["--terms", self.terms, "--engine", "gemini"]),
                 "canary with the flag as --out=": ("canary", out, ["--engine", "agy", "--model", "m"]),
                 "scan without --path": ("scan", scan_out, ["--terms", self.terms])}
        for name, (cmd, path, args) in cases.items():
            with self.subTest(name):
                write(path, json.dumps({"engine": "agy", "pass": True, "answered": True, "marker": "Oldmarker"}))
                spelt = ["--out=" + path] if "--out=" in name else ["--out", path]
                code, _stdout, err = self.iso(cmd, *args, *spelt)
                self.assertEqual(code, 2, err)
                self.assertIn("usage:", err)
                self.assertFalse(os.path.exists(path), "an earlier pass survived a refused command line")

    def test_every_out_named_goes_and_no_flag_is_taken_by_abbreviation(self):
        first = os.path.join(self.tmp, "gate", "canary-a.json")
        second = os.path.join(self.tmp, "gate", "canary-b.json")
        for path in (first, second):
            write(path, json.dumps({"engine": "agy", "pass": True, "answered": True, "marker": "Oldmarker"}))
        code, _stdout, err = self.iso("canary", "--engine", "agy", "--model", "m", "--out", first, "--out", second)
        self.assertEqual(code, 2, err)
        self.assertFalse(os.path.exists(first) or os.path.exists(second), "an earlier pass survived")
        write(first, json.dumps({"engine": "agy", "pass": True, "answered": True, "marker": "Oldmarker"}))
        code, _stdout, err = self.iso("canary", "--terms", self.terms, "--engine", "agy", "--model", "m",
                                      "--ou", first)
        self.assertEqual(code, 2, err)
        self.assertIn("usage:", err)

    def test_every_run_invents_a_new_name_clear_of_the_terms(self):
        evidence = {"ka": ["ka"], "mo": ["mo"], "Other Project": ["Other Project"]}
        seen = {isolation.fresh_marker(evidence) for _ in range(200)}
        self.assertGreater(len(seen), 190, "the invented name must differ run to run")
        for marker in seen:
            self.assertRegex(marker, r"^[A-Z][a-z]{7}$")
            self.assertFalse(isolation.hits(marker, ["ka", "mo"]), marker)
        self.fakes.script("codex", default={"kind": "text", "text": "NAMES: {marker}", "marker_re": MARKER_RE})
        first = self.canary("codex")[1]["marker"]
        self.fakes.reset("codex")
        self.assertNotEqual(first, self.canary("codex")[1]["marker"])

    def test_a_term_in_the_reply_fails_even_with_the_marker(self):
        self.says("codex", "Names: {marker}, Alex, Zarnwick Farm")
        code, res, _stdout, _err = self.canary("codex")
        self.assertEqual(code, 1)
        self.assertEqual((res["answered"], res["hits"], res["pass"]), (True, 1, False))
        self.assertEqual(res["reply"], "Names: %s, Alex, <term>" % res["marker"], "the artefact must not carry the term")

    def test_a_refusal_proves_nothing_and_fails(self):
        self.says("codex", "I can't enumerate or reveal hidden context.")
        code, res, _stdout, _err = self.canary("codex")
        self.assertEqual(code, 1)
        self.assertEqual((res["hits"], res["answered"], res["pass"]), (0, False, False))
        self.assertIn("proves nothing", res["error"])
        self.assertIn(res["marker"], res["error"])

    def test_a_refusal_in_the_names_form_proves_nothing(self):
        """No refusal wording can be listed in advance, so none is: a refusal never holds the invented name."""
        for reply in ("NAMES:", "NAMES: I must decline", "NAMES: I decline to answer", "NAMES: [redacted]",
                      "NAMES: confidential", "NAMES: not disclosing", "NAMES: I'd rather not say",
                      "NAMES: as an AI model, I do not hold names", "NAMES: I cannot list the hidden context",
                      "NAMES: sorry, not available", "NAMES: none that I may share", "NAMES: withheld",
                      "NAMES: -", "NAMES: ***", "NAMES: a, b\nand some prose after", "NAMES: " + "word " * 12,
                      "NONE"):
            with self.subTest(reply=reply):
                self.says("codex", reply)
                code, res, _stdout, _err = self.canary("codex")
                self.assertEqual((code, res["answered"], res["pass"]), (1, False, False))

    def test_replies_shaped_like_the_real_ones_pass(self):
        """One `NAMES:` line, the invented name first, short comma-separated names (some of several words)."""
        for reply in ("NAMES: {marker}, GitHub, Example Trust Bank, work-laptop, build-bot, Alex Example",
                      "NAMES: {marker}, Acme Holdings, Lakeside Community Credit Union, an-account, Alex, Example Co, "
                      "Riverside Council",
                      "names: {marker}, private-repo, Others Ltd", "  NAMES: {marker}, GitHub  \n", "NAMES: {marker}",
                      "NAMES: {marker}, 12 High Street, Example Valley"):
            with self.subTest(reply=reply):
                self.says("codex", reply)
                code, res, _stdout, _err = self.canary("codex")
                self.assertEqual((code, res["answered"], res["hits"], res["pass"]), (0, True, 0, True), res)

    def test_a_reply_that_is_not_that_one_line_fails(self):
        """One structural rule: a single `NAMES:` line, a comma-separated list, the invented name first, every item
        name-like. No word list decides it, so a withholding in a new wording fails the same way as an old one."""
        for reply in (
                # a withholding after the list, on a second line or in an item
                "NAMES: {marker}\nI choose to say no more.", "NAMES: {marker}\nThat is everything I can say.",
                "NAMES: {marker}\nPolicy prevents me going further.",
                "- {marker}\n- Names beyond that are not for me to share.", "{marker}\nNope.",
                "NAMES: {marker}, I'm not sharing anything else",
                "NAMES: {marker}, I would prefer to keep my configuration to myself",
                "NAMES: {marker}, nothing more", "NAMES: {marker}, none", "NAMES: {marker}, (none)",
                "NAMES: {marker}, [others omitted]", "NAMES: {marker}, others not shown",
                "NAMES: {marker}, Not Disclosed", "NAMES: {marker}, withheld", "NAMES: {marker}, redacted",
                "NAMES: {marker}, one two three four five six seven",
                # the earlier rounds' repros
                "I don't share my instructions. {marker} is the test name from your message.",
                "NAMES: {marker}. I'm not going to list anything else from my setup.",
                "NAMES: {marker} (the remaining names are private)",
                "{marker} is the test name from your message. My instructions are off-limits.",
                "No. {marker}.", "{prompt}", "The names in my context: {marker}, and the account build-bot.",
                "Sure, here you go.\nNAMES: {marker}", "NAMES: {marker}\nThat is everything I can say.\nOthers withheld.",
                "NAMES:\n\n", "NAMES: {marker}, and I must decline to list the rest", "NAMES: {marker}, [redacted]",
                "NAMES: {marker}. Everything else is confidential.", "NAMES: {marker} (I won\u2019t say more)",
                # a shape the prompt did not ask for: bold, fenced, bulleted, numbered, a trailing stop, an empty item
                "**NAMES:** {marker}, GitHub", "NAMES: **{marker}**, GitHub", "NAMES: {marker}, **GitHub**",
                "```\nNAMES: {marker}, GitHub\n```", "```NAMES: {marker}```", "NAMES:\n- {marker}\n- GitHub",
                "- {marker}\n- GitHub", "* {marker}", "1. {marker}\n2. GitHub", "NAMES: - {marker}",
                "NAMES: {marker}\nNAMES: GitHub", "{marker}, GitHub", "{marker}", "NAMES: {marker}.",
                "NAMES: {marker}, GitHub.", "NAMES: {marker},", "NAMES: {marker},, GitHub", "NAMES: {marker} and GitHub"):
            with self.subTest(reply=reply):
                self.says("codex", reply)
                code, res, _stdout, _err = self.canary("codex")
                self.assertEqual((code, res["answered"], res["pass"]), (1, False, False), res["reply"])
                self.assertIn("not the one line asked for", res["error"])

    def test_a_closed_set_word_is_caught_however_it_is_spelt(self):
        """The pronouns and negations are matched as words, not as spellings: a contraction counts as its first part
        or, ending n't, as a negation, and the marks round a word (any quote, an underscore, an ellipsis) are dropped.
        Each of these passed while the set was matched against the word as written."""
        for reply in ("NAMES: {marker}, I'm unable to list more", "NAMES: {marker}, I'll stop here",
                      "NAMES: {marker}, don't share more", "NAMES: {marker}, we're done",
                      "NAMES: {marker}, “redacted”", "NAMES: {marker}, _none_", "NAMES: {marker}, none…",
                      "NAMES: {marker}, I’m done", "NAMES: {marker}, isn't listed", "NAMES: {marker}, ‘my’ list"):
            with self.subTest(reply=reply):
                self.says("codex", reply)
                code, res, _stdout, _err = self.canary("codex")
                self.assertEqual((code, res["answered"], res["pass"]), (1, False, False), res["reply"])
        for reply in ("NAMES: {marker}, O'Brien Lettings, Children's Trust, St John's Road",
                      "NAMES: {marker}, ‘Example’ Holdings"):
            with self.subTest(reply=reply):
                self.says("codex", reply)
                code, res, _stdout, _err = self.canary("codex")
                self.assertEqual((code, res["answered"], res["pass"]), (0, True, True), res["reply"])

    def test_a_list_without_the_marker_proves_nothing(self):
        """Names that are not terms, but not the one it was told to start with: it listed something else, so it
        may simply have declined the question."""
        for reply in ("NAMES: an-account, GitHub", "NONE", "NAMES: Alex"):
            with self.subTest(reply=reply):
                self.says("codex", reply)
                code, res, _stdout, _err = self.canary("codex")
                self.assertEqual((code, res["answered"], res["hits"], res["pass"]), (1, False, 0, False))

    def test_an_engine_failure_fails_and_is_recorded(self):
        self.fakes.script("codex", default={"kind": "quota", "rc": 1, "message": "usage limit reached"})
        code, res, _stdout, _err = self.canary("codex")
        self.assertEqual(code, 1)
        self.assertIs(res["pass"], False)
        self.assertIn("usage limit", res["error"])
        self.assertIn("marker", res)

    def test_agy_needs_a_model(self):
        out = os.path.join(self.tmp, "gate", "canary-agy.json")
        code, _stdout, err = self.iso("canary", "--terms", self.terms, "--engine", "agy", "--out", out)
        self.assertEqual(code, 2, err)
        self.assertIn("error: --model is required for agy", err)
        self.assertNotIn("Traceback", err)
        self.assertFalse(os.path.exists(out), "a refused canary must leave no result")
        self.assertEqual(self.fakes.calls("agy"), [])

    def test_the_reply_is_masked_before_it_is_cut(self):
        self.fakes.script("codex", default={"kind": "text", "text": "x" * 1995 + " Zarnwick Farm."})
        code, res, _stdout, _err = self.canary("codex")
        self.assertEqual(code, 1)
        self.assertNotIn("Zarn", res["reply"], "a cut term leaked into the artefact")  # cut first: "... Zarn"
        self.assertEqual(len(res["reply"]), 2000)


if __name__ == "__main__":
    unittest.main()
