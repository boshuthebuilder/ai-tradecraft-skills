"""Cards: the batch builder, token budgets, the card schema, the whole-chunk join with halving, cached section notes
and the contamination guard, with fake engines.

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
import types
import unicodedata
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
TIMEOUT = 600  # seconds: a tool that hangs fails its test instead of the run
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import cards  # noqa: E402
import common  # noqa: E402
import engines  # noqa: E402
import isolation  # noqa: E402
from fake_engines import Fakes, tool_env  # noqa: E402

CATEGORIES = common.DEFAULTS["card_categories"]
CARD_SCHEMA_PATH = os.path.join(TOOLS, "schemas", "card.json")
with open(CARD_SCHEMA_PATH, encoding="utf-8") as _f:
    CARD_SCHEMA_TEXT = _f.read().strip()
CUT_STREAM = os.path.join(HERE, "fixtures", "agy", "agy-1.2.16-cut-stream.redacted.jsonl")
CUT_STDERR = os.path.join(HERE, "fixtures", "agy", "agy-1.2.16-cut-stderr.redacted.txt")
CUT = {"kind": "replay", "stdout": CUT_STREAM, "stderr": CUT_STDERR}
TERMS = "# isolation terms for the tests (fictional)\nZarnwick Farm|Zarnwick\nOther Project\n"


# cards.py run with the first engine call followed by the owner excluding a folder, as when the settings are edited while
# the worker runs: `TEST_EXCLUDE_AFTER_FIRST_CALL` is `<twin>|<folder>`.
EXCLUDE_AFTER_FIRST_CALL = (
    "import json, os, runpy, sys\n"
    "sys.path.insert(0, %r)\n"
    "import engines\n"
    "first = engines.Codex.__call__\n"
    "def hooked(self, *args, **kwargs):\n"
    "    got = first(self, *args, **kwargs)\n"
    "    engines.Codex.__call__ = first\n"
    "    twin, folder = os.environ['TEST_EXCLUDE_AFTER_FIRST_CALL'].split('|')\n"
    "    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(twin)), folder), exist_ok=True)\n"
    "    with open(twin, encoding='utf-8') as f:\n"
    "        data = json.load(f)\n"
    "    data['exclude'] = [folder]\n"
    "    with open(twin, 'w', encoding='utf-8') as f:\n"
    "        json.dump(data, f)\n"
    "    return got\n"
    "engines.Codex.__call__ = hooked\n"
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n") % os.path.realpath(TOOLS)


# cards.py run with the quota sleep replaced by the owner excluding a folder: `TEST_EXCLUDE_AT_SLEEP` is `<twin>|<folder>`.
# Only a sleep of a minute or more is the quota wait; nothing sleeps for real.
EXCLUDE_AT_SLEEP = (
    "import json, os, runpy, sys, time\n"
    "def sleeping(seconds):\n"
    "    if seconds < 60:\n"
    "        return\n"
    "    twin, folder = os.environ['TEST_EXCLUDE_AT_SLEEP'].split('|')\n"
    "    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(twin)), folder), exist_ok=True)\n"
    "    with open(twin, encoding='utf-8') as f:\n"
    "        data = json.load(f)\n"
    "    data['exclude'] = [folder]\n"
    "    with open(twin, 'w', encoding='utf-8') as f:\n"
    "        json.dump(data, f)\n"
    "time.sleep = sleeping\n"
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def eid(path):
    return hashlib.sha256(path.encode()).hexdigest()


def card_for(item_id, path="x.pdf", **changes):
    c = {"id": item_id, "doc_type": "Letter", "party": "Alex", "parties": [], "doc_date": "",
         "title": "Card of " + path, "summary": "About " + path + ".",
         "key_facts": {"dates": [], "amounts": [], "reference_numbers": []}, "category": "Other", "language": "en",
         "sensitive": False, "confidence": "high", "look": "", "proposed_name": ""}
    c.update(changes)
    return c


def sent_items(prompt):
    """The items a call was sent: the first JSON value after the heading (agy's prompt carries its schema after it)."""
    return json.JSONDecoder().raw_decode(prompt[prompt.index("\n", prompt.index("Input items (JSON")) + 1:])[0]


def item_count(call):
    m = re.search(r"Input items \(JSON, (\d+) items\)", call["prompt"])
    return int(m.group(1)) if m else None


class StubEngine:
    """An in-process engine: builds a card per item sent, optionally mangled, and records each call."""

    def __init__(self, mangle=None, error=None):
        self.mangle, self.error, self.calls = mangle, error, []

    def __call__(self, prompt, cwd, schema=None):
        items = sent_items(prompt)
        self.calls.append({"prompt": prompt, "cwd": cwd, "listing": sorted(os.listdir(cwd)), "n": len(items),
                           "ids": [it["id"] for it in items], "schema": schema})
        if self.error:
            raise self.error
        # an honest card quotes its own document's text
        out = [card_for(it["id"], it["path"], summary="About %s. %s" % (it["path"], it["text"])) for it in items]
        if self.mangle:
            out = self.mangle(out)
        return json.dumps({"items": out}), {"input_tokens": 1}


def swap_first_two(cs):
    if len(cs) >= 2:
        cs[0]["id"], cs[1]["id"] = cs[1]["id"], cs[0]["id"]
    return cs


def cross_contents(cs):
    """Contents rotated one place, ids and order intact."""
    if len(cs) >= 2:
        ids = [c["id"] for c in cs]
        cs = cs[1:] + cs[:1]
        for c, i in zip(cs, ids):
            c["id"] = i
    return cs


class BudgetAndSchemaTest(unittest.TestCase):
    def test_token_estimate(self):
        self.assertEqual(common.est_tokens("a" * 38), 10)
        self.assertEqual(common.est_tokens("中" * 10), 11)
        self.assertEqual(common.est_tokens("a" * 38 + "é" * 10), 21)
        self.assertEqual(common.est_tokens(""), 0)

    def test_the_card_fields_agree_across_both_schemas(self):
        items = []
        for name in ("card.json", "card_codex.json"):
            with open(os.path.join(TOOLS, "schemas", name), encoding="utf-8") as f:
                item = json.load(f)["properties"]["items"]["items"]
            self.assertEqual(item["required"], list(item["properties"]), name)
            items.append(item)
        agy, codex = items
        self.assertEqual(agy["required"], codex["required"])
        for key, prop in agy["properties"].items():
            self.assertEqual(prop["type"], codex["properties"][key]["type"], key)
        self.assertEqual(cards.CARD_SCHEMA, agy)

    def test_a_complete_card_is_valid(self):
        c = card_for("d1", notes="an extra field is allowed")
        self.assertIs(cards.validate(c, CATEGORIES), c)
        self.assertEqual(c["category"], "Other")

    def test_an_unknown_category_becomes_other(self):
        c = cards.validate(card_for("d1", category="Pets"), CATEGORIES)
        self.assertEqual((c["category"], c["category_raw"]), ("Other", "Pets"))

    def test_a_card_that_breaks_the_schema_is_invalid(self):
        def without(key):
            c = card_for("d1")
            del c[key]
            return c
        cases = {
            "not an object": ["d1"],
            "no summary": without("summary"),
            "no key facts": without("key_facts"),
            "sensitive as text": card_for("d1", sensitive="false"),
            "parties as text": card_for("d1", parties="Robin"),
            "a party that is not text": card_for("d1", parties=["Robin", 3]),
            "key facts without reference numbers": card_for("d1", key_facts={"dates": [], "amounts": []}),
            "key facts as a list": card_for("d1", key_facts=[]),
            "a title that is null": card_for("d1", title=None),
        }
        for name, c in cases.items():
            with self.subTest(name):
                self.assertIsNone(cards.validate(c, CATEGORIES))


class JoinTest(unittest.TestCase):
    """call_chunk: the reply's short ids must be exactly the ids sent, in the order sent, every card valid."""

    ITEMS = [{"id": eid("p%d" % i), "path": "02 Finance/p%d.pdf" % i, "class": "document", "page_count": 1,
              "read": "text_layer", "text": "text %d" % i} for i in range(3)]

    def setUp(self):
        self.cwd = tempfile.mkdtemp(prefix="join_test_")
        self.addCleanup(shutil.rmtree, self.cwd, True)

    def join(self, engine):
        return cards.call_chunk(engine, "INSTRUCTIONS", self.ITEMS, CATEGORIES, "schema.json", self.cwd)

    def test_a_good_reply_is_matched_by_short_ids(self):
        engine = StubEngine()
        got, usage = self.join(engine)
        self.assertEqual(list(got), [it["id"] for it in self.ITEMS])
        for it in self.ITEMS:
            self.assertEqual(got[it["id"]]["id"], it["id"])
            self.assertEqual(got[it["id"]]["title"], "Card of " + it["path"])
        prompt = engine.calls[0]["prompt"]
        self.assertTrue(prompt.startswith(engines.NO_TOOLS + "INSTRUCTIONS"))
        self.assertEqual(engine.calls[0]["ids"], ["d1", "d2", "d3"])
        for it in self.ITEMS:
            self.assertNotIn(it["id"], prompt, "a real id reached the engine")
        self.assertEqual(engine.calls[0]["schema"], "schema.json")

    def test_a_mismatch_rejects_the_whole_chunk(self):
        def dup(cs):
            cs[2]["id"] = "d1"
            return cs

        def not_a_card(cs):
            cs[1] = "d2"
            return cs

        def one_invalid(cs):
            cs[1]["sensitive"] = "no"
            return cs
        cases = {
            "two ids swapped": swap_first_two,
            "the same ids in another order": lambda cs: cs[::-1],
            "one missing": lambda cs: cs[:-1],
            "one extra": lambda cs: cs + [card_for("d4")],
            "an unknown id": lambda cs: cs[:2] + [card_for("d7")],
            "a duplicate id": dup,
            "an entry that is not a card": not_a_card,
            "one card breaking the schema": one_invalid,
            "no items list": lambda cs: {"cards": cs},
        }
        for name, mangle in cases.items():
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    self.join(StubEngine(mangle))

    def test_a_reply_without_json_is_rejected(self):
        with self.assertRaises(ValueError):
            cards.call_chunk(lambda p, c, schema=None: ("I cannot help with that.", None), "I", self.ITEMS,
                             CATEGORIES, None, self.cwd)


BANK, PASSPORT, INVOICE, BILL, LEASE, BUDGET, TAX, POLICY = range(8)


class SiblingFactsTest(unittest.TestCase):
    """call_chunk: a card carrying an identifier (5+ digits once separators are removed, not an amount, a year or a
    date) that a sibling's source holds and its own lacks is a crossed card, even with ids and order intact. Honest
    cards written as templates/card-instructions.md asks must pass."""

    ITEMS = [{"id": eid(path), "path": path, "class": "document", "page_count": 1, "read": "text_layer",
              "text": text} for path, text in [
                  ("02 Finance/Bank statement 2024-03.pdf",
                   "Example Bank plc\nStatement for Alex Example\nAccount 12345678, sort code 01-02-03\n"
                   "Card and account 123456 12345678\nPeriod 1 March 2024 to 31 March 2024\n"
                   "Rent to Example Lettings GBP 1,450.00\nDirect debit to Example Insurance, policy 88123456"),
                  ("01 Identity/Passport renewal 2021/Application form.docx",
                   "Passport renewal application for Alex Example\nSubmitted 2021-05-02\nPrevious passport P0987654"),
                  ("02 Finance/Old invoice.pdf",
                   "Invoice 2022-117 from Robin Trading Ltd to Alex Example\nConsulting, February 2022, GBP 800.00\n"
                   "Paid 2022-03-01"),
                  ("03 Home/Utilities /Electricity bill.pdf",
                   "Example Energy Ltd\nElectricity bill for Alex Example\nBill date 15 March 2O24\n"
                   "Meter read 15/03/24"),
                  ("03 Home/Lease renewal.pages",
                   "Lease renewal for 3 Example Road, signed by Alex Example\n\n"
                   "The new term runs from 1 May 2024 to 30 April 2025 at 1,450 per month"),
                  ("02 Finance/Tax/Budget.numbers",
                   "Household budget prepared by Alex Example\n\nRent 1,450 per month and utilities about 150"),
                  ("02 Finance/Tax/Tax return 2023.pdf", "Self assessment summary for Alex Example"),
                  ("02 Finance/Insurance policy 88123456.pdf", "Home insurance schedule for Alex Example")]]

    def setUp(self):
        self.cwd = tempfile.mkdtemp(prefix="facts_test_")
        self.addCleanup(shutil.rmtree, self.cwd, True)

    def join(self, mangle):
        return cards.call_chunk(StubEngine(mangle), "I", self.ITEMS, CATEGORIES, None, self.cwd)

    @staticmethod
    def edit(i, key, value, sub=None):
        def mangle(cs):
            if sub:
                cs[i]["key_facts"][sub] = value
            else:
                cs[i][key] = value
            return cs
        return mangle

    def test_honest_edits_are_accepted(self):
        e = self.edit
        cases = {
            "an ISO date from OCR text '15 March 2O24'": e(BILL, "doc_date", "2024-03-15"),
            "an ISO date from '15/03/24'": e(BILL, None, ["meter read 2024-03-15"], "dates"),
            "a currency the source lacks": e(LEASE, None, ["GBP 1,450 per month"], "amounts"),
            "a year inferred from context": e(BUDGET, "summary", "Household budget for 2023."),
            "a year alone": e(BUDGET, None, ["2024"], "dates"),
            "look naming a sibling, with its number": e(INVOICE, "look", "Paid from account 12345678; see the "
                                                                         "Bank statement 2024-03.pdf."),
            "a key fact in another case": e(PASSPORT, None, ["PASSPORT p0987654"], "reference_numbers"),
            "a key fact with other separators": e(BANK, None, ["account 1234-5678 sort 01 02 03"],
                                                  "reference_numbers"),
            "digits compared as digits": e(BANK, None, ["card and account 12-34-56 12345678"], "reference_numbers"),
            "an invoice number with another separator": e(INVOICE, None, ["invoice 2022/117"], "reference_numbers"),
            "amounts and dates": e(INVOICE, None, ["GBP 800.00 paid 2022-03-01", "February 2022"], "amounts"),
            "a date from its own path": e(TAX, "doc_date", "2023"),
            "an identifier only its own file name shows (a sibling's text has it too)":
                e(POLICY, None, ["policy 88123456"], "reference_numbers"),
        }
        for name, mangle in cases.items():
            with self.subTest(name):
                got, _usage = self.join(mangle)
                self.assertEqual(len(got), len(self.ITEMS))

    def test_a_real_crossing_is_rejected(self):
        e = self.edit
        cases = {
            "an account number from a sibling": (e(INVOICE, "summary", "Paid from account 12345678."), "d3", "d1"),
            "a passport number from a sibling": (e(BANK, None, ["passport P0987654"], "reference_numbers"),
                                                 "d1", "d2"),
            "an invoice number from a sibling": (e(PASSPORT, None, ["invoice 2022-117"], "reference_numbers"),
                                                 "d2", "d3"),
        }
        for name, (mangle, card, sibling) in cases.items():
            with self.subTest(name):
                with self.assertRaisesRegex(cards.Crossed, "card %s carries an identifier that its own source lacks "
                                                           "and the source of %s holds" % (card, sibling)):
                    self.join(mangle)

    def test_crossings_without_an_identifier_slip_through(self):
        """Documented limits: a sort code (date-shaped), a name or an amount carries no identifier."""
        e = self.edit
        for name, mangle in (("a sort code", e(INVOICE, None, ["sort code 01-02-03"], "reference_numbers")),
                             ("a name", e(BILL, "party", "Example Lettings")),
                             ("an amount", e(PASSPORT, None, ["GBP 800.00"], "amounts"))):
            with self.subTest(name):
                got, _usage = self.join(mangle)
                self.assertEqual(len(got), len(self.ITEMS))

    def test_an_identifier_both_sources_carry_is_accepted(self):
        items = [dict(it, text=it["text"] + " Customer 99990000.") for it in self.ITEMS[:2]]

        def shared(cs):
            cs[0]["summary"] = cs[1]["summary"] = "Customer 99990000."
            return cs
        got, _usage = cards.call_chunk(StubEngine(shared), "I", items, CATEGORIES, None, self.cwd)
        self.assertEqual(len(got), 2)

    def test_a_single_item_is_not_checked(self):
        mangle = self.edit(0, "summary", "Invoice 2022-117 and passport P0987654.")
        got, _usage = cards.call_chunk(StubEngine(mangle), "I", self.ITEMS[:1], CATEGORIES, None, self.cwd)
        self.assertEqual(len(got), 1)

    def test_identifiers(self):
        cases = {"2024-03-15": [], "15/03/24": [], "15 March 2O24": [], "GBP 1,450 per month": [], "for 2023": [],
                 "sort code 01-02-03": [], "202403": [], "20240315": [], "GBP 2,410.00": [], "15.03.2024": [],
                 "P0987654": ["0987654"], "Invoice 2022-117": ["2022117"], "123456": ["123456"],
                 "12-34-56 12345678": ["12345612345678", "12345678"]}
        for text, want in cases.items():
            with self.subTest(text):
                self.assertEqual(sorted(cards.identifiers(text)), want)


class RunItemsTest(unittest.TestCase):
    """run_items: a rejected chunk is retried, then halved, and never applied in part."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="run_items_test_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run_ = types.SimpleNamespace(rb={"card_categories": CATEGORIES}, state=self.tmp)
        self.log = []

    def items(self, n):
        return [{"id": eid("q%d" % i), "path": "q%d.pdf" % i, "class": "document", "page_count": 1,
                 "read": "text_layer", "text": "t"} for i in range(n)]

    def test_a_swapping_engine_is_halved_down_to_single_items(self):
        engine, sink, items = StubEngine(swap_first_two), {}, self.items(4)
        cards.run_items(self.run_, engine, "I", items, None, self.log.append, sink)
        self.assertEqual([c["n"] for c in engine.calls], [4, 4, 4, 2, 2, 2, 1, 1, 2, 2, 2, 1, 1])  # depth first
        self.assertEqual(sorted(sink), sorted(it["id"] for it in items))
        for it in items:
            self.assertEqual(sink[it["id"]]["title"], "Card of " + it["path"])
        cwds = [c["cwd"] for c in engine.calls]
        self.assertEqual(len(set(cwds)), len(cwds), "a working folder was reused")
        self.assertTrue(all(c["listing"] == [] for c in engine.calls), "a working folder was not empty")
        self.assertFalse(any(os.path.exists(d) for d in cwds), "a working folder was left behind")
        self.assertEqual([f for f in os.listdir(self.tmp) if f.startswith("card_err")], [])

    def test_a_crossing_is_halved_at_once_without_same_size_retries(self):
        items = [dict(it, text="Reference 5550%04d." % i) for i, it in enumerate(self.items(4))]
        engine, sink = StubEngine(cross_contents), {}
        cards.run_items(self.run_, engine, "I", items, None, self.log.append, sink)
        self.assertEqual([c["n"] for c in engine.calls], [4, 2, 1, 1, 2, 1, 1])
        for it in items:
            self.assertIn(it["text"], sink[it["id"]]["summary"])
        self.assertTrue(any("halving at once" in line for line in self.log))

    def test_a_chunk_that_never_joins_writes_no_card_and_records_every_item(self):
        for depth in (0, 6):
            with self.subTest(depth=depth):
                sink, items = {}, self.items(2)
                cards.run_items(self.run_, StubEngine(lambda cs: cs + [card_for("d9")]), "I", items, None,
                                self.log.append, sink, depth=depth)
                self.assertEqual(sink, {})
                for it in items:
                    self.assertTrue(os.path.exists(os.path.join(self.tmp, "card_err_%s.txt" % it["id"])), it["id"])
                    os.remove(os.path.join(self.tmp, "card_err_%s.txt" % it["id"]))

    def test_a_refused_or_cut_prompt_is_halved_at_once_without_same_size_retries(self):
        """The same chunk is refused (or cut) the same way, so retrying it at its size spends calls that cannot
        succeed; the halves can."""
        for error in (engines.PromptTooLong("over the limit"), engines.PromptCut("agy cut it")):
            with self.subTest(type(error).__name__):
                engine, sink, items = StubEngine(error=error), {}, self.items(2)
                cards.run_items(self.run_, engine, "I", items, None, self.log.append, sink)
                self.assertEqual([c["n"] for c in engine.calls], [2, 1, 1])
                self.assertEqual(sink, {})
                self.assertTrue(any("halving at once" in line for line in self.log))
                for it in items:
                    path = os.path.join(self.tmp, "card_err_%s.txt" % it["id"])
                    self.assertTrue(os.path.exists(path), it["id"])
                    os.remove(path)

    def test_quota_and_run_stopping_errors_pass_straight_through(self):
        for error in (engines.QuotaError("quota", 60), engines.CredentialError("auth.json in state"),
                      engines.SetupError("codex not found")):
            with self.subTest(type(error).__name__):
                engine, sink = StubEngine(error=error), {}
                with self.assertRaises(type(error)):
                    cards.run_items(self.run_, engine, "I", self.items(2), None, self.log.append, sink)
                self.assertEqual(len(engine.calls), 1, "a run-stopping error was retried")
                self.assertEqual(sink, {})


class CardsCliCase(unittest.TestCase):
    """A folder with extract records, fake engines first on PATH, and `cards.py` run as the operator runs it."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="cards_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "Alex Personal")
        os.makedirs(self.root)
        self.work = os.path.join(self.tmp, "work")
        self.extract = os.path.join(self.tmp, "extract")
        self.cards = os.path.join(self.tmp, "cards")
        self.terms = os.path.join(self.tmp, "terms.txt")
        write(self.terms, TERMS)
        self.fakes = Fakes(self.tmp)
        self.env = tool_env(self.tmp, self.fakes)
        self.entries = {}

    def record(self, path, pages, status="ok", tier="text_layer", now_at=None, flags=()):
        """An extract record for `path`, and its manifest entry: its current path is `now_at` when the document has
        moved since it was read (a record keeps the path it was read at), its flags `flags`."""
        i = eid(path)
        rec = {"id": i, "path": path, "class": "document", "status": status, "page_count": len(pages),
               "tiers": {tier: len(pages)}, "pages": [{"n": n + 1, "tier": tier, "text": t}
                                                      for n, t in enumerate(pages)]}
        rec["chars"] = sum(len(t) for t in pages)
        write(os.path.join(self.extract, i + ".json"), json.dumps(rec, ensure_ascii=False))
        self.stage(i, now_at or path, flags)
        return i

    def stage(self, i, current_path, flags=()):
        """The manifest entry of document `i`, at `current_path` with `flags`, written to the folder's own manifest."""
        self.entries[i] = {"id": i, "current_path": current_path, "class": "document", "hashed": True,
                           "flags": list(flags)}
        write(os.path.join(self.root, "_Audit", "manifest.json"),
              json.dumps({"schema": "family-ai-preprocess-manifest/2", "entries": self.entries}))

    def cards_py(self, *args):
        cmd = [sys.executable, os.path.join(TOOLS, "cards.py")] + list(args[:1]) + [
            "--root", self.root, "--work", self.work, "--extract", self.extract, "--out", self.cards] + list(args[1:])
        r = subprocess.run(cmd, capture_output=True, text=True, env=self.env, timeout=TIMEOUT)
        self.assertNotIn("ResourceWarning", r.stderr, "cards.py left a file or process open")
        return r.returncode, r.stdout, r.stderr

    def work_run(self, engine, *extra):
        return self.cards_py("work", "--engine", engine, "--model", "fake-model", *extra)

    def batches(self):
        d = os.path.join(self.work, "batches")
        out = {}
        for f in sorted(os.listdir(d)):
            out[f] = json.loads(read(os.path.join(d, f)))
        return out

    def written(self):
        return {f[:-5]: json.loads(read(os.path.join(self.cards, f)))
                for f in sorted(os.listdir(self.cards))} if os.path.isdir(self.cards) else {}

    def card_errors(self):
        state = os.path.join(self.work, "state")
        return sorted(f for f in os.listdir(state) if f.startswith("card_err_")) if os.path.isdir(state) else []


class BuildTest(CardsCliCase):
    BUDGET = ["--small-chars", "500", "--batch-chars", "1000", "--batch-items", "2", "--textless-batch", "3",
              "--single-max", "2000"]

    def test_groups_singles_and_sections(self):
        small = {self.record("04 Study/n%d.txt" % i, ["small text %d " % i * 5]) for i in range(3)}
        textless = self.record("IMG_0001.jpg", ["a photo"], status="photo", tier="photo")
        single = self.record("02 Finance/Statement.pdf", ["s" * 1500])
        sections = self.record("04 Study/Reader.pdf", ["r" * 1200, "r" * 1200])
        many_pages = self.record("05 Archive/Scans.pdf", ["p" * 30] + [""] * 49)
        self.record("01 Identity/Scan.pdf", ["x"], status="needs_vision")
        carded = self.record("03 Home/Lease.pdf", ["lease text"])
        write(os.path.join(self.cards, carded + ".json"), "{}")
        code, out, err = self.cards_py("build", *self.BUDGET)
        self.assertEqual(code, 0, err)
        self.assertIn("1 records still waiting for extraction", out)
        b = self.batches()
        by_mode = {}
        for name, bt in b.items():
            by_mode.setdefault((name[0], bt["mode"]), []).append([it["id"] for it in bt["items"]])
        self.assertEqual(sorted(len(g) for g in by_mode[("0", "group")]), [1, 2])
        self.assertEqual({i for g in by_mode[("0", "group")] for i in g}, small)
        self.assertEqual(by_mode[("1", "group")], [[textless]])
        self.assertEqual(by_mode[("0", "single")], [[single]])
        self.assertEqual(by_mode[("0", "sections")], [[sections]])
        self.assertEqual(by_mode[("2", "group")], [[many_pages]])
        self.assertEqual(len(b), 6, "the waiting and already carded records must not be planned")
        code, out, err = self.cards_py("build", *self.BUDGET)
        self.assertEqual(code, 0, err)
        self.assertIn("build: 0 new batches", out)

    def test_the_default_budget_follows_the_engine(self):
        """agy cuts a long message short, so its defaults keep every call under its byte limit; codex keeps the
        wide ones."""
        doc = self.record("04 Study/Reader.pdf", ["r" * 70_000])
        code, _out, err = self.cards_py("build")  # the engine defaults to agy
        self.assertEqual(code, 0, err)
        self.assertEqual([bt["mode"] for bt in self.batches().values()], ["sections"])
        shutil.rmtree(self.work)
        code, _out, err = self.cards_py("build", "--engine", "codex")
        self.assertEqual(code, 0, err)
        self.assertEqual([(bt["mode"], [it["id"] for it in bt["items"]]) for bt in self.batches().values()],
                         [("single", [doc])])


    def test_agys_budgets_are_50000_characters_because_it_cuts_a_prompt_at_192000_bytes(self):
        """A character of CJK text is three bytes of prompt, so 60,000 characters left the instructions no room under
        the 180,000-byte limit: every document-sized budget defaults to 50,000 for agy, and a document over it is
        read in sections. codex keeps its own."""
        a = self.record("04 Study/A.pdf", ["\u5b66" * 30_000])
        b = self.record("04 Study/B.pdf", ["\u4e60" * 30_000])
        c = self.record("04 Study/C.pdf", ["\u5b66" * 55_000])
        modes = lambda: sorted((bt["mode"], sorted(it["id"] for it in bt["items"])) for bt in self.batches().values())
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertEqual(modes(), sorted([("group", [a]), ("group", [b]), ("sections", [c])]),
                         "two 30,000-character documents shared a 60,000-character batch, or the long one went whole")
        shutil.rmtree(self.work)
        code, _out, err = self.cards_py("build", "--engine", "codex")
        self.assertEqual(code, 0, err)
        self.assertEqual(modes(), [("group", sorted([a, b, c]))])

    def test_the_agy_budget_leaves_room_for_the_largest_card_prompt(self):
        """The comment on AGY_BUDGET_CHARS as arithmetic: the budget in three-byte characters, beside the largest
        call's own text (a generous household's instructions, a full batch's per-item frames and the card schema's
        text, which agy is given in its prompt), stays under agy's limit. Raising the budget, growing the template or
        the schema fails this before it fails a run."""
        people = [{"name": "Person Number %d Example" % i, "also": ["Alias %d-%d" % (i, k) for k in range(4)],
                   "who": "a relative of the owner, appearing on shared household papers"} for i in range(12)]
        instr = cards.instructions(dict(common.DEFAULTS, people=people, folder_description="\u4e2d" * 2000))
        frames = [{"id": "d%d" % k, "path": "p" * 400, "class": "document", "page_count": 100, "read": "text_layer",
                   "text": ""} for k in range(1, 31)]
        batch = engines.with_schema(engines.NO_TOOLS + instr + "\n\nInput items (JSON, 30 items):\n" +
                                    json.dumps(frames, ensure_ascii=False), CARD_SCHEMA_PATH)
        section = engines.NO_TOOLS + cards.SECTION_PROMPT.format(path="p" * 400, k=99, n=99, text="",
                                                                 identifier_rule=cards.identifier_rule(common.DEFAULTS))
        for name, prompt in (("a full batch", batch), ("a section", section)):
            with self.subTest(name):
                total = 3 * cards.AGY_BUDGET_CHARS + len(prompt.encode("utf-8"))
                self.assertLessEqual(total, engines.AGY_MAX_PROMPT_BYTES, "%d bytes" % total)


class WorkTest(CardsCliCase):
    def two_docs(self, text_a="Rent for the flat.", text_b="Council tax bill."):
        a = self.record("03 Home/Rent.pdf", [text_a])
        b = self.record("03 Home/Council tax.pdf", [text_b])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        return a, b

    def test_a_tool_step_in_the_cards_lane_discards_the_reply_and_writes_no_card(self):
        """The cards lane lets the model use no tool: agy's tool step, here an allowed read of the call's own folder
        with a valid answer beside it, discards the reply, through the engine `work` itself builds. Reads are for the
        vision lane alone."""
        a, b = self.two_docs()
        step = {"event": "step_update", "step_update": {"conversation_id": "c-1", "step_index": 2, "state": "DONE",
                                                        "step_type": "tool", "tool_name": "view_file",
                                                        "tool_info": {"name": "view_file",
                                                                      "parameters": {"AbsolutePath": "p1.png"}}}}
        self.fakes.script("agy", default={"kind": "text", "events": [step]})
        code, _out, err = self.work_run("agy", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.written(), {}, "a card was written from a call whose model used a tool")
        self.assertEqual(self.card_errors(), sorted("card_err_%s.txt" % i for i in (a, b)))
        self.assertIn("tool use ['view_file']", read(os.path.join(self.work, "state", "card_err_%s.txt" % a)))

    def test_a_cut_prompt_halves_the_work_at_once(self):
        """The real stream of a cut prompt, as the first call's reply: the chunk is split in two and each half is
        carded, with no retry of the same chunk, which would be cut again."""
        a, b = self.two_docs()
        self.fakes.script("agy", replies=[CUT], default={"kind": "text"})
        code, _out, err = self.work_run("agy", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        self.assertEqual([item_count(c) for c in self.fakes.calls("agy")], [2, 1, 1])
        self.assertEqual(sorted(self.written()), sorted([a, b]))
        self.assertEqual(self.card_errors(), [])

    def test_a_swapping_engine_is_rejected_and_halved_and_never_written(self):
        for engine in ("codex", "agy"):
            with self.subTest(engine):
                shutil.rmtree(self.cards, True)
                shutil.rmtree(self.work, True)
                a, b = self.two_docs()
                self.fakes.script(engine, default={"kind": "text", "swap": True}, watch=self.cards)
                code, _out, err = self.work_run(engine, "--terms", self.terms)
                self.assertEqual(code, 0, err)
                calls = self.fakes.calls(engine)
                self.fakes.reset(engine)
                self.assertEqual([item_count(c) for c in calls], [2, 2, 2, 1, 1])
                self.assertTrue(all(c["watch"] == [] for c in calls), "a card was written mid-batch")
                got = self.written()
                self.assertEqual(sorted(got), sorted([a, b]))
                self.assertEqual(got[a]["title"], "Card of 03 Home/Rent.pdf")
                self.assertEqual(got[b]["title"], "Card of 03 Home/Council tax.pdf")
                self.assertEqual(got[a]["card_meta"]["via"], engine)
                self.assertEqual(self.card_errors(), [])
                cwds = [c["cwd"] for c in calls]
                self.assertEqual(len(set(cwds)), len(cwds))
                self.assertTrue(all(c["cwd_listing"] == [] for c in calls))
                self.assertEqual(os.listdir(self.env["TMPDIR"]), [], "a working folder was left behind")
                for c in calls:
                    self.assertTrue(c["prompt"].startswith(engines.NO_TOOLS))
                    self.assertNotIn(a, c["prompt"])
                    self.assertNotIn(b, c["prompt"])
                for c in calls:
                    if engine == "codex":
                        schema = c["argv"][c["argv"].index("--output-schema") + 1]
                        self.assertEqual(os.path.basename(schema), "card_codex.json")
                    else:
                        # agy is asked for the shape in the prompt, after the items, never by flag
                        self.assertNotIn("--json-schema", c["argv"])
                        self.assertTrue(c["prompt"].endswith(
                            "\n\nReply with JSON only, matching this JSON Schema exactly:\n" + CARD_SCHEMA_TEXT))

    def test_a_crossing_engine_is_rejected_and_halved_and_never_written(self):
        """Ids and order intact, contents crossed: only the sibling-identifier check can see it, and it halves at
        once (a same-size retry would cross the same way)."""
        a, b = self.two_docs("Rent for the flat, reference 55501234.", "Council tax bill, account 77709876.")
        self.fakes.script("codex", default={"kind": "text", "cross": True}, watch=self.cards)
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        calls = self.fakes.calls("codex")
        self.assertEqual([item_count(c) for c in calls], [2, 1, 1])
        self.assertTrue(all(c["watch"] == [] for c in calls), "a card was written mid-batch")
        self.assertIn("carries an identifier that its own source lacks", err)
        got = self.written()
        self.assertEqual(got[a]["key_facts"]["reference_numbers"], ["ref 55501234"])
        self.assertEqual(got[b]["key_facts"]["reference_numbers"], ["ref 77709876"])
        self.assertEqual(got[a]["title"], "Card of 03 Home/Rent.pdf")

    def test_a_correct_reply_in_another_order_costs_four_more_calls(self):
        """The order check rejects a reply that is right but reordered; this pins the cost of that decision: for a
        chunk of two, three rejected calls and two single calls instead of one call."""
        a, b = self.two_docs()
        self.fakes.script("codex", default={"kind": "text", "reorder": True})
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        self.assertEqual([item_count(c) for c in self.fakes.calls("codex")], [2, 2, 2, 1, 1])
        got = self.written()
        self.assertEqual((got[a]["title"], got[b]["title"]),
                         ("Card of 03 Home/Rent.pdf", "Card of 03 Home/Council tax.pdf"))

    def test_a_missing_card_is_rejected_and_halved(self):
        a, b = self.two_docs()
        self.fakes.script("codex", default={"kind": "text", "drop": True}, watch=self.cards)
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        self.assertEqual([item_count(c) for c in self.fakes.calls("codex")], [2, 2, 2, 1, 1])
        self.assertEqual(sorted(self.written()), sorted([a, b]))

    def test_a_reply_that_never_joins_writes_nothing(self):
        a, b = self.two_docs()
        self.fakes.script("codex", default={"kind": "text", "extra": True})
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.written(), {})
        self.assertEqual(self.card_errors(), sorted("card_err_%s.txt" % i for i in (a, b)))

    def test_isolation_terms_are_required(self):
        self.two_docs()
        code, _out, err = self.work_run("codex")
        self.assertEqual(code, 2)
        self.assertIn("--no-isolation-terms", err)
        self.assertEqual(self.fakes.calls("codex"), [])

    def test_agy_needs_a_model(self):
        self.two_docs()
        code, _out, err = self.cards_py("work", "--engine", "agy", "--terms", self.terms)
        self.assertEqual(code, 2, err)
        self.assertIn("error: --model is required for agy", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(self.fakes.calls("agy"), [])


class HeldForAnotherProjectTest(CardsCliCase):
    """A document whose current path in the manifest is under the migrations folder is held for another project:
    no batch is planned for it, no call is sent it, and the run counts it, whatever its flags and wherever its record
    says it was read."""

    STAGED = "_Migrations/Other Project/02 Finance/Old invoice.pdf"

    def test_build_plans_no_batch_for_a_held_record_and_counts_it(self):
        own = self.record("03 Home/Rent.pdf", ["Rent for the flat."])
        self.record(self.STAGED, ["Invoice for the other project."], flags=["migrating"])
        self.record("_Migrations/Other Project/Letter.pdf", ["A letter, its flag lost."])  # no `migrating` flag
        self.record("02 Finance/Statement.pdf", ["A statement."], now_at="_Migrations/Other Project/Statement.pdf",
                    flags=["migrating", "departed"])  # staged after it was read: its record keeps the old path
        self.record("01 Identity/Scan.pdf", ["x"], status="needs_vision",
                    now_at="_Migrations/Other Project/Scan.pdf")  # held, so not one still waiting for extraction
        code, out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertIn("build: 1 new batches, 0 records still waiting for extraction, 4 held for another project, "
                      "0 excluded", out)
        self.assertEqual([[it["id"] for it in bt["items"]] for bt in self.batches().values()], [[own]])

    def test_a_batch_planned_before_the_staging_is_not_sent(self):
        own = self.record("03 Home/Rent.pdf", ["Rent for the flat."])
        gone = self.record("02 Finance/Old invoice.pdf", ["Invoice for the other project, GBP 800."])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertEqual([len(bt["items"]) for bt in self.batches().values()], [2])
        self.stage(gone, self.STAGED, ["migrating"])  # a round stages it, and the audit is run again
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        calls = self.fakes.calls("codex")
        self.assertEqual([item_count(c) for c in calls], [1])
        self.assertNotIn("Old invoice", calls[0]["prompt"])
        self.assertNotIn("GBP 800", calls[0]["prompt"])
        self.assertEqual(sorted(self.written()), [own])
        self.assertIn("worker finished; held for another project: 1; excluded: 0", err)
        self.assertEqual(self.card_errors(), [])

    def test_a_redo_does_not_send_a_held_document(self):
        own = self.record("03 Home/Rent.pdf", ["Rent for the flat."])
        held = self.record(self.STAGED, ["Invoice for the other project, GBP 800."], flags=["migrating"])
        redo = os.path.join(self.tmp, "redo.txt")
        write(redo, "%s\n%s\n" % (held, own))
        code, _out, err = self.work_run("codex", "--terms", self.terms, "--redo", redo)
        self.assertEqual(code, 0, err)
        calls = self.fakes.calls("codex")
        self.assertEqual([item_count(c) for c in calls], [1])
        self.assertNotIn("GBP 800", calls[0]["prompt"])
        self.assertEqual(sorted(self.written()), [own])
        self.assertIn("worker finished; held for another project: 1; excluded: 0", err)

    def rulebook(self, **settings):
        """The folder's rulebook and its twin, pinned to it, carrying `settings`."""
        write(os.path.join(self.root, "CLAUDE.md"), "# Rules\n")
        pin = hashlib.sha256(read(os.path.join(self.root, "CLAUDE.md")).encode()).hexdigest()
        write(os.path.join(self.root, ".familyai", "rulebook.json"),
              json.dumps(dict(settings, version=1, rulebook_sha256=pin)))
        for entry in settings.get("exclude", []):  # an `exclude` entry must name a path: make each a folder
            os.makedirs(os.path.join(self.root, entry), exist_ok=True)

    def test_an_excluded_document_is_never_carded_and_is_counted_apart(self):
        self.rulebook(exclude=["Staff", "Letters/Private.pdf"])
        own = self.record("03 Home/Rent.pdf", ["Rent for the flat."])
        self.record("Staff/pay.pdf", ["Salary for the nanny."])
        self.record("Staff/2024/review.pdf", ["Review.", "More."], flags=["migrating"])
        self.record("Letters/Private.pdf", ["A private letter."], status="needs_vision")
        self.record("Letters/Kept.pdf", ["A letter to share."], now_at="Staff/Kept.pdf")  # moved under Staff since
        self.record(self.STAGED, ["Invoice for the other project."], flags=["migrating"])
        code, out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertIn("build: 1 new batches, 0 records still waiting for extraction, 1 held for another project, "
                      "4 excluded", out)
        self.assertEqual([[it["id"] for it in bt["items"]] for bt in self.batches().values()], [[own]])

    def test_a_batch_planned_before_the_exclusion_is_not_sent_and_a_redo_does_not_send_it_either(self):
        own = self.record("03 Home/Rent.pdf", ["Rent for the flat."])
        private = self.record("Staff/pay.pdf", ["Salary for the nanny, GBP 2,400."])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertEqual([len(bt["items"]) for bt in self.batches().values()], [2])
        self.rulebook(exclude=["Staff"])  # the owner excludes it after the batches were planned
        redo = os.path.join(self.tmp, "redo.txt")
        write(redo, "%s\n" % private)
        for extra in ([], ["--redo", redo]):
            with self.subTest(extra):
                shutil.rmtree(self.cards, True)
                self.fakes.reset("codex")
                code, _out, err = self.work_run("codex", "--terms", self.terms, *extra)
                self.assertEqual(code, 0, err)
                calls = self.fakes.calls("codex")
                self.assertEqual([item_count(c) for c in calls], [] if extra else [1])
                for c in calls:
                    self.assertNotIn("nanny", c["prompt"])
                self.assertEqual(sorted(self.written()), [] if extra else [own])
                self.assertIn("worker finished; held for another project: 0; excluded: 1", err)

    def test_an_exclusion_made_while_the_worker_runs_takes_effect_before_the_next_batch(self):
        """The worker reads the settings and the manifest again, and purges again, before each batch: the second batch
        (a document with next to no text, so a batch of its own) is not sent, its record is discarded, and it is counted."""
        own = self.record("03 Home/Rent.pdf", ["Rent for the flat, paid monthly by standing order."])
        private = self.record("Staff/pay.pdf", ["x"])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(len(bt["items"]) for bt in self.batches().values()), [1, 1])
        self.rulebook(exclude=[])
        twin = os.path.join(self.root, ".familyai", "rulebook.json")
        cmd = [sys.executable, "-c", EXCLUDE_AFTER_FIRST_CALL, os.path.join(TOOLS, "cards.py"), "work", "--root", self.root,
               "--work", self.work, "--extract", self.extract, "--out", self.cards, "--terms", self.terms,
               "--engine", "codex", "--model", "fake-model"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT,
                           env=dict(self.env, TEST_EXCLUDE_AFTER_FIRST_CALL="%s|Staff" % twin))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([item_count(c) for c in self.fakes.calls("codex")], [1])
        self.assertNotIn("pay.pdf", self.fakes.calls("codex")[0]["prompt"])
        self.assertEqual(sorted(self.written()), [own])
        self.assertFalse(os.path.exists(os.path.join(self.extract, private + ".json")), "the record was kept")
        self.assertIn("purged what withheld documents left behind: 1 extract record", r.stderr)
        self.assertIn("worker finished; held for another project: 0; excluded: 1", r.stderr)
        self.assertNotIn("Staff", r.stderr, "the purge names counts, never paths")

    def test_an_exclusion_made_during_a_quota_sleep_takes_effect_before_anything_is_resent(self):
        """The first call is refused for quota; the worker sleeps, and the owner excludes a folder meanwhile. The batch is
        resent only after the settings and the manifest are read again and the purge run again: the excluded document is
        not in the second call, its record is gone and it is counted."""
        own = self.record("03 Home/Rent.pdf", ["Rent for the flat, paid monthly by standing order."])
        private = self.record("Staff/pay.pdf", ["Salary for the nanny, GBP 2,400, paid monthly by the family."])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertEqual([len(bt["items"]) for bt in self.batches().values()], [2])
        self.rulebook(exclude=[])
        twin = os.path.join(self.root, ".familyai", "rulebook.json")
        self.fakes.script("codex", replies=[{"kind": "quota", "rc": 1, "message": "Quota exceeded. Resets in 5s"}],
                          default={"kind": "text"})
        cmd = [sys.executable, "-c", EXCLUDE_AT_SLEEP, os.path.join(TOOLS, "cards.py"), "work", "--root", self.root,
               "--work", self.work, "--extract", self.extract, "--out", self.cards, "--terms", self.terms,
               "--engine", "codex", "--model", "fake-model"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT,
                           env=dict(self.env, TEST_EXCLUDE_AT_SLEEP="%s|Staff" % twin))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("quota on", r.stderr)
        calls = self.fakes.calls("codex")
        self.assertEqual([item_count(c) for c in calls], [2, 1], "the resend carried the excluded document")
        self.assertIn("pay.pdf", calls[0]["prompt"])
        self.assertNotIn("pay.pdf", calls[1]["prompt"])
        self.assertNotIn("nanny", calls[1]["prompt"])
        self.assertEqual(sorted(self.written()), [own])
        self.assertFalse(os.path.exists(os.path.join(self.extract, private + ".json")), "the record was kept")
        self.assertIn("purged what withheld documents left behind: 1 extract record", r.stderr)
        self.assertIn("worker finished; held for another project: 0; excluded: 1", r.stderr)

    def repath(self, i, to):
        """What `extract.py repath --apply` does for the record of `i` and the manifest's entry: both now name `to`."""
        rec = os.path.join(self.extract, i + ".json")
        write(rec, json.dumps(dict(json.loads(read(rec)), path=to)))
        self.stage(i, to)

    def test_the_card_the_worker_writes_records_the_path_it_was_made_at_and_a_purge_reads_it(self):
        i = self.record("Staff/pay.pdf", ["Salary for the nanny, GBP 2,400, paid monthly by the family."])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.written()[i]["card_meta"]["path"], "Staff/pay.pdf")
        # the document is the copy at an included path now, its record repathed to it; the card still says where it was made
        self.repath(i, "Public/pay copy.pdf")
        self.rulebook(exclude=["Staff"])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertIn("purged what withheld documents left behind: 1 card\n", err)
        self.assertNotIn("Staff", err)
        self.assertEqual(self.written(), {})
        self.assertTrue(os.path.exists(os.path.join(self.extract, i + ".json")), "the record names an included path")

    def test_the_section_notes_the_worker_writes_record_the_path_and_a_purge_reads_it(self):
        pages = ["Page %d of the course reader. " % n + "w" * 3_000 for n in (1, 2, 3)]
        i = self.record("Staff/Course reader.pdf", pages)
        budget = ["--small-chars", "500", "--single-max", "1000"]
        code, _out, err = self.cards_py("build", *budget)
        self.assertEqual(code, 0, err)
        self.fakes.script("codex", default={"kind": "text"})
        code, _out, err = self.cards_py("work", "--engine", "codex", "--terms", self.terms, "--section-tokens", "1000",
                                        *budget)
        self.assertEqual(code, 0, err)
        cache = os.path.join(self.work, "sections")
        notes = sorted(os.listdir(cache))
        self.assertEqual(len(notes), 3)
        for name in notes:
            self.assertEqual(read(os.path.join(cache, name)).split("\n", 1)[0], "[path] Staff/Course reader.pdf")
        self.repath(i, "Public/Course reader copy.pdf")
        os.remove(os.path.join(self.cards, i + ".json"))  # only the notes name the old path now
        self.rulebook(exclude=["Staff"])
        code, _out, err = self.cards_py("build", *budget)
        self.assertEqual(code, 0, err)
        self.assertIn("purged what withheld documents left behind: 3 cached section notes\n", err)
        self.assertEqual(os.listdir(cache), [])

    def stage_synthetic(self, i, current_path):
        """The manifest entry an audit makes for an excluded path: a synthetic id, `hashed` false, no content."""
        self.entries[i] = {"id": i, "current_path": current_path, "class": "document", "hashed": False,
                           "synthetic_id": True, "flags": []}
        write(os.path.join(self.root, "_Audit", "manifest.json"),
              json.dumps({"schema": "family-ai-preprocess-manifest/2", "entries": self.entries}))

    def test_a_document_moved_into_an_excluded_folder_after_extraction_is_never_sent(self):
        """The audit cannot link a move into an excluded folder (it never hashes there): the old entry is `departed` at
        its old, included path and the file has a new synthetic id. The old id's record holds the full text."""
        own = self.record("03 Home/Rent.pdf", ["Rent for the flat."])
        old = self.record("Letters/Dismissal.txt", ["Dismissal letter, reference 98765432."])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertEqual([len(bt["items"]) for bt in self.batches().values()], [2])  # planned before the move
        self.entries[old]["flags"] = ["departed"]  # re-audited after the move and the exclusion
        self.stage_synthetic(eid("Private/Dismissal.txt"), "Private/Dismissal.txt")
        self.rulebook(exclude=["Private"])
        code, out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        calls = self.fakes.calls("codex")
        self.assertEqual([item_count(c) for c in calls], [1])
        self.assertNotIn("98765432", calls[0]["prompt"])
        self.assertNotIn("Dismissal", calls[0]["prompt"])
        self.assertEqual(sorted(self.written()), [own])
        self.assertIn("not live: 1", err)
        shutil.rmtree(os.path.join(self.work, "batches"))  # a fresh build plans nothing for it either
        code, out, err = self.cards_py("build")
        self.assertIn("1 not live", out)

    def test_a_departed_document_and_an_id_the_manifest_does_not_hold_are_not_carded(self):
        gone = self.record("Letters/Gone.txt", ["A letter that left the folder."], flags=["departed"])
        unknown = eid("Elsewhere/Unknown.txt")
        write(os.path.join(self.extract, unknown + ".json"), json.dumps({
            "id": unknown, "path": "Elsewhere/Unknown.txt", "class": "document", "status": "ok", "page_count": 1,
            "tiers": {"text_layer": 1}, "chars": 10, "pages": [{"n": 1, "tier": "text_layer", "text": "A stray."}]}))
        code, out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertIn("build: 0 new batches", out)
        self.assertIn("2 not live", out)
        redo = os.path.join(self.tmp, "redo.txt")
        write(redo, "%s\n%s\n" % (gone, unknown))
        code, _out, err = self.work_run("codex", "--terms", self.terms, "--redo", redo)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.fakes.calls("codex"), [])
        self.assertIn("not live: 2", err)

    def test_a_record_made_before_an_exclusion_is_purged_and_the_document_read_again_from_its_included_path(self):
        """`Staff/Nanny dismissal.txt` and an identical `Public/Payslip copy.txt`: the first name was canonical when
        the record was made. The owner excludes `Staff`, and the entry is now live at the other name, not withheld:
        its record still carries the excluded path, so every start discards it, and nothing is sent from it."""
        i = self.record("Staff/Nanny dismissal.txt", ["Dismissal of the nanny, reference 98765432."],
                        now_at="Public/Payslip copy.txt")
        self.rulebook(exclude=["Staff"])
        code, out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertIn("purged what withheld documents left behind: 1 extract record", err)
        self.assertNotIn("Staff", err + out, "the purge names counts, never paths")
        self.assertIn("build: 0 new batches", out)
        self.assertFalse(os.path.exists(os.path.join(self.extract, i + ".json")))
        self.assertEqual(self.batches(), {})
        redo = os.path.join(self.tmp, "redo.txt")
        write(redo, i + "\n")
        code, _out, err = self.work_run("codex", "--terms", self.terms, "--redo", redo)
        self.assertEqual(code, 2, err)
        self.assertIn("has no extract record", err)
        self.assertEqual(self.fakes.calls("codex"), [], "a record carrying an excluded path was sent")
        text = "Dismissal of the nanny, reference 98765432."  # read again, at the included path, as extract.py does
        write(os.path.join(self.extract, i + ".json"), json.dumps({
            "id": i, "path": "Public/Payslip copy.txt", "class": "document", "status": "ok", "page_count": 1,
            "tiers": {"text_layer": 1}, "chars": len(text), "pages": [{"n": 1, "tier": "text_layer", "text": text}]}))
        code, out, err = self.cards_py("build")
        self.assertIn("build: 1 new batches", out)
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        prompt = self.fakes.calls("codex")[0]["prompt"]
        self.assertIn("Public/Payslip copy.txt", prompt)
        self.assertNotIn("Staff", prompt)

    def test_a_call_names_a_document_by_the_manifests_path_never_the_records(self):
        i = self.record("03 Home/Old name.pdf", ["A lease, reference 55501234."], now_at="03 Home/New name.pdf")
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        item, = sent_items(self.fakes.calls("codex")[0]["prompt"])
        self.assertEqual(item["path"], "03 Home/New name.pdf")
        self.assertNotIn("Old name", self.fakes.calls("codex")[0]["prompt"])
        self.assertEqual(list(self.written()), [i])

    def test_the_migrations_folder_is_the_one_the_settings_name(self):
        write(os.path.join(self.root, "CLAUDE.md"), "# Rules\n")
        pin = hashlib.sha256(read(os.path.join(self.root, "CLAUDE.md")).encode()).hexdigest()
        write(os.path.join(self.root, ".familyai", "rulebook.json"),
              json.dumps({"version": 1, "rulebook_sha256": pin, "migrations_dir": "_Leaving"}))
        own = self.record("_Migrations/Notes.pdf", ["An ordinary folder now."])
        self.record("_Leaving/Other Project/Letter.pdf", ["Staged for another project."])
        code, out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertIn("build: 1 new batches, 0 records still waiting for extraction, 1 held for another project, "
                      "0 excluded", out)
        self.assertEqual([[it["id"] for it in bt["items"]] for bt in self.batches().values()], [[own]])

    def test_a_missing_or_unreadable_manifest_is_refused_not_read_as_nothing_held(self):
        for name, text, why in (("missing", None, "manifest missing"), ("not JSON", "{", "not valid JSON"),
                                ("no entries", "{}", "no \"entries\" object"),
                                ("an entry with no path", json.dumps({"entries": {"a" * 64: {}}}),
                                 "has no current_path")):
            with self.subTest(name):
                manifest = os.path.join(self.root, "_Audit", "manifest.json")
                shutil.rmtree(os.path.dirname(manifest), True)
                if text is not None:
                    write(manifest, text)
                code, out, err = self.cards_py("build")
                self.assertEqual(code, 2, out + err)
                self.assertIn(why, err)
                self.assertNotIn("Traceback", err)


def fixture_batch():
    """The fixture's text records (tests/expected/extract.json: the pages read by text layer, office or iWork
    readers), as extract records."""
    with open(os.path.join(HERE, "expected", "extract.json"), encoding="utf-8") as f:
        view = json.load(f)
    out = {}
    for path, r in view.items():
        pages = [{"n": n + 1, "tier": tier, "text": text} for n, (tier, text) in enumerate(zip(r["tiers"], r["text"]))
                 if text]
        if pages and r["status"] == "ok":
            out[path] = pages
    return out


# Honest cards for the fixture batch, written as templates/card-instructions.md asks, including the edits a model
# makes that the source does not show verbatim: ISO dates, a currency, a year from context, a key fact in another
# case or with other separators, and `look` naming a sibling.
HONEST = {
    "02 Finance/Bank statement 2024-03.pdf": {
        "doc_date": "2024-03-31", "summary": "March 2024 statement for account 12345678.",
        "key_facts": {"dates": ["period 2024-03-01 to 2024-03-31"],
                      "amounts": ["opening GBP 2,410.00", "closing GBP 4,160.00", "rent GBP 1,450.00"],
                      "reference_numbers": ["ACCOUNT 1234-5678 sort code 01-02-03"]}},
    "01 Identity/Passport renewal 2021/Application form.docx": {
        "doc_date": "2021-05-02", "key_facts": {"dates": ["submitted 2021-05-02"], "amounts": [],
                                                "reference_numbers": ["previous passport p0987654"]}},
    "03 Home/Utilities /Electricity bill.pdf": {"doc_date": "2024-03-15"},
    "03 Home/Lease renewal.pages": {
        "key_facts": {"dates": ["term 2024-05-01 to 2025-04-30"], "amounts": ["GBP 1,450 per month"],
                      "reference_numbers": []},
        "look": "Appears to be the same lease as Lease renewal.pdf."},
    "02 Finance/Tax/Budget.numbers": {"summary": "Household budget for 2023, rent GBP 1,450 a month.",
                                      "key_facts": {"dates": ["2023"], "amounts": ["rent GBP 1,450 per month"],
                                                    "reference_numbers": []}},
    "04 Study/Slides.pptx": {"key_facts": {"dates": ["exams 2024-06"], "amounts": [], "reference_numbers": []}},
    "06 Work/Contract.docx": {"key_facts": {"dates": ["start 2022-05-01"], "amounts": [], "reference_numbers": []}},
    "02 Finance/Tax/Budget final.xlsx": {"look": "A later version of Budget.numbers for 2023?"},
}


# The whole batch is rejected once and halved at once (no same-size retries); the two crossed documents fall into
# different halves (by id order), so each half is carded in one call: 3 calls, 24 items sent.
CROSSING_CALLS = [12, 6, 6]


class FixtureBatchTest(CardsCliCase):
    """The cost of the join on the fixture's 12-item text batch (the fixture's staged file is held for another
    project, so it is never extracted or carded): honest cards take one call; a crossing between the
    two documents that carry identifiers is halved until they are apart, and never written."""

    def setUp(self):
        super().setUp()
        self.ids = {path: self.record(path, [p["text"] for p in pages]) for path, pages in fixture_batch().items()}
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertEqual([len(bt["items"]) for bt in self.batches().values()], [12])

    def run_batch(self, **reply):
        self.fakes.script("codex", default=dict(kind="text", cards_by_path=HONEST, **reply), watch=self.cards)
        code, _out, err = self.work_run("codex", "--no-isolation-terms")
        self.assertEqual(code, 0, err)
        written = self.written()
        self.assertEqual(sorted(written), sorted(self.ids.values()))
        for path, i in self.ids.items():
            self.assertEqual(written[i]["title"], "Card of " + path, "a card was written onto another document")
        return [item_count(c) for c in self.fakes.calls("codex")]

    def test_honest_cards_take_one_call(self):
        self.assertEqual(len(self.ids), 12)
        self.assertEqual(self.run_batch(), [12])

    def test_a_crossing_is_halved_until_apart(self):
        calls = self.run_batch(cross_paths=["02 Finance/Bank statement 2024-03.pdf",
                                            "01 Identity/Passport renewal 2021/Application form.docx"])
        self.assertEqual(calls, CROSSING_CALLS)
        self.assertTrue(all(c["watch"] == [] for c in self.fakes.calls("codex")), "a card was written mid-batch")


class ContaminationTest(CardsCliCase):
    """A term in a card is an alert, whatever the document carries: the call was sent the document with every term
    withheld, so none can have come from it. One alert writes no card."""

    def docs(self, source_first, source_second):
        paths = sorted(["03 Home/Rent.pdf", "03 Home/Council tax.pdf"], key=eid)
        ids = [self.record(paths[0], [source_first]), self.record(paths[1], [source_second])]
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.fakes.script("codex", default={"kind": "text", "suffix": " Seen at Zarnwick Farm."})
        return ids

    def test_a_term_missing_from_the_source_alerts_and_writes_nothing(self):
        self.docs("Rent paid to Zarnwick Farm.", "Council tax bill.")
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 2, err)
        self.assertIn("contamination", err)
        self.assertNotIn("Zarnwick", err, "the alert must not repeat the term")
        alert = os.path.join(self.work, "state", "ALERT")
        self.assertTrue(os.path.exists(alert))
        self.assertNotIn("Zarnwick", read(alert))
        self.assertEqual(self.written(), {}, "a card from the alerted chunk was written")
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 3, err)
        self.assertIn("ALERT present", err)

    def test_redo_counts_an_id_only_once_its_card_is_written(self):
        ids = self.docs("Rent paid to Zarnwick Farm.", "Council tax bill.")
        self.fakes.script("codex", default={"kind": "text"})
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        redo = os.path.join(self.tmp, "redo.txt")
        write(redo, ids[1] + "\n")
        done = os.path.join(self.work, "state", "redo_done_0.txt")
        self.fakes.script("codex", default={"kind": "text", "suffix": " Seen at Zarnwick Farm."})
        code, _out, err = self.work_run("codex", "--terms", self.terms, "--redo", redo)
        self.assertEqual(code, 2, err)
        self.assertIn("contamination", err)
        self.assertNotIn(ids[1], read(done) if os.path.exists(done) else "", "an alerted id was recorded as redone")
        os.remove(os.path.join(self.work, "state", "ALERT"))
        self.fakes.reset("codex")
        self.fakes.script("codex", default={"kind": "text"})
        code, _out, err = self.work_run("codex", "--terms", self.terms, "--redo", redo)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.fakes.calls("codex")), 1, "the alerted id was skipped on the next --redo")
        self.assertEqual(self.written()[ids[1]]["card_meta"]["batch"], "redo_0")
        self.assertEqual(read(done).split(), [ids[1]])
        code, _out, err = self.work_run("codex", "--terms", self.terms, "--redo", redo)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.fakes.calls("codex")), 1, "a redone id was carded again")

    def test_a_term_its_own_source_carries_is_still_an_alert_because_the_call_never_carried_it(self):
        """The excuse is gone: a card naming a term its source also names was written by a model that was not shown
        the term, so it knew it from elsewhere."""
        self.docs("Rent paid to Zarnwick Farm.", "Council tax for Zarnwick, the farm.")
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 2, err)
        self.assertIn("contamination", err)
        self.assertTrue(os.path.exists(os.path.join(self.work, "state", "ALERT")))
        self.assertEqual(self.written(), {})
        self.assertNotIn("zarnwick", (err + read(os.path.join(self.work, "state", "ALERT"))).lower())

    def test_no_isolation_terms_by_decision(self):
        ids = self.docs("Rent.", "Council tax.")
        code, _out, err = self.work_run("codex", "--no-isolation-terms")
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(self.written()), sorted(ids))
        self.assertIn("by operator decision", err)


class ShieldTest(CardsCliCase):
    """No call carries a term of the isolation list: every path and text sent is shielded first."""

    PATH = "03 Home/Zarnwick Farm lease.pdf"
    TEXT = "Rent paid to Zarnwick Farm, ZARNWICK, and Other Project."

    def prompts(self, engine="codex"):
        return [c["prompt"] for c in self.fakes.calls(engine)]

    def assert_no_term(self, text):
        for term in ("zarnwick", "other project"):
            self.assertNotIn(term, text.lower())

    def test_a_document_that_carries_a_term_is_carded_from_its_text_with_the_term_withheld(self):
        doc = self.record(self.PATH, [self.TEXT])
        clean = self.record("03 Home/Council tax.pdf", ["Council tax bill."])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.fakes.script("codex", default={"kind": "text"})
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        prompt, = self.prompts()
        self.assert_no_term(prompt)
        items = {it["path"]: it for it in sent_items(prompt)}
        self.assertEqual(sorted(items), ["03 Home/Council tax.pdf", "03 Home/[withheld name] lease.pdf"])
        self.assertIn("[page 1]\nRent paid to [withheld name], [withheld name], and [withheld name].",
                      items["03 Home/[withheld name] lease.pdf"]["text"])
        got = self.written()
        self.assertEqual(sorted(got), sorted([doc, clean]))
        self.assertEqual(got[doc]["card_meta"]["shielded"], 4, "the path's term and the text's three")
        self.assertNotIn("shielded", got[clean]["card_meta"])
        self.assertEqual(got[doc]["card_meta"]["path"], self.PATH, "the card names the document by its real path")
        self.assertNotIn("zarnwick", json.dumps(got[doc]).lower().replace(self.PATH.lower(), ""))
        self.assertIn("shielded: 1", err)
        self.assertIn("worker finished; held for another project: 0; excluded: 0; not live: 0; shielded: 1", err)
        self.assertFalse(os.path.exists(os.path.join(self.work, "state", "ALERT")))

    def test_no_isolation_terms_shields_nothing(self):
        doc = self.record(self.PATH, [self.TEXT])
        self.cards_py("build")
        self.fakes.script("codex", default={"kind": "text"})
        code, _out, err = self.work_run("codex", "--no-isolation-terms")
        self.assertEqual(code, 0, err)
        item, = sent_items(self.prompts()[0])
        self.assertEqual((item["path"], item["text"]), (self.PATH, "[page 1]\n" + self.TEXT))
        self.assertNotIn("shielded", self.written()[doc]["card_meta"])
        self.assertIn("shielded: 0", err)

    def test_both_flags_and_neither_are_refused_before_anything_runs(self):
        self.record(self.PATH, [self.TEXT])
        self.cards_py("build")
        for args in (["--terms", self.terms, "--no-isolation-terms"], []):
            with self.subTest(args):
                code, _out, err = self.work_run("codex", *args)
                self.assertEqual(code, 2, err)
                self.assertIn("--terms (the isolation list) or --no-isolation-terms", err)
                self.assertEqual(self.fakes.calls("codex"), [])

    def test_sectioned_documents_are_shielded_in_every_section_the_notes_and_the_opening_text(self):
        pages = ["Page %d of the reader, held by Zarnwick Farm. " % n + "w" * 3_000 for n in (1, 2, 3)]
        doc = self.record("04 Study/Zarnwick reader.pdf", pages)
        budget = ["--small-chars", "500", "--single-max", "1000"]
        self.cards_py("build", *budget)
        self.fakes.script("codex", default={"kind": "text"})
        work = ["--engine", "codex", "--terms", self.terms, "--section-tokens", "1000"] + budget
        code, _out, err = self.cards_py("work", *work)
        self.assertEqual(code, 0, err)
        prompts = self.prompts()
        self.assertEqual(len(prompts), 4)
        for p in prompts:
            self.assert_no_term(p)
        self.assertIn("Document path: 04 Study/[withheld name] reader.pdf. This is section 1 of 3.", prompts[0])
        self.assertIn("Page 1 of the reader, held by [withheld name]. ", prompts[0])
        item, = sent_items(prompts[3])
        self.assertTrue(item["text"].startswith("SECTION NOTES (the document was read in 3 sections)"))
        self.assertIn("OPENING TEXT:\n[page 1]\nPage 1 of the reader, held by [withheld name]. ", item["text"])
        self.assertEqual(self.written()[doc]["card_meta"]["shielded"], 4)
        cache = os.path.join(self.work, "sections")
        for name in os.listdir(cache):
            self.assertEqual(common.note_path(os.path.join(cache, name)), "04 Study/Zarnwick reader.pdf",
                             "a purge reads the real path from the cache")

    def test_a_cached_note_is_shielded_again_when_it_is_read(self):
        pages = ["Page %d of the reader. " % n + "w" * 3_000 for n in (1, 2, 3)]
        doc = self.record("04 Study/Reader.pdf", pages)
        budget = ["--small-chars", "500", "--single-max", "1000"]
        self.cards_py("build", *budget)
        self.fakes.script("codex", default={"kind": "text"})
        work = ["--engine", "codex", "--terms", self.terms, "--section-tokens", "1000"] + budget
        self.assertEqual(self.cards_py("work", *work)[0], 0)
        cache = os.path.join(self.work, "sections")
        note = os.path.join(cache, sorted(os.listdir(cache))[0])
        write(note, read(note) + " Seen at Zarnwick Farm.")
        os.remove(os.path.join(self.cards, doc + ".json"))
        self.fakes.reset("codex")
        code, _out, err = self.cards_py("work", *work)
        self.assertEqual(code, 0, err)
        prompt, = self.prompts()  # the notes were cached: only the card call is made
        self.assert_no_term(prompt)
        self.assertIn("Seen at [withheld name].", prompt)

    def test_notes_cached_under_another_terms_file_are_not_reused(self):
        pages = ["Page %d of the reader. " % n + "w" * 3_000 for n in (1, 2, 3)]
        doc = self.record("04 Study/Reader.pdf", pages)
        budget = ["--small-chars", "500", "--single-max", "1000"]
        self.cards_py("build", *budget)
        self.fakes.script("codex", default={"kind": "text"})
        base = ["--engine", "codex", "--section-tokens", "1000"] + budget
        self.assertEqual(self.cards_py("work", "--no-isolation-terms", *base)[0], 0)
        cache = os.path.join(self.work, "sections")
        self.assertEqual(len(os.listdir(cache)), 3)
        os.remove(os.path.join(self.cards, doc + ".json"))
        self.fakes.reset("codex")
        self.assertEqual(self.cards_py("work", "--terms", self.terms, *base)[0], 0)
        self.assertEqual(len(self.fakes.calls("codex")), 4, "notes made with no shield were reused under one")
        self.assertEqual(len(os.listdir(cache)), 6)
        other = os.path.join(self.tmp, "other-terms.txt")
        write(other, "Another Name\n")
        os.remove(os.path.join(self.cards, doc + ".json"))
        self.fakes.reset("codex")
        self.assertEqual(self.cards_py("work", "--terms", other, *base)[0], 0)
        self.assertEqual(len(self.fakes.calls("codex")), 4, "notes made under one terms file were reused under another")
        os.remove(os.path.join(self.cards, doc + ".json"))
        self.fakes.reset("codex")
        self.assertEqual(self.cards_py("work", "--terms", other, *base)[0], 0)
        self.assertEqual(len(self.fakes.calls("codex")), 1, "the same terms file read the sections again")

    def own_terms(self, text):
        path = os.path.join(self.tmp, "own-terms.txt")
        write(path, text)
        return path

    def test_a_name_wrapped_at_a_line_end_or_set_with_a_no_break_space_is_shielded(self):
        """A PDF text layer wraps a name at a line end, and a Word export sets it with a no-break space: both are the name."""
        terms = self.own_terms("Quorvane Holdings\n")
        doc = self.record("03 Home/Lease.pdf", ["Lease between Alex and Quorvane\nHoldings for the flat, and\n"
                                                 "QUORVANE\u00a0Holdings again, narrow\u202fQuorvane Holdings too."])
        self.cards_py("build")
        self.fakes.script("codex", default={"kind": "text"})
        code, _out, err = self.work_run("codex", "--terms", terms)
        self.assertEqual(code, 0, err)
        prompt, = self.prompts()
        for form in ("quorvane", "holdings"):
            self.assertNotIn(form, prompt.lower().replace("[withheld name]", ""))
        self.assertEqual(self.written()[doc]["card_meta"]["shielded"], 3)
        self.assertIn("shielded: 1", err)
        self.assertFalse(os.path.exists(os.path.join(self.work, "state", "ALERT")))

    def test_a_path_stored_in_another_unicode_form_is_shielded(self):
        terms = self.own_terms("Jos\u00e9 Quorvane\n")
        path = unicodedata.normalize("NFD", "03 Home/Letter from Jos\u00e9 Quorvane.pdf")
        doc = self.record(path, ["A letter."])
        self.cards_py("build")
        self.fakes.script("codex", default={"kind": "text"})
        code, _out, err = self.work_run("codex", "--terms", terms)
        self.assertEqual(code, 0, err)
        item, = sent_items(self.prompts()[0])
        self.assertEqual(item["path"], "03 Home/Letter from [withheld name].pdf")
        self.assertEqual(self.written()[doc]["card_meta"]["shielded"], 1)

    def test_a_term_inside_the_placeholder_never_alerts_on_the_placeholder(self):
        """A surname such as Held stands in `[withheld name]`: the card repeats the shielded path, which is no contamination."""
        terms = self.own_terms("Held\n")
        doc = self.record("03 Home/Held letter.pdf", ["A letter."])
        self.cards_py("build")
        self.fakes.script("codex", default={"kind": "text"})
        code, _out, err = self.work_run("codex", "--terms", terms)
        self.assertEqual(code, 0, err)
        self.assertIn("[withheld name] letter.pdf", self.written()[doc]["summary"])
        self.assertFalse(os.path.exists(os.path.join(self.work, "state", "ALERT")))

    def sections(self, pages=None):
        pages = pages or ["Page %d of the reader. " % n + "w" * 3_000 for n in (1, 2, 3)]
        doc = self.record("04 Study/Reader.pdf", pages)
        budget = ["--small-chars", "500", "--single-max", "1000"]
        self.cards_py("build", *budget)
        return doc, ["--engine", "codex", "--section-tokens", "1000"] + budget

    def test_a_section_note_that_names_a_term_alerts_and_is_never_cached(self):
        """The section was sent shielded, so a term in its notes did not come from it: the light model is contaminated."""
        doc, work = self.sections()
        self.fakes.script("codex", default={"kind": "text", "note_suffix": " Seen at Zarnwick Farm."})
        code, _out, err = self.cards_py("work", "--terms", self.terms, *work)
        self.assertEqual(code, 2, err)
        self.assertIn("contamination alert; the note was not cached", err)
        self.assertNotIn("zarnwick", err.lower())
        alert = os.path.join(self.work, "state", "ALERT")
        self.assertTrue(os.path.exists(alert))
        self.assertNotIn("zarnwick", read(alert).lower())
        cache = os.path.join(self.work, "sections")
        self.assertEqual(os.listdir(cache) if os.path.isdir(cache) else [], [], "the contaminated note was cached")
        self.assertEqual(self.written(), {})
        self.assertEqual(len(self.fakes.calls("codex")), 1, "the lane stopped at the first note")

    def test_a_note_that_names_only_a_marker_is_shielded_before_it_is_cached(self):
        doc, work = self.sections()
        self.fakes.script("codex", default={"kind": "text", "note_suffix": " Seen at Zarnwick."})
        code, _out, err = self.cards_py("work", "--terms", self.terms, *work)
        self.assertEqual(code, 0, err)
        cache = os.path.join(self.work, "sections")
        for name in os.listdir(cache):
            self.assertNotIn("zarnwick", read(os.path.join(cache, name)).lower())
        self.assert_no_term(self.prompts()[-1])
        self.assertIn("Seen at [withheld name].", self.prompts()[-1])

    def test_a_term_across_a_cut_is_shielded_before_the_cut(self):
        """The text is shielded whole and cut after: a section boundary and the 20,000-character opening text never split a
        name, so no half of it is sent."""
        terms = self.own_terms("Quorvane Holdings\n")
        name = "Quorvane Holdings"
        lead = "w" * (20_000 - len("[page 1]\n") - 7)  # the opening text's cut falls inside the name
        doc = self.record("04 Study/Reader.pdf", [lead + name + " " + "z" * 6_000])
        self.cards_py("build", "--small-chars", "500", "--single-max", "1000")
        self.fakes.script("codex", default={"kind": "text"})
        code, _out, err = self.cards_py("work", "--terms", terms, "--engine", "codex", "--section-tokens", "1000",
                                        "--small-chars", "500", "--single-max", "1000")
        self.assertEqual(code, 0, err)
        for prompt in self.prompts():
            self.assertNotIn("quorvane", prompt.lower())
            self.assertNotIn("holdings", prompt.lower())
        self.assertIn("[withhe", self.prompts()[-1], "the cut falls inside the placeholder, which does no harm")

    def test_a_card_that_names_the_terms_alerts_whatever_the_document_carries(self):
        self.record(self.PATH, [self.TEXT])
        self.cards_py("build")
        self.fakes.script("codex", default={"kind": "text", "suffix": " Zarnwick Farm."})
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 2, err)
        self.assertEqual(self.written(), {})
        self.assertNotIn("zarnwick", err.lower())

    def test_the_card_records_the_engine_model_effort_and_light_model_a_canary_must_cover(self):
        doc = self.record("03 Home/Rent.pdf", ["Rent for the flat."])
        self.cards_py("build")
        self.fakes.script("codex", default={"kind": "text"})
        code, _out, err = self.work_run("codex", "--terms", self.terms, "--effort", "high", "--light-model", "light-m")
        self.assertEqual(code, 0, err)
        meta = self.written()[doc]["card_meta"]
        self.assertEqual({k: meta[k] for k in ("via", "model", "effort", "light_model", "light_model_effort")},
                         {"via": "codex", "model": "fake-model", "effort": "high", "light_model": "light-m",
                          "light_model_effort": "low"})
        self.assertEqual(meta["shield_sha256"], isolation.shield_digest(isolation.load_terms(self.terms)))
        os.remove(os.path.join(self.cards, doc + ".json"))
        self.fakes.script("agy", default={"kind": "text"})
        code, _out, err = self.work_run("agy", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        meta = self.written()[doc]["card_meta"]
        self.assertEqual((meta["via"], meta["model"]), ("agy", "fake-model"))
        self.assertNotIn("effort", meta, "agy's effort is part of its model id")
        self.assertNotIn("light_model", meta)
        self.assertNotIn("light_model_effort", meta)
        os.remove(os.path.join(self.cards, doc + ".json"))
        code, _out, err = self.work_run("agy", "--no-isolation-terms")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.written()[doc]["card_meta"]["shield_sha256"], "none")


class SectionsTest(CardsCliCase):
    def test_long_documents_are_read_in_sections_with_cached_notes(self):
        pages = ["Page %d of the course reader. " % n + "w" * 3_000 for n in (1, 2, 3)]  # about 800 tokens each
        doc = self.record("04 Study/Course reader.pdf", pages)
        budget = ["--small-chars", "500", "--single-max", "1000"]
        code, _out, err = self.cards_py("build", *budget)
        self.assertEqual(code, 0, err)
        self.assertEqual([bt["mode"] for bt in self.batches().values()], ["sections"])
        self.fakes.script("codex", default={"kind": "text"})
        work = ["--engine", "codex", "--terms", self.terms, "--section-tokens", "1000"] + budget
        code, _out, err = self.cards_py("work", *work)
        self.assertEqual(code, 0, err)
        calls = self.fakes.calls("codex")
        self.assertEqual(len(calls), 4)
        for k, c in enumerate(calls[:3], 1):
            self.assertIn("This is section %d of 3." % k, c["prompt"])
            self.assertIn("Page %d of the course reader." % k, c["prompt"])
            self.assertTrue(c["prompt"].startswith(engines.NO_TOOLS))
            self.assertEqual(c["cwd_listing"], [])
        item = sent_items(calls[3]["prompt"])[0]
        self.assertEqual(item["read"], "sectioned")
        self.assertTrue(item["text"].startswith("SECTION NOTES (the document was read in 3 sections)"))
        for k in (1, 2, 3):
            self.assertIn("[section %d of 3] notes on section %d of 3" % (k, k), item["text"])
        cache = os.path.join(self.work, "sections")
        self.assertEqual(len(os.listdir(cache)), 3)
        for k in (1, 2, 3):
            self.assertEqual(len([f for f in os.listdir(cache) if re.fullmatch(
                r"%s_codex_%d_3_[0-9a-f]{12}\.txt" % (doc[:16], k), f)]), 1, sorted(os.listdir(cache)))
        self.assertEqual(sorted(self.written()), [doc])
        os.remove(os.path.join(self.cards, doc + ".json"))
        self.fakes.reset("codex")
        code, _out, err = self.cards_py("work", *work)
        self.assertEqual(code, 0, err)
        calls = self.fakes.calls("codex")
        self.assertEqual(len(calls), 1, "cached section notes were read again")
        self.assertEqual(sent_items(calls[0]["prompt"])[0]["read"], "sectioned")


    def section_texts(self, engine="agy"):
        """The text each section call was sent, in order, and every call's prompt in UTF-8 bytes: the figure agy's
        cut follows (measured on agy 1.2.16)."""
        calls = self.fakes.calls(engine)
        texts = [c["prompt"].split("SECTION TEXT:\n", 1)[1] for c in calls if "SECTION TEXT:" in c["prompt"]]
        return texts, [len(c["prompt"].encode("utf-8")) for c in calls]

    def agy_work(self, doc_text):
        """A one-page document under agy's own defaults, built and carded; returns the document's id."""
        doc = self.record("04 Study/Annual report.txt", [doc_text])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertEqual([bt["mode"] for bt in self.batches().values()], ["sections"])
        self.fakes.script("agy", default={"kind": "text"})
        code, _out, err = self.cards_py("work", "--engine", "agy", "--model", "fake-model", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        return doc

    def test_a_single_page_document_over_the_byte_limit_is_split_to_fit(self):
        """Text, docx, rtf and csv extractions are one page, so sections cannot split at a page boundary: the page
        itself is split, at paragraph boundaries where it has them, and every call stays under agy's limit."""
        text = "\n\n".join("Paragraph %d. " % k + "w" * 6_990 for k in range(40))
        self.assertGreater(len(text), 280_000)
        doc = self.agy_work(text)
        texts, sizes = self.section_texts()
        self.assertGreaterEqual(len(texts), 5)
        self.assertTrue(all(n <= engines.AGY_MAX_PROMPT_BYTES for n in sizes), sizes)
        self.assertTrue(all(len(t) <= 50_000 for t in texts), [len(t) for t in texts])
        self.assertEqual("".join(texts), "[page 1]\n" + text, "every character must be sent exactly once")
        for t in texts:
            self.assertRegex(t, r"^(\[page 1\]\nParagraph \d+\. |\n\nParagraph \d+\. )", "a paragraph was cut")
        self.assertEqual(self.card_errors(), [])
        card = self.written()[doc]
        self.assertEqual(card["card_meta"]["batch"], os.path.basename(next(iter(self.batches())))[:-5])
        item = sent_items(self.fakes.calls("agy")[-1]["prompt"])[0]
        self.assertEqual(item["read"], "sectioned")
        for k in range(1, len(texts) + 1):
            self.assertIn("[section %d of %d] notes on" % (k, len(texts)), item["text"])
        self.assertNotIn("(unread)", item["text"])

    def test_a_cjk_document_at_the_budget_is_carded_whole_and_one_over_it_in_sections(self):
        """At the budget a document is one call of about 155,000 bytes; a document that a 60,000-character budget
        would have sent whole is over agy's limit in bytes, and is read in sections instead of being refused."""
        whole = self.record("04 Study/Notes.txt", ["\u5b66" * 49_991])  # 50,000 characters with its page marker
        sectioned = self.record("04 Study/Reader.txt", ["\u4e60" * 59_991])  # 60,000
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted((bt["mode"], bt["items"][0]["id"]) for bt in self.batches().values()),
                         sorted([("group", whole), ("sections", sectioned)]))
        self.fakes.script("agy", default={"kind": "text"})
        code, _out, err = self.cards_py("work", "--engine", "agy", "--model", "fake-model", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        sizes = [len(c["prompt"].encode("utf-8")) for c in self.fakes.calls("agy")]
        self.assertTrue(sizes and all(n <= engines.AGY_MAX_PROMPT_BYTES for n in sizes), sizes)
        self.assertEqual(sorted(self.written()), sorted([whole, sectioned]))
        self.assertEqual(self.card_errors(), [])

    def test_a_page_with_no_paragraph_or_line_break_is_cut_by_characters(self):
        text = "学习" * 75_000  # 150,000 CJK characters on one line: 450 KB
        self.agy_work(text)
        texts, sizes = self.section_texts()
        self.assertEqual("".join(texts), "[page 1]\n" + text)
        self.assertEqual([len(t) for t in texts], [50_000, 50_000, 50_000, 9],
                         "the first slice fills the page header's section")
        self.assertTrue(all(n <= engines.AGY_MAX_PROMPT_BYTES for n in sizes), sizes)
        self.assertEqual(self.card_errors(), [])

    def test_a_section_agy_cut_is_not_read_again_at_the_same_size(self):
        """A refusal before the call costs nothing to repeat, but a cut is a whole call: the same section would be cut
        again, so each section is tried once, and the document gets no card, with the cause named."""
        doc = self.record("04 Study/Annual report.txt", ["w" * 60_000])  # 60,009 characters: two sections
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.assertEqual([bt["mode"] for bt in self.batches().values()], ["sections"])
        self.fakes.script("agy", default=CUT)
        code, _out, err = self.cards_py("work", "--engine", "agy", "--model", "fake-model", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        self.assertEqual([("SECTION TEXT:" in c["prompt"]) for c in self.fakes.calls("agy")], [True, True])
        self.assertEqual(self.written(), {})
        self.assertEqual(self.card_errors(), ["card_err_%s.txt" % doc])
        why = read(os.path.join(self.work, "state", "card_err_%s.txt" % doc))
        self.assertIn("2 of 2 sections not read", why)
        self.assertIn("transcript_full.jsonl", why)

    def test_a_section_that_cannot_be_read_leaves_no_card_and_says_so(self):
        """A card made from notes with a hole in them would claim a coverage it lacks: the document gets no card, a
        card_err_ record names what was not read, and a rerun reads only the section that failed."""
        text = "\n\n".join("Paragraph %d. " % k + "w" * 6_990 for k in range(40))
        doc = self.record("04 Study/Annual report.txt", [text])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        fail = {"kind": "fail", "message": "agy: model overloaded"}
        self.fakes.script("agy", replies=[{"kind": "text"}, fail, fail, fail], default={"kind": "text"})  # section 2
        work = ["work", "--engine", "agy", "--model", "fake-model", "--terms", self.terms]
        code, _out, err = self.cards_py(*work)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.written(), {}, "a card was written from notes with a section missing")
        self.assertEqual(self.card_errors(), ["card_err_%s.txt" % doc])
        why = read(os.path.join(self.work, "state", "card_err_%s.txt" % doc))
        self.assertRegex(why, r"section 2 of \d+")
        self.assertIn("not read", why)
        self.assertFalse(any("Input items" in c["prompt"] for c in self.fakes.calls("agy")),
                         "the card call ran with a section missing")
        total = int(re.search(r"section 2 of (\d+)", why).group(1))
        self.assertEqual(len(os.listdir(os.path.join(self.work, "sections"))), total - 1, "the others stay cached")
        self.fakes.reset("agy")
        self.fakes.script("agy", default={"kind": "text"})
        code, _out, err = self.cards_py(*work)
        self.assertEqual(code, 0, err)
        calls = self.fakes.calls("agy")
        self.assertEqual([("SECTION TEXT:" in c["prompt"]) for c in calls], [True, False], "only the failed section")
        self.assertEqual(sorted(self.written()), [doc])
        self.assertEqual(self.card_errors(), [], "a card exists now: its error record is out of date")
        self.assertNotIn("(unread)", sent_items(calls[-1]["prompt"])[0]["text"])

    def test_a_section_over_the_limit_that_splitting_cannot_fix_is_not_carded(self):
        """Four-byte characters can still make a section over agy's limit: it is refused before the call (and not tried
        again), and the document is left without a card rather than carded from the sections that were read."""
        doc = self.record("04 Study/Annual report.txt", ["\U00020000" * 150_000])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        code, _out, err = self.cards_py("work", "--engine", "agy", "--model", "fake-model", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        calls = self.fakes.calls("agy")
        self.assertEqual(len(calls), 1, "only the last, short section fits; the others are refused once each")
        self.assertTrue(all(len(c["prompt"].encode("utf-8")) <= engines.AGY_MAX_PROMPT_BYTES for c in calls))
        self.assertFalse(any("Input items" in c["prompt"] for c in calls), "the card call ran with sections missing")
        self.assertEqual(self.written(), {})
        self.assertEqual(self.card_errors(), ["card_err_%s.txt" % doc])
        why = read(os.path.join(self.work, "state", "card_err_%s.txt" % doc))
        self.assertIn("3 of 4 sections not read", why)
        self.assertIn("byte limit", why)


    def test_a_section_reply_with_no_notes_is_not_a_read_section(self):
        doc = self.record("04 Study/Annual report.txt", ["page text " * 8_000])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        self.fakes.script("agy", default={"kind": "text", "no_notes": True})
        code, _out, err = self.cards_py("work", "--engine", "agy", "--model", "fake-model", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.written(), {})
        self.assertEqual(self.card_errors(), ["card_err_%s.txt" % doc])
        self.assertIn("reply has no notes", read(os.path.join(self.work, "state", "card_err_%s.txt" % doc)))
        self.assertEqual(os.listdir(os.path.join(self.work, "sections")), [], "an empty note was cached")


    def test_redo_reads_a_long_document_in_sections_and_reuses_the_cached_ones(self):
        """The documented recovery: a document left without a card because a section failed is listed in --redo, which
        plans it as a first run would (in sections), so only the section that failed is read again."""
        text = "\n\n".join("Paragraph %d. " % k + "w" * 6_990 for k in range(40))
        doc = self.record("04 Study/Annual report.txt", [text])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        fail = {"kind": "fail", "message": "agy: model overloaded"}
        self.fakes.script("agy", replies=[{"kind": "text"}, fail, fail, fail], default={"kind": "text"})
        work = ["--engine", "agy", "--model", "fake-model", "--terms", self.terms]
        code, _out, err = self.cards_py("work", *work)
        self.assertEqual((code, self.written(), self.card_errors()), (0, {}, ["card_err_%s.txt" % doc]), err)
        redo = os.path.join(self.tmp, "redo.txt")
        write(redo, doc + "\n")
        self.fakes.reset("agy")
        self.fakes.script("agy", default={"kind": "text"})
        code, _out, err = self.cards_py("work", *work, "--redo", redo)
        self.assertEqual(code, 0, err)
        calls = self.fakes.calls("agy")
        self.assertEqual([("SECTION TEXT:" in c["prompt"]) for c in calls], [True, False], "only the failed section")
        self.assertTrue(all(len(c["prompt"].encode("utf-8")) <= engines.AGY_MAX_PROMPT_BYTES for c in calls))
        card = self.written()[doc]
        self.assertEqual(card["card_meta"]["batch"], "redo_0")
        self.assertEqual(self.card_errors(), [])
        self.assertEqual(read(os.path.join(self.work, "state", "redo_done_0.txt")).split(), [doc])
        item = sent_items(calls[-1]["prompt"])[0]
        self.assertEqual(item["read"], "sectioned")
        self.assertNotIn("(unread)", item["text"])

    def test_a_redo_of_a_short_document_is_still_one_call_and_an_unknown_id_is_refused(self):
        doc = self.record("03 Home/Rent.pdf", ["Rent for the flat."])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        redo = os.path.join(self.tmp, "redo.txt")
        write(redo, doc + "\n")
        self.fakes.script("agy", default={"kind": "text"})
        work = ["work", "--engine", "agy", "--model", "fake-model", "--terms", self.terms, "--redo", redo]
        code, _out, err = self.cards_py(*work)
        self.assertEqual(code, 0, err)
        self.assertEqual([item_count(c) for c in self.fakes.calls("agy")], [1])
        write(redo, "0" * 64 + "\n")
        code, _out, err = self.cards_py(*work)
        self.assertEqual(code, 2, err)
        self.assertIn("has no extract record", err)

    def test_a_changed_budget_never_reuses_notes_on_other_text(self):
        """Run one reads section 1 and fails section 2; run two raises the budget. Section 1 now holds more text, so
        its cached notes must not be reused: every character is read, or no card says it was."""
        text = "\n\n".join("Paragraph %d. " % k + "w" * 984 for k in range(98))
        doc = self.record("04 Study/Annual report.txt", [text])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        fail = {"kind": "fail", "message": "agy: model overloaded"}
        self.fakes.script("agy", replies=[{"kind": "text"}, fail, fail, fail], default={"kind": "text"})
        work = ["work", "--engine", "agy", "--model", "fake-model", "--terms", self.terms]
        code, _out, err = self.cards_py(*work, "--section-chars", "60000")
        self.assertEqual((code, self.written()), (0, {}), err)
        self.fakes.reset("agy")
        self.fakes.script("agy", default={"kind": "text"})
        code, _out, err = self.cards_py(*work, "--section-chars", "65000")
        self.assertEqual(code, 0, err)
        texts, _sizes = self.section_texts()
        self.assertEqual("".join(texts), "[page 1]\n" + text, "a range of the document was never read")
        self.assertEqual(sorted(self.written()), [doc])
        self.assertEqual(self.card_errors(), [])


    def test_cached_notes_are_reused_only_for_the_same_model_and_only_when_whole(self):
        """The cache is keyed by the model that wrote the notes (and the budget and the prompt), and a cached file that
        is empty or lacks its header is a miss. To force a re-read, delete the document's files in sections/."""
        text = "\n\n".join("Paragraph %d. " % k + "w" * 6_990 for k in range(40))
        doc = self.record("04 Study/Annual report.txt", [text])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        cache = os.path.join(self.work, "sections")

        def run(model):
            self.fakes.reset("agy")
            self.fakes.script("agy", default={"kind": "text"})
            card = os.path.join(self.cards, doc + ".json")
            if os.path.exists(card):
                os.remove(card)
            code, _out, err = self.cards_py("work", "--engine", "agy", "--model", model, "--terms", self.terms)
            self.assertEqual((code, sorted(self.written())), (0, [doc]), err)
            return sum("SECTION TEXT:" in c["prompt"] for c in self.fakes.calls("agy"))

        sections = run("model-a")
        self.assertGreaterEqual(sections, 5)
        self.assertEqual(run("model-a"), 0, "the same model reads nothing again")
        files = sorted(os.listdir(cache))
        self.assertEqual(len(files), sections)
        write(os.path.join(cache, files[0]), "")
        write(os.path.join(cache, files[1]), "notes with no header, as a partly written file might leave")
        self.assertEqual(run("model-a"), 2, "an empty or headerless cached file is read again")
        self.assertEqual(run("model-b"), sections, "another model's notes are not reused")
        for f in os.listdir(cache):
            if f.startswith(doc[:16]):
                os.remove(os.path.join(cache, f))
        self.assertEqual(run("model-b"), sections, "deleting the document's cache files forces a re-read")
        self.assertEqual([f for f in os.listdir(cache) if ".tmp" in f], [], "a note was left half written")

    def test_a_section_budget_under_the_floor_is_refused(self):
        self.record("04 Study/Annual report.txt", ["page text " * 8_000])
        for flag in ("--section-tokens", "--section-chars"):
            for value in ("1", "999"):
                with self.subTest(flag=flag, value=value):
                    code, _out, err = self.cards_py("build", flag, value)
                    self.assertEqual(code, 2, err)
                    self.assertIn("is under the 1000 floor", err)
                    self.assertNotIn("Traceback", err)
        code, _out, err = self.cards_py("build", "--section-tokens", "1000")
        self.assertEqual(code, 0, err)


class SplitSectionsTest(unittest.TestCase):
    """The packer behind the sections: nothing lost or reordered, nothing over the limit, breaks kept where there are
    any, whichever way a section is sized."""

    TEXT = ("[page 1]\n" + "\n\n".join("Para %d. " % k + "word " * (20 + 90 * (k % 7)) for k in range(30))
            + "\n\n[page 2]\n" + "\n".join("line %d of a table" % k for k in range(400))
            + "\n\n[page 3]\n" + "x" * 9_000 + "\n\n[page 4]\n" + "学习" * 3_000 + "\n\n[page 5]\nShort.")

    def split(self, limit, size):
        return cards.split_sections(self.TEXT.split("\n\n[page "), limit, size)

    def test_sections_join_back_and_fit_by_characters(self):
        for limit in (500, 2_000, 7_000):
            with self.subTest(limit=limit):
                chunks = self.split(limit, len)
                self.assertEqual("".join(chunks), self.TEXT)
                self.assertTrue(all(0 < len(c) <= limit for c in chunks), [len(c) for c in chunks])

    def test_sections_join_back_and_fit_by_estimated_tokens(self):
        for limit in (150, 600, 2_000):
            with self.subTest(limit=limit):
                chunks = self.split(limit, common.est_tokens)
                self.assertEqual("".join(chunks), self.TEXT)
                self.assertTrue(all(0 < common.est_tokens(c) <= limit for c in chunks),
                                [common.est_tokens(c) for c in chunks])

    def test_short_lines_are_not_free_in_a_token_budget(self):
        """The estimate is rounded up, so a section of two-character lines costs what it holds: 400,000 of them are
        many sections under a 110,000-token budget, never one."""
        page = "[page 1]\n" + "\n".join("%02d" % (k % 100) for k in range(400_000))
        chunks = cards.split_sections(page.split("\n\n[page "), 110_000, common.est_tokens)
        self.assertEqual("".join(chunks), page)
        self.assertGreaterEqual(len(chunks), 4)
        self.assertTrue(all(common.est_tokens(c) <= 110_000 for c in chunks), [common.est_tokens(c) for c in chunks])
        self.assertEqual((common.est_tokens(""), common.est_tokens("ab"), common.est_tokens("\u4e2d" * 10)), (0, 1, 11))
        pieces = ["\n12"] * 1_000
        self.assertGreaterEqual(sum(common.est_tokens(x) for x in pieces), common.est_tokens("".join(pieces)))

    def test_a_page_that_fits_is_not_split_and_a_long_one_breaks_at_paragraphs(self):
        chunks = self.split(7_000, len)
        self.assertTrue(any(c.startswith("\n\n[page 5]") or "[page 5]\nShort." in c for c in chunks))
        long_page = "[page 1]\n" + "\n\n".join("P%d " % k + "w" * 900 for k in range(20))
        chunks = cards.split_sections(long_page.split("\n\n[page "), 4_000, len)
        self.assertEqual("".join(chunks), long_page)
        self.assertTrue(all(c.startswith(("[page 1]\nP", "\n\nP")) for c in chunks), "a paragraph was cut")


if __name__ == "__main__":
    unittest.main()
