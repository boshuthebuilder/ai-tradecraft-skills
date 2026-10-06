#!/usr/bin/env python3
"""Keep other projects out of model-facing context.

The operator supplies a terms file (never committed, never inside the folder, never shown to a model): one term per
line, optionally `Term|marker|marker`, where the markers are shorter forms that, when present in a document's own
text, show the term is genuine content of that document. Lines starting with `#` are comments.

    isolation.py scan   --terms F --path <file or dir> [...] [--if-present <file> ...] [--out <result.json>]
    isolation.py canary --terms F --engine agy|codex [--model M] [--effort E] --out <result.json>

The scan reads every file named, and every model-facing file (prompts, templates, schemas, code, config such as
`config.toml` or `jobs.yaml`) under a folder named, following links into folders (skills are often installed as
links) with each real folder read once, so a link loop ends; a broken link is an error, never a skip. A path that
does not exist is an error and a scan that checked no file fails. Every --path and --if-present is expanded here (`~`
and environment variables), so a quoted `~` works, and is an error when an expansion is left undone: a leading `~` or
`~user` for a user this machine lacks, or a `$NAME` that is not set. A `~` inside a name is part of the name and is
accepted (every iCloud Drive path has one, in `com~apple~CloudDocs`). An --if-present file (an engine's global
instructions, or a file in a folder kept anywhere) is read when the machine has it and listed in `absent`, and on
stderr, when it does not; but a path whose expansion was left undone, or one whose folder does not exist, is an error:
that is a typo, not an optional file, and a typo must never read as a clean scan. A file with terms is reported as
`<n>:<path>`, where n is the index of the path argument it came from (--path first, then --if-present) and the path
is relative to that argument (a named file: its own name), with every term and marker in it replaced by `<term>`;
when two such paths mask alike, the later ones get `#2`, `#3` and so on.

A canary checks a cooperating engine, and nothing more. Each run invents a fresh name (a capitalised nonsense
word), tells the engine it is in its context, and asks for every personal, family, account, organisation, company,
property, street, address or place name in its whole context, as exactly one line: `NAMES:` and the names separated
by commas, starting with that one. The reply counts as an answer only when, after surrounding whitespace, it is
that single line: `NAMES:`, then a comma-separated list whose first item is the invented name and whose every item
is name-like (one to six words, none of `. ! ? ; :` inside, no pronoun or negation from a small closed set, not
wrapped in brackets). A second line, a code fence, bold, a bullet or an item that fails the name-like test is unanswered,
which is a fail: an honest reply in another shape fails closed, which costs a rerun and never gives a false pass. Any term in
the reply then fails, and the reply is kept with its terms masked; the invented name is recorded as `marker`, with
the `model` and `effort` that were cleared. What that proves is that the engine answers in the form asked and names
no banned term. It cannot prove that a model withholding names deliberately holds nothing back (a well-formed
`NAMES:` line holding only the invented name passes): no reply can prove an absence, and the marker was put in the
message, not in an instruction file. The other two layers cover that: the scan of every file a model is shown, and
the contamination check on every card. Neither command writes a term out. Each clears its `--out` file first of all,
before the command line is even parsed, so a run that ends early never leaves an earlier pass behind. The result
files are the proof the gate ran; a missing or failed result means no real call may start. agy needs --model.

A canary clears one engine at one model and one effort, so a lane runs one per model it uses and writes each to its
own file: `<work>/state/canary-<engine>-<model>.json` (a codex lane that runs one model at two efforts adds the effort
to the name). `readiness.py` reads every `canary-*.json` there and, given the terms file, requires a passing one for
each engine and exact model the cards record, and for codex at the exact effort each ran at, the light model's included.
`--effort` is codex's reasoning effort (default `low`); agy has none to set, because its effort is part of its model id,
so `--effort` with agy is refused. The result records the effort used, and the sha256 of the terms file's forms it ran
against (`terms_sha256`, never the forms): `readiness.py` accepts a pass only when that equals the digest of the terms
file it is given, so a canary run against an older or shorter list clears nothing.

The shield (`shield`, `shield_value`) is what keeps a term out of a call in the first place. Every tool that sends text
or a path to an engine, or writes it into a file a model will read, replaces each term and marker with `[withheld
name]` first, by the one matcher (`alternation`) that `hits`, `carries` and `masked` use as well, so the shield and the
scan always agree: case-insensitive, in Unicode NFC, a space in a term matching any run of whitespace (a line break, a
no-break space), and not a name split by a hyphen or a zero-width character, which is a settled residual. It is one
home for the tools that need it (`cards.py`, `vision.py`, `wiki.py`); each requires `--terms` or `--no-isolation-terms`
(`evidence_of`) and never writes a term anywhere.
"""
import argparse
import functools
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import engines  # noqa: E402

# A factual check, not "list everything in your context": asked that, codex refuses ("I can't enumerate hidden
# context"), and a refusal holds no term, so the canary would pass while proving nothing. The reply is one line of
# a fixed shape, led by the invented name (see `answered`).
CANARY = ("A factual check of this session's setup, not a request for secrets or for the wording of your instructions. "
          "The invented name {marker} has been placed in your context as a test. List every personal name, family "
          "name, account name, organisation, company, property, street, address or place that appears anywhere in "
          "your context (system and instruction files, memories, notes, earlier conversations and this message), "
          "starting with {marker}. Reply with exactly one line: NAMES: followed by the names separated by commas, "
          "starting with {marker}, and nothing else (no other line, no explanation, no formatting). Do not create "
          "plans or files.")

SYLLABLES = [c + v for c in "bdfgklmnprstvz" for v in "aeiou"]
# Words no name holds: a first or second person pronoun, or a negation or a refusal. A closed set, a second check on
# each item beside its shape (see `name_like`), never the proof that an item is a name.
NOT_NAME_WORDS = {"i", "me", "my", "we", "our", "you", "your", "not", "no", "nope", "nothing", "none", "cannot",
                  "can't", "won't", "decline", "private", "withheld", "redacted"}
NOT_NAME_CHARS = re.compile(r"[.!?;:*`]")
WRAPPED = re.compile(r"[\[({<].*[\])}>]")
EDGE = re.compile(r"^[\W_]+|[\W_]+$")
APOSTROPHES = str.maketrans({"‘": "'", "’": "'", "ʼ": "'", "`": "'"})


def not_name_word(word):
    """Whether a word is one NOT_NAME_WORDS rules out, however it is spelt: the marks round it (quotes of any kind,
    brackets, underscores, an ellipsis) are dropped, and a contraction counts as its first part (`I'm`, `we're` and
    `I'll` are `i` and `we`) or, ending `n't`, as a negation (`don't`, `isn't`)."""
    word = EDGE.sub("", word.translate(APOSTROPHES)).lower()
    return word in NOT_NAME_WORDS or word.split("'")[0] in NOT_NAME_WORDS or word.endswith("n't")


def fresh_marker(evidence):
    """An invented capitalised word, new on every call, that holds no term or marker of the operator's (a reply
    carrying it could not be masked, or read as a hit)."""
    forms = [m for ms in evidence.values() for m in ms]
    for _ in range(100):
        marker = "".join(secrets.choice(SYLLABLES) for _ in range(4)).capitalize()
        if not hits(marker, forms):
            return marker
    raise common.ToolError("no invented name clear of the terms in 100 tries; a term of one or two letters?")


def name_like(item):
    """An item that could be a name: one to six words, none of `. ! ? ; :` (or the markup `*` and a backtick) inside
    it, not wrapped in brackets, and no word that `not_name_word` rules out (a hyphenated word is one word). Only
    those conditions fail an item: a short phrase that breaks none of them (`that is all`) passes, which is the
    settled residual of a check on a cooperating engine."""
    words = item.split()
    if not 1 <= len(words) <= 6 or NOT_NAME_CHARS.search(item) or WRAPPED.fullmatch(item):
        return False
    return not any(not_name_word(w) for w in words)


def answered(reply, marker):
    """Whether the reply has the one shape the canary asks for: after surrounding whitespace, a SINGLE line that is
    `NAMES:` and a comma-separated list, whose first item is the invented `marker` (any case) and every item
    name-like (see `name_like`). A second line, a code fence, bold, a bullet or an item that fails `name_like` is unanswered, so
    an honest reply in another shape fails closed, which costs a rerun and never gives a false pass. What the shape
    shows is that the engine answers in the form asked, never that it would list names from files it withholds: a
    model that writes `NAMES:` and the marker alone passes, and the scan and the contamination check cover that."""
    text = reply.replace("\u2019", "'").strip()
    if len(text.splitlines()) != 1 or not text.upper().startswith("NAMES:"):
        return False
    items = [x.strip() for x in text[len("NAMES:"):].split(",")]
    return items[0].lower() == marker.lower() and all(name_like(x) for x in items)


def load_terms(path):
    """{term: [term, marker, ...]} from the operator's terms file. A missing file is an error, not an empty list. A term or
    marker that occurs inside the placeholder `[withheld name]` (a surname such as Held, a marker such as Nam) is accepted:
    the matcher takes the placeholder out before it looks for any form, so none is ever found in it."""
    if not path or not os.path.exists(path):
        raise common.ToolError("isolation terms file missing: %s" % path)
    out = {}
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [x.strip() for x in line.split("|") if x.strip()]
        out[parts[0]] = parts
    if not out:
        raise common.ToolError("isolation terms file is empty: %s" % path)
    return out


SHIELD = "[withheld name]"
PLACEHOLDER = re.compile(r"\[\s*withheld\s+name\s*\]", re.I)  # the placeholder as a model may write it back


def without_placeholder(text):
    """`text` with every occurrence of the placeholder taken out for a mark that is no letter, ignoring case and the spacing
    inside the brackets. The matcher does this itself before it looks for any form (`hits`, `carries`), so the placeholder,
    however a model writes it back, is never read as a term whatever the caller, and no form can be found inside it."""
    return PLACEHOLDER.sub("\x00", text)


def forms(evidence):
    """Every term and marker of the evidence, once each, longest first (equal lengths in alphabetical order, so the order
    never varies between runs): the order `shield` and `masked` match in."""
    return sorted({m for ms in evidence.values() for m in ms}, key=lambda m: (-len(m), m))


def normal(text):
    """`text` in Unicode NFC, the one form every match is made in: a name may be stored decomposed (an older macOS file
    name) and written composed in the terms file, or the other way about."""
    return unicodedata.normalize("NFC", text)


@functools.lru_cache(maxsize=None)
def alternation(fs, protect=False):
    """The one pattern that finds any of the forms `fs` (a tuple, longest first), ignoring case: each form in NFC, each run
    of whitespace inside it standing for any run of Unicode whitespace in the text (a line break, a no-break space, a
    narrow no-break space, two spaces), so a name wrapped at the end of a line or set with a no-break space is the name.
    With `protect`, the placeholder (`PLACEHOLDER`, whatever its case or spacing) comes first, so text already shielded
    is matched as it stands: the shield is idempotent and `masked` leaves the placeholder alone. `hits` and `carries` take
    the placeholder out of the text before they search, so no form (a surname such as Held, a marker such as Nam) is ever
    found inside it.

    This is the one matcher: `hits` (the scan and the contamination check), `carries`, `shield` and `masked` all use it,
    so they always agree. What it does not match is a settled residual: a name split by a hyphen at the end of a line, or
    by a zero-width character or a soft hyphen, and a name in another script or spelling."""
    parts = [r"\s+".join(re.escape(w) for w in normal(f).split()) for f in fs if normal(f).split()]
    if protect:
        parts.insert(0, PLACEHOLDER.pattern)
    return re.compile("|".join(parts), re.I) if parts else None


def hits(text, terms):
    """The `terms` (a list of forms, or an evidence mapping, whose keys are its terms) that `text` carries, by the one
    matcher (`alternation`)."""
    body = without_placeholder(normal(text))
    return [t for t in terms if (rx := alternation((t,))) is not None and rx.search(body)]


def strings(value):
    """Every string in a JSON value, mapping keys left out: a card's values, never its field names. What a term is looked for
    in when a card is read (the contamination check, `wiki.shielded_document`), so a short term or marker such as Nam is not
    found in a field name such as `proposed_name`."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [x for v in value.values() for x in strings(v)]
    if isinstance(value, (list, tuple)):
        return [x for v in value for x in strings(v)]
    return []


def carries(text, evidence):
    """Whether `text` holds a term or a marker of the evidence: whether `shield` would replace anything in it. (`hits`
    reads the terms alone, which is what a card is an alert for naming; a marker is a form of the term, and a document
    that carries one is as much a document that carries the term.)"""
    rx = alternation(tuple(forms(evidence)))
    return rx is not None and rx.search(without_placeholder(normal(text))) is not None


def shield(text, evidence):
    """(`text` with every term and marker of `evidence` replaced by `SHIELD`, the number replaced). Matching is the one
    matcher's (`alternation`): case-insensitive, in Unicode NFC, a space in a form standing for any run of whitespace, longest
    form first, in one pass, so the placeholder is never scanned again and text already shielded is left as it is (the
    shield is idempotent). A text that held a match is returned in NFC. Empty evidence (`--no-isolation-terms`), or a
    text with no match, is returned as it was, with 0. A term is never written anywhere. A short term also matches
    inside longer words, which garbles the word and never leaks the term: prefer full names in the terms file."""
    rx = alternation(tuple(forms(evidence)), protect=True)
    if rx is None:
        return text, 0
    n = 0

    def replace(m):
        nonlocal n
        if not PLACEHOLDER.fullmatch(m.group(0)):
            n += 1
        return SHIELD
    out = rx.sub(replace, normal(text))
    return (out, n) if n else (text, 0)


def shield_value(value, evidence):
    """(`value` with every string in it, and every key of every mapping, shielded as `shield` does, the number replaced).
    A JSON value: strings, lists, mappings; anything else (numbers, booleans, null) is returned as it is. Two keys that
    shield alike are one key, the later value kept: the keys a tool shields are paths and names, never an identifier."""
    n = 0

    def walk(v):
        nonlocal n
        if isinstance(v, str):
            out, k = shield(v, evidence)
            n += k
            return out
        if isinstance(v, (list, tuple)):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {walk(k): walk(x) for k, x in v.items()}
        return v
    return walk(value), n


def shield_digest(evidence):
    """The sha256 of the evidence's forms, sorted and one to a line, never the forms: what a cached or built artefact
    records, so that one made under another terms file, or under none, is not taken for one made under this."""
    return hashlib.sha256("\n".join(sorted({m for ms in evidence.values() for m in ms})).encode("utf-8")).hexdigest()


def add_terms_args(parser):
    parser.add_argument("--terms", help="the operator's isolation terms file")
    parser.add_argument("--no-isolation-terms", action="store_true",
                        help="state explicitly that no other project needs isolating (nothing is shielded)")


def require_choice(a):
    """Refuse a command line that gives neither `--terms` nor `--no-isolation-terms`, or both: a run that shields nothing
    must be the operator's stated decision, never an omission or a contradiction. Checked before anything is read."""
    if a.terms and a.no_isolation_terms:
        raise common.ToolError("give --terms (the isolation list) or --no-isolation-terms, not both")
    if not (a.terms or a.no_isolation_terms):
        raise common.ToolError("give --terms (the isolation list) or --no-isolation-terms")


def evidence_of(a):
    """{term: [term, marker, ...]} for `--terms`, `{}` for `--no-isolation-terms` (see `require_choice`)."""
    require_choice(a)
    return {} if a.no_isolation_terms else load_terms(a.terms)


def term_in_source(term, src, evidence):
    for m in evidence.get(term, [term]):
        if re.fullmatch(r"[A-Za-z0-9 .&-]+", m):
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(m) + r"(?![A-Za-z0-9])", src, re.I):
                return True
        elif m.lower() in src.lower():
            return True
    return False


def contamination(card_text, source_text, evidence):
    """Terms a card names that its own source does not carry: each one is an alert. `card_text` is the card's values
    (`strings`, joined), never its field names. Given the source as it was sent,
    shielded (`shield`), in which no term or marker survives, nothing excuses a term, so every term the card names is
    returned: the model was never shown it. `hits` takes the placeholder out of the card first, whatever its case or
    spacing, so a model that writes it back never alerts, even where a term stands inside it (a surname such as Held)."""
    return [t for t in hits(card_text, evidence) if not term_in_source(t, source_text, evidence)]


def masked(text, evidence):
    """`text` with every term and marker replaced by `<term>`, by the one matcher (`alternation`), the placeholder left as it
    stands; a text with no match is returned as it was."""
    rx = alternation(tuple(forms(evidence)), protect=True)
    if rx is None:
        return text
    n = 0

    def replace(m):
        nonlocal n
        if PLACEHOLDER.fullmatch(m.group(0)):
            return m.group(0)
        n += 1
        return "<term>"
    out = rx.sub(replace, normal(text))
    return out if n else text


UNSET_VARIABLE = re.compile(r"\$(\w+|\{[^}]*\})", re.ASCII)  # what `os.path.expandvars` reads as a variable


def expand(path, option, evidence):
    """`path` with `~` and environment variables expanded. An expansion left undone is a typo and an error, named for
    its `option`: a path that still begins with `~` (a `~user` this machine lacks) or still holds a `$NAME` (a variable
    that is not set). A `~` or `$` inside a name is part of the name and is kept: `com~apple~CloudDocs` is the folder
    every iCloud Drive path runs through."""
    p = os.path.expanduser(os.path.expandvars(path))
    if p.startswith("~") or UNSET_VARIABLE.search(p):
        raise common.ToolError("%s %s still begins with ~ or holds an unexpanded $NAME after expansion: give a path "
                               "this machine can resolve" % (option, masked(p, evidence)))
    return p


def present_paths(given, evidence):
    """(the --if-present paths this machine has, the ones it lacks), each expanded. Only a file missing from a folder
    that exists counts as lacking; a path whose expansion was left undone (a quoted tilde of a user this machine lacks,
    an unset variable), or one whose folder is missing, is a typo and an error, so that a mistake cannot read as a clean
    scan."""
    have, lack = [], []
    for raw in given or []:
        p = expand(raw, "--if-present", evidence)
        if os.path.islink(p) and not os.path.exists(p):
            raise common.ToolError("--if-present %s is a broken link, not an absent file" % masked(p, evidence))
        if os.path.exists(p):
            have.append(p)
        elif not os.path.isdir(os.path.dirname(os.path.abspath(p))):
            raise common.ToolError("--if-present %s: its folder does not exist, which is a typo or an engine this "
                                   "machine does not have, not an optional file" % masked(p, evidence))
        else:
            lack.append(p)
    return have, lack


def walk_files(top, evidence):
    """The model-facing files under `top`, links into folders followed. A real folder is read once however many
    links lead to it, which also ends a loop; a broken link or a folder that cannot be read is an error (a file the
    scan cannot read is a file it did not check)."""
    seen, found = set(), []

    def unreadable(error):
        raise common.ToolError("unreadable folder under the scan: %s" % masked(os.path.relpath(error.filename, top),
                                                                               evidence))

    for d, dirs, fs in os.walk(top, followlinks=True, onerror=unreadable):
        real = os.path.realpath(d)
        if real in seen:
            dirs[:] = []
            continue
        seen.add(real)
        dirs.sort()
        for f in sorted(fs):
            p = os.path.join(d, f)
            if os.path.islink(p) and not os.path.exists(p):
                raise common.ToolError("broken link under the scan: %s" % masked(os.path.relpath(p, top), evidence))
            if re.search(r"\.(md|json|py|txt|sh|swift|csv|jsonl|toml|yaml|yml)$", f):
                found.append(p)
    return found


def scan(a):
    evidence = load_terms(a.terms)
    found, checked = {}, 0
    given = [expand(p, "--path", evidence) for p in a.path]
    present, lacking = present_paths(a.if_present, evidence)
    absent = [masked(p, evidence) for p in lacking]
    for p in absent:
        print("absent, and not an error: %s (this machine has no such file, so nothing was read there)" % p,
              file=sys.stderr)
    for n, p in enumerate(given + present):
        if os.path.isfile(p):
            base, files = os.path.dirname(p), [p]
        elif os.path.isdir(p):
            base, files = p, walk_files(p, evidence)
        else:
            raise common.ToolError("scan path missing (argument %d)" % n)
        for f in files:
            checked += 1
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    h = hits(fh.read(), evidence)
            except OSError:  # a file the scan cannot read is a file it did not check
                raise common.ToolError("unreadable file under the scan: %s" % masked(os.path.relpath(f, base), evidence))
            if h:
                key = "%d:%s" % (n, masked(os.path.relpath(f, base), evidence))
                k = 2
                while key in found:  # two paths that mask alike
                    key = "%d:%s#%d" % (n, masked(os.path.relpath(f, base), evidence), k)
                    k += 1
                found[key] = len(h)
    res = {"checked_at": common.now_local(), "files_checked": checked, "files_with_terms": found, "absent": absent,
           "terms": len(evidence), "pass": checked > 0 and not found}
    if a.out:
        common.Writer().json(a.out, res, indent=1)
    print(json.dumps(res, indent=1))
    return 0 if res["pass"] else 1


CODEX_EFFORT = "low"  # the codex default; agy has none to set: its effort is part of its model id
EFFORT = re.compile(r"[a-z]+")  # codex takes its levels as given (low, medium, high, ...): a word, never a TOML escape


def canary(a):
    evidence = load_terms(a.terms)
    marker = fresh_marker(evidence)
    effort = None if a.engine == "agy" else a.effort or CODEX_EFFORT
    d = engines.fresh_dir("canary_")
    res = {"engine": a.engine, "checked_at": common.now_local(), "terms": len(evidence),
           "terms_sha256": shield_digest(evidence), "marker": marker, "model": a.model or "cli-default",
           "effort": effort}
    try:
        eng = engines.Agy(a.model) if a.engine == "agy" else engines.Codex(a.model, effort=effort)
        reply, usage = eng(CANARY.format(marker=marker), d)
        res.update(reply=masked(reply.strip(), evidence)[:2000], usage=usage, hits=len(hits(reply, evidence)),
                   answered=answered(reply, marker))
        if not res["answered"]:
            res["error"] = ("the reply was not the one line asked for (NAMES: and comma-separated names, the test "
                            "name %s first, every item name-like), so the canary proves nothing" % marker)
    except engines.EngineError as ex:
        res.update(error=masked(str(ex), evidence)[:300])
    finally:
        shutil.rmtree(d, True)
    res["pass"] = "reply" in res and res["answered"] and res["hits"] == 0
    common.Writer().json(a.out, res, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "reply"}, indent=1))
    return 0 if res["pass"] else 1


def outs_named(argv):
    """Every --out the command line names (as `--out F` or `--out=F`), found before argparse can reject anything.
    Flags are never taken by abbreviation (`allow_abbrev=False`), so these are the only spellings."""
    outs = []
    for i, x in enumerate(argv):
        if x.startswith("--out="):
            outs.append(x[len("--out="):])
        elif x == "--out" and i + 1 < len(argv):
            outs.append(argv[i + 1])
    return outs


def main():
    # first of all, before argparse can refuse a flag: a run that ends early must not leave an earlier pass behind
    for stale in outs_named(sys.argv[1:]):
        if os.path.isfile(stale):
            os.remove(stale)
    ap = argparse.ArgumentParser(description="Isolation gate for model-facing context", allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan", allow_abbrev=False)
    p.add_argument("--terms", required=True)
    p.add_argument("--path", action="append", required=True)
    p.add_argument("--if-present", action="append", help="a model-facing file read when this machine has it (an "
                   "engine's global instructions); one missing from a folder that exists is listed as absent, one "
                   "whose folder is missing or whose ~ or $NAME was left unexpanded is an error")
    p.add_argument("--out", help="also write the result here, as the gate's liveness artefact")
    p = sub.add_parser("canary", allow_abbrev=False)
    p.add_argument("--terms", required=True)
    p.add_argument("--engine", choices=["agy", "codex"], required=True)
    p.add_argument("--model")
    p.add_argument("--effort", help="codex reasoning effort (default %s); agy's is part of its model id" % CODEX_EFFORT)
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "canary" and a.engine == "agy" and not a.model:
        raise common.ToolError(engines.AGY_MODEL_REQUIRED)
    if a.cmd == "canary" and a.effort is not None:
        if a.engine == "agy":
            raise common.ToolError("--effort is for codex: agy's effort is part of its model id, so choose it with --model")
        if not EFFORT.fullmatch(a.effort):
            raise common.ToolError("--effort %r is not a codex reasoning effort such as low, medium or high" % a.effort)
    return scan(a) if a.cmd == "scan" else canary(a)


if __name__ == "__main__":
    common.run_main(main)
