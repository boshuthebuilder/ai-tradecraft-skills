---
name: controlled-writing
description: >-
  Write an explanation in a controlled language so a person can read it fast and check it: short sentences
  with one idea each, active voice, simple tenses, one name for each thing, conditions before actions.
  Restates the ASD-STE100 (Simplified Technical English) rule families in its own words, with a setting dial
  ("80% of the way to ASD-STE100" is the default), a claims check so simpler words never drop a caveat, and
  the boundary with ai-writing-audit, whose rhythm check controlled text fails by design. Use when a person
  must understand or verify an agent's long answer, an incident write-up, a spec, a runbook or a handover;
  when steps must not be misread; for a reader whose first language is not English; or for narration.
  Triggers include "explain this in ASD-STE100", "Simplified Technical English", "STE", "controlled
  language", "80% of the way to ASD-STE100", "rewrite these steps so they can't be misread". For a diagram,
  page or video instead of prose, use bespoke-explainers.
---

# Controlled writing

As agents do more of the work, more of a person's time goes on reading what they produced and deciding
whether it is right. Default model prose makes that slow: long sentences, stacked qualifiers, a term that
changes name between paragraphs. A **controlled language** trades range for predictability. Each sentence
carries one idea, in a shape the reader has seen a hundred times, so attention goes to the content.

ASD-STE100, Simplified Technical English (STE), is the best-known controlled language. It was built so that
aircraft maintenance instructions could not be misread, by readers working in a second language. Models know
it by name, so one instruction gets most of its benefit. This skill says how to ask for it, how far to push
it, and how to keep the rewrite honest. Worked examples, templates and prompts are in
[`REFERENCE.md`](REFERENCE.md).

## When to use this skill

Use it when the text exists **to be understood or acted on**, and the reader's time or a misreading is
costly:

- an agent's long answer, analysis or plan that a person must check before acting on it;
- an incident write-up, a handover, a runbook or a procedure;
- a spec, a policy summary or a decision record that several people will read;
- a reader whose first language is not English;
- the narration script of an explainer video (see bespoke-explainers), where a listener cannot re-read.

Do not use it for text that must carry a person's own voice (a letter, a post, marketing copy). Do not use it
where exact wording is the point (a contract clause, a regulation, a clinical instruction): there, quote the
original and explain it beside the quote.

## The instruction

The short form works: *"Explain this in ASD-STE100."* The softer form usually reads better: *"Explain this
80% of the way to ASD-STE100."* The full rules are strict enough to make descriptive text stiff, and full
compliance depends on a dictionary of approved words the model does not have. So describe the output as
**STE-style**, never as STE-compliant.

## The dial

| setting | what is enforced | use for |
|---|---|---|
| **100%** | every rule family below. A technical term is replaced by plain words wherever plain words are exact, and the rest are defined | procedures where a misread step causes damage; non-native readers |
| **80%** (default) | every structural rule at full strength. Technical terms the intended reader knows stay as they are; only the ones they may not know are defined | explanations, analyses, handovers, most reading |
| **50%** | only three rules: the sentence ceilings, one name per thing, conditions first. The rest are encouraged, not required | text that must also read naturally to a general audience |

The structural rules are mechanical: a reader or a script can count them. The vocabulary rule is the
stringent one, and it is the one the 80% setting relaxes. A person who holds a copy of the specification can
supply its dictionary in context for a true 100% pass. Never paste the dictionary into a shared document.

## The rule families, in our words

1. **One word, one meaning; one meaning, one word.** Name a thing once and keep that name. A "node" that
   becomes a "server" and then a "host" reads as three things. If a name is long, give its short form once,
   in brackets, and then use only the short form.
2. **Simple, common words.** Prefer the short everyday word ("use", "start", "show"). Keep a technical term
   when no common word is exact. Define it the first time if the intended reader may not know it; defining
   what they already know is noise. Decide who the reader is before you start.
3. **Short noun groups.** No more than three nouns in a row. Break a longer stack with a preposition: "the
   retry limit of the upload job", not "the upload job retry limit setting".
4. **Verbs as verbs.** Use the verb, not a noun made from it: "test the unit", not "perform a test of the
   unit".
5. **Simple tenses, active voice.** Present, past and future. Say who does what. Use the passive only when
   the actor is unknown or does not matter, and never in an instruction.
6. **No "-ing" forms as verbs.** "When the job runs", not "with the job running".
7. **One idea per sentence.** Split a sentence that joins two claims with "and", "but" or "which".
8. **Short sentences.** At most 20 words in a procedure and 25 in a description (next section).
9. **Short paragraphs, one topic each.** Put the main point first, in the text as a whole and in each
   paragraph. Six sentences at most.
10. **Conditions before actions.** "If the light is red, stop the pump", not the other way round.
11. **Keep the small words.** Do not drop "the", "a" or "that" to save length. Telegraphic text is
    ambiguous.
12. **Warnings first, and as commands.** Put the warning before the step it protects. Start it with the
    action ("Disconnect the power"), then say the risk in one short sentence. In a description, state a
    risk before the recommendation it qualifies.

## Procedures and descriptions

Controlled text has two registers. Decide which one each passage is before writing it.

- **Procedure**: tells the reader what to do. Use numbered steps, one action per step, in the command form
  ("Open the valve."). Ceiling: 20 words per sentence. Do not number two actions as one step unless they must
  happen at the same time.
- **Description**: tells the reader what is true. Use paragraphs with the main point first. Ceiling: 25
  words per sentence.

The ceilings are limits, not targets. Let sentence length vary inside them (five words, then eighteen, then
eleven). Uniform sentences are tiring to read even when each one is clear. Expect the text to grow: one idea
per sentence costs words, and a 222-word incident note became about 340 words at the 80% setting.

## Simplify the words, never the claims

A rewrite into simpler words is where content quietly goes missing. Hedges vanish, conditions merge and a
number gets rounded. Guard it with a **claims ledger**:

1. Before rewriting, list every claim in the source: each fact, number, condition, exception, caveat and
   statement of uncertainty.
2. After rewriting, find each one in the new text. Nothing is dropped, nothing is added, no strength changes.
   A definition you add is not a claim from the source, so list your definitions separately and check each
   one: a plausible wrong definition is the commonest thing a rewrite adds.
3. Give each caveat its own sentence: "This was not tested on the old version." A caveat inside a long
   clause is the first thing a simplifier removes.
4. Leave numbers, units, names, identifiers and quoted text exactly as they were.

If a rule would force a false or weaker statement, break the rule. Accuracy outranks style.

## How to apply

1. Choose the register for each passage (procedure or description) and the setting (80% unless told
   otherwise).
2. List the claims (the ledger above).
3. Write, or rewrite, against the rule families.
4. Check the structure: count the words in every sentence over about 15, and scan for passives, "-ing"
   verbs, noun stacks and a term with two names. Models drift back to long sentences towards the end of a
   long text, so check the last third with the most care.
5. Check the ledger.
6. Deliver with the declaration line below.

## Controlled text and ai-writing-audit

`ai-writing-audit` treats very low sentence-length variance as its strongest stylistic sign of machine
authorship, and its scanner flags a standard deviation below 5. Controlled text produces exactly that by
design. The two skills ask different questions, so **the purpose of the text decides which one applies**:

- Controlled text is a declared **reading aid**, written for its reader, and nobody presents it as a
  person's own voice. The audit's rhythm band does not apply to it. Never lengthen a sentence past its
  ceiling, or merge two ideas, to satisfy the scanner.
- The audit's near-decisive provenance signs still apply: leaked citation markup, chat-mode leakage ("I
  hope this helps"), unfilled placeholders. They are never part of a controlled text.
- Its "fires when it co-occurs" signs are judged by the genre. Numbered steps, warning blocks and one name
  used again and again are what controlled text is meant to look like. Repeating a term is the opposite of
  the elegant variation the audit flags.
- If one text must do both jobs (a procedure published under a person's name, say), its declared purpose
  picks the winner. As a reading aid, controlled writing wins. As the person's voice, the audit wins and
  the setting drops to 50% or off.

## Output

1. One declaration line at the top: *Controlled English, 80% setting, written for reading.* It tells the
   reader what kind of text this is, and it tells an auditor why the rhythm is even.
2. The text.
3. The claims ledger, when the stakes are high or when asked.

## Limits

- The output is STE-style, not certified STE. Only a checker with the specification's dictionary can certify
  vocabulary.
- The rules are written for English. In another language, apply the structural families only, and say so.
- A controlled rewrite of a wrong answer is a clearer wrong answer. The ledger keeps the rewrite faithful to
  its source. It does not make the source true.

## Provenance

ASD-STE100 is maintained by ASD (the Aerospace, Security and Defence Industries Association of Europe), which
owns its copyright. Issue 9 (January 2025) has 53 writing rules and a dictionary of about 900 approved words.
Copies are free of charge on request from [asd-ste100.org](https://asd-ste100.org/). This skill restates the
rule families in its own words. It reproduces neither the specification's text nor its dictionary, so check
the specification itself when compliance matters. The case for asking a model to explain in STE, and the "80%
of the way" setting, come from [Andrej Karpathy's October 2026
post](https://x.com/karpathy/status/2105819303471976479) on understanding the output of language models.
Checked 2026-10. Re-check the rule families when a new Issue is published.
