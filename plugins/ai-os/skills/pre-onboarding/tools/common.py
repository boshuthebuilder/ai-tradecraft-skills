"""Shared helpers for the pre-onboarding tools: settings, guarded writes, logging, JSON parsing.

Standard library only (Python 3.9+). Every tool that writes goes through `Writer`, so `--read-only-root` is enforced
in one place: with it set, any write under the folder being prepared is refused before it happens.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import time

SETTINGS_VERSION = 1
RULEBOOK_FILES = ("CLAUDE.md", "AGENTS.md", "GEMINI.md")


class ToolError(Exception):
    """A named failure a tool reports and exits on; never swallowed."""


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


def resolve(args):
    """Normalise the common arguments; returns (root, settings_dir, work)."""
    root = os.path.realpath(args.root)
    if not os.path.isdir(root):
        raise ToolError("root missing: %s" % root)
    settings_dir = os.path.realpath(args.settings_dir) if args.settings_dir else os.path.join(root, ".familyai")
    work = os.path.realpath(args.work) if args.work else os.path.join(
        os.path.expanduser("~/.ai-os-pre-onboarding"), re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.basename(root)))
    if work == root or work.startswith(root + os.sep):
        raise ToolError("--work must be outside the folder: %s" % work)
    os.makedirs(work, exist_ok=True)
    return root, settings_dir, work


DEFAULTS = {
    "version": SETTINGS_VERSION,
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
    "pack_keywords": ["visa", r"\bilr\b", "passport", "application", "renew", "settlement", r"\bbrp\b",
                      "申请", "签证", "护照", "身份证"],
}


def load_rulebook(root, settings_dir, required=False):
    """The folder's own settings (twin of its rulebook), merged over the generic defaults. A present file with an
    unknown version or unknown keys fails loud; an absent one is allowed unless `required`."""
    path = os.path.join(settings_dir, "rulebook.json")
    data = {}
    if os.path.exists(path):
        data = json.load(open(path, encoding="utf-8"))
        if data.get("version") != SETTINGS_VERSION:
            raise ToolError("%s: unsupported version %r" % (path, data.get("version")))
        unknown = set(data) - set(DEFAULTS) - {"rulebook_sha256"}
        if unknown:
            raise ToolError("%s: unknown keys %s" % (path, sorted(unknown)))
        rb = os.path.join(root, "CLAUDE.md")
        if data.get("rulebook_sha256") and os.path.exists(rb) and sha256_file(rb) != data["rulebook_sha256"]:
            raise ToolError("stale: %s no longer matches CLAUDE.md; review and update it" % path)
    elif required:
        raise ToolError("missing folder settings: %s" % path)
    merged = dict(DEFAULTS)
    merged.update(data)
    merged["wiki_dir"] = merged.get("wiki_dir") or os.path.basename(root) + " Wiki"
    merged["_source"] = path if data else None
    return merged


def load_wiki_schema(settings_dir, root=None, required=True):
    path = os.path.join(settings_dir, "wiki-schema.json")
    if not os.path.exists(path):
        if required:
            raise ToolError("missing %s: run settings.py compile" % path)
        return None
    data = json.load(open(path, encoding="utf-8"))
    if data.get("version") != SETTINGS_VERSION:
        raise ToolError("%s: unsupported version %r" % (path, data.get("version")))
    if root and data.get("schema_path") and data.get("schema_sha256"):
        sp = os.path.join(root, data["schema_path"])
        if os.path.exists(sp) and sha256_file(sp) != data["schema_sha256"]:
            raise ToolError("stale: %s no longer matches %s; run settings.py compile" % (path, data["schema_path"]))
    return data


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
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return int(ascii_chars / 3.8 + (len(text) - ascii_chars) * 1.1)


def run_main(fn):
    try:
        sys.exit(fn() or 0)
    except ToolError as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(2)
