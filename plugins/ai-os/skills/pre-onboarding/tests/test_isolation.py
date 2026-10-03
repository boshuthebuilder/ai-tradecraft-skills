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

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
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
                           text=True, env=self.env)
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
            "an unexpandable user": ("~nosuchuser-qx/.codex/AGENTS.md", "still holds ~ or $"),
            "an unset variable": ("$NO_SUCH_VARIABLE_QX/AGENTS.md", "still holds ~ or $"),
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
        self.says("codex", "Names: {marker}, Alex, Zarnwick Farm.")
        code, res, _stdout, _err = self.canary("codex")
        self.assertEqual(code, 1)
        self.assertEqual((res["answered"], res["hits"], res["pass"]), (True, 1, False))
        self.assertEqual(res["reply"], "Names: %s, Alex, <term>." % res["marker"], "the artefact must not carry the term")

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

    def test_a_refusal_that_repeats_the_marker_still_fails(self):
        for reply in ("NAMES: {marker}, and I must decline to list the rest", "NAMES: {marker}, [redacted]",
                      "I cannot list my context, but the test name is {marker}.",
                      "NAMES: {marker}. Everything else is confidential.", "NAMES: {marker} (I won\u2019t say more)"):
            with self.subTest(reply=reply):
                self.says("codex", reply)
                code, res, _stdout, _err = self.canary("codex")
                self.assertEqual((code, res["answered"], res["pass"]), (1, False, False))

    def test_an_honest_list_in_any_format_passes(self):
        for reply in ("NAMES: {marker}", "names: {marker}, GitHub, Acme Holdings Pty Ltd, 12 High Street",
                      "NAMES:\n- {marker}\n- Acme Holdings Pty Ltd\n- an account called work-laptop",
                      "* {marker}\n* Lakeside Community Credit Union of Eastern Province", "NAMES: {marker}\nNAMES: GitHub",
                      "The names in my context: {marker}, and the account name build-bot."):
            with self.subTest(reply=reply):
                self.says("codex", reply)
                code, res, _stdout, _err = self.canary("codex")
                self.assertEqual((code, res["answered"], res["hits"], res["pass"]), (0, True, 0, True), res)

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
