#!/usr/bin/env python3
"""Keep other projects out of model-facing context.

The operator supplies a terms file (never committed, never inside the folder, never shown to a model): one term per
line, optionally `Term|marker|marker`, where the markers are shorter forms that, when present in a document's own
text, show the term is genuine content of that document. Lines starting with `#` are comments.

    isolation.py scan   --terms F --path <file or dir> [...] [--if-present <file> ...] [--out <result.json>]
    isolation.py canary --terms F --engine agy|codex [--model M] --out <result.json>

The scan reads every file named, and every model-facing file (prompts, templates, schemas, code, config such as
`config.toml` or `jobs.yaml`) under a folder named, following links into folders (skills are often installed as
links) with each real folder read once, so a link loop ends; a broken link is an error, never a skip. A path that
does not exist is an error and a scan that checked no file fails. Paths are expanded here (`~` and environment variables), so a quoted `~` works. An --if-present file
(an engine's global instructions) is read when the machine has it and listed in `absent`, and on stderr, when it
does not; but a path still holding `~` or `$` after expansion, or one whose folder does not exist, is an error:
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
wrapped in brackets). A second line, a code fence, bold, a bullet or a sentence-like item is unanswered, which is a
fail: an honest reply in another shape fails closed, which costs a rerun and never gives a false pass. Any term in
the reply then fails, and the reply is kept with its terms masked; the invented name is recorded as `marker`, with
the `model` and `effort` that were cleared. What that proves is that the engine answers in the form asked and names
no banned term. It cannot prove that a model withholding names deliberately holds nothing back (a well-formed
`NAMES:` line holding only the invented name passes): no reply can prove an absence, and the marker was put in the
message, not in an instruction file. The other two layers cover that: the scan of every file a model is shown, and
the contamination check on every card. Neither command writes a term out. Each clears its `--out` file first of all,
before the command line is even parsed, so a run that ends early never leaves an earlier pass behind. The result
files are the proof the gate ran; a missing or failed result means no real call may start. agy needs --model.
"""
import argparse
import json
import os
import re
import secrets
import shutil
import sys

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
    it, not wrapped in brackets, and no word of NOT_NAME_WORDS (any case; the quotes and brackets round a word are
    ignored, a hyphenated word is one word). A sentence, a comment and a placeholder fail."""
    words = item.split()
    if not 1 <= len(words) <= 6 or NOT_NAME_CHARS.search(item) or WRAPPED.fullmatch(item):
        return False
    return not {w.strip("\"'()[]{}<>").lower() for w in words} & NOT_NAME_WORDS


def answered(reply, marker):
    """Whether the reply has the one shape the canary asks for: after surrounding whitespace, a SINGLE line that is
    `NAMES:` and a comma-separated list, whose first item is the invented `marker` (any case) and every item
    name-like (see `name_like`). A second line, a code fence, bold, a bullet or a sentence-like item is unanswered, so
    an honest reply in another shape fails closed, which costs a rerun and never gives a false pass. What the shape
    shows is that the engine answers in the form asked, never that it would list names from files it withholds: a
    model that writes `NAMES:` and the marker alone passes, and the scan and the contamination check cover that."""
    text = reply.replace("\u2019", "'").strip()
    if len(text.splitlines()) != 1 or not text.upper().startswith("NAMES:"):
        return False
    items = [x.strip() for x in text[len("NAMES:"):].split(",")]
    return items[0].lower() == marker.lower() and all(name_like(x) for x in items)


def load_terms(path):
    """{term: [term, marker, ...]} from the operator's terms file. A missing file is an error, not an empty list."""
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


def hits(text, terms):
    low = text.lower()
    return [t for t in terms if t.lower() in low]


def term_in_source(term, src, evidence):
    for m in evidence.get(term, [term]):
        if re.fullmatch(r"[A-Za-z0-9 .&-]+", m):
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(m) + r"(?![A-Za-z0-9])", src, re.I):
                return True
        elif m.lower() in src.lower():
            return True
    return False


def contamination(card_text, source_text, evidence):
    """Terms a card names that its own source does not carry: each one is an alert."""
    return [t for t in hits(card_text, evidence) if not term_in_source(t, source_text, evidence)]


def masked(text, evidence):
    """`text` with every term and marker replaced by `<term>` (longest first, ignoring case)."""
    forms = sorted({m for ms in evidence.values() for m in ms}, key=len, reverse=True)
    for m in forms:
        text = re.sub(re.escape(m), "<term>", text, flags=re.I)
    return text


def expand(path):
    return os.path.expanduser(os.path.expandvars(path))


def present_paths(given, evidence):
    """(the --if-present paths this machine has, the ones it lacks), each expanded. Only a file missing from a folder
    that exists counts as lacking; a path still holding `~` or `$` (a quoted tilde, an unset variable), or one whose
    folder is missing, is a typo and an error, so that a mistake cannot read as a clean scan."""
    have, lack = [], []
    for raw in given or []:
        p = expand(raw)
        if "~" in p or "$" in p:
            raise common.ToolError("--if-present %s still holds ~ or $ after expansion: give a path this machine can "
                                   "resolve" % masked(p, evidence))
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
    present, lacking = present_paths(a.if_present, evidence)
    absent = [masked(p, evidence) for p in lacking]
    for p in absent:
        print("absent, and not an error: %s (this machine has no such file, so nothing was read there)" % p,
              file=sys.stderr)
    for n, p in enumerate([expand(p) for p in a.path] + present):
        if os.path.isfile(p):
            base, files = os.path.dirname(p), [p]
        elif os.path.isdir(p):
            base, files = p, walk_files(p, evidence)
        else:
            raise common.ToolError("scan path missing (argument %d)" % n)
        for f in files:
            checked += 1
            with open(f, encoding="utf-8", errors="replace") as fh:
                h = hits(fh.read(), evidence)
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


CODEX_EFFORT = "low"  # agy has none to set: its effort is part of its model id


def canary(a):
    evidence = load_terms(a.terms)
    marker = fresh_marker(evidence)
    d = engines.fresh_dir("canary_")
    res = {"engine": a.engine, "checked_at": common.now_local(), "terms": len(evidence), "marker": marker,
           "model": a.model or "cli-default", "effort": None if a.engine == "agy" else CODEX_EFFORT}
    try:
        eng = engines.Agy(a.model) if a.engine == "agy" else engines.Codex(a.model, effort=CODEX_EFFORT)
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


def out_named(argv):
    """The --out the command line names (as `--out F` or `--out=F`), found before argparse can reject anything."""
    for i, x in enumerate(argv):
        if x.startswith("--out="):
            return x[len("--out="):]
        if x == "--out" and i + 1 < len(argv):
            return argv[i + 1]
    return None


def main():
    # first of all, before argparse can refuse a flag: a run that ends early must not leave an earlier pass behind
    stale = out_named(sys.argv[1:])
    if stale and os.path.isfile(stale):
        os.remove(stale)
    ap = argparse.ArgumentParser(description="Isolation gate for model-facing context")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--terms", required=True)
    p.add_argument("--path", action="append", required=True)
    p.add_argument("--if-present", action="append", help="a model-facing file read when this machine has it (an "
                   "engine's global instructions); one missing from a folder that exists is listed as absent, one "
                   "whose folder is missing or that still holds ~ or $ is an error")
    p.add_argument("--out", help="also write the result here, as the gate's liveness artefact")
    p = sub.add_parser("canary")
    p.add_argument("--terms", required=True)
    p.add_argument("--engine", choices=["agy", "codex"], required=True)
    p.add_argument("--model")
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.out and os.path.isfile(a.out):
        os.remove(a.out)  # the same, for a flag argparse took by its abbreviation
    if a.cmd == "canary" and a.engine == "agy" and not a.model:
        raise common.ToolError(engines.AGY_MODEL_REQUIRED)
    return scan(a) if a.cmd == "scan" else canary(a)


if __name__ == "__main__":
    common.run_main(main)
