#!/usr/bin/env python3
"""Curation plans (folder-curation steps 3 to 6): propose, approve, execute under guards, prove by re-audit.

    plan.py light    --root R --out <plan dir>              propose a light-depth round (strays, name defects, redundant copies)
    plan.py migrate  --root R --project P --paths-file F --out <plan dir>   stage files for another project
    plan.py return   --root R --project P --paths-file F --out <plan dir>   bring staged files back
    plan.py reorg    --root R --mapping <json> --out <plan dir>   propose the re-organisation the owner approved
    plan.py approve  --plan <csv> --rows 1-5,7 --note "..." [--decline | --defer]   record the owner's decision
    plan.py rmdirs   --root R --plan <csv>                  add rows removing folders the approved moves empty
    plan.py check    --root R --plan <csv>                  dry-run every row, including delete rows
    plan.py execute  --root R --plan <csv> [--apply] [--phase deletes] [--bin DIR]
    plan.py prove    --plan <csv> --before <manifest> --after <manifest>   diff of (path, hash) must equal the rows

The executor reads the approved plan; for delete rows it also re-verifies against the freshly re-audited manifest
and the bytes on disk. Guards per row: both paths inside the folder, no symlinks on the path, source hash equals the
row's evidence before the move and the destination's after it, never overwrite, an `rmdir` only when the folder
holds nothing but `.DS_Store`, deletes only of copies the manifest marks `redundant`, never inside a pack, and only
after every other approved row is done and the manifest was regenerated after them, deleted items moved to the Bin
(never unlinked).
Every subcommand that takes `--root` also takes `--work`, as the other tools do: its start purges what withheld
documents left behind (`common.purge_withheld`) in the work folder it resolved, `--work` else the default for the
folder, and in no other. It keeps no state there of its own.
A path the rulebook excludes is proposed nothing, and a row whose `from` or `to` is one is refused by `check` and
`execute` before any hashing: the plan tools never open an excluded file. A `delete` row is refused, before either file
is hashed, when its copy, the canonical copy it would open to prove the bytes equal, or the document the manifest holds
the copy of is withheld (excluded, or staged for another project), even in a manifest audited before the exclusion.
`reorg` turns a mapping the owner approved, `{"scope": [folder, ...], "keep": [folder, ...], "moves": [{"from": <file or
folder>, "to": <folder>}, ...]}`, into `create`, per-file `move` and `rmdir` rows (`reorg`, below); the executor,
`check` and `prove` need nothing new for them.
Two-phase undo log: an `intent` line before each change and a `done` line with its reverse after. A failed row stops
its domain. A `convert` row is the owner's or the deployment's: the executor names it, leaves it pending and goes on.
"""
import collections
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
IWORK = set(common.PACKAGE_EXTS)
PACK_REFUSAL = "inside a pack: copies in a pack are never deleted"


def read_plan(path):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
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
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
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
    rb = common.load_rulebook(root, common.settings_dir_for(root, a.settings_dir))
    in_pack = common.pack_matcher(root, rb)
    if phase == "deletes":
        others = [r for r in rows if r["approved"] == "approved" and r["action"] not in ("delete", "convert")]
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
        if r["action"] == "convert":
            print("convert", r["from"], "-> not executed by these tools (the owner's or the deployment's)")
            continue
        if r["domain"] in failed_domains:
            r["status"], r["note"] = "skipped", "earlier row in this domain failed"
            continue
        try:
            act = r["action"]
            refuse_excluded(rb, r)
            if act == "create":
                dst = guard.inside(r["to"])
                if os.path.exists(dst) and not os.path.isdir(dst):
                    raise ValueError("exists and is not a folder")
                print("create", r["to"])
                if apply_:
                    os.makedirs(dst, exist_ok=True)
            elif act in ("move", "rename") and not r["from"].endswith("/"):
                if not r["to"]:
                    raise ValueError(NO_DESTINATION)
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
                if in_pack(os.path.dirname(r["from"])):
                    raise ValueError(PACK_REFUSAL)
                e = man.get(r["evidence"])
                if not e:
                    raise ValueError("evidence entry not in manifest")
                kinds = {c["path"]: c["kind"] for c in e.get("copies", [])}
                if kinds.get(r["from"]) != "redundant":
                    raise ValueError("manifest does not mark this path redundant")
                canon = [p for p, k in kinds.items() if k == "canonical"]
                if not canon or canon[0] == r["from"]:
                    raise ValueError("no separate canonical copy")
                refuse_withheld_delete(rb, e, r, canon[0])
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


EXCLUDED = ("%s is excluded from reading by the rulebook: no tool opens, hashes or moves it; the owner moves it by "
            "hand")


def refuse_excluded(rb, r):
    """Refuse a row whose `from` or `to` is a path the rulebook excludes (or under one), before any hashing: a check
    or a move would open the file to prove its hash, which the owner's exclusion forbids."""
    for key in ("from", "to"):
        if r[key] and common.is_excluded(rb, r[key].rstrip("/")):
            raise ValueError(EXCLUDED % ("the %s path" % key))


def refuse_withheld_delete(rb, e, r, keep):
    """Refuse a delete row before it hashes anything when the document it removes a copy of is withheld (its current path
    staged for another project or excluded: a copy of it at an included path is as withheld as it), or the copy, or
    the canonical copy `keep` it would open to prove the bytes equal, is. The plan tools never open a withheld path."""
    for what, path in (("the document the manifest holds this copy of", e["current_path"]), ("the copy", r["from"]),
                       ("the canonical copy", keep)):
        why = common.withheld(rb, path)
        if why:
            raise ValueError("%s is %s: no tool opens, hashes or moves it; the owner decides it by hand"
                             % (what, common.WITHHELD_WHY[why]))


NO_DESTINATION = "no destination: the owner must choose one before approving"


def no_destination(r):
    """Refuse a move or rename row with no `to` (a root stray the owner has not placed), as the executor does when it
    reaches the row. A row the owner declined or deferred is never run, so it is not refused."""
    if not r["to"] and r["approved"] not in ("declined", "deferred"):
        raise ValueError(NO_DESTINATION)


def check(a):
    """Dry run of every row with the executor's own guards; delete rows validated against the manifest."""
    root = os.path.realpath(a.root)
    guard = Guard(root)
    man = load_manifest(a.manifest or os.path.join(root, "_Audit", "manifest.json"))
    rb = common.load_rulebook(root, common.settings_dir_for(root, a.settings_dir))
    in_pack = common.pack_matcher(root, rb)
    ok = bad = 0
    for r in read_plan(a.plan):
        try:
            refuse_excluded(rb, r)
            if r["action"] == "delete":
                if in_pack(os.path.dirname(r["from"])):
                    raise ValueError(PACK_REFUSAL)
                e = man[r["evidence"]]
                kinds = {c["path"]: c["kind"] for c in e.get("copies", [])}
                if r["kind"] != "redundant" or kinds.get(r["from"]) != "redundant":
                    raise ValueError("not redundant")
                canon = [p for p, k in kinds.items() if k == "canonical"][0]
                refuse_withheld_delete(rb, e, r, canon)
                src, keep = guard.inside(r["from"]), guard.inside(canon)
                if not (is_item(src) and is_item(keep)):
                    raise ValueError("missing on disk")
                if common.content_id(src) != r["evidence"] or common.content_id(keep) != r["evidence"]:
                    raise ValueError("hash differs")
            elif r["action"] in ("move", "rename") and not r["from"].endswith("/"):
                no_destination(r)
                src = guard.inside(r["from"])
                guard.inside(r["to"])
                if not is_item(src) or common.content_id(src) != r["evidence"]:
                    raise ValueError("source missing or hash differs")
            elif r["action"] in ("rmdir", "rename", "create"):
                if r["action"] == "rename":
                    no_destination(r)
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


def refuse_decided(out):
    """Refuse to replace the plan in the plan folder `out` when the owner has begun to decide it: any row approved,
    declined or deferred. An untouched proposal may be replaced, so a round proposed again is not an error."""
    path = os.path.join(os.path.abspath(out), "move-plan.csv")
    if not os.path.lexists(path):
        return
    try:
        decided = sum(1 for r in read_plan(path) if r["approved"])
    except (OSError, UnicodeDecodeError, csv.Error) as ex:
        raise common.ToolError("%s already exists and cannot be read as a plan (%s); choose a new plan folder"
                               % (path, ex))
    if decided:
        raise common.ToolError("%s already holds %d approved, declined or deferred row(s); proposing again would "
                               "overwrite the owner's decisions: choose a new plan folder" % (path, decided))


def light(a):
    """A light-depth proposal: root strays (destination left for the owner), name defects, redundant copies."""
    import re
    refuse_decided(a.out)
    root = os.path.realpath(a.root)
    entries = load_manifest(a.manifest or os.path.join(root, "_Audit", "manifest.json"))
    rb = common.load_rulebook(root, common.settings_dir_for(root, a.settings_dir))
    # an item the tools may not read (staged for another project, or excluded) is proposed nothing, and a path it holds
    # is no stray, no name defect and no redundant copy: the owner's exclusion also means the plan leaves it alone
    live = {h: e for h, e in entries.items()
            if "departed" not in e.get("flags", []) and not common.withheld(rb, e["current_path"])}
    in_pack = common.pack_matcher(root, rb)
    redundant, allpaths = {}, {}
    for h, e in live.items():
        for c in e.get("copies", []):
            if c["kind"] == "redundant" and not common.withheld(rb, c["path"]):
                redundant[c["path"]] = h
        for p in [c["path"] for c in e.get("copies", [])] or [e["current_path"]]:
            if not common.withheld(rb, p):
                allpaths[p] = h
    rows = []
    if not a.deletes_only:
        for p in sorted(x for x in allpaths if "/" not in x):
            rows.append(new_row(domain="(root)", action="move", **{"from": p}, to="", evidence=allpaths[p],
                                reason="root stray", needs_a_look="choose the folder it belongs in"))
        folder_fix = {}
        for p, h in sorted(allpaths.items()):
            if common.in_migrations(rb, p) or p in redundant:
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
        # renaming a folder moves everything in it: not one that holds a withheld path (an excluded file, or one staged)
        held_under = list(common.withheld_paths(rb, entries)) + [common.fold(x).rstrip("/") for x in rb["exclude"]]
        for old, new in sorted(folder_fix.items()):
            if any(w.startswith(common.fold(old) + "/") for w in held_under):
                continue
            n = sum(1 for p in allpaths if p.startswith(old + "/"))
            rows.append(new_row(domain=domain_of(old), action="rename", **{"from": old + "/"}, to=new + "/",
                                reason="name defect: folder name ends with a space (%d files inside)" % n, sweep="no"))
    for p, h in sorted(redundant.items()):
        if in_pack(os.path.dirname(p)):
            continue
        canon = next(c["path"] for c in live[h]["copies"] if c["kind"] == "canonical")
        rows.append(new_row(domain=domain_of(p), action="delete", **{"from": p}, evidence=h, kind="redundant",
                            reason="accidental copy; identical bytes kept at " + canon))
    out = os.path.join(os.path.abspath(a.out), "move-plan.csv")
    write_plan(common.Writer(root if a.read_only_root else None), out, number(rows))
    print(len(rows), "rows ->", out)
    return 0


def read_paths(path):
    with open(path, encoding="utf-8") as f:
        return [l.rstrip("\n") for l in f if l.strip() and not l.startswith("#")]


def migrate(a):
    """Stage files for another project under <migrations dir>/<Project>/, keeping their original paths. A listed
    path ending in `/` stands for every live file under it. Copies left behind are listed in review.tsv."""
    refuse_decided(a.out)
    root = os.path.realpath(a.root)
    rb = common.load_rulebook(root, common.settings_dir_for(root, a.settings_dir))
    entries = load_manifest(a.manifest or os.path.join(root, "_Audit", "manifest.json"))
    where = {p: v for p, v in live_paths(entries).items() if not common.is_excluded(rb, p)}  # never an excluded path
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
    refuse_decided(a.out)
    root = os.path.realpath(a.root)
    rb = common.load_rulebook(root, common.settings_dir_for(root, a.settings_dir))
    entries = load_manifest(a.manifest or os.path.join(root, "_Audit", "manifest.json"))
    where = {p: v for p, v in live_paths(entries).items() if not common.is_excluded(rb, p)}
    base = "%s/%s/" % (rb["migrations_dir"], a.project)
    rows, review = [], []
    for item in read_paths(a.paths_file):
        src = base + item
        if src not in where:
            review.append(("MISSING", src, "", ""))
            continue
        rows.append(new_row(domain="Migrations", action="move", **{"from": src}, to=item, evidence=where[src][0],
                            reason=a.reason or "stays in this folder"))
    return _write_round(a, root, rows, review)       # `rmdirs` proposes the emptied folder once these are approved


def _write_round(a, root, rows, review):
    writer = common.Writer(root if a.read_only_root else None)
    d = os.path.abspath(a.out)
    write_plan(writer, os.path.join(d, "move-plan.csv"), number(rows))
    writer.text(os.path.join(d, "review.tsv"), "".join("\t".join(r) + "\n" for r in review))
    print(len(rows), "rows ->", d)
    return 0


# ------------------------------------------------------------------------------------ reorg

REORG_REASON_FILE = "re-organisation: the approved mapping files it under %s"
REORG_REASON_FOLDER = "re-organisation: the approved mapping moves everything under %s/ to %s"
SAMPLE_LIMIT = 3  # paths a refusal names for one mapping row that covers many documents


def read_mapping(path):
    """The mapping, `{"scope": [folder, ...], "keep": [folder, ...], "moves": [{"from": path, "to": folder}, ...]}`:
    exactly those keys; `scope` the folders the owner approved (non-empty), `keep` the folders the owner said must stay
    where they are (a list, empty when none), and a non-empty list of moves, each with exactly a `from` and a `to`, all
    text. Anything else is refused by name."""
    try:
        data = common.read_json_object(path)
    except OSError as e:
        raise common.ToolError("cannot read the mapping %s (%s)" % (path, e.strerror or e))
    if set(data) != {"scope", "keep", "moves"}:
        raise common.ToolError("%s: the mapping is {\"scope\": [...], \"keep\": [...], \"moves\": [...]}; it has the "
                               "keys %s" % (path, sorted(data)))
    scope, keep, moves = data["scope"], data["keep"], data["moves"]
    if not (isinstance(scope, list) and scope and all(isinstance(x, str) for x in scope)):
        raise common.ToolError("%s: scope must be a non-empty list of folders, the ones the owner approved" % path)
    if not (isinstance(keep, list) and all(isinstance(x, str) for x in keep)):
        raise common.ToolError("%s: keep must be a list of folders, the ones the owner said must stay where they are "
                               "(empty when none)" % path)
    if not (isinstance(moves, list) and moves):
        raise common.ToolError("%s: moves must be a non-empty list of {\"from\": ..., \"to\": ...}" % path)
    for i, m in enumerate(moves):
        if not (isinstance(m, dict) and set(m) == {"from", "to"} and all(isinstance(m[k], str) for k in m)):
            raise common.ToolError("%s: moves[%d] must be {\"from\": <file or folder>, \"to\": <folder>}, both text"
                                   % (path, i))
    return scope, keep, moves


def mapping_path(value, where):
    """`value`, a folder-relative path of the mapping, in Unicode NFC with one trailing `/` taken off: refused when it
    is empty or absolute, or has an empty part, a `.` or `..` part or a control character."""
    p = common.nfc(value[:-1] if value.endswith("/") else value)
    if not p or p.startswith("/") or any(x in ("", ".", "..") for x in p.split("/")) or any(
            ord(ch) < 0x20 or ord(ch) == 0x7F for ch in p):
        raise ValueError("%s %r is not a path relative to the folder, with no empty, . or .. part" % (where, value))
    return p


def named_folders(root, rb, settings_dir):
    """{fold(folder): where it is named} for every folder the rulebook's `active` and `finished` list and the compiled
    Schema's Routing table routes (each prefix less its closing `/`): a folder that moves whole would leave those
    naming a folder that is gone. Without a compiled Schema (the wiki is built after this step) routing names none."""
    named = {}
    for key in ("active", "finished"):
        for f in rb[key]:
            named.setdefault(common.fold(f.rstrip("/")), "`%s` in .familyai/rulebook.json" % key)
    ws = common.load_wiki_schema(root, settings_dir, required=False)
    for r in ws["routing"] if ws else ():
        named.setdefault(common.fold(r["prefix"].rstrip("/")), "the Routing table of %s" % ws["schema_path"])
    return named


def destination(root, to):
    """(`to` with each part that exists spelled as its folder has it, why `to` cannot be a destination or None). A part
    that differs from its folder's only in Unicode form is the same name and takes the folder's spelling, since the
    audit records the folder's; one that differs in case is refused, since the proof of the move would then see another
    path than the plan's. Refused too: a part that exists as a file, or inside an iWork package (one document), and a
    folder to create whose name has a space at either end."""
    parts, cur = to.split("/"), root
    for i, part in enumerate(parts):
        names = os.listdir(cur) if os.path.isdir(cur) else []
        same = [n for n in names if common.nfc(n) == part]
        like = [n for n in names if common.fold(n) == common.fold(part)]
        if not same and like:
            return to, "the folder %r is spelled %r in %r; spell it as the folder is" % (
                like[0], part, "/".join(parts[:i + 1]))
        if same:
            parts[i] = same[0]
        elif part != part.strip():
            return to, "%r would create a folder named with a space at either end" % "/".join(parts[:i + 1])
        cur = os.path.join(cur, parts[i])
        if os.path.lexists(cur) and not os.path.isdir(cur):
            return to, "%r exists and is not a folder" % "/".join(parts[:i + 1])
        if os.path.isdir(cur) and os.path.splitext(parts[i])[1].lower() in IWORK:
            return to, "%r is inside the package %r, which is one document" % (to, "/".join(parts[:i + 1]))
    return "/".join(parts), None


def reorg(a):
    """Propose the re-organisation the owner approved, `--mapping`, as a plan in `--out`: a `create` row for each
    destination folder that does not exist (shallowest first), a `move` row for each document that moves (evidence its
    manifest id, `kind` its copy kind), then an `rmdir` row for each top-most folder the moves empty, all `proposed`,
    depth `medium`. A `from` that is a document is one row; a `from` that is a folder moves its whole content, each
    live document under it, to the same place under `to` (the folder is then emptied), and a file the owner excluded
    stays where it is. `to` is a folder that exists or is created, never the folder's root. Rows run in the existing
    executor, `check` and `prove`.

    It refuses to run when the rulebook records `depth` `light`: the owner is not open to a re-organisation, and must
    agree a change first. Otherwise it refuses, writing nothing, and names each refusal (a mapping row by its index,
    `moves[2]`): a mapping that is not the shape above; a `from` that is not a live document or a folder holding one, or
    lies outside every `scope` folder or inside a `keep` folder (one the owner said must stay where it is); a document
    the owner excluded or staged for another project (named by its row, never its path); anything inside a pack, on
    either side; a folder that moves whole while the rulebook's `active` or `finished` lists it or the compiled Schema
    routes it (the message says which file to edit first); a destination that is a name the system reserves, is
    excluded or staged, is a file, is inside a package or is spelled other than its folder is; a document whose FINAL
    path (the destination folder and what lies under it) is inside a pack or under an excluded path or the migrations
    folder; a destination file that exists, or two documents to one path; a document whose content already
    lives in the destination folder once the moves are done (a duplicate: the light round drops it); a document that
    is not on disk, is cloud-only or no longer hashes to its manifest id. A folder the moves empty gets no `rmdir` row
    when a pack, the rulebook or the Schema names it, it lies outside every `scope` folder, or a move files a document
    into it or below it, and the output says so. It also names each new top-level folder it would create."""
    refuse_decided(a.out)
    root = os.path.realpath(a.root)
    guard = Guard(root)
    settings_dir = common.settings_dir_for(root, a.settings_dir)
    rb = common.load_rulebook(root, settings_dir)
    if rb["depth"] == "light":
        raise common.ToolError("the rulebook records depth light: the owner is not open to a re-organisation, so "
                               "nothing is proposed. The owner must agree a change first: record depth medium (or "
                               "full) in CLAUDE.md and .familyai/rulebook.json, re-pin rulebook_sha256, then propose "
                               "again")
    entries = load_manifest(a.manifest or os.path.join(root, "_Audit", "manifest.json"))
    scope, keep, moves = read_mapping(a.mapping)
    in_pack = common.pack_matcher(root, rb)
    named = named_folders(root, rb, settings_dir)
    where = live_paths(entries)                                 # every live path, a withheld one too
    live = common.live_document_paths(rb, entries)              # the ones the tools may read
    at = common.withheld_paths(rb, entries)
    folders = {"/".join(p.split("/")[:i]) for p in live for i in range(1, len(p.split("/")))}
    spelling = common.spelling_index(list(where) + sorted(folders))        # the manifest's own spelling
    reserved = {common.fold(x) for x in common.reserved_names(rb)} | {"outbox", "wiki"}
    problems = []

    def refuse(label, why):
        problems.append("%s: %s" % (label, why))

    def under(path, folder):
        f = common.fold(folder)
        return common.fold(path) == f or common.fold(path).startswith(f + "/")

    def listed(path, label, what):
        """`path` as the manifest spells it, or None after a refusal that names `label`."""
        try:
            norm = mapping_path(path, "%s %s" % (label, what))
        except ValueError as ex:
            refuse(label, str(ex))
            return None
        return common.as_spelled(spelling, norm)

    def system_name(path):
        top = common.fold(path.split("/")[0])
        return top in reserved or top.startswith(("_", "."))

    def folders_listed(names, key):
        """The folders of `names` (a mapping list called `key`) as the manifest spells them. A `scope` folder is refused
        when it is withheld or holds no live document. A `keep` folder only has to be a folder on disk: one that is
        withheld or holds no live document is the owner's answer copied as given, and nothing in it can move anyway."""
        out = []
        for i, f in enumerate(names):
            label = "%s[%d]" % (key, i)
            f = listed(f, label, "path")
            if f is None:
                continue
            if key == "keep":
                if os.path.isdir(os.path.join(root, f)) and not os.path.islink(os.path.join(root, f)):
                    out.append((label, f))
                else:
                    refuse(label, "%r is not a folder in the folder" % f)
                continue
            why = common.path_withheld(rb, at, f)
            if why:
                refuse(label, "the folder is %s: no tool opens or moves anything in it" % common.WITHHELD_WHY[why])
            elif f not in folders:
                refuse(label, "%r is not a folder holding live documents" % f)
            else:
                out.append((label, f))
        return out

    scopes, keeps = folders_listed(scope, "scope"), [f for _l, f in folders_listed(keep, "keep")]
    for label, f in scopes:
        inside = next((k for k in keeps if under(f, k)), None)
        if inside:
            refuse(label, "%r lies inside %r, which the owner said must stay where it is" % (f, inside))
    scopes = [f for _label, f in scopes]

    moved = {}                   # source path -> (destination path, mapping row)
    row_of = {}                  # mapping row -> (from, to, "file" or "folder")
    left_in_place = 0
    for i, m in enumerate(moves):
        label = "moves[%d]" % i
        src = listed(m["from"], label, "from")
        try:
            to = mapping_path(m["to"], label + " to")
        except ValueError as ex:
            refuse(label, str(ex))
            continue
        if src is None:
            continue
        why = common.path_withheld(rb, at, src)
        if why:
            refuse(label, "its from path is %s: no tool opens, hashes or moves it; the owner decides it by hand"
                   % common.WITHHELD_WHY[why])
            continue
        if src in live:
            kind, paths = "file", [src]
        elif src in folders:
            kind, paths = "folder", sorted(p for p in live if p.startswith(src + "/"))
            left_in_place += sum(1 for p in where if p.startswith(src + "/") and p not in live)
        else:
            refuse(label, "%r is neither a live document nor a folder holding one" % src)
            continue
        if not any(under(src, s) for s in scopes):
            refuse(label, "%r is outside the folders the owner approved (scope)" % src)
            continue
        kept = [p for p in paths if any(under(p, k) for k in keeps)]
        if kept:
            refuse(label, "%d of its documents lie in a folder the owner said must stay where it is (%s)" % (
                len(kept), next(k for k in keeps if under(kept[0], k))))
            continue
        why = common.withheld(rb, to)
        to, bad = destination(root, to)
        if system_name(to):
            bad = "%r is a name the system reserves, never a place for the owner's documents" % to
        elif why:
            bad = "its to path is %s: no tool opens, hashes or moves into it; the owner decides it by hand" % (
                common.WITHHELD_WHY[why])
        elif in_pack(to):
            bad = "%r is inside a pack: copies in a pack are history, and a document is never filed into one" % to
        elif kind == "folder" and under(to, src):
            bad = "%r is the folder it moves, or inside it" % to
        if bad:
            refuse(label, bad)
            continue
        packed = [p for p in paths if where[p][1] == "pack" or in_pack(os.path.dirname(p))]
        if packed:
            refuse(label, "%d of its documents are inside a pack (%s): copies in a pack are never moved" % (
                len(packed), "; ".join(packed[:SAMPLE_LIMIT])))
            continue
        hit = sorted(n for n in named if kind == "folder" and under(n, src))
        if hit:
            refuse(label, "moving %r whole leaves %s naming a folder that is gone; update it first (%s), then propose "
                   "again" % (src, named[hit[0]], "edit CLAUDE.md, its AGENTS.md copy and .familyai/rulebook.json, "
                                                  "then re-pin rulebook_sha256" if "rulebook.json" in named[hit[0]]
                   else "edit that page, then run settings.py compile"))
            continue
        row_of[i] = (src, to, kind)
        for p in paths:
            dst = to + "/" + (os.path.basename(p) if kind == "file" else p[len(src) + 1:])
            if p in moved:
                refuse(label, "%r is also moved by moves[%d]" % (p, moved[p][1]))
            else:
                moved[p] = (dst, i)

    # where each document will be, not only the folder it is sent to: a folder moved whole carries its own sub-folders,
    # and a pack or an excluded folder can sit below the destination
    # (a name the system reserves is the destination's first part, and every final path starts with it: refused above)
    landing = {}
    for p, (dst, i) in sorted(moved.items()):
        here = landing.setdefault(i, {"pack": [], "withheld": collections.Counter()})
        if common.withheld(rb, dst):
            here["withheld"][common.withheld(rb, dst)] += 1
        elif in_pack(os.path.dirname(dst)):
            here["pack"].append(dst)
    barred = {i for i, h in landing.items() if h["withheld"] or h["pack"]}
    for i, h in sorted(landing.items()):
        label = "moves[%d]" % i
        for why, n in sorted(h["withheld"].items()):
            refuse(label, "%d of its documents would land in a path that is %s: no tool opens, hashes or moves into "
                   "it; the owner decides it by hand" % (n, common.WITHHELD_WHY[why]))
        if h["pack"]:
            refuse(label, "%d of its documents would land inside a pack (%s): copies in a pack are history, and a "
                   "document is never filed into one" % (len(h["pack"]), "; ".join(h["pack"][:SAMPLE_LIMIT])))

    taken = {common.fold(p) for p in spelling.values()}
    owners = {}
    for p, (dst, i) in sorted(moved.items()):
        if i in barred:
            continue                                  # refused above, and its destination is never named
        if dst == p:
            refuse("moves[%d]" % i, "%r is in %r already" % (p, row_of[i][1]))
        elif common.fold(dst) in owners:
            refuse("moves[%d]" % i, "%r and %r both move to %r" % (p, owners[common.fold(dst)], dst))
        elif common.fold(dst) in taken or os.path.lexists(os.path.join(root, dst)):
            refuse("moves[%d]" % i, "the destination %r exists (nothing is overwritten)" % dst)
        owners.setdefault(common.fold(dst), p)
    paths_of = {}
    for p, h in live.items():
        paths_of.setdefault(h, []).append(moved[p][0] if p in moved else p)
    for p, (dst, i) in sorted(moved.items()):
        twins = sorted(q for q in paths_of[live[p]] if q != dst and under(q, row_of[i][1]))
        if twins:
            refuse("moves[%d]" % i, "the content of %r already lives at %r once the moves are done (a duplicate): "
                   "drop the copy with the light round (plan.py light) and leave it out of the mapping"
                   % (p, twins[0]))

    for p in sorted(moved) if not problems else ():       # hashing opens the files: only once nothing else is wrong
        label = "moves[%d]" % moved[p][1]
        try:
            src, _dst = guard.inside(p), guard.inside(moved[p][0])
        except ValueError as ex:
            refuse(label, str(ex))
            continue
        if not is_item(src):
            refuse(label, "%r is not on disk: the manifest is older than the folder; re-audit first" % p)
        elif common.is_dataless(src):
            refuse(label, "%r is a cloud-only file, so it cannot be checked without downloading it; download it "
                   "first" % p)
        elif common.content_id(src) != live[p]:
            refuse(label, "%r no longer hashes to its manifest id: it changed since the audit; re-audit first" % p)
    if problems:
        raise common.ToolError("refused, nothing written: %d problem(s):\n  %s" % (len(problems),
                                                                                    "\n  ".join(problems)))

    made = set()
    for p in moved:
        d = os.path.dirname(moved[p][0])
        while d and not os.path.isdir(os.path.join(root, d)):
            made.add(d)
            d = os.path.dirname(d)
    rows = [new_row(domain=domain_of(d + "/"), depth="medium", action="create", to=d + "/",
                    reason="a home the approved mapping needs") for d in sorted(made, key=lambda x: (x.count("/"), x))]
    for p in sorted(moved):
        src, to, kind = row_of[moved[p][1]]
        rows.append(new_row(domain=domain_of(p), depth="medium", action="move", **{"from": p}, to=moved[p][0],
                            evidence=live[p], kind=where[p][1],
                            reason=REORG_REASON_FILE % to if kind == "file" else REORG_REASON_FOLDER % (src, to)))
    receiving = set()                       # a folder a document is moved into, and every folder above it
    for dst, _i in moved.values():
        d = os.path.dirname(dst)
        while d:
            receiving.add(common.fold(d))
            d = os.path.dirname(d)
    emptied = [d for d in emptied_folders(root, set(moved)) if common.fold(d) not in receiving]
    outside = [d for d in top_most(emptied) if not any(under(d, s) for s in scopes)]
    kept = []
    for d in top_most([d for d in emptied if any(under(d, s) for s in scopes)]):
        if common.fold(d) in named or in_pack(d) or common.withheld(rb, d):
            kept.append(d)
            continue
        rows.append(new_row(domain=domain_of(d + "/"), depth="medium", action="rmdir", **{"from": d + "/"},
                            reason="emptied by the moves in this plan",
                            needs_a_look="empty only if every move out of it is approved; the owner may decline it "
                                         "(keep_empty_folders)"))
    out = os.path.join(os.path.abspath(a.out), "move-plan.csv")
    write_plan(common.Writer(root if a.read_only_root else None), out, number(rows))
    counts = collections.Counter(r["action"] for r in rows)
    print("%d rows -> %s" % (len(rows), out))
    print("create %d, move %d (from %d mapping row(s)), rmdir %d" % (counts["create"], counts["move"], len(moves),
                                                                   counts["rmdir"]))
    new_top = sorted(d for d in made if "/" not in d)
    if new_top:
        print("new top-level folder(s) it would create: %s" % "; ".join(new_top))
    if left_in_place:
        print("left where they are: %d path(s) under a folder that moves, which no tool may read" % left_in_place)
    for what, found in (("a pack, the rulebook or the Schema names", kept), ("lie outside the scope", outside)):
        if found:
            print("no rmdir row for %d emptied folder(s) that %s: %s" % (len(found), what, "; ".join(found)))
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
    decision = "declined" if a.decline else "deferred" if a.defer else "approved"
    for r in rows:
        if int(r["seq"]) in want:
            r["approved"] = decision
            r["approved_at"] = t
            r["status"] = "pending" if decision == "approved" else "skipped"
            r["note"] = a.note
    write_plan(common.Writer(), a.plan, rows)
    print(len(want), "rows", decision)
    return 0


def emptied_folders(root, moving):
    """The folders, relative to `root` and sorted, that hold nothing but `.DS_Store` and the paths in `moving` (the
    sources of the move rows), so that they are empty once those moves are done. `rmdirs` and `reorg` both propose from
    it."""
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

    return sorted(d for d in cands if empties(d))


def top_most(folders):
    """The folders of `folders` that no other of them lies under: one `rmdir` row takes the emptied folders below it
    to the Bin with it."""
    return [d for d in folders if not any(d != e and d.startswith(e + "/") for e in folders)]


def rmdirs(a):
    """Add rows for the top-most folders that hold nothing but the files the approved move rows take away."""
    root = os.path.realpath(a.root)
    rows = read_plan(a.plan)
    moving = {r["from"] for r in rows if r["action"] == "move" and r["approved"] == "approved"}
    top = top_most(emptied_folders(root, moving))
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
    """Re-audit proof: the change in (path, hash) pairs between the two manifests must equal the executed rows. A
    move or rename takes its pair from `from` to `to` (a folder rename carries every path under it), a delete takes
    its pair away; `rmdir` and `create` rows change no (path, hash) pair."""
    def pairs(entries):
        return {(p, h) for p, (h, _k, _o) in live_paths(entries).items()}
    plan_rows = read_plan(a.plan)
    done = [r for r in plan_rows if r["action"] in ("move", "rename") and r["status"] == "done"]
    deleted = [r for r in plan_rows if r["action"] == "delete" and r["status"] == "done"]
    rows = [r for r in done if not r["from"].endswith("/")]
    folders = [(r["from"], r["to"]) for r in done if r["from"].endswith("/")]
    before, after = pairs(load_manifest(a.before)), pairs(load_manifest(a.after))
    exp_gone = {(r["from"], r["evidence"]) for r in rows + deleted}
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
        "rows_checked": len(done) + len(deleted),
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
        p.add_argument("--work", help="state directory outside the folder (default ~/.ai-os-pre-onboarding/<folder>); "
                       "the one whose withheld artefacts are purged at the start")
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
    p = with_root(sub.add_parser("reorg"))
    p.add_argument("--mapping", required=True, help="the approved mapping: {\"scope\": [...], \"moves\": [...]}")
    p.add_argument("--out", required=True)
    p = sub.add_parser("approve")
    p.add_argument("--plan", required=True)
    p.add_argument("--rows", required=True, help="e.g. 1-5,7 or all")
    p.add_argument("--note", default="")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--decline", action="store_true")
    g.add_argument("--defer", action="store_true", help="record the rows as deferred: not this round")
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
        settings_dir = common.settings_dir_for(root, a.settings_dir)
        work = common.work_dir_for(root, a.work)
        common.verify_twins(root, settings_dir)
        common.purge_at_start(root, settings_dir, work, a, True)
    return {"light": light, "migrate": migrate, "return": return_, "reorg": reorg, "approve": approve,
            "rmdirs": rmdirs, "check": check, "execute": execute, "prove": prove}[a.cmd](a)


if __name__ == "__main__":
    common.run_main(main)
