"""Shared helpers for the pre-onboarding tools: settings, guarded writes, logging, JSON parsing.

Standard library only (Python 3.9+). Every tool that writes goes through `Writer`, so `--read-only-root` is enforced
in one place: with it set, any write under the folder being prepared is refused before it happens.
"""
import argparse
import atexit
import datetime
import functools
import hashlib
import json
import os
import re
import shlex
import sys
import time
import unicodedata

RULEBOOK_VERSION = 1
WIKI_SCHEMA_VERSION = 2  # 2: sections by number and name, one routing row per prefix, contracts with a reader
RULEBOOK_FILES = ("CLAUDE.md", "AGENTS.md", "GEMINI.md")
RULEBOOK_SOURCE = "CLAUDE.md"
SETTINGS_DIRNAME = ".familyai"
DEPTHS = ("light", "medium", "full")
IDENTIFIER_POLICIES = ("stated", "last-four", "home-only")


class ToolError(Exception):
    """A named failure a tool reports and exits on; never swallowed."""


class StaleTwin(ToolError):
    """A settings twin that no longer matches its source (`stale`) or records none (`unpinned`)."""

    def __init__(self, state, message):
        super().__init__("%s: %s" % (state, message))
        self.state = state


def clock():
    """Seconds since the epoch. Tests freeze it with PRE_ONBOARDING_NOW (epoch seconds) so outputs can be compared
    byte for byte; nothing else should set it."""
    fixed = os.environ.get("PRE_ONBOARDING_NOW")
    return float(fixed) if fixed else time.time()


def now_local():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(clock()))


def iso_utc(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha256_package(path):
    """Content id of an iWork package (a folder): sha256 over its members in walk order, directories and files
    sorted, each member contributing `relative path`, NUL, the member's sha256 hex, newline. The audit, the plan
    executor and any deployment reading the manifest must use exactly this definition."""
    h = hashlib.sha256()
    for dirpath, dirs, files in os.walk(path):
        dirs.sort()
        for name in sorted(files):
            fp = os.path.join(dirpath, name)
            h.update(os.path.relpath(fp, path).encode() + b"\0" + sha256_file(fp).encode() + b"\n")
    return h.hexdigest()


def content_id(path):
    return sha256_package(path) if os.path.isdir(path) else sha256_file(path)


def is_dataless(path):
    """True for an iCloud file whose bytes are not on this machine (reading it would download it)."""
    try:
        return bool(os.lstat(path).st_flags & 0x40000000)
    except (AttributeError, OSError):
        return False


class Writer:
    """The one place tools write files. With `protect` set to the folder root, any write inside it is refused."""

    def __init__(self, protect=None):
        self.protect = os.path.realpath(protect) if protect else None

    def check(self, path):
        if self.protect:
            real = os.path.realpath(os.path.dirname(os.path.abspath(path)) or ".")
            target = os.path.join(real, os.path.basename(path))
            if target == self.protect or target.startswith(self.protect + os.sep):
                raise ToolError("refused: %s is inside the protected folder (--read-only-root)" % path)
        return path

    def makedirs(self, path):
        self.check(os.path.join(path, "x"))
        os.makedirs(path, exist_ok=True)

    def text(self, path, text):
        self.check(path)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = "%s.tmp%d" % (path, os.getpid())
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def json(self, path, obj, indent=None):
        self.text(path, json.dumps(obj, ensure_ascii=False, indent=indent))

    def append(self, path, text):
        self.check(path)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())


def logger(work, name):
    os.makedirs(os.path.join(work, "logs"), exist_ok=True)
    fh = open(os.path.join(work, "logs", name + ".log"), "a", encoding="utf-8")
    atexit.register(fh.close)

    def log(*parts):
        line = time.strftime("%m-%d %H:%M:%S ") + " ".join(str(p) for p in parts)
        fh.write(line + "\n")
        fh.flush()
        print(line, file=sys.stderr, flush=True)
    return log


def base_args(description, writes=True):
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--root", required=True, help="the folder being prepared")
    ap.add_argument("--settings-dir", help="where rulebook.json and wiki-schema.json live (default <root>/.familyai)")
    ap.add_argument("--work", help="state directory outside the folder (default ~/.ai-os-pre-onboarding/<folder>)")
    if writes:
        ap.add_argument("--read-only-root", action="store_true",
                        help="refuse any write inside --root (use with --out elsewhere to prove a tool)")
    return ap


def resolve(args, verify=True):
    """Normalise the common arguments; returns (root, settings_dir, work). A stale twin is refused here, so every
    tool refuses it, unless `verify` is off: only for settings.py (compile is the remedy, check the diagnosis) and
    readiness.py (which reports the twins' freshness as hand-off findings). A malformed twin fails loud either way
    when it is read."""
    root = os.path.realpath(args.root)
    if not os.path.isdir(root):
        raise ToolError("root missing: %s" % root)
    settings_dir = settings_dir_for(root, args.settings_dir)
    work = os.path.realpath(args.work) if args.work else os.path.join(
        os.path.expanduser("~/.ai-os-pre-onboarding"), re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.basename(root)))
    if work == root or work.startswith(root + os.sep):
        raise ToolError("--work must be outside the folder: %s" % work)
    if verify:
        verify_twins(root, settings_dir)
    os.makedirs(work, exist_ok=True)
    return root, settings_dir, work


def settings_dir_for(root, given=None):
    return os.path.realpath(given) if given else os.path.join(root, SETTINGS_DIRNAME)


def verify_twins(root, settings_dir):
    """Refuse a twin in `settings_dir` that is stale, unpinned or malformed; an absent twin is not an error here."""
    load_rulebook(root, settings_dir)
    load_wiki_schema(root, settings_dir, required=False)


DEFAULTS = {
    "version": RULEBOOK_VERSION,
    "inbox": "_Inbox",
    "migrations_dir": "_Migrations",
    "wiki_dir": None,                 # default: "<folder name> Wiki"
    "reserved": [],
    "depth": "light",
    "packs": [],
    "working_formats": [],
    "active": [],
    "finished": [],
    "people": [],
    "identifiers": "stated",
    "boundaries": [],
    "card_categories": ["Identity & Immigration", "Health", "Education", "Work & Career", "Business",
                        "Finance & Tax", "Home & Household", "Travel", "Language Study", "Photos",
                        "Reference & Reading", "Legal & Correspondence", "Other"],
    "folder_description": "",
    "exclude": [],
    "keep_empty_folders": True,
    "image_cap_mb": 25,
    "pack_keywords": ["application", "passport", "renew", "visa", "submission", "evidence"],
    "ocr_languages": ["en-GB"],       # BCP 47 codes local OCR reads in, most likely first
}


NAME_LISTS = ("reserved", "packs", "working_formats", "active", "finished", "card_categories", "exclude",
              "pack_keywords", "ocr_languages")
SCHEMA_PAGES = ("90 Schema/90 Schema.md", "09 Schema/09 Schema.md")  # in order of precedence
WIKI_SCHEMA_KEYS = ("version", "schema_path", "schema_sha256", "sections", "routing", "contracts", "pages")
WIKI_SCHEMA_ROWS = {
    "sections": {"number": str, "name": str, "kind": str, "derived": bool, "pages": str, "professionals": list},
    "routing": {"prefix": str, "target": str, "section": (str, type(None))},
    "contracts": {"number": str, "name": str, "professionals": list, "reader": (str, type(None)), "questions": list,
                  "fields": list},
}
PAGE_ROW = {"professional": str, "deliverable": str, "tone": str}


def read_json_object(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, RecursionError) as e:  # a record nested too deeply is malformed, never a crash
        raise ToolError("%s: not valid JSON (%s)" % (path, e))
    if not isinstance(data, dict):
        raise ToolError("%s: expected a JSON object" % path)
    return data


EMPTY_PROBES = ("", "a", "Z", "0", " ", "/", "\u00e9", "Visa renewal 2021/Letters")  # names a zero-width keyword matches


def validate_rulebook(data, path):
    """Fail loud on a rulebook.json with an unknown version or key, or a value of the wrong shape."""
    def bad(key, want):
        raise ToolError("%s: %s must be %s, not %r" % (path, key, want, data[key]))

    def is_text(v):
        return isinstance(v, str) and v.strip() != ""
    if data.get("version") != RULEBOOK_VERSION:
        raise ToolError("%s: unsupported version %r" % (path, data.get("version")))
    unknown = set(data) - set(DEFAULTS) - {"rulebook_sha256"}
    if unknown:
        raise ToolError("%s: unknown keys %s" % (path, sorted(unknown)))
    if data.get("rulebook_sha256") and not is_sha256(data["rulebook_sha256"]):
        bad("rulebook_sha256", "a sha256 hex digest")
    for k in NAME_LISTS:
        if k in data and not (isinstance(data[k], list) and all(is_text(x) for x in data[k])):
            bad(k, "a list of non-empty strings")
    for p in data.get("packs", []):
        if p != p.strip() or p.startswith("/") or any(x in ("", ".", "..") for x in p.rstrip("/").split("/")):
            raise ToolError("%s: packs entry %r must be a folder path relative to the folder, with no leading or "
                            "trailing space, no leading /, and no empty, . or .. parts" % (path, p))
    for p in data.get("exclude", []):
        if p != p.strip() or p.startswith("/") or any(x in ("", ".", "..") for x in p.rstrip("/").split("/")):
            raise ToolError("%s: exclude entry %r must be a path relative to the folder, with no leading or trailing "
                            "space, no leading /, and no empty, . or .. parts" % (path, p))
    for k in data.get("pack_keywords", []):
        try:
            re.compile(k)
            re.compile("(%s)" % k)
        except re.error as e:
            raise ToolError("%s: pack_keywords entry %r is not a valid regular expression (%s)" % (path, k, e))
        if any(m is not None and m.end() == m.start() for m in (re.search(k, s, re.I) for s in EMPTY_PROBES)):
            raise ToolError("%s: pack_keywords entry %r can match without consuming any text (an empty name, a "
                            "lookahead), so it would match every folder" % (path, k))
    try:
        re.compile("(" + "|".join(data.get("pack_keywords", [])) + ")")
    except re.error as e:
        raise ToolError("%s: pack_keywords do not combine into one regular expression (%s)" % (path, e))
    if data.get("ocr_languages") == []:
        bad("ocr_languages", "a non-empty list")
    for code in data.get("ocr_languages", []):
        if not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*", code):
            raise ToolError("%s: ocr_languages entry %r is not a BCP 47 language code such as en-GB or zh-Hans"
                            % (path, code))
    for k in ("inbox", "migrations_dir"):
        if k in data and not is_text(data[k]):
            bad(k, "a non-empty string")
    if data.get("wiki_dir") is not None and not is_text(data["wiki_dir"]):
        bad("wiki_dir", "a non-empty string")
    if "folder_description" in data and not isinstance(data["folder_description"], str):
        bad("folder_description", "a string")
    if "depth" in data and data["depth"] not in DEPTHS:
        bad("depth", "one of %s" % ", ".join(DEPTHS))
    if "identifiers" in data and data["identifiers"] not in IDENTIFIER_POLICIES:
        bad("identifiers", "one of %s" % ", ".join(IDENTIFIER_POLICIES))
    if "keep_empty_folders" in data and not isinstance(data["keep_empty_folders"], bool):
        bad("keep_empty_folders", "true or false")
    cap = data.get("image_cap_mb", 1)
    if isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap <= 0:
        bad("image_cap_mb", "a positive number")
    if "boundaries" in data and not isinstance(data["boundaries"], list):
        bad("boundaries", "a list")
    if "people" in data and not isinstance(data["people"], list):
        bad("people", "a list")
    for i, p in enumerate(data.get("people", [])):
        ok = (isinstance(p, dict) and set(p) <= {"name", "also", "who"} and is_text(p.get("name"))
              and isinstance(p.get("also", []), list) and all(is_text(x) for x in p.get("also", []))
              and isinstance(p.get("who", ""), str))
        if not ok:
            raise ToolError("%s: people[%d] must be {\"name\": text, \"also\": [text], \"who\": text}, not %r"
                            % (path, i, p))


def load_rulebook(root, settings_dir, required=False, verify=True):
    """The folder's own settings (twin of its rulebook), merged over the generic defaults. A present file that is
    malformed fails loud, and one that is stale or unpinned is refused unless `verify` is off (only a diagnosis
    reads a twin it does not trust); an absent one is allowed unless `required`."""
    path = os.path.join(settings_dir, "rulebook.json")
    data = {}
    if os.path.exists(path):
        data = read_json_object(path)
        validate_rulebook(data, path)
        if verify:
            check_rulebook_pin(root, data, path)
    elif required:
        raise ToolError("missing folder settings: %s" % path)
    merged = dict(DEFAULTS)
    merged.update(data)
    merged["wiki_dir"] = (merged.get("wiki_dir") or os.path.basename(root) + " Wiki").rstrip("/")
    merged["packs"] = [p.rstrip("/") for p in merged["packs"]]
    merged["exclude"] = [p.rstrip("/") for p in merged["exclude"]]
    merged["_source"] = path if data else None
    check_excluded(root, merged)
    return merged


def check_rulebook_pin(root, data, path):
    src = os.path.join(root, RULEBOOK_SOURCE)
    fix = "review it against %s, then record that file's sha256 as rulebook_sha256" % src
    if not data.get("rulebook_sha256"):
        raise StaleTwin("unpinned", "%s records no rulebook_sha256; %s" % (path, fix))
    if not os.path.exists(src):
        raise StaleTwin("stale", "%s is pinned to %s, which is missing" % (path, src))
    if sha256_file(src) != data["rulebook_sha256"]:
        raise StaleTwin("stale", "%s no longer matches %s, edited since; %s" % (path, src, fix))


def is_sha256(v):
    return isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) is not None


def schema_page(root, wiki_dir):
    """The wiki's Schema page relative to the folder (the first of SCHEMA_PAGES that exists), or None."""
    return next(("%s/%s" % (wiki_dir, rel) for rel in SCHEMA_PAGES
                 if os.path.exists(os.path.join(root, wiki_dir, rel))), None)


def validate_wiki_schema(data, path, recompile):
    """Fail loud on a wiki-schema.json of another version or shape, so no consumer trips over it later."""
    def bad(what):
        raise ToolError("%s: %s; %s" % (path, what, recompile))

    def rows_ok(rows, shape):
        return all(isinstance(r, dict) and set(r) == set(shape)
                   and all(isinstance(r[k], t) and (t is not list or all(isinstance(x, str) for x in r[k]))
                           for k, t in shape.items()) for r in rows)
    if data.get("version") != WIKI_SCHEMA_VERSION:
        bad("unsupported version %r (this tool reads version %d)" % (data.get("version"), WIKI_SCHEMA_VERSION))
    if set(data) != set(WIKI_SCHEMA_KEYS):
        bad("keys %s, expected %s" % (sorted(data), list(WIKI_SCHEMA_KEYS)))
    sp = data["schema_path"]
    if not (isinstance(sp, str) and not os.path.isabs(sp) and ".." not in sp.split("/")
            and any(sp.endswith("/" + rel) for rel in SCHEMA_PAGES)):
        bad("schema_path %r is not a Schema page inside the folder" % (sp,))
    if not is_sha256(data["schema_sha256"]):
        bad("schema_sha256 is not a sha256 hex digest")
    for key, shape in WIKI_SCHEMA_ROWS.items():
        if not (isinstance(data[key], list) and rows_ok(data[key], shape)):
            bad("%s is not a list of %s" % (key, "{%s}" % ", ".join(shape)))
    if not (isinstance(data["pages"], dict) and rows_ok(data["pages"].values(), PAGE_ROW)):
        bad("pages is not a map of page to {%s}" % ", ".join(PAGE_ROW))


def load_wiki_schema(root, settings_dir, required=True):
    """The compiled twin of the wiki's Schema page, refused when the page has changed, gone or been superseded
    since it was compiled; an absent twin is allowed unless `required`."""
    path = os.path.join(settings_dir, "wiki-schema.json")
    compile_cmd = "settings.py compile --root %s" % shlex.quote(root)
    recompile = "recompile it: " + compile_cmd
    if not os.path.exists(path):
        if required:
            raise ToolError("missing %s; compile it: %s" % (path, compile_cmd))
        return None
    data = read_json_object(path)
    validate_wiki_schema(data, path, recompile)
    src = os.path.join(root, data["schema_path"])
    if not os.path.exists(src):
        raise StaleTwin("stale", "%s was compiled from %s, which is missing; restore it, then %s"
                        % (path, src, recompile))
    if sha256_file(src) != data["schema_sha256"]:
        raise StaleTwin("stale", "%s no longer matches %s, edited since; %s" % (path, src, recompile))
    current = schema_page(root, data["schema_path"].rsplit("/", 2)[0])
    if current != data["schema_path"]:
        raise StaleTwin("stale", "%s was compiled from %s, but %s now takes precedence; %s"
                        % (path, src, os.path.join(root, current), recompile))
    return data


def reserved_names(rb):
    """Every top-level name the folder's rulebook reserves: the deployment's rulebook filenames, the settings,
    audit, inbox, migrations and wiki folders, then the folder's own extras (`reserved`)."""
    names = list(RULEBOOK_FILES) + [SETTINGS_DIRNAME, "_Audit", rb["inbox"], rb["migrations_dir"], rb["wiki_dir"]]
    return list(dict.fromkeys(names + rb["reserved"]))


def _nfc(text):
    return unicodedata.normalize("NFC", text)


@functools.lru_cache(maxsize=1 << 16)
def fold(text):
    """A path or a name as every withheld comparison sees it: Unicode NFC, then case-folded, then NFC again. A name
    may be stored decomposed on disk and composed in a page or in rulebook.json, and the folder may be on a file system
    that ignores case (macOS opens `staff/pay.txt` for `Staff/pay.txt`), so two spellings that name one file are
    one name here."""
    return _nfc(_nfc(text).casefold())


def in_migrations(rb, path):
    """True when `path`, relative to the folder with `/` separators, lies under the folder's migrations folder
    (`migrations_dir`, `_Migrations` by default), compared as `fold` compares."""
    return fold(path).startswith(fold(rb["migrations_dir"]).rstrip("/") + "/")


def is_excluded(rb, path):
    """True when `path` is a path the folder's `exclude` lists, or lies under one, compared as `fold` compares."""
    p = fold(path)
    return any(p == e or p.startswith(e + "/") for e in (fold(x).rstrip("/") for x in rb["exclude"]))


def withheld(rb, path):
    """Why a document at `path` is read by no tool, or None. `"migrations"`: it is staged for another project, under
    the migrations folder. `"excluded"`: the owner excluded it from reading (`exclude`, a path and everything under
    it). The one decision `extract.py`, `cards.py`, `vision.py` and `readiness.py` share, whatever a document's flags:
    a withheld document is never read, sent to an engine or queued for one."""
    if in_migrations(rb, path):
        return "migrations"
    return "excluded" if is_excluded(rb, path) else None


def _manifest_entries(root, manifest=None):
    """The entries of the manifest, which is required and checked: a missing or malformed one would otherwise read as
    nothing withheld."""
    path = manifest or os.path.join(root, "_Audit", "manifest.json")
    if not os.path.exists(path):
        raise ToolError("manifest missing: %s; run audit.py first" % path)
    try:
        entries = read_json_object(path).get("entries")
    except OSError as e:
        raise ToolError("cannot read %s (%s)" % (path, e.strerror or e))
    if not isinstance(entries, dict):
        raise ToolError("%s has no \"entries\" object; it is not a manifest audit.py wrote" % path)
    for h, e in entries.items():
        where = e.get("current_path") if isinstance(e, dict) else None
        if not (isinstance(where, str) and where):
            raise ToolError("%s: entry %s has no current_path; re-run audit.py" % (path, h))
    return entries


def withheld_ids(root, rb, manifest=None):
    """{id: why} (as `withheld`) for the manifest's entries whose current path is withheld."""
    return withheld_in(rb, _manifest_entries(root, manifest))


def manifest_view(root, rb, manifest=None):
    """({id: state}, {id: current path}) for every entry of the manifest. A state is `"migrations"` or `"excluded"` when
    the entry's current path is withheld (as `withheld`, whatever its flags), else `"departed"` when it is, else
    `"ok"`: live and included, the only state whose document a tool may read, send to an engine or queue. An id the
    manifest does not hold is none of these, and a caller treats it as not live. The path is what a tool names a
    document by, never the one an extract record kept."""
    entries = _manifest_entries(root, manifest)
    states = {h: withheld(rb, e["current_path"]) or ("departed" if "departed" in e.get("flags", []) else "ok")
              for h, e in entries.items()}
    return states, {h: e["current_path"] for h, e in entries.items()}


def manifest_states(root, rb, manifest=None):
    """{id: state}, as `manifest_view` gives."""
    return manifest_view(root, rb, manifest)[0]


def withheld_in(rb, entries):
    """{id: why} (as `withheld`) for the entries of a manifest already read and checked, whatever their flags."""
    return {h: why for h, e in entries.items() for why in [withheld(rb, e["current_path"])] if why}


WITHHELD_WHY = {"migrations": "held for another project", "excluded": "excluded"}  # how a model-facing text says it


def withheld_paths(rb, entries):
    """{fold(path): why} (as `withheld`) for every path, current and copies', that a live entry withheld by its current
    path holds: a copy of a withheld document at an included path is as withheld as its canonical copy."""
    out = {}
    for e in entries.values():
        why = None if "departed" in e.get("flags", []) else withheld(rb, e["current_path"])
        if why:
            for p in [e["current_path"]] + [c["path"] for c in e.get("copies", [])]:
                out.setdefault(fold(p), why)
    return out


def path_withheld(rb, at, path):
    """Why a path a page, a routing row or a prompt names is withheld, or None: it is a path a withheld entry holds
    (`at`, from `withheld_paths`), or one `withheld` says is, as a file or as a folder (so the folder `Staff` and the
    bare migrations folder are withheld, and a folder holding only one excluded file is not)."""
    bare = path.rstrip("/")
    return at.get(fold(bare)) or withheld(rb, bare) or withheld(rb, bare + "/")


def named_exactly(root, rel):
    """The path of `rel` under `root` when every part is spelled exactly as its folder lists it (case included; both in
    Unicode NFC, as a name may be stored decomposed on disk and composed in rulebook.json), else None."""
    cur = root
    for part in _nfc(rel).split("/"):
        names = {_nfc(n): n for n in os.listdir(cur)} if os.path.isdir(cur) else {}
        if part not in names:
            return None
        cur = os.path.join(cur, names[part])
    return cur


def named_loosely(root, rel):
    """As `named_exactly`, but a part may differ in case and in Unicode form, as `fold` compares."""
    cur = root
    for part in rel.split("/"):
        names = {fold(n): n for n in os.listdir(cur)} if os.path.isdir(cur) else {}
        if fold(part) not in names:
            return None
        cur = os.path.join(cur, names[fold(part)])
    return cur


def check_excluded(root, rb):
    """Fail loud on an `exclude` entry that names no path under `root`, ignoring case and Unicode form (as the
    withheld comparisons do): a typo would exclude nothing, and the owner's exclusion would reach the engines without a
    word. `load_rulebook` calls it, so every tool that reads the settings refuses such an entry before it reads
    anything."""
    for p in rb["exclude"]:
        if named_loosely(root, p) is None:
            raise ToolError("%s: exclude entry %r is not a path under %s (ignoring case and Unicode form); update "
                            "rulebook.json exclude" % (rb.get("_source") or "rulebook.json", p, root))


def pack_matcher(root, rb):
    """A test of whether a folder (relative to the root) lies in a pack: under a folder the rulebook lists in
    `packs`, or matching its `pack_keywords`. The audit marks every copy there `pack`, even a duplicate beside its
    canonical copy, and the plan tools never propose or execute a delete there. A listed pack that is not an existing
    folder under `root`, named exactly (each part compared with its folder's listing, case included; both in Unicode
    NFC, as a name may be stored decomposed on disk and composed in rulebook.json), fails loud: it would match
    nothing and leave its copies deletable without a word."""
    nfc = _nfc
    for p in rb["packs"]:
        cur = named_exactly(root, p)
        if cur is not None and os.path.isdir(cur):
            continue
        raise ToolError("%s: packs entry %r is not an existing folder under %s (names compared exactly); update "
                        "rulebook.json packs (and name it in the rulebook, which `settings.py check` verifies)"
                        % (rb.get("_source") or "rulebook.json", p, root))
    # an empty alternation would match every folder, so no keywords means no keyword matches
    # each keyword on its own (in one alternation a zero-width alternative would shadow the keywords after it),
    # and a match that consumes no text fails loud: no finite probe at load can rule out one like `(?=q)`
    rxs = [(k, re.compile(k, re.I)) for k in rb["pack_keywords"]]
    listed = [nfc(p) + "/" for p in rb["packs"]]

    def is_pack(folder):
        if any((nfc(folder) + "/").startswith(pk) for pk in listed):
            return True
        found = False
        for k, rx in rxs:  # every keyword is checked, so a malformed one is never hidden by an earlier match
            m = rx.search(nfc(folder))  # a name may be stored decomposed on disk, as for packs
            if m is not None and m.end() == m.start():
                raise ToolError("%s: pack_keywords entry %r matched the folder %r without consuming any text; give "
                                "it a pattern that matches part of the folder's name"
                                % (rb.get("_source") or "rulebook.json", k, folder))
            found = found or m is not None
        return found
    return is_pack


def page_voice(ws, page):
    """The professional, deliverable and tone a wiki page (path relative to the wiki folder) is written in: its
    row in the Schema's Page professionals table, else its section's professional when the section names exactly
    one. A page in a section naming several must be listed; that is refused rather than guessed."""
    if page in ws["pages"]:
        return dict(ws["pages"][page], source="page")
    sec = next((s for s in ws["sections"] if page.startswith("%s %s/" % (s["number"], s["name"]))), None)
    if sec is None:
        raise ToolError("page %r is in no section of the Schema's Layout" % page)
    if len(sec["professionals"]) != 1:
        raise ToolError("page %r is not in the Schema's Page professionals table and section %s %s names %d "
                        "professionals (%s); list the page" % (page, sec["number"], sec["name"],
                                                               len(sec["professionals"]),
                                                               "; ".join(sec["professionals"])))
    return {"professional": sec["professionals"][0], "deliverable": None, "tone": None, "source": "section"}


def parse_json(text):
    """The first complete JSON object or array in a model reply, tolerant of code fences and prose around it."""
    s = text.strip()
    dec = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch in "{[":
            try:
                obj, _ = dec.raw_decode(s[i:])
                return obj
            except ValueError:
                continue
    raise ValueError("no JSON object in reply")


def est_tokens(text):
    """ASCII characters over 3.8 plus the others times 1.1, rounded up (in whole numbers, so a sum of pieces never
    undercounts what the pieces make together: a short line is not free)."""
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return -(-(ascii_chars * 50 + (len(text) - ascii_chars) * 209) // 190)


def run_main(fn):
    try:
        sys.exit(fn() or 0)
    except ToolError as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(2)
