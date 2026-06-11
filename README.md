# family-skills

Reusable [Agent Skills](https://code.claude.com/docs/en/skills) for maintaining **in-folder knowledge wikis** — a synthesised, always-current layer over a folder of real files. They work in any Claude Code or Cowork session, and the private `family-ai-os` pipeline consumes them from this same source, so the conventions live in **one home**.

## Skills

- **`wiki-maintenance`** — process an inbox item end to end (read → file by confident match → update the pages it touches → surface actions → log), keep the wiki in a human-readable numbered-domain layout, answer queries, and run periodic lint passes. Includes the three provenance classes, the never-overwrite-a-human-edit guard, and the last-4-only PII rule.

## Install (Claude Code / Cowork)

```
/plugin marketplace add boshuthebuilder/family-skills
/plugin install family-skills@family-skills
```

Then open the folder you want maintained and ask Claude to work on its wiki — `wiki-maintenance` loads automatically when relevant.

### For Hilary (or anyone with a Cowork session)

1. In your Cowork session, run the two commands above.
2. Point the session at the shared folder you want maintained.
3. Ask Claude to drain the inbox / update the wiki. The skill drives the rest.

You do **not** need `family-ai-os` to use these — they're self-contained method prose, no private data.

## Two writers on one folder is safe

If a folder is also maintained by the scheduled `family-ai-os` job (the unattended safety net), your inline Cowork edits are never clobbered: the system hashes every file it writes, so when it sees a page you changed it proposes a `.proposed.md` sibling instead of overwriting. Inline maintenance is first-class; the scheduled job is the backstop.

## How updates propagate

- **Cowork / interactive** — you get the latest each session (the marketplace tracks this repo).
- **The family-ai-os mini (unattended)** — consumes a **pinned** clone via `FAMILY_AI_SKILLS_DIR`, advanced only through a reviewed deploy, never auto-latest.

Edit a skill here once → interactive sessions pick it up immediately → the mini picks it up on its next deploy.

## Contributing a skill

Drop a folder under `skills/<name>/` with a `SKILL.md` (YAML frontmatter with at least a `description`). CI (`scripts/lint_skills.py`) lints every skill on push, so a malformed skill never ships. Validate locally with `claude plugin validate .`.
