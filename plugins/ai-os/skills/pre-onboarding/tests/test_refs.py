"""refs.py: truncated reference numbers repaired from each card's own source text when exactly one candidate matches,
the rest listed for re-carding; no model is called.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests
"""
import hashlib
import json
import os
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
from fake_engines import Fakes, tool_env  # noqa: E402


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def eid(path):
    return hashlib.sha256(path.encode()).hexdigest()


class RefsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="refs_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "Alex Personal")
        os.makedirs(self.root)
        self.work = os.path.join(self.tmp, "work")
        self.cards = os.path.join(self.tmp, "cards")
        self.extract = os.path.join(self.tmp, "extract")
        self.fakes = Fakes(self.tmp)
        self.env = tool_env(self.tmp, self.fakes)
        self.ids = {}
        # restorable: one candidate in its own source, for both the summary's "…" and the reference number
        self.card("01 Identity/Passport.pdf", "Passport number 123454471, issued 2021. Card 55559876.",
                  summary="Passport …4471 renewed.", refs=["passport ending 4471"])
        # ambiguous: two numbers in its own source end the same way
        self.card("02 Finance/Accounts.pdf", "Accounts 12344471 and 99994471.", refs=["account ****4471"])
        # not found: the tail is only in another card's source
        self.card("02 Finance/Card.pdf", "Card statement, no numbers here.", refs=["card ending 9876"])
        # nothing truncated
        self.card("02 Finance/Bank.pdf", "Sort code 20-00-00.", refs=["sort 20-00-00"])

    def card(self, path, source, summary="A document.", refs=()):
        i = eid(path)
        self.ids[path] = i
        rec = {"id": i, "path": path, "class": "document", "status": "ok", "page_count": 1,
               "pages": [{"n": 1, "tier": "text_layer", "text": source}]}
        write(os.path.join(self.extract, i + ".json"), json.dumps(rec))
        c = {"id": i, "title": "Card", "summary": summary,
             "key_facts": {"dates": [], "amounts": [], "reference_numbers": list(refs)},
             "card_meta": {"model": "fake-model", "via": "codex"}}
        write(os.path.join(self.cards, i + ".json"), json.dumps(c, ensure_ascii=False, indent=1))

    def refs(self, *extra, root=None):
        cmd = [sys.executable, os.path.join(TOOLS, "refs.py"), "--root", root or self.root, "--work", self.work,
               "--cards", self.cards, "--extract", self.extract] + list(extra)
        r = subprocess.run(cmd, capture_output=True, text=True, env=self.env)
        self.assertNotIn("ResourceWarning", r.stderr, "refs.py left a file open")
        return r.returncode, r.stdout, r.stderr

    def cards_on_disk(self):
        return {f: read(os.path.join(self.cards, f), "rb") for f in sorted(os.listdir(self.cards))}

    def test_a_dry_run_counts_and_writes_nothing(self):
        before = self.cards_on_disk()
        code, out, err = self.refs()
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"cards_with_truncation": 3, "forms_restored": 2, "forms_ambiguous": 1,
                                           "forms_not_found": 1, "cards_fully_restored": 1, "cards_to_recard": 2})
        self.assertEqual(self.cards_on_disk(), before)
        self.assertFalse(os.path.exists(os.path.join(self.work, "state", "redo_refs.txt")))
        self.assertEqual(self.fakes.calls("agy") + self.fakes.calls("codex"), [], "refs.py must not call a model")

    def test_apply_repairs_from_the_cards_own_source_and_lists_the_rest(self):
        before = self.cards_on_disk()
        code, _out, err = self.refs("--apply")
        self.assertEqual(code, 0, err)
        passport = self.ids["01 Identity/Passport.pdf"]
        fixed = json.loads(read(os.path.join(self.cards, passport + ".json")))
        self.assertEqual(fixed["summary"], "Passport 123454471 renewed.")
        self.assertEqual(fixed["key_facts"]["reference_numbers"], ["passport 123454471"])
        self.assertEqual(fixed["card_meta"]["via"], "codex")
        self.assertEqual(len(fixed["card_meta"]["fixes"]), 1)
        self.assertTrue(fixed["card_meta"]["fixes"][0].startswith("refs_restored_from_source "))
        after = self.cards_on_disk()
        for path in ("02 Finance/Accounts.pdf", "02 Finance/Card.pdf", "02 Finance/Bank.pdf"):
            name = self.ids[path] + ".json"
            self.assertEqual(after[name], before[name], path)
        redo = read(os.path.join(self.work, "state", "redo_refs.txt")).split()
        self.assertEqual(redo, sorted([self.ids["02 Finance/Accounts.pdf"], self.ids["02 Finance/Card.pdf"]]))
        code, out, err = self.refs("--apply")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out).get("forms_restored", 0), 0, "a second run found something to restore")

    def test_a_tail_the_source_shows_masked_is_never_restored(self):
        """The source masks the card number (****1234) and holds a different full number ending 1234: the tail is
        left unresolved and listed for re-carding, not completed from the coincidence."""
        forms = ("****1234", "xxxx-xxxx-1234", "•••• 1234", "…1234", "XXXX XXXX 1234")
        for n, masked_form in enumerate(forms):
            with self.subTest(masked_form):
                path = "02 Finance/Card %d.pdf" % n
                self.card(path, "Card %s. Account 55551234." % masked_form, refs=["card ending 1234"])
                code, out, err = self.refs("--apply")
                self.assertEqual(code, 0, err)
                self.assertEqual(json.loads(out).get("forms_masked_in_source"), 1)
                c = json.loads(read(os.path.join(self.cards, self.ids[path] + ".json")))
                self.assertEqual(c["key_facts"]["reference_numbers"], ["card ending 1234"])
                self.assertIn(self.ids[path], read(os.path.join(self.work, "state", "redo_refs.txt")).split())
                os.remove(os.path.join(self.cards, self.ids[path] + ".json"))

    def test_a_mask_of_another_tail_does_not_block_a_repair(self):
        path = "02 Finance/Card and account.pdf"
        # a lone x (a frame 30 x 1234 mm, a PO Box 1234) is not a mask
        self.card(path, "Card ****9999. Account 55551234. Frame 30 x 1234 mm, PO Box 1234.",
                  refs=["account ending 1234"])
        code, out, err = self.refs("--apply")
        self.assertEqual(code, 0, err)
        self.assertNotIn("forms_masked_in_source", json.loads(out))
        c = json.loads(read(os.path.join(self.cards, self.ids[path] + ".json")))
        self.assertEqual(c["key_facts"]["reference_numbers"], ["account 55551234"])

    def test_other_identifier_policies_are_refused(self):
        write(os.path.join(self.root, "CLAUDE.md"), "# Alex Personal\n\nReference numbers: last four only.\n")
        rb = {"version": 1, "identifiers": "last-four",
              "rulebook_sha256": common.sha256_file(os.path.join(self.root, "CLAUDE.md"))}
        write(os.path.join(self.root, ".familyai", "rulebook.json"), json.dumps(rb))
        before = self.cards_on_disk()
        code, _out, err = self.refs("--apply")
        self.assertEqual(code, 2)
        self.assertIn("'last-four'", err)
        self.assertEqual(self.cards_on_disk(), before)


if __name__ == "__main__":
    unittest.main()
