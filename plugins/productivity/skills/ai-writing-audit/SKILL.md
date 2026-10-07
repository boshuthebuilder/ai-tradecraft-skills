---
name: ai-writing-audit
description: >-
  Audit a document for the signs of AI authorship and rewrite to remove them. Judges by clusters and
  structure, not a single banned word: leaked citation markup, chat-mode leakage (cutoff disclaimers,
  placeholder text, "I hope this helps"), and low sentence-length variance are near-decisive; negative
  parallelism, formatting overkill, copula-dodging, and compulsive summaries fire when they co-occur;
  vocabulary and em-dashes only contribute. Use when a draft, report, brief, handover doc, marketing copy,
  README, or any prose you are about to share needs to read as a person wrote it rather than an LLM.
  Triggers include "audit for AI tells", "remove the signs of AI writing", "make this sound less like AI",
  "de-slop this", "proofread for AI patterns", references to the Wikipedia "Signs of AI writing" essay,
  and checking this catalogue is still current against that essay (tools/sync_check.py).
---

# AI writing audit

Detect the tells that mark prose as LLM-written, then rewrite so it reads as human. The pattern catalogue,
with examples and sources, is in [`REFERENCE.md`](REFERENCE.md); the triage scanner is
[`tools/audit.py`](tools/audit.py); the sync between the catalogue and the Wikipedia essay it tracks is
deterministic (see *Provenance* at the end).

## When to use this skill

Apply it whenever you (the assistant) have produced, or are about to produce, prose a real person will read
as human-written: handover docs, briefs, decision docs, marketing and landing copy, social posts, emails
sent on someone's behalf, READMEs, developer-facing prose. The user can also invoke it directly ("audit
this for AI tells", "de-slop this draft"). Text declared as controlled writing (a reading aid in a
controlled language) is a different genre, and controlled-writing says which of these checks still apply to it.

## The one principle: judge clusters and structure, not single words

The field moved on from word-lists. A lone "crucial" or a single em-dash proves nothing, and the loudest
old tells have been trained or instructed away (frontier models dialled back "delve" through 2025, and
OpenAI shipped an em-dash-suppression setting in late 2025). What survives that arms race is not any one
word. It is **how many tells cluster in one place** and **the shape of the writing underneath**. So weight
the evidence in three bands:

- **Near-decisive on its own.** Leaked citation or tool markup (`oaicite`, `[cite: 1]`, `turn0search0`,
  `grok_card`, `【85†...】`) and chat-mode leakage — cutoff/source-availability disclaimers, "I hope this
  helps", unfilled "[Insert X]" placeholders. These are provenance, not style; one confirmed hit is enough
  to conclude the text was pasted from an LLM. Very low sentence-length variance (robotic rhythm) is the
  strongest *stylistic* signal.
- **Fires when it co-occurs.** Negative parallelism ("it's not X, it's Y"), formatting overkill and
  document mechanics, the rule of three, compulsive summaries and outline-like conclusions, trailing
  "-ing" analysis, false ranges, sycophancy openers, copula-dodging, weasel attribution, significance
  inflation, elegant variation. One is ordinary human writing. Three or more stacked in a short span is
  the tell.
- **Contributes only.** Vocabulary (era-tagged in REFERENCE.md), hedging clichés, stock transitions,
  flattery adjectives, em-dash *density*. Never conclude from these alone; count them toward a cluster.

Rewrite to reduce **density across bands**, not to score zero on any single pattern. A human wrote "crucial"
too.

## The headline checks

Full detail and examples live in REFERENCE.md. In brief:

1. **Citation / markup artifacts** (near-decisive). Search for leaked tokens: `oaicite`, `oai_citation`,
   `turn0search0`, `[cite: 1]`, `grok_card`, `【85†...】`, `ppl-ai-file-upload`, `:::writing` — full
   table in REFERENCE.md §1. Delete them and verify the claim they were attached to.
2. **Chat-mode leakage** (near-decisive). The assistant talking inside the document: "as of my last
   knowledge update", "not widely documented in available sources", "I hope this helps", "[Insert X
   here]", "[Your Name]", "As an AI language model". Delete and re-verify the surrounding claims.
3. **Sentence-length rhythm** (strongest stylistic). LLM prose clusters near one length with a mid-sentence
   comma; human prose varies far more. Read aloud. Break the monotony with short sentences and the
   occasional fragment.
4. **Negative parallelism** (now the most common single tell). "It is not a product, it is a movement."
   Includes the reversed "X rather than Y" when it stacks. Rewrite to a direct claim.
5. **Formatting overkill and document mechanics.** Bold on most lines; a list whose bold title the next
   sentence restates; emoji headers; the title restated as a heading; Title Case; skipped heading levels;
   `---` between sections; tables where prose belongs. Format only where it earns its place; re-outline.
6. **Rule of three.** Stacked triplets where the third item is filler. Vary the cadence: two items, or four.
7. **Compulsive summaries and outline-like conclusions.** "In conclusion" on short sections; "Despite these
   challenges..." / "Future Outlook" closers. Cut them; end on the last substantive point.
8. **Trailing "-ing" analysis.** "Sales rose 12%, reflecting strong demand." Split into two sentences or cut
   the tail — and verify any source the gloss is pinned to.
9. **Sycophancy and collaborative framing** (a 2026 addition). "Great question", "You're absolutely right",
   "Let's break this down", "we will examine". Delete; answer directly.
10. **Copula-dodging, weasel attribution, significance inflation.** "Serves as" for "is"; "experts argue"
    for a named source; "a testament to" / "enduring legacy" for a fact. Restore the plain verb, name the
    source or drop the claim, replace the verdict with the fact that earned it.
11. **Vocabulary, hedging, transitions, flattery, em-dashes** (contributory). Suspicious in a cluster, fine
    alone. See the era-tagged list in REFERENCE.md before flagging a word.

## How to apply

1. **Scan for triage.** Run the scanner against the document or its source text:

   ```
   python3 tools/audit.py path/to/file.md
   ```

   It accepts plain text, Markdown, Python (it reads string literals), and PDF (via `pypdf`). It groups hits
   by evidence band and estimates a cluster verdict. Treat the output as a starting point, never a ruling:
   it cannot judge rhythm, whether a triplet is brand voice, or whether a bullet title is load-bearing.

2. **Read it yourself.** The scanner misses the strongest stylistic signals almost entirely: monotone
   rhythm, elegant variation (each entity renamed on every mention), and formatting overkill in tables.
   Read the document aloud. If a sentence would not come out of a person's mouth, mark it.

3. **Rewrite, do not surface-edit.** Deleting the offending word leaves the shape intact. Rewrite the clause.
   Common moves: negative parallelism to a direct claim; a triplet to two items or a plain sentence; a
   buzzword to a plain verb; a monotone run broken with a short sentence. Reduce the *cluster*, not the
   single hit.

4. **Keep the author's voice.** Phrases from a brand voice guide, a bio bank, or a real human author are not
   yours to flatten just because they pattern-match. The job is to remove tells that came from the model,
   not to sand down a person's writing. When unsure which phrases are intentional, ask.

5. **Re-scan and confirm.** Run the scanner again. Confirm the near-decisive band is empty (no leaked
   markup, no chat-mode leakage), the cluster count dropped, and no band is stacked. Report what changed.

## Output

When asked for an audit, produce:

1. A short summary: which tells appeared, in which evidence band, and the cluster verdict.
2. The rewritten document, or a list of suggested rewrites if the user only wants a review.
3. The post-rewrite scan.

Do not narrate the rationale sentence by sentence. The user can read the diff.

## Provenance

The catalogue tracks the Wikipedia "Signs of AI writing" essay and 2025–2026 primary sources (system cards,
stylometry studies, the tropes.fyi catalogue); REFERENCE.md carries the citations. **Synced 2026-08-15**
against the essay revision recorded in [`tools/coverage.json`](tools/coverage.json) — verify with
`python3 tools/sync_check.py` (exit 0 in sync; 1 coverage drift; 3 fetch failure, never assume in sync
offline; 4 vocabulary drift, re-verify the era-tagged tiers). The vocabulary layer is the most perishable
part of this skill; the structural signals age far more slowly. Update REFERENCE.md and re-sync the map,
not this page, when new patterns surface.
