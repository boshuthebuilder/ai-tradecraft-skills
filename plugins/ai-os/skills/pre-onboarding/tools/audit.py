#!/usr/bin/env python3
"""Deterministic folder audit (the folder-curation audit): manifest.json, AUDIT.md and summary.json.

No model calls. Walks the folder, hashes every item (an iWork package counts as one item, hashed over its members),
groups copies by content, tags each copy canonical, redundant, working copy or pack, finds overlapping homes,
generic names, unconverted iWork files, hygiene defects, root strays and files staged for another project, and
merges with the previous manifest so history (first seen, renames, departures) is kept.

    python3 audit.py --root <folder> [--out <dir>] [--work <dir>] [--settings-dir <dir>] [--read-only-root]

`--out` defaults to <root>/_Audit; the previous manifest is read from there. Schema family-ai-preprocess-manifest/2.
"""
import collections
import json
import os
import re
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

SCHEMA = "family-ai-preprocess-manifest/2"
GEN = "ai-os-pre-onboarding-audit/1"
BASE_RESERVED = {"AGENTS.md", "CLAUDE.md", "GEMINI.md", ".familyai", "Outbox", "Wiki"}  # names the walk skips at
# the top; not the names a rulebook must reserve (common.reserved_names), which include _Migrations, audited here
IMG = {".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".gif", ".bmp", ".webp"}
DOC = {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".html", ".htm", ".xlsx", ".xls",
       ".csv", ".pptx", ".ppt", ".pot", ".potx", ".pps", ".ppsx"}
IWORK = {".pages", ".numbers", ".key"}
EMAIL = {".eml", ".msg", ".emlx"}
ARCH = {".zip", ".rar", ".7z", ".tgz", ".gz", ".tar"}
EXPORTS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".pptx", ".ppt"}
GEN_PREFIX = re.compile(r"^(img|dsc|dscn|pxl|mvimg|screenshot|screen shot|scanned document|scanned|scan|document|"
                        r"untitled|image|photo|wechatimg|whatsapp image|微信图片|mmexport)(?=$|[\s_\-\d(])", re.I)
GEN_REST = re.compile(r"[\s_\-\d().]*((at|am|pm|copy)[\s_\-\d().]*)*", re.I)
COPY_RX = re.compile(r"( \(\d+\)| copy( \d+)?)$", re.I)
MODIFIERS = re.compile(r"(final|signed|updated|exported|export|copy|v\d+|version\d+|\d{8}|\d{6}|\(\d+\))$")


def is_generic(stem):
    s = stem.strip()
    if re.fullmatch(r"[\d\s_\-().]{3,}", s):
        return True
    m = GEN_PREFIX.match(s)
    return bool(m) and GEN_REST.fullmatch(s[m.end():]) is not None


def norm_stem(stem):
    s = unicodedata.normalize("NFKC", stem).lower()
    return re.sub(r"[\W_]+", "", s)


def near_stem(stem):
    s = norm_stem(stem)
    prev = None
    while prev != s:
        prev = s
        s = MODIFIERS.sub("", s)
    return s


def main():
    ap = common.base_args("Deterministic folder audit")
    ap.add_argument("--out", help="output directory (default <root>/_Audit); the previous manifest is read here")
    ap.add_argument("--cache", help="hash cache file (default <work>/hashcache.json)")
    ap.add_argument("--dataless", choices=["fail", "read"], default="fail",
                    help="iCloud files not on this machine: fail (default, lists them) or read (downloads them)")
    a = ap.parse_args()
    root, settings_dir, work = common.resolve(a)
    rb = common.load_rulebook(root, settings_dir)
    out = os.path.realpath(a.out) if a.out else os.path.join(root, "_Audit")
    writer = common.Writer(root if a.read_only_root else None)
    writer.check(os.path.join(out, "manifest.json"))
    migr = rb["migrations_dir"]
    reserved = BASE_RESERVED | set(rb["reserved"]) | {rb["wiki_dir"]}
    img_cap = int(rb["image_cap_mb"]) * 1024 * 1024
    in_pack = common.pack_matcher(root, rb)
    log = common.logger(work, "audit")
    folder = os.path.basename(root)

    t0 = common.clock()
    run_at = common.iso_utc(t0)
    log("audit start", folder)

    # ---- walk -------------------------------------------------------------------------
    items = []        # (rel, is_package)
    hidden, links, placeholders, dataless = [], [], [], []
    for dirpath, dirs, files in os.walk(root):
        rd = os.path.relpath(dirpath, root)
        rd = "" if rd == "." else rd
        keep = []
        for d in sorted(dirs):
            rel = os.path.join(rd, d) if rd else d
            full = os.path.join(dirpath, d)
            if not rd and (d in reserved or (d.startswith("_") and d != migr)):
                continue
            if d.startswith("."):
                hidden.append(rel)
                continue
            if os.path.islink(full):
                links.append(rel)
                continue
            if os.path.splitext(d)[1].lower() in IWORK:
                items.append((rel, True))
                continue
            keep.append(d)
        dirs[:] = keep
        for f in sorted(files):
            rel = os.path.join(rd, f) if rd else f
            full = os.path.join(dirpath, f)
            if not rd and f in reserved:
                continue
            if f.startswith("."):
                if f.endswith(".icloud"):
                    placeholders.append(rel)
                else:
                    hidden.append(rel)
                continue
            if os.path.islink(full):
                links.append(rel)
                continue
            items.append((rel, False))
    items.sort()
    for rel, pkg in items:
        full = os.path.join(root, rel)
        if pkg:
            dataless += [os.path.relpath(os.path.join(r2, f), root) for r2, _, fs in os.walk(full) for f in fs
                         if common.is_dataless(os.path.join(r2, f))]
        elif common.is_dataless(full):
            dataless.append(rel)
    log("walked", len(items), "items;", len(hidden), "hidden;", len(links), "symlinks;",
        len(placeholders), "placeholders;", len(dataless), "not downloaded")
    if dataless and a.dataless == "fail":
        for p in dataless[:20]:
            log("  not downloaded:", p)
        raise common.ToolError("%d file(s) are iCloud placeholders; download them or rerun with --dataless read"
                               % len(dataless))

    # ---- hash (with cache) ------------------------------------------------------------
    cache_p = a.cache or os.path.join(work, "hashcache.json")
    try:
        with open(cache_p, encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}

    def save_cache():
        with open(cache_p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(newcache, f)
        os.replace(cache_p + ".tmp", cache_p)
    newcache = {}
    meta = {}
    done_bytes = 0
    for i, (rel, pkg) in enumerate(items):
        full = os.path.join(root, rel)
        ext = os.path.splitext(rel)[1].lower()
        if pkg:
            members = []
            size, mt = 0, 0.0
            for r2, ds, fs in os.walk(full):
                ds.sort()
                for f in sorted(fs):
                    fp = os.path.join(r2, f)
                    st = os.stat(fp)
                    size += st.st_size
                    mt = max(mt, st.st_mtime)
                    members.append((os.path.relpath(fp, full), fp, st))
            key = "%s|pkg|%d|%d" % (rel, size, int(mt * 1e6))
            h = cache.get(key) or common.sha256_package(full)
            newcache[key] = h
            meta[rel] = dict(id=h, size=size, mtime=mt, cls="iwork", hashed=True, package=True)
        else:
            st = os.stat(full)
            size, mt = st.st_size, st.st_mtime
            cls = ("iwork" if ext in IWORK else "image" if ext in IMG else "document" if ext in DOC else
                   "email" if ext in EMAIL else "archive" if ext in ARCH else "other")
            if cls == "image" and size > img_cap:
                import hashlib
                h = hashlib.sha256(("%d:%s:%s" % (size, common.iso_utc(mt), rel)).encode()).hexdigest()
                meta[rel] = dict(id=h, size=size, mtime=mt, cls=cls, hashed=False, package=False)
                continue
            key = "%s|%d|%d" % (rel, size, st.st_mtime_ns)
            h = cache.get(key) or common.sha256_file(full)
            newcache[key] = h
            meta[rel] = dict(id=h, size=size, mtime=mt, cls=cls, hashed=True, package=False)
        done_bytes += meta[rel]["size"]
        if i % 250 == 0:
            log("hashed %d/%d  %.1f GB" % (i, len(items), done_bytes / 1e9))
            save_cache()
    save_cache()
    log("hashing done in %.0fs" % (time.time() - t0))

    # ---- group, canonical, copy kinds -------------------------------------------------
    groups = collections.defaultdict(list)
    for rel, m in meta.items():
        groups[m["id"]].append(rel)

    def canon_key(p):
        stem = os.path.splitext(os.path.basename(p))[0]
        return (1 if COPY_RX.search(stem) else 0, p.count("/"), len(p), p)

    dir_ids = collections.defaultdict(set)
    for rel, m in meta.items():
        if m["hashed"]:
            dir_ids[os.path.dirname(rel)].add(m["id"])

    copies_kind = {}
    for h, paths in groups.items():
        if len(paths) < 2 or not meta[paths[0]]["hashed"]:
            continue
        paths.sort(key=canon_key)
        c = paths[0]
        cdir = os.path.dirname(c)
        kinds = [{"path": c, "kind": "canonical"}]
        for p in paths[1:]:
            pdir = os.path.dirname(p)
            if in_pack(pdir):
                k = "pack"
            elif pdir == cdir:
                k = "redundant"
            else:
                sx, sc = dir_ids[pdir], dir_ids[cdir]
                k = "redundant" if len(sx) >= 3 and len(sx & sc) / len(sx) >= 0.8 else "working_copy"
            kinds.append({"path": p, "kind": k})
        copies_kind[h] = kinds

    # ---- overlapping homes (duplicate groups spanning two second-level folders) -------
    def home(p):
        parts = p.split("/")
        return "/".join(parts[:2]) if len(parts) > 2 else parts[0] if len(parts) > 1 else "(root)"

    pair_counts = collections.Counter()
    pair_members = collections.defaultdict(set)
    for h, ks in copies_kind.items():
        homes = sorted({home(k["path"]) for k in ks})
        for x in range(len(homes)):
            for y in range(x + 1, len(homes)):
                pid = homes[x] + " <> " + homes[y]
                pair_counts[pid] += 1
                pair_members[pid].add(h)
    overlaps = {pid: n for pid, n in pair_counts.items() if n >= 3}

    # ---- unconverted iWork: normalised-stem match, nearest wins, claimed once ---------
    canon_of = {h: sorted(ps, key=canon_key)[0] for h, ps in groups.items()}
    exports = [(h, p) for h, p in canon_of.items() if os.path.splitext(p)[1].lower() in EXPORTS]
    by_stem, by_near = collections.defaultdict(list), collections.defaultdict(list)
    for h, p in exports:
        st = os.path.splitext(os.path.basename(p))[0]
        by_stem[norm_stem(st)].append((h, p))
        by_near[near_stem(st)].append((h, p))

    def hops(a_, b_):
        A, B = os.path.dirname(a_).split("/"), os.path.dirname(b_).split("/")
        n = 0
        while n < min(len(A), len(B)) and A[n] == B[n]:
            n += 1
        return (len(A) - n) + (len(B) - n)

    cand = []
    iw = [(h, p) for h, p in canon_of.items() if meta[p]["cls"] == "iwork"]
    for h, p in iw:
        st = os.path.splitext(os.path.basename(p))[0]
        seen = set()
        for strength, pool in ((0, by_stem.get(norm_stem(st), [])), (1, by_near.get(near_stem(st), []))):
            for eh, ep in pool:
                if eh in seen:
                    continue
                seen.add(eh)
                cand.append((strength, hops(p, ep), abs(meta[p]["mtime"] - meta[ep]["mtime"]), p, ep, h, eh))
    cand.sort()
    claimed_iw, claimed_ex, pairing = set(), set(), {}
    for strength, _hp, _dt, p, ep, h, eh in cand:
        if h in claimed_iw or eh in claimed_ex:
            continue
        claimed_iw.add(h)
        claimed_ex.add(eh)
        pairing[h] = {"id": eh, "path": ep, "match": "stem" if strength == 0 else "stem_near"}

    # ---- hygiene ----------------------------------------------------------------------
    hyg = collections.defaultdict(list)
    lower_seen = collections.defaultdict(list)
    for p in meta:
        comps = p.split("/")
        for c in comps:
            if c != c.strip():
                hyg[p].append("whitespace_in_name")
                break
        stem = os.path.splitext(comps[-1])[0]
        if stem != stem.rstrip() and "whitespace_in_name" not in hyg[p]:
            hyg[p].append("space_before_extension")
        if any(len(c.encode()) > 255 for c in comps):
            hyg[p].append("component_over_255_bytes")
        lower_seen[(os.path.dirname(p), comps[-1].lower())].append(p)
    for _k, ps in lower_seen.items():
        if len(ps) > 1:
            for p in ps:
                hyg[p].append("case_only_name_clash")

    # ---- manifest (merged with the previous pass) -------------------------------------
    mpath = os.path.join(out, "manifest.json")
    prev = {}
    if os.path.exists(mpath):
        with open(mpath, encoding="utf-8") as f:
            pm = json.load(f)
        if pm.get("schema") not in (SCHEMA, "family-ai-preprocess-manifest/1"):
            raise common.ToolError("foreign manifest schema: %r" % pm.get("schema"))
        prev = pm.get("entries", {})
    entries = {}
    for h, ps in groups.items():
        c = sorted(ps, key=canon_key)[0]
        m = meta[c]
        old = prev.get(h, {})
        e = dict(old)
        e.update({
            "id": h,
            "original_name": old.get("original_name", os.path.basename(c)),
            "current_path": c,
            "rename_history": old.get("rename_history", []),
            "class": m["cls"],
            "size": m["size"],
            "mtime": common.iso_utc(m["mtime"]),
            "hashed": m["hashed"],
            "first_seen": old.get("first_seen", run_at),
        })
        if old.get("current_path") and old["current_path"] != c:
            e["rename_history"] = e["rename_history"] + [{"path": c, "at": run_at, "run_id": "audit"}]
        e.pop("copies", None)
        e.pop("synthetic_id", None)
        e.pop("package", None)
        e.pop("generic_name", None)
        e.pop("overlap", None)
        e.pop("convert_candidate", None)
        if "hygiene" in old.get("flags", []):
            e.pop("look_reason", None)
        flags = [f for f in old.get("flags", []) if f not in ("root_stray", "unconverted", "hygiene", "departed",
                                                              "migrating")]
        e.pop("migration_target", None)
        e.pop("migration_targets", None)
        mig = [p for p in ps if p.startswith(migr + "/") and p.count("/") >= 2]
        if mig:
            flags.append("migrating")
            e["migration_target"] = mig[0].split("/")[1]
            projects = sorted({p.split("/")[1] for p in mig})
            if len(projects) > 1:  # identical copies staged for two projects: one entry, every target named
                e["migration_targets"] = projects
        e.pop("departed_at", None)
        if not m["hashed"]:
            e["synthetic_id"] = True
        if m["package"]:
            e["package"] = True
        if h in copies_kind:
            e["copies"] = copies_kind[h]
        if is_generic(os.path.splitext(os.path.basename(c))[0]):
            e["generic_name"] = True
        if "/" not in c:
            flags.append("root_stray")
        if m["cls"] == "iwork":
            pr = pairing.get(h)
            if pr:
                e["convert_candidate"] = pr
            if not pr or pr["match"] != "stem":
                flags.append("unconverted")
        if hyg.get(c):
            flags.append("hygiene")
            e["look_reason"] = ", ".join(sorted(set(hyg[c])))
        for pid, mem in pair_members.items():
            if pid in overlaps and h in mem:
                e["overlap"] = pid
                break
        e["flags"] = sorted(set(flags))
        entries[h] = e
    departed = 0
    for h, old in prev.items():
        if h not in entries:
            e = dict(old)
            if "departed" not in e.get("flags", []):
                e["flags"] = sorted(set(e.get("flags", []) + ["departed"]))
                e["departed_at"] = run_at
            entries[h] = e
            departed += 1

    manifest = {"schema": SCHEMA, "generator_version": GEN, "generated_at": run_at,
                "entries": dict(sorted(entries.items()))}
    writer.text(mpath, json.dumps(manifest, ensure_ascii=False, indent=1))

    # ---- drift vs previous --------------------------------------------------------------
    drift = None
    if prev:
        prev_live = {h: e for h, e in prev.items() if "departed" not in e.get("flags", [])}
        drift = {
            "added": sorted(h for h in entries if h not in prev),
            "departed": sorted(h for h in prev_live if h not in groups),
            "moved": sorted(h for h in groups if h in prev_live
                            and prev_live[h].get("current_path") != entries[h]["current_path"]),
            "edited": sorted({meta[p]["id"] for p, h in
                              {e.get("current_path"): h for h, e in prev_live.items()}.items()
                              if p in meta and meta[p]["id"] != h}),
        }

    # ---- summary + AUDIT.md -------------------------------------------------------------
    live = [e for e in entries.values() if "departed" not in e["flags"]]
    top = collections.defaultdict(lambda: {"files": 0, "unique": set(), "bytes": 0, "newest": 0.0, "recent": 0})
    cutoff = t0 - 365 * 86400
    for p, m in meta.items():
        t = p.split("/")[0] if "/" in p else "(root)"
        d = top[t]
        d["files"] += 1
        d["unique"].add(m["id"])
        d["bytes"] += m["size"]
        d["newest"] = max(d["newest"], m["mtime"])
        d["recent"] += m["mtime"] >= cutoff
    kinds = collections.Counter(k["kind"] for e in live for k in e.get("copies", []))
    gen_by = collections.Counter((e["current_path"].split("/")[0] if "/" in e["current_path"] else "(root)")
                                 for e in live if e.get("generic_name"))
    unconv = [e for e in live if "unconverted" in e["flags"]]
    conv_ok = [e for e in live if e.get("convert_candidate", {}).get("match") == "stem"]
    hyg_list = [(p, k) for p, ks in sorted(hyg.items()) for k in sorted(set(ks))]
    strays = sorted(e["current_path"] for e in live if "root_stray" in e["flags"])
    migrs = sorted((p.split("/")[1], p) for e in live if "migrating" in e["flags"]
                   for p in dict.fromkeys([e["current_path"]] + [k["path"] for k in e.get("copies", [])])
                   if p.startswith(migr + "/") and p.count("/") >= 2)
    count_only = collections.Counter((e["current_path"].split("/")[0]) for e in live if not e["hashed"])
    cls_count = collections.Counter(e["class"] for e in live)
    redundant_paths = sorted(((e["size"], k["path"], e["id"]) for e in live for k in e.get("copies", [])
                              if k["kind"] == "redundant"), reverse=True)

    summary = {
        "generated_at": run_at, "items": len(meta), "unique_contents": len(live),
        "bytes": sum(m["size"] for m in meta.values()),
        "classes": dict(cls_count), "hashed": sum(1 for e in live if e["hashed"]),
        "count_only": sum(count_only.values()),
        "duplicate_groups": sum(1 for e in live if e.get("copies")), "copy_kinds": dict(kinds),
        "redundant_bytes": sum(s for s, _, _ in redundant_paths),
        "overlaps": overlaps, "generic_names": sum(gen_by.values()), "generic_by_folder": dict(gen_by),
        "unconverted": len(unconv), "converted_pairs": len(conv_ok),
        "hygiene": dict(collections.Counter(k for _, k in hyg_list)),
        "root_strays": strays, "migrating": dict(collections.Counter(t for t, _ in migrs)),
        "hidden": len(hidden), "symlinks": len(links), "placeholders": len(placeholders),
        "not_downloaded": len(dataless),
        "departed": departed, "drift": {k: len(v) for k, v in drift.items()} if drift else None,
        "top_level": {t: {"files": d["files"], "unique": len(d["unique"]), "bytes": d["bytes"],
                          "newest": common.iso_utc(d["newest"]) if d["newest"] else None,
                          "changed_last_12m": d["recent"]}
                      for t, d in sorted(top.items())},
        "elapsed_s": 0 if os.environ.get("PRE_ONBOARDING_NOW") else round(time.time() - t0),
    }
    writer.json(os.path.join(out, "summary.json"), summary, indent=1)

    def gb(n):
        return "%.2f GB" % (n / 1e9) if n >= 1e8 else "%.1f MB" % (n / 1e6)

    def cell(s):
        return str(s).replace("|", "\\|").replace("\n", " ")

    L = []
    w = L.append
    w("# Audit: %s" % folder)
    w("")
    w("Generated %s by `%s` from `manifest.json` (schema `%s`). Derived file: regenerate, never edit." % (
        run_at, GEN, SCHEMA))
    w("")
    w("## Summary")
    w("")
    w("| Measure | Count |")
    w("| --- | --- |")
    w("| Items on disk (iWork packages count as one) | %d |" % len(meta))
    w("| Unique contents (manifest entries) | %d |" % len(live))
    w("| Total size | %s |" % gb(summary["bytes"]))
    for c in ("document", "image", "iwork", "archive", "email", "other"):
        w("| Class `%s` | %d |" % (c, cls_count.get(c, 0)))
    w("| Count-only entries (images over %d MB) | %d |" % (int(rb["image_cap_mb"]), summary["count_only"]))
    w("| Departed entries | %d |" % departed)
    w("")
    w("## Top-level folders")
    w("")
    w("| Folder | Items | Unique | Size | Newest change | Changed in last 12 months |")
    w("| --- | --- | --- | --- | --- | --- |")
    for t, d in sorted(top.items()):
        w("| %s | %d | %d | %s | %s | %d |" % (cell(t), d["files"], len(d["unique"]), gb(d["bytes"]),
                                                common.iso_utc(d["newest"])[:10] if d["newest"] else "-",
                                                d["recent"]))
    w("")
    w("## Duplicate groups (%d)" % summary["duplicate_groups"])
    w("")
    w("Copy kinds: canonical %d, redundant %d, working copy %d, pack %d. Redundant copies hold %s." % (
        kinds.get("canonical", 0), kinds.get("redundant", 0), kinds.get("working_copy", 0), kinds.get("pack", 0),
        gb(summary["redundant_bytes"])))
    w("")
    w("Largest redundant copies (up to 40):")
    w("")
    for s, p, h in redundant_paths[:40]:
        w("- `%s` (%s, entry `%s`)" % (p, gb(s), h[:12]))
    if not redundant_paths:
        w("- none")
    w("")
    w("## Overlapping homes (%d)" % len(overlaps))
    w("")
    for pid, n in sorted(overlaps.items(), key=lambda x: -x[1]):
        w("- %s: %d shared contents" % (pid, n))
    if not overlaps:
        w("- none")
    w("")
    w("## Generic names (%d)" % summary["generic_names"])
    w("")
    for t, n in gen_by.most_common():
        w("- %s: %d" % (t, n))
    if not gen_by:
        w("- none")
    w("")
    w("## Unconverted formats (%d)" % len(unconv))
    w("")
    w("%d iWork items already have a confidently matched export. Near matches, where a `convert` row would name "
      "the candidate:" % len(conv_ok))
    w("")
    near = [e for e in unconv if e.get("convert_candidate")]
    for e in near[:60]:
        w("- `%s` near `%s`" % (e["current_path"], e["convert_candidate"]["path"]))
    if not near:
        w("- none")
    w("")
    w("## Hygiene defects (%d)" % len(hyg_list))
    w("")
    for p, k in hyg_list[:80]:
        w("- %s: `%s`" % (k, p))
    if not hyg_list:
        w("- none")
    w("")
    w("## Root strays (%d)" % len(strays))
    w("")
    for p in strays:
        w("- `%s`" % p)
    if not strays:
        w("- none")
    w("")
    w("## Migrating out (%d)" % len(migrs))
    w("")
    w("Files staged under `%s/<Project>/` for another project; they leave this folder once that project takes "
      "them." % migr)
    w("")
    for t, p in migrs:
        w("- %s: `%s`" % (t, p))
    if not migrs:
        w("- none")
    w("")
    w("## Hidden files, symlinks, cloud placeholders")
    w("")
    w("Hidden %d, symlinks %d, cloud-only placeholders %d, not downloaded %d." % (
        len(hidden), len(links), len(placeholders), len(dataless)))
    w("")
    w("## Drift since the last pass")
    w("")
    if drift is None:
        w("Baseline pass: no previous manifest.")
    else:
        w("Added %d, departed %d, moved %d, edited %d." % tuple(len(drift[k]) for k in ("added", "departed",
                                                                                       "moved", "edited")))
    w("")
    writer.text(os.path.join(out, "AUDIT.md"), "\n".join(L))
    log("audit done: %d items, %d entries, %d dup groups, %.0fs" % (len(meta), len(live),
                                                                    summary["duplicate_groups"], time.time() - t0))


if __name__ == "__main__":
    common.run_main(main)
