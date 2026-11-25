#!/usr/bin/env python3
"""Package each skill as a zip an agent takes by UPLOAD (a chat app with no marketplace install).

    python scripts/package_skills.py            # write dist/<skill>.zip
    python scripts/package_skills.py --check    # build in a temporary folder, check the limits, write nothing

The layout and the limits are the ones the Agent Skills upload contract states (issue #186): one zip holds ONE
top-level folder, named for the skill, with exactly one SKILL.md in it; at most 500 files; no file over 25 MB;
the zip at most 50 MB. A skill that breaks a limit fails the run, by name.

A zip holds one skill and nothing beside it. A link from that skill to a SIBLING skill (`../other-skill/…`) has
no target after an upload, so each such link is listed as a note: the skill still loads, and the reader of that
link needs the other skill installed too.

A bundle holds what git tracks, and nothing else: the file list and each file's mode come from the git index,
not from the disk. So a cache, an editor's backup file or an untracked draft is never packaged, and the execute
bit is the one the repository records, on any machine. A tracked symbolic link fails the run, by name: a zip
entry cannot stand in for it. The output is the same bytes for the same commit: entries are sorted and carry
one fixed timestamp.

Nothing is left behind by a failed run: every zip is built in a temporary folder, and the zips reach `dist/`
only when all of them passed.

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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_FILES = 500
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_ZIP_BYTES = 50 * 1024 * 1024
FIXED_TIME = (2026, 1, 1, 0, 0, 0)
# Tracked, but not part of what an agent loads: a skill's own tests and the repository's own housekeeping.
SKIP_DIRS = {"tests"}
SKIP_FILES = {".gitignore", ".gitattributes"}
SKIP_PREFIXES = ("test_",)
SYMLINK_MODE = "120000"
EXECUTABLE_MODE = "100755"
SIBLING_LINK = re.compile(r"\]\((\.\./[^)#\s]+)")


def skill_dirs() -> list[Path]:
    return sorted(p.parent for p in ROOT.glob("plugins/*/skills/*/SKILL.md"))


def tracked(skill: Path) -> dict[Path, str]:
    """Every file git tracks under the skill, with the mode the index records for it."""
    listing = subprocess.run(
        ["git", "ls-files", "-s", "-z", "--", str(skill.relative_to(ROOT))],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout
    entries = {}
    for record in filter(None, listing.split("\0")):
        meta, name = record.split("\t", 1)
        entries[ROOT / name] = meta.split()[0]
    return entries


def skipped(relative: Path) -> bool:
    return (
        any(part in SKIP_DIRS for part in relative.parts[:-1])
        or relative.name in SKIP_FILES
        or relative.name.startswith(SKIP_PREFIXES)
    )


def bundle_files(skill: Path, modes: dict[Path, str]) -> list[Path]:
    return sorted(f for f in modes if not skipped(f.relative_to(skill)))


def problems_for(skill: Path, files: list[Path], modes: dict[Path, str]) -> list[str]:
    name, problems = skill.name, []
    for f in files:
        if modes[f] == SYMLINK_MODE:
            problems.append(f"{name}: {f.relative_to(skill)} is a symbolic link, which a bundle cannot carry")
    files = [f for f in files if modes[f] != SYMLINK_MODE]
    manifests = [f for f in files if f.name.lower() == "skill.md"]
    if [f.relative_to(skill).as_posix() for f in manifests] != ["SKILL.md"]:
        found = ", ".join(f.relative_to(skill).as_posix() for f in manifests) or "none"
        problems.append(f"{name}: a bundle holds exactly one SKILL.md, spelt so, at its top; found {found}")
    if len(files) > MAX_FILES:
        problems.append(f"{name}: {len(files)} files, over the limit of {MAX_FILES}")
    for f in files:
        if not f.is_file():
            problems.append(f"{name}: {f.relative_to(skill)} is tracked but missing from the working tree")
        elif f.stat().st_size > MAX_FILE_BYTES:
            problems.append(f"{name}: {f.relative_to(skill)} is {f.stat().st_size} bytes, over {MAX_FILE_BYTES}")
    return problems


def sibling_links(skill: Path, files: list[Path]) -> list[str]:
    """Links that leave the skill's own folder. A `../` link from a file in a subfolder can still land inside
    the skill (`tools/README.md` -> `../SKILL.md`), so each is resolved from the file that holds it."""
    found = set()
    for f in files:
        if f.suffix != ".md":
            continue
        for link in SIBLING_LINK.findall(f.read_text(encoding="utf-8", errors="replace")):
            target = (f.parent / link).resolve()
            if skill.resolve() not in target.parents and target != skill.resolve():
                found.add(str(target.relative_to(ROOT)) if ROOT in target.parents else link)
    return sorted(found)


def write_zip(skill: Path, files: list[Path], modes: dict[Path, str], destination: Path) -> Path:
    target = destination / f"{skill.name}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for f in files:
            info = zipfile.ZipInfo(f"{skill.name}/{f.relative_to(skill).as_posix()}", FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if modes[f] == EXECUTABLE_MODE else 0o644) << 16
            bundle.writestr(info, f.read_bytes())
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="check the limits and write nothing under dist/")
    parser.add_argument("--out", default=str(ROOT / "dist"), help="where the zips go (default: dist/)")
    args = parser.parse_args(argv)

    skills = skill_dirs()
    if not skills:
        print("no plugins/*/skills/*/SKILL.md found", file=sys.stderr)
        return 1
    problems: list[str] = []
    lines: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        built = []
        for skill in skills:
            modes = tracked(skill)
            files = bundle_files(skill, modes)
            found = problems_for(skill, files, modes)
            problems += found
            if found:
                continue
            target = write_zip(skill, files, modes, Path(scratch))
            size = target.stat().st_size
            if size > MAX_ZIP_BYTES:
                problems.append(f"{skill.name}: the zip is {size} bytes, over the limit of {MAX_ZIP_BYTES}")
                continue
            built.append(target)
            links = sibling_links(skill, files)
            note = f" · note: {len(links)} link(s) to a sibling skill have no target in a single-skill upload" if links else ""
            lines.append(f"{skill.name}.zip  {len(files)} file(s), {size} bytes{note}")
        if problems:
            print("Packaging FAILED, and nothing was written:", file=sys.stderr)
            for line in problems:
                print(f"  - {line}", file=sys.stderr)
            return 1
        if not args.check:
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            for target in built:
                shutil.move(str(target), out / target.name)
    print("\n".join(lines))
    print(f"OK — {len(skills)} skill(s) " + ("checked" if args.check else f"packaged into {args.out}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
