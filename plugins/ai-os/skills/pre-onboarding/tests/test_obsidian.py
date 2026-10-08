"""`obsidian.py`: the editor setup built from a manifest and a local release server, checked, and never clobbering.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests

No network: a `http.server` in a thread serves the assets of a fake release, and the manifest under test pins their
hashes. The fixture wiki's own `.obsidian/` (stand-in assets, `tests/fixtures/obsidian-profile.json`) is checked too,
since `readiness.py` reports it.
"""
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.realpath(os.path.join(HERE, "..", "tools"))
TIMEOUT = 300
FIXTURE_WIKI = os.path.join(HERE, "fixture", "Alex Personal", "Alex Personal Wiki")
FIXTURE_MANIFEST = os.path.join(HERE, "fixtures", "obsidian-profile.json")
sys.path.insert(0, TOOLS)
import common  # noqa: E402
import obsidian  # noqa: E402

def assets_for(pid, version):
    """A fake release's three assets, each distinct per plugin, manifest.json valid JSON as Obsidian reads it."""
    return {"main.js": ("console.log('%s');\n" % pid).encode(),
            "manifest.json": json.dumps({"id": pid, "version": version}).encode() + b"\n",
            "styles.css": (".%s {}\n" % pid).encode()}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


class Server:
    """Serves `<repo>/releases/download/<version>/<asset>` from a dict, counting hits; a path it lacks is a 404."""

    def __init__(self, files):
        files_ = files
        hits = self.hits = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                data = files_.get(self.path)
                if data is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass
        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:%d/%%s/releases/download/%%s/%%s" % self.httpd.server_address[1]

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def run(*args, env=None):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "obsidian.py"), *args], capture_output=True, text=True,
                       timeout=TIMEOUT, env=dict(os.environ, **(env or {})))
    return r.returncode, r.stdout, r.stderr


class ObsidianTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="obsidian-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.vault = os.path.join(self.tmp, "Vault")
        os.makedirs(os.path.join(self.vault, "00 Index"))
        with open(os.path.join(self.vault, "00 Index", "00 Index.md"), "w", encoding="utf-8") as f:
            f.write("# 00 Index\n")
        self.cache = tempfile.mkdtemp(prefix="obsidian-cache-")  # beside, never inside, the vault's folder
        self.addCleanup(shutil.rmtree, self.cache, ignore_errors=True)
        self.files = {("one", "1.0.0"): assets_for("one", "1.0.0"), ("two", "2.1.0"): assets_for("two", "2.1.0")}
        self.plugins = [
            {"id": "one", "repo": "someone/obsidian-one", "version": "1.0.0", "desktop_only": False,
             "assets": {n: sha(d) for n, d in self.files[("one", "1.0.0")].items()},
             "data": {"hideFolderNote": True}},
            {"id": "two", "repo": "someone/obsidian-two", "version": "2.1.0", "desktop_only": True,
             "assets": {n: sha(d) for n, d in self.files[("two", "2.1.0")].items()}, "data": {}},
        ]
        self.manifest = {"profile_version": 1, "core_plugins": ["file-explorer", "backlink"],
                         "app": {"alwaysUpdateLinks": True}, "appearance": {},
                         "never": ["workspace.json", "graph.json"], "plugins": self.plugins}
        self.manifest_path = os.path.join(self.tmp, "manifest.json")
        self.write_manifest()
        files = {}
        for p in self.plugins:
            for name, data in self.files[(p["id"], p["version"])].items():
                files["/%s/releases/download/%s/%s" % (p["repo"], p["version"], name)] = data
        self.server = Server(files)
        self.addCleanup(self.server.close)

    def write_manifest(self):
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f)

    def write(self, **kw):
        m = obsidian.load_manifest(self.manifest_path)
        return obsidian.write_profile(self.vault, m, self.cache, release_url=self.server.url, **kw)

    def check(self):
        return obsidian.check_report(self.vault, obsidian.load_manifest(self.manifest_path))

    def ob(self, *parts):
        return os.path.join(self.vault, ".obsidian", *parts)

    # ---- write ----

    def test_a_fresh_write_builds_the_profile_and_check_reports_it_complete(self):
        actions, failures = self.write()
        self.assertEqual(failures, [])
        for p in self.plugins:
            for name in ("main.js", "manifest.json", "styles.css", "data.json"):
                self.assertTrue(os.path.isfile(self.ob("plugins", p["id"], name)), name)
        self.assertEqual(json.loads(read(self.ob("plugins", "one", "data.json"))), {"hideFolderNote": True})
        self.assertEqual(json.loads(read(self.ob("community-plugins.json"))), ["one", "two"])
        self.assertEqual(json.loads(read(self.ob("core-plugins.json"))), {"file-explorer": True, "backlink": True})
        self.assertEqual(json.loads(read(self.ob("app.json"))), {"alwaysUpdateLinks": True})
        self.assertEqual(json.loads(read(self.ob("appearance.json"))), {})
        self.assertFalse(os.path.exists(self.ob("workspace.json")))
        report = self.check()
        self.assertEqual(report["findings"], [])
        self.assertTrue(report["complete"])
        self.assertEqual({pid: st["complete"] for pid, st in report["plugins"].items()}, {"one": True, "two": True})

    def test_a_second_write_is_a_no_op_and_the_cache_serves_the_second_vault(self):
        self.write()
        hits = len(self.server.hits)
        self.assertEqual(hits, 6)
        actions, failures = self.write()
        self.assertEqual(failures, [])
        self.assertFalse(any(": wrote" in x or ": written" in x for x in actions), actions)
        self.assertEqual(len(self.server.hits), hits, "no fetch on a complete profile")
        other = os.path.join(self.tmp, "Other")
        os.makedirs(os.path.join(other, "00 Index"))
        open(os.path.join(other, "00 Index", "00 Index.md"), "w").close()
        obsidian.write_profile(other, obsidian.load_manifest(self.manifest_path), self.cache,
                               release_url=self.server.url)
        self.assertEqual(len(self.server.hits), hits, "the second vault is built from the cache")
        self.assertTrue(obsidian.check_report(other, obsidian.load_manifest(self.manifest_path))["complete"])

    def test_a_hash_mismatch_refuses_that_plugin_names_it_and_writes_the_rest(self):
        self.plugins[1]["assets"]["main.js"] = sha(b"something else")
        self.write_manifest()
        actions, failures = self.write()
        self.assertEqual([f[0] for f in failures], ["two"])
        self.assertIn("sha256", failures[0][1])
        self.assertIn("the manifest pins", failures[0][1])
        self.assertFalse(os.path.exists(self.ob("plugins", "two")), "nothing unverified is written")
        self.assertFalse(os.path.exists(os.path.join(self.cache, "two")), "nothing unverified is cached")
        self.assertTrue(os.path.isfile(self.ob("plugins", "one", "main.js")))
        self.assertEqual(json.loads(read(self.ob("community-plugins.json"))), ["one"])
        code, out, err = run("write", "--root", self.vault, "--manifest", self.manifest_path, "--cache", self.cache)
        self.assertEqual(code, 3, err)
        self.assertIn("plugin two could not be fetched", err)

    def test_an_unreachable_release_is_exit_3_not_a_crash(self):
        self.plugins[0]["version"] = "9.9.9"  # the server has no such release: 404
        self.write_manifest()
        actions, failures = self.write()
        self.assertEqual([f[0] for f in failures], ["one"])
        self.assertIn("HTTP 404", failures[0][1])

    def test_a_plugin_at_another_version_is_left_unless_upgrade_is_given(self):
        self.write()
        folder = self.ob("plugins", "one")
        with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "one", "version": "0.9.0"}, f)
        with open(os.path.join(folder, "main.js"), "w", encoding="utf-8") as f:
            f.write("old\n")
        actions, failures = self.write()
        self.assertEqual(failures, [])
        self.assertTrue(any("left at version 0.9.0" in x for x in actions), actions)
        self.assertEqual(read(os.path.join(folder, "main.js")), "old\n")
        report = self.check()
        self.assertFalse(report["complete"])
        self.assertTrue(any("installed version 0.9.0, the manifest pins 1.0.0" in f for f in report["findings"]))
        actions, failures = self.write(upgrade=True)
        self.assertTrue(any("plugin one: wrote" in x for x in actions), actions)
        self.assertTrue(self.check()["complete"])

    def test_write_merges_and_never_touches_device_state(self):
        os.makedirs(self.ob())
        with open(self.ob("app.json"), "w", encoding="utf-8") as f:
            json.dump({"alwaysUpdateLinks": False, "readableLineLength": False}, f)
        with open(self.ob("core-plugins.json"), "w", encoding="utf-8") as f:
            json.dump({"file-explorer": True, "footnotes": False, "backlink": False}, f)
        with open(self.ob("community-plugins.json"), "w", encoding="utf-8") as f:
            json.dump(["table-editor"], f)
        with open(self.ob("workspace.json"), "w", encoding="utf-8") as f:
            f.write("{\"main\": {}}")
        actions, failures = self.write()
        self.assertEqual(failures, [])
        self.assertEqual(json.loads(read(self.ob("app.json"))), {"alwaysUpdateLinks": False,
                                                                 "readableLineLength": False},
                         "a key that is present keeps its value; the manifest only adds what is absent")
        self.assertEqual(json.loads(read(self.ob("core-plugins.json"))),
                         {"file-explorer": True, "footnotes": False, "backlink": True})
        self.assertEqual(json.loads(read(self.ob("community-plugins.json"))), ["one", "two", "table-editor"])
        self.assertEqual(read(self.ob("workspace.json")), "{\"main\": {}}")
        self.assertTrue(any("workspace.json: device state, left alone" in x for x in actions), actions)
        report = self.check()
        self.assertEqual(report["device_state"], ["workspace.json"])
        self.assertTrue(report["complete"], report["findings"])

    def test_an_installed_main_js_with_obsidians_nosourcemap_marker_counts_as_the_release(self):
        self.write()
        path = self.ob("plugins", "one", "main.js")
        with open(path, "ab") as f:
            f.write(obsidian.NOSOURCEMAP)
        self.assertEqual(self.check()["plugins"]["one"]["assets"]["main.js"], "ok")
        actions, _ = self.write()
        self.assertTrue(any("plugin one: assets present" in x for x in actions), actions)

    # ---- check ----

    def test_check_names_each_gap(self):
        report = self.check()
        self.assertFalse(report["present"])
        self.assertEqual(sorted(report["findings"]),
                         sorted(["plugin one is not installed", "plugin two is not installed",
                                 "core-plugins.json is missing", "app.json is missing"]))
        self.write()
        os.remove(self.ob("plugins", "two", "styles.css"))
        os.remove(self.ob("plugins", "one", "data.json"))
        with open(self.ob("community-plugins.json"), "w", encoding="utf-8") as f:
            json.dump(["one"], f)
        report = self.check()
        self.assertEqual(sorted(report["findings"]), sorted([
            "plugin two: styles.css is missing", "plugin one: data.json is missing",
            "plugin two is not listed in community-plugins.json"]))
        code, out, err = run("check", "--root", self.vault, "--manifest", self.manifest_path)
        self.assertEqual(code, 1, err)
        self.assertIn("editor setup: incomplete", out)
        code, out, err = run("check", "--root", self.vault, "--manifest", self.manifest_path, "--json")
        self.assertEqual(json.loads(out)["findings"], report["findings"])

    def test_a_root_that_is_not_a_vault_or_a_bad_manifest_is_exit_2(self):
        code, out, err = run("check", "--root", os.path.join(self.tmp, "nowhere"), "--manifest", self.manifest_path)
        self.assertEqual(code, 2, err)
        self.assertIn("root missing", err)
        empty = os.path.join(self.tmp, "Empty")
        os.makedirs(empty)
        code, out, err = run("check", "--root", empty, "--manifest", self.manifest_path)
        self.assertEqual(code, 2, err)
        self.assertIn("no wiki skeleton", err)
        for change in ({"profile_version": 2}, {"plugins": [{"id": "x"}]}, {"core_plugins": "file-explorer"}):
            m = dict(self.manifest, **change)
            bad = os.path.join(self.tmp, "bad.json")
            with open(bad, "w", encoding="utf-8") as f:
                json.dump(m, f)
            with self.subTest(change=list(change)):
                code, out, err = run("check", "--root", self.vault, "--manifest", bad)
                self.assertEqual(code, 2, err)
                self.assertNotIn("Traceback", err)

    def test_the_cache_is_refused_inside_the_vault_or_its_folder(self):
        for inside in (os.path.join(self.vault, "cache"), os.path.join(self.tmp, "cache-beside")):
            with self.subTest(inside=inside):
                with self.assertRaisesRegex(common.ToolError, "outside the vault"):
                    obsidian.cache_dir(self.vault, inside)
        self.assertEqual(obsidian.cache_dir(self.vault, os.path.join(self.tmp, "..", "elsewhere-%d" % os.getpid())),
                         os.path.realpath(os.path.join(self.tmp, "..", "elsewhere-%d" % os.getpid())))

    # ---- the shipped manifest and the fixture ----

    def test_the_shipped_manifest_is_valid_and_names_no_one(self):
        m = obsidian.load_manifest(obsidian.DEFAULT_MANIFEST)
        self.assertEqual([p["id"] for p in m["plugins"]], ["folder-notes", "external-file-embed-and-link"])
        self.assertTrue(m["plugins"][0]["data"].get("hideFolderNote"))
        text = read(obsidian.DEFAULT_MANIFEST).lower()
        for word in ("/users/", "/home/", "@", "boshu"):
            self.assertNotIn(word, text)

    def test_the_fixture_wiki_is_complete_under_the_fixture_manifest(self):
        report = obsidian.check_report(FIXTURE_WIKI, obsidian.load_manifest(FIXTURE_MANIFEST))
        self.assertEqual(report["findings"], [])
        self.assertTrue(report["complete"])
        self.assertEqual(report["device_state"], [])
        self.assertFalse(obsidian.check_report(FIXTURE_WIKI, obsidian.load_manifest(obsidian.DEFAULT_MANIFEST))
                         ["complete"], "the stand-ins are not the plugins' code, so the shipped manifest finds them")


if __name__ == "__main__":
    unittest.main()
