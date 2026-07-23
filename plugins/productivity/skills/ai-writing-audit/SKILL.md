---
name: ai-writing-audit
description: >-
  Audit a document for the signs of AI authorship and rewrite to remove them. Judges by clusters and
  structure, not a single banned word: leaked citation markup and low sentence-length variance are near-
  decisive; negative parallelism, formatting overkill, and compulsive summaries fire when they co-occur;
  vocabulary and em-dashes only contribute. Use when a draft, report, brief, handover doc, marketing copy,
  README, or any prose you are about to share needs to read as a person wrote it rather than an LLM.
  Triggers include "audit for AI tells", "remove the signs of AI writing", "make this sound less like AI",
  "de-slop this", "proofread for AI patterns", and references to the Wikipedia "Signs of AI writing" essay.
---

# AI writing audit

Detect the tells that mark prose as LLM-written, then rewrite so it reads as human. The pattern catalogue,
with examples and sources, is in [`REFERENCE.md`](REFERENCE.md); the triage scanner is
[`tools/audit.py`](tools/audit.py). This page is the method. Last verified against the 2026 landscape
(see *Provenance* at the end).

## When to use this skill

Apply it whenever you (the assistant) have produced, or are about to produce, prose a real person will read
as human-written: handover docs, briefs, decision docs, marketing and landing copy, social posts, emails
sent on someone's behalf, READMEs, developer-facing prose. The user can also invoke it directly ("audit
this for AI tells", "de-slop this draft").

## The one principle: judge clusters and structure, not single words

The field moved on from word-lists. A lone "crucial" or a single em-dash proves nothing, and the loudest
old tells have been trained or instructed away (frontier models dialled back "delve" through 2025, and
OpenAI shipped an em-dash-suppression setting in late 2025). What survives that arms race is not any one
word. It is **how many tells cluster in one place** and **the shape of the writing underneath**. So weight
the evidence in three bands:

- **Near-decisive on its own.** Leaked citation or tool markup (`oaicite`, `[cite: 1]`, `turn0search0`,
  `grok_card`, `ppl-ai-file-upload`). These are machine artifacts, not style; one is enough to conclude the
  text was pasted from an LLM. Very low sentence-length variance (robotic rhythm) is the strongest
  *stylistic* signal.
- **Fires when it co-occurs.** Negative parallelism ("it's not X, it's Y"), formatting overkill, the rule
  of three, compulsive summaries, trailing "-ing" analysis, false ranges, praise-first sycophancy openers.
  One is ordinary human writing. Three or more stacked in a short span is the tell.
- **Contributes only.** Vocabulary (era-tagged in REFERENCE.md), hedging clichés, stock transitions,
  flattery adjectives, em-dash *density*. Never conclude from these alone; count them toward a cluster.

Rewrite to reduce **density across bands**, not to score zero on any single pattern. A human wrote "crucial"
too.

## The headline checks

Full detail and examples live in REFERENCE.md. In brief:

1. **Citation / markup artifacts** (near-decisive). Search for leaked tokens: `oaicite`, `contentReference`,
   `turn0search0`, `[cite: 1]`, `[span_1]`, `grok_card`, `ppl-ai-file-upload`. Delete them and verify the
   claim they were attached to.
2. **Sentence-length rhythm** (strongest stylistic). LLM prose clusters near one length with a mid-sentence
   comma; human prose varies far more. Read aloud. Break the monotony with short sentences and the
   occasional fragment.
3. **Negative parallelism** (now the most common single tell). "It is not a product, it is a movement."
   Rewrite to a direct claim.
4. **Formatting overkill.** Bold on most lines; a bulleted list whose bold title the next sentence restates;
   decorative arrows and emoji headers. Use bold for headings and load-bearing terms only.
5. **Rule of three.** Stacked triplets where the third item is filler. Vary the cadence: two items, or four.
6. **Compulsive summaries.** "In conclusion", "Overall," on short sections that need no summary. Cut them.
7. **Trailing "-ing" analysis.** "Sales rose 12%, reflecting strong demand." Split into two sentences or cut
   the tail.
8. **Sycophancy openers** (a 2026 addition). "Great question", "You're absolutely right", "Let's break this
   down." Delete; answer directly.
9. **Vocabulary, hedging, transitions, flattery, em-dashes** (contributory). Suspicious in a cluster, fine
   alone. See the era-tagged list in REFERENCE.md before flagging a word.

## How to apply

1. **Scan for triage.** Run the scanner against the document or its source text:

   ```
   python3 tools/audit.py path/to/file.md
   ```

   It accepts plain text, Markdown, Python (it reads string literals), and PDF (via `pypdf`). It groups hits
   by evidence band and estimates a cluster verdict. Treat the output as a starting point, never a ruling:
   it cannot judge rhythm, whether a triplet is brand voice, or whether a bullet title is load-bearing.

2. **Read it yourself.** The scanner misses the two strongest signals almost entirely: monotone rhythm and
   formatting overkill in tables. Read the document aloud. If a sentence would not come out of a person's
   mouth, mark it.

3. **Rewrite, do not surface-edit.** Deleting the offending word leaves the shape intact. Rewrite the clause.
   Common moves: negative parallelism to a direct claim; a triplet to two items or a plain sentence; a
   buzzword to a plain verb; a monotone run broken with a short sentence. Reduce the *cluster*, not the
   single hit.

4. **Keep the author's voice.** Phrases from a brand voice guide, a bio bank, or a real human author are not
   yours to flatten just because they pattern-match. The job is to remove tells that came from the model,
   not to sand down a person's writing. When unsure which phrases are intentional, ask.

5. **Re-scan and confirm.** Run the scanner again. Confirm the near-decisive band is empty (no leaked
   markup), the cluster count dropped, and no band is stacked. Report what changed.

## Output

When asked for an audit, produce:

1. A short summary: which tells appeared, in which evidence band, and the cluster verdict.
2. The rewritten document, or a list of suggested rewrites if the user only wants a review.
3. The post-rewrite scan.

Do not narrate the rationale sentence by sentence. The user can read the diff.

## Provenance

The catalogue tracks the Wikipedia "Signs of AI writing" essay and 2025–2026 primary sources (system cards,
stylometry studies, the tropes.fyi catalogue); REFERENCE.md carries the citations. **Last verified
2026-07.** The vocabulary layer is the most perishable part of this skill: individual words get patched out
within a release cycle once they become notorious, so re-verify the era-tagged list before trusting it. The
structural signals (rhythm, clustering, leaked markup) age far more slowly. Update REFERENCE.md, not this
page, when new patterns surface.
