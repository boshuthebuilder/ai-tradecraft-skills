"""Read the text out of a modern iWork file (Pages, Numbers, Keynote) without the apps.

iWork 2013+ stores its content as .iwa files: a stream of chunks, each a 4-byte header
(type 0, 3-byte little-endian length) followed by raw Snappy-compressed data. The decompressed
data is a run of protobuf archives. Without the schema we walk every protobuf message generically
and keep the length-delimited fields that are human text. Styles, fonts and identifiers are
filtered out; what remains is the document's words in storage order.
"""
import os, re, zipfile


def snappy_raw(data):
    """Decompress a raw (unframed) Snappy block."""
    pos, n, shift = 0, 0, 0
    while True:
        b = data[pos]; pos += 1
        n |= (b & 0x7F) << shift
        if b < 0x80:
            break
        shift += 7
    out = bytearray()
    L = len(data)
    while pos < L:
        tag = data[pos]; pos += 1
        t = tag & 3
        if t == 0:
            ln = tag >> 2
            if ln >= 60:
                nb = ln - 59
                ln = int.from_bytes(data[pos:pos + nb], "little"); pos += nb
            ln += 1
            out += data[pos:pos + ln]; pos += ln
            continue
        if t == 1:
            ln = ((tag >> 2) & 7) + 4
            off = ((tag >> 5) << 8) | data[pos]; pos += 1
        elif t == 2:
            ln = (tag >> 2) + 1
            off = int.from_bytes(data[pos:pos + 2], "little"); pos += 2
        else:
            ln = (tag >> 2) + 1
            off = int.from_bytes(data[pos:pos + 4], "little"); pos += 4
        if off <= 0 or off > len(out):
            raise ValueError("bad snappy offset")
        start = len(out) - off
        for i in range(ln):
            out.append(out[start + i])
    return bytes(out)


def iwa_decompress(buf):
    pos, out = 0, []
    while pos + 4 <= len(buf):
        ln = int.from_bytes(buf[pos + 1:pos + 4], "little")
        chunk = buf[pos + 4:pos + 4 + ln]
        pos += 4 + ln
        out.append(snappy_raw(chunk) if buf[pos - 4 - ln] == 0 else chunk)
    return b"".join(out)


def varint(b, p):
    r, s = 0, 0
    while True:
        if p >= len(b):
            raise ValueError("eof")
        x = b[p]; p += 1
        r |= (x & 0x7F) << s
        if x < 0x80:
            return r, p
        s += 7
        if s > 63:
            raise ValueError("varint")


def parse_msg(b, depth, out):
    """Generic protobuf walk. Returns False if b is not a well-formed message."""
    p = 0
    fields = []
    while p < len(b):
        key, p = varint(b, p)
        wt, fn = key & 7, key >> 3
        if fn == 0:
            return False
        if wt == 0:
            _, p = varint(b, p)
        elif wt == 1:
            p += 8
        elif wt == 5:
            p += 4
        elif wt == 2:
            ln, p = varint(b, p)
            if p + ln > len(b):
                return False
            fields.append(b[p:p + ln]); p += ln
        else:
            return False
        if p > len(b):
            return False
    for f in fields:
        handle(f, depth, out)
    return True


def is_text(s):
    if len(s) < 2:
        return False
    letters = sum(1 for ch in s if ch.isalpha())
    printable = sum(1 for ch in s if ch.isprintable() or ch in "\n\t  ￼")
    return printable / len(s) > 0.95 and letters >= 2


def handle(f, depth, out):
    if depth < 12 and len(f) >= 2:
        sub = []
        try:
            ok = parse_msg(f, depth + 1, sub)
        except Exception:
            ok = False
        if ok and sub:
            try:
                s = f.decode("utf-8")
                # prefer the string reading when the bytes are plainly prose
                if is_text(s) and (" " in s or re.search(r"[一-鿿]", s)) and len(s) >= 12:
                    out.append(s); return
            except UnicodeDecodeError:
                pass
            out.extend(sub); return
    try:
        s = f.decode("utf-8")
    except UnicodeDecodeError:
        return
    if is_text(s):
        out.append(s)


NOISE = re.compile(r"^(\.?[A-Za-z]+(-[A-Za-z]+)*|[A-Za-z]+[A-Z][A-Za-z]*|[\w.-]+\.(ttf|otf|png|jpe?g|tiff?|pdf|iwa|xml|plist)|"
                   r"[0-9A-F-]{16,}|com\.apple\.[\w.]+|[A-Z][A-Za-z]+(Bold|Italic|Regular|Light|Medium)\w*|"
                   r"(paragraph|character|list|shape|cell|table|chart|image|caption|header|footer|title|body|"
                   r"heading|bullet|none|default|normal|style|label)[\w -]{0,20})$", re.I)


LOCALE = re.compile(r"^(\d(st|nd|rd|th) quarter|Before Christ|Anno Domini|[dMyEHhmsazZLGQw ,:.'/\-]+|"
                    r"Sheet \d+|Sheet \d+_Table \d+|Table \d+)$")


def iwork_text(path):
    """Return a list of text blocks from an iWork package directory or zipped file."""
    blobs = []
    if os.path.isdir(path):
        idx = os.path.join(path, "Index.zip")
        if os.path.exists(idx):
            z = zipfile.ZipFile(idx)
            blobs = [(n, z.read(n)) for n in z.namelist() if n.endswith(".iwa")]
        else:
            for r, _, fs in os.walk(os.path.join(path, "Index")):
                for f in fs:
                    if f.endswith(".iwa"):
                        blobs.append((os.path.relpath(os.path.join(r, f), path), open(os.path.join(r, f), "rb").read()))
    else:
        z = zipfile.ZipFile(path)
        blobs = [(n, z.read(n)) for n in z.namelist() if n.endswith(".iwa")]

    def order(n):
        base = os.path.basename(n[0])
        return (0 if base == "Document.iwa" else 1 if re.match(r"(Slide|Tables|DataList|CalculationEngine)", base) else 2, n[0])

    seen, blocks = set(), []
    for name, data in sorted(blobs, key=order):
        base = os.path.basename(name)
        if re.match(r"(DocumentStylesheet|ThemeStylesheet|AnnotationAuthorStorage|Metadata|DocumentMetadata|ViewState)", base):
            continue
        try:
            raw = iwa_decompress(data)
        except Exception:
            continue
        out = []
        p = 0
        # each archive: varint length, ArchiveInfo, then payload messages; walking the whole
        # stream generically as one message is not valid, so walk archive by archive.
        while p < len(raw):
            try:
                ln, q = varint(raw, p)
                info = raw[q:q + ln]
                p = q + ln
                sizes = []
                # ArchiveInfo.message_infos (field 2) -> MessageInfo.length (field 3)
                ip = 0
                while ip < len(info):
                    k, ip = varint(info, ip)
                    wt, fn = k & 7, k >> 3
                    if wt == 0:
                        _, ip = varint(info, ip)
                    elif wt == 2:
                        l2, ip = varint(info, ip)
                        sub = info[ip:ip + l2]; ip += l2
                        if fn == 2:
                            sp = 0
                            while sp < len(sub):
                                k2, sp = varint(sub, sp)
                                w2, f2 = k2 & 7, k2 >> 3
                                if w2 == 0:
                                    v, sp = varint(sub, sp)
                                    if f2 == 3:
                                        sizes.append(v)
                                elif w2 == 2:
                                    l3, sp = varint(sub, sp); sp += l3
                                elif w2 == 1:
                                    sp += 8
                                elif w2 == 5:
                                    sp += 4
                                else:
                                    break
                    elif wt == 1:
                        ip += 8
                    elif wt == 5:
                        ip += 4
                    else:
                        break
                for sz in sizes:
                    parse_msg(raw[p:p + sz], 0, out)
                    p += sz
            except Exception:
                break
        for s in out:
            s = s.replace("￼", "").replace(" ", "\n").replace(" ", "\n").strip()
            if not s or NOISE.match(s) or s in seen:
                continue
            if not re.search(r"\s", s) and not re.search(r"[一-鿿]", s) and len(s) < 60:
                continue
            if LOCALE.match(s):
                continue
            seen.add(s)
            blocks.append(s)
    return blocks
