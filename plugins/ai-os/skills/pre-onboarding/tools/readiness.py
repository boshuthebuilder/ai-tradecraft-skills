#!/usr/bin/env python3
"""Readiness for hand-off: is the prepared folder in the shape an onboarding flow relies on?

Read-only on the folder. Every check reports a count (zero included), a state, a finding or a named not-verified
state, never silence. Every finding is listed in `findings` as [check, what], `check` being the report key that
holds it, and every named not-verified state in `not_verified` the same way: it is not a finding, but it is not a
pass either, and the operator reads it.

- manifest: live, departed, migrating, root strays, redundant copies, hygiene and unconverted iWork entries, and the
  items on disk (reported, not findings); `live_paths_missing`, live entries whose current path is gone, is a
  finding (the manifest is not current: re-audit);
- records: every live hashed document (those `extract.py` reads) has an extract record and a card, each card and
  extract record is in its format (one that is not is counted and named, never the end of the run), each card's
  category is one the rulebook allows, every extract record's path agrees with the manifest (else the finding
  names the repair, `extract.py repath`), and no card names an isolation term its own source lacks (not verified
  without --terms). A check that needed a record it could not read is not verified for that document. A count
  above zero is one finding;
- isolation: per engine, the canary result `isolation.py canary --out` wrote to `<work>/state/canary-<engine>.json`:
  `passed (model M, effort E)`, naming the model that was cleared, to compare with the model the cards ran on,
  `failed: ...` (a finding), `not run: ...` (not verified) or `not verified: ...` (a pass recorded without
  the invented name the canary now plants, so one from an earlier canary, which a refusal could pass: run it again);
- wiki: `wiki.py check`, as it reports; its problems are one finding, its not-verified states are listed;
- wiki_handoff: the rationale file exists (`check` does not count it missing, since drafting agents run `check`
  before it is assembled), and every page is accepted: each page `check` does not report `accepted` is one
  finding, naming the page, its state and why (a refused page included), except a page `check` lists in
  `acceptance_not_verified` (its professional and contract cannot be read), whose acceptance is not verified;
  `records_for_no_page` (records naming a page the wiki no longer holds) is information only;
- rulebook: `CLAUDE.md` and `AGENTS.md` present, valid UTF-8, identical and naming the wiki folder; scratch: no
  folder in `_Audit/` but the prepared folder's own (`plans`, `extract`, `cards`);
- handoff_contract, each "ok", "finding: ..." or "not verified: ...": the wiki folder is `<folder name> Wiki`; the
  fixed pages 00 Index, 01 Deadlines, 90 Schema and 91 Log exist; derived pages hold nothing hand-written (the
  Deadlines page holds only what the roll-up renders from the pages' frontmatter, and every other line is reported)
  and recurring dates live in page frontmatter, with any other derived page not verified (see `deadline_items`); the
  rulebook reserves the deployment's rulebook filenames and routes no new file to the migrations folder (read by
  keyword, see `contract`); both settings twins present and fresh.

Numbered sections are held by `check`: a page outside every Layout section of the compiled Schema is one of its
problems. Exit 0 when nothing is found, 1 on any finding, 2 on a tool error (a missing or malformed manifest, such
as a live entry without `hashed` true or false, or canary result, or a crash). A malformed card or extract record is
a finding, never a tool error.

    python3 readiness.py --root R [--terms F] [--manifest M] [--out <json>]
"""
import collections
import datetime
import json
import os
import posixpath
import re
import shlex
import sys
import time
import traceback
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cards as C  # noqa: E402
import common  # noqa: E402
import isolation  # noqa: E402
import wiki as W  # noqa: E402

FIXED = ("00 Index/00 Index.md", "01 Deadlines/01 Deadlines.md", "90 Schema/90 Schema.md", "91 Log/91 Log.md")
DEADLINES = FIXED[1]
AUDIT_DIRS = ("plans", "extract", "cards")  # the folders a prepared folder's _Audit/ holds; any other is scratch
CANARY_ENGINES = ("agy", "codex")  # isolation.py canary --engine
FRONTMATTER = re.compile(r"---\n(.*?)\n---\n", re.S)  # as wiki.py check reads it
DAY = re.compile(r"(?<![0-9])[0-9]{4}-[0-9]{2}-[0-9]{2}(?![0-9])")  # a dated deadline, as the roll-up writes it
ISO_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")  # spelt out: calendar.month_name follows the locale
MONTH_NUMBER = dict([(m.lower(), n) for n, m in enumerate(MONTHS, 1)]
                    + [(m[:3].lower(), n) for n, m in enumerate(MONTHS, 1)] + [("sept", 9)])
ORDINAL = r"(?:st|nd|rd|th)?"
EM = "\u2014"  # the roll-up's separator, as data: family-ai-os writes `- **5 April** \u2014 Tax \u2014 note (links)`
UNREAD = "## Could not read"
TITLE, MARKER = "# Deadlines", "> [!warning]"
INTRO = ("_File-derived deadlines, rolled up deterministically from page frontmatter " + EM + " do not hand-edit, "
         "regenerated each run. (Calendar events live in `Coming Events`.)_")
UNREAD_INTRO = "_These pages, or entries on them, were skipped. Fix their frontmatter so any deadline is picked up:_"
# What the roll-up writes besides its entries, exactly: its headings, its intro, the line for an empty section, the
# line over its list of what it could not read and the marker of a callout.
ROLL_UP_LINES = frozenset((TITLE, "## Upcoming", "## Every year", "## Past", UNREAD, "_None._", MARKER, INTRO,
                           UNREAD_INTRO))
# The banner an empty roll-up carries over a wiki that has pages, with `{}` for the count of pages it read: a callout
# of two lines (the marker, then the text) or one line.
BANNERS = (
    "> The roll-up found no frontmatter deadlines across {} pages.",
    "> **Roll-up found no frontmatter deadlines across {} readable pages " + EM + " likely a keying fault, not a "
    "deadline-free wiki.** Dates recorded in prose are invisible to this roll-up; record each forward date as a "
    "`deadline:`/`deadlines:` key, and each date that falls every year as a `recurring:` key, on the page that owns it "
    "(the reconcile conformance count names the pages to fix).")
DATE_HINT = "; write the date as MM-DD, month first, or as a day and a month name"
KEY_HINT = "; name the date with the key `date`, as in {date: MM-DD, note: ...}"
DAYS_IN_MONTH = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)  # 02-29 comes round in a leap year
SAMPLE = 5


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def month_day(s):
    """The `MM-DD` a yearly date names, or None. Read as family-ai-os reads it, so both sides accept the same
    spellings: `MM-DD`, month first, two digits each; or a day with an English month name, the day first or the
    month first (`5 April`, `April 5`), the name in full, its first three letters or `sept`, in any case, the day
    with an optional ordinal (`5th Apr`). Any other numeric form is None (`6/4` reads either way round), and so is a
    day the month cannot have (`31 April`); 29 February comes round in a leap year, so it is a date."""
    s = (s or "").strip()
    m = re.fullmatch(r"([0-9]{2})-([0-9]{2})", s)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
    else:
        m = (re.fullmatch(r"([0-9]{1,2})%s\s+([A-Za-z]+)" % ORDINAL, s)
             or re.fullmatch(r"([A-Za-z]+)\s+([0-9]{1,2})%s" % ORDINAL, s))
        if not m:
            return None
        word, number = (m.group(2), m.group(1)) if m.group(1).isdigit() else (m.group(1), m.group(2))
        month, day = MONTH_NUMBER.get(word.lower(), 0), int(number)
    if not (1 <= month <= 12 and 1 <= day <= DAYS_IN_MONTH[month - 1]):
        return None
    return "%02d-%02d" % (month, day)


def rendered_month_day(md):
    """The form the roll-up writes a yearly date in: the day, then the month's name (`5 April`)."""
    return "%d %s" % (int(md[3:]), MONTHS[int(md[:2]) - 1])


def banner(line):
    """0 for the callout text of an empty roll-up, 1 for its one-line banner (see BANNERS), else None; the count of
    pages in either is one number."""
    for kind, template in enumerate(BANNERS):
        head, tail = template.split("{}")
        count = line[len(head):len(line) - len(tail)]
        if line.startswith(head) and line.endswith(tail) and count.isascii() and count.isdigit():
            return kind
    return None


def says_nothing(line):
    """True for a line that is only markup, or markup around `none`, `nothing` or `n/a`, in one pass."""
    start = 0
    while start < len(line) and (line[start].isspace() or line[start] in ">*_`|-"):
        start += 1
    for word in ("", "nothing", "none", "n/a", "na"):
        stop = start + len(word)
        if line[start:stop].lower() == word and all(c.isspace() or c in ".*_`|-" for c in line[stop:]):
            return True
    return False


def parse_entry(line, pages):
    """(the date as written, the note, the pages linked) for a line laid out as the roll-up lays out an entry, else
    None: `- **<date>**`, then the titles and the note, each after a spaced em dash (family-ai-os), or `: <note>` (the
    fixture's roll-up), then ` (<links>)` ending the line. The links are read from the end of the line, each a page
    of the wiki named by its path from the roll-up and written as its path without `.md` or its title, so a page name
    holding brackets is read by its own text; the titles are the linked pages' own, so a note is never guessed at.
    Plain string handling, one pass over the line."""
    if not line.startswith("- **") or not line.endswith(")"):
        return None
    close = line.find("**", 4)
    if close < 0:
        return None
    if line.startswith(" " + EM + " ", close + 2):
        body, titled = close + 5, True
    elif line.startswith(": ", close + 2):
        body, titled = close + 4, False
    else:
        return None
    here, linked, taken, pos = posixpath.dirname(DEADLINES), [], set(), len(line) - 1
    while True:
        mid = line.rfind("](", body, pos - 1) if pos > body and line[pos - 1] == ")" else -1
        if mid < 0:
            return None
        target = urllib.parse.unquote(line[mid + 2:pos - 1])
        page = posixpath.normpath(posixpath.join(here, target))
        if page in taken or page not in pages or target != posixpath.relpath(page, here):
            return None
        for text in (page[:-3], posixpath.basename(page)[:-3]):
            if line[mid - len(text) - 1:mid] == "[" + text and mid - len(text) - 1 >= body:
                start = mid - len(text) - 1
                break
        else:
            return None
        linked.append(page)
        taken.add(page)
        if start - 2 >= body and line.startswith(", ", start - 2):
            pos = start - 2
        elif start - 2 >= body and line.startswith(" (", start - 2):
            cut = start - 2
            break
        else:
            return None
    linked.reverse()
    middle = line[body:cut]
    if not titled:
        return line[4:close], middle, linked
    titles = ", ".join(dict.fromkeys(posixpath.basename(x)[:-3] for x in linked))
    if middle == titles:
        return line[4:close], "", linked
    return (line[4:close], middle[len(titles) + 3:], linked) if middle.startswith(titles + " " + EM + " ") else None


def excerpt(line):
    """The start of `line`, for a finding: an invisible character is shown as its code."""
    shown = "".join(c if c.isprintable() else "\\u%04x" % ord(c) for c in line[:40])
    return shown + ("..." if len(line) > 40 else "")


def sample(items):
    shown = "; ".join(str(x) for x in items[:SAMPLE])
    return shown + (" and %d more" % (len(items) - SAMPLE) if len(items) > SAMPLE else "")


def split_page(text):
    """(frontmatter, body, the number of lines before the body)."""
    m = FRONTMATTER.match(text)
    return (W.parse_fm(m.group(1)), text[m.end():], text[:m.end()].count("\n")) if m else ({}, text, 0)


# ------------------------------------------------------------------------------------ the frontmatter this check reads

MAX_LINE, MAX_BLOCK = 20000, 200000  # a longer line or block is not read: the time to read it is bounded by this
KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
INDICATORS = {"&": "an anchor", "*": "an alias", "!": "a tag", "|": "a block scalar", ">": "a folded scalar",
              "%": "a directive", "@": "a reserved indicator", "`": "a reserved indicator"}
FLOW_STOP = re.compile(r"[,}\[\]{#:]")
DERIVED_NAMES = frozenset(("index.md", "log.md", "deadlines.md", "coming events.md", "open questions.md", "schema.md",
                           "conventions.md"))  # pages the roll-up never reads as a source, as family-ai-os names them


class OutOfScope(Exception):
    """A frontmatter construct this check does not read; the argument names it."""


class Malformed(Exception):
    """A frontmatter the roll-up cannot read as a mapping, for a reason that needs no YAML reader to see."""


class Scalar:
    """A scalar of the frontmatter: its text (None for no value), whether it was quoted, and how it was written."""
    __slots__ = ("text", "quoted", "raw")

    def __init__(self, text, quoted, raw):
        self.text, self.quoted, self.raw = text, quoted, raw


class Mapping(dict):
    """The pairs of a flow or block mapping, {key: Scalar} in order, with the text it was written as in `raw`."""
    raw = ""


def quoted(s, i):
    """(the value, the index after it) of the quoted scalar of `s` opening at `i`, or None when it never closes on
    the line. A `'` scalar writes its quote twice; a `"` scalar escapes `"` and `\\` with a backslash, and its other
    escapes are not read. It scans in place, so a line of many quoted scalars is read in one pass."""
    quote, parts, j = s[i], [], i + 1
    while True:
        k = s.find(quote, j)
        if k < 0:
            return None
        if quote == '"':
            b = s.find("\\", j, k)
            if b >= 0:
                if s[b + 1:b + 2] not in ('"', "\\"):
                    raise OutOfScope("an escape in a double-quoted scalar")
                parts.append(s[j:b] + s[b + 1])
                j = b + 2
                continue
        parts.append(s[j:k])
        if quote == "'" and s.startswith("''", k):
            parts.append("'")
            j = k + 2
            continue
        return "".join(parts), k + 1


def after(s, k):
    """The index of the first character of `s` from `k` that is not a space or a tab."""
    while k < len(s) and s[k] in " \t":
        k += 1
    return k


def comment_only(tail):
    """True when `tail` is empty or only a comment (a space, then `#`)."""
    return not tail.strip() or tail[:1] in " \t" and tail.lstrip().startswith("#")


def flow_scalar(s, j, is_key):
    """(the Scalar of the flow mapping `s` at `j`, the index after it): quoted, or plain up to the next comma or `}`
    (and for a key its colon), so an unquoted comma ends a value and what follows is a key of its own."""
    j = after(s, j)
    if j >= len(s):
        raise OutOfScope("a flow mapping that does not close on its line")
    c = s[j]
    if c in "'\"":
        got = quoted(s, j)
        if got is None:
            raise OutOfScope("an unclosed quote")
        k = after(s, got[1])
        if k >= len(s) or s[k] not in (",", "}") and not (is_key and s[k] == ":"):
            raise OutOfScope("text after a quoted scalar")
        return Scalar(got[0], True, s[j:got[1]]), k
    if c in INDICATORS:
        raise OutOfScope(INDICATORS[c])
    if c in "[{":
        raise OutOfScope("a nested flow collection")
    k = j
    while True:
        m = FLOW_STOP.search(s, k)
        if not m:
            raise OutOfScope("a flow mapping that does not close on its line")
        p, ch = m.start(), m.group()
        if ch in ",}":
            break
        if ch == ":":
            if s[p + 1:p + 2] in ("", " ", "\t", ",", "}"):
                if is_key:
                    break
                raise OutOfScope("a colon and space inside a plain scalar")
        elif ch == "#":
            if s[p - 1:p] in " \t":
                raise OutOfScope("a comment inside a flow mapping")
        else:
            raise OutOfScope("brackets in a plain scalar of a flow mapping")
        k = p + 1
    text = s[j:p].strip()
    return Scalar(text or None, False, text), p


def flow_mapping(s, i):
    """(the Mapping of the flow mapping of `s` opening at `i`, the index after its `}`): on one line, its values
    scalars, an unquoted comma ending each."""
    pairs, j = Mapping(), i + 1
    while True:
        j = after(s, j)
        if j >= len(s):
            raise OutOfScope("a flow mapping that does not close on its line")
        if s[j] == "}":
            pairs.raw = s[i:j + 1]
            return pairs, j + 1
        key, j = flow_scalar(s, j, True)
        value = Scalar(None, False, "")
        if key.text is None:
            raise OutOfScope("an empty key in a flow mapping")
        if j < len(s) and s[j] == ":":
            value, j = flow_scalar(s, j + 1, False)
        if j < len(s) and s[j] == ",":
            j += 1
        elif j >= len(s) or s[j] != "}":
            raise OutOfScope("text after a flow mapping value")
        pairs[key.text] = value


def block_value(rest):
    """What follows `key:` or a list dash, as a Scalar, a Mapping (a flow mapping), [] (for `[]`), or None for no
    value. A plain scalar ends at ` #`, where a comment starts; a quoted one is without its quotes."""
    rest = rest.lstrip(" ")
    if not rest or rest.startswith("#"):
        return None
    c = rest[0]
    if c in "'\"":
        got = quoted(rest, 0)
        if got is None:
            raise OutOfScope("an unclosed quote")
        if not comment_only(rest[got[1]:]):
            raise OutOfScope("text after a quoted scalar")
        return Scalar(got[0], True, rest[:got[1]])
    if c in INDICATORS:
        raise OutOfScope(INDICATORS[c])
    if c == "[":
        if rest.startswith("[]") and comment_only(rest[2:]):
            return []
        raise OutOfScope("a flow sequence")
    if c == "{":
        mapping, k = flow_mapping(rest, 0)
        if not comment_only(rest[k:]):
            raise OutOfScope("text after a flow mapping")
        return mapping
    if c in "-?:" and rest[1:2] in ("", " "):
        raise OutOfScope("a block indicator inside a value")
    cut = rest.find(" #")
    text = (rest[:cut] if cut >= 0 else rest).strip()
    if ": " in text or text.endswith(":"):
        raise OutOfScope("a colon and space inside a plain scalar")
    return Scalar(text, False, text)


def key_of(line, start=0):
    """The key of a plain `key: value` pair of `line` from `start`, and the index of its value, else None."""
    m = KEY.match(line, start)
    if m and line[m.end():m.end() + 1] == ":" and line[m.end() + 1:m.end() + 2] in ("", " "):
        return m.group(), m.end() + 1
    return None


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def skippable(line):
    return not line.strip() or line.lstrip().startswith("#")


def read_list(lines, i):
    """(the items, the index after them) of the block list under the key whose line is just before line `i`, or
    (None, i) when none follows. An item is a flow mapping, a `key: value` mapping of plain pairs over its lines, or a
    scalar."""
    n, items, indent, j = len(lines), [], None, i
    while j < n:
        line = lines[j]
        if skippable(line):
            j += 1
            continue
        k = indent_of(line)
        if len(line) > MAX_LINE:
            raise OutOfScope("a line over %d characters" % MAX_LINE)
        if line[k:k + 1] == "\t":
            raise OutOfScope("a tab for indentation")
        if not (line[k] == "-" and line[k + 1:k + 2] in ("", " ")):
            break
        if indent not in (None, k):
            raise OutOfScope("list items at different indents")
        indent = k
        at = after(line, k + 1)
        body, j = line[at:], j + 1
        if not body or body.startswith("#"):
            raise OutOfScope("an item on the lines after its dash")
        if body[0] == "[":
            raise OutOfScope("a flow sequence")
        if body[0] == "-" and body[1:2] in ("", " "):
            raise OutOfScope("a nested list")
        first = key_of(body)
        if body[0] == "{" or first is None:
            value = block_value(body)
            items.append(value)
            continue
        pairs, raws = Mapping(), []
        key, start = first
        while True:
            value = block_value(body[start:])
            if not isinstance(value, Scalar):
                raise OutOfScope("a nested block in a list item")
            pairs[key] = value
            raws.append("%s: %s" % (key, value.raw))
            while j < n and skippable(lines[j]):
                j += 1
            if j >= n or indent_of(lines[j]) < at:
                break
            if indent_of(lines[j]) > at or key_of(lines[j], at) is None:
                raise OutOfScope("a nested block in a list item")
            if len(lines[j]) > MAX_LINE:
                raise OutOfScope("a line over %d characters" % MAX_LINE)
            body, (key, start), j = lines[j][at:], key_of(lines[j], at), j + 1
            start -= at
        pairs.raw = "{" + ", ".join(raws) + "}"
        items.append(pairs)
    return (items, j) if items else (None, i)


def read_frontmatter(text):
    """The frontmatter of a page as {key: value} within the subset this check reads, `{}` for a page that opens none:
    a fence at column 0 and plain `key: value` pairs at column 0, their values plain, single-quoted or double-quoted
    scalars (an empty quoted one is kept as an empty string), a flow mapping of one line, or a block list of flow
    mappings, of mappings of plain pairs, or of scalars, with a ` #` comment after a scalar or a closing `}`. Raises
    Malformed for a page the roll-up cannot read as a mapping whatever YAML says (a fence that never closes, a
    list or a bare word where the keys should be), and OutOfScope, naming it, for any other construct."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        raise Malformed()
    if end > MAX_BLOCK:
        raise OutOfScope("frontmatter over %d characters" % MAX_BLOCK)
    lines = [x.rstrip("\r") for x in text[3:end].split("\n")]
    if lines[0].strip():
        raise OutOfScope("text after the opening fence")
    lines = lines[1:]
    content = [x.lstrip() for x in lines if not skippable(x)]
    if content and (content[0] == "-" or content[0].startswith("- ") or content[0][0] not in "{?&*!|>%@`\"'["
                    and not any(":" in x for x in content)):
        raise Malformed()
    fm, i = {}, 0
    while i < len(lines):
        line, i = lines[i], i + 1
        if skippable(line):
            continue
        if len(line) > MAX_LINE:
            raise OutOfScope("a line over %d characters" % MAX_LINE)
        if line[0] == "\t":
            raise OutOfScope("a tab for indentation")
        if line[0] == " ":
            raise OutOfScope("indented frontmatter" if not fm else "a multi-line scalar or an indented block")
        if line.startswith("? ") or line == "?":
            raise OutOfScope("a `? ` key")
        if line.rstrip() == "...":
            raise OutOfScope("a document end marker")
        if line.startswith("- ") or line.rstrip() == "-":
            raise OutOfScope("a block sequence that is not under a key")
        if line[0] in INDICATORS or line[0] in "\"'[{":
            raise OutOfScope(INDICATORS.get(line[0], "a key that is not a plain word"))
        pair = key_of(line)
        if pair is None:
            raise OutOfScope("a line that is not a plain `key: value` pair")
        key, start = pair
        value = block_value(line[start:])
        if value is None:
            value, i = read_list(lines, i)
        if key == "status" and isinstance(value, Scalar) and value.quoted:
            raise OutOfScope("a quoted status")
        fm[key] = value
    return fm


def yaml_value(text, was_quoted):
    """The Python value YAML gives a scalar, so far as a refused item shows it: a plain date, whole number or decimal
    is one (`datetime.date(2025, 1, 31)`), nothing is None; the rest, `yes`, `12:30`, `null` and the escapes of a
    quoted scalar apart, is the text. A quoted scalar is always its text, an empty one included."""
    if was_quoted:
        return text
    if not text:
        return None
    try:
        if ISO_DAY.fullmatch(text):
            return datetime.date(int(text[:4]), int(text[5:7]), int(text[8:]))
        if re.fullmatch(r"[-+]?[0-9]+", text):
            return int(text)
        if re.fullmatch(r"[-+]?[0-9]*\.[0-9]+", text):
            return float(text)
    except ValueError:
        pass
    return text


def items_of(value):
    """The list items a key's value stands for: a list is its items, a lone scalar or mapping is one item, and no
    value is none."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [] if isinstance(value, Scalar) and value.text is None and not value.quoted else [value]


def date_entry(it):
    """(date, note) of one frontmatter date item, a Mapping (`date` and `note`) or a Scalar (a bare date); the note
    is None when there is none."""
    if isinstance(it, Mapping):
        date, note = it.get("date"), it.get("note")
        return (date.text or "") if date else "", (note.text or None) if note else None
    return it.text or "", None


def refused_item(it):
    """What the roll-up writes for a `recurring` item it refuses, `repr(item)[:60]` and the way to write it, or None
    when it reads the item: its date must be a month and day as `month_day` reads."""
    if isinstance(it, Mapping):
        item = {key: yaml_value(value.text, value.quoted) for key, value in it.items()}
        date, keyed = item.get("date"), True
    else:
        item = yaml_value(it.text, it.quoted)
        date, keyed = item, False
    if isinstance(date, str) and month_day(date):
        return None
    return repr(item)[:60] + (KEY_HINT if keyed and "date" not in item else DATE_HINT)


# ------------------------------------------------------------------------------------ derived pages

def real_day(s):
    """True for `YYYY-MM-DD` naming a day the calendar has."""
    if not ISO_DAY.fullmatch(s or ""):
        return False
    try:
        datetime.date(int(s[:4]), int(s[5:7]), int(s[8:]))
    except ValueError:
        return False
    return True


def frontmatter_dates(fm):
    """(the YYYY-MM-DD dates in `deadline` and `deadlines`, each a date or {date, note}; the MM-DD dates in
    `recurring`, each as MM-DD; the `deadline` and `deadlines` entries not read as a real YYYY-MM-DD; the `recurring`
    entries not in the form {date, note}, the date read by `month_day`, with a note; the entries the roll-up renders
    from this page, as {(date, note)}, the date a YYYY-MM-DD or an MM-DD and the note as the roll-up writes it (a
    `deadline`'s note is its `deadline_note`, a bare date has none); what the roll-up writes for each `recurring` item
    it refuses) of one page's frontmatter, read by `read_frontmatter`. A date is the first ten characters of its
    text, as the roll-up reads it."""
    days, yearly, bad_days, bad, rendered, refused = set(), set(), [], [], set(), []

    def written(note):
        return " ".join((note or "").split())
    for key in ("deadline", "deadlines"):
        for it in items_of(fm.get(key)):
            d, note = date_entry(it)
            d = d.strip()[:10]
            if key == "deadline" and note is None and isinstance(fm.get("deadline_note"), Scalar):
                note = fm["deadline_note"].text
            if real_day(d):
                days.add(d)
                rendered.add((d, written(note)))
            else:
                bad_days.append("%s: %s" % (key, it.raw))
    for it in items_of(fm.get("recurring")):
        d, note = date_entry(it)
        if month_day(d):
            rendered.add((month_day(d), written(note)))
        got = refused_item(it)
        if got:
            refused.append(got)
        if month_day(d) and note:
            yearly.add(month_day(d))
        else:
            bad.append(it.raw)
    return days, yearly, bad_days, bad, rendered, refused


def roll_up_pages(wiki):
    """Every `.md` page under the wiki folder as the roll-up lists them, relative with `/` separators, sorted: pages
    under a dot folder and dot files too, which `wiki.py check` leaves out."""
    out = []
    for d, ds, fs in os.walk(wiki):
        ds.sort()
        out += [os.path.relpath(os.path.join(d, f), wiki).replace(os.sep, "/") for f in sorted(fs) if f.endswith(".md")]
    return sorted(out)


def read_by_roll_up(p):
    """False for a page the roll-up never reads as a source: its derived pages, and a page's `.proposed.md` and
    `.superseded.md` siblings."""
    name = posixpath.basename(p)
    return not (name.endswith((".proposed.md", ".superseded.md")) or re.sub(r"^[0-9]{1,2}\s+", "", name).lower()
                in DERIVED_NAMES)


def deadline_items(wiki, pages, ws):
    """(derived pages hold nothing hand-written, recurring dates in frontmatter, other derived pages, the pages whose
    frontmatter this check does not read): the first three each "ok", "finding: ..." or "not verified: ...", the last a
    list of "not verified: ..." states. The rule is wiki-maintenance's "Deadlines are derived, not authored"
    (../../wiki-maintenance/SKILL.md#rules-that-keep-it-safe), read through the frontmatter keys its roll-up reads
    (#canonical-frontmatter--the-keys-the-deterministic-sweeps-read, including which pages the sweeps skip), with
    01 Deadlines the derived list of forward dates.

    The page may hold only what the roll-up renders from the pages' frontmatter; every other line is reported.
    What the roll-up could write is worked out from the pages, every `.md` under the wiki folder bar its derived pages
    and the `.proposed.md` and `.superseded.md` siblings, each read by `read_frontmatter` (a defined subset of YAML,
    plain, quoted and flow scalars with a comma ending a flow value and ` #` a comment): its entries, `(date, note,
    page)`; the pages it could not read, whose frontmatter is malformed, or whose `recurring` dates it refuses, as the
    lines of its "Could not read" list, each as many times as the roll-up writes it. A page whose frontmatter uses
    YAML outside that subset is named as not verified, and the judgements that need it are withheld: whether an
    entry is backed by the pages, and the "Could not read" list; every line outside the roll-up's grammar is
    still reported. The page is then read line by line against that grammar (see ROLL_UP_LINES, BANNERS and
    `parse_entry`): its frontmatter, which holds only `provenance: derived`, `status: current` and a `last-updated`
    day, once each; its headings, intro, `_None._` and blank lines; the empty-roll-up banner, only directly after the
    intro or title and, when the pages are read, only when they give no entry; the lines under its "Could not read"
    heading, each one the roll-up writes; and entries, laid out as family-ai-os lays them out or as the fixture's
    roll-up does. An entry is split by plain string handling into date, note and page links, and is clean only when
    its date is in the form the roll-up writes (`5 April`, `YYYY-MM-DD`) and its `(date, note, page)` is in that set,
    the dated ones by their full date and the recurring ones by month and day. An entry whose date no page carries is
    reported as that date (a YYYY-MM-DD no page's frontmatter carries, or a day and month no page's `recurring` list
    carries); one whose date is not a date the contract reads is an unreadable yearly date; every other line, a line
    that appears twice included, is hand-written content, with its line number and its start. Each line is read in
    one pass, so a long line costs a long line and no more. The roll-up must also show every deadline of a page the
    sweeps read that is not before its `last-updated` (a `last-updated` after today is a finding, and forward is
    then judged from today, the tools' clock) and every recurring date; a roll-up with none of those to show says
    why; and a deadline entry that is not a real YYYY-MM-DD, or a recurring entry the contract does not read, is
    reported. Another page the Schema marks derived (an open-questions list) is built from the pages in a way no date
    shows, so it is named as not verified, apart. A Deadlines page that cannot be read as UTF-8 is a finding."""
    derived_dirs = tuple("%s %s/" % (s["number"], s["name"]) for s in (ws or {}).get("sections", []) if s["derived"])
    others = [p for p in pages if p != DEADLINES and p.startswith(derived_dirs)] if derived_dirs else []
    other_item = "not verified: %s (derived, built from the pages in a way no date shows)" % sample(others) \
        if others else "ok"
    if DEADLINES not in pages:
        why = "not verified: no %s (fixed_pages reports it)" % DEADLINES
        return why, why, other_item, []
    days, yearly = collections.defaultdict(list), collections.defaultdict(list)  # date: the current pages holding it
    swept_days, swept_yearly, bad_days, bad, any_derived = set(), set(), [], [], False
    entries, unread, outside = set(), collections.Counter(), []  # what the roll-up renders and could not read
    every = roll_up_pages(wiki)
    for p in every:
        if p == DEADLINES or p in others or not read_by_roll_up(p):
            continue
        try:
            text = read(os.path.join(wiki, *p.split("/")))
        except (OSError, UnicodeDecodeError) as e:  # a malformed page: wiki.py check counts it, and so does the roll-up
            unread["- %s (unreadable: %s)" % (p, type(e).__name__)] += 1
            continue
        try:
            fm = read_frontmatter(text)
        except Malformed:
            unread["- %s (malformed frontmatter)" % p] += 1
            continue
        except OutOfScope as e:
            outside.append("not verified: %s uses YAML this check does not read (%s)" % (p, e))
            continue
        if fm.get("status") is not None and getattr(fm["status"], "text", None) == "superseded":
            continue  # no longer the wiki's: the roll-up shows none of its dates
        d, y, bd, b, rendered, refused = frontmatter_dates(fm)
        entries |= {(key, note, p) for key, note in rendered}
        unread.update("- %s (unreadable recurring date: %s)" % (p, why) for why in refused)
        for x in d:
            days[x].append(p)
        for x in y:
            yearly[x].append(p)
        provenance = getattr(fm.get("provenance"), "text", None)
        if provenance not in ("manual", "calendar"):
            swept_days |= d
            swept_yearly |= y
        bad_days += ["%s: %s" % (p, e) for e in bd]
        bad += ["%s: %s" % (p, e) for e in b]
        any_derived = any_derived or provenance == "derived"
    verified = not outside  # every page read: what the roll-up could write is known
    try:
        text = read(os.path.join(wiki, *DEADLINES.split("/")))
    except (OSError, UnicodeDecodeError) as e:  # a hand-kept table saved by another editor: a finding, not a crash
        return ("finding: %s cannot be read as UTF-8 text (%s)" % (DEADLINES, type(e).__name__),
                "not verified: %s cannot be read" % DEADLINES, other_item, outside)
    fm, body, offset = split_page(text)
    derived = []
    stamp = str(fm.get("last-updated", "")).strip().strip("\"'")
    stamp = stamp if real_day(stamp) else None
    today = time.strftime("%Y-%m-%d", time.localtime(common.clock()))
    if stamp and stamp > today:  # a build not yet made: a finding, and forward is judged from today
        derived.append("%s is last-updated %s, after today (%s)" % (DEADLINES, stamp, today))
        stamp = today
    hand, hand_yearly, written, unreadable, shown_days, shown_yearly = [], [], [], [], set(), set()
    page_set, dates, section, seen, prev = set(every), {key for key, _note, _page in entries}, None, set(), None
    frontmatter = FRONTMATTER.match(text)
    keys = set()
    for n, line in enumerate(frontmatter.group(1).split("\n") if frontmatter else [], 2):
        key = line.partition(":")[0]
        if line.strip() and (key in keys or not (line in ("provenance: derived", "status: current")
                                                 or line.startswith("last-updated: ") and real_day(line[14:]))):
            written.append("line %d: %s" % (n, excerpt(line)))  # the roll-up writes three keys, once each
        keys.add(key)
    for n, line in enumerate(body.splitlines(), offset + 1):
        if not line.strip():
            continue
        before, prev = prev, line
        if section == UNREAD and line not in ROLL_UP_LINES:  # a line of its list, once for each the roll-up writes
            if verified and not unread[line]:
                written.append("line %d: %s" % (n, excerpt(line)))
            unread[line] -= 1
            continue
        if line in seen:  # a line the roll-up writes once
            written.append("line %d: %s" % (n, excerpt(line)))
            continue
        seen.add(line)
        if line in ROLL_UP_LINES and line != MARKER:
            section = line if line.startswith("#") else section
            continue
        kind = banner(line)
        if line == MARKER or kind is not None:  # the banner of an empty roll-up, in the place the roll-up puts it
            if (not entries or not verified) and (before == MARKER if kind == 0 else before in (INTRO, TITLE)):
                continue
            written.append("line %d: %s" % (n, excerpt(line)))
            continue
        entry = parse_entry(line, page_set)
        if entry is None:  # nothing the roll-up writes: a date in it is still the dated check's to judge
            written.append("line %d: %s" % (n, excerpt(line)))
            if verified:
                hand += ["line %d: %s" % (n, m.group(0)) for m in DAY.finditer(line)
                         if m.group(0) not in days and m.group(0) != stamp]
            continue
        when, note, linked = entry
        if DAY.fullmatch(when):
            shown_days.add(when)
            key = when
            if verified and when not in days and when != stamp:
                hand.append("line %d: %s" % (n, when))
                continue
        elif month_day(when):
            key = month_day(when)
            if when != rendered_month_day(key):  # a spelling the roll-up does not write: hand-edited
                written.append("line %d: %s" % (n, excerpt(line)))
                continue
            shown_yearly.add(key)
            if verified and key not in dates:
                hand_yearly.append("line %d: %s" % (n, key))
                continue
        else:
            unreadable.append("line %d: %s" % (n, excerpt(when)))
            continue
        if verified and not all((key, note, page) in entries for page in linked):  # not what the pages give
            written.append("line %d: %s" % (n, excerpt(line)))
    if hand:
        derived.append("%s holds %d date(s) no current page's frontmatter carries (%s)"
                       % (DEADLINES, len(hand), sample(hand)))
    if written:
        derived.append("%s holds hand-written content in a derived page, %d line(s) (%s)"
                       % (DEADLINES, len(written), sample(written)))
    forward = {d for d in swept_days if stamp is None or d >= stamp}  # one before the roll-up's build is past
    missing = ["%s (%s)" % (d, ", ".join(days[d])) for d in sorted(forward - shown_days)]
    if missing:
        derived.append("%s lacks %d page deadline(s) (%s)" % (DEADLINES, len(missing), sample(missing)))
    if bad_days:
        derived.append("%d deadline entr(ies) not a real YYYY-MM-DD or {date, note} (%s)"
                       % (len(bad_days), sample(bad_days)))
    says = [line for line in body.splitlines() if line.strip() and not line.lstrip().startswith("#")
            and not says_nothing(line)]
    if not forward and not swept_yearly and any_derived and not says:  # nothing to list, and no word why
        derived.append("%s is an empty roll-up that does not say why" % DEADLINES)
    recurring = []
    if hand_yearly:
        recurring.append("%s holds %d yearly date(s) no page's recurring: list carries (%s)"
                         % (DEADLINES, len(hand_yearly), sample(hand_yearly)))
    if unreadable:
        recurring.append("%s holds %d unreadable yearly date(s) (%s); a yearly date is a page's recurring: entry, "
                         "MM-DD (month first) or a day and a month name, and a dated one is YYYY-MM-DD in deadline:"
                         % (DEADLINES, len(unreadable), sample(unreadable)))
    if bad:
        recurring.append("%d recurring: entr(ies) not {date, note} with a date as MM-DD (month first) or a day and "
                         "a month name, a day the month has (%s)"
                         % (len(bad), sample(bad)))
    missing = ["%s (%s)" % (d, ", ".join(yearly[d])) for d in sorted(swept_yearly - shown_yearly)]
    if missing:
        recurring.append("%s lacks %d recurring date(s) (%s)" % (DEADLINES, len(missing), sample(missing)))
    return ("finding: " + "; ".join(derived) if derived else "ok",
            "finding: " + "; ".join(recurring) if recurring else "ok", other_item, outside)


# ------------------------------------------------------------------------------------ the hand-off contract

def contract(root, rb, settings_dir, ws, pages, rulebook_text):
    items = collections.OrderedDict()
    wiki = os.path.join(root, rb["wiki_dir"])
    folder_wiki = os.path.basename(root) + " Wiki"
    items["wiki_folder_named_after_folder"] = "ok" if rb["wiki_dir"] == folder_wiki else \
        "finding: the wiki folder is %r, not %r" % (rb["wiki_dir"], folder_wiki)
    missing = [p for p in FIXED if p not in pages]
    items["fixed_pages"] = "ok" if not missing else "finding: missing %s" % ", ".join(missing)
    items["derived_pages_hold_nothing_hand_written"], items["recurring_dates_in_frontmatter"], \
        items["other_derived_pages"], outside = deadline_items(wiki, pages, ws)
    # The rulebook is prose, read by keyword and substring: each filename written anywhere in it reserves it, and a
    # line naming the migrations folder with "new file", "dropped", "goes to" or "go to" routes new files there.
    if rulebook_text is None:
        items["rulebook_reserves_rulebook_filenames"] = items["new_files_routed_within_folder"] = \
            "not verified: CLAUDE.md missing (rulebook.present reports it)"
    else:
        unreserved = [n for n in common.RULEBOOK_FILES if n not in rulebook_text]
        items["rulebook_reserves_rulebook_filenames"] = "ok" if not unreserved else \
            "finding: the rulebook does not reserve %s" % ", ".join(unreserved)
        routes_out = [line.strip() for line in rulebook_text.splitlines() if rb["migrations_dir"] + "/" in line
                      and re.search(r"(?i)new file|dropped|goes to|go to", line)]
        items["new_files_routed_within_folder"] = "ok" if not routes_out else \
            "finding: the rulebook routes new files to %s/ (%d line(s)); migrations are the owner's cross-project " \
            "synthesis to propose" % (rb["migrations_dir"], len(routes_out))
    try:
        common.load_rulebook(root, settings_dir, required=True)
        items["settings_rulebook_json"] = "ok"
    except common.ToolError as e:
        items["settings_rulebook_json"] = "finding: %s" % e
    try:
        common.load_wiki_schema(root, settings_dir, required=True)
        items["settings_wiki_schema_json"] = "ok"
    except common.ToolError as e:
        items["settings_wiki_schema_json"] = "finding: %s" % e
    return items, outside


# ------------------------------------------------------------------------------------ the other checks

def manifest_counts(root, man, ents, summary_path):
    live = {h: e for h, e in ents.items() if "departed" not in e.get("flags", [])}
    summ = W.read_object(summary_path) if os.path.exists(summary_path) else {}
    gone = sorted(e["current_path"] for e in live.values()
                  if not os.path.lexists(os.path.join(root, e["current_path"])))
    return live, gone, collections.OrderedDict([
        ("generated_at", man.get("generated_at")), ("live_entries", len(live)),
        ("departed_entries", len(ents) - len(live)),
        ("migrating", sum("migrating" in e.get("flags", []) for e in live.values())),
        ("root_strays", sum("root_stray" in e.get("flags", []) for e in live.values())),
        ("redundant_copies", sum(1 for e in live.values() for c in e.get("copies", [])
                                 if c.get("kind") == "redundant")),
        ("hygiene", sum("hygiene" in e.get("flags", []) for e in live.values())),
        ("unconverted_iwork", sum("unconverted" in e.get("flags", []) for e in live.values())),
        ("items_on_disk", summ.get("items", "not verified: no summary.json beside the manifest")),
        ("live_paths_missing", len(gone))])


def within(root, text):
    """`text` with the folder's own path taken off, so a finding names a file as the folder holds it."""
    return text.replace(os.path.join(root, ""), "")


def unread(n, paths, why):
    """`n`, the count a check made, or a named not-verified state when `paths` are documents it could not read."""
    if not paths:
        return n
    gap = "not verified for %d document(s) whose %s" % (len(paths), why)
    return gap if not n else "%d; %s" % (n, gap)


def record_checks(root, rb, live, evidence):
    """{check: [what, ...]} for the records, and each check's count or state. A card or extract record that cannot be
    read is counted with the rest and never the end of the check; a check that needed it says it is not verified."""
    audit = os.path.join(root, "_Audit")
    xdir, cdir = os.path.join(audit, "extract"), os.path.join(audit, "cards")
    found = collections.OrderedDict((k, []) for k in ("missing_extracts", "missing_cards", "malformed_cards",
                                                      "malformed_extracts", "bad_category", "extract_paths_stale",
                                                      "contamination"))
    no_extract, no_terms = [], []  # documents whose extract record could not be read; whose terms check could not run
    for h, e in sorted(live.items(), key=lambda kv: kv[1]["current_path"]):
        if not isinstance(e.get("hashed"), bool):
            raise common.ToolError("manifest entry %s (%s) records no hashed true or false; it is not a manifest "
                                   "audit.py wrote: re-run audit.py" % (h, e["current_path"]))
        if not e["hashed"]:
            continue  # counted only, never read: extract.py makes no record for it
        path = e["current_path"]
        try:
            card = W.load_card(cdir, h)
        except common.ToolError as ex:  # counted with the rest, never the end of the check
            found["malformed_cards"].append("%s: %s" % (path, within(root, str(ex).split(": ", 2)[-1])))
            card = False
        x = None
        if os.path.exists(os.path.join(xdir, h + ".json")):
            try:
                x = W.load_extract(xdir, h, os.path.join(cdir, h + ".json"))
            except common.ToolError as ex:
                found["malformed_extracts"].append("%s: %s" % (path, within(root, str(ex).split(": ", 1)[-1])))
                no_extract.append(path)
                x = False
        if x is None:
            found["missing_extracts"].append(path)
        elif x is not False and x.get("path") != path:
            found["extract_paths_stale"].append("%r is now %r" % (x.get("path"), path))
        if card is None:
            found["missing_cards"].append(path)
            continue
        if card is False:
            no_terms.append(path)
            continue
        if card.get("category") not in rb["card_categories"]:
            found["bad_category"].append("%s: %r" % (path, card.get("category")))
        if x is False:
            no_terms.append(path)
        elif evidence and x is not None:
            blob = json.dumps({k: v for k, v in card.items() if k != "card_meta"}, ensure_ascii=False)
            if isolation.contamination(blob, C.full_text(x), evidence):
                found["contamination"].append(path)  # the terms themselves are never written out
    counts = collections.OrderedDict((k, len(v)) for k, v in found.items())
    counts["extract_paths_stale"] = unread(counts["extract_paths_stale"], no_extract, "extract record is malformed")
    if not evidence:
        counts["contamination"] = "not verified: no --terms"
    else:
        counts["contamination"] = unread(counts["contamination"], no_terms, "card or extract record is malformed")
    return found, counts


def canary(work, engine):
    """passed, failed: ..., not run: ... or not verified: ..., from the result isolation.py canary wrote."""
    rel = os.path.join("state", "canary-%s.json" % engine)
    path = os.path.join(work, rel)
    if not os.path.exists(path):
        return "not run: no %s in the work directory (isolation.py canary --out)" % rel
    res = W.read_object(path)
    if res.get("engine") != engine or not isinstance(res.get("pass"), bool):
        raise common.ToolError("%s is not a canary result for %s; run isolation.py canary again" % (path, engine))
    if res["pass"]:
        if res.get("answered") is not True or not res.get("marker"):
            return ("not verified: %s records a pass without the invented name a canary now plants, so it may be from "
                    "a canary a refusal could pass; run isolation.py canary again" % rel)
        effort = res.get("effort")  # agy's is in its model id; the cards' model is `card_meta.model`, to compare by eye
        return "passed (model %s%s)" % (res.get("model", "not recorded"), ", effort %s" % effort if effort else "")
    if "reply" in res and res.get("answered") is not False:
        why = "%s isolation term(s) in the engine's reply" % res.get("hits")
    else:  # no reply at all, or one in neither of the canary's forms (a refusal): the reason is the error
        why = "the engine gave no usable answer (%s)" % res.get("error", "no error recorded")
    return "failed: %s, checked %s" % (why, res.get("checked_at"))


def repath_command(a):
    """The command that repaths the records. The paths are `<root>`, `<work>` and so on for the operator to fill in:
    a finding never carries a path of the machine it was run on."""
    cmd = ["extract.py", "repath", "--root", "<root>"]
    for flag, value, name in (("--settings-dir", a.settings_dir, "<settings-dir>"), ("--work", a.work, "<work>"),
                              ("--manifest", a.manifest, "<manifest>")):
        if value:
            cmd += [flag, name]
    return " ".join(cmd + ["--apply"])


def main():
    ap = common.base_args("Readiness for hand-off")
    ap.add_argument("--terms", help="the operator's isolation terms file (contamination is not verified without it)")
    ap.add_argument("--out")
    ap.add_argument("--manifest", help="default <root>/_Audit/manifest.json")
    a = ap.parse_args()
    # A diagnosis, not a gate: a stale or unpinned twin is a hand-off finding below, so the settings are read here
    # without trusting them (as settings.py check does). A malformed rulebook.json still fails loud.
    root, settings_dir, work = common.resolve(a, verify=False)
    rb = common.load_rulebook(root, settings_dir, verify=False)
    mpath, ents = W.load_manifest(root, a.manifest)
    evidence = isolation.load_terms(a.terms) if a.terms else None
    audit = os.path.join(root, "_Audit")
    wiki = os.path.join(root, rb["wiki_dir"])
    pages = W.wiki_pages(wiki)
    try:
        ws = common.load_wiki_schema(root, settings_dir, required=False)
    except common.ToolError:
        ws = None  # a stale or malformed twin: handoff_contract.settings_wiki_schema_json reports it
    claude, agents = (os.path.join(root, n) for n in ("CLAUDE.md", "AGENTS.md"))
    not_utf8, rulebook_text = [], None
    for p in (claude, agents):
        if os.path.exists(p):
            with open(p, "rb") as f:
                raw = f.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as e:  # a finding, as settings.py check makes it; the rest read it as it is
                not_utf8.append("%s (byte %d)" % (os.path.basename(p), e.start))
                text = raw.decode("utf-8", "replace")
            rulebook_text = text if p == claude else rulebook_text

    out = collections.OrderedDict()
    live, gone, out["manifest"] = manifest_counts(root, W.read_object(mpath), ents,
                                                  os.path.join(os.path.dirname(mpath), "summary.json"))
    found, out["records"] = record_checks(root, rb, live, evidence)
    out["isolation"] = {"canary": collections.OrderedDict((e, canary(work, e)) for e in CANARY_ENGINES)}
    out["wiki"] = W.check_result(root, rb, ents, settings_dir=settings_dir)
    rows = out["wiki"]["acceptance_pages"]
    cannot_read = set(out["wiki"]["acceptance_not_verified"])  # no readable professional and contract to judge by
    unverifiable = [row for row in rows if row[0] in cannot_read and row[1] == "not recorded"]
    not_accepted = [row for row in rows if row[1] != "accepted" and row not in unverifiable]  # a refusal stands
    out["wiki_handoff"] = collections.OrderedDict([
        ("rationale_file", "finding: _Audit/wiki-rationale.md is missing; wiki.py rationale assembles it from the "
                           "drafters' returns" if out["wiki"]["rationale"] == "not recorded" else "ok"),
        ("pages_accepted", "%d/%d" % (len(rows) - len(not_accepted) - len(unverifiable), len(rows))),
        ("pages_not_accepted", len(not_accepted)), ("pages_not_verified", len(unverifiable)),
        ("records_for_no_page", out["wiki"]["acceptance_records_for_no_page"])])  # information: records stay as made
    missing = [os.path.basename(p) for p in (claude, agents) if not os.path.exists(p)]
    out["rulebook"] = collections.OrderedDict([
        ("present", "finding: missing %s" % " and ".join(missing) if missing else "ok"),
        ("valid_utf8", "finding: not valid UTF-8: %s" % ", ".join(not_utf8) if not_utf8 else "ok"),
        ("copies_identical", "not verified: %s missing" % " and ".join(missing) if missing
         else common.sha256_file(claude) == common.sha256_file(agents)),
        ("names_wiki_folder", "not verified: CLAUDE.md missing" if rulebook_text is None
         else rb["wiki_dir"] in rulebook_text)])
    out["scratch"] = {"left_in_audit": sorted(d for d in os.listdir(audit) if d not in AUDIT_DIRS
                                              and os.path.isdir(os.path.join(audit, d)))
                      if os.path.isdir(audit) else []}
    out["handoff_contract"], outside = contract(root, rb, settings_dir, ws, pages, rulebook_text)

    findings, unverified = [], []
    if gone:
        findings.append(["manifest.live_paths_missing", "%d live entr(ies) whose current path is gone (%s); "
                         "re-audit (audit.py)" % (len(gone), sample(gone))])
    if isinstance(out["manifest"]["items_on_disk"], str):
        unverified.append(["manifest.items_on_disk", out["manifest"]["items_on_disk"]])
    what = {"missing_extracts": "live document(s) with no extract record",
            "missing_cards": "live document(s) with no card",
            "malformed_cards": "card(s) not in the card format; re-card them (cards.py work --redo)",
            "malformed_extracts": "extract record(s) not in the extract format; remove each and run extract.py again",
            "bad_category": "card(s) with a category the rulebook does not allow",
            "extract_paths_stale": "extract record(s) whose path the manifest no longer holds",
            "contamination": "card(s) naming an isolation term their own source lacks"}
    for key, hits in found.items():
        if hits:
            fix = ""
            if key == "extract_paths_stale":
                fix = ("; repath them: %s" if not found["malformed_extracts"] else
                       "; repath refuses a record that is not valid JSON, not a JSON object, or without its id and "
                       "path, so remove or redo any such malformed extract record first, then repath them: %s"
                       ) % repath_command(a)
            findings.append(["records." + key, "%d %s (%s)%s" % (len(hits), what[key], sample(hits), fix)])
    for key in ("extract_paths_stale", "contamination"):
        if isinstance(out["records"][key], str):
            unverified.append(["records." + key, out["records"][key]])
    for engine, state in out["isolation"]["canary"].items():
        if state.startswith("failed"):
            findings.append(["isolation.canary." + engine, state])
        elif state.startswith(("not run", "not verified")):
            unverified.append(["isolation.canary." + engine, state])
    if out["wiki"]["problems"]:
        findings.append(["wiki.problems", "wiki.py check reports %d problem(s); %d backticked path(s) were not checked "
                         "against the folder (a pattern, or outside the live folders)"
                         % (out["wiki"]["problems"], out["wiki"]["backticked_paths_unchecked"])])
    for key, value in out["wiki"].items():
        for k, v in (value.items() if isinstance(value, dict) else [(None, value)]):
            if isinstance(v, str) and v.startswith("not verified"):
                unverified.append([".".join(x for x in ("wiki", key, k) if x), v])
    if out["wiki_handoff"]["rationale_file"] != "ok":
        findings.append(["wiki_handoff.rationale_file", out["wiki_handoff"]["rationale_file"]])
    for page, state, why in not_accepted:
        findings.append(["wiki_handoff.pages_not_accepted", "%s: %s (%s)" % (page, state, why)])
    if unverifiable:
        unverified.append(["wiki_handoff.pages_not_verified", "%d page(s) whose acceptance cannot be judged: their "
                           "professional and contract cannot be read (%s)"
                           % (len(unverifiable), sample([row[0] for row in unverifiable]))])
    said = {"copies_identical": "CLAUDE.md and AGENTS.md differ; copy CLAUDE.md over AGENTS.md",
            "names_wiki_folder": "the rulebook does not name the wiki folder %r" % rb["wiki_dir"]}
    for key, value in out["rulebook"].items():
        if value is False or isinstance(value, str) and value.startswith("finding"):
            findings.append(["rulebook." + key, said[key] if value is False else value])
        elif isinstance(value, str) and value.startswith("not verified"):
            unverified.append(["rulebook." + key, value])
    if out["scratch"]["left_in_audit"]:
        findings.append(["scratch.left_in_audit", "folders left in _Audit/: %s" % sample(
            out["scratch"]["left_in_audit"])])
    for key, value in out["handoff_contract"].items():
        if value.startswith("finding"):
            findings.append(["handoff_contract." + key, value])
        elif value.startswith("not verified"):
            unverified.append(["handoff_contract." + key, value])
    unverified += [["handoff_contract.frontmatter_read", why] for why in outside]  # pages the check does not read
    out["findings"], out["not_verified"] = findings, unverified
    out["summary"] = collections.OrderedDict([("findings", len(findings)), ("not_verified", len(unverified))])
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out:
        common.Writer(root if a.read_only_root else None).text(a.out, text)
    print(text)
    return 1 if findings else 0


def run():
    """A crash is a tool error (exit 2), never read as findings (exit 1)."""
    try:
        common.run_main(main)
    except Exception:  # noqa: BLE001 (anything not caught above is a crash)
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    run()
