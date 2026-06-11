#!/usr/bin/env python3
"""Lint every skills/<name>/SKILL.md: it must open with a YAML frontmatter block carrying a
non-empty ``description`` (the field Claude Code uses to decide when to invoke the skill). Fail loud —
a malformed skill must never ship to a consumer (the family-ai-os pipeline inlines it; Cowork installs it)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


def frontmatter(text: str) -> dict | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def main() -> int:
    problems: list[str] = []
    skill_files = sorted(SKILLS.glob("*/SKILL.md"))
    if not skill_files:
        problems.append("no skills/<name>/SKILL.md found")
    for f in skill_files:
        rel = f.relative_to(ROOT)
        fm = frontmatter(f.read_text())
        if fm is None:
            problems.append(f"{rel}: missing or malformed YAML frontmatter")
            continue
        desc = fm.get("description")
        if not isinstance(desc, str) or not desc.strip():
            problems.append(f"{rel}: frontmatter needs a non-empty `description`")

    if problems:
        print("SKILL.md lint FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK — {len(skill_files)} skill(s) valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
