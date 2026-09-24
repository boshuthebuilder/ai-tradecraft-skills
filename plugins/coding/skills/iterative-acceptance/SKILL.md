---
name: iterative-acceptance
description: >-
  Develop a system on top of nondeterministic tools (LLMs, OCR, vision models) when the
  expectations cannot be fully specified up front — by iterating real test runs against a frozen
  baseline with predictions registered BEFORE each run and scored honestly after it. Covers the
  frozen-baseline invariant (byte-identity checked around every experiment), the registered
  prediction table, the blank-slate protocol (park all state so context comes only from the
  operator's prompt), the misses-become-capabilities rule (every gap turns into a systematic
  feature, never a hack for the test data), and the context-vs-code boundary (batch knowledge
  lives in the prompt channel; fixes live in code). Use when building or hardening any pipeline
  whose core step is a model call and whose "correct output" is discovered by looking at real
  results — document processing, extraction, classification, synthesis.
---

# iterative-acceptance

Some systems cannot be specified into existence. When the core step is a nondeterministic tool
and the owner's real expectations only surface on contact with real output ("these two should
have merged", "this date was readable", "those files belong to different worlds"), the unit of
progress is not a ticket — it is a **scored test run**. This skill is the loop that makes those
runs cumulative instead of anecdotal. It was proven building a document-preprocessing pipeline
across four releases, each triggered by the owner reviewing the previous run's real output; the
attention queue went from 88 of 132 files to 2, none of them wrong.

## The loop

1. **Freeze a baseline artefact.** The first credible real run's output becomes a frozen
   reference: fingerprint it (per-file hashes rolled up into one digest, with the exact command
   recorded — the METHOD is part of the invariant; a different sort order or path form yields a
   different rollup from identical bytes). Verify byte-identity BEFORE, optionally DURING, and
   AFTER every later experiment. The baseline is the one thing that must never drift, because
   every later comparison silently assumes it hasn't.
2. **Register predictions before the run.** Before each test, write the expected-outcome table:
   counts, named files, specific behaviours, wall-clock. Predictions bind you honestly — after
   the run, each line is scored HIT or MISS, and a miss gets an explanation, never a
   rationalisation. ("The odd-only file will be flagged" scored as a miss-of-mechanism when the
   file turned out to be a both-halves pair failing a gate — right behaviour, wrong prediction,
   said so.) Soft predictions (judgement outcomes like a category rebalance) are marked as such
   when registered, not reclassified after.
3. **Blank-slate when memory would flatter.** To test what the system does for a NEW user, make
   it genuinely new: park every state artefact aside (manifest, history, engine state — into an
   ignored location, nothing deleted), so all context arrives through the operator's prompt.
   Scrub the prompt itself of history references ("earlier passes could not read this" leaks the
   very memory the test erased). A forced re-judge over live state approximates this but leaks
   vocabulary and prior entries; say which mode ran.
4. **Misses become capabilities, never hacks.** Every reviewed gap turns into a SYSTEMATIC
   feature that would have handled the case — never a patch keyed to the test data. The test for
   this: the fix must make sense for a batch you have never seen. (A reversed-scan merge became
   a general geometry-declaration channel; a hard-to-read date became a general second-look
   pass — not code that knows about one file.)
5. **Context in the prompt, fixes in the code.** Knowledge specific to a batch — known dates,
   entity framing, how one pair was physically scanned — is OPERATOR CONTEXT, supplied at run
   time through the prompt channel and honoured by general machinery. If you find batch facts
   hardening into the system (a filename in code, a date in a config), stop: that is the hack
   rule 4 forbids, wearing a different coat.
6. **Iterate until the attention surface is near-empty.** The exit condition is the owner's:
   the queue of things needing a human holds only items a human genuinely must decide, each with
   a stated reason. Then the next batch of real input starts the loop again, cheaper.

For a synthesis, the attention surface includes unresolved citations and links, malformed tables,
missing contract fields, undated roll-up rows, identifier-policy violations and
independent reader findings. Record the same scoped counters in each build's verification artefact;
a policy-permitted mask is not a defect, and zero findings from an unperformed check is not success.
A formatting miss may become a deterministic renderer; an incorrect identifier completion may become
a typed, evidence-logged resolver. Recheck the capability on new fixtures, not only the page that
exposed the miss.

## Costs and honesty

- Every run's cost/wall-clock is part of the scored table — regressions are findings.
- The run's operator context is stored with the run, verbatim, so "what did we tell it" is
  always answerable later.
- A clean scorecard on a re-run of the SAME data is necessary, not sufficient: schedule fresh
  data through the loop before trusting the system unattended.

The reference implementation of the loop is family-ai-os's preprocess acceptance protocol
(frozen `Runs/<ts>` parcel + rollup digest; per-release prediction tables; the parked-state
blank-slate run; four releases of misses-to-capabilities). Pair with `adversarial-review` (the
code gate each release still passes) and `implementation-discipline` (the conduct inside each
change); this skill is the loop AROUND them for systems whose spec is discovered, not written.
