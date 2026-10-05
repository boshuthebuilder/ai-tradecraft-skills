#!/usr/bin/env python3
"""Full text of every live document in the manifest, every page, from local tools only (no model calls).

Per page the first clean reading wins: the PDF text layer (unless it is broken, with spaces decoded as `)` or `!`),
then Apple Vision through `page-ocr`, then tesseract, both in the languages the folder's rulebook.json lists as
`ocr_languages` (`vision_passes` says how Vision is routed). A page none of them reads cleanly is queued for the model
vision lane (`vision.py`) and marked `pending_vision`. Office zip formats are parsed directly, rtf/doc/odt/html through
`textutil`, iWork through the `.iwa` reader (`iwa.py`) with the preview image as a fallback, legacy .ppt/.xls through
LibreOffice when it is installed. Resumable: an existing record is never rewritten unless `--retry-failed`, which reads
again a record that failed, or that was read while a local OCR tier was missing (its `notes` say so).

A document whose current path is under the migrations folder is held for another project, and one the rulebook
`exclude`s (a listed path, or under one) is excluded: neither is ever read or queued, whatever its flags, and the run's
log counts each (`held_for_another_project`, `excluded`).

    python3 extract.py --root R --lane main --worker 0/4
    python3 extract.py --root R --lane apps
    python3 extract.py repath --root R [--apply]     after a round moved documents: paths from the manifest, by hash

Record: id, path, class, status (ok, partial, blank, photo, listed, no_reader, needs_vision, failed), page_count,
tiers, chars, extractor, extracted_at, pages[{n, text, tier, engine?, conf?}], notes?. A tier whose tool is missing
is named in `notes`, never skipped silently.
"""
import collections
import html
import json
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import iwa  # noqa: E402

GEN = "ai-os-pre-onboarding-extract/1"
LEGACY = {".ppt", ".pot", ".pps", ".xls"}
IWORK = {".pages", ".key", ".numbers"}
TEXTUTIL = {".doc", ".rtf", ".odt", ".html", ".htm", ".webarchive"}
OFFICE_ZIP = {".docx", ".pptx", ".xlsx", ".ppsx", ".potx"}
PLAIN = {".txt", ".md", ".csv"}
PHOTO_MIN_CHARS = 80
CJK_LANGS = ("zh",)             # the languages `cjk()` counts and both OCR tables know
# A BCP 47 code, in lower case, by language and its script or region, else by language alone: tesseract's language
# and Vision's. The Vision codes are those in Vision's supportedRecognitionLanguages, to be confirmed on a Mac with
# `page-ocr --lang`; Vision is given these, never the rulebook's own regional codes.
TESSERACT_LANGS = {"en": "eng", "fr": "fra", "de": "deu", "es": "spa",
                   "zh-hans": "chi_sim", "zh-cn": "chi_sim", "zh-sg": "chi_sim",
                   "zh-hant": "chi_tra", "zh-tw": "chi_tra", "zh-hk": "chi_tra", "zh-mo": "chi_tra"}
VISION_LANGS = {"en": "en-US", "fr": "fr-FR", "de": "de-DE", "es": "es-ES",
                "zh-hans": "zh-Hans", "zh-cn": "zh-Hans", "zh-sg": "zh-Hans",
                "zh-hant": "zh-Hant", "zh-tw": "zh-Hant", "zh-hk": "zh-Hant", "zh-mo": "zh-Hant"}
SEARCH = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin"]


def ocr_codes(langs, table):
    """`table`'s codes for the rulebook's BCP 47 codes, in order, without repeats; an unknown code fails loud."""
    out = []
    for code in langs:
        parts = code.lower().split("-")
        key = next((k for k in ("-".join(parts[:2]), parts[0]) if k in table), None)
        if key is None:
            raise common.ToolError("ocr_languages entry %r is not a language local OCR reads (known: en, fr, de, es, "
                                   "zh-Hans, zh-CN, zh-SG, zh-Hant, zh-TW, zh-HK, zh-MO)" % code)
        out.append(table[key])
    return list(dict.fromkeys(out))


def tesseract_langs(langs):
    """tesseract's `-l` value for the rulebook's codes."""
    return "+".join(ocr_codes(langs, TESSERACT_LANGS))


def vision_passes(langs):
    """The language sets Vision reads a page with, in Vision's codes: the Chinese codes with the English ones, then,
    for a page on which that finds no Chinese text, the other codes; one pass with every code when the list has no
    Chinese code or nothing else. Vision is not given Chinese beside a language other than English."""
    codes = ocr_codes(langs, VISION_LANGS)
    cjk_codes = [c for c in codes if c.split("-")[0].lower() in CJK_LANGS]
    other = [c for c in codes if c not in cjk_codes]
    if not cjk_codes or not other:
        return ",".join(codes), None
    return ",".join(cjk_codes + [c for c in other if c.split("-")[0].lower() == "en"]), ",".join(other)


def which(name, explicit=None):
    if explicit:
        return explicit if os.path.exists(explicit) else None
    path = os.environ.get("PATH", "") + ":" + ":".join(SEARCH)
    return shutil.which(name, path=path)


class Ctx:
    def __init__(self, a, root, work, out, langs=tuple(common.DEFAULTS["ocr_languages"])):
        self.root, self.work, self.out = root, work, out
        self.langs, self.tesseract_langs, self.vision_passes = list(langs), tesseract_langs(langs), vision_passes(langs)
        self.queue = os.path.join(work, "vision_queue")
        self.tmp = tempfile.mkdtemp(prefix="extract_")
        self.bins = {n: which(n) for n in ("pdftotext", "pdfinfo", "pdftoppm", "tesseract", "textutil", "sips",
                                           "soffice")}
        here = os.path.dirname(os.path.abspath(__file__))
        self.bins["page-ocr"] = which("page-ocr", a.ocr_bin or (os.path.join(here, "page-ocr")
                                                                  if os.path.exists(os.path.join(here, "page-ocr"))
                                                                  else None))
        self.ocr = OCR(self.bins["page-ocr"])
        self.cur = None


def run(cmd, timeout):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.stdout.decode("utf-8", "replace"), r.returncode, r.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return "", -9, "timeout"
    except OSError as e:
        return "", -1, str(e)


class OCR:
    """A persistent `page-ocr --stdin` process, restarted if it stalls. The first run compiles Vision's model
    (about a minute); that is not a hang."""

    def __init__(self, binary):
        self.bin, self.p = binary, None

    def read(self, img, langs, timeout=300):
        if not self.bin:
            return {"text": "", "confidence": 0.0, "error": "page-ocr not available"}
        for _attempt in range(2):
            if self.p is None or self.p.poll() is not None:
                self.p = subprocess.Popen([self.bin, "--stdin"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL, text=True, bufsize=1)
            try:
                self.p.stdin.write("LANG=%s|%s\n" % (langs, img))
                self.p.stdin.flush()
                ready, _, _ = select.select([self.p.stdout], [], [], timeout)
                if ready:
                    line = self.p.stdout.readline()
                    if line:
                        return json.loads(line)
            except (OSError, ValueError):
                pass
            self.close()
        return {"text": "", "confidence": 0.0, "error": "ocr stalled"}

    def close(self):
        """Stop the process, if one is running, and close its pipes."""
        if self.p is None:
            return
        for stream in (self.p.stdin, self.p.stdout):
            try:
                stream.close()
            except OSError:
                pass
        try:
            self.p.kill()
        except OSError:
            pass
        self.p.wait()
        self.p = None


def quality(s):
    if not s:
        return 0.0
    ok = sum(1 for ch in s if ch.isalnum() or ch.isspace() or ch in ".,;:/-()'&£$€¥%#@+!?\"’“”‘–\u2014·•*，。、；：？！（）《》【】「」…")
    return ok / len(s)


def good(t, conf=1.0):
    s = t.strip()
    if len(s) < 40 or quality(s) < 0.85 or conf < 0.45:
        return False
    ns = [ch for ch in s if not ch.isspace()]
    if sum(1 for ch in ns if ch.isalnum()) / max(1, len(ns)) < 0.5:
        return False
    return bool(re.search(r"[A-Za-zÀ-ÿ]{3,}", s)) or len(re.findall(r"[一-鿿]", s)) >= 15


def broken_layer(s):
    """A text layer whose spaces decode as `)` or `!` (a missing font map): OCR the page instead."""
    glued = len(re.findall(r"[A-Za-z0-9,][)!\]#][A-Za-z0-9(]", s))
    spaces = len(re.findall(r"[A-Za-z,.] [A-Za-z(]", s))
    return glued >= 5 and glued / (glued + spaces) > 0.3


def tidy(t):
    return "\n".join(line.rstrip() for line in t.replace("\r", "").split("\n")).strip()


def cjk(t):
    return len(re.findall(r"[一-鿿]", t))


def textutil_format(path):
    """Whether a file textutil can convert sits under an Office name: RTF, a legacy Word file (an OLE container) or
    HTML, which a person or an old export may have saved as .docx. Anything else is not read as text."""
    with open(path, "rb") as f:
        head = f.read(512)
    lead = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return (head.startswith(b"{\\rtf") or head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
            or lead.startswith(b"<!doctype html") or lead.startswith(b"<html"))


def vision(ctx, img):
    first, second = ctx.vision_passes
    a = ctx.ocr.read(img, first)
    if second is None or cjk(a.get("text", "")) >= 5:
        return a.get("text", ""), float(a.get("confidence") or 0)
    b = ctx.ocr.read(img, second)
    best = max((a, b), key=lambda r: (float(r.get("confidence") or 0) * min(1, len(r.get("text", "")) / 40.0)))
    return best.get("text", ""), float(best.get("confidence") or 0)


def tesseract(ctx, img):
    if not ctx.bins["tesseract"]:
        return ""
    o, _rc, _ = run([ctx.bins["tesseract"], img, "stdout", "-l", ctx.tesseract_langs], 300)
    return o


def enqueue(ctx, img, n):
    os.makedirs(ctx.queue, exist_ok=True)
    dst = os.path.join(ctx.queue, "%s_%05d.png" % (ctx.cur, n))
    if ctx.bins["sips"]:
        run([ctx.bins["sips"], "-Z", "2200", "-s", "format", "png", img, "--out", dst], 120)
    if not os.path.exists(dst):
        shutil.copyfile(img, dst)
    return os.path.basename(dst)


def ocr_page(ctx, img, n, layer=""):
    v, conf = vision(ctx, img)
    if good(v, conf):
        return {"n": n, "tier": "local_ocr", "engine": "vision", "conf": round(conf, 3), "text": tidy(v)}
    t = tesseract(ctx, img)
    if good(t):
        return {"n": n, "tier": "local_ocr", "engine": "tesseract", "text": tidy(t)}
    best = max([v, t, layer], key=lambda x: len(x.strip()))
    if len(best.strip()) < 25:
        return {"n": n, "tier": "blank", "text": tidy(best)}
    return {"n": n, "tier": "pending_vision", "text": tidy(best), "queued": enqueue(ctx, img, n)}


def pdf_pages(ctx, path):
    if not (ctx.bins["pdftotext"] and ctx.bins["pdfinfo"]):
        raise RuntimeError("pdftotext/pdfinfo not available (install poppler)")
    info, _rc, _err = run([ctx.bins["pdfinfo"], path], 120)
    m = re.search(r"Pages:\s+(\d+)", info)
    n = int(m.group(1)) if m else None
    full, _rc, err = run([ctx.bins["pdftotext"], "-layout", "-enc", "UTF-8", path, "-"], 1800)
    parts = full.split("\f")
    if n is None:
        if not full.strip():
            raise RuntimeError("pdf unreadable: " + (err.strip()[:200] or "no pages"))
        n = len(parts) - 1 if len(parts) > 1 and not parts[-1].strip() else len(parts)
    pages = []
    for i in range(n):
        t = parts[i] if i < len(parts) else ""
        if good(t) and not broken_layer(t):
            pages.append({"n": i + 1, "tier": "text_layer", "text": tidy(t)})
            continue
        if broken_layer(t):
            t = ""
        if not ctx.bins["pdftoppm"]:
            pages.append({"n": i + 1, "tier": "none", "text": tidy(t), "note": "pdftoppm not available"})
            continue
        d = tempfile.mkdtemp(dir=ctx.tmp)
        try:
            run([ctx.bins["pdftoppm"], "-r", "200", "-f", str(i + 1), "-l", str(i + 1), "-png", "-singlefile", path,
                 os.path.join(d, "p")], 300)
            img = os.path.join(d, "p.png")
            if os.path.exists(img):
                pages.append(ocr_page(ctx, img, i + 1, t))
            else:
                pages.append({"n": i + 1, "tier": "none", "text": tidy(t), "note": "render_failed"})
        finally:
            shutil.rmtree(d, True)
    return pages


def xml_text(s):
    s = re.sub(r"<(w|a):tab/>", "\t", s)
    s = re.sub(r"</w:p>|</a:p>|<w:br[^>]*/>|<a:br/>|<w:cr/>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)


def num_key(name):
    m = re.search(r"(\d+)\.xml$", name)
    return int(m.group(1)) if m else 0


def office_zip(path, ext):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    if ext == ".docx":
        parts = [n for n in names if re.fullmatch(r"word/(document|footnotes|endnotes)\.xml", n)]
        text = "\n".join(xml_text(z.read(n).decode("utf-8", "replace")) for n in sorted(parts))
        return [{"n": 1, "tier": "text_layer", "text": tidy(text)}]
    if ext in (".pptx", ".ppsx", ".potx"):
        slides = sorted([n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)], key=num_key)
        notes = {num_key(n): n for n in names if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)}
        out = []
        for i, n in enumerate(slides):
            t = xml_text(z.read(n).decode("utf-8", "replace"))
            if num_key(n) in notes:
                t += "\n[notes]\n" + xml_text(z.read(notes[num_key(n)]).decode("utf-8", "replace"))
            out.append({"n": i + 1, "tier": "text_layer", "text": tidy(t)})
        return out
    if ext == ".xlsx":
        shared = []
        if "xl/sharedStrings.xml" in names:
            ss = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
            shared = [xml_text(si) for si in re.findall(r"<si>(.*?)</si>", ss, re.S)]
        sheets = sorted([n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)], key=num_key)
        out = []
        for i, n in enumerate(sheets):
            x = z.read(n).decode("utf-8", "replace")
            rows = []
            for row in re.findall(r"<row[^>]*>(.*?)</row>", x, re.S):
                cells = []
                for attrs, body in re.findall(r"<c(?:\s([^>]*?))?(?:/>|>(.*?)</c>)", row, re.S):
                    v = re.search(r"<v>(.*?)</v>", body or "", re.S)
                    if re.search(r"""\bt=["']s["']""", attrs) and v:
                        try:
                            cells.append(shared[int(v.group(1))])
                        except (IndexError, ValueError):
                            cells.append("")
                    elif re.search(r"""\bt=["']inlineStr["']""", attrs):
                        cells.append(xml_text(body or ""))
                    else:
                        cells.append(html.unescape(v.group(1)) if v else "")
                if any(c.strip() for c in cells):
                    rows.append("\t".join(c.strip() for c in cells))
            out.append({"n": i + 1, "tier": "text_layer", "text": "\n".join(rows)})
        return out
    raise RuntimeError("unsupported office zip")


def decode(b):
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("latin-1", "replace")


def legacy_export(ctx, src):
    """Legacy .ppt/.xls through LibreOffice when installed; the export is read like any PDF."""
    if not ctx.bins["soffice"]:
        raise RuntimeError("no reader: LibreOffice (soffice) not installed")
    d = tempfile.mkdtemp(dir=ctx.tmp)
    try:
        _o, rc, err = run([ctx.bins["soffice"], "--headless", "--convert-to", "pdf", "--outdir", d, src], 300)
        pdfs = [f for f in os.listdir(d) if f.endswith(".pdf")]
        if rc != 0 or not pdfs:
            raise RuntimeError("LibreOffice export failed: %s" % (err.strip()[:160] or rc))
        pages = pdf_pages(ctx, os.path.join(d, pdfs[0]))
        for p in pages:
            p["via"] = "libreoffice"
        return pages
    finally:
        shutil.rmtree(d, True)


def iwork_preview(ctx, src):
    blob = None
    if os.path.isdir(src):
        for n in ("preview.jpg", "QuickLook/Thumbnail.jpg"):
            if os.path.exists(os.path.join(src, n)):
                with open(os.path.join(src, n), "rb") as f:
                    blob = f.read()
                break
    elif zipfile.is_zipfile(src):
        z = zipfile.ZipFile(src)
        for n in ("preview.jpg", "QuickLook/Thumbnail.jpg"):
            if n in z.namelist():
                blob = z.read(n)
                break
    if not blob:
        raise RuntimeError("no readable content in iWork file")
    d = tempfile.mkdtemp(dir=ctx.tmp)
    try:
        p = os.path.join(d, "p.jpg")
        with open(p, "wb") as f:
            f.write(blob)
        pg = ocr_page(ctx, p, 1)
        pg["via"] = "preview_image"
        return [pg]
    finally:
        shutil.rmtree(d, True)


def process(ctx, e):
    path = os.path.join(ctx.root, e["current_path"])
    ext = os.path.splitext(path)[1].lower()
    cls = e["class"]
    status = None
    notes = []
    if ext == ".pdf":
        pages = pdf_pages(ctx, path)
    elif cls == "image":
        v, conf = vision(ctx, path)
        if good(v, conf) and len(v.strip()) >= PHOTO_MIN_CHARS:
            pages = [{"n": 1, "tier": "local_ocr", "engine": "vision", "conf": round(conf, 3), "text": tidy(v)}]
        elif len(v.strip()) < PHOTO_MIN_CHARS:
            pages, status = [{"n": 1, "tier": "photo", "text": tidy(v)}], "photo"
        else:
            pages = [ocr_page(ctx, path, 1)]
    elif ext in IWORK:
        pages = []
        try:
            blocks = iwa.iwork_text(path)
            if blocks:
                pages = [{"n": 1, "tier": "text_layer", "via": "iwa", "text": tidy("\n\n".join(blocks))}]
        except (OSError, ValueError, zipfile.BadZipFile) as ex:
            notes.append("iwa read failed: %s" % str(ex)[:120])
        if not pages:
            pages = iwork_preview(ctx, path)
            status = "partial"
    elif ext in LEGACY:
        pages = legacy_export(ctx, path)
    elif ext in OFFICE_ZIP:
        try:
            pages = office_zip(path, ext)
        except (zipfile.BadZipFile, KeyError, RuntimeError):
            if not ctx.bins["textutil"] or not (zipfile.is_zipfile(path) or textutil_format(path)):
                raise  # textutil reads any other file as plain text: its bytes would pass as the text
            o, rc, _err = run([ctx.bins["textutil"], "-convert", "txt", "-stdout", path], 300)
            if rc != 0 and not o.strip():
                raise
            pages = [{"n": 1, "tier": "text_layer", "text": tidy(o), "via": "textutil"}]
    elif ext in TEXTUTIL:
        if not ctx.bins["textutil"]:
            raise RuntimeError("no reader: textutil not available on this machine")
        o, rc, err = run([ctx.bins["textutil"], "-convert", "txt", "-stdout", path], 300)
        if rc != 0 and not o.strip():
            raise RuntimeError("textutil failed: " + err.strip()[:200])
        pages = [{"n": 1, "tier": "text_layer", "text": tidy(o)}]
    elif ext in PLAIN:
        with open(path, "rb") as f:
            pages = [{"n": 1, "tier": "text_layer", "text": tidy(decode(f.read()))}]
    elif cls == "archive" and zipfile.is_zipfile(path):
        names = zipfile.ZipFile(path).namelist()
        pages, status = [{"n": 1, "tier": "listing", "text": "\n".join(names)}], "listed"
    else:
        with open(path, "rb") as f:
            b = f.read(2_000_000)
        t = decode(b)
        if len(b) < 2_000_000 and quality(t) > 0.95 and len(t.strip()) > 20:
            pages = [{"n": 1, "tier": "text_layer", "text": tidy(t)}]
        else:
            pages, status = [], "no_reader"
    tiers = collections.Counter(p["tier"] for p in pages)
    if status is None:
        if tiers.get("pending_vision"):
            status = "needs_vision"
        elif tiers.get("none"):
            status = "partial"
        elif pages and all(p["tier"] == "blank" for p in pages):
            status = "blank"
        else:
            status = "ok"
    missing = [n for n in ("page-ocr", "tesseract") if not ctx.bins[n]]
    if missing and any(p["tier"] in ("pending_vision", "blank", "none", "photo") for p in pages):
        notes.append("local OCR tier not available here: %s" % ", ".join(missing))
    rec = {"id": e["id"], "path": e["current_path"], "class": cls, "status": status,
           "page_count": len(pages), "tiers": dict(tiers), "chars": sum(len(p.get("text", "")) for p in pages),
           "extractor": GEN, "extracted_at": common.now_local(), "pages": pages}
    if notes:
        rec["notes"] = notes
    return rec


OCR_MISSING = "local OCR tier not available here"  # the start of the note `process` records for a missing OCR tool


def retryable(path):
    """Whether `--retry-failed` reads the record at `path` again: it failed, it cannot be read, or the only thing wrong
    with it is a local OCR tier that was missing when it was read (its notes say so), so a corrected `--ocr-bin` or an
    installed tesseract recovers it."""
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return True
    if not isinstance(rec, dict):
        return True
    notes = rec.get("notes")
    return rec.get("status") == "failed" or isinstance(notes, list) and any(
        isinstance(n, str) and n.startswith(OCR_MISSING) for n in notes)


def main():
    ap = common.base_args("Full-text extraction, local tools only")
    ap.add_argument("--lane", choices=["main", "apps"], default="main",
                    help="apps = iWork, legacy office and packages; main = everything else")
    ap.add_argument("--worker", default="0/1")
    ap.add_argument("--retry-failed", action="store_true",
                    help="read again a record that failed, or that was read while a local OCR tier was missing")
    ap.add_argument("--manifest", help="default <root>/_Audit/manifest.json")
    ap.add_argument("--out", help="default <root>/_Audit/extract")
    ap.add_argument("--ocr-bin", help="path to the built page-ocr binary (refused unless an executable file)")
    a = ap.parse_args()
    if a.ocr_bin and not (os.path.isfile(a.ocr_bin) and os.access(a.ocr_bin, os.X_OK)):
        raise common.ToolError("--ocr-bin %s is not an executable file; build the helper (`swiftc -O page_ocr.swift "
                               "-o page-ocr`) and give its path, or leave --ocr-bin out" % a.ocr_bin)
    root, settings_dir, work = common.resolve(a, extract=a.out)
    rb = common.load_rulebook(root, settings_dir)
    langs = rb["ocr_languages"]
    ocr_codes(langs, TESSERACT_LANGS)   # an unknown code fails loud before anything is written
    out = os.path.realpath(a.out) if a.out else os.path.join(root, "_Audit", "extract")
    writer = common.Writer(root if a.read_only_root else None)
    writer.makedirs(out)
    ctx = Ctx(a, root, work, out, langs)
    wi, wn = [int(x) for x in a.worker.split("/")]
    tag = "%s%d" % (a.lane, wi)
    log = common.logger(work, "extract_" + tag)
    log("tools:", {k: bool(v) for k, v in ctx.bins.items()})
    with open(a.manifest or os.path.join(root, "_Audit", "manifest.json"), encoding="utf-8") as f:
        man = json.load(f)
    todo, held = [], collections.Counter()
    for e in sorted(man["entries"].values(), key=lambda x: x["id"]):
        if "departed" in e.get("flags", []):
            continue
        ext = os.path.splitext(e["current_path"])[1].lower()
        is_app = ext in IWORK or ext in LEGACY or bool(e.get("package"))
        if (a.lane == "apps") != is_app:
            continue
        if a.lane == "main" and int(e["id"][:8], 16) % wn != wi:
            continue
        why = common.withheld(rb, e["current_path"])
        if why:
            held[why] += 1  # staged for another project, or excluded by the owner: never read, whatever its flags
            continue
        if e.get("hashed"):
            todo.append(e)
    counts = "held_for_another_project=%d excluded=%d" % (held["migrations"], held["excluded"])
    log("start lane=%s worker=%s todo=%d %s" % (a.lane, a.worker, len(todo), counts))
    os.makedirs(os.path.join(work, "index"), exist_ok=True)
    idx = open(os.path.join(work, "index", "extract_%s.jsonl" % tag), "a", encoding="utf-8")
    done = failed = skipped = 0
    t0 = time.time()
    for i, e in enumerate(todo):
        outp = os.path.join(out, e["id"] + ".json")
        if os.path.exists(outp) and not (a.retry_failed and retryable(outp)):
            skipped += 1
            continue
        ctx.cur = e["id"]
        t1 = time.time()
        try:
            rec = process(ctx, e)
        except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as ex:
            rec = {"id": e["id"], "path": e["current_path"], "class": e["class"], "status": "failed",
                   "error": str(ex)[:500], "pages": [], "page_count": 0, "tiers": {}, "chars": 0,
                   "extractor": GEN, "extracted_at": common.now_local()}
            failed += 1
        writer.json(outp, rec)
        idx.write(json.dumps({"id": e["id"], "status": rec["status"], "pages": rec["page_count"],
                              "tiers": rec["tiers"]}) + "\n")
        idx.flush()
        done += 1
        log("%d/%d %s %s pages=%d %.1fs" % (i + 1, len(todo), rec["status"], e["id"][:12], rec["page_count"],
                                            time.time() - t1))
    idx.close()
    ctx.ocr.close()
    shutil.rmtree(ctx.tmp, True)
    log("finished done=%d failed=%d skipped=%d %s in %.0fs" % (done, failed, skipped, counts, time.time() - t0))
    os.makedirs(os.path.join(work, "state"), exist_ok=True)
    with open(os.path.join(work, "state", "extract_%s.done" % tag), "w") as f:
        f.write(common.now_local())
    return 1 if failed else 0


# ------------------------------------------------------------------------------------ repath

def repath_unsettled(entries):
    """{id: why} for each live entry whose paths the manifest's canonical choice does not settle: copies naming no
    canonical copy, more than one, or one other than the current path, or a current path another live entry also
    holds. Repathing any record of one would guess."""
    out, holders = {}, collections.defaultdict(list)
    for h, e in entries.items():
        if "departed" in e.get("flags", []):
            continue
        cur, copies = e["current_path"], e.get("copies") or []
        canon = [c["path"] for c in copies if c.get("kind") == "canonical"]
        if copies and canon != [cur]:
            out[h] = "%d live paths, canonical %s, current path %r" % (len(copies), canon or "none", cur)
        else:
            holders[cur].append(h)
    for cur, hs in holders.items():
        for h in hs if len(hs) > 1 else []:
            out[h] = "current path %r is also held by %s" % (cur, ", ".join(x[:12] for x in hs if x != h))
    return out


def repath_stage(writer, path, tmp, rec):
    """`rec` written to `tmp`, the temporary file beside `path`, after the writer's guard on `path`."""
    writer.check(path)
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(rec, ensure_ascii=False))
        f.flush()
        os.fsync(f.fileno())


def repath(argv):
    """`extract.py repath`: rewrite each extract record's `path` to its document's current path in the manifest,
    matched by content hash (the record's id). No document is read again and no model is called; nothing else in a
    record changes. A dry run by default. Records of departed documents, and records whose id the manifest does not
    hold, are left as they are and listed. It refuses, naming each and writing nothing (exit 2): a record whose
    document has paths the manifest's canonical choice does not settle (`repath_unsettled`), and a move to a current
    path that is not in the folder (the manifest is older than the folder: re-audit first). --apply writes every
    repathed record to a temporary file beside it, through the guarded writer (--read-only-root refuses a write
    inside the folder), and only then replaces the records. Whatever stops it part way, no temporary file stays: an
    OS error or a refusal is a named error (exit 2) listing the records already replaced, and anything else (an
    interrupt) is raised again once the temporary files are gone."""
    import wiki  # the manifest's one reader, which refuses a malformed one by name
    ap = common.base_args("Repath extract records from the manifest by content hash (no re-read)")
    ap.prog = "extract.py repath"
    ap.add_argument("--manifest", help="default <root>/_Audit/manifest.json")
    ap.add_argument("--out", help="the extract records (default <root>/_Audit/extract)")
    ap.add_argument("--apply", action="store_true", help="write the repathed records (default: a dry run)")
    a = ap.parse_args(argv)
    root, _settings_dir, _work = common.resolve(a, extract=a.out)
    records = os.path.realpath(a.out) if a.out else os.path.join(root, "_Audit", "extract")
    _mpath, entries = wiki.load_manifest(root, a.manifest)
    try:
        names = sorted(n for n in os.listdir(records) if n.endswith(".json"))
    except OSError as e:
        raise common.ToolError("cannot repath: %s" % e)
    unsettled, moves, left, unknown, current = repath_unsettled(entries), [], [], [], 0
    refused = []
    for n in names:
        path = os.path.join(records, n)
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError) as e:
            raise common.ToolError("cannot repath: %s: %s" % (path, e))
        eid = n[:-5]
        if not (isinstance(rec, dict) and rec.get("id") == eid and isinstance(rec.get("path"), str)):
            raise common.ToolError("cannot repath: %s is not an extract record for %s (an id and a path)" % (path, eid))
        e = entries.get(eid)
        if e is None:
            unknown.append([eid, rec["path"]])
        elif "departed" in e.get("flags", []):
            left.append([eid, rec["path"]])
        elif eid in unsettled:
            refused.append("%s (%s): %s" % (eid, rec["path"], unsettled[eid]))
        elif rec["path"] != e["current_path"]:
            moves.append((path, rec, rec["path"], e["current_path"]))
        else:
            current += 1
    if refused:
        raise common.ToolError("refused, nothing written: the manifest does not settle where %d record(s) belong: %s"
                               % (len(refused), "; ".join(refused)))
    absent = ["%s to %r" % (rec["id"], new) for _p, rec, _old, new in moves
              if not os.path.lexists(os.path.join(root, *new.split("/")))]
    if absent:
        raise common.ToolError("refused, nothing written: %d record(s) would move to a path that is not in the folder "
                               "(%s); the manifest is older than the folder: re-audit (audit.py) first, then repath"
                               % (len(absent), "; ".join(absent)))
    if a.apply:
        writer, staged, replaced = common.Writer(root if a.read_only_root else None), [], []
        try:
            for path, rec, _old, new in moves:
                staged.append(("%s.repath%d" % (path, os.getpid()), path))  # recorded before it is opened
                repath_stage(writer, path, staged[-1][0], dict(rec, path=new))
            for tmp, path in staged:
                os.replace(tmp, path)
                replaced.append(os.path.basename(path))
        except BaseException as e:  # whatever stops it, no temporary file stays
            for tmp, _path in staged[len(replaced):]:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            if not isinstance(e, (OSError, common.ToolError)):
                raise
            raise common.ToolError("repath stopped, %s: %s" % (
                "%d record(s) already replaced (%s)" % (len(replaced), ", ".join(replaced)) if replaced
                else "no record replaced", e))
    print(json.dumps(collections.OrderedDict([
        ("records", len(names)), ("applied", a.apply), ("paths_changed", len(moves)),
        ("already_current", current), ("moves", [[rec["id"], old, new] for _p, rec, old, new in moves]),
        ("departed_left", left), ("not_in_manifest", unknown)]), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    common.run_main(lambda: repath(sys.argv[2:]) if sys.argv[1:2] == ["repath"] else main())
