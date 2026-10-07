---
name: bespoke-explainers
description: >-
  Choose and build the format that gets a person to understanding fastest: plain prose, a diagram, an
  interactive HTML page or a narrated explainer video, climbing only as far as the understanding needs.
  Treats the result as a custom, throwaway artefact built for one reader, and as model output whose claims are
  checked before anything is rendered. Picks the diagram tool by where it will be seen and how big it is
  (Mermaid, hand-written SVG, computed layout, or a script that reads the real source). Carries a verified
  video recipe: Manim Community Edition with text-to-speech narration timed beat by beat, a free local voice
  by default, and a paid voice only through an environment variable, never a key pasted into chat. Use when
  asked to "explain this visually", "draw a diagram of", "build an interactive page that shows", "make a
  3Blue1Brown-style video explainer", "explainer video with voiceover", or when a long answer would land
  faster as a picture, a page or a film. The prose case goes to controlled-writing.
---

# Bespoke explainers

When agents do more of the work, more of a person's job is understanding what was done. Prose is often the
slowest way to get there. Structure is easier to see than to read about, a mechanism is easier to grasp by
poking at it, and a process that unfolds in time is easiest to watch. Code is now cheap, so it is reasonable
to build a diagram, a small web page or a short narrated video **for one reader and one question**, and then
throw it away. Ten years ago nobody would have built a custom animated explainer for a single incident review.
Now it costs minutes.

This skill picks the format and says how to build each one so that it is right, not just impressive. The
recipes, worked choices and the tested video pipeline are in [`REFERENCE.md`](REFERENCE.md).

## When to use this skill

- Someone asks for a visual, a page or a video explanation of anything.
- An answer you are about to give is long, and its subject has structure (parts and links), state (things
  that change), or time (steps in order). Offer the better format, or build it when that is cheap.
- Someone has to understand or approve something an agent built: an architecture, a migration, a data flow,
  an incident. The explainer is how they check the work without reading all of it.

## The ladder: choose by what the reader must see

| format | use it when the reader must see… | cost to make | cost to check | home |
|---|---|---|---|---|
| **prose** | an argument, a decision, a short procedure | lowest | read it | controlled-writing |
| **diagram** | parts and how they connect; a flow; states and transitions; a timeline | low | look at it | below |
| **HTML page** | a mechanism to try for themselves: inputs, a toggle, "what happens if" | medium | open it and use every control | below |
| **video** | a process unfolding in time, or an intuition that motion builds | highest | watch all of it | below |

Start at the cheapest format that can show the thing, and climb only when the format below cannot show it.
Ask "what could the rung below not show?" and write the answer down. If the answer is "nothing", stay
there. A video of something a diagram shows equally well costs more to make and to check, and buys
nothing.

## Treat it as discardable

The artefact serves one reader in one sitting, so it does not need the qualities of maintained software:
abstraction, configuration, tests for the long run. It does need the qualities of a correct explanation.

- **Keep the source, not the render.** The script, the scene file, the HTML and the diagram text are what
  you keep. Regenerate the render from them, and never edit a render by hand.
- **Regenerate rather than patch.** When the content changes, edit the source and rebuild.
- **Do not polish.** Effort goes into the claim being right and the picture being legible, not into
  styling.

## It is model output: check the content before the render

An explainer is the most persuasive thing a model can produce, which makes a wrong one worse than a wrong
paragraph. A confident animation of a mechanism that does not exist is very hard to un-see.

1. **Write the claims first.** Before any drawing or code, list what the explainer will assert, as plain
   sentences. Check each one against the source (the code, the log, the document), not against the model's
   memory.
2. **Draw real structure from the real source.** A diagram of code dependencies, a schema or a call graph
   comes from a script that reads the source. A diagram drawn from what the model remembers can be
   confidently wrong.
3. **Say what it is.** Put one line on the artefact saying it was generated, what it was checked against, and
   what is simulated or simplified.
4. **Build a sample first.** One diagram node, one page control, a 20-second clip. Check it, then build the
   whole thing.

## Diagram: choose the tool by where it is seen and how big it is

| where it is seen / how big | tool | check |
|---|---|---|
| inside a `.md` that a person opens in Obsidian, Typora or GitHub | Mermaid (which kinds render where belongs to portable-markdown) | render it with the Mermaid CLI and look; open it in the editor when it matters |
| inside an HTML page or a video frame, from Mermaid | Mermaid pre-rendered to SVG by the CLI, so the page loads no script | as below |
| small (about 10 nodes or fewer), where placement and emphasis matter | SVG written directly | **render it and look**: overlapping labels, arrows through boxes and clipped text raise no error |
| a large graph (dozens of nodes) | a computed layout (Graphviz, or ELK inside the page); the model writes the edges, never the coordinates | render it and look |
| real structure: dependencies, a schema, a call graph | a script reads the source and emits one of the formats above | spot-check a few edges against the source |
| a mood or an illustration only | an image model | never for labels or structure: it garbles text |

Every row ends in looking at the rendered result. A diagram fails silently: it is valid code that draws the
wrong picture.

## HTML page

One self-contained `.html` file that opens from disk:

- inline CSS and JavaScript, data embedded, **no network** (no CDN script, no font service, no `fetch`);
- the question it answers stated at the top, and the "generated, checked against…" line;
- two to four controls, each changing something the reader can see;
- works at phone width and in dark mode;
- no secrets, ever: the page is code that anyone it is sent to can read.

To check it, open it from disk, confirm that the browser made **zero** network requests, and use every
control once.

## Video

The look people mean by "3Blue1Brown style" comes from Manim. Its community-maintained, documented fork
is **Manim Community Edition**, which is what the recipe uses. The original author's own version (ManimGL) has a
different API, and models mix the two.

The pipeline: **script → beats → voice → scene → 20-second sample → full render → check.**

- **Script.** Write the narration first, one line per beat, with controlled-writing (12 to 20 words a line,
  numbers and abbreviations spelt as they should be spoken). A listener cannot re-read, so each line carries
  one idea.
- **Audio is the clock.** Synthesise one audio file per beat, measure each one, and time the animation to the
  audio, never the reverse. Each beat ends at an absolute time (the sum of the durations so far plus a
  short pause), so frame rounding cannot drift. Editing one line and re-rendering re-flows everything after it.
- **Check the render**, not just the exit code: an audio stream exists, each beat starts where the plan
  says, and a frame grabbed from each beat shows what the line describes.

**The voice policy:**

- A **free local voice** by default. It needs no account and sends nothing anywhere.
- A **paid voice only when the person names it.** Its key is read at run time from the environment variable
  the vendor's SDK reads, set by the person in their own shell.
- If the paid voice is chosen and its variable is unset, **stop and say so**. Never fall back silently to
  another voice: the video would change without anyone deciding it.
- **Never ask for a key in chat, and never write one into a file**: not the scene, a `.env`, a log or the
  shell history. Some tools offer to prompt for a key and save it to `.env`; do not let them.

## How to apply

1. Name the reader and the question, in one sentence each.
2. Pick the rung (the ladder above), and write down what the rung below could not show.
3. List the claims and check each against the source.
4. Build the smallest sample that can be checked, and check it.
5. Build the whole thing, and check the whole thing (look at every diagram, use every control, watch every
   second).
6. Hand it back with: where the source is, how to regenerate it, what was checked, and what is simulated.

## Where the pieces live

- Writing the prose rung, and every narration script: **controlled-writing**.
- Which Mermaid kinds and callout types render in Typora and Obsidian, and how a markdown page should link
  to an `.html` or `.mp4` explainer beside it: **portable-markdown**.
- Whether prose reads as a person wrote it: **ai-writing-audit**. It does not apply to narration written as
  controlled text.

## Provenance

The ladder (prose, diagram, page, video, each "even better" than the last) and the case for large,
custom, discardable artefacts come from [Andrej Karpathy's October 2026
post](https://x.com/karpathy/status/2105819303471976479) on understanding the output of language models. The
video recipe was proven end to end on 2026-10-07, on an Apple-silicon Mac with macOS 27.0.1 and Python 3.12.13:
Manim Community Edition 0.21.0 (pycairo 1.29.2, ManimPango 0.7.0, PyAV 19.0.1), with narration by Kokoro through
`kokoro-onnx` 0.6.1 (int8 model, v1.0 voices), and by Piper (`piper-tts` 1.8.0) and the macOS `say` voice as
alternatives. Every beat started within 0.10 s of plan. A second agent reproduced it from REFERENCE alone. The
diagram rows were checked with the Mermaid CLI 12.0.0 (Mermaid 12.1.0) and a hand-written SVG, rendered in
one self-contained page with zero network requests. **Documented, not run:** the paid voice's own call, the
computed-layout row (Graphviz and ELK), and any platform other than macOS. Re-verify after a major version of
Manim or of either voice package; the per-run record is in REFERENCE.
