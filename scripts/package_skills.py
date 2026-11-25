#!/usr/bin/env python3
"""Package each skill as a zip an agent takes by UPLOAD (a chat app with no marketplace install).

    python scripts/package_skills.py            # write dist/<skill>.zip
    python scripts/package_skills.py --check    # build, check the limits, write nothing

The layout and the limits are the ones the Agent Skills upload contract states (issue #186): one zip holds ONE
top-level folder, named for the skill, with exactly one SKILL.md in it; at most 500 files; no file over 25 MB;
the zip at most 50 MB. A skill that breaks a limit fails the run, by name.

A zip holds one skill and nothing beside it. A link from that skill to a SIBLING skill (`../other-skill/…`) has
no target after an upload, so each such link is listed as a note: the skill still loads, and the reader of that
link needs the other skill installed too.

A bundle holds what the commit holds, and nothing else: the file list, each file's bytes and each file's mode
are read from HEAD, never from the disk. So an uncommitted edit, a cache or an editor's backup file is never
packaged, and a checkout's line endings do not reach the zip. The run says so when the working tree differs.
A symbolic link in the commit fails the run, by name: a zip entry cannot stand in for it. The output is the
same bytes for the same commit: entries are sorted and carry one fixed timestamp and one fixed header.

`dist/` is this script's own folder. A run that passes replaces it whole, so it never holds a zip of a skill
that is gone. A run that fails removes it, so `dist/` existing means the last run passed.

Standard library only; needs `git` on PATH and a checkout (not an archive download).
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
MAX_FILES = 500
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_ZIP_BYTES = 50 * 1024 * 1024
FIXED_TIME = (2026, 1, 1, 0, 0, 0)
UNIX = 3
# In the commit, but not part of what an agent loads: a skill's own tests and the repository's housekeeping.
SKIP_DIRS = {"tests"}
SKIP_FILES = {".gitignore", ".gitattributes"}
SKIP_PREFIXES = ("test_",)
SYMLINK_MODE = "120000"
EXECUTABLE_MODE = "100755"
SIBLING_LINK = re.compile(r"\]\((\.\./[^)#\s]+)")


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def committed_skills() -> dict[PurePosixPath, dict[PurePosixPath, tuple[str, str]]]:
    """Every skill in HEAD: its folder, and for each file under it (path relative to the skill) the mode and
    the blob id the commit records."""
    skills: dict[PurePosixPath, dict[PurePosixPath, tuple[str, str]]] = {}
    entries = []
    for record in filter(None, git("ls-tree", "-r", "-z", "HEAD", "--", "plugins").decode().split("\0")):
        meta, name = record.split("\t", 1)
        mode, _kind, blob = meta.split()
        entries.append((PurePosixPath(name), mode, blob))
    roots = sorted(path.parent for path, _, _ in entries if path.match("plugins/*/skills/*/SKILL.md"))
    for root in roots:
        skills[root] = {}
    for path, mode, blob in entries:
        for root in roots:
            if root in path.parents:
                skills[root][path.relative_to(root)] = (mode, blob)
    return skills


def skipped(relative: PurePosixPath) -> bool:
    return (
        any(part in SKIP_DIRS for part in relative.parts[:-1])
        or relative.name in SKIP_FILES
        or relative.name.startswith(SKIP_PREFIXES)
    )


def problems_for(name: str, files: dict[PurePosixPath, tuple[str, bytes]]) -> list[str]:
    problems = []
    for relative, (mode, _) in files.items():
        if mode == SYMLINK_MODE:
            problems.append(f"{name}: {relative} is a symbolic link, which a bundle cannot carry")
    manifests = [str(relative) for relative in files if relative.name.lower() == "skill.md"]
    if manifests != ["SKILL.md"]:
        problems.append(
            f"{name}: a bundle holds exactly one SKILL.md, spelt so, at its top; found {', '.join(manifests) or 'none'}"
        )
    if len(files) > MAX_FILES:
        problems.append(f"{name}: {len(files)} files, over the limit of {MAX_FILES}")
    for relative, (_, content) in files.items():
        if len(content) > MAX_FILE_BYTES:
            problems.append(f"{name}: {relative} is {len(content)} bytes, over {MAX_FILE_BYTES}")
    return problems


def sibling_links(root: PurePosixPath, files: dict[PurePosixPath, tuple[str, bytes]]) -> list[str]:
    """Links that leave the skill's own folder. A `../` link from a file in a subfolder can still land inside
    the skill (`tools/README.md` -> `../SKILL.md`), so each is resolved from the file that holds it."""
    found = set()
    for relative, (_, content) in files.items():
        if relative.suffix != ".md":
            continue
        for link in SIBLING_LINK.findall(content.decode("utf-8", errors="replace")):
            parts: list[str] = []
            for part in (root / relative.parent / link).parts:
                if part == "..":
                    parts and parts.pop()
                elif part != ".":
                    parts.append(part)
            target = PurePosixPath(*parts)
            if target != root and root not in target.parents:
                found.add(str(target))
    return sorted(found)


def write_zip(name: str, files: dict[PurePosixPath, tuple[str, bytes]], destination: Path) -> Path:
    target = destination / f"{name}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for relative in sorted(files):
            mode, content = files[relative]
            info = zipfile.ZipInfo(f"{name}/{relative}", FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = UNIX
            info.external_attr = (0o755 if mode == EXECUTABLE_MODE else 0o644) << 16
            bundle.writestr(info, content)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="check the limits and write nothing")
    args = parser.parse_args(argv)

    skills = committed_skills()
    if not skills:
        print("no plugins/*/skills/*/SKILL.md in HEAD", file=sys.stderr)
        return 1
    problems: list[str] = []
    lines: list[str] = []
    # Beside dist/, so the last step is one rename on one file system.
    scratch = Path(tempfile.mkdtemp(prefix=".dist-", dir=ROOT))
    try:
        for root, listed in skills.items():
            name = root.name
            files = {
                relative: (mode, b"" if mode == SYMLINK_MODE else git("cat-file", "blob", blob))
                for relative, (mode, blob) in listed.items()
                if not skipped(relative)
            }
            found = problems_for(name, files)
            if not found:
                size = write_zip(name, files, scratch).stat().st_size
                if size > MAX_ZIP_BYTES:
                    found = [f"{name}: the zip is {size} bytes, over the limit of {MAX_ZIP_BYTES}"]
            problems += found
            if found:
                continue
            links = sibling_links(root, files)
            note = f" · note: {len(links)} link(s) to a sibling skill have no target in a single-skill upload" if links else ""
            lines.append(f"{name}.zip  {len(files)} file(s), {size} bytes{note}")
        if not args.check:
            shutil.rmtree(DIST, ignore_errors=True)
            if not problems:
                scratch.rename(DIST)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if problems:
        print("Packaging FAILED, and dist/ holds nothing:" if not args.check else "Packaging FAILED:", file=sys.stderr)
        for line in problems:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    if git("status", "--porcelain", "--", "plugins").strip():
        print("note: the working tree differs from HEAD under plugins/; the zips hold HEAD, not those changes")
    print(f"OK — {len(skills)} skill(s) " + ("checked" if args.check else "packaged into dist/, from HEAD"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
