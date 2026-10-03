#!/usr/bin/env python3
"""One card per live document, written by a model (agy or codex) from the document's whole extracted text.

    cards.py build --root R                                    plan batches from finished extract records
    cards.py work  --root R --engine agy --model M --terms F [--worker 0/3] [--redo ids.txt]

Batches: small documents share a call (group), long ones get their own (single), and documents over the context
budget are read section by section into cached notes, then carded from the notes (sections). Instructions come from
`templates/card-instructions.md`, filled from the folder's own settings (people, description, categories,
identifier policy). A section is at most the budget, whatever the document: a page over it (a text, Word or csv
extraction is one page) is split at paragraph, then line, then character breaks. A section that cannot be read means
no card, a `card_err_<id>.txt` naming it, and the notes already read cached for the rerun: a card made from the rest
would claim a read it lacks.

The join is deterministic: each call issues short ids (d1, d2, ...) for the items it sends, and a reply is applied
only when it passes three checks, each catching something different:

- Ids: the reply's ids are exactly the ids sent, in the order sent. This catches a missing, extra, duplicated or
  unknown id, and two ids swapped while the cards stay in place. It also rejects a correct reply in another order
  (the instructions ask for the order sent), which costs a retry of the chunk.
- Schema: every card meets the card schema (schemas/card.json).
- Sibling identifiers: in a chunk of two or more items, no card carries an identifier that is in another item's
  source (its path and text) but not in its own. An identifier is a run of digits of five or more once the spaces,
  hyphens and slashes inside it are removed, that is not an amount (a run with a decimal point or a thousands
  comma) and not year- or date-shaped (every part a year or at most two digits, or a compact yyyymm, mmyyyy,
  yyyymmdd or ddmmyyyy); a part of five or more digits inside a longer run counts on its own too. Identifiers are
  compared as digit strings, so "12-34-56 12345678" matches "123456 12345678"; key_facts count only through the
  identifiers in them, and `look` is not checked, since it is asked to name other files. This catches a card whose
  contents were crossed with a sibling's while the ids and their order stayed intact, when either card carries such
  an identifier (an account, invoice, policy or passport number). It does not catch a crossing distinguished only by
  names, addresses, dates, amounts or short numbers, and a chunk of one item (a single or sections batch, every
  --redo batch, the last step of halving) has no siblings, so it is not checked. A crossing is deterministic: the
  chunk is halved at once instead of being retried at the same size.

Otherwise the chunk is retried, then halved, and never applied in part. Every item of a chunk that still fails is
recorded in <work>/state/card_err_<id>.txt. Before any card of a batch is written, the contamination guard checks
them all: a term from the operator's isolation list that a card names but its own source text does not carry
writes <work>/state/ALERT, writes none of them and stops every worker. With --redo, an id counts as redone only once
its card is written.
"""
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import engines  # noqa: E402
import isolation  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FINAL = {"ok", "partial", "blank", "photo", "listed", "no_reader", "failed"}
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool}
RUN = re.compile(r"\d+(?:[ ,./\-]\d+)*")  # digits, and the single separators that may sit inside one number
YEAR = re.compile(r"(?:19|20)\d\d$")
SECTION_PROMPT = """You are reading one section of a long document from a private archive, to help write a
catalogue card for the whole document later. Document path: {path}. This is section {k} of {n}.
Reply directly with JSON only: {{"notes": "..."}} where notes (at most 200 words, UK English) record what this
section covers, the people and organisations named, dates, amounts, and anything that identifies what the document
is and why it is in this folder. {identifier_rule} Do not create plans or files and do not run commands.

SECTION TEXT:
{text}"""


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def mode_for(chars, b):
    """How a document of `chars` characters is sent: with others (group), alone (single) or in sections."""
    return "group" if chars <= b.small_chars else "single" if chars <= b.single_max else "sections"


class Budget:
    def __init__(self, a):
        self.small_chars, self.batch_chars = a.small_chars, a.batch_chars
        self.batch_items, self.textless_batch = a.batch_items, a.textless_batch
        self.section_chars, self.single_max = a.section_chars, a.single_max
        self.section_tokens, self.single_tokens = a.section_tokens, a.single_tokens


def read_label(tiers):
    t = {k for k, v in (tiers or {}).items() if v} - {"blank"}
    if not t or t <= {"photo", "none", "unread"}:
        return "none"
    if len(t) == 1:
        return {"text_layer": "text_layer", "local_ocr": "local_ocr", "vision": "vision",
                "listing": "text_layer"}.get(next(iter(t)), "mixed")
    return "mixed"


def full_text(r):
    parts = []
    for p in r.get("pages", []):
        tx = (p.get("text") or "").strip()
        if tx and p.get("tier") != "photo":
            parts.append("[page %d]\n%s" % (p.get("n", 0), tx))
    return "\n\n".join(parts)


def identifier_rule(rb):
    if rb["identifiers"] == "stated":
        return "written IN FULL exactly as in the document"
    if rb["identifiers"] == "last-four":
        return "written as their last four characters only"
    return "written in full only on the document's own home page; elsewhere their last four characters"


def instructions(rb):
    people = "\n".join("- %s (also: %s): %s" % (p.get("name"), ", ".join(p.get("also", [])) or "none",
                                                  p.get("who", "")) for p in rb["people"]) or "- none recorded"
    t = read_text(os.path.join(HERE, "templates", "card-instructions.md"))
    return t.format(folder_description=rb["folder_description"] or "No description recorded.", people=people,
                    categories=", ".join(rb["card_categories"]), identifier_rule=identifier_rule(rb))


class Run:
    def __init__(self, a):
        self.root, settings_dir, self.work = common.resolve(a)
        self.rb = common.load_rulebook(self.root, settings_dir)
        self.extract = os.path.realpath(a.extract) if a.extract else os.path.join(self.root, "_Audit", "extract")
        self.cards = os.path.realpath(a.out) if a.out else os.path.join(self.root, "_Audit", "cards")
        self.batches = os.path.join(self.work, "batches")
        self.state = os.path.join(self.work, "state")
        os.makedirs(self.state, exist_ok=True)
        self.alert = os.path.join(self.state, "ALERT")
        self.writer = common.Writer(self.root if getattr(a, "read_only_root", False) else None)
        self.budget = Budget(a)

    def record(self, eid):
        return load_json(os.path.join(self.extract, eid + ".json"))

    def payload(self, eid, text_override=None):
        r = self.record(eid)
        return {"id": eid, "path": r["path"], "class": r["class"], "page_count": r.get("page_count", 0),
                "read": read_label(r.get("tiers")), "text": full_text(r) if text_override is None else text_override}


def build(a):
    run = Run(a)
    b = run.budget
    os.makedirs(run.batches, exist_ok=True)
    planned = {it["id"] for f in glob.glob(os.path.join(run.batches, "*.json"))
               for it in load_json(f)["items"]}
    buckets = {0: [], 1: [], 2: [], 3: []}
    waiting = 0
    for f in sorted(os.listdir(run.extract)):
        if not f.endswith(".json"):
            continue
        eid = f[:-5]
        if eid in planned or os.path.exists(os.path.join(run.cards, eid + ".json")):
            continue
        r = load_json(os.path.join(run.extract, f))
        if r.get("status") not in FINAL:
            waiting += 1
            continue
        chars = len(full_text(r))
        pc = r.get("page_count", 0)
        buckets[1 if chars < 20 else 0 if pc <= 20 else 2 if pc <= 100 else 3].append({"id": eid, "chars": chars})
    seq = len(glob.glob(os.path.join(run.batches, "*.json")))
    made = 0
    for bk in (0, 1, 2, 3):
        cur, cur_chars = [], 0
        for it in sorted(buckets[bk], key=lambda x: x["id"]) + [None]:
            flush = it is None or (it["chars"] <= b.small_chars and cur and (
                len(cur) >= (b.textless_batch if bk == 1 else b.batch_items)
                or cur_chars + it["chars"] > b.batch_chars))
            if flush and cur:
                common.Writer().json(os.path.join(run.batches, "%d_%05d.json" % (bk, seq)),
                                     {"bucket": bk, "mode": "group", "items": cur})
                seq, made, cur, cur_chars = seq + 1, made + 1, [], 0
            if it is None:
                break
            if it["chars"] > b.small_chars:
                common.Writer().json(os.path.join(run.batches, "%d_%05d.json" % (bk, seq)),
                                     {"bucket": bk, "mode": mode_for(it["chars"], b), "items": [it]})
                seq, made = seq + 1, made + 1
                continue
            cur.append(it)
            cur_chars += it["chars"]
    print("build: %d new batches, %d records still waiting for extraction" % (made, waiting))
    return 0


def schema_problems(value, schema, where="card"):
    """How `value` breaks `schema`, in the subset of JSON Schema the card schemas use (type, properties, required,
    items)."""
    want = TYPES.get(schema.get("type"))
    if want and not isinstance(value, want):
        return ["%s is not %s" % (where, schema["type"])]
    out = []
    if isinstance(value, dict):
        out += ["%s.%s is missing" % (where, k) for k in schema.get("required", []) if k not in value]
        out += [p for k, sub in schema.get("properties", {}).items() if k in value
                for p in schema_problems(value[k], sub, "%s.%s" % (where, k))]
    if isinstance(value, list) and "items" in schema:
        out += [p for i, x in enumerate(value) for p in schema_problems(x, schema["items"], "%s[%d]" % (where, i))]
    return out


with open(os.path.join(HERE, "schemas", "card.json"), encoding="utf-8") as _f:
    CARD_SCHEMA = json.load(_f)["properties"]["items"]["items"]


def validate(card, categories):
    """The card when it meets the card schema, else None. A category outside the folder's list becomes Other, with
    the model's word kept as category_raw."""
    if schema_problems(card, CARD_SCHEMA):
        return None
    if card["category"] not in categories:
        card["category_raw"] = card["category"]
        card["category"] = "Other"
    return card


class Crossed(ValueError):
    """A card carries a sibling's identifier. Deterministic: the chunk is halved rather than retried as it is."""


def date_shaped(parts):
    """True for a run whose parts read as a year or a date in the common forms."""
    def month(g):
        return len(g) == 2 and 1 <= int(g) <= 12

    def day(g):
        return len(g) == 2 and 1 <= int(g) <= 31
    if len(parts) > 1:
        return all(len(g) <= 2 or YEAR.match(g) for g in parts)
    g = parts[0]
    if len(g) == 6:
        return bool(YEAR.match(g[:4]) and month(g[4:]) or month(g[:2]) and YEAR.match(g[2:]))
    if len(g) == 8:
        return bool(YEAR.match(g[:4]) and month(g[4:6]) and day(g[6:])
                    or day(g[:2]) and month(g[2:4]) and YEAR.match(g[4:]))
    return bool(YEAR.match(g))


def identifiers(text):
    """The identifier-like digit strings in `text` (see the module docstring)."""
    found = set()
    for m in RUN.finditer(text):
        run = m.group(0)
        if "," in run or "." in run:
            continue  # an amount, or a dotted date
        parts = re.split(r"[ /\-]", run)
        for digits, shape in [("".join(parts), parts)] + [(g, [g]) for g in parts if len(parts) > 1]:
            if len(digits) >= 5 and not date_shaped(shape):
                found.add(digits)
    return found


def card_identifiers(card):
    """The identifiers in every text of a card, except its id and `look` (which is asked to name other files)."""
    texts = []

    def walk(v):
        if isinstance(v, str):
            texts.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk({k: v for k, v in card.items() if k not in ("id", "look")})
    return set().union(*(identifiers(t) for t in texts)) if texts else set()


def source_digits(item):
    """Every digit run of an item's source (its path and text), as digit strings, joined by a separator."""
    text = "%s\n%s" % (item.get("path", ""), item.get("text", ""))
    return "|".join(re.sub(r"\D", "", m.group(0)) for m in RUN.finditer(text))


def crossed(cards, items):
    """(short id, [short ids of the siblings whose sources hold it]) for the first card carrying an identifier that
    its own source lacks and a sibling's source holds, else None. A chunk of one item has no siblings."""
    if len(items) < 2:
        return None
    sources = {k: source_digits(it) for k, it in items.items()}
    for k, c in cards.items():
        for ident in sorted(card_identifiers(c)):
            if ident in sources[k]:
                continue
            holders = [j for j, s in sources.items() if j != k and ident in s]
            if holders:
                return k, holders
    return None


def call_chunk(engine, instr, items, categories, schema, cwd):
    """One call for `items`. Returns {real id: card} only when the reply passes the three checks in the module
    docstring: ids, schema and sibling facts."""
    short = {"d%d" % (i + 1): it for i, it in enumerate(items)}
    sent = [dict(it, id=k) for k, it in short.items()]
    prompt = engines.NO_TOOLS + instr + "\n\nInput items (JSON, %d items):\n" % len(sent) + json.dumps(
        sent, ensure_ascii=False)
    reply, usage = engine(prompt, cwd, schema=schema)
    obj = common.parse_json(reply)
    arr = obj.get("items") if isinstance(obj, dict) else obj
    if not isinstance(arr, list):
        raise ValueError("reply has no items list")
    ids = [c.get("id") if isinstance(c, dict) else None for c in arr]
    if ids != list(short):
        raise ValueError("reply ids %s are not the ids sent, in order (%s)" % (ids[:8], list(short)[:8]))
    checked = {}
    for c in arr:
        card = validate(dict(c), categories)
        if card is None:
            raise ValueError("invalid card for %s: %s" % (c["id"], "; ".join(schema_problems(c, CARD_SCHEMA)[:3])))
        checked[c["id"]] = card
    hit = crossed(checked, short)
    if hit:
        raise Crossed("card %s carries an identifier that its own source lacks and the source of %s holds"
                      % (hit[0], ", ".join(hit[1])))
    out = {}
    for k, card in checked.items():
        card["id"] = short[k]["id"]
        out[card["id"]] = card
    return out, usage


def run_items(run, engine, instr, items, schema, log, sink, depth=0):
    last = "?"
    for attempt in range(3):
        d = engines.fresh_dir("cards_")
        try:
            got, usage = call_chunk(engine, instr, items, run.rb["card_categories"], schema, d)
            sink.update(got)
            log("  %d items ok usage=%s" % (len(items), json.dumps(usage)))
            return
        except (engines.QuotaError, common.ToolError):
            raise
        except Crossed as ex:
            last = str(ex)[:200]
            log("  attempt %d for %d items: %s; halving at once" % (attempt + 1, len(items), last))
            break  # the same chunk would cross the same way
        except (engines.EngineError, ValueError) as ex:
            last = str(ex)[:200]
            log("  attempt %d for %d items: %s" % (attempt + 1, len(items), last))
        finally:
            shutil.rmtree(d, True)
    if len(items) > 1 and depth < 6:
        h = len(items) // 2
        run_items(run, engine, instr, items[:h], schema, log, sink, depth + 1)
        run_items(run, engine, instr, items[h:], schema, log, sink, depth + 1)
        return
    for it in items:
        record_failure(run, it["id"], last)


def record_failure(run, eid, why):
    with open(os.path.join(run.state, "card_err_%s.txt" % eid), "w", encoding="utf-8") as f:
        f.write(why)


class SectionsUnread(Exception):
    """A section of a long document could not be read. A card made from the others would claim a read it lacks, so
    the document gets no card."""


def widest_fit(limit, size):
    """How many characters of the costliest kind (a wide one) `size` still puts within `limit`, at least one."""
    lo, hi = 1, max(1, limit)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if size("\u4e2d" * mid) <= limit:
            lo = mid
        else:
            hi = mid - 1
    return lo


def split_sections(blocks, limit, size):
    """`blocks` (a document's pages) packed in order into sections none over `limit` by `size`. A page goes whole into
    the section in progress when it fits there, else starts the next; a page over the limit by itself is split at
    paragraph breaks, a paragraph still over at line breaks, a line still over at any character, each break kept at
    the start of the part after it. Joined, the sections are the blocks again."""
    chunks, cur, used = [], "", 0
    step = widest_fit(limit, size)  # characters that always fit

    def add(piece, seps):
        nonlocal cur, used
        n = size(piece)
        if used + n <= limit:
            cur, used = cur + piece, used + n
        elif n <= limit:
            chunks.append(cur)
            cur, used = piece, n
        elif seps:
            head, *rest = piece.split(seps[0])
            add(head, seps[1:])
            for part in rest:
                add(seps[0] + part, seps[1:])
        else:
            width = widest_fit(limit - used, size)  # the first slice fills the section in progress
            while piece:
                add(piece[:width], ())
                piece, width = piece[width:], step

    for i, block in enumerate(blocks):
        add(block if i == 0 else "\n\n[page " + block, ("\n\n", "\n"))
    if cur:
        chunks.append(cur)
    return chunks


def read_section(engine_light, rb, path, k, n, text, log):
    """(notes, None) for one section, or (None, why) after three tries; a section over agy's byte limit is not
    retried, since the same text would be refused again."""
    last = "?"
    for attempt in range(3):
        d = engines.fresh_dir("sections_")
        try:
            resp, _usage = engine_light(engines.NO_TOOLS + SECTION_PROMPT.format(
                path=path, k=k, n=n, text=text,
                identifier_rule="Write reference numbers %s." % identifier_rule(rb)), d)
            obj = common.parse_json(resp)
            notes = obj.get("notes") if isinstance(obj, dict) else None
            if not isinstance(notes, str) or not notes.strip():
                raise ValueError("reply has no notes")
            return "[section %d of %d] %s" % (k, n, notes), None
        except (engines.QuotaError, common.ToolError):
            raise
        except engines.PromptTooLong as ex:
            return None, str(ex)[:200]
        except (engines.EngineError, ValueError) as ex:
            last = str(ex)[:200]
            log("  section %d/%d attempt %d failed: %s" % (k, n, attempt + 1, last[:160]))
        finally:
            shutil.rmtree(d, True)
    return None, last


def sections_text(run, engine_light, eid, log, engine_name):
    """The text a long document is carded from: the notes on every section, then its first 20,000 characters. Raises
    SectionsUnread when any section could not be read; the notes that were read stay cached for the rerun."""
    it = run.payload(eid)
    text = it["text"]
    b = run.budget
    size = common.est_tokens if b.section_tokens else len
    limit = b.section_tokens or b.section_chars
    chunks = split_sections(text.split("\n\n[page "), limit, size)
    budget = "%s:%d" % ("tokens" if b.section_tokens else "chars", limit)
    cache = os.path.join(run.work, "sections")
    os.makedirs(cache, exist_ok=True)
    notes, unread = [], []
    for k, c in enumerate(chunks, 1):
        # named by the section's own text and the budget, so a changed budget can never reuse notes on other text
        digest = hashlib.sha256((budget + "\n" + c).encode("utf-8")).hexdigest()[:12]
        cp = os.path.join(cache, "%s_%s_%d_%d_%s.txt" % (eid[:16], engine_name, k, len(chunks), digest))
        if os.path.exists(cp):
            with open(cp, encoding="utf-8") as f:
                notes.append(f.read())
            continue
        note, why = read_section(engine_light, run.rb, it["path"], k, len(chunks), c, log)
        if note is None:
            unread.append("section %d of %d: %s" % (k, len(chunks), why))
            continue
        with open(cp, "w", encoding="utf-8") as f:
            f.write(note)
        notes.append(note)
    if unread:
        raise SectionsUnread("%d of %d sections not read, so no card is written from the rest (rerun once the cause "
                             "is fixed; the sections already read are cached): %s"
                             % (len(unread), len(chunks), "; ".join(unread)))
    return "SECTION NOTES (the document was read in %d sections):\n%s\n\nOPENING TEXT:\n%s" % (
        len(chunks), "\n".join(notes), text[:20000])


def write_cards(run, cards, batch_name, evidence, meta, log):
    """Every card is checked before any is written: one alert writes none of them."""
    for eid, c in cards.items():
        src = full_text(run.record(eid))
        blob = json.dumps(c, ensure_ascii=False)
        bad = isolation.contamination(blob, src, evidence) if evidence else []
        if bad:
            with open(run.alert, "w", encoding="utf-8") as f:
                f.write("contamination: card %s names %d isolation term(s) absent from its source\n"
                        % (eid, len(bad)))
            log("ALERT: card %s names isolation terms absent from its source" % eid[:12])
            raise common.ToolError("contamination alert; no card of this batch written; every worker stops")
    for eid, c in cards.items():
        c["card_meta"] = dict(meta, batch=batch_name, created_at=common.now_local())
        run.writer.json(os.path.join(run.cards, eid + ".json"), c, indent=1)
        stale = os.path.join(run.state, "card_err_%s.txt" % eid)
        if os.path.exists(stale):
            os.remove(stale)  # the card exists now: the record of why it did not is out of date


def redo_mode(run, eid):
    """A redone document is sent as a first run would send it (its size decides: a long one in sections, with their
    cached notes), never whole in one call: that is what a document with sections left to read cannot survive."""
    path = os.path.join(run.extract, eid + ".json")
    if not os.path.exists(path):
        raise common.ToolError("--redo names %s, which has no extract record in %s" % (eid, run.extract))
    return mode_for(len(full_text(load_json(path))), run.budget)


def work(a):
    run = Run(a)
    b = run.budget
    wi, wn = [int(x) for x in a.worker.split("/")]
    log = common.logger(run.work, ("redo%d" if a.redo else "cards%d") % wi)
    if a.no_isolation_terms:
        evidence = {}
        log("isolation terms: none, by operator decision (--no-isolation-terms)")
    else:
        evidence = isolation.load_terms(a.terms)
    if a.engine == "codex":
        engine = engines.Codex(a.model, effort=a.effort)
        light = engines.Codex(a.light_model, effort="low") if a.light_model else engine
        schema = os.path.join(HERE, "schemas", "card_codex.json")
    else:
        engine = light = engines.Agy(a.model)
        schema = os.path.join(HERE, "schemas", "card.json")
    meta = {"model": a.model or "cli-default", "via": a.engine}
    instr = instructions(run.rb)
    run.writer.makedirs(run.cards)
    if a.redo:
        ids = [x.strip() for x in read_text(a.redo).splitlines() if x.strip()]
        batches = [{"name": "redo_%d" % i, "mode": redo_mode(run, x), "items": [{"id": x}]}
                   for i, x in enumerate(ids) if i % wn == wi]
        done_p = os.path.join(run.state, "redo_done_%d.txt" % wi)
        redone = {x.strip() for x in read_text(done_p).splitlines()} if os.path.exists(done_p) else set()

        def has(e):
            return e in redone

        def written(cards):
            """Record ids as redone only once write_cards has written their cards."""
            with open(done_p, "a", encoding="utf-8") as fh:
                for eid in cards:
                    fh.write(eid + "\n")
                    redone.add(eid)
    else:
        files = sorted(glob.glob(os.path.join(run.batches, "*.json")))
        batches = [dict(load_json(f), name=os.path.basename(f)[:-5]) for i, f in enumerate(files) if i % wn == wi]

        def has(e):
            return os.path.exists(os.path.join(run.cards, e + ".json"))

        def written(cards):
            pass
    for bt in batches:
        if os.path.exists(run.alert):
            log("ALERT present, stopping")
            return 3
        todo = [it["id"] for it in bt["items"] if not has(it["id"])]
        if not todo:
            continue
        t0 = time.time()
        while todo:
            sink = {}
            try:
                big = bt["mode"] == "sections" or (bt["mode"] == "single" and b.single_tokens and
                                                    common.est_tokens(run.payload(todo[0])["text"]) > b.single_tokens)
                if big:
                    items = [dict(run.payload(todo[0], sections_text(run, light, todo[0], log, a.engine)),
                                  read="sectioned")]
                else:
                    items = [run.payload(e) for e in todo]
                run_items(run, engine, instr, items, schema, log, sink)
                write_cards(run, sink, bt["name"], evidence, meta, log)
                written(sink)
                todo = []
            except SectionsUnread as ex:
                record_failure(run, todo[0], str(ex))
                log("  %s: %s" % (todo[0][:12], ex))
                todo = []
            except engines.QuotaError as ex:
                write_cards(run, sink, bt["name"], evidence, meta, log)
                written(sink)
                wait = min(5 * 3600, (ex.reset_seconds or (1800 if a.engine == "codex" else 600)) + 90)
                log("quota on %s; sleeping %d min" % (bt["name"], wait // 60))
                time.sleep(wait)
                todo = [e for e in todo if not has(e)]
        log("batch %s mode=%s carded in %.0fs" % (bt["name"], bt["mode"], time.time() - t0))
    with open(os.path.join(run.state, ("redo%d" if a.redo else "cards%d") % wi + ".done"), "w", encoding="utf-8") as f:
        f.write(common.now_local())
    log("worker finished")
    return 0


def main():
    ap = common.base_args("Per-document cards")
    ap.add_argument("cmd", choices=["build", "work"])
    ap.add_argument("--extract", help="extract records (default <root>/_Audit/extract)")
    ap.add_argument("--out", help="cards directory (default <root>/_Audit/cards)")
    ap.add_argument("--engine", choices=["agy", "codex"], default="agy")
    ap.add_argument("--model", help="engine model id (agy: effort encoded in the id)")
    ap.add_argument("--effort", default="medium", help="codex reasoning effort")
    ap.add_argument("--light-model", help="codex model for section notes")
    ap.add_argument("--terms", help="the operator's isolation terms file")
    ap.add_argument("--no-isolation-terms", action="store_true",
                    help="state explicitly that no other project needs isolating (logged)")
    ap.add_argument("--worker", default="0/1")
    ap.add_argument("--redo", help="file of ids to re-card even though cards exist")
    ap.add_argument("--small-chars", type=int, default=60_000)
    ap.add_argument("--batch-chars", type=int, help="default 180000; agy 60000")
    ap.add_argument("--batch-items", type=int, default=30)
    ap.add_argument("--textless-batch", type=int, default=60)
    ap.add_argument("--section-chars", type=int, help="default 400000; agy 60000")
    ap.add_argument("--single-max", type=int, help="default 600000; agy 60000")
    ap.add_argument("--section-tokens", type=int, help="budget sections by estimated tokens (codex: 110000)")
    ap.add_argument("--single-tokens", type=int, help="largest single call in estimated tokens (codex: 150000)")
    a = ap.parse_args()
    # agy refuses a message over engines.AGY_MAX_MESSAGE_BYTES; 60,000 characters stays under it even at three bytes
    # a character (CJK text), with room for the instructions
    wide = {"batch_chars": 180_000, "section_chars": 400_000, "single_max": 600_000}
    for k, v in wide.items():
        if getattr(a, k) is None:
            setattr(a, k, 60_000 if a.engine == "agy" else v)
    if a.cmd == "work" and not (a.terms or a.no_isolation_terms):
        raise common.ToolError("give --terms (the isolation list) or --no-isolation-terms")
    if a.cmd == "work" and a.engine == "agy" and not a.model:
        raise common.ToolError(engines.AGY_MODEL_REQUIRED)
    return build(a) if a.cmd == "build" else work(a)


if __name__ == "__main__":
    common.run_main(main)
