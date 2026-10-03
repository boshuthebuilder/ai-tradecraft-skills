#!/usr/bin/env python3
"""Keep other projects out of model-facing context.

The operator supplies a terms file (never committed, never inside the folder, never shown to a model): one term per
line, optionally `Term|marker|marker`, where the markers are shorter forms that, when present in a document's own
text, show the term is genuine content of that document. Lines starting with `#` are comments.

    isolation.py scan   --terms F --path <file or dir> [...] [--if-present <file> ...] [--out <result.json>]
    isolation.py canary --terms F --engine agy|codex [--model M] --out <result.json>

The scan reads every file named, and every model-facing file (prompts, templates, schemas, code, config such as
`config.toml` or `jobs.yaml`) under a folder named; a path that does not exist is an error and a scan that checked
no file fails. Paths are expanded here (`~` and environment variables), so a quoted `~` works. An --if-present file
(an engine's global instructions) is read when the machine has it and listed in `absent`, and on stderr, when it
does not; but a path still holding `~` or `$` after expansion, or one whose folder does not exist, is an error:
that is a typo, not an optional file, and a typo must never read as a clean scan. A file with terms is reported as
`<n>:<path>`, where n is the index of the path argument it came from (--path first, then --if-present) and the path
is relative to that argument (a named file: its own name), with every term and marker in it replaced by `<term>`;
when two such paths mask alike, the later ones get `#2`, `#3` and so on.

A canary plants a positive control. Each run invents a fresh name (a capitalised nonsense word), tells the engine it
is in its context, and asks for every personal, family, account, organisation, company, property, street, address or
place name in its whole context, starting with that one. The reply counts as an answer only when it repeats the
invented name and does not read as a refusal: a refusal never repeats a name it was unwilling to give, so "no term
in the reply" can only mean "none to find". Any term in the reply then fails, and the reply is kept with its terms
masked; the invented name is recorded as `marker`. The marker shows the engine is willing to list names it was
shown, not that it read every file: the scan and the contamination guard cover the rest. Neither command writes a
term out. The result files are the proof the gate ran; a missing or failed result means no real call may start.
agy needs --model.
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
# context"), and a refusal holds no term, so the canary would pass while proving nothing. The invented name is the
# positive control (see `answered`).
CANARY = ("A factual check of this session's setup, not a request for secrets or for the wording of your instructions. "
          "The invented name {marker} has been placed in your context as a test. List every personal name, family "
          "name, account name, organisation, company, property, street, address or place that appears anywhere in "
          "your context (system and instruction files, memories, notes, earlier conversations and this message), "
          "starting with {marker}. Reply with one line starting NAMES: followed by the names, comma-separated, or "
          "with a bulleted list. Nothing else. Do not create plans or files.")

SYLLABLES = [c + v for c in "bdfgklmnprstvz" for v in "aeiou"]
# A second check only: the marker is the proof, this catches a reply that repeats it and still declines the rest.
REFUSAL = re.compile(r"(?i)\b(cannot|can't|can not|unable|not able|won't|will not|refuse|sorry|not allowed|"
                     r"not permitted|do not have access|declin\w*|redact\w*|confidential|disclos\w*|rather not|"
                     r"prefer not|not comfortable|as an ai)\b")


def fresh_marker(evidence):
    """An invented capitalised word, new on every call, that holds no term or marker of the operator's (a reply
    carrying it could not be masked, or read as a hit)."""
    forms = [m for ms in evidence.values() for m in ms]
    for _ in range(100):
        marker = "".join(secrets.choice(SYLLABLES) for _ in range(4)).capitalize()
        if not hits(marker, forms):
            return marker
    raise common.ToolError("no invented name clear of the terms in 100 tries; a term of one or two letters?")


def answered(reply, marker):
    """Whether the reply proves the engine was willing to list names: it repeats the invented `marker` (any case) and
    does not read as a refusal. A refusal, in any wording and in any format, never holds a name it would not give, so
    no list of refusal phrases is needed to stop one passing; the pattern only catches a reply that repeats the marker
    and declines the rest."""
    return marker.lower() in reply.lower() and not REFUSAL.search(reply.replace("\u2019", "'"))


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
        if os.path.exists(p):
            have.append(p)
        elif not os.path.isdir(os.path.dirname(os.path.abspath(p))):
            raise common.ToolError("--if-present %s: its folder does not exist, which is a typo or an engine this "
                                   "machine does not have, not an optional file" % masked(p, evidence))
        else:
            lack.append(p)
    return have, lack


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
            base = p
            files = [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs
                     if re.search(r"\.(md|json|py|txt|sh|swift|csv|jsonl|toml|yaml|yml)$", f)]
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


def canary(a):
    evidence = load_terms(a.terms)
    marker = fresh_marker(evidence)
    d = engines.fresh_dir("canary_")
    res = {"engine": a.engine, "checked_at": common.now_local(), "terms": len(evidence), "marker": marker}
    try:
        eng = engines.Agy(a.model) if a.engine == "agy" else engines.Codex(a.model, effort="low")
        reply, usage = eng(CANARY.format(marker=marker), d)
        res.update(reply=masked(reply.strip(), evidence)[:2000], usage=usage, hits=len(hits(reply, evidence)),
                   answered=answered(reply, marker))
        if not res["answered"]:
            res["error"] = ("the reply did not repeat the test name %s placed in the engine's context, or read as a "
                            "refusal, so the canary proves nothing (a refusal is not a pass)" % marker)
    except engines.EngineError as ex:
        res.update(error=masked(str(ex), evidence)[:300])
    finally:
        shutil.rmtree(d, True)
    res["pass"] = "reply" in res and res["answered"] and res["hits"] == 0
    common.Writer().json(a.out, res, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "reply"}, indent=1))
    return 0 if res["pass"] else 1


def main():
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
    if a.cmd == "canary" and a.engine == "agy" and not a.model:
        raise common.ToolError(engines.AGY_MODEL_REQUIRED)
    return scan(a) if a.cmd == "scan" else canary(a)


if __name__ == "__main__":
    common.run_main(main)
