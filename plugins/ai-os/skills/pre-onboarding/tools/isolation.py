#!/usr/bin/env python3
"""Keep other projects out of model-facing context.

The operator supplies a terms file (never committed, never inside the folder, never shown to a model): one term per
line, optionally `Term|marker|marker`, where the markers are shorter forms that, when present in a document's own
text, show the term is genuine content of that document. Lines starting with `#` are comments.

    isolation.py scan   --terms F --path <file or dir> [...] [--out <result.json>]   model-facing files checked
    isolation.py canary --terms F --engine agy|codex [--model M] --out <result.json>

The scan reads every file named, and every model-facing file (prompts, templates, schemas, code, config such as
`config.toml` or `jobs.yaml`) under a folder named; a path that does not exist is an error and a scan that checked
no file fails. A file with terms is reported as `<n>:<path>`, where n is the index of the --path argument it came
from and the path is relative to that argument (a named file: its own name), with every term and marker in it
replaced by `<term>`; when two such paths mask alike, the later ones get `#2`, `#3` and so on. A canary asks the
engine to list every name in its context besides the prompt; any term in the reply fails, and the reply is kept
with its terms masked. Neither writes a term out. The result files are the proof the gate ran; a missing or failed
result means no real call may start. agy needs --model.
"""
import argparse
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import engines  # noqa: E402

# Asked as a factual check with a fixed reply form: asked to "list everything in your context", codex refuses
# ("I can't enumerate hidden context"), and a refusal holds no term, so it would pass while proving nothing.
CANARY = ("A factual check of this session's setup, not a request for secrets or for the wording of your instructions. "
          "Apart from this message, does any text you were given (instructions, memories, notes, earlier "
          "conversations) contain a personal name, family name, account name, company, property, street or address? "
          "Reply with exactly NONE, or with one line starting NAMES: followed by each such name, comma-separated. "
          "Nothing else. Do not create plans or files.")


def answered(reply):
    """Whether the reply takes one of the canary's two forms; anything else (a refusal, an essay) proves nothing."""
    r = reply.strip()
    return r == "NONE" or r[:6].upper() == "NAMES:"


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


def scan(a):
    evidence = load_terms(a.terms)
    found, checked = {}, 0
    for n, p in enumerate(a.path):
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
    res = {"checked_at": common.now_local(), "files_checked": checked, "files_with_terms": found,
           "terms": len(evidence), "pass": checked > 0 and not found}
    if a.out:
        common.Writer().json(a.out, res, indent=1)
    print(json.dumps(res, indent=1))
    return 0 if res["pass"] else 1


def canary(a):
    evidence = load_terms(a.terms)
    d = engines.fresh_dir("canary_")
    res = {"engine": a.engine, "checked_at": common.now_local(), "terms": len(evidence)}
    try:
        eng = engines.Agy(a.model) if a.engine == "agy" else engines.Codex(a.model, effort="low")
        reply, usage = eng(CANARY, d)
        res.update(reply=masked(reply.strip(), evidence)[:2000], usage=usage, hits=len(hits(reply, evidence)),
                   answered=answered(reply))
        if not res["answered"]:
            res["error"] = "the engine did not reply NONE or NAMES: ..., so the canary proves nothing (a refusal is not a pass)"
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
