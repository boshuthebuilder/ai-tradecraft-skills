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

RUNNER = ("import runpy, sys, time\n"
          "time.sleep = lambda seconds: None\n"
          "if sys.argv[1] != '-':\n"
          "    sys.path.insert(0, %r)\n"
          "    import engines\n"
          "    error = getattr(engines, sys.argv[1])\n"
          "    def stop(self, *args, **kwargs):\n"
          "        raise error('a run-stopping error from the engine adapter')\n"
          "    engines.Agy.__call__ = stop\n"
          "sys.argv = sys.argv[2:]\n"
          "runpy.run_path(sys.argv[0], run_name='__main__')\n") % os.path.realpath(TOOLS)


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

    def vision(self, stop_with="-"):
        cmd = [sys.executable, "-c", RUNNER, stop_with, VISION, "--root", self.root, "--work", self.work,
               "--out", self.out, "--model", "vision-model", "--lanes", "extraction"]
        r = subprocess.run(cmd, capture_output=True, text=True, env=self.env, timeout=120)
        self.assertNotIn("ResourceWarning", r.stderr, "vision.py left a file or process open")
        return r.returncode, r.stdout, r.stderr

    def record(self):
        return json.loads(read(os.path.join(self.out, self.eid + ".json")))

    def test_a_good_reply_replaces_the_local_text(self):
        # the model opening its images shows as a tool event; only the vision lane accepts that
        self.fakes.script("agy", default={"kind": "text", "events": [{"event": "tool_call", "name": "view_file"}]})
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
        self.assertEqual(os.path.basename(argv[argv.index("--json-schema") + 1]), "ocr.json")
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
