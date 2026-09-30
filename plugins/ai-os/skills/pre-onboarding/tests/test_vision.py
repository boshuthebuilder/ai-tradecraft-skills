"""The vision lane against a fake `agy`: the images alone in a fresh folder, the whole-batch join (every image back,
in the order sent, or nothing applied), three tries then `unread` with the local text kept, and quota waits that do
not count as tries.

vision.py polls with `time.sleep(60)`; the runner below replaces `time.sleep` with a no-op in the tool's own process
so the lane runs to its end at once. Nothing else about the tool changes.

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
from fake_engines import Fakes, tool_env  # noqa: E402

RUNNER = ("import runpy, sys, time\n"
          "time.sleep = lambda seconds: None\n"
          "sys.argv = sys.argv[1:]\n"
          "runpy.run_path(sys.argv[0], run_name='__main__')\n")


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
        self.id = hashlib.sha256(b"01 Identity/Scan.pdf").hexdigest()
        self.queue = os.path.join(self.work, "vision_queue")
        for n in (1, 2):
            write(os.path.join(self.queue, "%s_%05d.png" % (self.id, n)), b"\x89PNG fake page %d" % n)
        rec = {"id": self.id, "path": "01 Identity/Scan.pdf", "class": "document", "status": "needs_vision",
               "page_count": 3, "tiers": {"pending_vision": 2, "text_layer": 1},
               "pages": [{"n": 1, "tier": "pending_vision", "text": "local one", "queued": True},
                         {"n": 2, "tier": "pending_vision", "text": "local two", "queued": True},
                         {"n": 3, "tier": "text_layer", "text": "typed page"}]}
        write(os.path.join(self.out, self.id + ".json"), json.dumps(rec))

    def vision(self):
        cmd = [sys.executable, "-c", RUNNER, VISION, "--root", self.root, "--work", self.work, "--out", self.out,
               "--model", "vision-model", "--lanes", "extraction"]
        r = subprocess.run(cmd, capture_output=True, text=True, env=self.env, timeout=120)
        return r.returncode, r.stdout, r.stderr

    def record(self):
        return json.loads(read(os.path.join(self.out, self.id + ".json")))

    def test_a_good_reply_replaces_the_local_text(self):
        self.fakes.script("agy", default={"kind": "text"})
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
        self.assertEqual(sorted(k for k in call["env"] if k.endswith("_API_KEY")), [])
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


if __name__ == "__main__":
    unittest.main()
