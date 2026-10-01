#!/usr/bin/env python3
"""Run the deterministic tools on a copy of the fixture and write (or compare) the frozen expected outputs.

    python3 regen_expected.py --check            compare against tests/expected/ (exit 1 on any difference)
    python3 regen_expected.py --update           rewrite tests/expected/ (commit with a reason)

The copy gets fixed modification times and the tools a frozen clock (PRE_ONBOARDING_NOW), so outputs are byte-stable.
The fixture tree's digest is checked before and after, so a run that touched the fixture is caught. Extraction is
compared on the deterministic tiers only (text layers, office files, iWork); pages read by OCR are compared on
their tier, not their text, because OCR engines vary between machines.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
FIXTURE = os.path.join(HERE, "fixture", "Alex Personal")
EXPECTED = os.path.join(HERE, "expected")
NOW = "1719748800"          # 2024-06-30T12:00:00Z
MTIME = 1717200000          # 2024-06-01T00:00:00Z
DETERMINISTIC_TIERS = {"text_layer", "listing"}


def tree_digest(root):
    h = hashlib.sha256()
    for d, ds, fs in os.walk(root):
        ds.sort()
        for f in sorted(fs):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode() + b"\0" + open(p, "rb").read() + b"\n")
    return h.hexdigest()


def copy_fixture(dst):
    shutil.copytree(FIXTURE, dst)
    for d, ds, fs in os.walk(dst):
        for n in ds + fs:
            os.utime(os.path.join(d, n), (MTIME, MTIME), follow_symlinks=False)
    os.utime(dst, (MTIME, MTIME))


def run(tool, *args, env=None, ok=(0, 1)):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, tool)] + list(args), capture_output=True, text=True,
                       env=env)
    if r.returncode not in ok:
        raise SystemExit("%s failed (%d): %s" % (tool, r.returncode, r.stderr[-800:]))
    return r.stdout


def extract_view(extract_dir):
    out = {}
    for f in sorted(os.listdir(extract_dir)):
        r = json.load(open(os.path.join(extract_dir, f), encoding="utf-8"))
        out[r["path"]] = {"status": r["status"], "page_count": r["page_count"],
                          "tiers": [p["tier"] for p in r["pages"]],
                          "text": [p["text"] if p["tier"] in DETERMINISTIC_TIERS else None for p in r["pages"]]}
    return out


def produce(tmp, with_extract):
    root = os.path.join(tmp, "Alex Personal")
    copy_fixture(root)
    env = dict(os.environ, PRE_ONBOARDING_NOW=NOW)
    work, out = os.path.join(tmp, "work"), os.path.join(tmp, "out")
    common = ["--root", root, "--work", work]
    run("audit.py", *common, "--out", os.path.join(out, "_Audit"), "--read-only-root", env=env, ok=(0,))
    manifest = os.path.join(out, "_Audit", "manifest.json")
    run("settings.py", "compile", *common, "--settings-dir", os.path.join(root, ".familyai"), env=env, ok=(0,))
    results = {
        "manifest.json": open(manifest, encoding="utf-8").read(),
        "AUDIT.md": open(os.path.join(out, "_Audit", "AUDIT.md"), encoding="utf-8").read(),
        "summary.json": open(os.path.join(out, "_Audit", "summary.json"), encoding="utf-8").read(),
        "wiki-schema.json": open(os.path.join(root, ".familyai", "wiki-schema.json"), encoding="utf-8").read(),
        "wiki-check.json": run("wiki.py", "check", *common, "--manifest", manifest, env=env),
        "readiness.json": run("readiness.py", *common, "--manifest", manifest, env=env, ok=(0,)),  # green, or fail
        "plan-light.csv": None,
    }
    run("plan.py", "light", "--root", root, "--manifest", manifest, "--out", os.path.join(out, "plan"), env=env,
        ok=(0,))
    results["plan-light.csv"] = open(os.path.join(out, "plan", "move-plan.csv"), encoding="utf-8").read()
    if with_extract:
        run("extract.py", *common, "--manifest", manifest, "--out", os.path.join(out, "extract"), "--lane", "main",
            env=env)
        run("extract.py", *common, "--manifest", manifest, "--out", os.path.join(out, "extract"), "--lane", "apps",
            env=env)
        results["extract.json"] = json.dumps(extract_view(os.path.join(out, "extract")), ensure_ascii=False,
                                             indent=1)
    return results


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--update", action="store_true")
    ap.add_argument("--with-extract", action="store_true", help="also run extraction (needs macOS tools)")
    a = ap.parse_args()
    before = tree_digest(FIXTURE)
    tmp = tempfile.mkdtemp(prefix="fixture_run_")
    try:
        results = produce(tmp, a.with_extract)
    finally:
        shutil.rmtree(tmp, True)
    if tree_digest(FIXTURE) != before:
        raise SystemExit("the fixture changed during the run")
    diffs = []
    os.makedirs(EXPECTED, exist_ok=True)
    for name, text in results.items():
        path = os.path.join(EXPECTED, name)
        if a.update:
            open(path, "w", encoding="utf-8").write(text)
        elif not os.path.exists(path) or open(path, encoding="utf-8").read() != text:
            diffs.append(name)
    print("updated" if a.update else ("differs: %s" % diffs if diffs else "all expected outputs match"))
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
