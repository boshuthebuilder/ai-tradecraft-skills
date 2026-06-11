# ai-os-skills

Reusable [Agent Skills](https://code.claude.com/docs/en/skills) for maintaining **in-folder knowledge wikis** — a synthesised, always-current layer over a folder of real files. They work in any Claude Code or Cowork session, and can also be consumed by an automated pipeline from this same source, so the conventions live in **one home**.

## Skills

- **`wiki-maintenance`** — process an inbox item end to end (read → file by confident match → update the pages it touches → surface actions → log), keep a synthesised wiki current over a folder of files, answer queries, and run periodic lint passes. Includes the provenance model, the never-overwrite-a-human-edit guard, and a sensitive-data rule (record identifiers as last-4 only).

## Install (Claude Code / Cowork)

```
/plugin marketplace add boshuthebuilder/ai-os-skills
/plugin install ai-os-skills@ai-os-skills
```

Then open the folder you want maintained and ask Claude to work on its wiki — `wiki-maintenance` loads automatically when relevant.

### Using it in a Cowork session

1. Run the two commands above in your Cowork session.
2. Point the session at the folder you want maintained (your own, or one shared with you).
3. Ask Claude to drain the inbox / update the wiki — the skill drives the rest.

You don't need any particular system to use these — they're self-contained method prose, no private data.

## Two writers on one folder is safe

If a folder is also maintained by a scheduled automation (an unattended safety net), your inline edits are never clobbered: a well-behaved system hashes every file it writes, so when it sees a page you changed it proposes a `.proposed.md` sibling instead of overwriting. Inline maintenance is first-class; the scheduled pass is the backstop.

## How updates propagate

- **Cowork / interactive** — you get the latest each session (the marketplace tracks this repo).
- **An unattended automation** — should consume a **pinned** clone, advanced only through a reviewed deploy, never auto-latest.

Edit a skill here once → interactive sessions pick it up immediately → a pinned automation picks it up on its next deploy.

## Contributing a skill

Drop a folder under `skills/<name>/` with a `SKILL.md` (YAML frontmatter with at least a `description`). CI (`scripts/lint_skills.py`) lints every skill on push, so a malformed skill never ships. Validate locally with `claude plugin validate .`.
