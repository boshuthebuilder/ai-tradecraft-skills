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
# What the roll-up writes besides its entries, exactly: its headings, its intro, the line for an empty section, the
# line over its list of what it could not read and the marker of a callout.
ROLL_UP_LINES = frozenset((
    "# Deadlines", "## Upcoming", "## Every year", "## Past", UNREAD, "_None._", "> [!warning]",
    "_File-derived deadlines, rolled up deterministically from page frontmatter " + EM + " do not hand-edit, "
    "regenerated each run. (Calendar events live in `Coming Events`.)_",
    "_These pages, or entries on them, were skipped. Fix their frontmatter so any deadline is picked up:_"))
# The banner an empty roll-up carries over a wiki that has pages, with `{}` for the count of pages it read.
BANNERS = (
    "> The roll-up found no frontmatter deadlines across {} pages.",
    "> **Roll-up found no frontmatter deadlines across {} readable pages " + EM + " likely a keying fault, not a "
    "deadline-free wiki.** Dates recorded in prose are invisible to this roll-up; record each forward date as a "
    "`deadline:`/`deadlines:` key, and each date that falls every year as a `recurring:` key, on the page that owns it "
    "(the reconcile conformance count names the pages to fix).")
UNREAD_HINTS = ("; write the date as MM-DD, month first, or as a day and a month name",
                "; name the date with the key `date`, as in {date: MM-DD, note: ...}")
DATE_ITEM = re.compile(r"\{\s*date:\s*[\"']?([^,\"'}]+?)[\"']?\s*(?:,\s*note:\s*(.*?))?\s*\}")  # {date: ..., note: ...}
DAYS_IN_MONTH = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)  # 02-29 comes round in a leap year
SAYS_NOTHING = re.compile(r"(?i)[\s>*_`|-]*(none|nothing|n/?a)?[\s.*_`|-]*")
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


def banner(line):
    """True for the line an empty roll-up writes about the pages it read (see BANNERS)."""
    for template in BANNERS:
        head, tail = template.split("{}")
        count = line[len(head):len(line) - len(tail)]
        if line.startswith(head) and line.endswith(tail) and count.isascii() and count.isdigit():
            return True
    return False


def parse_links(tail, pages):
    """The pages a roll-up entry links, in order, when `tail` is exactly its links (`[text](target), [text](target)`),
    each text the page's path without `.md` or its title and each target the page's path from the roll-up, percent
    encoded; else None. Plain splitting, each piece bounded, so a long line costs a long line and no more."""
    here, linked, pos = posixpath.dirname(DEADLINES), [], 0
    while len(linked) < 50 and tail.startswith("[", pos):
        mid = tail.find("](", pos + 1, pos + 302)
        end = tail.find(")", mid + 2, mid + 302) if mid > 0 else -1
        if end < 0:
            return None
        target = urllib.parse.unquote(tail[mid + 2:end])
        page = posixpath.normpath(posixpath.join(here, target))
        if (page not in pages or page in linked or target != posixpath.relpath(page, here)
                or tail[pos + 1:mid] not in (page[:-3], posixpath.basename(page)[:-3])):
            return None  # a page is linked once on a line, as the roll-up folds its entries
        linked.append(page)
        pos = end + 1
        if pos == len(tail):
            return linked
        if not tail.startswith(", ", pos):
            return None
        pos += 2
    return None


def parse_entry(line, pages):
    """(the date as written, the note, the pages linked) for a line laid out as the roll-up lays out an entry, else
    None: `- **<date>**`, then ` \u2014 <titles>[ \u2014 <note>]` (family-ai-os) or `: <note>` (the fixture's roll-up),
    then ` (<links>)` ending the line. The titles are the linked pages' own, so a line is split by what its links say
    and not by guessing where a note stops."""
    if not line.startswith("- **"):
        return None
    close = line.find("**", 4, 80)
    rest = line[close + 2:] if close > 0 else ""
    if rest.startswith(" " + EM + " "):
        rest, titled = rest[3:], True
    elif rest.startswith(": "):
        rest, titled = rest[2:], False
    else:
        return None
    end = len(rest)
    for _ in range(8):  # a note may hold " ([" itself, but not many times
        cut = rest.rfind(" ([", 0, end)
        if cut < 0 or not rest.endswith(")"):
            return None
        linked = parse_links(rest[cut + 2:-1], pages)
        if linked:
            break
        end = cut + 2
    else:
        return None
    middle = rest[:cut]
    if not titled:
        return line[4:close], middle, linked
    titles = ", ".join(dict.fromkeys(posixpath.basename(x)[:-3] for x in linked))
    if middle == titles:
        return line[4:close], "", linked
    return (line[4:close], middle[len(titles) + 3:], linked) if middle.startswith(titles + " " + EM + " ") else None


def unread_line(line, pages, refusing):
    """True for a line of the roll-up's own list of what it could not read: `- <page> (<why>)`, the page one of the
    wiki's, and the why one the roll-up writes (a page that cannot be read, a malformed frontmatter, or a recurring
    date it refuses, which that page must hold)."""
    cut = 2
    for _ in range(8):
        cut = line.find(" (", cut)
        if cut < 0 or not line.startswith("- ") or not line.endswith(")"):
            return False
        why = line[cut + 2:-1]
        if line[2:cut] in pages:
            if why == "malformed frontmatter":
                return True
            if why.startswith("unreadable: ") and why[12:].isidentifier():
                return True
            if why.startswith("unreadable recurring date: ") and line[2:cut] in refusing:
                hint = next((h for h in UNREAD_HINTS if why.endswith(h)), None)
                return hint is not None and len(why) - len("unreadable recurring date: ") - len(hint) <= 60
        cut += 2
    return False


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


# ------------------------------------------------------------------------------------ derived pages

def scalar(text):
    """`text` as YAML reads a scalar: a quoted one without its quotes (and the quote written as `''` or `\\"` inside
    it), any other as it is. The roll-up reads the frontmatter with a YAML reader, so a note written
    `"Renew: 2 weeks before"` is rendered without the quotes."""
    text = (text or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        inner = text[1:-1]
        return inner.replace("''", "'") if text[0] == "'" else inner.replace('\\"', '"').replace("\\\\", "\\")
    return text


def date_entry(it):
    """(date, note) of one frontmatter date entry: `{date: ..., note: ...}` (as wiki.py parses it, or as text), or a
    bare date; the note is None when there is none."""
    if isinstance(it, dict):
        return scalar(str(it.get("date", ""))), scalar(it.get("note") or "") or None
    text = str(it).strip()
    m = DATE_ITEM.fullmatch(text)
    return (m.group(1), scalar(m.group(2)) or None) if m else (scalar(text), None)


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
    `deadline`'s note is its `deadline_note`, a bare date has none); whether a `recurring` date is one the roll-up
    refuses) of one page's frontmatter."""
    days, yearly, bad_days, bad, rendered, refused = set(), set(), [], [], set(), False

    def shown(it):
        return it if isinstance(it, str) else json.dumps(it, ensure_ascii=False)

    def written(note):
        return " ".join((note or "").split())
    for key in ("deadline", "deadlines"):
        v = fm.get(key)
        for it in v if isinstance(v, list) else [v] if v else []:
            d, note = date_entry(it)
            if key == "deadline" and note is None and isinstance(fm.get("deadline_note"), str):
                note = scalar(fm["deadline_note"])
            if real_day(d):
                days.add(d)
                rendered.add((d, written(note)))
            else:
                bad_days.append("%s: %s" % (key, shown(it)))
    v = fm.get("recurring")
    for it in v if isinstance(v, list) else [v] if v else []:
        d, note = date_entry(it)
        if month_day(d):
            rendered.add((month_day(d), written(note)))
        else:
            refused = True
        if month_day(d) and note:
            yearly.add(month_day(d))
        else:
            bad.append(shown(it))
    return days, yearly, bad_days, bad, rendered, refused


def deadline_items(wiki, pages, ws):
    """(derived pages hold nothing hand-written, recurring dates in frontmatter, other derived pages): each "ok",
    "finding: ..." or "not verified: ...". The rule is wiki-maintenance's "Deadlines are derived, not authored"
    (../../wiki-maintenance/SKILL.md#rules-that-keep-it-safe), read through the frontmatter keys its roll-up reads
    (#canonical-frontmatter--the-keys-the-deterministic-sweeps-read, including which pages the sweeps skip), with
    01 Deadlines the derived list of forward dates.

    The page may hold only what the roll-up renders from the pages' frontmatter; every other line is reported.
    Each page's frontmatter gives the entries the roll-up could write, `(date, note, page)`: a `recurring` item's
    month and day, a `deadline` with its `deadline_note`, a `deadlines` item's date, each with the note as YAML reads
    it, whitespace collapsed. The page is then read line by line against the roll-up's output grammar (see
    ROLL_UP_LINES, BANNERS, `parse_entry` and `unread_line`): its frontmatter, its headings, intro, `_None._` and
    banner lines, the lines under its own "Could not read" heading, blank lines, and entries, whether laid out as
    family-ai-os lays them out or as the fixture's roll-up does. An entry is split by plain string handling into date,
    note and page links, and is clean only when its `(date, note, page)` is in that set, the dated ones by their full
    date and the recurring ones by month and day. An entry whose date no page carries is reported as that date (a
    YYYY-MM-DD no page's frontmatter carries, or a day and month no page's `recurring` list carries); one whose date is
    not a date the contract reads is an unreadable yearly date; every other line is hand-written content, with its line
    number and its start. Each line is read in one pass, so a long line costs a long line and no more. The roll-up
    must also show every deadline of a page the sweeps read that is not before its `last-updated` (a `last-updated`
    after today is a finding, and forward is then judged from today, the tools' clock) and every recurring date; a
    roll-up with none of those to show says why; and a deadline entry that is not a real YYYY-MM-DD, or a recurring
    entry the contract does not read, is reported. Another page the Schema marks derived (an open-questions list) is
    built from the pages in a way no date shows, so it is named as not verified, apart."""
    derived_dirs = tuple("%s %s/" % (s["number"], s["name"]) for s in (ws or {}).get("sections", []) if s["derived"])
    others = [p for p in pages if p != DEADLINES and p.startswith(derived_dirs)] if derived_dirs else []
    other_item = "not verified: %s (derived, built from the pages in a way no date shows)" % sample(others) \
        if others else "ok"
    if DEADLINES not in pages:
        why = "not verified: no %s (fixed_pages reports it)" % DEADLINES
        return why, why, other_item
    days, yearly = collections.defaultdict(list), collections.defaultdict(list)  # date: the current pages holding it
    swept_days, swept_yearly, bad_days, bad, any_derived = set(), set(), [], [], False
    entries, refusing = set(), set()  # (date, note, page) the roll-up renders; pages with a recurring date it refuses
    for p in pages:
        if p == DEADLINES or p in others:
            continue
        fm, _body, _n = split_page(read(os.path.join(wiki, *p.split("/"))))
        if fm.get("status") == "superseded":
            continue  # no longer the wiki's: the roll-up shows none of its dates
        d, y, bd, b, rendered, refused = frontmatter_dates(fm)
        if not p.endswith((".proposed.md", ".superseded.md")):  # a sibling the roll-up never reads
            entries |= {(key, note, p) for key, note in rendered}
            if refused:
                refusing.add(p)
        for x in d:
            days[x].append(p)
        for x in y:
            yearly[x].append(p)
        if fm.get("provenance") not in ("manual", "calendar"):
            swept_days |= d
            swept_yearly |= y
        bad_days += ["%s: %s" % (p, e) for e in bd]
        bad += ["%s: %s" % (p, e) for e in b]
        any_derived = any_derived or fm.get("provenance") == "derived"
    fm, body, offset = split_page(read(os.path.join(wiki, *DEADLINES.split("/"))))
    derived = []
    stamp = str(fm.get("last-updated", "")).strip().strip("\"'")
    stamp = stamp if real_day(stamp) else None
    today = time.strftime("%Y-%m-%d", time.localtime(common.clock()))
    if stamp and stamp > today:  # a build not yet made: a finding, and forward is judged from today
        derived.append("%s is last-updated %s, after today (%s)" % (DEADLINES, stamp, today))
        stamp = today
    hand, hand_yearly, written, unreadable, shown_days, shown_yearly = [], [], [], [], set(), set()
    page_set, dates, section = set(pages), {key for key, _note, _page in entries}, None
    for n, line in enumerate(body.splitlines(), offset + 1):
        if not line.strip() or line in ROLL_UP_LINES or banner(line):
            section = line if line.startswith("#") else section
            continue
        entry = None if section == UNREAD else parse_entry(line, page_set)
        if section == UNREAD and unread_line(line, page_set, refusing):
            continue
        if entry is None:  # nothing the roll-up writes: a date in it is still the dated check's to judge
            written.append("line %d: %s" % (n, excerpt(line)))
            hand += ["line %d: %s" % (n, m.group(0)) for m in DAY.finditer(line)
                     if m.group(0) not in days and m.group(0) != stamp]
            continue
        when, note, linked = entry
        if DAY.fullmatch(when):
            shown_days.add(when)
            key = when
            if when not in days and when != stamp:
                hand.append("line %d: %s" % (n, when))
                continue
        elif month_day(when):
            key = month_day(when)
            shown_yearly.add(key)
            if key not in dates:
                hand_yearly.append("line %d: %s" % (n, key))
                continue
        else:
            unreadable.append("line %d: %s" % (n, excerpt(when)))
            continue
        if not all((key, note, page) in entries for page in linked):  # not what the pages' frontmatter gives
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
            and not SAYS_NOTHING.fullmatch(line)]
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
            "finding: " + "; ".join(recurring) if recurring else "ok", other_item)


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
        items["other_derived_pages"] = deadline_items(wiki, pages, ws)
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
    return items


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
    out["handoff_contract"] = contract(root, rb, settings_dir, ws, pages, rulebook_text)

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
