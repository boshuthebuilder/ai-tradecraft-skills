"""Extraction on the deterministic tiers: the quality gate, broken-layer detection, the office zip readers, the iWork
reader and the record statuses, on fixture copies and small synthetic files.

Tiers that need a local tool (pdftotext, tesseract, macOS Vision OCR, textutil, LibreOffice) are tested against the
fixture only where the tool is installed; elsewhere the test is skipped and its reason names the tier. The per-page
tier logic itself is tested everywhere, with those tools stood in for.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
FIXTURE = os.path.join(HERE, "fixture", "Alex Personal")
EXPECTED = os.path.join(HERE, "expected", "extract.json")
NOW = 1719748800
sys.path.insert(0, TOOLS)
import common  # noqa: E402
import extract  # noqa: E402
import iwa  # noqa: E402

FOUR = ["zh-Hans", "zh-Hant", "en-GB", "fr-FR"]     # the fixture folder's ocr_languages

HAVE = {n: bool(extract.which(n)) for n in ("pdftotext", "pdfinfo", "pdftoppm", "tesseract", "textutil", "soffice")}
_OCR_BIN = os.path.join(TOOLS, "page-ocr")
HAVE["page-ocr"] = bool(extract.which("page-ocr", _OCR_BIN if os.path.exists(_OCR_BIN) else None))
POPPLER = HAVE["pdftotext"] and HAVE["pdfinfo"]
DETERMINISTIC_TIERS = {"text_layer", "listing"}
PDF_TEXT_LAYER = "PDF text-layer tier: needs pdftotext and pdfinfo (poppler), not installed here"
VISION_OCR = "local OCR tier (macOS Vision): needs tools/page-ocr built from page_ocr.swift, pdftotext and pdftoppm"
TESSERACT_OCR = "local OCR tier (tesseract): needs tesseract, pdftotext and pdftoppm"
TEXTUTIL = "textutil tier (rtf, doc, odt, html): needs macOS textutil, not installed here"
ZH_CERTIFICATE = "中文课程结业证书，学生姓名：亚历克斯，课程名称：中级汉语会话，学习时间：二〇二三年九月至二〇二四年六月"
FRENCH = "Cours de français, niveau B1\nÉcole d'Exemple, Paris\nRelevé de notes du trimestre"
STATEMENT = ("Example Bank plc\nStatement for Alex Example\nOpening balance GBP 2,410.00\n"
             "Closing balance GBP 4,160.00")
GARBAGE = "~^|<>{}~^|<>{}~^|<>{} ~^|<>{}~^|<>{}"


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data.encode("utf-8") if isinstance(data, str) else data)


def run(tool, *args, now=NOW):
    """Run a tool with a frozen clock and every ResourceWarning an error; a file it leaves open fails the test."""
    env = dict(os.environ, PRE_ONBOARDING_NOW=str(now), PYTHONWARNINGS="error::ResourceWarning")
    r = subprocess.run([sys.executable, os.path.join(TOOLS, tool)] + list(args), capture_output=True, text=True,
                       env=env)
    if "ResourceWarning" in r.stderr:
        raise AssertionError("%s left a file open:\n%s" % (tool, r.stderr[-2000:]))
    return r.returncode, r.stdout, r.stderr


def tree_digest(root):
    h = hashlib.sha256()
    for d, ds, fs in os.walk(root):
        ds.sort()
        for f in sorted(fs):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode() + b"\0" + read(p, "rb") + b"\n")
    return h.hexdigest()


def view(rec):
    """A record as expected/extract.json holds it: text kept only on the deterministic tiers."""
    return {"status": rec["status"], "page_count": rec["page_count"], "tiers": [p["tier"] for p in rec["pages"]],
            "text": [p["text"] if p["tier"] in DETERMINISTIC_TIERS else None for p in rec["pages"]]}


def expected():
    return json.loads(read(EXPECTED))


def broken_tax_layer():
    """The text layer a PDF reader decodes from the fixture's tax return: its font maps the space to `)`."""
    pdf = read(os.path.join(FIXTURE, "02 Finance", "Tax", "Tax return 2023.pdf"), "rb").decode("latin-1")
    src, dst = re.search(r"beginbfchar\s*<([0-9A-F]{2})>\s*<([0-9A-F]{4})>", pdf).groups()
    lines = [s.replace("\\(", "(").replace("\\)", ")") for s in re.findall(r"\(((?:\\.|[^\\)])*)\) '", pdf)]
    return "\n".join(lines).replace(chr(int(src, 16)), chr(int(dst, 16))), "\n".join(lines)


# ------------------------------------------------------------------------ builders for synthetic office and iWork files

def zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data)
    return buf.getvalue()


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def field(num, data):
    return varint((num << 3) | 2) + varint(len(data)) + data


def snappy_literal(data):
    n = len(data) - 1
    head = bytes([n << 2]) if n < 60 else bytes([60 << 2, n]) if n < 256 else bytes([61 << 2]) + n.to_bytes(2, "little")
    return varint(len(data)) + head + data


def iwa_chunk(texts):
    """One Snappy-compressed .iwa archive holding one message whose fields are `texts`."""
    payload = b"".join(field(i + 1, t.encode("utf-8")) for i, t in enumerate(texts))
    info = varint(1 << 3) + varint(1) + field(2, varint(1 << 3) + varint(1) + varint(3 << 3) + varint(len(payload)))
    comp = snappy_literal(varint(len(info)) + info + payload)
    return bytes([0]) + len(comp).to_bytes(3, "little") + comp


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="extract_test_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def file(self, rel, data):
        p = os.path.join(self.tmp, rel)
        write(p, data)
        return p


# ------------------------------------------------------------------------ the quality gate and broken layers

class QualityGateTest(unittest.TestCase):
    def test_quality(self):
        self.assertEqual(extract.quality(""), 0.0)
        self.assertEqual(extract.quality("Rent GBP 1,450 (per month); paid!"), 1.0)
        self.assertEqual(extract.quality("ab~~"), 0.5)

    def test_a_clean_reading(self):
        self.assertTrue(extract.good(STATEMENT))
        self.assertTrue(extract.good(ZH_CERTIFICATE))
        self.assertTrue(extract.good(FRENCH, 0.45))

    def test_what_the_gate_refuses(self):
        cases = {
            "under 40 characters": "Example Bank plc statement",
            "low quality": STATEMENT + GARBAGE * 4,
            "low confidence": (STATEMENT, 0.44),
            "mostly punctuation": "- - - - - - - - - - ab - - - - - - - - - - - - - -",
            "no word": "1234 5678 9012 3456 7890 1234 5678 9012 3456",
            "too few Chinese characters": "二〇二三 二〇二四 二〇二五 二〇二六 2023 2024 2025 2026 2027 2028 2029",
        }
        for name, case in cases.items():
            with self.subTest(name):
                text, conf = case if isinstance(case, tuple) else (case, 1.0)
                self.assertFalse(extract.good(text, conf))


class BrokenLayerTest(unittest.TestCase):
    def test_the_fixture_tax_return(self):
        broken, clean = broken_tax_layer()
        self.assertIn("Self)assessment)tax)return", broken)
        self.assertTrue(extract.good(broken), "only the broken-layer check stops this page")
        self.assertTrue(extract.broken_layer(broken))
        self.assertFalse(extract.broken_layer(clean))

    def test_a_few_glued_marks_in_real_prose(self):
        self.assertFalse(extract.broken_layer("Self)assessment tax return"))                  # fewer than 5
        prose = " ".join(["Alex paid the rent on time and kept every receipt in the folder."] * 6)
        self.assertFalse(extract.broken_layer(prose + " Options 1)a 2)b 3)c 4)d 5)e 6)f."))   # under 30%
        self.assertTrue(extract.broken_layer("Options 1)a 2)b 3)c 4)d 5)e 6)f."))


# ------------------------------------------------------------------------ per-page tiers, with the local tools stood in

class StandInOcr:
    """Answers `page-ocr` would give, by language set."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def read(self, img, langs, timeout=300):
        self.calls.append(langs)
        return dict(self.answers.get(langs, {"text": "", "confidence": 0.0}))


def stand_in_tools(pages, count=True, render=True):
    """A replacement for extract.run: pdfinfo, pdftotext and pdftoppm as the fixture's tools would answer."""
    def fake(cmd, timeout):
        tool = os.path.basename(cmd[0])
        if tool == "pdfinfo":
            return ("Pages:          %d\n" % len(pages)) if count else "", 0, ""
        if tool == "pdftotext":
            return "\f".join(pages) + "\f", 0, ""
        if tool == "pdftoppm" and render:
            write(cmd[-1] + ".png", b"a rendered page")
        return "", 0, ""
    return fake


class PageTierTest(Tmp):
    def ctx(self, *present, ocr=None, langs=("en-GB",)):
        c = extract.Ctx(argparse.Namespace(ocr_bin=None), os.path.join(self.tmp, "root"),
                        os.path.join(self.tmp, "work"), os.path.join(self.tmp, "out"), langs)
        self.addCleanup(shutil.rmtree, c.tmp, True)
        c.bins = {n: ("/stand-in/" + n if n in present else None) for n in c.bins}
        c.ocr = ocr or extract.OCR(None)
        c.cur = "entry"
        return c

    def pdf(self, ctx, pages, **kw):
        with mock.patch.object(extract, "run", stand_in_tools(pages, **kw)):
            return extract.process(ctx, {"id": "entry", "current_path": "Scan.pdf", "class": "document"})

    def test_a_clean_layer_is_kept_and_a_broken_one_is_never_used(self):
        broken, _clean = broken_tax_layer()
        rec = self.pdf(self.ctx("pdftotext", "pdfinfo"), [STATEMENT, broken, ""])
        self.assertEqual([p["tier"] for p in rec["pages"]], ["text_layer", "none", "none"])
        self.assertEqual(rec["pages"][0]["text"], STATEMENT)
        self.assertEqual(rec["pages"][1]["text"], "")
        self.assertEqual(rec["pages"][1]["note"], "pdftoppm not available")
        self.assertEqual(rec["status"], "partial")
        self.assertEqual(rec["notes"], ["local OCR tier not available here: page-ocr, tesseract"])

    def test_pages_no_local_tier_reads(self):
        broken, _clean = broken_tax_layer()
        c = self.ctx("pdftotext", "pdfinfo", "pdftoppm")
        rec = self.pdf(c, [STATEMENT, broken, GARBAGE])
        self.assertEqual([p["tier"] for p in rec["pages"]], ["text_layer", "blank", "pending_vision"])
        self.assertEqual(rec["pages"][2]["queued"], "entry_00003.png")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "work", "vision_queue", "entry_00003.png")))
        self.assertEqual(rec["status"], "needs_vision")
        self.assertEqual(self.pdf(c, ["", "  \n "])["status"], "blank")
        self.assertEqual(self.pdf(c, [STATEMENT])["status"], "ok")
        self.assertNotIn("notes", self.pdf(c, [STATEMENT]))

    def test_a_page_that_does_not_render(self):
        rec = self.pdf(self.ctx("pdftotext", "pdfinfo", "pdftoppm"), [GARBAGE], render=False)
        self.assertEqual((rec["pages"][0]["tier"], rec["pages"][0]["note"], rec["status"]),
                         ("none", "render_failed", "partial"))

    def test_without_poppler_or_a_page_count(self):
        with self.assertRaisesRegex(RuntimeError, r"pdftotext/pdfinfo not available \(install poppler\)"):
            self.pdf(self.ctx(), [STATEMENT])
        with self.assertRaisesRegex(RuntimeError, "pdf unreadable"):
            self.pdf(self.ctx("pdftotext", "pdfinfo"), [""], count=False)
        rec = self.pdf(self.ctx("pdftotext", "pdfinfo"), [STATEMENT, STATEMENT], count=False)
        self.assertEqual(rec["page_count"], 2)

    def test_vision_passes_and_tesseract_languages(self):
        """Vision gets its own codes for the rulebook's (en-GB is read as en-US), tesseract its own, case aside."""
        self.assertEqual(extract.vision_passes(["en-GB"]), ("en-US", None))
        self.assertEqual(extract.vision_passes(["en-GB", "en-US", "EN-au"]), ("en-US", None))
        self.assertEqual(extract.vision_passes(["fr-CA", "de-AT", "es-MX"]), ("fr-FR,de-DE,es-ES", None))
        self.assertEqual(extract.vision_passes(["zh-Hans"]), ("zh-Hans", None))
        self.assertEqual(extract.vision_passes(FOUR), ("zh-Hans,zh-Hant,en-US", "en-US,fr-FR"))
        self.assertEqual(extract.vision_passes(["zh-TW", "fr-FR"]), ("zh-Hant", "fr-FR"))
        self.assertEqual(extract.tesseract_langs(FOUR), "chi_sim+chi_tra+eng+fra")
        self.assertEqual(extract.tesseract_langs(["en-GB", "en-US", "zh-Hans-CN", "de-DE", "es-ES"]),
                         "eng+chi_sim+deu+spa")
        regions = {"zh-CN": ("chi_sim", "zh-Hans"), "zh-SG": ("chi_sim", "zh-Hans"), "ZH-Hans": ("chi_sim", "zh-Hans"),
                   "zh-TW": ("chi_tra", "zh-Hant"), "zh-HK": ("chi_tra", "zh-Hant"), "zh-mo": ("chi_tra", "zh-Hant"),
                   "zh-Hant-HK": ("chi_tra", "zh-Hant"), "EN-gb": ("eng", "en-US")}
        for code, (tess, vision) in regions.items():
            with self.subTest(code):
                self.assertEqual((extract.tesseract_langs([code]), extract.vision_passes([code])),
                                 (tess, (vision, None)))
        for code in ("ja-JP", "zh", "ko-KR", "yue-Hant"):
            with self.subTest(code):
                with self.assertRaisesRegex(common.ToolError, re.escape("ocr_languages entry %r" % code)):
                    extract.tesseract_langs(["en-GB", code])
                with self.assertRaisesRegex(common.ToolError, re.escape("ocr_languages entry %r" % code)):
                    extract.vision_passes(["en-GB", code])

    def test_language_routing(self):
        img = self.file("page.png", b"a rendered page")
        first, second = extract.vision_passes(FOUR)
        zh = StandInOcr({first: {"text": ZH_CERTIFICATE, "confidence": 0.9}})
        page = extract.ocr_page(self.ctx(ocr=zh, langs=FOUR), img, 1)
        self.assertEqual((page["tier"], page["engine"], page["conf"], page["text"]),
                         ("local_ocr", "vision", 0.9, ZH_CERTIFICATE))
        self.assertEqual(zh.calls, [first], "a page with Chinese is not read again")
        fr = StandInOcr({first: {"text": "Cours de fran ais niveau", "confidence": 0.3},
                         second: {"text": FRENCH, "confidence": 0.95}})
        page = extract.ocr_page(self.ctx(ocr=fr, langs=FOUR), img, 1)
        self.assertEqual((page["tier"], page["text"]), ("local_ocr", FRENCH))
        self.assertEqual(fr.calls, [first, second])
        unsure = StandInOcr({first: {"text": FRENCH, "confidence": 0.3}})
        self.assertEqual(extract.ocr_page(self.ctx(ocr=unsure, langs=FOUR), img, 1)["tier"], "pending_vision")
        one = StandInOcr({"en-US": {"text": FRENCH, "confidence": 0.9}})
        self.assertEqual(extract.ocr_page(self.ctx(ocr=one), img, 1)["text"], FRENCH)
        self.assertEqual(one.calls, ["en-US"], "the default reads each page once, as en-US")

    def test_images(self):
        img = self.file("root/IMG_0002.jpg", b"a photo")
        e = {"id": "entry", "current_path": "IMG_0002.jpg", "class": "image"}
        rec = extract.process(self.ctx(), e)
        self.assertEqual((rec["status"], rec["pages"][0]["tier"]), ("photo", "photo"))
        beach = StandInOcr({"en-US": {"text": "Beach", "confidence": 0.9}})
        self.assertEqual(extract.process(self.ctx(ocr=beach), e)["status"], "photo")
        letter = StandInOcr({"en-US": {"text": STATEMENT + "\n" + STATEMENT, "confidence": 0.9}})
        rec = extract.process(self.ctx(ocr=letter), e)
        self.assertEqual((rec["status"], rec["pages"][0]["tier"]), ("ok", "local_ocr"))
        smudged = StandInOcr({"en-US": {"text": STATEMENT + "\n" + GARBAGE * 3, "confidence": 0.9}})
        rec = extract.process(self.ctx(ocr=smudged), e)
        self.assertEqual((rec["status"], rec["pages"][0]["tier"]), ("needs_vision", "pending_vision"))
        self.assertTrue(os.path.isfile(img))

    def test_a_reader_that_is_not_installed_is_named(self):
        c = self.ctx()
        for path, pattern in (("Old/Deck.ppt", r"no reader: LibreOffice \(soffice\) not installed"),
                              ("Old/Budget.xls", r"no reader: LibreOffice \(soffice\) not installed"),
                              ("Study/Notes.rtf", "no reader: textutil not available on this machine"),
                              ("Study/Page.html", "no reader: textutil not available on this machine")):
            with self.subTest(path):
                with self.assertRaisesRegex(RuntimeError, pattern):
                    extract.process(c, {"id": "entry", "current_path": path, "class": "document"})


class OcrLanguagesTest(Tmp):
    """The languages local OCR reads in come from the folder's rulebook.json (`ocr_languages`)."""

    def folder(self, **settings):
        root = os.path.join(self.tmp, "Alex Papers")
        rulebook = "# Rules\n\nThe owner's rules for this folder.\n"
        write(os.path.join(root, "CLAUDE.md"), rulebook)
        write(os.path.join(root, "Notes.txt"), "Robin's notes on the move.")
        self.settings(root, **settings)
        return root

    def settings(self, root, **settings):
        pin = hashlib.sha256(read(os.path.join(root, "CLAUDE.md"), "rb")).hexdigest()
        write(os.path.join(root, ".familyai", "rulebook.json"),
              json.dumps(dict(settings, version=1, rulebook_sha256=pin)))

    def test_the_default_and_the_shape(self):
        root = self.folder()
        settings_dir = os.path.join(root, ".familyai")
        self.assertEqual(common.load_rulebook(root, settings_dir)["ocr_languages"], ["en-GB"])
        for value, pattern in (("en-GB", "a list of non-empty strings"), ([], "a non-empty list"),
                               (["en GB"], "BCP 47"), (["english"], "BCP 47"), (["en_GB"], "BCP 47")):
            with self.subTest(value=value):
                self.settings(root, ocr_languages=value)
                with self.assertRaisesRegex(common.ToolError, pattern):
                    common.load_rulebook(root, settings_dir)

    def test_a_code_tesseract_cannot_read_stops_extraction_before_it_writes(self):
        root = self.folder(ocr_languages=["en-GB", "ko-KR"])
        work, audit_out, out = (os.path.join(self.tmp, n) for n in ("work", "audit", "extract"))
        code, _o, err = run("audit.py", "--root", root, "--work", work, "--out", audit_out, "--read-only-root")
        self.assertEqual(code, 0, err)
        code, _o, err = run("extract.py", "--root", root, "--work", work, "--manifest",
                            os.path.join(audit_out, "manifest.json"), "--out", out, "--read-only-root")
        self.assertEqual(code, 2, err)
        self.assertIn("ocr_languages entry 'ko-KR'", err)
        self.assertFalse(os.path.exists(out))


# ------------------------------------------------------------------------ office zip readers

class OfficeZipTest(Tmp):
    def test_the_fixture_files_read_as_expected(self):
        exp = expected()
        for rel in ("06 Work/Essay.docx", "06 Work/Contract.docx", "04 Study/Slides.pptx",
                    "01 Identity/Passport renewal 2021/Application form.docx", "02 Finance/Tax/Budget final.xlsx"):
            with self.subTest(rel):
                pages = extract.office_zip(os.path.join(FIXTURE, rel), os.path.splitext(rel)[1])
                self.assertEqual([p["text"] for p in pages], exp[rel]["text"])

    def test_spreadsheet_cells(self):
        sst = ("<sst><si><t>Item</t></si><si><r><t>Mon</t></r><r><t>thly</t></r></si>"
               "<si><t>Rent &amp; bills</t></si></sst>")
        sheet = ('<worksheet><sheetData>'
                 '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                 '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>1450</v></c><c r="C2"/></row>'
                 '<row r="3"><c t="inlineStr"><is><t>Savings</t></is></c><c><v>400</v></c></row>'
                 '<row r="4"><c r="A4"/><c r="B4" t="s"><v>9</v></c></row>'
                 '<row r="5"><c r="A5" t="str"><v>a &lt; b</v></c></row>'
                 '</sheetData></worksheet>')
        p = self.file("Budget.xlsx", zip_bytes([("xl/sharedStrings.xml", sst), ("xl/worksheets/sheet1.xml", sheet)]))
        self.assertEqual(extract.office_zip(p, ".xlsx"),
                         [{"n": 1, "tier": "text_layer", "text": "Item\tMonthly\nRent & bills\t1450\t\n"
                                                                    "Savings\t400\na < b"}])

    def test_cell_types_in_single_quotes(self):
        sheet = ("<worksheet><sheetData><row><c r='A1' t='s'><v>0</v></c><c t='inlineStr'><is><t>monthly</t></is></c>"
                 "<c><v>1450</v></c></row></sheetData></worksheet>")
        p = self.file("Quoted.xlsx", zip_bytes([("xl/sharedStrings.xml", "<sst><si><t>Rent</t></si></sst>"),
                                                ("xl/worksheets/sheet1.xml", sheet)]))
        self.assertEqual(extract.office_zip(p, ".xlsx")[0]["text"], "Rent\tmonthly\t1450")

    def test_sheets_and_slides_in_number_order(self):
        sheets = [("xl/worksheets/sheet%d.xml" % n, "<worksheet><sheetData><row><c><v>%d</v></c></row></sheetData>"
                   "</worksheet>" % n) for n in (10, 2, 1)]
        p = self.file("Many.xlsx", zip_bytes(sheets))
        self.assertEqual([(pg["n"], pg["text"]) for pg in extract.office_zip(p, ".xlsx")], [(1, "1"), (2, "2"),
                                                                                           (3, "10")])
        slides = [("ppt/slides/slide%d.xml" % n, "<p:sld><a:p><a:t>Slide %d</a:t></a:p></p:sld>" % n)
                  for n in (10, 2, 1)]
        notes = [("ppt/notesSlides/notesSlide2.xml", "<p:notes><a:p><a:t>Only slide two has notes</a:t></a:p>"
                  "</p:notes>")]
        p = self.file("Deck.pptx", zip_bytes(slides + notes))
        self.assertEqual([pg["text"] for pg in extract.office_zip(p, ".pptx")],
                         ["Slide 1", "Slide 2\n\n[notes]\nOnly slide two has notes", "Slide 10"])

    def test_a_document(self):
        body = ('<w:document><w:body><w:p><w:r><w:t>Name</w:t><w:tab/><w:t>Alex &amp; Robin</w:t></w:r></w:p>'
                '<w:p><w:r><w:t>Line one</w:t><w:br/><w:t>Line two</w:t></w:r></w:p></w:body></w:document>')
        p = self.file("Letter.docx", zip_bytes([
            ("word/document.xml", body), ("word/header1.xml", "<w:hdr><w:p><w:t>Header</w:t></w:p></w:hdr>"),
            ("word/footnotes.xml", "<w:footnotes><w:p><w:t>A footnote</w:t></w:p></w:footnotes>")]))
        self.assertEqual(extract.office_zip(p, ".docx")[0]["text"],
                         "Name\tAlex & Robin\nLine one\nLine two\n\nA footnote")

    def test_what_it_cannot_read(self):
        with self.assertRaises(zipfile.BadZipFile):
            extract.office_zip(self.file("Broken.docx", b"not a zip at all"), ".docx")
        with self.assertRaisesRegex(RuntimeError, "unsupported office zip"):
            extract.office_zip(self.file("Odd.zip", zip_bytes([("a.xml", "<a/>")])), ".zip")


# ------------------------------------------------------------------------ the iWork reader

class IwaTest(Tmp):
    def test_snappy(self):
        self.assertEqual(iwa.snappy_raw(bytes([9, 8]) + b"abc" + bytes([9, 3])), b"abcabcabc")    # 1-byte offset
        self.assertEqual(iwa.snappy_raw(bytes([6, 8]) + b"xyz" + bytes([10, 3, 0])), b"xyzxyz")    # 2-byte offset
        self.assertEqual(iwa.snappy_raw(snappy_literal(b"L" * 300)), b"L" * 300)
        with self.assertRaisesRegex(ValueError, "bad snappy offset"):
            iwa.snappy_raw(bytes([9, 8]) + b"abc" + bytes([9, 5]))

    def test_chunks(self):
        stored = b"stored as is"
        self.assertEqual(iwa.iwa_decompress(bytes([1]) + len(stored).to_bytes(3, "little") + stored), stored)
        packed = snappy_literal(b"packed")
        two = bytes([0]) + len(packed).to_bytes(3, "little") + packed + bytes([1, 2, 0, 0]) + b"ok"
        self.assertEqual(iwa.iwa_decompress(two), b"packedok")

    def test_the_fixture_numbers_file(self):
        self.assertEqual(iwa.iwork_text(os.path.join(FIXTURE, "02 Finance", "Tax", "Budget.numbers")),
                         ["Household budget for 2023 prepared by Alex Example",
                          "Rent 1,450 per month and utilities about 150 per month"])

    def test_words_kept_and_noise_left_out(self):
        texts = ["Lease renewal for 3 Example Road", "Helvetica-Bold", "com.apple.iWork.pages", "paragraph style 12",
                 "Sheet 1", "d MMM yyyy", "Signed", ZH_CERTIFICATE, "中文", "0A1B2C3D-4E5F-6A7B-8C9D", "logo.png",
                 "SFWPFontStyle", "Lease renewal for 3 Example Road"]
        p = self.file("Lease.pages", zip_bytes([
            ("Index/Other.iwa", iwa_chunk(["Last: a note in another archive"])),
            ("Index/Tables/DataList.iwa", iwa_chunk(["A table cell with some words"])),
            ("Index/DocumentStylesheet.iwa", iwa_chunk(["Stylesheet prose that must not appear"])),
            ("Index/Document.iwa", iwa_chunk(texts)),
            ("preview.jpg", b"jpeg"),
        ]))
        self.assertEqual(iwa.iwork_text(p), ["Lease renewal for 3 Example Road", ZH_CERTIFICATE, "中文",
                                             "A table cell with some words", "Last: a note in another archive"])

    def test_a_package_with_an_index_zip(self):
        pkg = os.path.join(self.tmp, "Old.pages")
        write(os.path.join(pkg, "Index.zip"), zip_bytes([("Index/Document.iwa", iwa_chunk(["Written before 2015 "
                                                                                             "in a package"]))]))
        self.assertEqual(iwa.iwork_text(pkg), ["Written before 2015 in a package"])

    def test_unreadable_archives_give_nothing(self):
        p = self.file("Garbage.numbers", zip_bytes([("Index/Document.iwa", b"\x00\x05\x00\x00hello\xff\xff"),
                                                    ("Index/Tables/Tile.iwa", bytes(range(256)))]))
        self.assertEqual(iwa.iwork_text(p), [])


# ------------------------------------------------------------------------ extract.py on a copy of the fixture

class FixtureRun:
    """Both lanes run once on one fixture copy per test class, with the outputs outside it and the folder
    read-only."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="extract_fixture_")
        cls.root = os.path.join(cls.tmp, "Alex Personal")
        shutil.copytree(FIXTURE, cls.root)
        cls.before = tree_digest(cls.root)
        cls.work, cls.manifest = os.path.join(cls.tmp, "work"), os.path.join(cls.tmp, "audit", "manifest.json")
        code, _o, err = run("audit.py", "--root", cls.root, "--work", cls.work, "--out", os.path.dirname(cls.manifest),
                            "--read-only-root")
        if code != 0:
            raise RuntimeError("the audit of the fixture copy failed (%d): %s" % (code, err))
        cls.out = os.path.join(cls.tmp, "extract")
        cls.codes = [cls.extract(cls.out, "--lane", lane)[0] for lane in ("main", "apps")]
        cls.records = cls.load(cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    @classmethod
    def extract(cls, out, *args, now=NOW):
        return run("extract.py", "--root", cls.root, "--work", cls.work, "--manifest", cls.manifest, "--out", out,
                   "--read-only-root", *args, now=now)

    @staticmethod
    def load(out):
        recs = {}
        for f in sorted(os.listdir(out)):
            r = json.loads(read(os.path.join(out, f)))
            recs[r["path"]] = r
        return recs


class FixtureRunTest(FixtureRun, unittest.TestCase):
    def test_the_folder_is_untouched(self):
        self.assertEqual(tree_digest(self.root), self.before)
        self.assertEqual(len(self.records), 18)

    def test_office_iwork_plain_and_photo_records_match_expected(self):
        exp = expected()
        for rel, want in exp.items():
            ext = os.path.splitext(rel)[1].lower()
            if ext in extract.OFFICE_ZIP | extract.IWORK | extract.PLAIN or ext == ".jpg":
                with self.subTest(rel):
                    self.assertEqual(view(self.records[rel]), want)
        self.assertEqual(self.records["03 Home/Lease renewal.pages"]["pages"][0]["via"], "iwa")

    @unittest.skipIf(POPPLER, "PDF text-layer tier is installed here; its records are compared instead")
    def test_pdfs_fail_naming_poppler_when_it_is_missing(self):
        pdfs = {p: r for p, r in self.records.items() if p.endswith(".pdf")}
        self.assertEqual(len(pdfs), 8)
        for rel, r in pdfs.items():
            with self.subTest(rel):
                self.assertEqual((r["status"], r["error"], r["pages"]),
                                 ("failed", "pdftotext/pdfinfo not available (install poppler)", []))
        self.assertEqual(self.codes[0], 1, "a failed record makes the lane exit 1")

    @unittest.skipUnless(POPPLER, PDF_TEXT_LAYER)
    def test_pdf_text_layers_match_expected(self):
        exp = expected()
        for rel, want in exp.items():
            if rel.endswith(".pdf"):
                with self.subTest(rel):
                    got = view(self.records[rel])
                    for n, tier in enumerate(want["tiers"]):
                        if tier == "text_layer":
                            self.assertEqual((got["tiers"][n], got["text"][n]), ("text_layer", want["text"][n]))
                        else:
                            self.assertNotEqual(got["tiers"][n], "text_layer", "page %d is a scan or broken" % (n + 1))

    @unittest.skipUnless(HAVE["page-ocr"] and POPPLER and HAVE["pdftoppm"], VISION_OCR)
    def test_every_tier_matches_expected_with_vision(self):
        exp = expected()
        for rel, want in exp.items():
            if rel.endswith(".pdf"):
                with self.subTest(rel):
                    self.assertEqual(view(self.records[rel])["tiers"], want["tiers"])
                    self.assertEqual(self.records[rel]["status"], want["status"])

    @unittest.skipUnless(HAVE["tesseract"] and POPPLER and HAVE["pdftoppm"], TESSERACT_OCR)
    def test_scans_are_read_locally_with_tesseract(self):
        for rel in ("01 Identity/Passport scan.pdf", "04 Study/Cours de français.pdf"):
            with self.subTest(rel):
                page = self.records[rel]["pages"][0]
                self.assertIn(page["tier"], ("local_ocr", "pending_vision"))
                if page["tier"] == "local_ocr" and not HAVE["page-ocr"]:
                    self.assertEqual(page["engine"], "tesseract")

    @unittest.skipIf(HAVE["textutil"], "textutil tier is installed here; the rtf record is compared instead")
    def test_rtf_fails_naming_textutil_when_it_is_missing(self):
        r = self.records["04 Study/Notes.rtf"]
        self.assertEqual((r["status"], r["error"]), ("failed", "no reader: textutil not available on this machine"))

    @unittest.skipUnless(HAVE["textutil"], TEXTUTIL)
    def test_rtf_matches_expected(self):
        self.assertEqual(view(self.records["04 Study/Notes.rtf"]), expected()["04 Study/Notes.rtf"])

    def test_lanes_and_workers_split_the_work(self):
        apps = {p for p, r in self.records.items() if os.path.splitext(p)[1] in extract.IWORK}
        self.assertEqual(apps, {"03 Home/Lease renewal.pages", "02 Finance/Tax/Budget.numbers"})
        halves = []
        for w in ("0/2", "1/2"):
            out = os.path.join(self.tmp, "worker" + w[0])
            self.extract(out, "--lane", "main", "--worker", w)
            halves.append(set(self.load(out)))
        self.assertFalse(halves[0] & halves[1])
        self.assertEqual(halves[0] | halves[1], set(self.records) - apps)
        self.assertTrue(halves[0] and halves[1])

    def test_read_only_root_refuses_the_default_out(self):
        code, _o, err = run("extract.py", "--root", self.root, "--work", self.work, "--manifest", self.manifest,
                            "--read-only-root")
        self.assertEqual(code, 2)
        self.assertIn("--read-only-root", err)
        self.assertEqual(tree_digest(self.root), self.before)


class ResumeTest(FixtureRun, unittest.TestCase):
    """An existing record is never rewritten, unless it failed and --retry-failed is given."""

    def test_resume(self):
        before = {f: read(os.path.join(self.out, f), "rb") for f in os.listdir(self.out)}
        for lane in ("main", "apps"):
            self.extract(self.out, "--lane", lane, now=NOW + 60)
        self.assertEqual({f: read(os.path.join(self.out, f), "rb") for f in os.listdir(self.out)}, before)
        for lane in ("main", "apps"):
            self.extract(self.out, "--lane", lane, "--retry-failed", now=NOW + 60)
        for rel, r in self.load(self.out).items():
            with self.subTest(rel):
                redone = self.records[rel]["status"] == "failed"
                self.assertEqual(r["extracted_at"] != self.records[rel]["extracted_at"], redone)


# ------------------------------------------------------------------------ statuses on a synthetic folder

class StatusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="extract_status_")
        cls.root = os.path.join(cls.tmp, "Alex Papers")
        preview = read(os.path.join(FIXTURE, "03 Home", "Lease renewal.pages", "preview.jpg"), "rb")
        files = {
            "Mail/Bundle.zip": zip_bytes([("a.txt", "a"), ("b/c.pdf", "c")]),
            "Misc/blob.bin": bytes(range(256)) * 8,
            "Misc/server.log": "2024-06-30 12:00 backup finished without errors for Alex\n",
            "Docs/Broken.docx": b"not a zip at all",
            "Docs/Letter.docx": b"{\\rtf1\\ansi A letter saved as rich text under a Word name.}",
            "Docs/Notes.md": "# Notes\n\nRobin's birthday is in June.\n",
            "Docs/Skipped.md": "hashed false in the manifest",
            "Docs/Gone.md": "departed in the manifest",
            "Docs/Blank.pages/Index/Document.iwa": b"\x00\x05\x00\x00hello",
            "Docs/Blank.pages/preview.jpg": preview,
            "Docs/Empty.numbers": zip_bytes([("Index/Document.iwa", b"\x00\x05\x00\x00hello")]),
        }
        for rel, data in files.items():
            write(os.path.join(cls.root, rel), data)
        work, out = os.path.join(cls.tmp, "work"), os.path.join(cls.tmp, "audit")
        code, _o, err = run("audit.py", "--root", cls.root, "--work", work, "--out", out, "--read-only-root")
        if code != 0:
            raise RuntimeError("the audit of the synthetic folder failed (%d): %s" % (code, err))
        manifest = os.path.join(out, "manifest.json")
        m = json.loads(read(manifest))
        for e in m["entries"].values():
            if e["current_path"] == "Docs/Skipped.md":
                e["hashed"] = False
            if e["current_path"] == "Docs/Gone.md":
                e["flags"] = ["departed"]
        write(manifest, json.dumps(m))
        cls.out = os.path.join(cls.tmp, "extract")
        for lane in ("main", "apps"):
            run("extract.py", "--root", cls.root, "--work", work, "--manifest", manifest, "--out", cls.out,
                "--lane", lane, "--read-only-root")
        cls.records = {r["path"]: r for r in (json.loads(read(os.path.join(cls.out, f)))
                                              for f in os.listdir(cls.out))}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def test_listed(self):
        r = self.records["Mail/Bundle.zip"]
        self.assertEqual((r["status"], r["pages"]), ("listed", [{"n": 1, "tier": "listing", "text": "a.txt\nb/c.pdf"}]))

    def test_no_reader_and_readable_other_files(self):
        self.assertEqual((self.records["Misc/blob.bin"]["status"], self.records["Misc/blob.bin"]["pages"]),
                         ("no_reader", []))
        log = self.records["Misc/server.log"]
        self.assertEqual((log["status"], log["pages"][0]["tier"]), ("ok", "text_layer"))
        self.assertEqual(self.records["Docs/Notes.md"]["pages"][0]["text"], "# Notes\n\nRobin's birthday is in June.")

    def test_failed(self):
        r = self.records["Docs/Broken.docx"]
        self.assertEqual((r["status"], r["pages"], r["page_count"]), ("failed", [], 0))
        self.assertIn("zip", r["error"])
        r = self.records["Docs/Empty.numbers"]
        self.assertEqual((r["status"], r["error"]), ("failed", "no readable content in iWork file"))

    @unittest.skipUnless(shutil.which("textutil"), "needs macOS textutil")
    def test_rich_text_under_a_word_name_is_still_read(self):
        r = self.records["Docs/Letter.docx"]
        self.assertEqual(r["status"], "ok")
        self.assertIn("A letter saved as rich text", r["pages"][0]["text"])

    def test_an_iwork_file_read_only_from_its_preview_is_partial(self):
        r = self.records["Docs/Blank.pages"]
        self.assertEqual((r["status"], r["pages"][0]["via"]), ("partial", "preview_image"))
        if not (HAVE["page-ocr"] or HAVE["tesseract"]):
            self.assertEqual(r["pages"][0]["tier"], "blank")
            self.assertEqual(r["notes"], ["local OCR tier not available here: page-ocr, tesseract"])

    def test_unhashed_and_departed_entries_are_left_alone(self):
        self.assertEqual(sorted(self.records), ["Docs/Blank.pages", "Docs/Broken.docx", "Docs/Empty.numbers",
                                                "Docs/Letter.docx", "Docs/Notes.md", "Mail/Bundle.zip", "Misc/blob.bin",
                                                "Misc/server.log"])


if __name__ == "__main__":
    unittest.main()
