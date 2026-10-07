# Controlled writing — reference

Examples, templates and prompts for [`SKILL.md`](SKILL.md). Every example is invented. The rule families are
restated in this repo's own words; nothing here is copied from the ASD-STE100 specification or its
dictionary, which ASD owns (a free copy is available from [asd-ste100.org](https://asd-ste100.org/)).

## The rule families, wrong and right

| # | family | instead of | write |
|---|---|---|---|
| 1 | one word, one meaning | "Restart the node. If the server does not come back, check the host logs." | "Restart the node. If the node does not come back, check the node logs." |
| 2 | simple, common words | "Utilise the configuration utility to facilitate the modification." | "Use the configuration tool to make the change." |
| 3 | short noun groups | "the upload job retry limit setting value" | "the value of the retry limit for the upload job" |
| 4 | verbs as verbs | "Perform a verification of the backup." | "Verify the backup." |
| 5 | simple tenses, active voice | "The token will have been rotated by the scheduler." | "The scheduler rotates the token." |
| 6 | no "-ing" verbs | "With the migration running, writes are queued." | "When the migration runs, the system queues writes." |
| 7 | one idea per sentence | "The disk filled, which stopped the writer, and the queue backed up." | "The disk filled. The full disk stopped the writer. The queue then grew." |
| 8 | short sentences | a 38-word sentence | two sentences of 15 and 19 words |
| 9 | short paragraphs, point first | the conclusion in the last sentence | the conclusion in the first sentence |
| 10 | conditions first | "Stop the pump if the light is red." | "If the light is red, stop the pump." |
| 11 | keep the small words | "Check config, restart service, confirm status." | "Check the configuration. Restart the service. Confirm the status." |
| 12 | warnings first, as commands | "Note that the terminals may remain live, so caution is advised." | "Do not touch the terminals for 60 seconds. They stay live." |

Family 7 has a trap: splitting must not lose the link. "The full disk stopped the writer" keeps the cause
that "which" carried. Keep connecting words ("because", "so", "but", "then") at the start of the new sentence.

## One passage at three settings

**Source (descriptive, 52 words):**

> The nightly export, which had been silently skipping records whose `updated_at` timestamp fell exactly on
> the batch boundary due to an off-by-one in the window comparison, has been patched, although records
> skipped before the fix will only be recovered once the backfill job, currently scheduled for Thursday
> pending approval, has run.

**Claims ledger:** (1) the nightly export skipped some records; (2) silently, with no error; (3) only records
whose `updated_at` fell exactly on the batch boundary; (4) the cause was an off-by-one in the window
comparison; (5) it is fixed; (6) records skipped before the fix are still missing; (7) the backfill job will
recover them; (8) it is scheduled for Thursday; (9) it needs approval first.

**100%:**

> The nightly export did not copy some records. It did not show an error when this occurred. These records
> had an `updated_at` time exactly on the boundary of a batch. The cause was an error of one unit in the
> comparison of times. We corrected the error. The records that the export did not copy before the
> correction are still missing. The backfill job will copy them. This job must be approved. Then it can
> start on Thursday.

**80% (default), written for an engineering reader, so "off-by-one" and "backfill job" stay undefined:**

> The nightly export skipped records whose `updated_at` time fell exactly on a batch boundary. It reported
> no error when it did this. The cause was an off-by-one error in the time comparison. This error is now
> fixed. Records skipped before the fix are still missing. The backfill job will recover them. It is scheduled for
> Thursday, but it needs approval first.

**50%:**

> The nightly export was silently skipping records whose `updated_at` time fell exactly on a batch boundary,
> because of an off-by-one error in the time comparison. That is now fixed. Records skipped before the fix
> come back only when the backfill job runs; it is scheduled for Thursday, pending approval.

A first 80% draft of this passage dropped claim 2: "The nightly export skipped records" says nothing about
the silence, and the silence is why nobody noticed. The ledger is what caught it.

## Templates

**Procedure.** A warning goes before the step it protects. In markdown that a person opens in Typora or
Obsidian, use one of the five callout types both render (`note`, `tip`, `important`, `warning`, `caution`),
with the marker alone on its line. The rule for that belongs to portable-markdown.

```markdown
> [!warning]
> **Disconnect the power before you open the panel.** The terminals stay live for 60 seconds.

1. Set the main switch to OFF.
2. Wait 60 seconds.
3. Remove the four screws from the panel.
4. If the green light is on, stop. Set the main switch to OFF again.
```

**Description.**

```markdown
<The main point, in one sentence.> <The reason or evidence.> <A condition or exception, in its own sentence.>
<What is not known, in its own sentence.> <What happens next.>
```

## Prompts

| use | prompt |
|---|---|
| one line | "Explain this in ASD-STE100." |
| the default | "Explain this for <the reader, e.g. an on-call engineer> 80% of the way to ASD-STE100. Keep every structural rule: one idea per sentence, 25 words at most, active voice, one name for each thing. Allow a necessary technical term once you define it. Keep every number, caveat and condition." |
| rewrite with a ledger | "Rewrite the text below 80% of the way to ASD-STE100. First list every claim in it. After the rewrite, confirm that each claim is present, with the same strength." |
| procedure | "Turn this into an STE-style procedure: numbered steps, one action each, command form, conditions before actions, each warning before the step it protects, 20 words per sentence at most." |
| narration | "Write narration for an explainer with N beats, one line per beat, 80% of the way to ASD-STE100, 12 to 20 words a line. Spell numbers and abbreviations the way they should be spoken." |

## The self-check, as counts

Run these on the output before delivering it. Each is a count, so the result is a number, not an
impression.

- Sentences over the ceiling (20 in a procedure, 25 in a description): **0**.
- Steps with more than one action: **0**, unless the actions must happen at the same time.
- Noun groups of four or more nouns: **0**.
- Passive verbs in instructions: **0**.
- Things with more than one name: **0** (list each key noun and every name it appears under).
- Claims from the ledger missing or changed: **0**.
- Paragraphs over six sentences: **0**.

Scripted counting is fine for the first two and the last. A model's own count of words in its sentences is
unreliable, so count them with code or by hand.

## How models get it wrong

- **Tail drift.** The first third obeys the ceilings and the last third does not. Check the end first.
- **Dropped hedges.** "Initial investigation suggests" becomes a plain statement. The ledger catches this.
- **Term drift.** "cache entry", then "cached value", then "the record". Rule 1 is the most often broken.
- **Lost links.** Splitting a sentence drops its "because", and two facts lose their cause.
- **Invented definitions.** Asked to define a term, the model defines it plausibly and wrongly. Check every
  definition against the source.
- **Telegraphic text.** Dropped articles read as clipped and become ambiguous ("Check status, restart").
- **Rounded numbers.** "71%" becomes "about 70%". Numbers are copied, never simplified.
- **A compliance claim.** "This text follows ASD-STE100." It cannot know that. Use the declaration line in
  SKILL.md instead.

## Measured: controlled text against the ai-writing-audit scanner

Measured 2026-10 on an invented 222-word incident note, four sentences long (the longest 74 words). A fresh
agent rewrote it from these two pages alone, as a description, at each setting. Sentence lengths were counted
by script. The rhythm figure is `ai-writing-audit`'s `tools/audit.py`.

| text | words | sentences | longest | over the ceiling | sentence-length SD | scanner verdict |
|---|---|---|---|---|---|---|
| source | 222 | 4 | 74 | 4 | 10.7 | (not run) |
| 100% | 429 | 38 | 19 | 0 | 4.1 | "monotone rhythm, an AI tell" |
| 80% | 343 | 31 | 19 | 0 | 4.3 | "monotone rhythm, an AI tell" |
| 50% | 253 | 19 | 21 | 0 | 4.7 | not run |

Every claim in the ledger survived at every setting. The scanner flagged only the rhythm, and nothing else
in any band. That is the expected result, and the reason for the boundary in SKILL.md: the flag is correct
about the shape and irrelevant to a declared reading aid. The same run found the over-definition failure:
written with no reader named, the 80% rewrite defined "p95 latency", "TTL" and "hit rate" for what was
plainly an engineering audience. Name the reader in the prompt.
