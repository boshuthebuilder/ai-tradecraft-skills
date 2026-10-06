"""Withheld means purged: every tool's start discards what a withheld document left behind.

`common.purge_withheld` computes the withheld set from the settings and the manifest (a document staged for another
project under the migrations folder, or excluded by the owner) and removes every derived artefact that could carry such
a document or its path: extract records, cards, cached section notes, queued page images and card errors of a withheld
document; a record, card or note whose recorded source path is withheld though its document is not (a canonical copy
that moved into an excluded folder); the hash cache's entries; bundles and rendered files built under another withheld
set. It prints counts, never paths. The first group of tests drives the function; the second runs the tools.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests
"""
import ast
import contextlib
import errno
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
TIMEOUT = 600  # seconds: a tool that hangs fails its test instead of the run
FIXTURE = os.path.join(HERE, "fixture", "Alex Personal")
MANIFEST = os.path.join(HERE, "expected", "manifest.json")
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import common  # noqa: E402
from fake_engines import Fakes, tool_env  # noqa: E402

RB = {"exclude": ["Staff"], "migrations_dir": "_Migrations"}
PLAN_COLUMNS = ["seq", "domain", "depth", "action", "from", "to", "evidence", "reason", "kind", "sweep", "needs_a_look",
                "approved", "approved_at", "status", "executed_at", "note"]


def eid(path):
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(text, bytes) else "w", **({} if isinstance(text, bytes) else
                                                                  {"encoding": "utf-8"})) as f:
        f.write(text)


class PurgeCase(unittest.TestCase):
    """A folder with a manifest of a withheld document in each way, and its work directory."""

    PAY = "Staff/pay.pdf"
    STAGED = "_Migrations/Other Project/Letter.pdf"
    OK = "Public/ok.pdf"

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="purge_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "Alex Personal")
        self.work = os.path.join(self.tmp, "work")
        self.audit = os.path.join(self.root, "_Audit")
        os.makedirs(os.path.join(self.root, "Staff"))
        self.entries = {}
        for path in (self.PAY, self.STAGED, self.OK):
            self.add(path)

    def add(self, path, now_at=None, copies=()):
        i = eid(path)
        self.entries[i] = {"id": i, "current_path": now_at or path, "class": "document", "hashed": True, "flags": [],
                           "copies": [{"path": now_at or path, "kind": "canonical"}]
                           + [{"path": c, "kind": "redundant"} for c in copies]}
        write(os.path.join(self.audit, "manifest.json"), json.dumps({"entries": self.entries}))
        return i

    def record(self, i, path):
        write(os.path.join(self.audit, "extract", i + ".json"), json.dumps({"id": i, "path": path, "pages": []}))

    def card(self, i, path=None):
        card = {"id": i, "title": "t"}
        if path:
            card["card_meta"] = {"path": path}
        write(os.path.join(self.audit, "cards", i + ".json"), json.dumps(card))

    def note(self, i, header=None, name="codex_1_2_abc"):
        path = os.path.join(self.work, "sections", "%s_%s.txt" % (i[:16], name))
        write(path, ("[path] %s\n" % header if header else "") + "[section 1 of 2]\nA note.\n")
        return path

    def has(self, *parts):
        return os.path.lexists(os.path.join(*parts))

    def purge(self, **kw):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            counts = common.purge_withheld(self.root, kw.pop("rb", RB), self.work, **kw)
        return counts, err.getvalue()


class PurgeTest(PurgeCase):
    def test_everything_a_withheld_document_left_is_discarded_and_the_rest_is_kept(self):
        pay, staged, ok = eid(self.PAY), eid(self.STAGED), eid(self.OK)
        for i, path in ((pay, self.PAY), (staged, self.STAGED), (ok, self.OK)):
            self.record(i, path)
            self.card(i, path)
            write(os.path.join(self.work, "vision_queue", "%s_00001.png" % i), b"\x89PNG")
            write(os.path.join(self.work, "state", "card_err_%s.txt" % i), "failed\n")
        notes = {i: self.note(i, p) for i, p in ((pay, self.PAY), (staged, self.STAGED), (ok, self.OK))}
        counts, err = self.purge()
        self.assertEqual(dict(counts), {"extract record": 2, "card": 2, "cached section note": 2,
                                        "queued page image": 2, "card error": 2})
        for i in (pay, staged):
            self.assertFalse(self.has(self.audit, "extract", i + ".json"))
            self.assertFalse(self.has(self.audit, "cards", i + ".json"))
            self.assertFalse(self.has(notes[i]))
            self.assertFalse(self.has(self.work, "vision_queue", "%s_00001.png" % i))
            self.assertFalse(self.has(self.work, "state", "card_err_%s.txt" % i))
        self.assertTrue(all(self.has(*x) for x in ((self.audit, "extract", ok + ".json"), (self.audit, "cards", ok + ".json"),
                                                  (notes[ok],), (self.work, "vision_queue", "%s_00001.png" % ok),
                                                  (self.work, "state", "card_err_%s.txt" % ok))))
        self.assertIn("purged what withheld documents left behind: ", err)
        for named in ("Staff", "pay", "Letter", "Other Project", "_Migrations"):
            self.assertNotIn(named, err, "the purge names counts, never paths")
        self.assertEqual(self.purge()[0], {}, "a second purge finds nothing")

    def test_a_record_card_or_note_carrying_a_withheld_path_goes_though_its_document_is_live(self):
        """The canonical copy moved into an excluded folder and an identical copy is now the document: what was made from
        the old path names it, so it is discarded and the document is read again from the path that is included."""
        i = self.add("Public/copy.pdf")
        self.record(i, "Staff/old.pdf")
        self.card(i, "Staff/old.pdf")
        note = self.note(i, "Staff/old.pdf")
        self.assertEqual(dict(self.purge()[0]), {"extract record": 1, "card": 1, "cached section note": 1})
        self.assertFalse(any(self.has(*x) for x in ((self.audit, "extract", i + ".json"),
                                                    (self.audit, "cards", i + ".json"), (note,))))

    def test_the_queued_images_and_card_error_of_a_document_whose_record_named_a_withheld_path_go_too(self):
        i = self.add("Public/copy.pdf")
        self.record(i, "Staff/old.pdf")
        write(os.path.join(self.work, "vision_queue", "%s_00001.png" % i), b"\x89PNG")
        write(os.path.join(self.work, "state", "card_err_%s.txt" % i), "failed\n")
        self.assertEqual(dict(self.purge()[0]), {"extract record": 1, "queued page image": 1, "card error": 1})

    def test_each_artefact_is_judged_by_its_own_recorded_path(self):
        i = self.add("Public/a.pdf")
        j = self.add("Public/b.pdf")
        k = self.add("Public/c.pdf")
        self.record(i, "Public/a.pdf")
        self.card(i, "Staff/elsewhere.pdf")  # only the card names a withheld path
        self.record(j, "Public/b.pdf")
        self.card(j, "Public/b.pdf")
        note_k = self.note(k, "Staff/elsewhere.pdf")  # only the note does
        note_j = self.note(j, "Public/b.pdf")
        self.assertEqual(dict(self.purge()[0]), {"card": 1, "cached section note": 1})
        self.assertTrue(self.has(self.audit, "extract", i + ".json") and self.has(self.audit, "cards", j + ".json"))
        self.assertFalse(self.has(self.audit, "cards", i + ".json") or self.has(note_k))
        self.assertTrue(self.has(note_j))

    def test_a_record_that_only_moved_between_included_paths_is_kept(self):
        """`extract.py repath` brings such a record up to date: its old path names nothing withheld."""
        i = self.add("Public/new name.pdf")
        self.record(i, "Public/old name.pdf")
        self.card(i, "Public/old name.pdf")
        self.assertEqual(self.purge()[0], {})
        self.assertTrue(self.has(self.audit, "extract", i + ".json") and self.has(self.audit, "cards", i + ".json"))

    def test_a_case_or_unicode_variant_of_a_withheld_path_is_withheld(self):
        accented = unicodedata.normalize("NFC", "Café/menu.txt")
        rb = dict(RB, exclude=["Staff", accented.split("/")[0]])
        for stored in ("STAFF/Pay.pdf", "staff/pay.pdf", unicodedata.normalize("NFD", accented)):
            with self.subTest(stored):
                i = self.add("Public/x.pdf")
                self.record(i, stored)
                self.assertEqual(dict(self.purge(rb=rb)[0]), {"extract record": 1})

    def test_the_hash_cache_loses_the_entries_of_withheld_paths_only(self):
        write(os.path.join(self.work, "hashcache.json"), json.dumps({
            "Staff/pay.pdf|10|1": ["a"], "_Migrations/Other Project/Letter.pdf|10|1": ["b"], "Public/ok.pdf|10|1": ["c"]}))
        counts, _err = self.purge()
        self.assertEqual(dict(counts), {"hash cache entry": 2})
        self.assertEqual(list(json.loads(read(os.path.join(self.work, "hashcache.json")))), ["Public/ok.pdf|10|1"])

    def test_a_purge_inside_a_read_only_folder_is_refused_and_removes_nothing(self):
        i = eid(self.PAY)
        self.record(i, self.PAY)
        with self.assertRaises(common.ToolError) as caught:
            self.purge(read_only=True)
        self.assertIn("--read-only-root, but 1 artefact(s) of withheld documents inside the folder must be purged first",
                      str(caught.exception))
        self.assertNotIn("Staff", str(caught.exception))
        self.assertTrue(self.has(self.audit, "extract", i + ".json"))
        os.remove(os.path.join(self.audit, "extract", i + ".json"))
        self.assertEqual(self.purge(read_only=True)[0], {}, "nothing to purge is not a refusal")

    def test_an_extract_folder_outside_the_folder_is_purged_even_when_the_folder_is_read_only(self):
        outside = os.path.join(self.tmp, "extract")
        i = eid(self.PAY)
        write(os.path.join(outside, i + ".json"), json.dumps({"id": i, "path": self.PAY}))
        counts, _err = self.purge(read_only=True, extract_dirs=[outside])
        self.assertEqual(dict(counts), {"extract record": 1})
        self.assertFalse(self.has(outside, i + ".json"))

    def test_a_missing_manifest_is_no_reason_to_skip_the_purge_of_a_withheld_stored_path(self):
        os.remove(os.path.join(self.audit, "manifest.json"))
        i = eid(self.OK)
        self.record(i, self.PAY)
        self.assertEqual(dict(self.purge()[0]), {"extract record": 1})

    def test_a_record_nested_too_deeply_is_not_a_crash(self):
        write(os.path.join(self.audit, "extract", eid(self.OK) + ".json"), "[" * 200000)
        write(os.path.join(self.audit, "cards", eid(self.OK) + ".json"), "[" * 200000)
        self.assertEqual(self.purge()[0], {})


class RemovalFailureTest(PurgeCase):
    """A removal that fails stops the tool (exit 2) naming the kind and count of what stayed, never a path."""

    def test_a_removal_that_fails_raises_naming_kinds_and_counts_and_no_path(self):
        a, b = eid(self.PAY), eid(self.STAGED)
        for i, path in ((a, self.PAY), (b, self.STAGED)):
            self.record(i, path)
            self.card(i, path)
        real = os.remove

        def remove(path, *args, **kw):
            if os.sep + "extract" + os.sep in path:
                raise PermissionError(errno.EACCES, "Permission denied", path)
            return real(path, *args, **kw)
        with mock.patch("os.remove", remove), self.assertRaises(common.ToolError) as caught:
            self.purge()
        text = str(caught.exception)
        self.assertIn("could not remove 2 extract records of withheld documents (Permission denied)", text)
        for named in ("Staff", "pay", "Letter", self.tmp):
            self.assertNotIn(named, text, "the failure names counts, never paths")
        self.assertFalse(self.has(self.audit, "cards", a + ".json"), "what could be removed was")
        self.assertTrue(self.has(self.audit, "extract", a + ".json"))

    def test_register_output_refuses_a_path_inside_the_folder_and_registers_one_outside(self):
        rb = dict(RB, exclude=[])
        for inside in (os.path.join(self.root, "_Audit", "profile.json"), os.path.join(self.root, "profile.json"), self.root):
            with self.subTest(inside=os.path.relpath(inside, self.root)), self.assertRaises(common.ToolError) as caught:
                common.register_output(self.root, self.work, rb, inside)
            self.assertIn("are working files, never written inside the folder", str(caught.exception))
        self.assertFalse(self.has(self.work, "state", "rendered.json"), "a refused path was registered")
        outside = os.path.join(self.tmp, "report.json")
        common.register_output(self.root, self.work, rb, outside)
        with open(os.path.join(self.work, "state", "rendered.json"), encoding="utf-8") as f:
            self.assertEqual([i["path"] for i in json.load(f)], [outside])

    def test_inside_the_folder_is_decided_on_resolved_real_paths_folded_so_a_letter_case_cannot_get_out(self):
        """On a case-insensitive volume `ALEX PERSONAL/x` is `Alex Personal/x`: every check of a path against the folder
        compares resolved real paths folded as `common.fold` folds them."""
        shouted = os.path.join(self.tmp, "ALEX PERSONAL")
        link = os.path.join(self.tmp, "link-to-the-folder")
        os.symlink(self.root, link)
        self.addCleanup(os.remove, link)
        for where in (shouted, os.path.join(shouted, "_Audit"), os.path.join(self.root.upper(), "_AUDIT"), link,
                      os.path.join(link, "_audit")):
            out = os.path.join(where, "report.json")
            with self.subTest(out=os.path.relpath(out, self.tmp)):
                with self.assertRaises(common.ToolError) as caught:
                    common.working_file(self.root, out, "reports")
                self.assertIn("are working files, never written inside the folder", str(caught.exception))
                with self.assertRaises(common.ToolError):
                    common.register_output(self.root, self.work, dict(RB, exclude=[]), out)
                with self.assertRaises(common.ToolError) as caught:
                    common.Writer(self.root).check(out)
                self.assertIn("--read-only-root", str(caught.exception))
        self.assertEqual(common.working_file(self.root, os.path.join(self.tmp, "elsewhere", "r.json"), "reports"),
                         os.path.join(self.tmp, "elsewhere", "r.json"))
        self.assertTrue(common.within(self.root, os.path.join(self.root.upper(), "x")))
        self.assertFalse(common.within(self.root, self.root + " copy"), "a sibling that shares a prefix is not inside")

    def test_a_work_folder_spelt_in_another_case_is_still_inside_the_folder(self):
        env = dict(os.environ, HOME=os.path.join(self.tmp, "home"))
        shouted = os.path.join(self.tmp, "ALEX PERSONAL", "work")
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "settings.py"), "compile", "--root", self.root, "--work",
                            shouted], capture_output=True, text=True, env=env, timeout=TIMEOUT)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--work must be outside the folder", r.stderr)

    def test_the_message_says_where_the_artefacts_that_stayed_are_without_naming_one(self):
        a = eid(self.PAY)
        self.record(a, self.PAY)
        self.card(a, self.PAY)
        stuck = os.path.join(self.tmp, "stuck.md")
        write(stuck, "x\n")
        common.register_rendered(self.work, stuck, "old")
        real = os.remove

        def remove(path, *args, **kw):
            if os.sep + "extract" + os.sep in path or os.sep + "cards" + os.sep in path or path == stuck:
                raise PermissionError(errno.EACCES, "Permission denied", path)
            return real(path, *args, **kw)
        with mock.patch("os.remove", remove), self.assertRaises(common.ToolError) as caught:
            self.purge()
        text = str(caught.exception)
        for where in ("card in the cards folder", "extract record in the extract records folder",
                      "rendered file listed in %s" % os.path.join(self.work, "state", "rendered.json")):
            self.assertIn(where, text)
        for named in ("Staff", "pay.pdf", stuck, self.audit):
            self.assertNotIn(named, text, "the message names a path of a withheld document")

    def test_a_rendered_file_that_could_not_be_removed_stays_registered_for_the_next_purge(self):
        stuck, gone = os.path.join(self.tmp, "stuck.md"), os.path.join(self.tmp, "gone.md")
        for path in (stuck, gone):
            write(path, "x\n")
            common.register_rendered(self.work, path, "old")
        real = os.remove

        def remove(path, *args, **kw):
            if path == stuck:
                raise PermissionError(errno.EACCES, "Permission denied", path)
            return real(path, *args, **kw)
        with mock.patch("os.remove", remove), self.assertRaises(common.ToolError) as caught:
            self.purge()
        self.assertIn("could not remove 1 rendered file", str(caught.exception))
        with open(os.path.join(self.work, "state", "rendered.json"), encoding="utf-8") as f:
            self.assertEqual([i["path"] for i in json.load(f)], [stuck])
        self.assertFalse(self.has(gone))
        self.assertEqual(dict(self.purge()[0]), {"rendered file": 1}, "the next purge removes it")

    @unittest.skipIf(os.name != "posix" or os.geteuid() == 0, "a directory that cannot be written needs a non-root user")
    def test_a_tool_stops_with_exit_2_when_the_folder_will_not_let_a_record_go(self):
        tmp = os.path.realpath(tempfile.mkdtemp(prefix="purge_stuck_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        root = os.path.join(tmp, "Alex Personal")
        shutil.copytree(FIXTURE, root)
        shutil.copy(MANIFEST, os.path.join(root, "_Audit", "manifest.json"))
        env = dict(os.environ, HOME=os.path.join(tmp, "home"))
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "settings.py"), "compile", "--root", root, "--work",
                            os.path.join(tmp, "work")], capture_output=True, text=True, env=env, timeout=TIMEOUT)
        self.assertEqual(r.returncode, 0, r.stderr)
        twin = os.path.join(root, ".familyai", "rulebook.json")
        write(twin, json.dumps(dict(json.loads(read(twin)), exclude=["06 Work"]), ensure_ascii=False))
        extract = os.path.join(root, "_Audit", "extract")
        os.chmod(extract, 0o500)  # records can be read, none removed
        self.addCleanup(os.chmod, extract, 0o700)
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "wiki.py"), "profile", "--root", root, "--work",
                            os.path.join(tmp, "work")], capture_output=True, text=True, env=env, timeout=TIMEOUT)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stdout, "", "the tool carried on")
        self.assertIn("error: refused: could not remove 2 extract records of withheld documents (Permission denied)",
                      r.stderr)
        self.assertNotIn("Contract", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


class RenderedFilesTest(PurgeCase):
    """Bundles, rendered briefs and review prompts are purged whenever the withheld set changed since they were written."""

    def digest(self, **changes):
        return common.withheld_digest(dict(RB, **changes), self.entries)

    def bundles(self, where, digest):
        write(os.path.join(where, "bundles.json"), json.dumps({"withheld_sha256": digest}))
        write(os.path.join(where, "bundle_10.jsonl"), "{}\n")
        write(os.path.join(where, "notes.txt"), "kept\n")

    def test_bundles_built_under_another_withheld_set_are_removed_and_the_current_ones_kept(self):
        here, elsewhere = os.path.join(self.work, "bundles"), os.path.join(self.tmp, "kept-bundles")
        self.bundles(here, "old")
        self.bundles(elsewhere, "old")
        common.register_rendered(self.work, elsewhere, "old", "bundles")
        counts, _err = self.purge()
        self.assertEqual(dict(counts), {"bundle file": 4})
        self.assertEqual((sorted(os.listdir(here)), sorted(os.listdir(elsewhere))), (["notes.txt"], ["notes.txt"]))
        self.bundles(here, self.digest())
        self.assertEqual(self.purge()[0], {})
        self.assertEqual(sorted(os.listdir(here)), ["bundle_10.jsonl", "bundles.json", "notes.txt"])

    def test_a_rendered_file_registered_under_another_set_is_removed_and_one_under_this_set_kept(self):
        old, new = os.path.join(self.tmp, "brief-old.md"), os.path.join(self.tmp, "brief-new.md")
        write(old, "a brief\n")
        write(new, "a brief\n")
        common.register_rendered(self.work, old, "old")
        common.register_rendered(self.work, new, self.digest())
        counts, _err = self.purge()
        self.assertEqual(dict(counts), {"rendered file": 1})
        self.assertFalse(self.has(old))
        self.assertTrue(self.has(new))

    def test_a_review_prompt_nothing_registered_is_removed(self):
        prompt = os.path.join(self.work, "reviews", "20 Finance", "Tax.owner.md")
        write(prompt, "a prompt\n")
        self.assertEqual(dict(self.purge()[0]), {"rendered file": 1})
        self.assertFalse(self.has(prompt))

    def test_the_digest_covers_the_exclusions_the_migrations_folder_and_every_path_of_a_withheld_entry(self):
        base = self.digest()
        self.assertEqual(self.digest(), base)
        self.assertNotEqual(self.digest(exclude=["Staff", "Public"]), base, "an exclusion added")
        self.assertNotEqual(self.digest(exclude=[]), base, "an exclusion dropped")
        self.assertEqual(self.digest(exclude=["STAFF/"]), base, "the same exclusion spelt another way")
        self.assertNotEqual(self.digest(migrations_dir="_Leaving"), base, "another migrations folder")
        self.entries[eid(self.PAY)]["copies"].append({"path": "Public/pay copy.pdf", "kind": "redundant"})
        self.assertNotEqual(self.digest(), base, "a copy, at an included path, of a withheld document")
        again = self.digest()
        self.entries[eid(self.OK)]["copies"].append({"path": "Public/ok copy.pdf", "kind": "redundant"})
        self.assertEqual(self.digest(), again, "a copy of a document that is not withheld changes nothing")


class PriorPathsTest(PurgeCase):
    """The paths a withheld document held before it moved are withheld too, from the one function every consumer uses."""

    def test_staged_origin_is_the_path_under_the_project_folder(self):
        for path, want in (("_Migrations/Other Project/02 Finance/Old.pdf", "02 Finance/Old.pdf"),
                           ("_migrations/Other Project/Old.pdf", "Old.pdf"), ("_Migrations/Other Project", None),
                           ("_Migrations/Other Project/", None), ("_Migrations", None), ("Public/ok.pdf", None)):
            with self.subTest(path):
                self.assertEqual(common.staged_origin(RB, path), want)

    def test_the_history_and_the_staged_from_path_of_a_withheld_document_are_withheld_unless_a_live_document_holds_them(self):
        self.entries[eid(self.STAGED)]["current_path"] = self.STAGED
        self.entries[eid(self.PAY)]["rename_history"] = [{"path": "Old/pay draft.pdf"}, {"path": self.PAY}]
        self.entries[eid(self.OK)]["rename_history"] = [{"path": "Old/ok before.pdf"}]  # not withheld: not read
        got = common.withheld_paths(RB, self.entries)
        self.assertEqual(got[common.fold("Old/pay draft.pdf")], "excluded")
        self.assertEqual(got[common.fold("Letter.pdf")], "migrations")
        self.assertNotIn(common.fold("Old/ok before.pdf"), got)
        self.assertEqual(set(common.prior_paths(RB, self.entries)), {common.fold("Old/pay draft.pdf"),
                                                                      common.fold("Letter.pdf")})
        self.add("Old/pay draft.pdf")  # a live document that is not withheld holds it now
        self.assertNotIn(common.fold("Old/pay draft.pdf"), common.withheld_paths(RB, self.entries))

    def test_a_departed_withheld_entry_contributes_nothing(self):
        self.entries[eid(self.PAY)]["rename_history"] = [{"path": "Old/pay draft.pdf"}]
        self.entries[eid(self.PAY)]["flags"] = ["departed"]
        self.assertNotIn(common.fold("Old/pay draft.pdf"), common.withheld_paths(RB, self.entries))


# What each tool does with its own work directory is written into the folder's tree, so a tool is run on a copy.
class EveryToolTest(unittest.TestCase):
    """Run the tools on a folder holding the artefacts of a withheld document: each discards them at its start."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="purge_tools_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def fresh(self):
        root = os.path.join(self.tmp, "run", "Alex Personal")
        shutil.rmtree(os.path.dirname(root), True)
        shutil.copytree(FIXTURE, root)
        shutil.copy(MANIFEST, os.path.join(root, "_Audit", "manifest.json"))
        work = os.path.join(self.tmp, "run", "work")
        self.run_tool("settings.py", "compile", "--root", root, "--work", work)
        twin = os.path.join(root, ".familyai", "rulebook.json")
        with open(twin, encoding="utf-8") as f:
            data = json.load(f)
        write(twin, json.dumps(dict(data, exclude=["06 Work"]), ensure_ascii=False))
        with open(MANIFEST, encoding="utf-8") as f:
            entries = {e["current_path"]: h for h, e in json.load(f)["entries"].items()}
        self.contract, self.essay = entries["06 Work/Contract.docx"], entries["06 Work/Essay.docx"]
        for doc in (self.contract, self.essay):  # the fixture holds a record and a card of each
            self.assertTrue(os.path.exists(os.path.join(root, "_Audit", "extract", doc + ".json")))
            self.assertTrue(os.path.exists(os.path.join(root, "_Audit", "cards", doc + ".json")))
        return root, work

    def run_tool(self, tool, *args):
        env = dict(os.environ, HOME=os.path.join(self.tmp, "home"))
        r = subprocess.run([sys.executable, os.path.join(TOOLS, tool)] + list(args), capture_output=True, text=True,
                           env=env, timeout=TIMEOUT)
        return r.returncode, r.stdout, r.stderr

    PURGED = "purged what withheld documents left behind: 2 cards, 2 extract records"  # Contract and Essay, in 06 Work

    def assert_purged(self, root, err):
        self.assertIn(self.PURGED, err)
        for named in ("Contract", "Essay", "06 Work"):
            self.assertNotIn(named, err, "the purge names counts, never paths")
        for doc in (self.contract, self.essay):
            self.assertFalse(os.path.lexists(os.path.join(root, "_Audit", "extract", doc + ".json")))
            self.assertFalse(os.path.lexists(os.path.join(root, "_Audit", "cards", doc + ".json")))

    def test_every_tool_discards_the_artefacts_of_a_withheld_document_before_it_reads_anything(self):
        plans = os.path.join(self.tmp, "plans")
        tools = (("audit.py", lambda r, w: ["--root", r, "--work", w]),
                 ("cards.py", lambda r, w: ["build", "--root", r, "--work", w]),
                 ("wiki.py", lambda r, w: ["profile", "--root", r, "--work", w]),
                 ("wiki.py", lambda r, w: ["check", "--root", r, "--work", w]),
                 ("wiki.py", lambda r, w: ["bundles", "--root", r, "--work", w]),
                 ("wiki.py", lambda r, w: ["drift", "--root", r, "--work", w]),
                 ("plan.py", lambda r, w: ["light", "--root", r, "--out", plans]),
                 ("plan.py", lambda r, w: ["check", "--root", r, "--plan", os.path.join(plans, "move-plan.csv")]),
                 ("readiness.py", lambda r, w: ["--root", r, "--work", w]),
                 ("refs.py", lambda r, w: ["--root", r, "--work", w]),
                 ("settings.py", lambda r, w: ["check", "--root", r, "--work", w]),
                 ("extract.py", lambda r, w: ["repath", "--root", r, "--work", w]))
        for tool, make in tools:
            root, work = self.fresh()
            shutil.rmtree(plans, True)
            write(os.path.join(plans, "move-plan.csv"), ",".join(PLAN_COLUMNS) + "\n")
            args = make(root, work)
            with self.subTest(tool=tool, args=args[:1]):
                code, out, err = self.run_tool(tool, *args)
                self.assertNotIn("Traceback", err)
                self.assert_purged(root, err)

    def test_the_vision_lane_purges_at_its_start_too(self):
        root, work = self.fresh()
        write(os.path.join(work, "state", "extraction.done"), "done")
        runner = ("import runpy, sys, time\ntime.sleep = lambda s: None\nsys.argv = sys.argv[1:]\n"
                  "runpy.run_path(sys.argv[0], run_name='__main__')")
        r = subprocess.run([sys.executable, "-c", runner, os.path.join(TOOLS, "vision.py"), "--root", root, "--work", work,
                            "--lanes", "extraction", "--model", "m"], capture_output=True, text=True,
                           env=tool_env(self.tmp, Fakes(self.tmp)), timeout=TIMEOUT)  # the fake agy, never a real one
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_purged(root, r.stderr)


class EveryToolIsWiredTest(unittest.TestCase):
    """A tool that reads a folder is run through `common.resolve`, which purges: a command added without it fails here."""

    def source(self, name):
        with open(os.path.join(TOOLS, name), encoding="utf-8") as f:
            return f.read()

    def test_every_command_of_wiki_py_resolves_the_folder_through_the_common_loader(self):
        src = self.source("wiki.py")
        commands = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)
                    and any(ast.unparse(d) == "os_errors" for d in n.decorator_list)]
        self.assertGreaterEqual(len(commands), 10)
        for fn in commands:
            with self.subTest(command=fn.name):
                self.assertIn("common.resolve(", ast.get_source_segment(src, fn))
        parser = src[src.index("def main():"):]
        for name in ("profile", "bundles", "brief", "check", "rationale", "review-prompts", "accept", "move", "drift",
                     "deadlines", "chart"):
            self.assertIn('add_parser("%s")' % name, parser)

    def test_every_other_tool_that_takes_a_folder_resolves_it_through_the_common_loader(self):
        for name in ("audit.py", "extract.py", "cards.py", "vision.py", "refs.py", "readiness.py", "settings.py"):
            with self.subTest(tool=name):
                self.assertIn("common.resolve(", self.source(name))
        self.assertIn("common.purge_at_start(", self.source("plan.py"))
        self.assertIn("purge_at_start(root, settings_dir, work, args, verify, extract, cards, manifest)",
                      self.source("common.py"))

    def test_plan_py_and_the_common_loader_resolve_the_work_directory_in_one_place(self):
        """What `plan.py` purges is the work directory `common.work_dir_for` gives it, the function `common.resolve`
        uses for every other tool: not `common.default_work`, which would clear a folder it was not given."""
        plan, common_src = self.source("plan.py"), self.source("common.py")
        self.assertIn("work = common.work_dir_for(root, a.work)", plan)
        self.assertIn("common.purge_at_start(root, settings_dir, work, a, True)", plan)
        self.assertNotIn("default_work", plan)
        self.assertIn("work = work_dir_for(root, args.work)", common_src)

    def test_the_workers_purge_again_before_each_batch(self):
        self.assertIn("common.purge_withheld(", self.source("vision.py"))
        cards = self.source("cards.py")
        self.assertIn("def refresh(self):", cards)
        self.assertIn("        run.refresh()\n", cards)


if __name__ == "__main__":
    unittest.main()
