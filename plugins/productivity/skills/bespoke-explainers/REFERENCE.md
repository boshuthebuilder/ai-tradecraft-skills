# Bespoke explainers — reference

Worked choices, the diagram and page how-tos, and the tested video recipe for [`SKILL.md`](SKILL.md). Every
example is invented.

## Choosing the rung: worked cases

| the reader needs to understand… | rung | why not the rung below |
|---|---|---|
| why a team chose one queue library over another | prose | there is no structure to show; it is an argument |
| how six services call each other after a refactor | diagram, from a script that reads the service configs | prose lists the calls but hides the shape; the model's memory of the calls may be stale |
| why a cache served a balance from before a transfer | HTML page: load, transfer, reload, with a toggle for the fix | a diagram shows the parts but not the moment the stale entry wins; the reader has to make it happen |
| how a retry storm builds after one slow dependency | video: the queue grows, retries multiply, the dependency falls over | a page could simulate it, but the point is the build-up over time, which motion shows and a static state cannot |
| a ten-step release procedure | prose, as an STE-style procedure | a diagram of a straight line of steps adds nothing |

## Diagrams

### Mermaid, rendered and looked at

```bash
mmdc -i flow.mmd -o flow.svg -b transparent -I flow
```

- `-I` sets the SVG's id. **Give every diagram on one page its own id**: the CLI's default id is the same
  each time, and two inlined diagrams with one id share arrowheads and styles, so one draws wrongly.
- Check the bundled Mermaid version with `npm ls -g mermaid`. The CLI tested here bundles Mermaid 12.1.0,
  while Obsidian and Typora bundled 11.13.0 when portable-markdown last checked them. A clean CLI render of a
  diagram meant for an editor is strong evidence, not proof. Open it in the editor when it matters.
- The output embeds its fonts as data, so one diagram is about 200 KB and loads nothing from the network.
- Mermaid's automatic layout is weak past a dozen nodes: edges cross and labels collide. Split the diagram,
  or move to a computed layout.

### SVG written directly

Write it when the diagram is small and its placement is the point. The failures are all visual, so render it
and look at it at its real size.

- Set a `viewBox` and keep every element inside it.
- Put every label inside its box, or in a legend. Free-floating labels collide.
- Route an arrow around any box it would cross, with an L-shaped path.
- Give every connector `fill="none"`. A path without it fills black.
- Use `currentColor`, or colours defined for both light and dark backgrounds, so it reads in dark mode.

### Large graphs: a computed layout (documented, not run)

For dozens of nodes, have the model (or a script) write only the nodes and edges, and let a layout engine
place them: Graphviz `dot -Tsvg graph.dot -o graph.svg`, or ELK running inside the HTML page with the library
inlined. Neither was installed for the proof run. Treat this row as guidance until someone renders one.

### Real structure: generate it

When the diagram shows something that exists (imports between modules, tables and foreign keys, which job
calls which), write a short script that reads the source and prints Mermaid or DOT. Then spot-check three
edges by hand. The script is the source to keep, and the diagram is regenerated from it.

## HTML pages

**Prompt shape:** "Build one self-contained HTML file that answers: <question>. Inline all CSS and JavaScript
and embed the data. Load nothing from the network. Two to four controls, each changing something visible. A
first line saying it is generated and what it was checked against. Works at phone width and in dark mode."

**Failure modes:**

| looks like | is |
|---|---|
| works for you, blank for the reader | a CDN script or web font that the reader's network blocks, or that is gone a year later |
| a control does nothing when opened from disk | `fetch()` of a local file, which browsers block on `file://` |
| state is lost or shared oddly | `localStorage` on `file://`, which browsers treat inconsistently; keep state in memory |
| one of two diagrams draws wrongly | two inlined SVGs with the same element ids |
| unreadable at night | colours set for a light background only |

**Check:** open the file from disk; confirm that the browser's network panel shows zero requests; use every
control once; look at it at phone width and in dark mode. (The proof page in the record below passed all of
these. A preview pane that shows local files as static snapshots cannot run the controls, so serve the folder
on `localhost` to click through it.)

## The video recipe

Proven on macOS. Copy the four files below into one folder and run the commands in order.

### Install

```bash
brew install cairo pkgconf                 # pycairo has no wheel for Apple silicon; it builds against these
python3.12 -m venv ~/.venvs/explainers     # or: uv venv --python 3.12 ~/.venvs/explainers
~/.venvs/explainers/bin/pip install manim kokoro-onnx soundfile   # or: uv pip install -p ~/.venvs/explainers ...
```

Keep the environment at a **short path**, such as the one above (see the espeak-ng pitfall). Python 3.12
was tested. A separate virtual environment per voice also works, because the scene never imports the voice.
No ffmpeg binary is needed, because Manim's PyAV dependency carries its own. A LaTeX install is
needed only for `MathTex`/`Tex`, so use `Text` and shapes unless the subject needs equations.
`manim checkhealth` reports both; its "manim is not on your PATH" warning only means the environment is not
activated.

**Voice files** (Kokoro, about 120 MB) come from the `kokoro-onnx` project's release
`model-files-v1.0`: `kokoro-v1.0.int8.onnx` (92 MB) and `voices-v1.0.bin` (28 MB).

```bash
mkdir -p ~/.cache/kokoro && cd ~/.cache/kokoro
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```

### Voices

| voice | licence | footprint | 4 lines took | notes |
|---|---|---|---|---|
| **Kokoro** via `kokoro-onnx` (default) | MIT wrapper, Apache-2.0 weights | 128 MB environment + 120 MB files | 15 s | the default for its permissive licence; compare voices by ear |
| Piper via `piper-tts` | GPL-3.0 engine; the tested voice is MIT | 147 MB environment + 63 MB voice | 4 s | fastest; `python -m piper.download_voices en_US-lessac-medium` |
| macOS `say` | system voice; read its terms before publishing | none | under 5 s | for drafts and for proving the timing |
| a paid voice (for example ElevenLabs) | the vendor's terms | an SDK | not run | key from the environment only; see below |

### `beats.json`: the script, one line per beat

```json
[
  "A queue is a line of items. A new item joins at the back.",
  "The program always takes the next item from the front of the line, never from the back.",
  "So the first item that joins is the first item that leaves.",
  "This order is called first in, first out. Use a queue when the order is important."
]
```

### `voice.py`: text in, one WAV per beat out

```python
"""Narration: one WAV per beat, plus manifest.json with each beat's duration.

Usage: python voice.py <say|kokoro|piper|elevenlabs> beats.json audio/
The scene reads only the WAVs and the manifest, so it never knows which voice made them.
"""
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

ESPEAK_PATH_LIMIT = 158  # longer and espeak-ng exits, naming a path on the package's build machine


def check_espeak_path(data_path):
    override = os.environ.get("ESPEAK_DATA_PATH", "")
    if len(str(data_path)) > ESPEAK_PATH_LIMIT and not 0 < len(override) <= ESPEAK_PATH_LIMIT:
        sys.exit(f"espeak-ng cannot use its data path ({len(str(data_path))} characters, limit "
                 f"{ESPEAK_PATH_LIMIT}). Create the virtual environment at a shorter path, or link the "
                 f"folder to a short path and point ESPEAK_DATA_PATH at the link:\n"
                 f"  ln -s {data_path} ~/.espeak-ng-data && export ESPEAK_DATA_PATH=~/.espeak-ng-data")


def say(text, out):
    subprocess.run(["say", "-o", str(out), "--file-format=WAVE", "--data-format=LEI16@22050", text], check=True)


def kokoro(text, out):
    import espeakng_loader
    import soundfile
    from kokoro_onnx import Kokoro
    check_espeak_path(espeakng_loader.get_data_path())
    model = Kokoro(os.environ["KOKORO_MODEL"], os.environ["KOKORO_VOICES"])
    samples, rate = model.create(text, voice=os.environ.get("KOKORO_VOICE", "af_heart"), lang="en-us")
    soundfile.write(out, samples, rate, subtype="PCM_16")


def piper(text, out):
    import piper as piper_pkg
    check_espeak_path(Path(piper_pkg.__file__).parent / "espeak-ng-data")
    subprocess.run([sys.executable, "-m", "piper", "-m", os.environ["PIPER_MODEL"], "-f", str(out)],
                   input=text.encode(), check=True, capture_output=True)


def elevenlabs(text, out):
    if not os.environ.get("ELEVENLABS_API_KEY"):
        sys.exit("The elevenlabs voice reads ELEVENLABS_API_KEY from the environment, and it is unset. "
                 "Set it in your own shell before running, or choose a local voice. "
                 "There is no fallback: a different voice would change the video.")
    raise NotImplementedError("Documented, not run: add the vendor SDK's text-to-speech call here.")


VOICES = {"say": say, "kokoro": kokoro, "piper": piper, "elevenlabs": elevenlabs}


def main(voice, beats_file, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").unlink(missing_ok=True)  # a failed run must not leave the last run's timings
    manifest = []
    for i, text in enumerate(json.loads(Path(beats_file).read_text())):
        wav = out_dir / f"beat{i}.wav"
        VOICES[voice](text, wav)
        with wave.open(str(wav)) as w:
            manifest.append({"text": text, "wav": wav.name, "seconds": w.getnframes() / w.getframerate()})
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"{len(manifest)} beats, {sum(b['seconds'] for b in manifest):.1f} s of speech")


if __name__ == "__main__":
    main(*sys.argv[1:4])
```

### `scene.py`: the animation, timed to the audio

```python
"""Render: manim -qm scene.py Explainer   (reads audio/manifest.json written by voice.py)"""
import json
from pathlib import Path

from manim import (BLUE, DOWN, GREEN, LEFT, RIGHT, UP, YELLOW, FadeIn, Scene, Square, Text,
                   VGroup, Write)

AUDIO = Path(__file__).parent / "audio"
PAD = 0.4   # silence after each beat; check.py assumes the same
TAIL = 0.5  # hold after the last beat, so its audio is never cut


class Explainer(Scene):
    def construct(self):
        beats = json.loads((AUDIO / "manifest.json").read_text())
        ends, t = [], 0.0
        for b in beats:
            t += b["seconds"] + PAD
            ends.append(t)  # absolute targets, so frame rounding cannot accumulate

        def beat(i, *steps):
            """Start beat i's audio, play its animation steps, then hold until beat i's absolute end."""
            self.add_sound(str(AUDIO / beats[i]["wav"]))
            for animations, run_time in steps:
                self.play(*animations, run_time=run_time)
            if ends[i] > self.time:
                self.wait(ends[i] - self.time)

        items = VGroup(*[Square(0.9).set_fill(BLUE, 0.6) for _ in range(3)]).arrange(RIGHT, buff=0.3)
        front = Text("front", font_size=28).next_to(items, DOWN).align_to(items, LEFT)
        back = Text("back", font_size=28).next_to(items, DOWN).align_to(items, RIGHT)
        new = Square(0.9).set_fill(GREEN, 0.6).move_to(RIGHT * 6)
        beat(0, ([FadeIn(items), FadeIn(front), FadeIn(back)], 1.0),
                ([new.animate.next_to(items, RIGHT, buff=0.3), back.animate.shift(RIGHT * 1.2)], 1.0))
        beat(1, ([items[0].animate.set_fill(YELLOW, 0.9)], 0.6))
        rest = VGroup(*items[1:], new)
        beat(2, ([items[0].animate.shift(LEFT * 3).set_opacity(0)], 1.2),
                ([rest.animate.shift(LEFT * 1.2), back.animate.shift(LEFT * 1.2)], 0.8))
        beat(3, ([Write(Text("first in, first out", font_size=44).to_edge(UP))], 1.5))
        self.wait(TAIL)
```

### `check.py`: check the render, not just the exit code

```python
"""Check a render: python check.py <video.mp4> audio/manifest.json
Uses PyAV, which Manim installs, so no ffmpeg binary is needed. Exits 1 if the video fails a check."""
import json
import sys
from pathlib import Path

import av
import numpy as np

PAD, TAIL = 0.4, 0.5  # must match scene.py
video, manifest = sys.argv[1], json.loads(Path(sys.argv[2]).read_text())
starts, t = [], 0.0
for b in manifest:
    starts.append(t)
    t += b["seconds"] + PAD
planned = t + TAIL
failures = []

with av.open(video) as c:
    v = next(s for s in c.streams if s.type == "video")
    has_audio = any(s.type == "audio" for s in c.streams)
    fps = float(v.average_rate)
    duration = c.duration / av.time_base
print(f"video {v.codec_context.name} {v.codec_context.width}x{v.codec_context.height} {fps:g} fps; audio "
      f"{'present' if has_audio else 'MISSING'}; duration {duration:.2f} s (planned {planned:.2f} s)")
if not has_audio:
    sys.exit("FAIL: no audio stream")
if abs(duration - planned) > 0.5:
    failures.append(f"duration is {duration - planned:+.2f} s from plan")

with av.open(video) as c:
    frames = [f for f in c.decode(audio=0)]
rate = frames[0].sample_rate
samples = np.concatenate([f.to_ndarray().mean(axis=0) for f in frames])
step = int(rate * 0.02)
rms = np.sqrt(np.convolve(samples ** 2, np.ones(step) / step, mode="same"))[::step]
loud = rms > rms.max() * 0.05
onsets = [i * 0.02 for i in range(len(loud)) if loud[i] and (i < 13 or not loud[i - 13:i].any())]
tolerance = 1 / fps + 0.1
for i, want in enumerate(starts):  # a pause inside a beat is an onset too, so take the nearest
    got = min(onsets, key=lambda o: abs(o - want))
    flag = "" if abs(got - want) <= tolerance else "  <-- late or early"
    print(f"beat {i}: planned {want:6.2f} s, heard {got:6.2f} s ({got - want:+.2f}){flag}")
    if flag:
        failures.append(f"beat {i} starts {got - want:+.2f} s from plan")

stem = Path(video).with_suffix("")
with av.open(video) as c:
    for i, s in enumerate(starts):
        target = s + min(1.5, manifest[i]["seconds"])
        c.seek(int(target / av.time_base))  # lands on the keyframe before the target, so decode forward
        frame = next(f for f in c.decode(video=0) if f.time >= target)
        frame.to_image().save(f"{stem}-beat{i}.png")
print(f"frames: {stem}-beat0.png ... look at each one")
if failures:
    sys.exit("FAIL: " + "; ".join(failures))
print("OK")
```

### Run

```bash
cd <the folder holding the four files>
export KOKORO_MODEL=~/.cache/kokoro/kokoro-v1.0.int8.onnx KOKORO_VOICES=~/.cache/kokoro/voices-v1.0.bin
~/.venvs/explainers/bin/python voice.py kokoro beats.json audio
~/.venvs/explainers/bin/manim -qm scene.py Explainer          # -ql while iterating; -qh for the final
~/.venvs/explainers/bin/python check.py media/videos/scene/720p30/Explainer.mp4 audio/manifest.json
```

Then open every `Explainer-beatN.png` that `check.py` wrote, and watch the video once with sound.

### Pitfalls: what it looks like, and what it is

| looks like | is |
|---|---|
| `Error processing file '/Users/runner/work/.../espeak-ng-data/phontab'` and the process exits | Kokoro's and Piper's bundled espeak-ng cannot use a data path longer than 158 characters. It falls back to the path on the machine that built the package. Put the environment at a short path. Or link the bundled `espeak-ng-data` folder itself (not its parent) to a short path and point the variable at the link: `ln -s <path>/espeak-ng-data ~/.espeak-ng-data` and `export ESPEAK_DATA_PATH=~/.espeak-ng-data`. `voice.py` checks this first and prints the exact command. |
| `pip install manim` fails at "Dependency lookup for cairo" | pycairo is building from source, and pkg-config is missing: `brew install cairo pkgconf` |
| the video has no sound, or sound only in parts | rendering with `-s` or with animations skipped: `add_sound` does nothing for skipped sections |
| narration drifts later and later | each beat was timed relative to the last instead of to an absolute end time, so frame rounding accumulates |
| the old narration plays after an edit | the voice step failed and the scene read the previous manifest; `voice.py` deletes the manifest before it starts so this cannot happen silently |
| `ShowCreation`, `TexMobject` or `from manimlib import *` errors | ManimGL names in a Manim CE scene: use `Create`, `MathTex`/`Text` and `from manim import ...` |
| `SyntaxWarning: invalid escape sequence` from `pydub`, or Manim's `WARNING Some options were not used` | harmless noise: the first from a Manim dependency on newer Python, the second from Manim's own video writer |
| a voice-over plugin asks for an API key and writes `.env` | `manim-voiceover`'s paid-voice services prompt for a missing key and save it in plain text to `./.env` (and read `ELEVEN_API_KEY`, not the SDK's `ELEVENLABS_API_KEY`). An agent must never answer that prompt; the recipe above does not use the plugin. |
| a paid voice still says the key is missing after you set it | the ElevenLabs SDK reads `ELEVENLABS_API_KEY` as a default argument when it is imported: set it before Python starts |
| a number is read wrongly ("2026" as "two zero two six", "p95" as "p ninety-five") | the voice reads the text as written: spell numbers and abbreviations the way they should be spoken |

### The proof-run record

| item | result |
|---|---|
| machine | Apple-silicon Mac, macOS 27.0.1, Python 3.12.13, `uv` virtual environments |
| install | `pkgconf` was the one missing system package; pycairo 1.29.2 built from source in 5 s once it was present |
| Manim environment | 259 MB (Manim CE 0.21.0, pycairo 1.29.2, ManimPango 0.7.0, PyAV 19.0.1, numpy 2.5.3) |
| sample | 4 beats, about 18.5 s at 1280×720, 30 fps, H.264 with AAC; render took about 6 s |
| timing | every beat started within 0.07 s of plan (Kokoro), 0.10 s (Piper) and 0.05 s (`say`); duration within 0.03 s |
| re-flow | lengthening line 2 by 1.7 s moved every later beat by the same amount, still within 0.04 s |
| fail-loud | a stale manifest, a long espeak path and an unset paid-voice key each stopped the run with a message naming the cause |
| HTML | one page with a hand-written SVG, a Mermaid sequence diagram from `mmdc` 12.0.0 and three controls: zero network requests, no console errors, every control behaved as described |
| reproduction | a second agent, given only this page, rebuilt the sample in a new folder: `check.py` passed, every beat within 0.07 s, all four frames matched their lines. Its one guess (how to shorten the espeak path) is now spelt out in `voice.py`'s message and the pitfalls table |
| not run | the paid voice's call; Graphviz and ELK; Linux and Windows |
