# pre-onboarding tools

Standard-library Python (3.9+) plus one Swift helper for Apple Vision OCR. Generic and settings-driven: nothing
here names a folder, a person or a project. Every tool takes `--root <folder>`; most also take `--settings-dir`
(default `<root>/.familyai`), `--work` (state outside the folder, default `~/.ai-os-pre-onboarding/<folder>`) and
`--read-only-root` (refuse any write inside the folder, used with `--out` elsewhere to prove a tool). Every tool
that takes `--root` refuses a stale settings twin before it reads or writes anything, except `settings.py check` and
`readiness.py`, which report it, and `settings.py compile`, which is how a stale `wiki-schema.json` is fixed; the
twins' formats are in [`../references/settings.md`](../references/settings.md).

| Tool | What it does |
| --- | --- |
| `audit.py` | Deterministic audit: manifest `/2`, `AUDIT.md`, `summary.json`; merges with the previous manifest |
| `plan.py` | Curation plans: `light`, `migrate`, `return`, `approve`, `rmdirs`, `check`, `execute`, `prove` |
| `extract.py` | Full text per page: text layer, broken-layer detection, Vision OCR, tesseract, office and iWork readers |
| `iwa.py` | iWork text without the apps (Snappy-compressed protobuf, walked generically) |
| `page_ocr.swift` | Apple Vision OCR helper; build with `swiftc -O page_ocr.swift -o page-ocr` |
| `vision.py` | Model vision lane for pages local OCR could not read |
| `engines.py` | agy and codex adapters: stdin prompts, sandboxed, tool use refused, typed outcomes, credential guard |
| `isolation.py` | Isolation terms scan and per-engine canary |
| `cards.py` | One card per document; deterministic whole-chunk join; contamination guard |
| `refs.py` | Deterministic repair of truncated reference numbers from each card's own source |
| `settings.py` | Compile `wiki-schema.json` from the Schema's tables; check both twins and the rulebook's facts |
| `wiki.py` | Evidence bundles, wiki checks, page moves with link rewriting |
| `readiness.py` | Hand-off readiness, including the hand-off contract |
| `common.py` | Shared: settings loading, guarded writes, package hash, JSON parsing, token estimate |

The package hash (sha256 over an iWork package's members in walk order, directories and files sorted, each member
contributing relative path, NUL, member sha256 hex, newline) is shared with any deployment that reads the manifest.
