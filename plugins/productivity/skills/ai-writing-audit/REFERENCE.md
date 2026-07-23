# Signs of AI writing. Detailed reference.

The authoritative pattern list for the `ai-writing-audit` skill. **Last verified 2026-07.**

Primary sources, weighted over SEO content: the Wikipedia essay
[Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) (which now era-tags its
own vocabulary and grades evidence by strength); the [tropes.fyi](https://tropes.fyi/directory) catalogue
(regex-validated against verified human and AI corpora, Feb 2026); a peer-reviewed stylometry study in
[Nature HSSC 2025](https://www.nature.com/articles/s41599-025-05986-3); Pangram Labs'
[detection guide](https://www.pangram.com/blog/comprehensive-guide-to-spotting-ai-writing-patterns);
lab statements on em-dash suppression
([TechCrunch, Nov 2025](https://techcrunch.com/2025/11/14/openai-says-its-fixed-chatgpts-em-dash-problem/))
and negative parallelism
([TechCrunch, Apr 2026](https://techcrunch.com/2026/04/20/ai-writing-its-not-just-this-its-that-barrons/)).

## How to read this list

Models are trained to pick the likely next token, so their prose regresses to the centre of the training
distribution. The patterns below are the footprints of that regression. Two things changed since the
2023–2024 word-list era, and they set how you must weigh a hit:

1. **The loud lexical tells get patched.** Once a word or a punctuation habit becomes notorious, labs train
   or instruct it away. "delve" dropped off sharply in frontier chat models through 2025; OpenAI shipped a
   working em-dash-suppression instruction in November 2025. A single banned word is therefore weak and
   perishable evidence.
2. **Structure outlasts vocabulary.** What a model cannot cheaply hide is the *shape* of its output:
   uniform sentence rhythm, stacked patterns, and literal tool markup it leaked into the text. These are the
   durable signals.

So grade every hit into one of three bands and judge the document on **cluster density**, not any single
match. Wikipedia's own essay made the same move: single word or phrase hits are "weak" evidence; clusters
and hard artifacts are "strong".

- **Band 1 — near-decisive.** Leaked citation/tool markup (§1); very low sentence-length variance (§2).
- **Band 2 — fires in clusters.** §3–§9. One is ordinary; three-plus stacked in a short span is the tell.
- **Band 3 — contributory only.** §10–§14. Count toward a cluster, never conclude from alone.

---

## Band 1 — near-decisive

### 1. Citation and markup artifacts

The strongest signal in the whole catalogue, and the newest. When text is pasted out of a chat product, the
rendering tokens sometimes come with it. These are machine artifacts, not style: **one is enough** to
conclude the passage was generated. Search for, and delete, the leaked markers below, then verify the claim
each was attached to (the citation it "supported" may be fabricated).

| Product | Leaked tokens |
|---|---|
| ChatGPT | `oaicite`, `contentReference`, `:contentReference[oaicite:...]`, `turn0search0`, `turn0view0`, `turn0news0` |
| Gemini | `[cite: 1]`, `[cite_start]`, `[span_1]`, `[start_span]` |
| Grok | `grok_card`, `grok_render_citation_card_json` |
| Perplexity | `ppl-ai-file-upload`, `attached_file` |

### 2. Sentence-length rhythm (burstiness)

The strongest *stylistic* tell, and the one that has gained the most evidence since 2024. Human writing
varies sentence length a lot; LLM writing clusters near a single length, often with a comma in the middle.
Quantified: human academic prose runs a sentence-length standard deviation of roughly 8.2 words, against
about 4.1 for GPT-4o and 5.3 for Claude (Nature HSSC 2025). Low "burstiness" is what detectors like GPTZero
lean on precisely because it is expensive to fake.

Fix by varying length deliberately. Put a three-word sentence next to a thirty-word one. Use the occasional
fragment. Read the passage aloud; if it plods in a steady beat, restructure.

---

## Band 2 — fires in clusters

### 3. Negative parallelism

Now the single most commonly identified tell (its use in corporate communications roughly quadrupled from
2023 to 2025, and it is named as a tic of 2025-era frontier models). Forms: "It's not X, it's Y", "Not only
X, but Y", "Not just X, but also Y".

| AI-shaped | Human-shaped |
|---|---|
| It is not a product. It is a movement. | It is more of a movement than a product. |
| Not only is it fast, but it is also cheap. | It is fast and cheap. |
| This is not just an update. It is a rethink. | This is a rethink, not just an update. |

### 4. Formatting overkill

Consistently cited across every current source. Three sub-patterns:

a. **Bold on most lines.** Bold stops meaning anything when everything is bold. Reserve it for headings,
   table headers, and the occasional load-bearing term.

b. **Bulleted list whose bold title the next sentence restates.** Pick one.

> - **Add to Meta Business Portfolio.** Adding to the Meta Business Portfolio covers Facebook Page and
>   Instagram. → **Add to Meta Business Portfolio.** Covers Facebook Page and Instagram.

c. **Unicode decoration.** Arrows (→), decorative bullets, and emoji section headers used as ornament.

### 5. Rule of three (triplets)

Three-item lists everywhere: adjectives, benefits, takeaways. Models default to three because it is rhythmic
and over-represented in marketing prose.

| AI-shaped | Human-shaped |
|---|---|
| Innovative, transformative, and groundbreaking. | (Pick one. Or use two, or four if the content needs four.) |
| Convenient, efficient, scalable. | Convenient and efficient. |

Triplets are legitimate in brand bios, taglines, and creative writing. The tell is when they stack across
paragraphs and the third item is filler. tropes.fyi catalogues the same thing as "Tricolon Abuse".

### 6. Compulsive summaries

"In conclusion", "Overall,", "To summarise", "In summary" on short sections that needed no summary. The
instinct comes from academic and corporate training data. tropes.fyi flags the escalation, "Fractal
Summaries", where the same wrap-up recurs at every heading level, not just the end.

### 7. Trailing "-ing" analysis

Sentences ending in a present-participle phrase that adds vague commentary or attribution. Named in the live
Wikipedia essay as a current pattern.

| AI-shaped | Human-shaped |
|---|---|
| Sales rose 12%, reflecting strong consumer demand. | Sales rose 12%. Consumer demand was strong. |
| She joined in 2019, bringing experience from two startups. | She joined in 2019. She came from two startups. |

### 8. False ranges

"From X to Y" implying a spectrum that is not in the source. Acceptable for a real, verifiable continuum
("from £5 to £500"); not for vague pseudo-ranges that gesture at scale ("from intimate gatherings to global
movements").

### 9. Sycophancy openers (2026 addition)

A behavioural tell, distinct from the lexical flattery in §13. Labs tuned models warmer through 2025–2026,
and one 2026 study found the major chat assistants agree with a user about 49% more often than a person
would. The visible residue is the praise-first opener and the reflexive validation: "Great question",
"You're absolutely right", "Certainly!", "I'd be happy to", and the pedagogical "Let's break this down".
Delete them and answer directly. tropes.fyi adds sibling tics: "Here's the Kicker", "The Truth Is Simple",
"Think of It As", and the "Serves-As Dodge" (writing "stands as" / "represents" / "marks" to avoid a plain
"is").

---

## Band 3 — contributory only

Never conclude from these alone. Each counts toward a cluster.

### 10. Vocabulary (era-tagged)

The word-list is the most perishable layer. Wikipedia now tiers it by model generation rather than keeping
one flat list, because the words rotate as models are retuned. Treat a word as *weak* evidence and check the
era before flagging.

- **2023–mid-2024 (GPT-4 era), now fading:** delve, intricate, tapestry, pivotal, underscore, boast.
  "delve" in particular dropped off sharply in 2025 frontier output. Lower-quality "signs of AI" blogs still
  lead with it; that is recycled, not current.
- **mid-2024–mid-2025 (GPT-4o era):** align with, enhance, foster, showcase, emphasise, seamless.
- **mid-2025+ (GPT-5 era):** emphasise, highlight, plus "notability-focused" phrasing in encyclopedic text.
- **Still overused but often legitimate:** crucial, critical, robust, comprehensive, meticulous, leverage
  (verb), navigate (metaphor), elevate, myriad, plethora, landscape (metaphor), realm, ensure.

A note on folklore: the popular story that "delve" entered LLMs through a specific dialect of RLHF
annotators is **not established** — a corpus study found no such dialect signal and left the cause open. Do
not repeat it as fact.

### 11. Hedging clichés

"It is important to note that", "It is worth noting that", "Notably,", "Importantly,", "It should be
acknowledged that". If the note matters, state it. If it does not, cut it.

### 12. Stock transitions

"Furthermore,", "Moreover,", "Additionally,", "On the other hand,", "That being said,", "With that said,".
Not wrong, but stacked they read as AI. Prefer "And", "But", "Also", or drop the transition.

### 13. Flattery and puffery

Praise the content has not earned: fascinating, intriguing, remarkable, exceptional, captivating,
mesmerising, transformative, paradigm-shifting, powerful (with no specific power), compelling, must-read.
Newer models are more *subtly* positive than the blatant GPT-4 version, so the lexical form is weakening;
the behavioural form is §9. If removing the adjective loses no information, remove it.

### 14. Em-dash density

Once called "the most infamous tell", now demoted and contested. It is gameable (OpenAI ships a setting to
suppress it) and there is public pushback defending it as ordinary punctuation. So judge **density**, not
presence: a natural writer uses two or three em-dashes in a piece, while LLM output can run twenty-plus.
Flag the piece only when the rate is several times the human baseline (roughly, more than one per hundred
words), and always as a contributor, never alone. Watch also for the double hyphen (`word--word`) as the
replacement once a writer or model starts avoiding the literal em-dash.

### 15. Wikipedia-specific tells

For encyclopedic text: "best known for" on non-famous subjects; vague attribution ("experts say", "many
believe", "observers argue"); promotional puffery ("vibrant", "nestled", "rich heritage"); year-by-year
career narration; and the mid-2025+ overemphasis on media coverage and "notability".

---

## Model fingerprints

When the source model matters, these tendencies are documented well enough to help attribute (all as of
2026, all soft signals):

- **ChatGPT** — most detectable overall; most likely to leak the §1 citation artifacts.
- **Gemini** — flagged more on rigid hierarchical structure than on vocabulary.
- **Grok** — pseudo-scientific vocabulary ("causal", "empirical", "correlate") and a persistent "underscore".
- **Claude** — the best sentence-length variance (hardest to catch on §2), with a documented residual
  tendency to over-hedge and moralise as a side effect of sycophancy reduction.

## Scoring: how the scanner and you should decide

`tools/audit.py` groups hits by band and prints a verdict on the same logic you should apply by hand:

- Any **Band 1** hit → conclude AI-shaped (verify markup is a leaked token, not a code sample).
- No Band 1, but **three or more distinct Band 2 patterns** clustered → AI-shaped.
- Only **Band 3** hits → inconclusive; a human wrote "crucial" too. Read for rhythm before judging.

Reduce density across bands. Do not chase zero on any single pattern.

## Limits of automated scanning

The scanner finds the easy cases. It cannot judge sentence rhythm (§2 — the strongest stylistic signal, and
essentially invisible to regex), whether a triplet is brand voice, whether "navigate" is literal or
metaphor, or whether a bullet title is load-bearing. Always read the document yourself after the scan. The
scanner is triage, not a verdict.

## Brand-voice exception

Phrases from a brand's voice guide, a bio bank, or a real human author are not to be edited just because
they pattern-match. The job is to remove tells that came from the model, not to flatten a person's writing.
When in doubt, ask which phrases are intentional.
