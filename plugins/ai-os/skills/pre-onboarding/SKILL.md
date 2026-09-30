---
name: pre-onboarding
description: >-
  Prepare a lived-in folder for onboarding onto an AI-OS deployment, in an interactive session: audit it, tidy it only
  through plans the owner approves, extract the full text of every document and write a summary card for each, build
  its wiki (sections by responsibility; every page written in the voice of the one professional best suited to it,
  against a page contract, with its rationale recorded and accepted by the owner and that professional through a
  model that did not write it), then check the folder meets the hand-off contract and hand it to
  project-onboarding. Ships the tools that do the deterministic work. Use when a person wants a folder they already
  keep made ready for the system; for a folder that is already tidy and has no wiki, project-onboarding alone is
  enough.
---

# pre-onboarding

A lived-in folder should reach the system already understood: every document read, the owner's rules written
down, a wiki the owner can use from day one, and nothing left for the maintenance jobs to guess. This skill is the
person's entry point for that preparation. It runs in an interactive session on the operator's machine, calls the
other skills as components, and uses the tools in `tools/` for everything that must be exact.

This skill is being written up (milestone "Pre-onboarding skill"); the tools are in place and proven on a real
folder, and the full method text follows.

## The sequence

1. **Audit** (`tools/audit.py`): the hash-keyed manifest (`family-ai-preprocess-manifest/2`), `AUDIT.md` and
   `summary.json`. Method: `folder-curation` step 1.
2. **Interview and rulebook**: the owner's answers in the folder's rulebook (`CLAUDE.md`, byte-identical
   `AGENTS.md`) and its twin `.familyai/rulebook.json`. Method: `folder-curation` step 2.
3. **Curation rounds** (`tools/plan.py`): propose, the owner approves row by row, execute under guards, prove by
   re-audit. Deletes go to the Bin, only after a clean re-audit of the moves.
4. **Extract** (`tools/extract.py`, `tools/vision.py`): the full text of every document, every page, local tools
   first.
5. **Cards** (`tools/cards.py`, `tools/refs.py`): one summary card per document, written by a bulk engine, joined
   deterministically and checked against the isolation list.
6. **Wiki** (`tools/settings.py`, `tools/wiki.py`): a librarian proposes sections by responsibility and each page's
   best professional; each professional agrees a page contract and writes the page for the owner; a model that
   did not write it reviews every page as the owner and as that professional. Method: `wiki-onboarding` and the
   core wiki rule in `wiki-maintenance`.
7. **Readiness** (`tools/readiness.py`): the hand-off contract, every check a count or a named not-verified state.
8. **Hand off** to `project-onboarding`, which onboards cold and prepared folders the same way.

## Principles

- **The folder carries its own settings.** Its rulebook, and the twins in `.familyai/` that tools read, each pinned
  to its source so an edit makes it stale rather than silently wrong; every tool refuses a stale twin. Formats and
  checks: [`references/settings.md`](references/settings.md).
- **Guards in the tools, not in prompts.** Every write goes through one guarded writer; `--read-only-root` proves a
  tool against a real folder without changing it.
- **One login per machine per engine, context isolated per call.** Tokens are never copied.
- **Nothing is permanently deleted.** Removed copies and emptied folders go to the Bin.
