#!/usr/bin/env python3
"""Curation plans (folder-curation steps 3 to 6): propose, approve, execute under guards, prove by re-audit.

    plan.py light    --root R --out <plan dir>              propose a light-depth round (strays, name defects, redundant copies)
    plan.py migrate  --root R --project P --paths-file F --out <plan dir>   stage files for another project
    plan.py return   --root R --project P --paths-file F --out <plan dir>   bring staged files back
    plan.py approve  --plan <csv> --rows 1-5,7 --note "..." [--decline]    record the owner's decision
    plan.py rmdirs   --root R --plan <csv>                  add rows removing folders the approved moves empty
    plan.py check    --root R --plan <csv>                  dry-run every row, including delete rows
    plan.py execute  --root R --plan <csv> [--apply] [--phase deletes] [--bin DIR]
    plan.py prove    --plan <csv> --before <manifest> --after <manifest>   diff of (path, hash) must equal the rows

The executor reads the approved plan; for delete rows it also re-verifies against the freshly re-audited manifest
and the bytes on disk. Guards per row: both paths inside the folder, no symlinks on the path, source hash equals the
row's evidence before the move and the destination's after it, never overwrite, an `rmdir` only when the folder
holds nothing but `.DS_Store`, deletes only of copies the manifest marks `redundant` and only after every other
approved row is done and the manifest was regenerated after them, deleted items moved to the Bin (never unlinked).
Two-phase undo log: an `intent` line before each change and a `done` line with its reverse after. A failed row stops
its domain.
"""
import csv
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

COLS = ["seq", "domain", "depth", "action", "from", "to", "evidence", "reason", "kind", "sweep", "needs_a_look",
        "approved", "approved_at", "status", "executed_at", "note"]
IWORK = {".pages", ".numbers", ".key"}


def read_plan(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8", newline="")))
    for r in rows:
        for c in COLS:
            r.setdefault(c, "")
    return rows


def write_plan(writer, path, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, quoting=csv.QUOTE_MINIMAL, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in COLS})
    writer.text(path, buf.getvalue())


def load_manifest(path):
    m = json.load(open(path, encoding="utf-8"))
    return m["entries"] if "entries" in m else m


def live_paths(entries):
    """path -> (entry id, copy kind, other paths) for every live path in the manifest."""
    where = {}
    for h, e in entries.items():
        if "departed" in e.get("flags", []):
            continue
        copies = e.get("copies") or [{"path": e["current_path"], "kind": ""}]
        for c in copies:
            where[c["path"]] = (h, c.get("kind", ""), [x["path"] for x in copies if x["path"] != c["path"]])
    return where


def domain_of(p):
    return p.split("/")[0] if "/" in p else "(root)"


class Guard:
    def __init__(self, root):
        self.root = os.path.realpath(root)

    def inside(self, rel):
        p = os.path.realpath(os.path.join(self.root, rel))
        if not (p == self.root or p.startswith(self.root + os.sep)):
            raise ValueError("outside the folder: %s" % rel)
        parts = rel.split("/")
        for i in range(1, len(parts) + 1):
            if os.path.islink(os.path.join(self.root, *parts[:i])):
                raise ValueError("symlink on path: %s" % "/".join(parts[:i]))
        return os.path.join(self.root, rel)


def is_item(p):
    return os.path.isfile(p) or (os.path.isdir(p) and os.path.splitext(p)[1].lower() in IWORK)


def bin_target(bin_dir, base):
    tgt = os.path.join(bin_dir, base)
    n = 1
    while os.path.lexists(tgt):
        stem, ext = os.path.splitext(base)
        tgt = os.path.join(bin_dir, "%s (%d)%s" % (stem, n, ext))
        n += 1
    return tgt


# ------------------------------------------------------------------------------------ execute

def execute(a):
    root = os.path.realpath(a.root)
    guard = Guard(root)
    plan = os.path.abspath(a.plan)
    writer = common.Writer()
    undo = os.path.join(os.path.dirname(plan), "undo.log")
    rows = read_plan(plan)
    apply_ = a.apply
    phase = a.phase
    bin_dir = os.path.abspath(a.bin or os.path.expanduser("~/.Trash"))
    failed_domains = set()
    man = None
    if phase == "deletes":
        others = [r for r in rows if r["approved"] == "approved" and r["action"] != "delete"]
        if any(r["status"] != "done" for r in others):
            raise common.ToolError("refusing deletes: approved non-delete rows are not all done")
        mpath = a.manifest or os.path.join(root, "_Audit", "manifest.json")
        last = max([r["executed_at"] for r in others] or [""])
        mt = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(os.path.getmtime(mpath)))
        if last and mt <= last:
            raise common.ToolError("refusing deletes: re-audit the folder after the moves first")
        man = load_manifest(mpath)

    def log_undo(obj):
        if apply_:
            writer.append(undo, json.dumps(obj, ensure_ascii=False) + "\n")

    for r in sorted(rows, key=lambda r: int(r["seq"])):
        if (r["action"] == "delete") != (phase == "deletes"):
            continue
        if r["approved"] != "approved" or r["status"] == "done":
            if r["approved"] != "approved" and r["status"] in ("", "pending", "proposed"):
                r["status"] = "skipped"
            continue
        if r["domain"] in failed_domains:
            r["status"], r["note"] = "skipped", "earlier row in this domain failed"
            continue
        try:
            act = r["action"]
            if act == "create":
                dst = guard.inside(r["to"])
                if os.path.exists(dst) and not os.path.isdir(dst):
                    raise ValueError("exists and is not a folder")
                print("create", r["to"])
                if apply_:
                    os.makedirs(dst, exist_ok=True)
            elif act in ("move", "rename") and not r["from"].endswith("/"):
                if not r["to"]:
                    raise ValueError("no destination: the owner must choose one before approving")
                src, dst = guard.inside(r["from"]), guard.inside(r["to"])
                if not is_item(src):
                    raise ValueError("source missing")
                if os.path.lexists(dst):
                    raise ValueError("destination exists")
                if common.content_id(src) != r["evidence"]:
                    raise ValueError("source hash differs from evidence")
                print(act, r["from"], "->", r["to"])
                if apply_:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    log_undo({"seq": r["seq"], "phase": "intent", "op": act, "from": r["from"], "to": r["to"],
                              "sha256": r["evidence"], "at": common.now_local()})
                    os.rename(src, dst)
                    if common.content_id(dst) != r["evidence"]:
                        raise ValueError("destination hash differs after %s" % act)
                    log_undo({"seq": r["seq"], "phase": "done", "undo": {"op": act, "from": r["to"], "to": r["from"]},
                              "at": common.now_local()})
            elif act == "rename":
                src, dst = guard.inside(r["from"].rstrip("/")), guard.inside(r["to"].rstrip("/"))
                if not os.path.isdir(src):
                    raise ValueError("source folder missing")
                if os.path.lexists(dst):
                    raise ValueError("destination exists")
                print("rename folder", r["from"], "->", r["to"])
                if apply_:
                    log_undo({"seq": r["seq"], "phase": "intent", "op": "rename-folder", "from": r["from"],
                              "to": r["to"], "at": common.now_local()})
                    os.rename(src, dst)
                    log_undo({"seq": r["seq"], "phase": "done", "undo": {"op": "rename-folder", "from": r["to"],
                              "to": r["from"]}, "at": common.now_local()})
            elif act == "rmdir":
                src = guard.inside(r["from"].rstrip("/"))
                if not os.path.isdir(src) or is_item(src):
                    raise ValueError("not a folder")
                left = [os.path.relpath(os.path.join(d, f), src) for d, _, fs in os.walk(src) for f in fs
                        if f != ".DS_Store"]
                if left:
                    raise ValueError("folder not empty: %s" % left[:3])
                tgt = bin_target(bin_dir, os.path.basename(src))
                print("rmdir", r["from"], "(empty; to the Bin)")
                if apply_:
                    log_undo({"seq": r["seq"], "phase": "intent", "op": "trash-empty-folder", "from": r["from"],
                              "to": tgt, "at": common.now_local()})
                    os.rename(src, tgt)
                    log_undo({"seq": r["seq"], "phase": "done", "undo": {"op": "rename-folder", "from": tgt,
                              "to": r["from"]}, "at": common.now_local()})
            elif act == "delete":
                if r["kind"] != "redundant":
                    raise ValueError("only redundant copies are deleted")
                e = man.get(r["evidence"])
                if not e:
                    raise ValueError("evidence entry not in manifest")
                kinds = {c["path"]: c["kind"] for c in e.get("copies", [])}
                if kinds.get(r["from"]) != "redundant":
                    raise ValueError("manifest does not mark this path redundant")
                canon = [p for p, k in kinds.items() if k == "canonical"]
                if not canon or canon[0] == r["from"]:
                    raise ValueError("no separate canonical copy")
                src, keep = guard.inside(r["from"]), guard.inside(canon[0])
                if not is_item(src) or not is_item(keep):
                    raise ValueError("copy or canonical missing on disk")
                if common.content_id(src) != r["evidence"] or common.content_id(keep) != r["evidence"]:
                    raise ValueError("hash differs on disk (copy or canonical)")
                tgt = bin_target(bin_dir, os.path.basename(src))
                print("delete", r["from"], "(kept:", canon[0] + ")")
                if apply_:
                    log_undo({"seq": r["seq"], "phase": "intent", "op": "trash", "from": r["from"], "to": tgt,
                              "sha256": r["evidence"], "at": common.now_local()})
                    os.rename(src, tgt)
                    log_undo({"seq": r["seq"], "phase": "done", "undo": {"op": "move", "from": tgt, "to": r["from"]},
                              "at": common.now_local()})
            else:
                raise ValueError("action %s not supported by this executor" % act)
            if apply_:
                r["status"], r["executed_at"] = "done", common.now_local()
                r["note"] = ("undo.log seq %s" % r["seq"]) if act != "create" else ""
        except (ValueError, OSError) as ex:
            print("FAILED row", r["seq"], ex)
            failed_domains.add(r["domain"])
            if apply_:
                r["status"], r["executed_at"], r["note"] = "failed", common.now_local(), str(ex)
    if apply_:
        write_plan(writer, plan, rows)
    counts = {}
    for r in rows:
        counts[r["status"] or "pending"] = counts.get(r["status"] or "pending", 0) + 1
    print("rows:", len(rows), "approved:", sum(r["approved"] == "approved" for r in rows), "status:", counts)
    return 1 if failed_domains else 0


def check(a):
    """Dry run of every row with the executor's own guards; delete rows validated against the manifest."""
    root = os.path.realpath(a.root)
    guard = Guard(root)
    man = load_manifest(a.manifest or os.path.join(root, "_Audit", "manifest.json"))
    ok = bad = 0
    for r in read_plan(a.plan):
        try:
            if r["action"] == "delete":
                e = man[r["evidence"]]
                kinds = {c["path"]: c["kind"] for c in e.get("copies", [])}
                if r["kind"] != "redundant" or kinds.get(r["from"]) != "redundant":
                    raise ValueError("not redundant")
                canon = [p for p, k in kinds.items() if k == "canonical"][0]
                src, keep = guard.inside(r["from"]), guard.inside(canon)
                if not (is_item(src) and is_item(keep)):
                    raise ValueError("missing on disk")
                if common.content_id(src) != r["evidence"] or common.content_id(keep) != r["evidence"]:
                    raise ValueError("hash differs")
            elif r["action"] in ("move", "rename") and not r["from"].endswith("/"):
                src = guard.inside(r["from"])
                guard.inside(r["to"])
                if not is_item(src) or common.content_id(src) != r["evidence"]:
                    raise ValueError("source missing or hash differs")
            elif r["action"] in ("rmdir", "rename", "create"):
                guard.inside((r["from"] or r["to"]).rstrip("/"))
            ok += 1
        except (KeyError, IndexError, ValueError, OSError) as ex:
            bad += 1
            print("FAIL", r["seq"], r["action"], r["from"][-80:], ex)
    print("rows ok", ok, "failed", bad)
    return 1 if bad else 0


# ------------------------------------------------------------------------------------ proposals

def new_row(**kw):
    r = {c: "" for c in COLS}
    r.update(kw)
    if not r["depth"]:
        r["depth"] = "light"
    if not r["status"]:
        r["status"] = "proposed"
    return r


def number(rows):
    for i, r in enumerate(rows, 1):
        r["seq"] = i
    return rows


def light(a):
    """A light-depth proposal: root strays (destination left for the owner), name defects, redundant copies."""
    import re
    root = os.path.realpath(a.root)
    entries = load_manifest(a.manifest or os.path.join(root, "_Audit", "manifest.json"))
    live = {h: e for h, e in entries.items() if "departed" not in e.get("flags", [])}
    rb = common.load_rulebook(root, common.settings_dir_for(root, a.settings_dir))
    migr = rb["migrations_dir"]
    redundant, allpaths = {}, {}
    for h, e in live.items():
        for c in e.get("copies", []):
            if c["kind"] == "redundant":
                redundant[c["path"]] = h
        for p in [c["path"] for c in e.get("copies", [])] or [e["current_path"]]:
            allpaths[p] = h
    rows = []
    if not a.deletes_only:
        for p in sorted(x for x in allpaths if "/" not in x):
            rows.append(new_row(domain="(root)", action="move", **{"from": p}, to="", evidence=allpaths[p],
                                reason="root stray", needs_a_look="choose the folder it belongs in"))
        folder_fix = {}
        for p, h in sorted(allpaths.items()):
            if p.startswith(migr + "/") or p in redundant:
                continue
            parts = p.split("/")
            for i, seg in enumerate(parts[:-1]):
                if seg != seg.strip():
                    folder_fix["/".join(parts[:i + 1])] = "/".join(parts[:i] + [seg.strip()])
            name = parts[-1]
            stem, ext = os.path.splitext(name)
            new = (re.sub(r"[\s-]+$", "", stem).lstrip() if stem != stem.rstrip() else stem.lstrip()) + ext
            if new != name:
                tgt = "/".join(parts[:-1] + [new])
                rows.append(new_row(domain=domain_of(p), action="rename", **{"from": p}, to=tgt, evidence=h,
                                    reason="name defect: space before the extension or at the end of the name",
                                    needs_a_look="a file with the new name already exists" if tgt in allpaths else ""))
        for old, new in sorted(folder_fix.items()):
            n = sum(1 for p in allpaths if p.startswith(old + "/"))
            rows.append(new_row(domain=domain_of(old), action="rename", **{"from": old + "/"}, to=new + "/",
                                reason="name defect: folder name ends with a space (%d files inside)" % n, sweep="no"))
    for p, h in sorted(redundant.items()):
        canon = next(c["path"] for c in live[h]["copies"] if c["kind"] == "canonical")
        rows.append(new_row(domain=domain_of(p), action="delete", **{"from": p}, evidence=h, kind="redundant",
                            reason="accidental copy; identical bytes kept at " + canon))
    out = os.path.join(os.path.abspath(a.out), "move-plan.csv")
    write_plan(common.Writer(root if a.read_only_root else None), out, number(rows))
    print(len(rows), "rows ->", out)
    return 0


def read_paths(path):
    return [l.rstrip("\n") for l in open(path, encoding="utf-8") if l.strip() and not l.startswith("#")]


def migrate(a):
    """Stage files for another project under <migrations dir>/<Project>/, keeping their original paths. A listed
    path ending in `/` stands for every live file under it. Copies left behind are listed in review.tsv."""
    root = os.path.realpath(a.root)
    rb = common.load_rulebook(root, common.settings_dir_for(root, a.settings_dir))
    entries = load_manifest(a.manifest or os.path.join(root, "_Audit", "manifest.json"))
    where = live_paths(entries)
    rows, seen, review = [], set(), []
    for item in read_paths(a.paths_file):
        ps = sorted(p for p in where if p.startswith(item)) if item.endswith("/") else [item]
        if not ps or (not item.endswith("/") and item not in where):
            review.append(("MISSING", item, "", ""))
            continue
        for p in ps:
            if p in seen:
                continue
            seen.add(p)
            h, kind, others = where[p]
            rows.append(new_row(domain="Migrations", action="move", **{"from": p},
                                to="%s/%s/%s" % (rb["migrations_dir"], a.project, p), evidence=h, kind=kind,
                                reason=a.reason or "belongs to the %s project" % a.project,
                                needs_a_look=("copies stay at: " + "; ".join(others)) if others else ""))
            review.append((a.project, p, kind, "; ".join(others)))
    return _write_round(a, root, rows, review)


def return_(a):
    root = os.path.realpath(a.root)
    rb = common.load_rulebook(root, common.settings_dir_for(root, a.settings_dir))
    entries = load_manifest(a.manifest or os.path.join(root, "_Audit", "manifest.json"))
    where = live_paths(entries)
    base = "%s/%s/" % (rb["migrations_dir"], a.project)
    rows, review = [], []
    for item in read_paths(a.paths_file):
        src = base + item
        if src not in where:
            review.append(("MISSING", src, "", ""))
            continue
        rows.append(new_row(domain="Migrations", action="move", **{"from": src}, to=item, evidence=where[src][0],
                            reason=a.reason or "stays in this folder"))
    staged = [p for p in where if p.startswith(base)]
    if staged and all(p in {r["from"] for r in rows} for p in staged):
        rows.append(new_row(domain="Migrations", action="rmdir", **{"from": base},
                            reason="emptied: everything else was collected"))
    return _write_round(a, root, rows, review)


def _write_round(a, root, rows, review):
    writer = common.Writer(root if a.read_only_root else None)
    d = os.path.abspath(a.out)
    write_plan(writer, os.path.join(d, "move-plan.csv"), number(rows))
    writer.text(os.path.join(d, "review.tsv"), "".join("\t".join(r) + "\n" for r in review))
    print(len(rows), "rows ->", d)
    return 0


def parse_rows(spec):
    out = set()
    for part in spec.split(","):
        if "-" in part:
            x, y = part.split("-")
            out |= set(range(int(x), int(y) + 1))
        elif part.strip():
            out.add(int(part))
    return out


def approve(a):
    rows = read_plan(a.plan)
    want = parse_rows(a.rows) if a.rows != "all" else {int(r["seq"]) for r in rows}
    t = common.now_local()
    for r in rows:
        if int(r["seq"]) in want:
            r["approved"] = "declined" if a.decline else "approved"
            r["approved_at"] = t
            r["status"] = "skipped" if a.decline else "pending"
            r["note"] = a.note
    write_plan(common.Writer(), a.plan, rows)
    print(len(want), "rows", "declined" if a.decline else "approved")
    return 0


def rmdirs(a):
    """Add rows for the top-most folders that hold nothing but the files the approved move rows take away."""
    root = os.path.realpath(a.root)
    rows = read_plan(a.plan)
    moving = {r["from"] for r in rows if r["action"] == "move" and r["approved"] == "approved"}
    cands = set()
    for p in moving:
        d = os.path.dirname(p)
        while d:
            cands.add(d)
            d = os.path.dirname(d)

    def empties(d):
        for dirpath, ds, fs in os.walk(os.path.join(root, d)):
            rel = os.path.relpath(dirpath, root)
            if os.path.splitext(dirpath)[1].lower() in IWORK:
                if rel not in moving:
                    return False
                ds[:] = []
                continue
            for f in fs:
                if f != ".DS_Store" and os.path.join(rel, f) not in moving:
                    return False
        return True

    empty = sorted(d for d in cands if empties(d))
    top = [d for d in empty if not any(d != e and d.startswith(e + "/") for e in empty)]
    have = {r["from"] for r in rows if r["action"] == "rmdir"}
    t = common.now_local()
    for d in top:
        if d + "/" in have:
            continue
        rows.append(new_row(seq=len(rows) + 1, domain="Migrations" if d.startswith("_") else domain_of(d),
                            action="rmdir", **{"from": d + "/"}, reason="emptied by the moves in this plan",
                            approved="approved" if a.approve_note else "", approved_at=t if a.approve_note else "",
                            status="pending" if a.approve_note else "proposed", note=a.approve_note or ""))
    write_plan(common.Writer(root if a.read_only_root else None), a.plan, rows)
    print("rmdir rows:", top)
    return 0


def prove(a):
    """Re-audit proof: the change in (path, hash) pairs between the two manifests must equal the executed moves."""
    def pairs(entries):
        return {(p, h) for p, (h, _k, _o) in live_paths(entries).items()}
    done = [r for r in read_plan(a.plan) if r["action"] in ("move", "rename") and r["status"] == "done"]
    rows = [r for r in done if not r["from"].endswith("/")]
    folders = [(r["from"], r["to"]) for r in done if r["from"].endswith("/")]
    before, after = pairs(load_manifest(a.before)), pairs(load_manifest(a.after))
    exp_gone = {(r["from"], r["evidence"]) for r in rows}
    exp_new = {(r["to"], r["evidence"]) for r in rows}
    for old, new in folders:              # a folder rename carries every path under it
        for p, h in before:
            if p.startswith(old):
                exp_gone.add((p, h))
                exp_new.add((new + p[len(old):], h))
    gone, new = before - after, after - before
    allowed = tuple(a.allow_departed_under or ())
    res = {
        "gone_unexpected": sorted(map(list, {x for x in gone - exp_gone if not x[0].startswith(allowed or ("\0",))})),
        "new_unexpected": sorted(map(list, new - exp_new)),
        "gone_missing": sorted(map(list, exp_gone - gone)),
        "new_missing": sorted(map(list, exp_new - new)),
        "rows_checked": len(done),
    }
    res["ok"] = not any(res[k] for k in ("gone_unexpected", "new_unexpected", "gone_missing", "new_missing"))
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res["ok"] else 1


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Curation plans: propose, approve, execute, prove")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def with_root(p, writes=True):
        p.add_argument("--root", required=True)
        p.add_argument("--settings-dir")
        p.add_argument("--manifest", help="default <root>/_Audit/manifest.json")
        if writes:
            p.add_argument("--read-only-root", action="store_true")
        return p

    p = with_root(sub.add_parser("light"))
    p.add_argument("--out", required=True)
    p.add_argument("--deletes-only", action="store_true")
    for name in ("migrate", "return"):
        p = with_root(sub.add_parser(name))
        p.add_argument("--project", required=True)
        p.add_argument("--paths-file", required=True)
        p.add_argument("--out", required=True)
        p.add_argument("--reason")
    p = sub.add_parser("approve")
    p.add_argument("--plan", required=True)
    p.add_argument("--rows", required=True, help="e.g. 1-5,7 or all")
    p.add_argument("--note", default="")
    p.add_argument("--decline", action="store_true")
    p = with_root(sub.add_parser("rmdirs"))
    p.add_argument("--plan", required=True)
    p.add_argument("--approve-note", help="approve the added rows with this note (the owner already agreed)")
    p = with_root(sub.add_parser("check"), writes=False)
    p.add_argument("--plan", required=True)
    p = with_root(sub.add_parser("execute"), writes=False)
    p.add_argument("--plan", required=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--phase", choices=["main", "deletes"], default="main")
    p.add_argument("--bin", help="where removed items go (default ~/.Trash)")
    p = sub.add_parser("prove")
    p.add_argument("--plan", required=True)
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--allow-departed-under", action="append",
                   help="a path prefix whose departures are expected (files the other project collected)")
    a = ap.parse_args()
    if getattr(a, "root", None):
        root = os.path.realpath(a.root)
        if not os.path.isdir(root):
            raise common.ToolError("root missing: %s" % root)
        common.verify_twins(root, common.settings_dir_for(root, a.settings_dir))
    return {"light": light, "migrate": migrate, "return": return_, "approve": approve, "rmdirs": rmdirs,
            "check": check, "execute": execute, "prove": prove}[a.cmd](a)


if __name__ == "__main__":
    common.run_main(main)
