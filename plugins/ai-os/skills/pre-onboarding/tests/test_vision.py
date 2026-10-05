"""The vision lane against a fake `agy`: the images alone in a fresh folder, the whole-batch join (every image back,
in the order sent, or nothing applied), three tries then `unread` with the local text kept, quota waits that do
not count as tries, the model allowed to open its images, and run-stopping errors that stop the lane.

vision.py polls with `time.sleep(60)`; the runner below replaces `time.sleep` with a no-op in the tool's own process
so the lane runs to its end at once. Nothing else about the tool changes, except in the one test that makes the
engine raise a run-stopping error, which it does by replacing the adapter's call in that same process.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
VISION = os.path.join(TOOLS, "vision.py")
sys.path.insert(0, HERE)
from fake_engines import SECRETS, Fakes, tool_env  # noqa: E402

RUNNER = ("import os, runpy, sys, time\n"
          "time.sleep = lambda seconds: None\n"
          "stage = os.environ.get('VISION_TEST_STAGE_AFTER_FIRST_CALL')\n"
          "if stage:\n"
          "    sys.path.insert(0, %r)\n"
          "    import engines\n"
          "    first = engines.Agy.__call__\n"
          "    def staging(self, *args, **kwargs):\n"
          "        got = first(self, *args, **kwargs)\n"
          "        engines.Agy.__call__ = first\n"
          "        manifest, eid, where = stage.split('|')\n"
          "        import json\n"
          "        with open(manifest) as f:\n"
          "            m = json.load(f)\n"
          "        m['entries'][eid]['current_path'] = where\n"
          "        with open(manifest, 'w') as f:\n"
          "            json.dump(m, f)\n"
          "        return got\n"
          "    engines.Agy.__call__ = staging\n"
          "if sys.argv[1] != '-':\n"
          "    sys.path.insert(0, %r)\n"
          "    import engines\n"
          "    error = getattr(engines, sys.argv[1])\n"
          "    def stop(self, *args, **kwargs):\n"
          "        raise error('a run-stopping error from the engine adapter')\n"
          "    engines.Agy.__call__ = stop\n"
          "sys.argv = sys.argv[2:]\n"
          "runpy.run_path(sys.argv[0], run_name='__main__')\n") % (os.path.realpath(TOOLS), os.path.realpath(TOOLS))


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(data, bytes) else "w") as f:
        f.write(data)


class VisionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="vision_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "Alex Personal")
        os.makedirs(self.root)
        self.work = os.path.join(self.tmp, "work")
        self.out = os.path.join(self.tmp, "extract")
        self.fakes = Fakes(self.tmp)
        self.env = tool_env(self.tmp, self.fakes)
        write(os.path.join(self.work, "state", "extraction.done"), "done")
        self.eid = hashlib.sha256(b"01 Identity/Scan.pdf").hexdigest()
        self.queue = os.path.join(self.work, "vision_queue")
        for n in (1, 2):
            write(os.path.join(self.queue, "%s_%05d.png" % (self.eid, n)), b"\x89PNG fake page %d" % n)
        rec = {"id": self.eid, "path": "01 Identity/Scan.pdf", "class": "document", "status": "needs_vision",
               "page_count": 3, "tiers": {"pending_vision": 2, "text_layer": 1},
               "pages": [{"n": 1, "tier": "pending_vision", "text": "local one", "queued": True},
                         {"n": 2, "tier": "pending_vision", "text": "local two", "queued": True},
                         {"n": 3, "tier": "text_layer", "text": "typed page"}]}
        write(os.path.join(self.out, self.eid + ".json"), json.dumps(rec))
        self.entries = {}
        self.stage(self.eid, "01 Identity/Scan.pdf")

    def stage(self, eid, current_path, flags=()):
        """Document `eid` as the manifest holds it, at `current_path`: the folder's own manifest is rewritten."""
        self.entries[eid] = {"id": eid, "current_path": current_path, "class": "document", "hashed": True,
                             "flags": list(flags)}
        write(os.path.join(self.root, "_Audit", "manifest.json"),
              json.dumps({"schema": "family-ai-preprocess-manifest/2", "entries": self.entries}))

    def vision(self, stop_with="-", env=None):
        cmd = [sys.executable, "-c", RUNNER, stop_with, VISION, "--root", self.root, "--work", self.work,
               "--out", self.out, "--model", "vision-model", "--lanes", "extraction"]
        r = subprocess.run(cmd, capture_output=True, text=True, env=dict(self.env, **(env or {})), timeout=120)
        self.assertNotIn("ResourceWarning", r.stderr, "vision.py left a file or process open")
        return r.returncode, r.stdout, r.stderr

    def record(self):
        return json.loads(read(os.path.join(self.out, self.eid + ".json")))

    def test_a_good_reply_replaces_the_local_text(self):
        # the model opening its images shows as a tool step (the shape agy 1.2.16 streams); only the vision lane
        # accepts that, and only for a tool that reads
        step = {"event": "step_update", "step_update": {"step_index": 2, "state": "DONE", "step_type": "tool",
                                                        "tool_name": "view_file",
                                                        "tool_info": {"name": "view_file",
                                                                      "parameters": {"AbsolutePath": "p1.png"}}}}
        self.fakes.script("agy", default={"kind": "text", "events": [step]})
        code, _out, err = self.vision()
        self.assertEqual(code, 0, err)
        r = self.record()
        p1, p2, p3 = r["pages"]
        self.assertEqual((p1["tier"], p1["text"], p1["local_text"], p1["engine"]),
                         ("vision", "transcribed p1.png", "local one", "agy"))
        self.assertEqual((p2["tier"], p2["text"], p2["local_text"]), ("vision", "transcribed p2.png", "local two"))
        self.assertEqual(p3, {"n": 3, "tier": "text_layer", "text": "typed page"})
        self.assertEqual(r["status"], "ok")
        self.assertEqual(os.listdir(self.queue), [])
        call, = self.fakes.calls("agy")
        self.assertEqual(call["cwd_listing"], ["p1.png", "p2.png"], "the images must be alone in the folder")
        self.assertIn("these image files: p1.png, p2.png.", call["prompt"])
        argv = call["argv"]
        self.assertEqual(argv[argv.index("--model") + 1], "vision-model")
        self.assertNotIn("--json-schema", argv, "agy is asked for the shape in the prompt, never by flag")
        with open(os.path.join(TOOLS, "schemas", "ocr.json"), encoding="utf-8") as f:
            self.assertTrue(call["prompt"].endswith(
                "\n\nReply with JSON only, matching this JSON Schema exactly:\n" + f.read().strip()))
        self.assertEqual(sorted(set(SECRETS) & set(call["env"])), [])
        self.assertEqual(os.listdir(self.env["TMPDIR"]), [], "the call's folder was left behind")
        self.assertTrue(os.path.exists(os.path.join(self.work, "state", "vision0.done")))

    def test_a_reply_that_does_not_join_is_never_applied(self):
        cases = {"two images swapped": {"kind": "text", "swap": True},
                 "an image missing": {"kind": "text", "drop": True},
                 "no pages list": {"kind": "text", "no_pages": True},
                 "a page without text": {"kind": "text", "null_text": True}}
        for name, reply in cases.items():
            with self.subTest(name):
                self.setUp()
                self.fakes.script("agy", default=reply)
                code, _out, err = self.vision()
                self.assertEqual(code, 0, err)
                self.assertEqual(len(self.fakes.calls("agy")), 3, "three tries, then unread")
                r = self.record()
                self.assertEqual([(p["tier"], p["text"]) for p in r["pages"]],
                                 [("unread", "local one"), ("unread", "local two"), ("text_layer", "typed page")])
                self.assertNotIn("transcribed", json.dumps(r))
                self.assertEqual(r["status"], "partial")
                self.assertEqual(os.listdir(self.queue), [])

    def test_a_quota_wait_is_not_a_try(self):
        self.fakes.script("agy", replies=[{"kind": "quota", "rc": 1, "message": "Quota exceeded. Resets in 5s"}],
                          default={"kind": "text"})
        code, _out, err = self.vision()
        self.assertEqual(code, 0, err)
        self.assertIn("quota; sleeping 1 min", err)
        self.assertEqual(len(self.fakes.calls("agy")), 2)
        self.assertEqual([p["tier"] for p in self.record()["pages"]], ["vision", "vision", "text_layer"])
        self.assertEqual(json.loads(read(os.path.join(self.work, "state", "vision_tries_0.json"))), {})

    STAGED = "_Migrations/Other Project/01 Identity/Scan.pdf"

    def test_a_document_staged_for_another_project_is_never_sent(self):
        """Held whatever its flags: its record and queued images are purged before anything is read or sent, so the lane
        still ends, and the log counts the document."""
        for flags in (["migrating"], []):
            with self.subTest(flags=flags):
                self.setUp()
                self.stage(self.eid, self.STAGED, flags)
                code, _out, err = self.vision()
                self.assertEqual(code, 0, err)
                self.assertEqual(self.fakes.calls("agy"), [], "a page of another project's document was sent")
                self.assertFalse(os.path.exists(os.path.join(self.out, self.eid + ".json")), "its record was kept")
                self.assertEqual(os.listdir(self.queue), [], "a held image was left in the queue")
                self.assertIn("purged what withheld documents left behind: 1 extract record, 2 queued page images", err)
                self.assertNotIn("Scan", err, "the purge names counts, never paths")
                self.assertIn("finished; held for another project: 1; excluded: 0; not live: 0", err)
                self.assertTrue(os.path.exists(os.path.join(self.work, "state", "vision0.done")))

    def exclude(self, *paths):
        write(os.path.join(self.root, "CLAUDE.md"), "# Rules\n")
        pin = hashlib.sha256(b"# Rules\n").hexdigest()
        write(os.path.join(self.root, ".familyai", "rulebook.json"),
              json.dumps({"version": 1, "rulebook_sha256": pin, "exclude": list(paths)}))
        for entry in paths:  # an `exclude` entry must name a path: make each one
            os.makedirs(os.path.dirname(os.path.join(self.root, entry)), exist_ok=True)
            write(os.path.join(self.root, entry), b"") if entry.endswith(".pdf") else \
                os.makedirs(os.path.join(self.root, entry), exist_ok=True)

    def test_an_excluded_document_is_never_sent_and_is_counted_apart(self):
        for paths in (["01 Identity"], ["01 Identity/Scan.pdf"]):
            with self.subTest(paths):
                self.setUp()
                self.exclude(*paths)
                code, _out, err = self.vision()
                self.assertEqual(code, 0, err)
                self.assertEqual(self.fakes.calls("agy"), [], "a page of an excluded document was sent")
                self.assertFalse(os.path.exists(os.path.join(self.out, self.eid + ".json")), "its record was kept")
                self.assertEqual(os.listdir(self.queue), [])
                self.assertIn("finished; held for another project: 0; excluded: 1; not live: 0", err)

    def test_staged_and_excluded_documents_are_counted_apart(self):
        other = hashlib.sha256(b"02 Finance/Statement.pdf").hexdigest()
        write(os.path.join(self.queue, "%s_%05d.png" % (other, 1)), b"\x89PNG fake statement")
        write(os.path.join(self.out, other + ".json"), json.dumps({
            "id": other, "path": "02 Finance/Statement.pdf", "class": "document", "status": "needs_vision",
            "page_count": 1, "tiers": {"pending_vision": 1},
            "pages": [{"n": 1, "tier": "pending_vision", "text": "local statement", "queued": True}]}))
        self.stage(other, self.STAGED)
        self.exclude("01 Identity")
        code, _out, err = self.vision()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.fakes.calls("agy"), [])
        self.assertIn("finished; held for another project: 1; excluded: 1; not live: 0", err)

    def test_a_document_moved_into_an_excluded_folder_after_extraction_is_never_sent(self):
        """Its old entry is `departed` at the old included path; the file has a synthetic entry in the excluded folder."""
        self.entries[self.eid]["flags"] = ["departed"]
        self.stage(hashlib.sha256(b"Private/Scan.pdf").hexdigest(), "Private/Scan.pdf")
        self.exclude("Private")
        before = self.record()
        code, _out, err = self.vision()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.fakes.calls("agy"), [], "pages of a document moved into an excluded folder were sent")
        self.assertEqual(self.record(), before)
        self.assertIn("finished; held for another project: 0; excluded: 1; not live: 1", err)

    def test_an_image_of_an_id_the_manifest_does_not_hold_is_not_sent(self):
        del self.entries[self.eid]
        self.stage(hashlib.sha256(b"Other/Doc.pdf").hexdigest(), "Other/Doc.pdf")
        code, _out, err = self.vision()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.fakes.calls("agy"), [])
        self.assertIn("not live: 1", err)

    def test_only_the_document_that_is_not_held_is_sent(self):
        other = hashlib.sha256(b"02 Finance/Statement.pdf").hexdigest()
        write(os.path.join(self.queue, "%s_%05d.png" % (other, 1)), b"\x89PNG fake statement")
        rec = {"id": other, "path": "02 Finance/Statement.pdf", "class": "document", "status": "needs_vision",
               "page_count": 1, "tiers": {"pending_vision": 1},
               "pages": [{"n": 1, "tier": "pending_vision", "text": "local statement", "queued": True}]}
        write(os.path.join(self.out, other + ".json"), json.dumps(rec))
        self.stage(other, "02 Finance/Statement.pdf")
        self.stage(self.eid, self.STAGED, ["migrating"])
        code, _out, err = self.vision()
        self.assertEqual(code, 0, err)
        call, = self.fakes.calls("agy")
        self.assertEqual(call["cwd_listing"], ["p1.png"], "only the live document's image is sent")
        self.assertEqual(json.loads(read(os.path.join(self.out, other + ".json")))["pages"][0]["tier"], "vision")
        self.assertFalse(os.path.exists(os.path.join(self.out, self.eid + ".json")), "the staged document's record")
        self.assertEqual(os.listdir(self.queue), [], "the staged document's images were left in the queue")
        self.assertIn("finished; held for another project: 1; excluded: 0; not live: 0", err)

    def test_a_round_that_stages_a_document_while_the_lane_runs_is_seen(self):
        """The manifest is read again before each batch: six images go in a call, so the document's seventh and
        eighth are held back once the first call has been made and the manifest says it is staged."""
        many = hashlib.sha256(b"02 Finance/Long.pdf").hexdigest()
        for n in range(1, 9):
            write(os.path.join(self.queue, "%s_%05d.png" % (many, n)), b"\x89PNG fake page %d" % n)
        rec = {"id": many, "path": "02 Finance/Long.pdf", "class": "document", "status": "needs_vision",
               "page_count": 8, "tiers": {"pending_vision": 8},
               "pages": [{"n": n, "tier": "pending_vision", "text": "local %d" % n, "queued": True}
                         for n in range(1, 9)]}
        write(os.path.join(self.out, many + ".json"), json.dumps(rec))
        self.stage(many, "02 Finance/Long.pdf")
        self.stage(self.eid, self.STAGED, ["migrating"])
        manifest = os.path.join(self.root, "_Audit", "manifest.json")
        code, _out, err = self.vision(env={"VISION_TEST_STAGE_AFTER_FIRST_CALL":
                                           "|".join((manifest, many, "_Migrations/Other Project/Long.pdf"))})
        self.assertEqual(code, 0, err)
        call, = self.fakes.calls("agy")
        self.assertEqual(call["cwd_listing"], ["p%d.png" % n for n in range(1, 7)])
        self.assertFalse(os.path.exists(os.path.join(self.out, many + ".json")),
                         "the record of a document staged while the lane ran was kept")
        self.assertEqual(os.listdir(self.queue), [], "the staged document's last two images were left in the queue")
        self.assertIn("finished; held for another project: 2; excluded: 0; not live: 0", err)

    def test_a_missing_manifest_stops_the_lane(self):
        os.remove(os.path.join(self.root, "_Audit", "manifest.json"))
        code, _out, err = self.vision()
        self.assertEqual(code, 2, err)
        self.assertIn("manifest missing", err)
        self.assertEqual(self.fakes.calls("agy"), [])

    def test_a_run_stopping_error_stops_the_lane_and_is_not_a_try(self):
        for error in ("CredentialError", "SetupError"):
            with self.subTest(error):
                self.setUp()
                before = self.record()
                code, _out, err = self.vision(stop_with=error)
                self.assertEqual(code, 2, err)
                self.assertIn("error: a run-stopping error", err)
                self.assertEqual(self.record(), before, "the record changed")
                self.assertEqual(len(os.listdir(self.queue)), 2, "the queue was drained")
                self.assertFalse(os.path.exists(os.path.join(self.work, "state", "vision_tries_0.json")),
                                 "a run-stopping error was counted as a try")
                self.assertEqual(os.listdir(self.env["TMPDIR"]), [], "the call's folder was left behind")


if __name__ == "__main__":
    unittest.main()
