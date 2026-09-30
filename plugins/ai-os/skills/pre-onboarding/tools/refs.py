#!/usr/bin/env python3
"""Deterministic repair of truncated reference numbers in cards, from each card's own source text.

When the folder's identifier policy is `stated` (numbers in full), a card that shows only a tail ("...4471",
"ending 2210", "****2210") is repaired when exactly one distinct number in the card's own extracted text ends with
those characters. Ambiguous or unmatched tails are listed for re-carding (`cards.py work --redo`). No model calls:
prefer this to re-running a model.

    python3 refs.py --root R [--apply]
"""
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cards as C  # noqa: E402
import common  # noqa: E402

TRUNC = re.compile(r"…\s?([A-Za-z0-9]{2,4})(?![A-Za-z0-9])")
TRUNC_REF = re.compile(r"(?:…\s?|\.\.\.\s?|\*{2,}\s*|[xX]{3,}\s*|"
                       r"(?i:ending(?: in)?|ends(?: in)?|last 4(?: digits)?:?)\s+)"
                       r"([A-Za-z0-9]{2,4})(?![A-Za-z0-9])")
CAND = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{0,3}\d(?:\d|[ \-/](?=\d)){3,34}|[A-Z0-9]{5,24})(?![A-Za-z0-9])")


def core(s):
    return re.sub(r"[^A-Za-z0-9]", "", s).upper()


def main():
    ap = common.base_args("Repair truncated reference numbers from each card's own source")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--cards", help="default <root>/_Audit/cards")
    ap.add_argument("--extract", help="default <root>/_Audit/extract")
    a = ap.parse_args()
    root, settings_dir, work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    if rb["identifiers"] != "stated":
        raise common.ToolError("the folder's identifier policy is %r; repairing to full numbers would break it"
                               % rb["identifiers"])
    cards_dir = a.cards or os.path.join(root, "_Audit", "cards")
    extract_dir = a.extract or os.path.join(root, "_Audit", "extract")
    writer = common.Writer(root if a.read_only_root else None)
    stats = collections.Counter()
    redo = []
    for f in sorted(glob.glob(os.path.join(cards_dir, "*.json"))):
        c = C.load_json(f)
        eid = c["id"]
        body = json.dumps({k: v for k, v in c.items() if k not in ("id", "card_meta")}, ensure_ascii=False)
        refs_blob = json.dumps((c.get("key_facts") or {}).get("reference_numbers") or [], ensure_ascii=False)
        if not (any(re.search(r"\d", m.group(1)) for m in TRUNC.finditer(body)) or
                any(re.search(r"\d", m.group(1)) for m in TRUNC_REF.finditer(refs_blob))):
            continue
        stats["cards_with_truncation"] += 1
        src = C.full_text(C.load_json(os.path.join(extract_dir, eid + ".json")))
        by_core = {}
        for m in CAND.finditer(src):
            by_core.setdefault(core(m.group(1)), m.group(1).strip())
        unresolved = [0]

        def fix(m):
            tail = m.group(1).upper()
            if not re.search(r"\d", tail):
                return m.group(0)
            found = {k: v for k, v in by_core.items() if k.endswith(tail) and len(k) > len(tail)}
            if len(found) == 1:
                stats["forms_restored"] += 1
                return next(iter(found.values()))
            stats["forms_ambiguous" if found else "forms_not_found"] += 1
            unresolved[0] += 1
            return m.group(0)

        def walk(v, ref=False):
            if isinstance(v, dict):
                return {k: (x if k in ("id", "card_meta") else walk(x, k == "reference_numbers")) for k, x in v.items()}
            if isinstance(v, list):
                return [walk(x, ref) for x in v]
            if isinstance(v, str):
                return (TRUNC_REF if ref else TRUNC).sub(fix, v)
            return v

        new = walk(c)
        if unresolved[0]:
            redo.append(eid)
        elif new != c:
            stats["cards_fully_restored"] += 1
        if a.apply and new != c:
            new.setdefault("card_meta", {})["fixes"] = (new["card_meta"].get("fixes") or []) + [
                "refs_restored_from_source %s" % common.now_local()]
            writer.json(f, new, indent=1)
    stats["cards_to_recard"] = len(redo)
    if a.apply:
        common.Writer().text(os.path.join(work, "state", "redo_refs.txt"), "\n".join(redo) + ("\n" if redo else ""))
    print(json.dumps(dict(stats), indent=1))
    return 0


if __name__ == "__main__":
    common.run_main(main)
