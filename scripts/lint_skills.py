#!/usr/bin/env python3
"""Lint every plugins/<direction>/skills/<name>/SKILL.md: it must open with a YAML frontmatter
block carrying a non-empty ``description`` (the field Claude Code uses to decide when to invoke
the skill). Fail loud — a malformed skill must never ship to a consumer (a pinned deployment
inlines it; Cowork installs it).

Also lints every direction plugin's manifest, because a stale one is the silent version of the
same failure: Claude Code compares a plugin's ``version`` to decide whether an update exists, so
a manifest frozen at an old release leaves every plugin consumer pinned to stale skills while the
repo ships on. The single-plugin manifest sat at 1.0.0 through four releases exactly this way.

Restructure hazards get their own loud failures: a plugin directory with zero skills, and any
SKILL.md living outside plugins/*/skills/*/ (the signature of a partial move — the old layout's
glob would simply have linted fewer files and said OK)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
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


def newest_release(problems: list[str]) -> str | None:
    changelog = CHANGELOG.read_text() if CHANGELOG.exists() else ""
    match = RELEASE_RE.search(changelog)
    if match is None:
        problems.append("CHANGELOG.md: no `## vX.Y.Z` release heading found")
        return None
    return match.group(1)


def check_plugin(
    plugin_dir: Path,
    marketplace: dict | None,
    latest: str | None,
    problems: list[str],
    versions: dict[str, str],
) -> list[Path]:
    """One direction plugin: manifest identity + version agreement + its skill files."""
    rel = plugin_dir.relative_to(ROOT)
    manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
    manifest = load_json(manifest_path, problems)
    if manifest is not None:
        name = manifest.get("name")
        if name != plugin_dir.name:
            problems.append(
                f"{rel}/.claude-plugin/plugin.json: name {name!r} != directory name {plugin_dir.name!r}"
            )
        declared = manifest.get("version")
        if not isinstance(declared, str) or not declared.strip():
            problems.append(f"{rel}/.claude-plugin/plugin.json: needs a non-empty `version`")
        else:
            versions[str(rel)] = declared
            if latest is not None and declared != latest:
                problems.append(
                    f"{rel}/.claude-plugin/plugin.json: version {declared} != newest CHANGELOG "
                    f"release {latest} — bump it in the release commit, or plugin consumers stay "
                    "pinned to stale skills"
                )
        if marketplace is not None:
            entries = marketplace.get("plugins")
            entries = entries if isinstance(entries, list) else []
            entry = next(
                (e for e in entries if isinstance(e, dict) and e.get("name") == name), None
            )
            if entry is None:
                problems.append(
                    f".claude-plugin/marketplace.json: no plugin entry named {name!r}"
                )
            else:
                # The entry's `version` is optional, but when it IS declared `claude plugin tag`
                # requires it to agree with plugin.json — fail at PR time, not at the refused tag.
                entry_version = entry.get("version")
                if (
                    isinstance(entry_version, str)
                    and entry_version.strip()
                    and entry_version != declared
                ):
                    problems.append(
                        f".claude-plugin/marketplace.json: entry {name!r} version {entry_version} "
                        f"!= {rel}/.claude-plugin/plugin.json version {declared}"
                    )

    skill_files = sorted(plugin_dir.glob("skills/*/SKILL.md"))
    if not skill_files:
        problems.append(f"{rel}: no skills/<name>/SKILL.md found — a plugin with zero skills")
    return skill_files


def main() -> int:
    problems: list[str] = []
    versions: dict[str, str] = {}
    marketplace = load_json(MARKETPLACE, problems)
    latest = newest_release(problems)

    plugin_dirs = sorted(p for p in PLUGINS.glob("*") if p.is_dir()) if PLUGINS.is_dir() else []
    if not plugin_dirs:
        problems.append("no plugins/<direction>/ directories found")

    all_skill_files: list[Path] = []
    for plugin_dir in plugin_dirs:
        all_skill_files += check_plugin(plugin_dir, marketplace, latest, problems, versions)

    if len(set(versions.values())) > 1:
        problems.append(
            "plugin versions disagree (single version stream: every release bumps every "
            f"manifest): {versions}"
        )

    for f in all_skill_files:
        rel = f.relative_to(ROOT)
        fm = frontmatter(f.read_text())
        if fm is None:
            problems.append(f"{rel}: missing or malformed YAML frontmatter")
            continue
        desc = fm.get("description")
        if not isinstance(desc, str) or not desc.strip():
            problems.append(f"{rel}: frontmatter needs a non-empty `description`")

    accounted_for = set(all_skill_files)
    for stray in sorted(ROOT.rglob("SKILL.md")):
        # `.git` internals, and the gitignored `.claude/` tree (git worktrees under
        # `.claude/worktrees/`, the plugin cache) are never real skill sources — skipping them keeps the
        # stray-file check from failing on a concurrent session's worktree (which is absent in a clean clone).
        if ".git" in stray.parts or ".claude" in stray.parts or stray in accounted_for:
            continue
        problems.append(
            f"{stray.relative_to(ROOT)}: SKILL.md outside plugins/*/skills/*/ — stray file or "
            "partial move"
        )

    if problems:
        print("Lint FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(
        f"OK — {len(all_skill_files)} skill(s) across {len(plugin_dirs)} plugin(s) · v{latest}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
