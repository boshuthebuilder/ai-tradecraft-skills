#!/usr/bin/env python3
"""Lint every skills/<name>/SKILL.md: it must open with a YAML frontmatter block carrying a
non-empty ``description`` (the field Claude Code uses to decide when to invoke the skill). Fail loud —
a malformed skill must never ship to a consumer (the family-ai-os pipeline inlines it; Cowork installs it).

Also lints the published plugin manifest, because a stale one is the silent version of the same
failure: Claude Code compares ``.claude-plugin/plugin.json``'s ``version`` to decide whether an
update exists, so a manifest frozen at an old release leaves every plugin consumer pinned to stale
skills while the repo ships on. It sat at 1.0.0 through four releases exactly this way."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
CHANGELOG = ROOT / "CHANGELOG.md"
RELEASE_RE = re.compile(r"^## v(\d+\.\d+\.\d+)", re.M)


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


def load_json(path: Path, problems: list[str]) -> dict | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"{path.relative_to(ROOT)}: unreadable ({exc})")
        return None
    if not isinstance(data, dict):
        problems.append(f"{path.relative_to(ROOT)}: expected a JSON object")
        return None
    return data


def check_plugin_manifest(problems: list[str]) -> str | None:
    """plugin.json's version must equal the newest CHANGELOG release, and the marketplace must
    actually list the plugin — the same pair `claude plugin tag` refuses to tag when they disagree."""
    changelog = CHANGELOG.read_text() if CHANGELOG.exists() else ""
    match = RELEASE_RE.search(changelog)
    latest = match.group(1) if match else None
    if latest is None:
        problems.append("CHANGELOG.md: no `## vX.Y.Z` release heading found")

    plugin = load_json(PLUGIN, problems)
    if plugin is None:
        return latest
    declared = plugin.get("version")
    if not isinstance(declared, str) or not declared.strip():
        problems.append(".claude-plugin/plugin.json: needs a non-empty `version`")
    elif latest is not None and declared != latest:
        problems.append(
            f".claude-plugin/plugin.json: version {declared} != newest CHANGELOG release {latest} "
            "— bump it in the release commit, or plugin consumers stay pinned to stale skills"
        )

    marketplace = load_json(MARKETPLACE, problems)
    if marketplace is not None:
        entries = marketplace.get("plugins")
        entries = entries if isinstance(entries, list) else []
        entry = next(
            (e for e in entries if isinstance(e, dict) and e.get("name") == plugin.get("name")), None
        )
        if entry is None:
            problems.append(
                f".claude-plugin/marketplace.json: no plugin entry named {plugin.get('name')!r}"
            )
        else:
            # The entry's `version` is optional, but when it IS declared `claude plugin tag` requires
            # it to agree with plugin.json — so a disagreement has to fail here, at PR time, rather
            # than surface as a refused tag once the release is already being cut.
            entry_version = entry.get("version")
            if isinstance(entry_version, str) and entry_version.strip() and entry_version != declared:
                problems.append(
                    f".claude-plugin/marketplace.json: entry version {entry_version} != "
                    f".claude-plugin/plugin.json version {declared}"
                )
    return latest


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

    version = check_plugin_manifest(problems)

    if problems:
        print("SKILL.md lint FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK — {len(skill_files)} skill(s) valid · plugin manifest v{version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
