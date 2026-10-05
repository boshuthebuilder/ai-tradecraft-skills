# The fixture folder

`Alex Personal/` is a fictional folder (Alex and Robin Example, Robin Trading Ltd, Example Lettings) built once on
macOS by `build.py` with `render.swift`. The committed bytes are the baseline; `../expected/` holds the frozen
outputs of the deterministic tools, regenerated only on purpose with `python3 ../regen_expected.py --update`
(add `--with-extract` on macOS with `tools/page-ocr` built), in a commit that says why.

| File | What it exercises |
| --- | --- |
| `02 Finance/Bank statement 2024-03.pdf` | a clean PDF text layer |
| `02 Finance/Bank statement 2024-03 (1).pdf` | a redundant copy in the same folder (a delete candidate) |
| `02 Finance/Tax/Tax return 2023.pdf` | a broken text layer (spaces decode as `)`), so the page is OCR'd |
| `03 Home/Utilities /Electricity bill.pdf` | a mixed PDF (typed page, then a scanned page); its folder name ends in a space (hygiene) |
| `04 Study/Cours de français.pdf`, `04 Study/中文课程.pdf` | image-only scans in French and in Chinese (language routing) |
| `01 Identity/Passport scan.pdf` and `01 Identity/Passport renewal 2021/` | a scan, and an application pack holding a copy (kind `pack`, never deleted) |
| `03 Home/Lease renewal.pages` | an iWork package directory read through `iwa.py`, with a matching PDF export (converted, `stem`) |
| `02 Finance/Tax/Budget.numbers` | a zipped iWork file with only a near-named export (`Budget final.xlsx`, `stem_near`, still unconverted) |
| `04 Study/*.docx`, `*.pptx`, `*.rtf`, `02 Finance/Tax/*.xlsx` | office readers and textutil |
| `05 Archive/` | a parallel tree copied from `04 Study/` (redundant by folder similarity; an overlapping home) |
| `06 Work/Essay.docx` | a copy in an unrelated folder (a working copy; it also wins canonical by being the shortest path) |
| `03 Home/Lease notes .txt` | a space before the extension (hygiene) |
| `IMG_0001.jpg` | a root stray with a generic camera name, read as a photo |
| `_Migrations/Other Project/02 Finance/Old invoice.pdf` | a file staged for another project (`migrating`) |
| `CLAUDE.md`, `AGENTS.md`, `.familyai/rulebook.json` | the rulebook, its identical copy and its settings twin |
| `Alex Personal Wiki/` | a small wiki: Schema with Layout, Page professionals, Routing and Page contracts (with a Reader column) tables; pages by different professionals (a CFO's cash note beside personal pages); Mermaid `gantt`, `xychart-beta` bar, `pie` and `timeline`, each rendered by `wiki.py chart` from figures its cited file states, with its data table beside it (no line chart: no file here states three dated figures); a callout with its marker alone on its line |
| `_Audit/wiki-rationale.md` | one five-line rationale block per page, naming its professional and its questions |
| `_Audit/extract/`, `_Audit/cards/` | an extract record and a card per live document, by content id (`PREPARED`) |
| `_Audit/wiki-acceptance.json` | every page accepted in both lenses by another model (`wiki.py accept`) |

With these prepared records `readiness.py` finds only the file staged in the migrations folder, which a folder
must have cleared before hand-off (the readiness tests clear it first, with its record and card). They follow the
files and the wiki: after changing a wiki page or `PREPARED`, run `python3 build.py --prepared-only` (any machine) and commit what it writes
with the change.

The folder is about 470 KB on disk; scans are greyscale JPEG pages inside PDFs to keep it small.
