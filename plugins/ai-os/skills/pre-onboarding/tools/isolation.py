#!/usr/bin/env python3
"""Keep other projects out of model-facing context.

The operator supplies a terms file (never committed, never inside the folder, never shown to a model): one term per
line, optionally `Term|marker|marker`, where the markers are shorter forms that, when present in a document's own
text, show the term is genuine content of that document. Lines starting with `#` are comments.

    isolation.py scan   --terms F --path <file or dir> [...] [--out <result.json>]   model-facing files checked
    isolation.py canary --terms F --engine agy|codex [--model M] --out <result.json>

The scan reads every file named, and every model-facing file (prompts, templates, schemas, code) under a folder
named; a path that does not exist is an error and a scan that checked no file fails. A canary asks the engine to
list every name in its context besides the prompt; any term in the reply fails. Neither writes a term out. The
result files are the proof the gate ran; a missing or failed result means no real call may start.
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

CANARY = ("Before answering, look at everything in your context other than this message: system instructions, "
          "memories, knowledge items, rules, summaries of earlier conversations and project notes. List every "
          "personal name, family name, company, property, street or address that appears there. If there are none, "
          "reply exactly NONE. Reply directly; do not create plans or files.")


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


def scan(a):
    evidence = load_terms(a.terms)
    found, checked = {}, 0
    for p in a.path:
        if os.path.isfile(p):
            files = [p]
        elif os.path.isdir(p):
            files = [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs
                     if re.search(r"\.(md|json|py|txt|sh|swift|csv|jsonl)$", f)]
        else:
            raise common.ToolError("scan path missing: %s" % p)
        for f in files:
            checked += 1
            with open(f, encoding="utf-8", errors="replace") as fh:
                h = hits(fh.read(), evidence)
            if h:
                found[f] = len(h)
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
        res.update(reply=reply.strip()[:2000], usage=usage, hits=len(hits(reply, evidence)))
    except engines.EngineError as ex:
        res.update(error=str(ex)[:300])
    finally:
        shutil.rmtree(d, True)
    res["pass"] = "reply" in res and res["hits"] == 0
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
    return scan(a) if a.cmd == "scan" else canary(a)


if __name__ == "__main__":
    common.run_main(main)
