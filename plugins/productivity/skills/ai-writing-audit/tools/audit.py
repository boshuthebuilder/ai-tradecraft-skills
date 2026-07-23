#!/usr/bin/env python3
"""AI writing audit. Scan a document for the patterns catalogued in REFERENCE.md.

Usage:
    python3 tools/audit.py path/to/file.md
    python3 tools/audit.py path/to/file.pdf
    python3 tools/audit.py path/to/file.txt
    python3 tools/audit.py path/to/script.py   # extracts string literals

Grades every hit into one of three evidence bands and prints a cluster verdict:
    Band 1 (near-decisive)  leaked citation/tool markup; very low sentence-length variance
    Band 2 (fires in clusters)  negative parallelism, summaries, triplets, sycophancy, ...
    Band 3 (contributory only)  vocabulary, hedging, transitions, flattery, em-dash density

Triage only. The scanner cannot judge rhythm nuance, brand voice, or load-bearing
formatting. Read the document yourself after the scan.
"""
from __future__ import annotations

import io
import re
import statistics
import sys
from pathlib import Path

# Band 1 — near-decisive. A single hit means the text was generated. These are leaked
# rendering tokens, not style; verify each was not a legitimate code sample.
ARTIFACTS: list[tuple[str, str]] = [
    ("ChatGPT citation markup",    r"oaicite|contentReference|turn\d+(?:search|view|news|image)\d+"),
    ("Gemini citation markup",     r"\[cite:\s*\d+\]|\[cite_start\]|\[/?span_\d+\]|\[start_span\]"),
    ("Grok citation markup",       r"grok_card|grok_render_citation_card_json"),
    ("Perplexity upload markup",   r"ppl-ai-file-upload|attached_file"),
]

# Band 2 — fires in clusters. Three or more distinct patterns stacked means AI-shaped.
CLUSTER: list[tuple[str, str]] = [
    ("negative parallelism: not only/but",
                                   r"\bnot\s+only\b[^.]{1,80}\bbut\b"),
    ("negative parallelism: not X, (it/but) Y",
                                   r"\b(?:it|this|that|we|you)(?:'s|'re|\s+(?:is|are|was|were))\s+not\s+[^.,;!?]{1,45}?[.,]\s+(?:it|but|this|that|we|you)\b"),
    ("rule of three (x, y, and z)",
                                   r"\b(\w+),\s+(\w+),\s+and\s+(\w+)\b"),
    ("compulsive summary",
                                   r"\bin\s+conclusion\b|\bin\s+summary\b|\bto\s+summari[sz]e\b|(?:^|\.\s+)overall,"),
    ("trailing -ing analysis",
                                   r",\s+\w+ing\s+(?:the|a|an|its|their|how|that|to)\b[^.]{1,80}\."),
    ("false range: from X to Y",
                                   r"\bfrom\s+[a-z]+(?:\s+[a-z]+)?\s+to\s+[a-z]+\b"),
    ("sycophancy opener",
                                   r"(?:^|\.\s+)(?:great\s+question|good\s+question|you'?re\s+absolutely\s+right|certainly!|i'?d\s+be\s+happy\s+to|let'?s\s+break\s+(?:this|it)\s+down|here'?s\s+the\s+kicker|the\s+truth\s+is\s+simple)"),
]

# Band 3 — contributory only. Never conclude from these alone; they count toward a cluster.
WEAK: list[tuple[str, str]] = [
    # Vocabulary is era-tagged in REFERENCE.md §10 and is the most perishable layer.
    ("vocab (fading GPT-4 era)",
                                   r"\bdelv\w*\b|\bintricate\w*\b|\btapestry\b|\bpivotal\b|\bunderscor\w*\b"),
    ("vocab (still overused)",
                                   r"\bfoster\w*\b|\bseamless\b|\bleverag\w*\b|\bmyriad\b|\bplethora\b|\brealm\b|\btestament\s+to\b"),
    ("hedging cliché",
                                   r"it\s+(?:is|'s)\s+(?:important\s+to\s+note|worth\s+noting)|(?:^|\.\s+)(?:notably|importantly),"),
    ("stock transition",
                                   r"(?:^|\.\s+)(?:furthermore|moreover|additionally),|that\s+being\s+said"),
    ("flattery / puffery",
                                   r"\bfascinat\w*\b|\bremarkable\b|\bcaptivat\w*\b|\btransformative\b|\bgroundbreaking\b|\bparadigm\s+shift\b"),
    ("double-hyphen dash",
                                   r"\w+--\w+"),
]


def extract_text(path: Path) -> str:
    """Return body text from the file. Supports md, txt, py, pdf."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import pypdf  # type: ignore
        except ImportError as e:
            sys.exit(
                "PDF input requires pypdf. Install with `pip3 install --break-system-packages pypdf`.\n"
                f"Original error: {e}"
            )
        reader = pypdf.PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    text = path.read_text(encoding="utf-8", errors="replace")

    if suffix == ".py":
        # Extract string literals so we audit prose embedded in code.
        triple = re.findall(r'"""(.*?)"""', text, flags=re.DOTALL)
        triple += re.findall(r"'''(.*?)'''", text, flags=re.DOTALL)
        single = re.findall(r'"([^"\n]*)"', text)
        single += re.findall(r"'([^'\n]*)'", text)
        return "\n".join(triple + single)

    return text


def scan(text: str, patterns: list[tuple[str, str]]) -> list[tuple[str, int, list[str]]]:
    """Return [(name, count, samples)] for patterns that hit, sorted by descending count."""
    results: list[tuple[str, int, list[str]]] = []
    for name, pattern in patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if matches:
            samples = []
            for m in matches[:3]:
                if isinstance(m, tuple):
                    samples.append(" ".join(s for s in m if s))
                else:
                    samples.append(str(m))
            results.append((name, len(matches), samples))
    results.sort(key=lambda r: -r[1])
    return results


def burstiness(text: str) -> tuple[float | None, int]:
    """Sentence-length standard deviation and sentence count. See REFERENCE.md §2.

    Human academic prose runs ~8.2; GPT-4o ~4.1; Claude ~5.3. Low variance is the
    strongest stylistic tell. Returns (None, n) when there are too few sentences to judge.
    """
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    lengths = [len(s.split()) for s in sentences if len(s.split()) >= 3]
    if len(lengths) < 8:
        return None, len(lengths)
    return statistics.pstdev(lengths), len(lengths)


def emdash_density(text: str) -> tuple[int, float]:
    """Em-dash count and rate per 100 words. See REFERENCE.md §14 (contributory, gameable)."""
    count = text.count("—") + len(re.findall(r"&mdash;", text, flags=re.IGNORECASE))
    words = max(1, len(text.split()))
    return count, count / words * 100


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[1]).expanduser()
    if not path.is_file():
        print(f"audit.py: {path} is not a file", file=sys.stderr)
        return 2

    try:
        text = extract_text(path)
    except Exception as e:  # noqa: BLE001 - triage tool, report and move on
        print(f"audit.py: failed to read {path}: {e}", file=sys.stderr)
        return 1

    words = len(text.split())
    artifacts = scan(text, ARTIFACTS)
    cluster = scan(text, CLUSTER)
    weak = scan(text, WEAK)
    sd, n_sent = burstiness(text)
    em_count, em_rate = emdash_density(text)
    low_rhythm = sd is not None and sd < 5.0

    out = io.StringIO()
    out.write("AI writing audit\n")
    out.write(f"file:    {path}\n")
    out.write(f"length:  {len(text)} chars, ~{words} words\n")
    if sd is not None:
        out.write(f"rhythm:  sentence-length SD {sd:.1f} over {n_sent} sentences "
                  f"({'LOW — monotone, an AI tell' if low_rhythm else 'varied'})\n")
    else:
        out.write(f"rhythm:  too few sentences ({n_sent}) to judge burstiness\n")
    out.write(f"em-dash: {em_count} ({em_rate:.2f} per 100 words"
              f"{'; high' if em_rate > 1.0 else ''})\n\n")

    def dump(title: str, hits: list[tuple[str, int, list[str]]]) -> None:
        if not hits:
            return
        out.write(f"{title}\n")
        for name, count, samples in hits:
            sample_str = " | ".join(s[:40] for s in samples)
            out.write(f"  {count:>3}  {name:<38}  {sample_str}\n")
        out.write("\n")

    dump("Band 1 — near-decisive (leaked markup):", artifacts)
    dump("Band 2 — fires in clusters:", cluster)
    dump("Band 3 — contributory only:", weak)

    # Verdict, mirroring REFERENCE.md "Scoring".
    if artifacts:
        verdict = "AI-shaped — leaked citation/tool markup (verify it is not a code sample)"
    elif len(cluster) >= 3 or (len(cluster) >= 2 and low_rhythm):
        verdict = f"AI-shaped — {len(cluster)} Band-2 patterns clustered" + (
            " plus monotone rhythm" if low_rhythm else "")
    elif low_rhythm:
        verdict = "possibly AI-shaped — monotone rhythm; read for sentence variety before judging"
    elif cluster or weak:
        verdict = "inconclusive — scattered contributory hits; a person writes these too. Read for rhythm."
    else:
        verdict = "no tells found. Read the document yourself for tone and rhythm."
    out.write(f"VERDICT: {verdict}\n\n")

    out.write("Triage only. Rewrite to reduce cluster density, not to zero any single pattern.\n")
    out.write("The scanner cannot see rhythm nuance, brand voice, or load-bearing bold. See REFERENCE.md.\n")
    print(out.getvalue())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
