#!/usr/bin/env python3
"""obsidian.py — the editor setup: build `.obsidian/` from the method's manifest, and check it.

    obsidian.py write --root <wiki folder or vault> [--manifest <file>] [--cache <dir>] [--upgrade] [--json]
    obsidian.py check --root <wiki folder or vault> [--manifest <file>] [--json]

`--root` is the folder the owner opens as the vault: a project's wiki folder, or a user vault's root. The manifest
(`obsidian-profile.json` beside this tool unless `--manifest` names another) pins each required plugin by id, GitHub
repo, version, the sha256 of its three release assets and its `data.json`, and names the core plugins, the `app.json`
keys and the device-state files the tool never touches. `write` fetches each asset from the plugin's GitHub release
with the standard library (a per-machine cache keeps a second vault offline), verifies its hash before anything is
written, and merges rather than clobbers; `check` reports the setup against the manifest. Obsidian's own first-open
question (trust the vault's plugins) is answered by the owner, once per machine: it lives in Obsidian's app storage,
not in the vault, so neither command sees or sets it. The convention is wiki-maintenance's *The editor setup*; the
contract is references/tools.md.

Exit codes: 0 complete or nothing to do; 1 findings (`check`); 2 a bad root, manifest or argument; 3 an asset could
not be fetched or failed its hash (`write` names it and writes nothing for that plugin).
"""
import argparse
import hashlib
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MANIFEST = os.path.join(HERE, "obsidian-profile.json")
PROFILE_VERSION = 1
ASSETS = ("main.js", "manifest.json", "styles.css")
NOSOURCEMAP = b"\n/* nosourcemap */"  # what Obsidian's own installer appends to a main.js it installs
RELEASE_URL = "https://github.com/%s/releases/download/%s/%s"
USER_AGENT = "ai-os-obsidian/1"
SETTINGS_FILES = ("app.json", "appearance.json", "core-plugins.json", "community-plugins.json")
EXIT_FETCH = 3
NAME = re.compile(r"(?!\.+$)[A-Za-z0-9._-]+")  # a plugin id or version: one path part, never . or ..
REPO = re.compile(r"(?!\.+/)[A-Za-z0-9._-]+/(?!\.+$)[A-Za-z0-9._-]+")  # owner/name, each one such part


class FetchError(common.ToolError):
    """An asset that could not be fetched or failed its hash: exit 3, never 2."""


# ---- the manifest ----------------------------------------------------------------------------------------------

def default_cache():
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Caches/ai-os/obsidian")
    return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "ai-os", "obsidian")


def load_manifest(path):
    """The manifest, validated: fail loud on a shape the tool would misread."""
    if not os.path.isfile(path):
        raise common.ToolError("manifest missing: %s" % path)
    m = common.read_json_object(path)

    def bad(what):
        raise common.ToolError("%s: %s" % (path, what))
    if m.get("profile_version") != PROFILE_VERSION:
        bad("unsupported profile_version %r" % m.get("profile_version"))
    for key, kind in (("core_plugins", list), ("app", dict), ("appearance", dict), ("never", list),
                      ("plugins", list)):
        if not isinstance(m.get(key), kind):
            bad("%s must be a %s" % (key, kind.__name__))
    for key in ("core_plugins", "never"):
        if not all(isinstance(x, str) and x for x in m[key]):
            bad("%s must be a list of non-empty strings" % key)
    seen = set()
    for i, p in enumerate(m["plugins"]):
        ok = (isinstance(p, dict) and all(isinstance(p.get(k), str) and p[k] for k in ("id", "repo", "version"))
              and isinstance(p.get("assets"), dict) and set(p["assets"]) == set(ASSETS)
              and all(common.is_sha256(v) for v in p["assets"].values()) and isinstance(p.get("data"), dict)
              and isinstance(p.get("desktop_only", False), bool))
        if not ok:
            bad("plugins[%d] must have id, repo, version, assets {%s: sha256} and data {}" % (i, ", ".join(ASSETS)))
        if not (NAME.fullmatch(p["id"]) and NAME.fullmatch(p["version"]) and REPO.fullmatch(p["repo"])):
            bad("plugins[%d]: id %r and version %r must be plain names (letters, digits, . _ -) and repo %r "
                "an owner/name pair of the same, so the release URL stays on github.com under that repo"
                % (i, p["id"], p["version"], p["repo"]))
        if p["id"] in seen:
            bad("plugins[%d]: id %r appears twice" % (i, p["id"]))
        seen.add(p["id"])
    return m


# ---- fetching ---------------------------------------------------------------------------------------------------

def ssl_context():
    """The default trust store, or certifi where the interpreter ships without one (python.org macOS builds)."""
    ctx = ssl.create_default_context()
    try:
        ctx.load_default_certs()
        if not ctx.get_ca_certs():
            import certifi  # type: ignore  # optional, as in sync_check.py
            ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass  # the fetch fails loud below if no certificate can be verified
    return ctx


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise FetchError("%s: HTTP %s" % (url, e.code))
    except (urllib.error.URLError, OSError, ValueError) as e:
        reason = getattr(e, "reason", None) or e
        raise FetchError("%s: %s" % (url, reason))


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def hashes_to(data, want):
    """True when `data`, or `data` without Obsidian's appended nosourcemap line, hashes to `want`."""
    if sha256_bytes(data) == want:
        return True
    return data.endswith(NOSOURCEMAP) and sha256_bytes(data[:-len(NOSOURCEMAP)]) == want


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def asset_bytes(plugin, name, cache, release_url=RELEASE_URL, fetch_fn=fetch):
    """The verified bytes of one release asset: from the cache when it holds them at the manifest's hash, else
    fetched, verified, and cached. A mismatch is a FetchError; nothing unverified is ever cached or written."""
    want = plugin["assets"][name]
    cached = os.path.join(cache, plugin["id"], plugin["version"], name)
    if os.path.isfile(cached):
        data = read_bytes(cached)
        if sha256_bytes(data) == want:
            return data
    url = release_url % (plugin["repo"], plugin["version"], name)
    data = fetch_fn(url)
    if sha256_bytes(data) != want:
        raise FetchError("%s: sha256 %s, but the manifest pins %s for %s %s %s" % (
            url, sha256_bytes(data), want, plugin["id"], plugin["version"], name))
    os.makedirs(os.path.dirname(cached), exist_ok=True)
    tmp = "%s.tmp%d" % (cached, os.getpid())
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, cached)
    return data


# ---- the vault --------------------------------------------------------------------------------------------------

def vault_root(given):
    root = os.path.realpath(given)
    if not os.path.isdir(root):
        raise common.ToolError("root missing or not a folder: %s" % root)
    ob = os.path.join(root, ".obsidian")
    if os.path.lexists(ob) and not os.path.isdir(ob):
        raise common.ToolError("%s exists but is not a folder; move it aside before the editor setup is written or "
                               "checked" % ob)
    has_pages = any(n.lower().endswith(".md") for n in os.listdir(root)) or os.path.isdir(os.path.join(root,
                                                                                                        "00 Index"))
    if not has_pages:
        raise common.ToolError("%s holds no wiki skeleton (no .md page at its root and no 00 Index/): --root is "
                               "the folder the owner opens as the vault, a project's wiki folder or a user vault's "
                               "root" % root)
    return root


def cache_dir(root, given):
    """`--cache`, else the rulebook twin's `obsidian_cache` when the root is a wiki inside a prepared folder, else
    the platform cache; `~` expanded; refused inside the vault or the prepared folder."""
    root = os.path.realpath(root)
    parent = os.path.dirname(root)
    chosen, why = given, "--cache"
    if not chosen and os.path.isfile(os.path.join(parent, common.SETTINGS_DIRNAME, "rulebook.json")):
        chosen = common.load_rulebook(parent, os.path.join(parent, common.SETTINGS_DIRNAME))["obsidian_cache"]
        why = "obsidian_cache in rulebook.json"
    if not chosen:
        chosen, why = default_cache(), "the platform cache"
    cache = os.path.realpath(os.path.expanduser(chosen))
    for folder in (root, parent):
        if common.within(folder, cache):
            raise common.ToolError("%s must be outside the vault and the folder that holds it: %s" % (why, cache))
    return cache


def read_json_file(path):
    """The parsed JSON at `path`, None when the file is absent; malformed JSON fails loud."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, RecursionError) as e:
        raise common.ToolError("%s: not valid JSON (%s)" % (path, e))


def core_enabled(core):
    """The enabled core plugins of a `core-plugins.json`: a dict of id to bool in current Obsidian, a list in older."""
    if isinstance(core, dict):
        return {k for k, on in core.items() if on is True}
    if isinstance(core, list):
        return {x for x in core if isinstance(x, str)}
    return set()


def plugin_state(root, plugin):
    """One plugin's state in the vault: installed version, each asset ok|missing|mismatch, data present."""
    folder = os.path.join(root, ".obsidian", "plugins", plugin["id"])
    try:
        installed = read_json_file(os.path.join(folder, "manifest.json")) if os.path.isdir(folder) else None
    except common.ToolError:
        installed = None  # a malformed manifest.json is a mismatch below, not a crash
    version = installed.get("version") if isinstance(installed, dict) else None
    assets = {}
    for name in ASSETS:
        p = os.path.join(folder, name)
        if not os.path.isfile(p):
            assets[name] = "missing"
        else:
            assets[name] = "ok" if hashes_to(read_bytes(p), plugin["assets"][name]) else "mismatch"
    return {"installed": os.path.isdir(folder), "version": version, "assets": assets,
            "data": os.path.isfile(os.path.join(folder, "data.json"))}


def check_report(root, m):
    """The editor setup against the manifest, as a dict with a `findings` list and a `complete` flag."""
    ob = os.path.join(root, ".obsidian")
    report = {"root": root, "present": os.path.isdir(ob), "plugins": {}, "findings": []}
    enabled = read_json_file(os.path.join(ob, "community-plugins.json")) or []
    if not isinstance(enabled, list):
        enabled = []
    for plugin in m["plugins"]:
        st = plugin_state(root, plugin)
        st["enabled"] = plugin["id"] in enabled
        st["complete"] = all(v == "ok" for v in st["assets"].values()) and st["data"] and st["enabled"]
        report["plugins"][plugin["id"]] = st
        if not st["installed"]:
            report["findings"].append("plugin %s is not installed" % plugin["id"])
        else:
            for name, state in st["assets"].items():
                if state != "ok":
                    report["findings"].append("plugin %s: %s is %s%s" % (
                        plugin["id"], name, state,
                        " (installed version %s, the manifest pins %s)" % (st["version"], plugin["version"])
                        if st["version"] and st["version"] != plugin["version"] else ""))
            if not st["data"]:
                report["findings"].append("plugin %s: data.json is missing" % plugin["id"])
            if not st["enabled"]:
                report["findings"].append("plugin %s is not listed in community-plugins.json" % plugin["id"])
    core = read_json_file(os.path.join(ob, "core-plugins.json"))
    if core is None:
        report["core"] = "missing"
        report["findings"].append("core-plugins.json is missing")
    else:
        lacking = sorted(set(m["core_plugins"]) - core_enabled(core))
        report["core"] = "ok" if not lacking else "differs: %s not enabled" % ", ".join(lacking)
        if lacking:
            report["findings"].append("core plugins not enabled: %s" % ", ".join(lacking))
    for name, wanted in (("app.json", m["app"]), ("appearance.json", m["appearance"])):
        have = read_json_file(os.path.join(ob, name))
        if wanted and have is None:
            report[name] = "missing"
            report["findings"].append("%s is missing" % name)
        elif wanted and not isinstance(have, dict):
            report[name] = "malformed"
            report["findings"].append("%s is not a JSON object" % name)
        else:
            missing = sorted(k for k in wanted if k not in (have or {}))
            report[name] = "ok" if not missing else "keys missing: %s" % ", ".join(missing)
            if missing:
                report["findings"].append("%s lacks %s" % (name, ", ".join(missing)))
    report["device_state"] = sorted(n for n in m["never"] if os.path.exists(os.path.join(ob, n)))  # noted, not found
    report["complete"] = report["present"] and not report["findings"]
    return report


# ---- commands ---------------------------------------------------------------------------------------------------

def write_profile(root, m, cache, upgrade=False, fetch_fn=fetch, release_url=RELEASE_URL):
    """Build or complete the profile. Returns (actions, failures): one line per thing done or left, and the plugins
    that could not be fetched, each with its reason. Nothing unverified is written; device state is never touched."""
    ob = os.path.join(root, ".obsidian")
    w = common.Writer()
    actions, failures = [], []
    have = read_json_file(os.path.join(ob, "community-plugins.json"))  # read first: a file the tool cannot read
    if have is not None and not (isinstance(have, list) and all(isinstance(x, str) for x in have)):  # stops it
        raise common.ToolError("%s is not a list of plugin ids as Obsidian writes it; fix it by hand before the "
                               "editor setup is written, since the tool never replaces what it cannot read"
                               % os.path.join(ob, "community-plugins.json"))
    for plugin in m["plugins"]:
        pid, folder = plugin["id"], os.path.join(ob, "plugins", plugin["id"])
        st = plugin_state(root, plugin)
        if st["installed"] and st["version"] and st["version"] != plugin["version"] and not upgrade:
            actions.append("plugin %s: left at version %s (the manifest pins %s; --upgrade replaces it)"
                           % (pid, st["version"], plugin["version"]))
            if not st["data"]:
                w.json(os.path.join(folder, "data.json"), plugin["data"], indent=2)
                actions.append("plugin %s: wrote data.json" % pid)
            continue
        if all(v == "ok" for v in st["assets"].values()):
            actions.append("plugin %s: assets present at the manifest's hashes" % pid)
        else:
            try:
                data = {name: asset_bytes(plugin, name, cache, release_url, fetch_fn) for name in ASSETS}
            except FetchError as e:
                failures.append((pid, str(e)))
                actions.append("plugin %s: not written (%s)" % (pid, e))
                continue
            os.makedirs(folder, exist_ok=True)
            for name in ASSETS:
                if st["assets"][name] != "ok":
                    tmp = os.path.join(folder, "%s.tmp%d" % (name, os.getpid()))
                    with open(tmp, "wb") as f:
                        f.write(data[name])
                    os.replace(tmp, os.path.join(folder, name))
            actions.append("plugin %s: wrote %s at version %s" % (
                pid, ", ".join(n for n in ASSETS if st["assets"][n] != "ok"), plugin["version"]))
        if not st["data"]:
            w.json(os.path.join(folder, "data.json"), plugin["data"], indent=2)
            actions.append("plugin %s: wrote data.json" % pid)
    # the settings files: merge, keep what the manifest does not name, never clobber a key that is present
    ids = [p["id"] for p in m["plugins"] if p["id"] not in [f[0] for f in failures]]
    listed = list(have) if have else []
    merged = ids + [x for x in listed if x not in ids] if any(i not in listed for i in ids) else listed
    if merged != listed or have is None:
        w.json(os.path.join(ob, "community-plugins.json"), merged)
        actions.append("community-plugins.json: %s" % ("written" if have is None else "updated"))
    core = read_json_file(os.path.join(ob, "core-plugins.json"))
    lacking = [c for c in m["core_plugins"] if c not in core_enabled(core)]
    if core is None:
        w.json(os.path.join(ob, "core-plugins.json"), {c: True for c in m["core_plugins"]}, indent=2)
        actions.append("core-plugins.json: written")
    elif lacking:
        if isinstance(core, dict):
            core.update({c: True for c in lacking})
        else:
            core = list(core) + lacking
        w.json(os.path.join(ob, "core-plugins.json"), core, indent=2)
        actions.append("core-plugins.json: enabled %s" % ", ".join(lacking))
    for name, wanted in (("app.json", m["app"]), ("appearance.json", m["appearance"])):
        current = read_json_file(os.path.join(ob, name))
        if current is None:
            w.json(os.path.join(ob, name), wanted, indent=2)
            actions.append("%s: written" % name)
        elif isinstance(current, dict):
            missing = {k: v for k, v in wanted.items() if k not in current}
            if missing:
                current.update(missing)
                w.json(os.path.join(ob, name), current, indent=2)
                actions.append("%s: added %s" % (name, ", ".join(sorted(missing))))
    for name in m["never"]:
        if os.path.exists(os.path.join(ob, name)):
            actions.append("%s: device state, left alone" % name)
    return actions, failures


def cmd_write(a):
    m = load_manifest(a.manifest)
    root = vault_root(a.root)
    cache = cache_dir(root, a.cache)
    actions, failures = write_profile(root, m, cache, upgrade=a.upgrade)
    wrote = [x for x in actions if ": wrote" in x or ": written" in x or ": updated" in x or ": enabled" in x
             or ": added" in x]
    if a.json:
        print(json.dumps({"root": root, "cache": cache, "actions": actions,
                          "failures": [{"plugin": p, "reason": r} for p, r in failures],
                          "wrote": bool(wrote)}, ensure_ascii=False, indent=1))
    else:
        for line in actions:
            print(line)
        print("nothing to do" if not wrote and not failures else "written: %d change(s)" % len(wrote))
    if failures:
        for pid, reason in failures:
            print("error: plugin %s could not be fetched: %s" % (pid, reason), file=sys.stderr)
        return EXIT_FETCH
    return 0


def cmd_check(a):
    m = load_manifest(a.manifest)
    root = vault_root(a.root)
    report = check_report(root, m)
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print("editor setup: %s" % ("complete" if report["complete"] else "incomplete"))
        for line in report["findings"]:
            print("  finding: " + line)
        if report["device_state"]:
            print("  device state present (noted, not a finding): %s" % ", ".join(report["device_state"]))
    return 0 if report["complete"] else 1


def main():
    ap = argparse.ArgumentParser(description="The editor setup: build .obsidian/ from the manifest, or check it")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("write", cmd_write), ("check", cmd_check)):
        p = sub.add_parser(name)
        p.add_argument("--root", required=True, help="the folder the owner opens as the vault")
        p.add_argument("--manifest", default=DEFAULT_MANIFEST, help="default: obsidian-profile.json beside this tool")
        p.add_argument("--json", action="store_true", help="print the report as JSON")
        if name == "write":
            p.add_argument("--cache", help="where fetched assets are kept (default: the rulebook twin's "
                                           "obsidian_cache, else the platform cache)")
            p.add_argument("--upgrade", action="store_true",
                           help="replace a plugin present at another version with the manifest's")
        p.set_defaults(func=fn)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    common.run_main(main)
