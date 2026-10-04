#!/usr/bin/env python3
"""Build the fictional fixture folder "Alex Personal" (run once on macOS; the result is committed and frozen).

Needs macOS with swiftc (for render.swift) and sips. Every person and organisation is invented. What each file is
for is listed in build.md. Rebuilding changes some bytes (PDF and PNG metadata); the committed files are the
baseline, so rebuild only on purpose and regenerate the expected outputs in the same commit.

    python3 build.py [--out <dir>]                   default: this directory
    python3 build.py --prepared-only [--out <dir>]   rewrite only the prepared records in an existing fixture

The prepared records are what a prepared folder carries in `_Audit/` beyond the rationale: an extract record and a
card per live document, and the wiki's acceptance record. `--prepared-only` rewrites them from `PREPARED` and the
wiki as committed, on any machine (standard-library Python and the tools beside this skill); the full build writes
them last. A change to a wiki page or to `PREPARED` is followed by `--prepared-only` in the same commit.
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.realpath(os.path.join(HERE, "..", "..", "tools"))
FOLDER = "Alex Personal"
WIKI = FOLDER + " Wiki"
ZIP_DATE = (2024, 1, 1, 0, 0, 0)


def w(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(path, mode, **({} if mode == "wb" else {"encoding": "utf-8"})) as f:
        f.write(data)


def render(tool, *args):
    subprocess.run([tool] + list(args), check=True)


# ---------------------------------------------------------------- a PDF whose spaces decode as ")"

def broken_layer_pdf(lines):
    content = "BT /F1 12 Tf 72 720 Td 16 TL\n" + "".join("(%s) '\n" % l.replace("(", "\\(").replace(")", "\\)")
                                                        for l in lines) + "ET\n"
    cmap = """/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<00> <FF>
endcodespacerange
1 beginbfchar
<20> <0029>
endbfchar
1 beginbfrange
<21> <7E> <0021>
endbfrange
endcmap
CMapName currentdict /CMapName get /CMapResource defineresource pop
end
end
"""
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> "
        "/Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding /ToUnicode 6 0 R >>",
        "<< /Length %d >>\nstream\n%sendstream" % (len(content), content),
        "<< /Length %d >>\nstream\n%sendstream" % (len(cmap), cmap),
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(("%d 0 obj\n%s\nendobj\n" % (i, o)).encode("latin-1"))
    xref = out.tell()
    out.write(("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode())
    for off in offsets:
        out.write(("%010d 00000 n \n" % off).encode())
    out.write(("trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)).encode())
    return out.getvalue()


# ---------------------------------------------------------------- iWork .iwa (Snappy literal + protobuf)

def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def field_bytes(num, data):
    return varint((num << 3) | 2) + varint(len(data)) + data


def snappy_literal(data):
    out = bytearray(varint(len(data)))
    pos = 0
    while pos < len(data):
        chunk = data[pos:pos + 65536]
        n = len(chunk) - 1
        if n < 60:
            out.append(n << 2)
        elif n < 256:
            out += bytes([60 << 2, n])
        else:
            out += bytes([61 << 2]) + n.to_bytes(2, "little")
        out += chunk
        pos += len(chunk)
    return bytes(out)


def iwa(texts):
    payload = b"".join(field_bytes(i + 1, t.encode("utf-8")) for i, t in enumerate(texts))
    info = varint(1 << 3) + varint(1) + field_bytes(2, varint(1 << 3) + varint(1) + varint(3 << 3) + varint(len(payload)))
    raw = varint(len(info)) + info + payload
    comp = snappy_literal(raw)
    return bytes([0]) + len(comp).to_bytes(3, "little") + comp


def zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(zipfile.ZipInfo(name, ZIP_DATE), data)
    return buf.getvalue()


CT = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
      'content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')


def docx(paras):
    body = "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % p for p in paras)
    return zip_bytes([("[Content_Types].xml", CT), ("word/document.xml",
                      '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                      '<w:body>%s</w:body></w:document>' % body)])


def pptx(slides):
    files = [("[Content_Types].xml", CT)]
    for i, (text, note) in enumerate(slides, 1):
        files.append(("ppt/slides/slide%d.xml" % i, '<p:sld xmlns:a="a" xmlns:p="p"><a:p><a:t>%s</a:t></a:p></p:sld>'
                      % text))
        files.append(("ppt/notesSlides/notesSlide%d.xml" % i, '<p:notes xmlns:a="a" xmlns:p="p"><a:p><a:t>%s</a:t>'
                      '</a:p></p:notes>' % note))
    return zip_bytes(files)


def xlsx(rows):
    strings = sorted({c for r in rows for c in r if not c.replace(".", "").isdigit()})
    sst = "".join("<si><t>%s</t></si>" % s for s in strings)
    xml_rows = []
    for i, r in enumerate(rows, 1):
        cells = []
        for c in r:
            if c in strings:
                cells.append('<c t="s"><v>%d</v></c>' % strings.index(c))
            else:
                cells.append("<c><v>%s</v></c>" % c)
        xml_rows.append('<row r="%d">%s</row>' % (i, "".join(cells)))
    return zip_bytes([("[Content_Types].xml", CT), ("xl/sharedStrings.xml", "<sst>%s</sst>" % sst),
                      ("xl/worksheets/sheet1.xml", "<worksheet><sheetData>%s</sheetData></worksheet>"
                       % "".join(xml_rows))])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=HERE)
    ap.add_argument("--prepared-only", action="store_true", help="rewrite only the prepared records in _Audit/")
    a = ap.parse_args()
    root = os.path.join(a.out, FOLDER)
    if a.prepared_only:
        write_prepared(root)
        print("prepared", root)
        return
    if os.path.exists(root):
        shutil.rmtree(root)
    tmp = tempfile.mkdtemp(prefix="fixture_")
    tool = os.path.join(tmp, "render")
    subprocess.run(["swiftc", "-O", os.path.join(HERE, "render.swift"), "-o", tool], check=True)
    t = lambda *p: os.path.join(tmp, *p)  # noqa: E731
    R = lambda *p: os.path.join(root, *p)  # noqa: E731

    # scans (images with no text layer)
    render(tool, "image", t("passport.png"), "PASSPORT\nSurname: EXAMPLE\nGiven names: ALEX\nNationality: "
           "Freedonian\nPassport No. P1234567\nDate of issue 2021-07-15\nDate of expiry 2031-07-15")
    render(tool, "image", t("french.png"), "Cours de français, niveau B1\nÉcole d'Exemple, Paris\n"
           "Relevé de notes du trimestre\nCompréhension écrite : 16/20\nExpression orale : 14/20\n"
           "Le professeur recommande de passer au niveau B2 en septembre.")
    render(tool, "image", t("chinese.png"), "中文课程结业证书\n学生姓名：亚历克斯\n课程名称：中级汉语会话\n"
           "学习时间：二〇二三年九月至二〇二四年六月\n成绩：优秀\n特此证明，本学生已完成全部课程要求。")
    render(tool, "image", t("bill_scan.png"), "Electricity usage, page 2\nMeter reading 12 Feb 2024: 45210\n"
           "Meter reading 12 Mar 2024: 45530\nUnits used: 320\nAmount due: GBP 96.40 by 2024-04-01")
    render(tool, "image", t("photo.png"), "Beach")
    render(tool, "textpdf", t("statement.pdf"), "Example Bank plc\nStatement for Alex Example\nAccount 12345678, "
           "sort code 01-02-03\nPeriod 1 March 2024 to 31 March 2024\nOpening balance GBP 2,410.00\n"
           "Salary from Robin Trading Ltd GBP 3,200.00\nRent to Example Lettings GBP 1,450.00\n"
           "Closing balance GBP 4,160.00")
    render(tool, "textpdf", t("cover.pdf"), "Example Energy Ltd\nElectricity bill for Alex Example\n"
           "3 Example Road, Exampleton\nBill date 15 March 2024\nThe usage details are on page 2.")
    render(tool, "textpdf", t("lease.pdf"), "Lease renewal\nLandlord: Example Lettings\nTenant: Alex Example\n"
           "Property: 3 Example Road, Exampleton\nTerm: 1 May 2024 to 30 April 2025\nRent GBP 1,450 per month")
    render(tool, "textpdf", t("invoice.pdf"), "Invoice 2022-117 from Robin Trading Ltd to Alex Example\n"
           "Consulting, February 2022, GBP 800.00\nPaid 2022-03-01")
    for n in ("passport", "french", "chinese", "bill_scan"):     # scans as small greyscale JPEGs, then PDF
        subprocess.run(["sips", "-Z", "1100", "-m", "/System/Library/ColorSync/Profiles/Generic Gray Profile.icc",
                        "-s", "format", "jpeg", "-s", "formatOptions", "55", t(n + ".png"), "--out", t(n + ".jpg")],
                       check=True, capture_output=True)
    render(tool, "imagepdf", t("passport.pdf"), t("passport.jpg"))
    render(tool, "imagepdf", t("french.pdf"), t("french.jpg"))
    render(tool, "imagepdf", t("chinese.pdf"), t("chinese.jpg"))
    render(tool, "imagepdf", t("bill_page2.pdf"), t("bill_scan.jpg"))
    render(tool, "merge", t("bill.pdf"), t("cover.pdf"), t("bill_page2.pdf"))
    subprocess.run(["sips", "-Z", "400", "-s", "format", "jpeg", t("photo.png"), "--out", t("photo.jpg")],
                   check=True, capture_output=True)
    subprocess.run(["sips", "-Z", "200", "-s", "format", "jpeg", t("passport.png"), "--out", t("preview.jpg")],
                   check=True, capture_output=True)

    rd = lambda p: open(p, "rb").read()  # noqa: E731
    # 01 Identity: a passport scan and an application pack holding a copy
    w(R("01 Identity", "Passport scan.pdf"), rd(t("passport.pdf")))
    w(R("01 Identity", "Passport renewal 2021", "Passport scan.pdf"), rd(t("passport.pdf")))
    w(R("01 Identity", "Passport renewal 2021", "Application form.docx"), docx([
        "Passport renewal application for Alex Example", "Submitted 2021-05-02", "Previous passport P0987654"]))
    # 02 Finance: a clean text layer, a same-folder redundant copy, a broken text layer, iWork and Excel
    w(R("02 Finance", "Bank statement 2024-03.pdf"), rd(t("statement.pdf")))
    w(R("02 Finance", "Bank statement 2024-03 (1).pdf"), rd(t("statement.pdf")))
    w(R("02 Finance", "Tax", "Tax return 2023.pdf"), broken_layer_pdf([
        "Self assessment tax return 2022 to 2023", "Taxpayer: Alex Example, UTR 1234567890",
        "Employment income from Robin Trading Ltd: GBP 38,400", "Tax paid through PAYE: GBP 5,160",
        "Balance due by 31 January 2024: GBP 0", "Filed online on 12 December 2023"]))
    w(R("02 Finance", "Tax", "Budget.numbers"), zip_bytes([
        ("Index/Document.iwa", iwa(["Household budget for 2023 prepared by Alex Example",
                                    "Rent 1,450 per month and utilities about 150 per month"])),
        ("preview.jpg", rd(t("preview.jpg")))]))
    w(R("02 Finance", "Tax", "Budget final.xlsx"), xlsx([["Item", "Monthly"], ["Rent", "1450"],
                                                          ["Utilities", "150"], ["Savings", "400"]]))
    # 03 Home: a Pages package with its PDF export, a mixed PDF, name defects
    w(R("03 Home", "Lease renewal.pages", "Index", "Document.iwa"), iwa([
        "Lease renewal for 3 Example Road, signed by Alex Example",
        "The new term runs from 1 May 2024 to 30 April 2025 at 1,450 per month"]))
    w(R("03 Home", "Lease renewal.pages", "preview.jpg"), rd(t("preview.jpg")))
    w(R("03 Home", "Lease renewal.pdf"), rd(t("lease.pdf")))
    w(R("03 Home", "Lease notes .txt"), "Notes on the lease: ask Example Lettings about the boiler service.\n")
    w(R("03 Home", "Utilities ", "Electricity bill.pdf"), rd(t("bill.pdf")))
    # 04 Study: French and Chinese scans, office files, rtf
    study = {
        "Cours de français.pdf": rd(t("french.pdf")),
        "中文课程.pdf": rd(t("chinese.pdf")),
        "Slides.pptx": pptx([("Language learning plan for 2024", "Speak with Robin every week"),
                             ("Targets: B2 French and HSK 4 Chinese", "Exams in June")]),
        "Essay.docx": docx(["Essay: why learn a third language", "Written by Alex Example for the evening class",
                            "Learning a language changes how you see your own."]),
    }
    for name, data in study.items():
        w(R("04 Study", name), data)
    w(R("04 Study", "Notes.rtf"), "{\\rtf1\\ansi{\\fonttbl\\f0 Helvetica;}\\f0 Class notes: irregular verbs and "
      "measure words, reviewed with Robin Example.}\n")
    # 05 Archive: a parallel tree copied from 04 Study (redundant by folder similarity)
    for name, data in study.items():
        w(R("05 Archive", name), data)
    # 06 Work: one copy in an unrelated folder (a working copy)
    w(R("06 Work", "Essay.docx"), study["Essay.docx"])
    w(R("06 Work", "Contract.docx"), docx(["Employment contract between Robin Trading Ltd and Alex Example",
                                           "Start date 2022-05-01", "Notice period one month"]))
    # a root stray with a generic camera name; a file staged for another project
    w(R("IMG_0001.jpg"), rd(t("photo.jpg")))
    w(R("_Migrations", "Other Project", "02 Finance", "Old invoice.pdf"), rd(t("invoice.pdf")))
    os.makedirs(R("_Inbox"), exist_ok=True)

    write_rulebook_and_wiki(R)
    write_prepared(root)
    shutil.rmtree(tmp, True)
    print("built", root)


RULEBOOK = """# Alex Personal: rules for AI sessions

This file is the folder's rulebook. Every AI session working in this folder follows it. `CLAUDE.md` is the
authority; `AGENTS.md` is a byte-identical copy. Edit `CLAUDE.md`, then copy it over `AGENTS.md`.

Owner: Alex Example. Answers recorded at the curation interview (fictional fixture).

## Who uses this folder

- Alex, and the AI OS worker. Nobody else.

## How far to reorganise

- Depth: **light**. Nothing moves, is renamed or is deleted without an approved row in
  `_Audit/plans/<date>/move-plan.csv`. Empty folders are kept.

## How new files arrive

- `_Inbox/` at the top is the drop point. The system files each new item inside this folder, by the wiki's
  routing, and says where it went. Files that may belong to another project are left to the owner's cross-project
  synthesis to propose moving; this folder never routes them elsewhere itself.

## Formats and packs

- Pages and Numbers are working formats; the system reads them directly.
- Packs: `01 Identity/Passport renewal 2021` is a submission record; copies inside it are never deleted.

## Identifiers

- Reference numbers are recorded in full. Passwords are never written anywhere.

## Where AI outputs go

- `Alex Personal Wiki/`: the wiki. `_Audit/`: the manifest, extracts, cards, plans, rationale.
  `_Migrations/<Project>/`: files the owner approved moving to another project.

### People and organisations

| Canonical | Also appears as | Who |
| --- | --- | --- |
| Alex Example | Alex, 亚历克斯 | owner of this folder |
| Robin Example | Robin | Alex's partner |
| Robin Trading Ltd | | Alex's employer |

## Reserved names at the top

`_Audit`, `_Inbox`, `_Migrations`, `Alex Personal Wiki`, `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.familyai`.
"""


def page(fm_sources, body, deadlines=None):
    fm = ["---", "provenance: derived", "last-updated: 2024-06-30", "status: current"]
    if fm_sources:
        fm.append("sources:")
        fm += ['  - "%s"' % s for s in fm_sources]
    if deadlines:
        fm.append("deadlines:")
        fm += ["  - {date: %s, note: %s}" % d for d in deadlines]
    return "\n".join(fm + ["---", body.strip(), ""])


def write_rulebook_and_wiki(R):
    w(R("CLAUDE.md"), RULEBOOK)
    w(R("AGENTS.md"), RULEBOOK)
    W = lambda *p: R(WIKI, *p)  # noqa: E731
    schema = """# 90 Schema

The constitution of Alex's wiki (fictional fixture).

## Readers and purpose

- Reader: Alex. It answers, most important first: what expires or is due; money in and out; where a document is.

## Layout

| Section | Pages | Professional lens | Kind |
| --- | --- | --- | --- |
| 00 Index | dashboard | chief of staff | fixed |
| 01 Deadlines | every forward date, rolled up | chief of staff | fixed, derived |
| 02 People | everyone who appears | personal assistant | fixed |
| 10 Identity | passport | immigration adviser | active |
| 20 Finance | Bank accounts; Cash position; Tax | private banker; CFO; chartered tax adviser | active |
| 30 Home | lease, bills | household manager | active |
| 40 Study | courses and certificates | academic registrar | history |
| 90 Schema | this page | librarian | fixed |
| 91 Log | append-only history | librarian | fixed |

## Page professionals

| Page | Professional | Deliverable | Tone |
| --- | --- | --- | --- |
| 20 Finance/20 Finance.md | private banker | finance overview | measured |
| 20 Finance/Bank accounts.md | private banker | accounts schedule | measured |
| 20 Finance/Cash position.md | CFO | cash note | numerate, brief |
| 20 Finance/Tax.md | chartered tax adviser | annual tax position letter | exact, dated |

## Routing

| Files under | Section and page |
| --- | --- |
| `01 Identity/` | 10 Identity |
| `02 Finance/Tax/` | 20 Tax |
| `02 Finance/` | 20 Bank accounts and Cash position |
| `03 Home/` | 30 Home |
| `04 Study/`, `05 Archive/` | 40 Study |
| `06 Work/` | 20 Tax (employment income) |
| `_Inbox/` | filed by the routing above |

## Page contracts

| Section (professional) | Reader | Questions, most important first | Fields every page carries |
| --- | --- | --- | --- |
| 10 Identity (immigration adviser) | Alex | 1. When does the passport expire? 2. Which numbers would an application need? | number, issue date, expiry, scan path |
| 20 Finance (private banker; CFO; chartered tax adviser) | Alex | 1. Is anything due? 2. What came in and went out? 3. What is the tax position? | account, period, balances, tax year, amounts |
| 30 Home (household manager) | Alex | 1. Where does Alex live and on what terms? 2. What bills are due? | address, landlord, term, rent, bills |
| 40 Study (academic registrar) | Alex | 1. Which courses and certificates are held? 2. Where are they? | course, school, dates, result, path |

## Writing rules

- Identifiers in full. Source files named by path in backticks, never linked. UK English, no em dashes.
"""
    w(W("90 Schema", "90 Schema.md"), page([], schema))
    w(W("91 Log", "91 Log.md"), page([], "# 91 Log\n\n## [2024-06-30] build | Wiki built from the fixture folder."))
    w(W("00 Index", "00 Index.md"), page([], """# 00 Index

> [!note]
> **Needs attention.** The electricity bill of GBP 96.40 is due by 2024-04-01.

Waiting to be filed: `IMG_0001.jpg` at the top of the folder (a beach photo).

| Section | Holds |
| --- | --- |
| [10 Identity](../10%20Identity/10%20Identity.md) | passport |
| [20 Finance](../20%20Finance/20%20Finance.md) | bank, cash, tax |
| [30 Home](../30%20Home/30%20Home.md) | lease and bills |
| [40 Study](../40%20Study/40%20Study.md) | language courses |
| [02 People](../02%20People/02%20People.md) | who is who |
| [01 Deadlines](../01%20Deadlines/01%20Deadlines.md) | coming dates |
"""))
    w(W("01 Deadlines", "01 Deadlines.md"), page([], """# Deadlines

_File-derived deadlines, rolled up deterministically from page frontmatter: do not hand-edit, regenerated each run. (Calendar events live in `Coming Events`.)_

## Upcoming

- **2025-04-30**: Lease ends ([30 Home](../30%20Home/30%20Home.md))
- **2031-07-15**: Passport P1234567 expires ([10 Identity](../10%20Identity/10%20Identity.md))
"""))
    w(W("02 People", "02 People.md"), page([], """# 02 People

| Name | Also | Who |
| --- | --- | --- |
| Alex Example | Alex, 亚历克斯 | the owner |
| Robin Example | Robin | Alex's partner |
| Robin Trading Ltd | | Alex's employer |
| Example Lettings | | the landlord |
"""))
    w(W("10 Identity", "10 Identity.md"), page(["01 Identity/Passport scan.pdf"], """# 10 Identity

Alex holds passport P1234567, valid until 15 Jul 2031. No action is due.

| Document | Number | Issued | Expires | Scan |
| --- | --- | --- | --- | --- |
| Passport | P1234567 | 2021-07-15 | 2031-07-15 | `01 Identity/Passport scan.pdf` |

```mermaid
gantt
    title Passport validity
    dateFormat YYYY-MM-DD
    section Passport
    P1234567 :2021-07-15, 2031-07-15
```

| Section | Label | Start | End | Source |
| --- | --- | --- | --- | --- |
| Passport | P1234567 | 2021-07-15 | 2031-07-15 | `01 Identity/Passport scan.pdf` |

The 2021 renewal pack is kept whole in `01 Identity/Passport renewal 2021/` (2 files: the scan copy and
`01 Identity/Passport renewal 2021/Application form.docx`, which names the previous passport P0987654).
""", deadlines=[("2031-07-15", '"Passport P1234567 expires"')]))
    w(W("20 Finance", "20 Finance.md"), page([], """# 20 Finance

- [Bank accounts](Bank%20accounts.md): the current account.
- [Cash position](Cash%20position.md): money in and out in March 2024.
- [Tax](Tax.md): the 2022 to 2023 return and the budget.
"""))
    w(W("20 Finance", "Bank accounts.md"), page(["02 Finance/Bank statement 2024-03.pdf"], """# Bank accounts

One current account at Example Bank plc, number 12345678, sort code 01-02-03 (`02 Finance/Bank statement
2024-03.pdf`; an identical copy sits beside it as `02 Finance/Bank statement 2024-03 (1).pdf`).

| Account | Sort code | Latest statement | Closing balance | Source |
| --- | --- | --- | --- | --- |
| 12345678 | 01-02-03 | March 2024 | GBP 4,160.00 | `02 Finance/Bank statement 2024-03.pdf` |

The March 2024 statement, from opening to closing balance:

```mermaid
xychart-beta
    title "Current account, March 2024 (GBP)"
    x-axis ["Opening balance", "Salary in", "Rent out", "Closing balance"]
    y-axis "GBP" 0 --> 4160.00
    bar [2410.00, 3200.00, 1450.00, 4160.00]
```

| Label | Value (GBP) | Source |
| --- | ---: | --- |
| Opening balance | 2410.00 | `02 Finance/Bank statement 2024-03.pdf` |
| Salary in | 3200.00 | `02 Finance/Bank statement 2024-03.pdf` |
| Rent out | 1450.00 | `02 Finance/Bank statement 2024-03.pdf` |
| Closing balance | 4160.00 | `02 Finance/Bank statement 2024-03.pdf` |
"""))
    w(W("20 Finance", "Cash position.md"), page(["02 Finance/Bank statement 2024-03.pdf",
                                                 "02 Finance/Tax/Budget final.xlsx"], """# Cash position

March 2024 closed GBP 1,750 higher than it opened: salary in, rent out.

Planned monthly spending from `02 Finance/Tax/Budget final.xlsx`:

```mermaid
pie title Planned monthly spending (GBP)
    "Rent" : 1450
    "Utilities" : 150
    "Savings" : 400
```

| Label | Value (GBP) | Source |
| --- | ---: | --- |
| Rent | 1450 | `02 Finance/Tax/Budget final.xlsx` |
| Utilities | 150 | `02 Finance/Tax/Budget final.xlsx` |
| Savings | 400 | `02 Finance/Tax/Budget final.xlsx` |
"""))
    w(W("20 Finance", "Tax.md"), page(["02 Finance/Tax/Tax return 2023.pdf", "06 Work/Contract.docx"], """# Tax

Nothing is due: the 2022 to 2023 return was filed on 12 Dec 2023 with a balance of GBP 0 (UTR 1234567890).

| Tax year | Employment income (GBP) | Tax paid (GBP) | Filed | Source |
| --- | --- | --- | --- | --- |
| 2022-23 | 38400 | 5160 | 2023-12-12 | `02 Finance/Tax/Tax return 2023.pdf` |

The employer is Robin Trading Ltd since 1 May 2022 (`06 Work/Contract.docx`; a copy of the study essay also sits
in `06 Work/Essay.docx`). The household budget is in `02 Finance/Tax/Budget.numbers`.
"""))
    w(W("30 Home", "30 Home.md"), page(["03 Home/Lease renewal.pdf", "03 Home/Utilities /Electricity bill.pdf"],
                                      """# 30 Home

Alex rents 3 Example Road from Example Lettings until 30 Apr 2025 at GBP 1,450 a month.

```mermaid
timeline
    title Home
    2024-05-01 : Lease renewed to 2025-04-30
    2024-03-15 : Electricity bill GBP 96.40
```

| Date | Label | Source |
| --- | --- | --- |
| 2024-05-01 | Lease renewed to 2025-04-30 | `03 Home/Lease renewal.pdf` |
| 2024-03-15 | Electricity bill GBP 96.40 | `03 Home/Utilities /Electricity bill.pdf` |

| Record | Date | Path |
| --- | --- | --- |
| Lease renewal (Pages original and PDF export) | 2024-05-01 | `03 Home/Lease renewal.pages`, `03 Home/Lease renewal.pdf` |
| Electricity bill | 2024-03-15 | `03 Home/Utilities /Electricity bill.pdf` |
| Lease notes | | `03 Home/Lease notes .txt` |
""", deadlines=[("2025-04-30", '"Lease ends"')]))
    w(W("40 Study", "40 Study.md"), page([], """# 40 Study

French to B1 and a Chinese intermediate certificate, 2023 to 2024.

| Course | Result | Path |
| --- | --- | --- |
| French B1 | 16/20 written, 14/20 oral | `04 Study/Cours de français.pdf` |
| Chinese intermediate | excellent | `04 Study/中文课程.pdf` |

| Folder | Files | What it holds |
| --- | --- | --- |
| `04 Study/` | 5 | certificates, slides, essay, notes |
| `05 Archive/` | 4 | copies of the study files |
"""))
    # Each page's one professional (common.page_voice) and its questions: its section's contract's, in order, or
    # for a fixed section the page's own.
    finance = "1. Is anything due? 2. What came in and went out? 3. What is the tax position?"
    blocks = []
    for rel, prof, asks in [
            ("00 Index/00 Index.md", "chief of staff", "1. What needs attention now? 2. Where is each matter kept?"),
            ("01 Deadlines/01 Deadlines.md", "chief of staff", "1. What is due next? 2. What falls due later?"),
            ("02 People/02 People.md", "personal assistant",
             "1. Who is each person or organisation? 2. Which other names do they appear under?"),
            ("10 Identity/10 Identity.md", "immigration adviser",
             "1. When does the passport expire? 2. Which numbers would an application need?"),
            ("20 Finance/20 Finance.md", "private banker", finance),
            ("20 Finance/Bank accounts.md", "private banker", finance), ("20 Finance/Cash position.md", "CFO", finance),
            ("20 Finance/Tax.md", "chartered tax adviser", finance),
            ("30 Home/30 Home.md", "household manager",
             "1. Where does Alex live and on what terms? 2. What bills are due?"),
            ("40 Study/40 Study.md", "academic registrar",
             "1. Which courses and certificates are held? 2. Where are they?"),
            ("90 Schema/90 Schema.md", "librarian", "1. How is the wiki divided? 2. Where does each file go?"),
            ("91 Log/91 Log.md", "librarian", "1. What changed, and when?")]:
        blocks.append("### %s\n- Reader and use: Alex, checking this matter.\n- Professional lens: %s; questions "
                      "answered in order: %s\n- Shape: as the Schema sets out\n- Changed from the previous page: "
                      "first version\n- Left out or flagged: nothing\n" % (rel, prof, asks))
    w(R("_Audit", "wiki-rationale.md"), "# Wiki rationale\n\n" + "\n".join(blocks))
    rb_sha = hashlib.sha256(RULEBOOK.encode("utf-8")).hexdigest()
    w(R(".familyai", "rulebook.json"), json.dumps({
        "version": 1, "rulebook_sha256": rb_sha, "inbox": "_Inbox", "migrations_dir": "_Migrations",
        "wiki_dir": WIKI, "reserved": [], "depth": "light", "packs": ["01 Identity/Passport renewal 2021"],
        "working_formats": [".pages", ".numbers"], "active": ["01 Identity", "02 Finance", "03 Home"],
        "finished": ["04 Study", "05 Archive"],
        "people": [{"name": "Alex Example", "also": ["Alex", "亚历克斯"], "who": "owner of this folder"},
                   {"name": "Robin Example", "also": ["Robin"], "who": "Alex's partner"},
                   {"name": "Robin Trading Ltd", "also": [], "who": "Alex's employer"}],
        "identifiers": "stated", "boundaries": [], "folder_description": "Alex Example's personal papers: identity, "
        "money, home and language study.", "exclude": [], "keep_empty_folders": True,
        "ocr_languages": ["zh-Hans", "zh-Hant", "en-GB", "fr-FR"]}, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- the prepared records (_Audit/)

PREPARED_AT = "2024-06-30T12:00:00+0000"  # the frozen clock of the expected outputs
ACCEPTED_ON = "2024-06-30"
AUTHOR, REVIEWER = "model-a", "model-b"  # fictional: the model that wrote the pages, and the other that reviewed them


def card(doc_type, party, parties, doc_date, title, summary, facts, category, language, sensitive, look="",
         proposed_name="", confidence="high"):
    """A card in tools/schemas/card.json's shape, fields in the order templates/card-instructions.md lists them."""
    dates, amounts, refs = facts
    return {"doc_type": doc_type, "party": party, "parties": parties, "doc_date": doc_date, "title": title,
            "summary": summary, "key_facts": {"dates": dates, "amounts": amounts, "reference_numbers": refs},
            "category": category, "language": language, "sensitive": sensitive, "confidence": confidence,
            "look": look, "proposed_name": proposed_name}


# Each live document by the path the audit keeps for it (its canonical copy): its pages as extraction reads them
# (tier and text; a scan's text is what main() renders) and its card, written as templates/card-instructions.md asks.
PREPARED = {
    "01 Identity/Passport renewal 2021/Application form.docx": (
        [("text_layer", "Passport renewal application for Alex Example\nSubmitted 2021-05-02\n"
                        "Previous passport P0987654")],
        card("Form", "Alex Example", [], "2021-05-02", "Passport renewal application, 2021",
             "Alex's application to renew the passport, submitted on 2021-05-02. It names the previous passport, "
             "P0987654, and is kept in the 2021 renewal pack.",
             (["submitted 2021-05-02"], [], ["previous passport P0987654"]), "Identity & Immigration", "en", True)),
    "01 Identity/Passport scan.pdf": (
        [("local_ocr", "PASSPORT\nSurname: EXAMPLE\nGiven names: ALEX\nNationality: Freedonian\nPassport No. P1234567\n"
                       "Date of issue 2021-07-15\nDate of expiry 2031-07-15")],
        card("Passport Scan", "Alex Example", [], "2021-07-15", "Passport scan, P1234567",
             "A scan of Alex's Freedonian passport P1234567, issued on 2021-07-15 and valid until 2031-07-15.",
             (["issue 2021-07-15", "expiry 2031-07-15"], [], ["passport P1234567"]), "Identity & Immigration", "en",
             True)),
    "02 Finance/Bank statement 2024-03.pdf": (
        [("text_layer", "Example Bank plc\nStatement for Alex Example\nAccount 12345678, sort code 01-02-03\n"
                        "Period 1 March 2024 to 31 March 2024\nOpening balance GBP 2,410.00\n"
                        "Salary from Robin Trading Ltd GBP 3,200.00\nRent to Example Lettings GBP 1,450.00\n"
                        "Closing balance GBP 4,160.00")],
        card("Bank Statement", "Alex Example", ["Example Bank plc", "Robin Trading Ltd", "Example Lettings"],
             "2024-03-31", "Current account statement, March 2024",
             "The Example Bank plc current account statement for March 2024: salary in from Robin Trading Ltd, rent "
             "out to Example Lettings, closing at GBP 4,160.00.",
             (["period 2024-03-01 to 2024-03-31"], ["opening GBP 2,410.00", "salary GBP 3,200.00",
                                                    "rent GBP 1,450.00", "closing GBP 4,160.00"],
              ["account 12345678 sort code 01-02-03"]), "Finance & Tax", "en", True)),
    "02 Finance/Tax/Budget final.xlsx": (
        [("text_layer", "Item\tMonthly\nRent\t1450\nUtilities\t150\nSavings\t400")],
        card("Spreadsheet", "Alex Example", [], "", "Household budget, final",
             "Planned monthly spending: rent 1450, utilities 150 and savings 400.",
             ([], ["rent 1450 per month", "utilities 150 per month", "savings 400 per month"], []), "Finance & Tax",
             "en", False, look="It appears to be an export of Budget.numbers under another name.")),
    "02 Finance/Tax/Budget.numbers": (
        [("text_layer", "Household budget for 2023 prepared by Alex Example\n\n"
                        "Rent 1,450 per month and utilities about 150 per month")],
        card("Spreadsheet", "Alex Example", [], "2023", "Household budget, 2023",
             "Alex's household budget for 2023: rent 1,450 a month and utilities about 150 a month.",
             (["2023"], ["rent 1,450 per month", "utilities about 150 per month"], []), "Finance & Tax", "en", False)),
    "02 Finance/Tax/Tax return 2023.pdf": (
        [("local_ocr", "Self assessment tax return 2022 to 2023\nTaxpayer: Alex Example, UTR 1234567890\n"
                       "Employment income from Robin Trading Ltd: GBP 38,400\nTax paid through PAYE: GBP 5,160\n"
                       "Balance due by 31 January 2024: GBP 0\nFiled online on 12 December 2023")],
        card("Tax Return", "Alex Example", ["Robin Trading Ltd"], "2023-12-12",
             "Self assessment tax return 2022 to 2023",
             "The 2022 to 2023 return, filed online on 2023-12-12: employment income from Robin Trading Ltd, tax "
             "paid through PAYE and nothing left to pay.",
             (["filed 2023-12-12", "balance due by 2024-01-31"],
              ["employment income GBP 38,400", "tax paid GBP 5,160", "balance due GBP 0"], ["UTR 1234567890"]),
             "Finance & Tax", "en", True)),
    "03 Home/Lease notes .txt": (
        [("text_layer", "Notes on the lease: ask Example Lettings about the boiler service.")],
        card("Notes", "Alex Example", ["Example Lettings"], "", "Notes on the lease",
             "A reminder to ask Example Lettings about the boiler service.", ([], [], []), "Home & Household", "en",
             False)),
    "03 Home/Lease renewal.pages": (
        [("text_layer", "Lease renewal for 3 Example Road, signed by Alex Example\n\n"
                        "The new term runs from 1 May 2024 to 30 April 2025 at 1,450 per month")],
        card("Tenancy Agreement", "Alex Example", ["Example Lettings"], "2024-05-01",
             "Lease renewal, 3 Example Road (Pages original)",
             "The signed lease renewal for 3 Example Road: the new term runs from 2024-05-01 to 2025-04-30 at 1,450 a "
             "month.", (["term 2024-05-01 to 2025-04-30"], ["rent 1,450 per month"], []), "Home & Household", "en",
             False, look="It appears to be the same lease as Lease renewal.pdf, its export.")),
    "03 Home/Lease renewal.pdf": (
        [("text_layer", "Lease renewal\nLandlord: Example Lettings\nTenant: Alex Example\n"
                        "Property: 3 Example Road, Exampleton\nTerm: 1 May 2024 to 30 April 2025\n"
                        "Rent GBP 1,450 per month")],
        card("Tenancy Agreement", "Alex Example", ["Example Lettings"], "2024-05-01", "Lease renewal, 3 Example Road",
             "The lease renewal between Example Lettings and Alex for 3 Example Road, Exampleton: the term runs from "
             "2024-05-01 to 2025-04-30 at GBP 1,450 a month.",
             (["term 2024-05-01 to 2025-04-30"], ["rent GBP 1,450 per month"], []), "Home & Household", "en", False)),
    "03 Home/Utilities /Electricity bill.pdf": (
        [("text_layer", "Example Energy Ltd\nElectricity bill for Alex Example\n3 Example Road, Exampleton\n"
                        "Bill date 15 March 2024\nThe usage details are on page 2."),
         ("local_ocr", "Electricity usage, page 2\nMeter reading 12 Feb 2024: 45210\nMeter reading 12 Mar 2024: 45530\n"
                       "Units used: 320\nAmount due: GBP 96.40 by 2024-04-01")],
        card("Invoice", "Alex Example", ["Example Energy Ltd"], "2024-03-15", "Electricity bill, March 2024",
             "The Example Energy Ltd electricity bill for 3 Example Road, dated 2024-03-15: 320 units used and GBP "
             "96.40 due by 2024-04-01.", (["bill date 2024-03-15", "due 2024-04-01"], ["GBP 96.40"], []),
             "Home & Household", "en", False)),
    "04 Study/Cours de français.pdf": (
        [("local_ocr", "Cours de français, niveau B1\nÉcole d'Exemple, Paris\nRelevé de notes du trimestre\n"
                       "Compréhension écrite : 16/20\nExpression orale : 14/20\n"
                       "Le professeur recommande de passer au niveau B2 en septembre.")],
        card("Transcript", "Alex Example", ["École d'Exemple"], "", "French B1 term transcript (Cours de français)",
             "The term transcript of the B1 French course at École d'Exemple, Paris: written comprehension 16/20, "
             "speaking 14/20. The teacher recommends moving up to B2 in September.", ([], [], []), "Language Study",
             "fr", False)),
    "04 Study/Notes.rtf": (
        [("text_layer", "Class notes: irregular verbs and measure words, reviewed with Robin Example.")],
        card("Lecture Notes", "Alex Example", ["Robin Example"], "", "Class notes",
             "Class notes on irregular verbs and measure words, reviewed with Robin.", ([], [], []), "Language Study",
             "en", False)),
    "04 Study/Slides.pptx": (
        [("text_layer", "Language learning plan for 2024\n\n[notes]\nSpeak with Robin every week"),
         ("text_layer", "Targets: B2 French and HSK 4 Chinese\n\n[notes]\nExams in June")],
        card("Presentation", "Alex Example", ["Robin Example"], "2024", "Language learning plan for 2024",
             "Alex's language plan for 2024: speak with Robin every week, aim for B2 French and HSK 4 Chinese, with "
             "the exams in June.", (["exams 2024-06"], [], []), "Language Study", "en", False)),
    "04 Study/中文课程.pdf": (
        [("local_ocr", "中文课程结业证书\n学生姓名：亚历克斯\n课程名称：中级汉语会话\n学习时间：二〇二三年九月至二〇二四年六月\n"
                       "成绩：优秀\n特此证明，本学生已完成全部课程要求。")],
        card("Certificate", "Alex Example", [], "2024-06", "Chinese course completion certificate (中文课程结业证书)",
             "A certificate that Alex (亚历克斯) completed the intermediate spoken Chinese course (中级汉语会话), "
             "September 2023 to June 2024, graded excellent (优秀).", (["course 2023-09 to 2024-06"], [], []),
             "Language Study", "zh", False)),
    "06 Work/Contract.docx": (
        [("text_layer", "Employment contract between Robin Trading Ltd and Alex Example\nStart date 2022-05-01\n"
                        "Notice period one month")],
        card("Contract", "Alex Example", ["Robin Trading Ltd"], "2022-05-01", "Employment contract, Robin Trading Ltd",
             "Alex's employment contract with Robin Trading Ltd, starting on 2022-05-01, with one month's notice.",
             (["start 2022-05-01"], [], []), "Work & Career", "en", False)),
    "06 Work/Essay.docx": (
        [("text_layer", "Essay: why learn a third language\nWritten by Alex Example for the evening class\n"
                        "Learning a language changes how you see your own.")],
        card("Essay", "Alex Example", [], "", "Essay: why learn a third language",
             "Alex's essay for the evening class on why to learn a third language.", ([], [], []), "Language Study",
             "en", False)),
    "IMG_0001.jpg": (
        [("photo", "Beach")],
        card("Photo", "Unknown", [], "", "Beach photo", "A photo of a beach; the only text in it is the word Beach.",
             ([], [], []), "Photos", "none", False, look="A stray at the top of the folder: decide where it belongs.",
             proposed_name="Unknown - Photo Beach.jpg", confidence="low")),
    "_Migrations/Other Project/02 Finance/Old invoice.pdf": (
        [("text_layer", "Invoice 2022-117 from Robin Trading Ltd to Alex Example\n"
                        "Consulting, February 2022, GBP 800.00\nPaid 2022-03-01")],
        card("Invoice", "Robin Trading Ltd", ["Alex Example"], "2022-02", "Consulting invoice 2022-117",
             "An invoice from Robin Trading Ltd to Alex for consulting in February 2022, GBP 800.00, paid on "
             "2022-03-01.", (["paid 2022-03-01"], ["GBP 800.00"], ["invoice 2022-117"]), "Business", "en", False)),
}


def tool(args):
    """Run a tool beside this skill; a failure stops the build with the tool's own message."""
    r = subprocess.run([sys.executable, os.path.join(TOOLS, args[0])] + args[1:], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("%s %s failed (%d): %s" % (args[0], args[1], r.returncode, (r.stderr or r.stdout).strip()))
    return r.stdout


def write_prepared(root):
    """Write the prepared records into `root`/_Audit/: per document of PREPARED, `extract/<id>.json` (as extract.py
    writes one) and `cards/<id>.json` (as cards.py writes one), the id being the document's content id; then
    `wiki-acceptance.json`, through `wiki.py accept`: every page accepted in the owner's lens and its professional's,
    by REVIEWER, a model other than its author, at the page's bytes as committed. Earlier records are removed first."""
    sys.path.insert(0, TOOLS)
    import common  # noqa: E402 (the tools' content id: the audit's, for a package too)
    audit = os.path.join(root, "_Audit")
    for d in ("extract", "cards"):
        shutil.rmtree(os.path.join(audit, d), True)
    for name in ("wiki-acceptance.json", "wiki-acceptance.json.lock"):
        if os.path.exists(os.path.join(audit, name)):
            os.remove(os.path.join(audit, name))
    for rel, (pages, fields) in PREPARED.items():
        eid = common.content_id(os.path.join(root, *rel.split("/")))
        ext = os.path.splitext(rel)[1].lower()
        tiers = {}
        for tier, _text in pages:
            tiers[tier] = tiers.get(tier, 0) + 1
        record = {"id": eid, "path": rel, "class": "iwork" if ext in (".pages", ".numbers") else
                  "image" if ext == ".jpg" else "document", "status": "photo" if "photo" in tiers else "ok",
                  "page_count": len(pages), "tiers": tiers, "chars": sum(len(t) for _tier, t in pages),
                  "extractor": "fixture", "extracted_at": PREPARED_AT,
                  "pages": [{"n": n, "tier": tier, "text": text} for n, (tier, text) in enumerate(pages, 1)]}
        w(os.path.join(audit, "extract", eid + ".json"), json.dumps(record, ensure_ascii=False))
        meta = {"model": "fixture", "via": "fixture", "batch": "fixture", "created_at": PREPARED_AT}
        w(os.path.join(audit, "cards", eid + ".json"),
          json.dumps(dict({"id": eid}, **fields, card_meta=meta), ensure_ascii=False, indent=1))
    tmp = tempfile.mkdtemp(prefix="fixture_accept_")
    try:
        settings = os.path.join(tmp, "settings")  # a compiled Schema for the review, kept out of the fixture
        os.makedirs(settings)
        shutil.copy(os.path.join(root, ".familyai", "rulebook.json"), settings)
        base = ["--root", root, "--work", os.path.join(tmp, "work"), "--settings-dir", settings]
        tool(["settings.py", "compile"] + base)
        wiki = os.path.join(root, WIKI)
        pages = sorted(os.path.relpath(os.path.join(d, f), wiki).replace(os.sep, "/")
                       for d, _ds, fs in os.walk(wiki) for f in fs if f.endswith(".md"))
        record = os.path.join(tmp, "wiki-acceptance.json")  # recorded here, so the lock accept leaves stays here
        for n, page in enumerate(pages):
            for lens in ("owner", "professional"):
                reply = os.path.join(tmp, "reply-%d-%s.json" % (n, lens))
                w(reply, json.dumps({"page": page, "lens": lens, "verdict": "accepted", "findings": []},
                                    ensure_ascii=False))
                tool(["wiki.py", "accept"] + base + ["--reply", reply, "--author-model", AUTHOR, "--reviewer-model",
                                                     REVIEWER, "--date", ACCEPTED_ON, "--out", record])
        shutil.copy(record, os.path.join(audit, "wiki-acceptance.json"))
    finally:
        shutil.rmtree(tmp, True)


if __name__ == "__main__":
    main()
