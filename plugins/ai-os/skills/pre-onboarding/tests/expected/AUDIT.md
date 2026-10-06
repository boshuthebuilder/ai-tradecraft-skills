# Audit: Alex Personal

Generated 2024-06-30T12:00:00Z by `ai-os-pre-onboarding-audit/1` from `manifest.json` (schema `family-ai-preprocess-manifest/2`). Derived file: regenerate, never edit.

## Summary

| Measure | Count |
| --- | --- |
| Items on disk (iWork packages count as one) | 25 |
| Unique contents (manifest entries) | 18 |
| Total size | 0.3 MB |
| Class `document` | 15 |
| Class `image` | 1 |
| Class `iwork` | 2 |
| Class `archive` | 0 |
| Class `email` | 0 |
| Class `other` | 0 |
| Count-only entries (images over 25 MB) | 0 |
| Excluded from reading (rulebook `exclude`) | 0 |
| Departed entries | 0 |

## Top-level folders

| Folder | Items | Unique | Size | Newest change | Changed in last 12 months |
| --- | --- | --- | --- | --- | --- |
| (root) | 1 | 1 | 0.0 MB | 2024-06-01 | 1 |
| 01 Identity | 3 | 2 | 0.1 MB | 2024-06-01 | 3 |
| 02 Finance | 5 | 4 | 0.0 MB | 2024-06-01 | 5 |
| 03 Home | 4 | 4 | 0.1 MB | 2024-06-01 | 4 |
| 04 Study | 5 | 5 | 0.1 MB | 2024-06-01 | 5 |
| 05 Archive | 4 | 4 | 0.1 MB | 2024-06-01 | 4 |
| 06 Work | 2 | 2 | 0.0 MB | 2024-06-01 | 2 |
| _Migrations | 1 | 1 | 0.0 MB | 2024-06-01 | 1 |

## Duplicate groups (6)

Copy kinds: canonical 6, redundant 4, working copy 2, pack 1. Redundant copies hold 0.1 MB.

Largest redundant copies (up to 40):

- `05 Archive/Cours de français.pdf` (0.0 MB, entry `e6286ec60509`)
- `05 Archive/中文课程.pdf` (0.0 MB, entry `41b91fb91d3d`)
- `02 Finance/Bank statement 2024-03 (1).pdf` (0.0 MB, entry `f69a0211da79`)
- `05 Archive/Slides.pptx` (0.0 MB, entry `a3a90b859cd2`)

## Overlapping homes (1)

- 04 Study <> 05 Archive: 4 shared contents

## Generic names (1)

- (root): 1

## Unconverted formats (1)

1 iWork items already have a confidently matched export. Near matches, where a `convert` row would name the candidate:

- `02 Finance/Tax/Budget.numbers` near `02 Finance/Tax/Budget final.xlsx`

## Hygiene defects (2)

- space_before_extension: `03 Home/Lease notes .txt`
- whitespace_in_name: `03 Home/Utilities /Electricity bill.pdf`

## Root strays (1)

- `IMG_0001.jpg`

## Migrating out (1)

Files staged under `_Migrations/<Project>/` for another project; they leave this folder once that project takes them.

- Other Project: `_Migrations/Other Project/02 Finance/Old invoice.pdf`

## Not audited (0)

Top-level names the walk skipped, with the items under each. A reserved name is skipped by the audit and by every tool; a leading `_` marks a system folder, which the deployment also never reads. Anything the owner needs prepared does not belong under one.

- none

## Hidden files, symlinks, cloud placeholders

Hidden 0, symlinks 0, cloud-only placeholders 0, not downloaded 0.

## Drift since the last pass

Baseline pass: no previous manifest.
