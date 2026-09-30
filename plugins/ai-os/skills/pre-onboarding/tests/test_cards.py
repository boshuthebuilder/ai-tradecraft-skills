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
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import cards  # noqa: E402
import common  # noqa: E402
import engines  # noqa: E402
from fake_engines import Fakes, tool_env  # noqa: E402

CATEGORIES = common.DEFAULTS["card_categories"]
TERMS = "# isolation terms for the tests (fictional)\nZarnwick Farm|Zarnwick\nOther Project\n"


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
    return json.loads(prompt[prompt.index("\n", prompt.index("Input items (JSON")) + 1:])


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
        out = [card_for(it["id"], it["path"]) for it in items]
        if self.mangle:
            out = self.mangle(out)
        return json.dumps({"items": out}), {"input_tokens": 1}


def swap_first_two(cs):
    if len(cs) >= 2:
        cs[0]["id"], cs[1]["id"] = cs[1]["id"], cs[0]["id"]
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


class SiblingFactsTest(unittest.TestCase):
    """call_chunk: a card carrying a fact (4+ digits, or a key fact) from a sibling's source, not its own, is a
    crossed card: the chunk is rejected even though ids and order are intact."""

    ITEMS = [{"id": eid(path), "path": path, "class": "document", "page_count": 1, "read": "text_layer",
              "text": text} for path, text in [
                  ("02 Finance/Statement.pdf", "Statement for account 55501234, period 2024-03."),
                  ("03 Home/Council tax.pdf", "Council tax bill, reference 77709876, sort 20-00-00."),
                  ("02 Finance/Receipt 2024-05.pdf", "Receipt, no numbers here.")]]

    def setUp(self):
        self.cwd = tempfile.mkdtemp(prefix="facts_test_")
        self.addCleanup(shutil.rmtree, self.cwd, True)

    def join(self, mangle):
        return cards.call_chunk(StubEngine(mangle), "I", self.ITEMS, CATEGORIES, None, self.cwd)

    def test_crossed_contents_are_rejected(self):
        def cross(cs):
            cs[0]["summary"], cs[1]["summary"] = "Council tax, reference 77709876.", "Account 55501234."
            return cs

        def crossed_key_fact(cs):
            cs[2]["key_facts"]["reference_numbers"] = ["reference 77709876"]
            return cs

        def crossed_date(cs):
            cs[1]["key_facts"]["dates"] = ["period 2024-03"]
            return cs

        def crossed_short_digits(cs):
            cs[0]["key_facts"]["reference_numbers"] = ["sort 20-00-00"]  # no run of four digits: the key fact alone
            return cs
        for name, mangle in (("digits", cross), ("a key fact", crossed_key_fact), ("a dated key fact", crossed_date),
                             ("a key fact without four digits in a row", crossed_short_digits)):
            with self.subTest(name):
                with self.assertRaisesRegex(ValueError, "from d\\d's source"):
                    self.join(mangle)

    def test_facts_of_its_own_or_of_nobody_are_accepted(self):
        def own(cs):
            cs[0]["key_facts"]["reference_numbers"] = ["account 55501234"]
            cs[0]["summary"] = "Statement for account 55501234."
            return cs

        def nobody(cs):
            cs[2]["summary"] = "Receipt from 2019, total 4999."
            return cs

        def from_its_path(cs):
            cs[2]["title"] = "Receipt of May 2024"  # the year is in its own path, and in a sibling's text
            return cs
        for name, mangle in (("its own", own), ("nobody's", nobody), ("its own path", from_its_path)):
            with self.subTest(name):
                got, _usage = self.join(mangle)
                self.assertEqual(len(got), 3)

    def test_a_fact_both_sources_carry_is_accepted(self):
        items = [dict(it, text=it["text"] + " Customer 99990000.") for it in self.ITEMS[:2]]

        def shared(cs):
            cs[0]["summary"] = cs[1]["summary"] = "Customer 99990000."
            return cs
        got, _usage = cards.call_chunk(StubEngine(shared), "I", items, CATEGORIES, None, self.cwd)
        self.assertEqual(len(got), 2)


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

    def record(self, path, pages, status="ok", tier="text_layer"):
        i = eid(path)
        rec = {"id": i, "path": path, "class": "document", "status": status, "page_count": len(pages),
               "tiers": {tier: len(pages)}, "pages": [{"n": n + 1, "tier": tier, "text": t}
                                                      for n, t in enumerate(pages)]}
        rec["chars"] = sum(len(t) for t in pages)
        write(os.path.join(self.extract, i + ".json"), json.dumps(rec, ensure_ascii=False))
        return i

    def cards_py(self, *args):
        cmd = [sys.executable, os.path.join(TOOLS, "cards.py")] + list(args[:1]) + [
            "--root", self.root, "--work", self.work, "--extract", self.extract, "--out", self.cards] + list(args[1:])
        r = subprocess.run(cmd, capture_output=True, text=True, env=self.env)
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


class WorkTest(CardsCliCase):
    def two_docs(self, text_a="Rent for the flat.", text_b="Council tax bill."):
        a = self.record("03 Home/Rent.pdf", [text_a])
        b = self.record("03 Home/Council tax.pdf", [text_b])
        code, _out, err = self.cards_py("build")
        self.assertEqual(code, 0, err)
        return a, b

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
                schema = c["argv"][c["argv"].index("--output-schema" if engine == "codex" else "--json-schema") + 1]
                self.assertEqual(os.path.basename(schema), "card_codex.json" if engine == "codex" else "card.json")

    def test_a_crossing_engine_is_rejected_and_halved_and_never_written(self):
        """Ids and order intact, contents crossed: only the sibling-facts check can see it."""
        a, b = self.two_docs("Rent for the flat, reference 55501234.", "Council tax bill, account 77709876.")
        self.fakes.script("codex", default={"kind": "text", "cross": True}, watch=self.cards)
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        calls = self.fakes.calls("codex")
        self.assertEqual([item_count(c) for c in calls], [2, 2, 2, 1, 1])
        self.assertTrue(all(c["watch"] == [] for c in calls), "a card was written mid-batch")
        self.assertIn("carries a fact from", err)
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


class ContaminationTest(CardsCliCase):
    """A term in a card is an alert only when the card's own source text lacks it; one alert writes no card."""

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

    def test_a_term_its_own_source_carries_is_not_an_alert(self):
        ids = self.docs("Rent paid to Zarnwick Farm.", "Council tax for Zarnwick, the farm.")
        code, _out, err = self.work_run("codex", "--terms", self.terms)
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(self.written()), sorted(ids))
        self.assertFalse(os.path.exists(os.path.join(self.work, "state", "ALERT")))

    def test_no_isolation_terms_by_decision(self):
        ids = self.docs("Rent.", "Council tax.")
        code, _out, err = self.work_run("codex", "--no-isolation-terms")
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(self.written()), sorted(ids))
        self.assertIn("by operator decision", err)


class SectionsTest(CardsCliCase):
    def test_long_documents_are_read_in_sections_with_cached_notes(self):
        pages = ["Page %d of the course reader. " % n + "w" * 400 for n in (1, 2, 3)]
        doc = self.record("04 Study/Course reader.pdf", pages)
        budget = ["--small-chars", "500", "--single-max", "1000"]
        code, _out, err = self.cards_py("build", *budget)
        self.assertEqual(code, 0, err)
        self.assertEqual([bt["mode"] for bt in self.batches().values()], ["sections"])
        self.fakes.script("codex", default={"kind": "text"})
        work = ["--engine", "codex", "--terms", self.terms, "--section-tokens", "150"] + budget
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
        self.assertEqual(sorted(os.listdir(cache)), ["%s_codex_%d_3.txt" % (doc[:16], k) for k in (1, 2, 3)])
        self.assertEqual(sorted(self.written()), [doc])
        os.remove(os.path.join(self.cards, doc + ".json"))
        self.fakes.reset("codex")
        code, _out, err = self.cards_py("work", *work)
        self.assertEqual(code, 0, err)
        calls = self.fakes.calls("codex")
        self.assertEqual(len(calls), 1, "cached section notes were read again")
        self.assertEqual(sent_items(calls[0]["prompt"])[0]["read"], "sectioned")


if __name__ == "__main__":
    unittest.main()
