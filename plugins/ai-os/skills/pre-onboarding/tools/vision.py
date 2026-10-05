#!/usr/bin/env python3
"""The vision lane: a model reads the page images local OCR could not read cleanly.

Drains <work>/vision_queue (images written by extract.py). Each batch of up to six images is copied into a fresh,
otherwise empty folder and agy runs there sandboxed in plan mode (it can view files in that folder; writes and
commands are refused). The transcription replaces the page's text in the extract record (tier `vision`, engine
`agy`); the local text is kept as `local_text`. A reply is applied only when it returns every image, in the order
sent, with its text; anything else is a failed attempt, and after three a page is marked `unread` with the local
text kept. Worker k of N owns the ids that hash to k. Exits when extraction has finished and its share is empty.

A queued image whose document's current path in the manifest is under the migrations folder (held for another
project) or is one the rulebook `exclude`s (excluded) is never sent, whatever the document's flags: it stays in the
queue and out of the share that has to be empty, and the lane's log counts the documents of each kind. The manifest is
read again before each batch, so a round that stages a document while the lane runs is seen.

    python3 vision.py --root R --model <vision model id> [--worker 0/2]
"""
import collections
import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import engines  # noqa: E402

BATCH = 6
MAX_TRIES = 3
SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemas", "ocr.json")
PROMPT = """You are transcribing scanned document pages for a private archive.
The current directory contains these image files: {files}.
For each image, transcribe ALL of its text exactly as written, top to bottom, preserving line breaks.
Keep Chinese in Chinese characters and accents as written. Do not translate, summarise or correct.
If an image has no readable text, return an empty string for it.
Reply directly in this message with JSON only: {{"pages": [{{"file": "p1.png", "text": "..."}}, ...]}}
with exactly one entry per image, in the order listed. Do not create plans, files or run commands."""


def main():
    ap = common.base_args("Vision lane for pages local OCR could not read")
    ap.add_argument("--model", required=True, help="agy model id for transcription (effort encoded in the id)")
    ap.add_argument("--worker", default="0/1")
    ap.add_argument("--out", help="extract records (default <root>/_Audit/extract)")
    ap.add_argument("--manifest", help="default <root>/_Audit/manifest.json")
    ap.add_argument("--lanes", default="extract_main0,extract_apps0",
                    help="done markers in <work>/state that mean extraction has finished")
    a = ap.parse_args()
    root, settings_dir, work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    out = os.path.realpath(a.out) if a.out else os.path.join(root, "_Audit", "extract")
    writer = common.Writer(root if a.read_only_root else None)
    queue = os.path.join(work, "vision_queue")
    state = os.path.join(work, "state")
    os.makedirs(state, exist_ok=True)
    wi, wn = [int(x) for x in a.worker.split("/")]
    log = common.logger(work, "vision%d" % wi)
    agy = engines.Agy(a.model, allow_reads=True)  # the one caller that lets the model open files (its images)
    tries_p = os.path.join(state, "vision_tries_%d.json" % wi)
    alert = os.path.join(state, "ALERT")

    def load_json(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    tries = collections.Counter(load_json(tries_p) if os.path.exists(tries_p) else {})

    def extraction_finished():
        return all(os.path.exists(os.path.join(state, n + ".done")) for n in a.lanes.split(","))

    def load(eid):
        p = os.path.join(out, eid + ".json")
        return load_json(p) if os.path.exists(p) else None

    idle = 0
    held_seen = {}
    while True:
        if os.path.exists(alert):
            log("ALERT present, stopping")
            return 3
        os.makedirs(queue, exist_ok=True)
        files = sorted(f for f in os.listdir(queue) if re.match(r"[0-9a-f]{64}_\d{5}\.png$", f)
                       and int(f[:8], 16) % wn == wi)
        held = common.withheld_ids(root, rb, a.manifest)
        ready, recs = [], {}
        for f in files:
            eid = f[:64]
            if eid in held:
                held_seen[eid] = held[eid]
                continue
            recs.setdefault(eid, load(eid))
            if recs[eid] and recs[eid].get("status") == "needs_vision":
                ready.append(f)
            if len(ready) >= BATCH:
                break
        if not ready:
            if extraction_finished():
                idle += 1
                if idle >= 2:
                    break
            time.sleep(60)
            continue
        idle = 0
        d = engines.fresh_dir("vision_")
        names = []
        for i, f in enumerate(ready):
            shutil.copyfile(os.path.join(queue, f), os.path.join(d, "p%d.png" % (i + 1)))
            names.append("p%d.png" % (i + 1))
        got = None
        try:
            resp, _usage = agy(PROMPT.format(files=", ".join(names)), cwd=d,
                               schema=SCHEMA if os.path.exists(SCHEMA) else None)
            obj = common.parse_json(resp)
            pages = obj.get("pages") if isinstance(obj, dict) else obj
            if not isinstance(pages, list):
                raise ValueError("reply has no pages list")
            files = [p.get("file") if isinstance(p, dict) and isinstance(p.get("text"), str) else None for p in pages]
            if files != names:
                raise engines.EngineError("reply files %s are not the images sent, in order (%s)" % (files, names))
            got = {p["file"]: p["text"] for p in pages}
        except engines.QuotaError as ex:
            wait = min(5 * 3600, (ex.reset_seconds or 600) + 90)
            log("quota; sleeping %d min" % (wait // 60))
            shutil.rmtree(d, True)
            time.sleep(wait)
            continue
        except common.ToolError:
            shutil.rmtree(d, True)
            raise  # a credential file or a setup problem stops the lane; it is not a failed try
        except (engines.EngineError, ValueError) as ex:
            log("batch failed: %s" % str(ex)[:200])
            for f in ready:
                tries[f] += 1
            got = None
        shutil.rmtree(d, True)
        for i, f in enumerate(ready):
            eid, n = f[:64], int(f[65:70])
            r = load(eid)
            if not r:
                continue
            if got is None and tries[f] < MAX_TRIES:
                continue
            text = got.get(names[i], "") if got is not None else None
            for p in r["pages"]:
                if p.get("n") == n and p.get("tier") == "pending_vision":
                    if text is not None:
                        p["local_text"] = p.get("text", "")
                        p["text"] = text.strip()
                        p["tier"] = "vision" if text.strip() else "blank"
                        p["engine"] = "agy"
                    else:
                        p["tier"] = "unread"
                        p["note"] = "vision tier failed %d times; local OCR text kept" % tries[f]
                    p.pop("queued", None)
            tiers = collections.Counter(p["tier"] for p in r["pages"])
            r["tiers"] = dict(tiers)
            r["chars"] = sum(len(p.get("text", "")) for p in r["pages"])
            if not tiers.get("pending_vision"):
                r["status"] = "partial" if (tiers.get("unread") or tiers.get("none")) else "ok"
                r["vision_done_at"] = common.now_local()
            writer.json(os.path.join(out, eid + ".json"), r)
            try:
                os.remove(os.path.join(queue, f))
            except OSError:
                pass
        with open(tries_p, "w", encoding="utf-8") as f:
            json.dump(tries, f)
        log("batch %d images %s" % (len(ready), "ok" if got is not None else "FAILED"))
    log("finished; held for another project: %d; excluded: %d"
        % tuple(sum(why == kind for why in held_seen.values()) for kind in ("migrations", "excluded")))
    with open(os.path.join(state, "vision%d.done" % wi), "w", encoding="utf-8") as f:
        f.write(common.now_local())
    return 0


if __name__ == "__main__":
    common.run_main(main)
