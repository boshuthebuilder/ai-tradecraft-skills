"""The curation plan tools on fixture copies: proposals, approval, the executor's guards, deletes to an injected Bin,
the undo log and the re-audit proof.

Every run of the executor names its own Bin (`--bin`) and runs with a temporary HOME, so nothing here can reach the
real Bin even by mistake.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests
"""
import csv
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
TIMEOUT = 600  # seconds: a tool that hangs fails its test instead of the run
FIXTURE = os.path.join(HERE, "fixture", "Alex Personal")
EXPECTED = os.path.join(HERE, "expected")
PAST = 1719748800           # 2024-06-30T12:00:00Z: the frozen clock of a move phase, so its order is not left to luck
sys.path.insert(0, TOOLS)
import common  # noqa: E402
import plan  # noqa: E402

BANK = "02 Finance/Bank statement 2024-03.pdf"
BANK_COPY = "02 Finance/Bank statement 2024-03 (1).pdf"
PASSPORT_PACK = "01 Identity/Passport renewal 2021/Passport scan.pdf"
ESSAY_WORKING = "04 Study/Essay.docx"
LEASE_PAGES = "03 Home/Lease renewal.pages"
LEASE_NOTES = "03 Home/Lease notes .txt"

# plan.py with a rename that lands and is then written to, as a sync client might, before the executor re-hashes.
DRIFTING_RENAME = """
import os
import sys
sys.path.insert(0, sys.argv[1])
import common
import plan
real_rename = os.rename


def rename(src, dst):
    real_rename(src, dst)
    with open(dst, "ab") as f:
        f.write(b"!")


os.rename = rename
sys.argv = ["plan.py"] + sys.argv[2:]
common.run_main(plan.main)
"""


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data.encode("utf-8") if isinstance(data, str) else data)


def tree_digest(root, skip=()):
    """Every file's relative path and bytes (a symlink's target instead of its bytes); `skip` names top-level
    entries left out."""
    h = hashlib.sha256()
    for d, ds, fs in os.walk(root):
        ds.sort()
        if d == root:
            ds[:] = [x for x in ds if x not in skip]
        for f in sorted(fs + [x for x in ds if os.path.islink(os.path.join(d, x))]):
            p = os.path.join(d, f)
            data = b"-> " + os.readlink(p).encode() if os.path.islink(p) else read(p, "rb")
            h.update(os.path.relpath(p, root).encode() + b"\0" + data + b"\n")
    return h.hexdigest()


def read_rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=plan.COLS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in plan.COLS})


def row(seq, action, frm="", to="", evidence="", kind="", domain=None, approved="approved", status="pending"):
    return {"seq": str(seq), "domain": domain or plan.domain_of((frm or to).rstrip("/")), "depth": "light",
            "action": action, "from": frm, "to": to, "evidence": evidence, "kind": kind, "approved": approved,
            "status": status}


class PlanCase(unittest.TestCase):
    """A fixture copy audited into its own _Audit/, a plan beside it, an empty Bin and a temporary HOME."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="plan_test_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        self.bin = os.path.join(self.tmp, "Bin")
        os.makedirs(self.home)
        os.makedirs(self.bin)
        self.root = os.path.join(self.tmp, "a", "Alex Personal")
        shutil.copytree(FIXTURE, self.root)
        self.prepare()
        self.manifest_path = os.path.join(self.root, "_Audit", "manifest.json")
        self.audit()
        self.plan = os.path.join(self.tmp, "plan", "move-plan.csv")

    def prepare(self):
        """Changes to the fixture copy before the first audit."""

    def tearDown(self):
        self.assertFalse(os.path.exists(os.path.join(self.home, ".Trash")), "something used the default Bin")

    def run_tool(self, tool, *args, now=None, script=None, cwd=None):
        """Run a tool (in `cwd`, else the current directory) with a temporary HOME and every ResourceWarning an error;
        a file it leaves open fails."""
        env = dict(os.environ, HOME=self.home, PYTHONWARNINGS="error::ResourceWarning")
        env.pop("PRE_ONBOARDING_NOW", None)
        if now is not None:
            env["PRE_ONBOARDING_NOW"] = str(now)
        cmd = [sys.executable, "-c", script, TOOLS] if script else [sys.executable, os.path.join(TOOLS, tool)]
        r = subprocess.run(cmd + list(args), capture_output=True, text=True, env=env, timeout=TIMEOUT, cwd=cwd)
        self.assertNotIn("ResourceWarning", r.stderr, "%s left a file open" % tool)
        return r.returncode, r.stdout, r.stderr

    def run_plan(self, *args, **kw):
        return self.run_tool("plan.py", *args, **kw)

    def audit(self):
        code, _o, err = self.run_tool("audit.py", "--root", self.root, "--work", os.path.join(self.tmp, "work"))
        self.assertEqual(code, 0, err)
        self.manifest = json.loads(read(self.manifest_path))
        self.ids = {p: h for p, (h, _k, _o) in plan.live_paths(self.manifest["entries"]).items()}
        return self.manifest

    def path(self, rel):
        return os.path.join(self.root, rel)

    def execute(self, *extra, apply=True, now=None, script=None):
        args = ["execute", "--root", self.root, "--plan", self.plan, "--bin", self.bin] + list(extra)
        return self.run_plan(*(args + (["--apply"] if apply else [])), now=now, script=script)

    def rows(self):
        return {r["seq"]: r for r in read_rows(self.plan)}

    def status(self, seq):
        r = self.rows()[str(seq)]
        return r["status"], r["note"]

    def undo_lines(self):
        p = os.path.join(os.path.dirname(self.plan), "undo.log")
        return [json.loads(x) for x in read(p).splitlines()] if os.path.exists(p) else []

    def bin_names(self):
        return sorted(os.listdir(self.bin))

    def refused(self, rows, note, seq=1, phase=()):
        """Execute a plan whose row `seq` must fail with `note`, leaving the folder and the Bin untouched."""
        write_rows(self.plan, rows)
        before = tree_digest(self.root)
        code, out, err = self.execute(*phase)
        self.assertEqual(code, 1, out + err)
        self.assertNotIn("Traceback", err)
        status, got = self.status(seq)
        self.assertEqual(status, "failed", got)
        self.assertIn(note, got)
        self.assertEqual(tree_digest(self.root), before, "a refused row changed the folder")
        self.assertEqual(self.bin_names(), [])


# ---------------------------------------------------------------------------------------------- proposals

class ProposalTest(PlanCase):
    def test_the_light_plan_is_byte_identical_to_expected(self):
        code, _o, err = self.run_plan("light", "--root", self.root, "--out", os.path.dirname(self.plan))
        self.assertEqual(code, 0, err)
        self.assertEqual(read(self.plan, "rb"), read(os.path.join(EXPECTED, "plan-light.csv"), "rb"))

    def propose(self, cmd, out, *, code=0):
        """`cmd` proposing into the plan folder `out`: light, or migrate or return of one file."""
        paths = os.path.join(self.tmp, cmd + "-paths.txt")
        write(paths, {"light": "", "migrate": "06 Work/Contract.docx\n",
                      "return": "02 Finance/Old invoice.pdf\n"}[cmd])
        extra = [] if cmd == "light" else ["--project", "Other Project" if cmd == "return" else "Household",
                                           "--paths-file", paths]
        got, o, err = self.run_plan(cmd, "--root", self.root, "--out", out, *extra)
        self.assertEqual(got, code, o + err)
        self.assertNotIn("Traceback", err)
        return err

    def test_a_proposal_does_not_replace_a_plan_the_owner_has_begun_to_decide(self):
        for cmd in ("light", "migrate", "return"):
            for decision in ([], ["--decline"], ["--defer"]):
                with self.subTest(cmd=cmd, decision=decision):
                    out = os.path.join(self.tmp, "round-%s-%s" % (cmd, decision[0][2:] if decision else "approve"))
                    self.propose(cmd, out)
                    plan_path = os.path.join(out, "move-plan.csv")
                    self.run_plan("approve", "--plan", plan_path, "--rows", "1", "--note", "Alex agreed", *decision)
                    before = tree_digest(out)
                    err = self.propose(cmd, out, code=2)
                    self.assertIn("error: %s already holds 1 approved, declined or deferred row(s)" % plan_path, err)
                    self.assertIn("choose a new plan folder", err)
                    self.assertEqual(tree_digest(out), before, "the owner's decision was overwritten")

    def test_an_untouched_proposal_may_be_proposed_again(self):
        for cmd in ("light", "migrate", "return"):
            with self.subTest(cmd):
                out = os.path.join(self.tmp, "again-" + cmd)
                self.propose(cmd, out)
                plan_path = os.path.join(out, "move-plan.csv")
                proposed = read(plan_path, "rb")
                rows = read_rows(plan_path)
                rows[0]["to"], rows[0]["reason"] = "somewhere", "edited by hand"
                write_rows(plan_path, rows)
                self.propose(cmd, out)
                self.assertEqual(read(plan_path, "rb"), proposed, "a proposal nobody has decided is replaced")

    def test_a_plan_that_cannot_be_read_is_not_replaced_unseen(self):
        out = os.path.join(self.tmp, "unreadable")
        write(os.path.join(out, "move-plan.csv"), b"\xff\xfe not a plan")
        err = self.propose("light", out, code=2)
        self.assertIn("already exists and cannot be read as a plan", err)
        self.assertIn("choose a new plan folder", err)
        self.assertEqual(read(os.path.join(out, "move-plan.csv"), "rb"), b"\xff\xfe not a plan")

    def test_deletes_only(self):
        self.run_plan("light", "--root", self.root, "--out", os.path.dirname(self.plan), "--deletes-only")
        self.assertEqual([(r["action"], r["from"], r["kind"]) for r in self.rows().values()],
                         [("delete", BANK_COPY, "redundant"),
                          ("delete", "05 Archive/Cours de français.pdf", "redundant"),
                          ("delete", "05 Archive/Slides.pptx", "redundant"),
                          ("delete", "05 Archive/中文课程.pdf", "redundant")])

    def test_approve_and_decline(self):
        self.run_plan("light", "--root", self.root, "--out", os.path.dirname(self.plan))
        code, _o, err = self.run_plan("approve", "--plan", self.plan, "--rows", "1-2,4", "--note", "agreed with Alex")
        self.assertEqual(code, 0, err)
        self.run_plan("approve", "--plan", self.plan, "--rows", "3", "--decline", "--note", "keep the space")
        self.run_plan("approve", "--plan", self.plan, "--rows", "5", "--defer", "--note", "next round")
        got = {s: (r["approved"], r["status"], r["note"]) for s, r in self.rows().items()}
        self.assertEqual(got["1"], ("approved", "pending", "agreed with Alex"))
        self.assertEqual(got["4"], ("approved", "pending", "agreed with Alex"))
        self.assertEqual(got["3"], ("declined", "skipped", "keep the space"))
        self.assertEqual(got["5"], ("deferred", "skipped", "next round"))
        self.assertEqual(got["6"], ("", "proposed", ""))
        code, _o, err = self.run_plan("approve", "--plan", self.plan, "--rows", "6", "--decline", "--defer")
        self.assertEqual(code, 2, err)
        self.assertEqual(self.rows()["6"]["approved"], "")


class StagedAndRedundantNamesTest(PlanCase):
    def prepare(self):
        write(self.path("_Migrations/Other Project/Draft .txt"), "a draft staged for another project")
        shutil.copy(self.path(BANK), self.path("02 Finance/Bank statement 2024-03 duplicate .pdf"))

    def test_no_name_fix_for_a_staged_file_or_a_redundant_copy(self):
        self.run_plan("light", "--root", self.root, "--out", os.path.dirname(self.plan))
        rows = list(self.rows().values())
        self.assertEqual(sorted(r["from"] for r in rows if r["action"] == "rename"),
                         ["03 Home/Lease notes .txt", "03 Home/Utilities /"])
        self.assertIn("02 Finance/Bank statement 2024-03 duplicate .pdf",
                      [r["from"] for r in rows if r["action"] == "delete"])


class RmdirsProposalTest(PlanCase):
    def test_the_top_most_folders_the_moves_empty(self):
        write(self.path("06 Work/.DS_Store"), "finder")
        write_rows(self.plan, [
            row(1, "move", "06 Work/Essay.docx", "03 Home/Essay.docx", self.ids["06 Work/Essay.docx"]),
            row(2, "move", "06 Work/Contract.docx", "03 Home/Contract.docx", self.ids["06 Work/Contract.docx"]),
            row(3, "move", "03 Home/Utilities /Electricity bill.pdf", "03 Home/Electricity bill.pdf",
                self.ids["03 Home/Utilities /Electricity bill.pdf"]),
            row(4, "move", "04 Study/Notes.rtf", "03 Home/Notes.rtf", self.ids["04 Study/Notes.rtf"], approved=""),
        ])
        for _ in range(2):                           # a second run adds nothing
            code, _o, err = self.run_plan("rmdirs", "--root", self.root, "--plan", self.plan)
            self.assertEqual(code, 0, err)
        added = [(r["seq"], r["action"], r["from"], r["approved"], r["status"]) for r in self.rows().values()
                 if r["action"] == "rmdir"]
        self.assertEqual(added, [("5", "rmdir", "03 Home/Utilities /", "", "proposed"),
                                 ("6", "rmdir", "06 Work/", "", "proposed")])

    def test_a_file_that_stays_keeps_its_folder(self):
        write(self.path("06 Work/.DS_Store"), "finder")
        write_rows(self.plan, [row(1, "move", "06 Work/Essay.docx", "04 Study/Essays/Essay.docx",
                                   self.ids["06 Work/Essay.docx"])])
        self.run_plan("rmdirs", "--root", self.root, "--plan", self.plan)
        self.assertEqual([r["action"] for r in self.rows().values()], ["move"])

    def test_a_package_that_stays_keeps_its_folder_and_only_the_top_is_proposed(self):
        moves = [row(n, "move", rel, "06 Work/" + os.path.basename(rel), self.ids[rel]) for n, rel in enumerate(
            ("03 Home/Lease renewal.pdf", "03 Home/Lease notes .txt", "03 Home/Utilities /Electricity bill.pdf"), 1)]
        write_rows(self.plan, moves)
        self.run_plan("rmdirs", "--root", self.root, "--plan", self.plan)
        self.assertEqual([r["from"] for r in self.rows().values() if r["action"] == "rmdir"], ["03 Home/Utilities /"])
        write_rows(self.plan, moves + [row(4, "move", LEASE_PAGES, "06 Work/Lease renewal.pages",
                                           self.ids[LEASE_PAGES])])
        self.run_plan("rmdirs", "--root", self.root, "--plan", self.plan)
        self.assertEqual([r["from"] for r in self.rows().values() if r["action"] == "rmdir"], ["03 Home/"])

    def test_approved_when_the_owner_already_agreed(self):
        write_rows(self.plan, [row(1, "move", "03 Home/Utilities /Electricity bill.pdf", "03 Home/Bill.pdf",
                                   self.ids["03 Home/Utilities /Electricity bill.pdf"])])
        self.run_plan("rmdirs", "--root", self.root, "--plan", self.plan, "--approve-note", "Alex agreed")
        r = self.rows()["2"]
        self.assertEqual((r["from"], r["approved"], r["status"], r["note"]),
                         ("03 Home/Utilities /", "approved", "pending", "Alex agreed"))


# ---------------------------------------------------------------------------------------------- moves

class MoveGuardTest(PlanCase):
    def test_a_move_and_its_undo_record(self):
        write_rows(self.plan, [row(1, "move", BANK, "02 Finance/Bank/Statement 2024-03.pdf", self.ids[BANK])])
        code, out, err = self.execute()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(os.path.isfile(self.path("02 Finance/Bank/Statement 2024-03.pdf")))
        self.assertFalse(os.path.exists(self.path(BANK)))
        self.assertEqual(self.status(1), ("done", "undo.log seq 1"))
        intent, done = self.undo_lines()
        self.assertEqual((intent["phase"], intent["op"], intent["from"], intent["sha256"]),
                         ("intent", "move", BANK, self.ids[BANK]))
        self.assertEqual((done["phase"], done["undo"]), ("done", {"op": "move", "from": "02 Finance/Bank/Statement "
                                                                  "2024-03.pdf", "to": BANK}))

    def test_containment(self):
        outside = os.path.join(self.tmp, "a", "outside.txt")
        write(outside, "a file beside the folder")
        cases = {
            "from outside": row(1, "move", "../outside.txt", "02 Finance/outside.txt",
                                common.content_id(outside)),
            "to outside": row(1, "move", BANK, "../Bank statement.pdf", self.ids[BANK]),
            "to an absolute path": row(1, "move", BANK, os.path.join(self.tmp, "Bank statement.pdf"),
                                       self.ids[BANK]),
        }
        for name, r in cases.items():
            with self.subTest(name):
                self.refused([r], "outside the folder")
                self.assertTrue(os.path.isfile(outside))
                self.assertEqual(os.listdir(self.tmp).count("Bank statement.pdf"), 0)

    def test_no_symlink_on_either_path(self):
        os.symlink(self.path("02 Finance"), self.path("Money"))
        os.symlink(self.path(BANK), self.path("Statement.pdf"))
        cases = {
            "a linked folder in the source": (row(1, "move", "Money/Bank statement 2024-03.pdf", "06 Work/Bank.pdf",
                                                  self.ids[BANK]), "symlink on path: Money"),
            "a linked source": (row(1, "move", "Statement.pdf", "06 Work/Statement.pdf", self.ids[BANK]),
                                "symlink on path: Statement.pdf"),
            "a linked folder in the destination": (row(1, "move", "06 Work/Contract.docx", "Money/Contract.docx",
                                                       self.ids["06 Work/Contract.docx"]), "symlink on path: Money"),
        }
        for name, (r, note) in cases.items():
            with self.subTest(name):
                self.refused([r], note)

    def test_a_row_without_a_destination(self):
        self.refused([row(1, "move", "IMG_0001.jpg", "", self.ids["IMG_0001.jpg"])], "no destination")

    def test_the_source_must_be_an_item(self):
        self.refused([row(1, "move", "02 Finance/Missing.pdf", "06 Work/Missing.pdf", self.ids[BANK])],
                     "source missing")
        folder = common.sha256_package(self.path("06 Work"))       # a plain folder hashes like a package
        self.refused([row(1, "move", "06 Work", "07 Work", folder)], "source missing")

    def test_never_overwrite(self):
        self.refused([row(1, "move", BANK, "06 Work/Contract.docx", self.ids[BANK])], "destination exists")
        self.assertEqual(common.sha256_file(self.path("06 Work/Contract.docx")), self.ids["06 Work/Contract.docx"])

    def test_the_source_hash_before_the_move(self):
        with open(self.path(BANK), "ab") as f:
            f.write(b"\n% edited after the audit\n")
        self.refused([row(1, "move", BANK, "06 Work/Bank.pdf", self.ids[BANK])], "source hash differs from evidence")

    def test_the_destination_hash_after_the_move(self):
        write_rows(self.plan, [row(1, "move", BANK, "06 Work/Bank.pdf", self.ids[BANK])])
        code, out, err = self.execute(script=DRIFTING_RENAME)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(self.status(1)[0], "failed")
        self.assertIn("destination hash differs after move", self.status(1)[1])
        self.assertEqual([x["phase"] for x in self.undo_lines()], ["intent"], "no done line for a failed move")

    def test_a_package_moves_whole_hashed_as_the_audit_hashes_it(self):
        dst = "03 Home/Lease/Lease renewal.pages"
        write_rows(self.plan, [row(1, "move", LEASE_PAGES, dst, self.ids[LEASE_PAGES])])
        code, out, err = self.execute()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(common.sha256_package(self.path(dst)), self.ids[LEASE_PAGES])
        self.assertTrue(os.path.isfile(self.path(dst + "/Index/Document.iwa")))
        self.assertFalse(os.path.exists(self.path(LEASE_PAGES)))

    def test_a_package_with_a_changed_member_stays(self):
        member = common.sha256_file(self.path(LEASE_PAGES + "/Index/Document.iwa"))
        self.refused([row(1, "move", LEASE_PAGES, "06 Work/Lease renewal.pages", member)],
                     "source hash differs from evidence")
        write(self.path(LEASE_PAGES + "/Data/extra.png"), b"a member added after the audit")
        self.refused([row(1, "move", LEASE_PAGES, "06 Work/Lease renewal.pages", self.ids[LEASE_PAGES])],
                     "source hash differs from evidence")

    def test_an_unknown_action(self):
        self.refused([row(1, "copy", BANK, "06 Work/Bank.pdf", self.ids[BANK])], "action copy not supported")

    def test_create(self):
        write_rows(self.plan, [row(1, "create", to="07 Travel/"), row(2, "create", to="06 Work/", domain="x")])
        code, out, err = self.execute()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(os.path.isdir(self.path("07 Travel")))
        self.assertEqual((self.status(1), self.status(2)), (("done", ""), ("done", "")))
        self.refused([row(1, "create", to="03 Home/Lease notes .txt")], "exists and is not a folder")


class RowOrderTest(PlanCase):
    def test_a_failed_row_stops_its_domain(self):
        write_rows(self.plan, [
            row(1, "move", BANK, "02 Finance/Bank.pdf", "0" * 64),
            row(2, "move", "02 Finance/Tax/Budget final.xlsx", "02 Finance/Budget final.xlsx",
                self.ids["02 Finance/Tax/Budget final.xlsx"]),
            row(3, "move", "06 Work/Contract.docx", "06 Work/Employment contract.docx",
                self.ids["06 Work/Contract.docx"]),
        ])
        code, out, err = self.execute()
        self.assertEqual(code, 1, out + err)
        self.assertEqual(self.status(1)[0], "failed")
        self.assertEqual(self.status(2), ("skipped", "earlier row in this domain failed"))
        self.assertEqual(self.status(3)[0], "done")
        self.assertTrue(os.path.isfile(self.path("02 Finance/Tax/Budget final.xlsx")))
        self.assertTrue(os.path.isfile(self.path("06 Work/Employment contract.docx")))

    def test_only_approved_rows_run(self):
        write_rows(self.plan, [
            row(1, "move", BANK, "06 Work/Bank.pdf", self.ids[BANK], approved="", status="proposed"),
            row(2, "move", "06 Work/Contract.docx", "06 Work/C.docx", self.ids["06 Work/Contract.docx"],
                approved="declined", status="skipped"),
            row(3, "move", ESSAY_WORKING, "04 Study/E.docx", self.ids[ESSAY_WORKING], approved="deferred",
                status="skipped"),
        ])
        before = tree_digest(self.root)
        code, out, err = self.execute()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(tree_digest(self.root), before)
        self.assertEqual([self.status(s)[0] for s in (1, 2, 3)], ["skipped"] * 3)

    def test_a_convert_row_is_left_to_the_owner(self):
        """A convert row is not executed by these tools: it stays pending, is named in the output, does not stop its
        domain and does not hold the deletes back."""
        numbers, final = "02 Finance/Tax/Budget.numbers", "02 Finance/Tax/Budget final.xlsx"
        write_rows(self.plan, [
            row(1, "convert", numbers, "02 Finance/Tax/Budget.xlsx", self.ids[numbers], kind="xlsx"),
            row(2, "move", final, "02 Finance/Budget final.xlsx", self.ids[final]),
            row(3, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant"),
        ])
        os.utime(self.manifest_path, (PAST - 60, PAST - 60))
        code, out, err = self.execute(now=PAST)
        self.assertEqual(code, 0, out + err)
        self.assertIn("convert %s -> not executed by these tools" % numbers, out)
        self.assertEqual((self.status(1), self.status(2)[0]), (("pending", ""), "done"))
        self.assertTrue(os.path.isfile(self.path("02 Finance/Budget final.xlsx")))
        self.audit()
        code, out, err = self.execute("--phase", "deletes")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((self.status(1)[0], self.status(3)[0]), ("pending", "done"))
        self.assertEqual(self.bin_names(), ["Bank statement 2024-03 (1).pdf"])

    def test_a_done_row_is_not_run_again(self):
        write_rows(self.plan, [row(1, "move", BANK, "06 Work/Bank.pdf", self.ids[BANK])])
        self.assertEqual(self.execute()[0], 0)
        code, out, err = self.execute()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.status(1), ("done", "undo.log seq 1"))
        self.assertEqual(len(self.undo_lines()), 2)

    def test_delete_rows_wait_for_the_deletes_phase(self):
        write_rows(self.plan, [row(1, "move", "IMG_0001.jpg", "03 Home/Beach.jpg", self.ids["IMG_0001.jpg"]),
                               row(2, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant")])
        code, out, err = self.execute()
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("Traceback", err)
        self.assertEqual((self.status(1)[0], self.status(2)[0]), ("done", "pending"))
        self.assertTrue(os.path.isfile(self.path(BANK_COPY)))
        self.assertEqual(self.bin_names(), [])


class FolderRenameTest(PlanCase):
    def test_a_folder_rename_carries_its_files(self):
        write_rows(self.plan, [row(1, "rename", "03 Home/Utilities /", "03 Home/Utilities/", domain="03 Home")])
        code, out, err = self.execute()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(os.path.isfile(self.path("03 Home/Utilities/Electricity bill.pdf")))
        self.assertFalse(os.path.exists(self.path("03 Home/Utilities ")))
        self.assertEqual(self.undo_lines()[1]["undo"], {"op": "rename-folder", "from": "03 Home/Utilities/",
                                                        "to": "03 Home/Utilities /"})

    def test_the_source_must_be_a_folder(self):
        self.refused([row(1, "rename", "03 Home/Lease notes .txt/", "03 Home/Lease notes.txt/")],
                     "source folder missing")

    def test_never_onto_an_existing_folder(self):
        os.makedirs(self.path("07 Empty"))
        self.refused([row(1, "rename", "06 Work/", "07 Empty/")], "destination exists")


# ---------------------------------------------------------------------------------------------- rmdir

class RmdirTest(PlanCase):
    def test_a_folder_holding_only_finder_files_goes_to_the_bin(self):
        write(self.path("07 Old/.DS_Store"), "finder")
        write(self.path("07 Old/2019/.DS_Store"), "finder")
        write_rows(self.plan, [row(1, "rmdir", "07 Old/")])
        code, out, err = self.execute()
        self.assertEqual(code, 0, out + err)
        self.assertFalse(os.path.exists(self.path("07 Old")))
        self.assertEqual(self.bin_names(), ["07 Old"])
        self.assertTrue(os.path.isfile(os.path.join(self.bin, "07 Old", "2019", ".DS_Store")))
        self.assertEqual(self.undo_lines()[1]["undo"], {"op": "rename-folder", "from": os.path.join(self.bin, "07 Old"),
                                                        "to": "07 Old/"})

    def test_anything_else_keeps_the_folder(self):
        write(self.path("08 Mixed/.DS_Store"), "finder")
        write(self.path("08 Mixed/Deep/Note.txt"), "a note")
        write(self.path("09 Hidden/.localized"), "")
        self.refused([row(1, "rmdir", "08 Mixed/")], "folder not empty")
        self.refused([row(1, "rmdir", "09 Hidden/")], "folder not empty")

    def test_only_a_folder(self):
        write(self.path("10 Drafts/Blank.pages/.DS_Store"), "finder")      # a package, not a folder to tidy
        self.refused([row(1, "rmdir", "03 Home/Lease notes .txt/")], "not a folder")
        self.refused([row(1, "rmdir", "10 Drafts/Blank.pages/")], "not a folder")
        self.refused([row(1, "rmdir", "07 Nowhere/")], "not a folder")

    def test_never_overwrite_in_the_bin(self):
        write(os.path.join(self.bin, "07 Old", "kept.txt"), "already in the Bin")
        write(self.path("07 Old/.DS_Store"), "finder")
        write_rows(self.plan, [row(1, "rmdir", "07 Old/")])
        self.assertEqual(self.execute()[0], 0)
        self.assertEqual(self.bin_names(), ["07 Old", "07 Old (1)"])
        self.assertEqual(read(os.path.join(self.bin, "07 Old", "kept.txt")), "already in the Bin")


# ---------------------------------------------------------------------------------------------- deletes

class DeleteTest(PlanCase):
    def test_a_full_round(self):
        """Propose, approve, move, prove by re-audit, then delete the redundant copies to the Bin."""
        before = os.path.join(self.tmp, "before.json")
        shutil.copy(self.manifest_path, before)
        self.run_plan("light", "--root", self.root, "--out", os.path.dirname(self.plan))
        rows = read_rows(self.plan)
        rows[0]["to"] = "03 Home/Beach.jpg"                  # the owner chose where the stray belongs
        write_rows(self.plan, rows)
        self.run_plan("approve", "--plan", self.plan, "--rows", "all", "--note", "agreed with Alex")
        os.utime(self.manifest_path, (PAST - 60, PAST - 60))  # the audit ran before the moves
        code, out, err = self.execute(now=PAST)
        self.assertEqual(code, 0, out + err)
        self.assertEqual([self.status(s)[0] for s in range(1, 8)], ["done"] * 3 + ["pending"] * 4)
        for rel in ("03 Home/Beach.jpg", "03 Home/Lease notes.txt", "03 Home/Utilities/Electricity bill.pdf"):
            self.assertTrue(os.path.isfile(self.path(rel)), rel)

        code, _o, err = self.execute("--phase", "deletes")
        self.assertEqual(code, 2)
        self.assertIn("re-audit the folder after the moves first", err)
        self.assertEqual(self.bin_names(), [])

        self.audit()
        code, out, err = self.run_plan("prove", "--plan", self.plan, "--before", before, "--after",
                                       self.manifest_path)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads(out)["rows_checked"], 3)

        code, out, err = self.execute("--phase", "deletes")
        self.assertEqual(code, 0, out + err)
        self.assertEqual([self.status(s)[0] for s in range(1, 8)], ["done"] * 7)
        self.assertEqual(self.bin_names(), sorted(["Bank statement 2024-03 (1).pdf", "Cours de français.pdf",
                                                   "Slides.pptx", "中文课程.pdf"]))
        for rel in (BANK, "04 Study/Cours de français.pdf", "04 Study/Slides.pptx", "04 Study/中文课程.pdf",
                    PASSPORT_PACK, ESSAY_WORKING):
            self.assertTrue(os.path.isfile(self.path(rel)), rel)
        self.audit()
        summary = json.loads(read(os.path.join(self.root, "_Audit", "summary.json")))
        self.assertEqual(summary["copy_kinds"], {"canonical": 2, "pack": 1, "working_copy": 2})

    def test_deletes_wait_for_every_other_approved_row(self):
        for status in ("pending", "failed", "skipped"):
            with self.subTest(status):
                write_rows(self.plan, [
                    row(1, "move", "IMG_0001.jpg", "03 Home/Beach.jpg", self.ids["IMG_0001.jpg"], status=status),
                    row(2, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant"),
                ])
                code, _o, err = self.execute("--phase", "deletes")
                self.assertEqual(code, 2)
                self.assertIn("approved non-delete rows are not all done", err)
                self.assertEqual(self.bin_names(), [])
        write_rows(self.plan, [row(1, "move", "IMG_0001.jpg", "", self.ids["IMG_0001.jpg"], approved="declined",
                                   status="skipped"),
                               row(2, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant")])
        self.assertEqual(self.execute("--phase", "deletes")[0], 0, "a declined row does not hold deletes back")

    def test_deletes_wait_for_a_manifest_newer_than_the_moves(self):
        write_rows(self.plan, [row(1, "move", "IMG_0001.jpg", "03 Home/Beach.jpg", self.ids["IMG_0001.jpg"]),
                               row(2, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant")])
        self.assertEqual(self.execute(now=PAST)[0], 0)
        for stamp in (PAST - 60, PAST):
            with self.subTest(manifest_at=stamp - PAST):
                os.utime(self.manifest_path, (stamp, stamp))
                code, _o, err = self.execute("--phase", "deletes")
                self.assertEqual(code, 2)
                self.assertIn("re-audit", err)
                self.assertTrue(os.path.isfile(self.path(BANK_COPY)))
        os.utime(self.manifest_path, (PAST + 60, PAST + 60))
        self.assertEqual(self.execute("--phase", "deletes")[0], 0)
        self.assertEqual(self.bin_names(), ["Bank statement 2024-03 (1).pdf"])

    def test_only_paths_the_manifest_marks_redundant(self):
        cases = {"a working copy": ESSAY_WORKING, "a canonical copy": "04 Study/Slides.pptx",
                 "a unique file": "06 Work/Contract.docx"}         # a pack copy: PackDuplicateTest
        for name, rel in cases.items():
            with self.subTest(name):
                self.refused([row(1, "delete", rel, evidence=self.ids[rel], kind="redundant")],
                             "manifest does not mark this path redundant", phase=("--phase", "deletes"))

    def test_the_row_must_say_redundant(self):
        for kind in ("", "working_copy", "pack"):
            with self.subTest(kind=kind):
                self.refused([row(1, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind=kind)],
                             "only redundant copies are deleted", phase=("--phase", "deletes"))

    def test_the_evidence_must_be_in_the_manifest(self):
        self.refused([row(1, "delete", BANK_COPY, evidence="f" * 64, kind="redundant")],
                     "evidence entry not in manifest", phase=("--phase", "deletes"))

    def test_both_copies_are_hashed_again(self):
        for name, rel in (("the canonical copy", BANK), ("the redundant copy", BANK_COPY)):
            with self.subTest(name):
                original = read(self.path(rel), "rb")
                write(self.path(rel), original + b"\n% edited after the audit\n")
                self.refused([row(1, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant")],
                             "hash differs on disk (copy or canonical)", phase=("--phase", "deletes"))
                write(self.path(rel), original)

    def test_both_copies_must_be_on_disk(self):
        for rel in (BANK, BANK_COPY):
            with self.subTest(rel):
                aside = os.path.join(self.tmp, "aside.pdf")
                os.rename(self.path(rel), aside)
                self.refused([row(1, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant")],
                             "copy or canonical missing on disk", phase=("--phase", "deletes"))
                os.rename(aside, self.path(rel))

    def test_a_group_without_a_canonical_copy(self):
        doctored = json.loads(read(self.manifest_path))
        for c in doctored["entries"][self.ids[BANK]]["copies"]:
            if c["kind"] == "canonical":
                c["kind"] = "working_copy"
        path = os.path.join(self.tmp, "doctored.json")
        write(path, json.dumps(doctored))
        self.refused([row(1, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant")],
                     "no separate canonical copy", phase=("--phase", "deletes", "--manifest", path))

    def test_never_overwrite_in_the_bin(self):
        write(os.path.join(self.bin, "Bank statement 2024-03 (1).pdf"), "already in the Bin")
        write_rows(self.plan, [row(1, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant")])
        self.assertEqual(self.execute("--phase", "deletes")[0], 0)
        self.assertEqual(self.bin_names(), ["Bank statement 2024-03 (1) (1).pdf", "Bank statement 2024-03 (1).pdf"])
        self.assertEqual(read(os.path.join(self.bin, "Bank statement 2024-03 (1).pdf")), "already in the Bin")
        self.assertEqual(common.sha256_file(os.path.join(self.bin, "Bank statement 2024-03 (1) (1).pdf")),
                         self.ids[BANK_COPY])


class PackageDeleteTest(PlanCase):
    def prepare(self):
        shutil.copytree(self.path(LEASE_PAGES), self.path("03 Home/Lease renewal (1).pages"))

    def test_a_redundant_package_goes_to_the_bin_whole(self):
        copy = "03 Home/Lease renewal (1).pages"
        self.assertEqual(plan.live_paths(self.manifest["entries"])[copy][1], "redundant")
        write_rows(self.plan, [row(1, "delete", copy, evidence=self.ids[copy], kind="redundant")])
        code, out, err = self.execute("--phase", "deletes")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.bin_names(), ["Lease renewal (1).pages"])
        self.assertEqual(common.sha256_package(os.path.join(self.bin, "Lease renewal (1).pages")), self.ids[copy])
        self.assertTrue(os.path.isdir(self.path(LEASE_PAGES)))


def list_pack_in_rulebook(case, pack):
    """List one more pack in the fixture copy's twin, which is all the tools read (`settings.py check`, which would
    also want it named in the rulebook's prose, is not run here)."""
    twin = json.loads(read(case.path(".familyai/rulebook.json")))
    twin["packs"].append(pack)
    write(case.path(".familyai/rulebook.json"), json.dumps(twin, ensure_ascii=False, indent=1))


class PackDuplicateTest(PlanCase):
    """Two identical files in one folder inside a pack: the audit calls both copies' second file a `pack`, and the
    plan tools refuse a delete inside a pack even when a manifest (an older audit's, or one edited by hand) says
    `redundant`, whether the pack is listed or named by keyword."""

    LOAN_COPY = "02 Finance/Loan 2022/Payslip (1).pdf"
    FORM_COPY = "01 Identity/Passport renewal 2021/Application form (1).docx"

    def prepare(self):
        write(self.path("02 Finance/Loan 2022/Payslip.pdf"), "a payslip sent with the loan papers")
        shutil.copy(self.path("02 Finance/Loan 2022/Payslip.pdf"), self.path(self.LOAN_COPY))
        shutil.copy(self.path("01 Identity/Passport renewal 2021/Application form.docx"), self.path(self.FORM_COPY))
        list_pack_in_rulebook(self, "02 Finance/Loan 2022")

    def doctored(self):
        """The manifest with the copies inside the packs marked `redundant`."""
        m = json.loads(read(self.manifest_path))
        for e in m["entries"].values():
            for c in e.get("copies", []):
                if c["path"] in (self.LOAN_COPY, self.FORM_COPY, PASSPORT_PACK):
                    c["kind"] = "redundant"
        path = os.path.join(self.tmp, "doctored.json")
        write(path, json.dumps(m))
        return path

    def delete_rows(self):
        return [row(1, "delete", self.LOAN_COPY, evidence=self.ids[self.LOAN_COPY], kind="redundant", domain="loan"),
                row(2, "delete", self.FORM_COPY, evidence=self.ids[self.FORM_COPY], kind="redundant", domain="form"),
                row(3, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant", domain="bank"),
                row(4, "delete", PASSPORT_PACK, evidence=self.ids[PASSPORT_PACK], kind="redundant", domain="pp")]

    def light_deletes(self, *manifest):
        self.run_plan("light", "--root", self.root, "--out", os.path.dirname(self.plan), *manifest)
        return [r["from"] for r in self.rows().values() if r["action"] == "delete"]

    def test_the_audit_calls_them_packs_and_light_proposes_no_delete(self):
        kinds = {p: k for p, (_h, k, _o) in plan.live_paths(self.manifest["entries"]).items()}
        self.assertEqual((kinds[self.LOAN_COPY], kinds[self.FORM_COPY]), ("pack", "pack"))
        deletes = self.light_deletes()
        self.assertEqual([p for p in (self.LOAN_COPY, self.FORM_COPY, BANK_COPY) if p in deletes], [BANK_COPY])

    def test_light_proposes_no_delete_inside_a_pack_whatever_the_manifest_says(self):
        deletes = self.light_deletes("--manifest", self.doctored())
        self.assertEqual([p for p in (self.LOAN_COPY, self.FORM_COPY, PASSPORT_PACK, BANK_COPY) if p in deletes],
                         [BANK_COPY])

    def test_check_refuses_a_delete_inside_a_pack(self):
        write_rows(self.plan, self.delete_rows())
        code, out, err = self.run_plan("check", "--root", self.root, "--plan", self.plan, "--manifest", self.doctored())
        self.assertEqual(code, 1, out + err)
        failed = {line.split()[1]: line for line in out.splitlines() if line.startswith("FAIL")}
        self.assertEqual(sorted(failed), ["1", "2", "4"])
        for seq in ("1", "2", "4"):
            self.assertIn(plan.PACK_REFUSAL, failed[seq])

    def test_execute_refuses_a_delete_inside_a_pack(self):
        doctored = self.doctored()
        for rel in (self.LOAN_COPY, self.FORM_COPY, PASSPORT_PACK):
            with self.subTest(rel):
                self.refused([row(1, "delete", rel, evidence=self.ids[rel], kind="redundant")], plan.PACK_REFUSAL,
                             phase=("--phase", "deletes", "--manifest", doctored))

    def test_a_duplicate_outside_any_pack_is_still_deleted(self):
        write_rows(self.plan, self.delete_rows())
        code, out, err = self.execute("--phase", "deletes", "--manifest", self.doctored())
        self.assertEqual(code, 1, out + err)
        self.assertEqual([self.status(s)[0] for s in (1, 2, 3, 4)], ["failed", "failed", "done", "failed"])
        self.assertEqual(self.bin_names(), ["Bank statement 2024-03 (1).pdf"])
        for rel in (self.LOAN_COPY, self.FORM_COPY, PASSPORT_PACK):
            self.assertTrue(os.path.isfile(self.path(rel)), rel)


class PackListingTest(PlanCase):
    """A listed pack that names no existing folder would match nothing and leave its copies deletable, so every tool
    that relies on packs refuses to run until rulebook.json is put right."""

    def packs(self, *packs):
        twin = json.loads(read(self.path(".familyai/rulebook.json")))
        twin["packs"] = list(packs)
        write(self.path(".familyai/rulebook.json"), json.dumps(twin, ensure_ascii=False, indent=1))

    def assert_refused(self, code, err, pack):
        self.assertEqual(code, 2, err)
        self.assertIn("packs entry %r" % pack, err)
        self.assertIn("update rulebook.json packs (and name it in the rulebook, which `settings.py check` verifies)",
                      err)
        self.assertNotIn("Traceback", err)

    def test_every_tool_refuses_a_listed_pack_that_is_not_a_folder(self):
        write_rows(self.plan, [row(1, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant")])
        cases = {"absent": "02 Finance/Loan 2022", "a wrong case": "01 identity/Passport Renewal 2021", "a file": BANK}
        for name, pack in cases.items():
            self.packs("01 Identity/Passport renewal 2021", pack)
            commands = {
                "audit": lambda: self.run_tool("audit.py", "--root", self.root, "--work", os.path.join(self.tmp, "w")),
                "light": lambda: self.run_plan("light", "--root", self.root, "--out", os.path.join(self.tmp, "lp")),
                "check": lambda: self.run_plan("check", "--root", self.root, "--plan", self.plan),
                "execute": lambda: self.execute("--phase", "deletes"),
            }
            for cmd, go in commands.items():
                with self.subTest(name, cmd=cmd):
                    code, _out, err = go()
                    self.assert_refused(code, err, pack)
        self.assertEqual(self.bin_names(), [])
        self.assertTrue(os.path.isfile(self.path(BANK_COPY)))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "lp")))

    def test_a_pack_renamed_by_an_approved_row_stops_the_deletes(self):
        write_rows(self.plan, [row(1, "rename", "01 Identity/Passport renewal 2021/", "01 Identity/Passport 2021/"),
                               row(2, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant")])
        os.utime(self.manifest_path, (PAST - 60, PAST - 60))
        self.assertEqual(self.execute(now=PAST)[0], 0)
        code, _out, err = self.execute("--phase", "deletes")
        self.assert_refused(code, err, "01 Identity/Passport renewal 2021")
        code, _out, err = self.run_tool("audit.py", "--root", self.root, "--work", os.path.join(self.tmp, "work"))
        self.assert_refused(code, err, "01 Identity/Passport renewal 2021")
        self.assertEqual(self.bin_names(), [])


# ---------------------------------------------------------------------------------------------- dry run, undo

class DryRunTest(PlanCase):
    def test_without_apply_nothing_changes(self):
        write(self.path("07 Old/.DS_Store"), "finder")
        write_rows(self.plan, [
            row(1, "create", to="07 Travel/"),
            row(2, "move", "IMG_0001.jpg", "03 Home/Beach.jpg", self.ids["IMG_0001.jpg"]),
            row(3, "rename", LEASE_NOTES, "03 Home/Lease notes.txt", self.ids[LEASE_NOTES]),
            row(4, "rename", "03 Home/Utilities /", "03 Home/Utilities/"),
            row(5, "rmdir", "07 Old/"),
            row(6, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant"),
            row(7, "move", "06 Work/Contract.docx", "06 Work/C.docx", self.ids["06 Work/Contract.docx"], approved="",
                status="proposed"),
        ])
        before, plan_bytes = tree_digest(self.root), read(self.plan, "rb")
        code, out, err = self.execute(apply=False)
        self.assertEqual(code, 0, out + err)
        for word in ("create", "move", "rename", "rename folder", "rmdir"):
            self.assertIn(word, out)
        self.assertEqual((tree_digest(self.root), read(self.plan, "rb")), (before, plan_bytes))
        self.assertEqual((self.undo_lines(), self.bin_names()), ([], []))
        self.assertFalse(os.path.exists(self.path("07 Travel")), "a dry run created a folder")

    def test_a_dry_run_of_the_deletes(self):
        write_rows(self.plan, [row(1, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant")])
        before, plan_bytes = tree_digest(self.root), read(self.plan, "rb")
        code, out, err = self.execute("--phase", "deletes", apply=False)
        self.assertEqual(code, 0, out + err)
        self.assertIn("delete " + BANK_COPY, out)
        self.assertEqual((tree_digest(self.root), read(self.plan, "rb")), (before, plan_bytes))
        self.assertEqual((self.undo_lines(), self.bin_names()), ([], []))


class UndoLogTest(PlanCase):
    def test_replaying_the_undo_log_restores_the_folder(self):
        write(self.path("07 Old/.DS_Store"), "finder")
        original = tree_digest(self.root, skip=("_Audit",))
        write_rows(self.plan, [
            row(1, "move", "IMG_0001.jpg", "03 Home/Beach.jpg", self.ids["IMG_0001.jpg"]),
            row(2, "rename", LEASE_NOTES, "03 Home/Lease notes.txt", self.ids[LEASE_NOTES]),
            row(3, "rename", "03 Home/Utilities /", "03 Home/Utilities/"),
            row(4, "rmdir", "07 Old/"),
            row(5, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant"),
        ])
        os.utime(self.manifest_path, (PAST - 60, PAST - 60))
        self.assertEqual(self.execute(now=PAST)[0], 0)
        self.audit()
        self.assertEqual(self.execute("--phase", "deletes")[0], 0)
        lines = self.undo_lines()
        self.assertEqual([(x["seq"], x["phase"]) for x in lines],
                         [(s, p) for s in "12345" for p in ("intent", "done")])
        self.assertNotEqual(tree_digest(self.root, skip=("_Audit",)), original)
        for x in reversed([x for x in lines if x["phase"] == "done"]):
            src = os.path.join(self.root, x["undo"]["from"].rstrip("/"))
            dst = os.path.join(self.root, x["undo"]["to"].rstrip("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.rename(src, dst)
        self.assertEqual(tree_digest(self.root, skip=("_Audit",)), original)
        self.assertEqual(self.bin_names(), [])


# ---------------------------------------------------------------------------------------------- prove, check

class ProveTest(PlanCase):
    def moved(self):
        self.before = os.path.join(self.tmp, "before.json")
        shutil.copy(self.manifest_path, self.before)
        write_rows(self.plan, [
            row(1, "move", "IMG_0001.jpg", "03 Home/Beach.jpg", self.ids["IMG_0001.jpg"]),
            row(2, "rename", "03 Home/Utilities /", "03 Home/Utilities/"),
            row(3, "move", ESSAY_WORKING, "04 Study/Essays/Essay.docx", self.ids[ESSAY_WORKING]),
        ])
        self.assertEqual(self.execute()[0], 0)

    def prove(self, *extra):
        self.audit()
        code, out, err = self.run_plan("prove", "--plan", self.plan, "--before", self.before, "--after",
                                       self.manifest_path, *extra)
        self.assertIn(code, (0, 1), err)
        result = json.loads(out)
        self.assertEqual(code, 0 if result["ok"] else 1)
        return result

    def test_the_diff_equals_the_rows(self):
        self.moved()
        result = self.prove()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["rows_checked"], 3)

    def test_an_unplanned_change_is_caught(self):
        self.moved()
        contract = self.ids["06 Work/Contract.docx"]
        os.remove(self.path("06 Work/Contract.docx"))
        write(self.path("06 Work/New.txt"), "added by hand")
        result = self.prove()
        self.assertFalse(result["ok"])
        self.assertEqual(result["gone_unexpected"], [["06 Work/Contract.docx", contract]])
        self.assertEqual([p for p, _h in result["new_unexpected"]], ["06 Work/New.txt"])
        self.assertEqual((result["gone_missing"], result["new_missing"]), ([], []))

    def test_a_row_marked_done_that_did_not_happen(self):
        self.moved()
        rows = read_rows(self.plan)
        rows.append(row(4, "move", "06 Work/Contract.docx", "06 Work/C.docx", self.ids["06 Work/Contract.docx"],
                        status="done"))
        write_rows(self.plan, rows)
        result = self.prove()
        self.assertFalse(result["ok"])
        self.assertEqual(result["gone_missing"], [["06 Work/Contract.docx", self.ids["06 Work/Contract.docx"]]])
        self.assertEqual(result["new_missing"], [["06 Work/C.docx", self.ids["06 Work/Contract.docx"]]])

    def test_departures_the_owner_expects(self):
        self.moved()
        os.remove(self.path("06 Work/Contract.docx"))           # collected by another project
        self.assertFalse(self.prove()["ok"])
        self.assertTrue(self.prove("--allow-departed-under", "06 Work/")["ok"])

    def only(self, result, component):
        """The proof failed on `component` alone."""
        self.assertFalse(result["ok"], result)
        parts = ("gone_unexpected", "new_unexpected", "gone_missing", "new_missing")
        self.assertEqual([k for k in parts if result[k]], [component], result)

    def done_row(self, frm, to):
        rows = read_rows(self.plan)
        rows.append(row(4, "move", frm, to, self.ids[frm], status="done"))
        write_rows(self.plan, rows)

    def test_a_file_added_by_hand_alone(self):
        self.moved()
        write(self.path("06 Work/New.txt"), "added by hand")
        self.only(self.prove(), "new_unexpected")

    def test_a_source_copied_not_moved(self):
        self.moved()
        shutil.copy(self.path("06 Work/Contract.docx"), self.path("06 Work/C.docx"))
        self.done_row("06 Work/Contract.docx", "06 Work/C.docx")
        self.only(self.prove(), "gone_missing")

    def test_a_moved_file_that_never_arrived(self):
        self.moved()
        os.remove(self.path("06 Work/Contract.docx"))
        self.done_row("06 Work/Contract.docx", "06 Work/C.docx")
        self.only(self.prove(), "new_missing")

    def test_a_proof_across_the_moves_and_the_deletes(self):
        """A whole light round, moves then deletes, proved from the first manifest to the last."""
        shutil.copy(self.manifest_path, os.path.join(self.tmp, "before.json"))
        self.before = os.path.join(self.tmp, "before.json")
        self.run_plan("light", "--root", self.root, "--out", os.path.dirname(self.plan))
        rows = read_rows(self.plan)
        rows[0]["to"] = "03 Home/Beach.jpg"
        write_rows(self.plan, rows)
        self.run_plan("approve", "--plan", self.plan, "--rows", "all")
        os.utime(self.manifest_path, (PAST - 60, PAST - 60))
        self.assertEqual(self.execute(now=PAST)[0], 0)
        self.audit()
        self.assertEqual(self.execute("--phase", "deletes")[0], 0)
        result = self.prove()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["rows_checked"], 7)


class CheckTest(PlanCase):
    def check(self):
        code, out, err = self.run_plan("check", "--root", self.root, "--plan", self.plan)
        self.assertIn(code, (0, 1), err)
        failed = {line.split()[1]: line for line in out.splitlines() if line.startswith("FAIL")}
        self.assertEqual(code, 1 if failed else 0)
        return failed

    def test_the_light_plan_with_a_destination_chosen(self):
        self.run_plan("light", "--root", self.root, "--out", os.path.dirname(self.plan))
        rows = read_rows(self.plan)
        rows[0]["to"] = "03 Home/Beach.jpg"
        write_rows(self.plan, rows)
        self.assertEqual(self.check(), {})

    def stray(self):
        """The fixture's one root stray, proposed with no destination: the owner has yet to choose one."""
        self.run_plan("light", "--root", self.root, "--out", os.path.dirname(self.plan))
        rows = read_rows(self.plan)
        self.assertEqual((rows[0]["action"], rows[0]["from"], rows[0]["to"]), ("move", "IMG_0001.jpg", ""))
        return rows

    def test_a_stray_row_with_no_destination_is_refused_with_the_row_named(self):
        self.stray()
        failed = self.check()
        self.assertEqual(sorted(failed), ["1"])
        self.assertIn("FAIL 1 move IMG_0001.jpg no destination: the owner must choose one before approving",
                      failed["1"])
        self.run_plan("approve", "--plan", self.plan, "--rows", "1")
        self.assertIn("no destination", self.check()["1"], "approved, the executor refuses it too")

    def test_check_and_execute_refuse_the_same_row(self):
        self.stray()
        self.run_plan("approve", "--plan", self.plan, "--rows", "1")
        self.assertIn("no destination", self.check()["1"])
        code, out, _err = self.execute(apply=False)
        self.assertEqual(code, 1)
        self.assertIn("FAILED row 1 no destination", out)

    def test_a_declined_or_deferred_row_with_no_destination_is_never_run_so_check_passes_it(self):
        for decision in ("--decline", "--defer"):
            with self.subTest(decision):
                self.stray()
                self.run_plan("approve", "--plan", self.plan, "--rows", "1", decision)
                self.assertEqual(self.check(), {})

    def test_a_folder_rename_with_no_destination_is_refused_too(self):
        write_rows(self.plan, [row(1, "rename", "03 Home/Utilities /", "")])
        self.assertIn("no destination", self.check()["1"])
        write_rows(self.plan, [row(1, "rename", "03 Home/Utilities /", "03 Home/Utilities/")])
        self.assertEqual(self.check(), {})

    def test_every_bad_row_is_named(self):
        outside = os.path.join(self.tmp, "a", "outside.txt")
        write(outside, "beside the folder")
        with open(self.path(ESSAY_WORKING), "ab") as f:
            f.write(b"edited")
        os.remove(self.path("04 Study/Slides.pptx"))
        write_rows(self.plan, [
            row(1, "delete", ESSAY_WORKING, evidence=self.ids[ESSAY_WORKING], kind="redundant"),
            row(2, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="working_copy"),
            row(3, "delete", "05 Archive/Slides.pptx", evidence=self.ids["05 Archive/Slides.pptx"],
                kind="redundant"),
            row(4, "delete", BANK_COPY, evidence="f" * 64, kind="redundant"),
            row(5, "move", BANK, "../Bank.pdf", self.ids[BANK]),
            row(6, "move", "../outside.txt", "06 Work/outside.txt", common.content_id(outside)),
            row(7, "move", ESSAY_WORKING, "04 Study/E.docx", self.ids[ESSAY_WORKING]),
            row(8, "rmdir", "../"),
            row(9, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant"),
            row(10, "move", "06 Work/Contract.docx", "06 Work/C.docx", self.ids["06 Work/Contract.docx"]),
            row(11, "move", "02 Finance/Missing.pdf", "06 Work/Missing.pdf", self.ids[BANK]),
            row(12, "delete", PASSPORT_PACK, evidence=self.ids[PASSPORT_PACK], kind="redundant"),
        ])
        failed = self.check()
        self.assertEqual(sorted(failed, key=int), [str(n) for n in range(1, 9)] + ["11", "12"])
        for seq, reason in (("1", "not redundant"), ("2", "not redundant"), ("3", "missing on disk"),
                            ("5", "outside the folder"), ("6", "outside the folder"),
                            ("7", "source missing or hash differs"), ("8", "outside the folder"),
                            ("11", "source missing or hash differs"), ("12", plan.PACK_REFUSAL)):
            self.assertIn(reason, failed[seq])

    def test_a_changed_copy_or_canonical(self):
        for rel in (BANK, BANK_COPY):
            with self.subTest(rel):
                original = read(self.path(rel), "rb")
                write(self.path(rel), original + b"edited")
                write_rows(self.plan, [row(1, "delete", BANK_COPY, evidence=self.ids[BANK_COPY], kind="redundant")])
                self.assertIn("hash differs", self.check()["1"])
                write(self.path(rel), original)


# ---------------------------------------------------------------------------------------------- the owner's exclusions

NEVER_HASH_EXCLUDED = """
import sys
sys.path.insert(0, sys.argv[1])
import common
import plan
real = common.sha256_file


def guarded(path):
    if "IMG_0001" in path or "Lease notes" in path:
        raise AssertionError("hashed " + path)
    return real(path)


common.sha256_file = guarded
sys.argv = ["plan.py"] + sys.argv[2:]
common.run_main(plan.main)
"""


def never_hash(*names):
    """A runner script for plan.py that raises when any path containing one of `names` is hashed."""
    return NEVER_HASH_NAMES % (names,)


NEVER_HASH_NAMES = """
import sys
sys.path.insert(0, sys.argv[1])
import common
import plan
NAMES = %r
real_file, real_id = common.sha256_file, common.content_id


def guarded(real):
    def hashed(path, *args):
        if any(n in path for n in NAMES):
            raise AssertionError("hashed " + path)
        return real(path, *args)
    return hashed


common.sha256_file = guarded(real_file)
common.content_id = guarded(real_id)
sys.argv = ["plan.py"] + sys.argv[2:]
common.run_main(plan.main)
"""


class ExcludedPlanTest(PlanCase):
    """A path the rulebook excludes is proposed nothing, and a row that names one is refused before any hashing."""

    EXCLUDED = ("IMG_0001.jpg", "03 Home/Lease notes .txt", "05 Archive/Slides.pptx")

    def setUp(self):
        super().setUp()
        # the exclusion is made AFTER the audit, as an owner makes it: the manifest still holds every excluded item (and
        # `05 Archive/Slides.pptx` as a redundant copy) as an ordinary entry, so only the plan tools' own filters keep
        # them out of a proposal
        twin = os.path.join(self.root, ".familyai", "rulebook.json")
        write(twin, json.dumps(dict(json.loads(read(twin)), exclude=list(self.EXCLUDED)), ensure_ascii=False))

    def test_light_proposes_nothing_for_an_excluded_stray_name_defect_or_redundant_copy(self):
        code, _o, err = self.run_plan("light", "--root", self.root, "--out", os.path.dirname(self.plan))
        self.assertEqual(code, 0, err)
        text = read(self.plan)
        for named in ("IMG_0001", "Lease notes", "Slides"):
            self.assertNotIn(named, text, "a row names an excluded item")
        kept = [(r["action"], r["from"]) for r in self.rows().values()]
        self.assertIn(("rename", "03 Home/Utilities /"), kept, "the rows for what is not excluded are unchanged")
        self.assertIn(("delete", "05 Archive/Cours de fran\u00e7ais.pdf"), kept)

    def test_check_and_execute_refuse_a_row_that_names_an_excluded_path_before_hashing(self):
        write_rows(self.plan, [row(1, "move", "IMG_0001.jpg", "03 Home/Beach.jpg", "f" * 64),
                               row(2, "rename", "03 Home/Lease notes .txt", "03 Home/Lease notes.txt", "e" * 64),
                               row(3, "move", "03 Home/Lease renewal.pdf", "05 Archive/Slides.pptx",
                                   self.ids["03 Home/Lease renewal.pdf"]),
                               row(4, "delete", "05 Archive/Slides.pptx", "", "d" * 64, kind="redundant")])
        code, out, err = self.run_plan("check", "--root", self.root, "--plan", self.plan, script=NEVER_HASH_EXCLUDED)
        self.assertEqual(code, 1, out + err)
        failed = {line.split()[1]: line for line in out.splitlines() if line.startswith("FAIL")}
        self.assertEqual(sorted(failed), ["1", "2", "3", "4"])
        for seq, which in (("1", "from"), ("2", "from"), ("3", "to"), ("4", "from")):
            self.assertIn("the %s path is excluded from reading by the rulebook: no tool opens, hashes or moves it"
                          % which, failed[seq])
            self.assertNotIn("source missing or hash differs", failed[seq])
        before = tree_digest(self.root)
        code, out, err = self.execute(script=NEVER_HASH_EXCLUDED)
        self.assertEqual(code, 1, out + err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(self.status(1)[0], "failed")
        self.assertIn("excluded from reading", self.status(1)[1])
        self.assertEqual(tree_digest(self.root), before, "a refused row changed the folder")

    def test_a_row_for_what_is_not_excluded_still_runs_and_is_checked(self):
        write_rows(self.plan, [row(1, "move", "03 Home/Lease renewal.pdf", "03 Home/Renewal.pdf",
                                   self.ids["03 Home/Lease renewal.pdf"])])
        code, out, err = self.run_plan("check", "--root", self.root, "--plan", self.plan)
        self.assertEqual((code, "rows ok 1 failed 0" in out), (0, True), out + err)

    def test_migrate_and_return_never_list_an_excluded_path(self):
        paths = os.path.join(self.tmp, "paths.txt")
        write(paths, "IMG_0001.jpg\n03 Home/\n")
        out = os.path.join(self.tmp, "round")
        code, _o, err = self.run_plan("migrate", "--root", self.root, "--project", "Household", "--paths-file", paths,
                                      "--out", out)
        self.assertEqual(code, 0, err)
        rows = read_rows(os.path.join(out, "move-plan.csv"))
        self.assertNotIn("Lease notes", read(os.path.join(out, "move-plan.csv")))
        self.assertTrue(rows and all(not r["from"].startswith("IMG_0001") for r in rows))
        self.assertIn("MISSING\tIMG_0001.jpg", read(os.path.join(out, "review.tsv")))


class ExcludedAfterTheAuditPlanTest(PlanCase):
    """A manifest audited BEFORE the owner excluded a path still holds that path's document, and its copies, as ordinary
    entries: the plan tools must leave all of it alone without waiting for a fresh audit."""

    COURS = "05 Archive/Cours de fran\u00e7ais.pdf"
    COURS_CANON = "04 Study/Cours de fran\u00e7ais.pdf"

    def exclude(self, *paths):
        twin = os.path.join(self.root, ".familyai", "rulebook.json")
        write(twin, json.dumps(dict(json.loads(read(twin)), exclude=list(paths)), ensure_ascii=False))

    def light(self):
        code, _o, err = self.run_plan("light", "--root", self.root, "--out", os.path.dirname(self.plan))
        self.assertEqual(code, 0, err)
        return [(r["action"], r["from"]) for r in self.rows().values()]

    def test_light_proposes_no_delete_for_a_redundant_copy_excluded_after_the_audit(self):
        self.assertIn(("delete", self.COURS), self.light())
        self.exclude(self.COURS)
        proposed = self.light()
        self.assertNotIn("Cours de fran", read(self.plan), "the excluded copy is named in a row")
        self.assertIn(("delete", "05 Archive/Slides.pptx"), proposed, "the other redundant copies are still proposed")
        self.exclude("05 Archive")
        proposed = self.light()
        self.assertEqual([f for a, f in proposed if a == "delete"], [BANK_COPY], "nothing in the excluded folder")

    def test_light_proposes_nothing_for_the_copies_of_a_document_whose_canonical_copy_is_excluded(self):
        self.exclude(self.COURS_CANON)
        proposed = self.light()
        self.assertNotIn("Cours de fran", read(self.plan), "the copy of an excluded document is named in a row")
        self.assertIn(("delete", "05 Archive/Slides.pptx"), proposed)

    def test_light_proposes_no_rename_of_a_folder_that_holds_an_excluded_path(self):
        """Renaming `03 Home/Utilities /` would move the excluded file inside it: the owner's exclusion also means the plan
        leaves it alone."""
        man = json.loads(read(self.manifest_path))  # a second, included file in the folder, so the rename is proposed
        man["entries"]["d" * 64] = {"id": "d" * 64, "current_path": "03 Home/Utilities /Gas bill.pdf", "class": "document",
                                    "hashed": True, "flags": [], "copies": [], "size": 1, "mtime": "2024-06-01T00:00:00Z"}
        write(self.manifest_path, json.dumps(man))
        self.assertIn(("rename", "03 Home/Utilities /"), self.light())
        self.exclude("03 Home/Utilities /Electricity bill.pdf")
        proposed = self.light()
        self.assertNotIn("Utilities", read(self.plan), "a row names the folder or the excluded file")
        self.assertIn(("rename", "03 Home/Lease notes .txt"), proposed, "the rows for what is not held are unchanged")

    def test_light_proposes_no_rename_of_a_folder_that_holds_a_document_staged_for_another_project(self):
        man = json.loads(read(self.manifest_path))
        slides = next(e for e in man["entries"].values() if e["current_path"] == "04 Study/Slides.pptx")
        slides["current_path"] = "_Migrations/Other Project/Slides.pptx"
        slides["copies"] = [{"path": "03 Home/Utilities /Slides copy.pptx", "kind": "redundant"},
                            {"path": "_Migrations/Other Project/Slides.pptx", "kind": "canonical"}]
        write(self.manifest_path, json.dumps(man))
        self.assertNotIn("Utilities", read(self.plan) if self.light() else "")

    def delete_row(self, path, evidence_of):
        return row(1, "delete", path, "", self.ids[evidence_of], kind="redundant")

    def test_check_and_execute_never_hash_the_canonical_copy_of_an_excluded_document(self):
        """The row removes an included copy of a document whose canonical copy the owner has since excluded: proving the
        copy equals the canonical copy would open the excluded file, so the row is refused before anything is hashed."""
        self.exclude(self.COURS_CANON)
        write_rows(self.plan, [self.delete_row(self.COURS, self.COURS_CANON)])
        guard = never_hash("Cours de fran")
        code, out, err = self.run_plan("check", "--root", self.root, "--plan", self.plan, script=guard)
        self.assertEqual(code, 1, out + err)
        self.assertIn("is excluded: no tool opens, hashes or moves it", out)
        self.assertNotIn("04 Study", out + err, "the refusal names the excluded canonical copy")
        before = tree_digest(self.root)
        code, out, err = self.execute("--phase", "deletes", script=guard)
        self.assertEqual(code, 1, out + err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(self.status(1)[0], "failed")
        self.assertIn("is excluded: no tool opens, hashes or moves it", self.status(1)[1])
        self.assertEqual(tree_digest(self.root), before, "a refused row changed the folder")
        self.assertEqual(self.bin_names(), [])

    def test_a_delete_row_whose_copy_or_canonical_copy_is_staged_for_another_project_is_refused_before_hashing(self):
        man = json.loads(read(self.manifest_path))
        slides = next(h for h, e in man["entries"].items() if e["current_path"] == "04 Study/Slides.pptx")
        entry = man["entries"][slides]
        staged = "_Migrations/Other Project/Slides.pptx"
        entry["current_path"] = staged
        entry["copies"] = [{"path": staged, "kind": "canonical"}, {"path": "05 Archive/Slides.pptx", "kind": "redundant"}]
        write(self.manifest_path, json.dumps(man))
        write_rows(self.plan, [row(1, "delete", "05 Archive/Slides.pptx", "", slides, kind="redundant")])
        guard = never_hash("Slides")
        code, out, err = self.run_plan("check", "--root", self.root, "--plan", self.plan, script=guard)
        self.assertEqual(code, 1, out + err)
        self.assertIn("is held for another project: no tool opens, hashes or moves it", out)
        code, out, err = self.execute("--phase", "deletes", script=guard)
        self.assertEqual(code, 1, out + err)
        self.assertIn("is held for another project", self.status(1)[1])
        self.assertTrue(os.path.exists(self.path("05 Archive/Slides.pptx")))

    def test_every_kind_of_row_naming_an_excluded_path_is_refused_by_check_and_by_both_phases(self):
        self.exclude("03 Home")
        rows = [row(1, "create", "", "03 Home/New/"), row(2, "rmdir", "03 Home/Utilities /"),
                row(3, "rename", "03 Home/Utilities /", "03 Home/Utilities/"),
                row(4, "move", "03 Home/Lease renewal.pdf", "04 Study/Lease.pdf", self.ids["03 Home/Lease renewal.pdf"]),
                row(5, "delete", "03 Home/Lease notes .txt", "", "d" * 64, kind="redundant")]
        write_rows(self.plan, rows)
        guard = never_hash("Lease", "Electricity")
        code, out, err = self.run_plan("check", "--root", self.root, "--plan", self.plan, script=guard)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(sorted(line.split()[1] for line in out.splitlines() if line.startswith("FAIL")),
                         ["1", "2", "3", "4", "5"])
        before = tree_digest(self.root)
        code, out, err = self.execute(script=guard)
        self.assertNotIn("Traceback", err)
        self.assertEqual(code, 1, out + err)
        self.assertEqual({r["status"] for r in self.rows().values() if r["seq"] != "5"} - {"failed", "skipped"}, set())
        self.assertEqual(self.status(1)[0], "failed", "a row's domain stops at its first failure")
        self.assertIn("excluded from reading", self.status(1)[1])
        self.assertEqual(tree_digest(self.root), before)
        write_rows(self.plan, [rows[4]])
        code, out, err = self.execute("--phase", "deletes", script=guard)
        self.assertEqual(code, 1, out + err)
        self.assertIn("the from path is excluded", self.status(5)[1])
        self.assertEqual(tree_digest(self.root), before)


# ---------------------------------------------------------------------------------------------- work folder

class WorkFolderTest(PlanCase):
    """`--work` as every other tool takes it: the work folder a plan tool purges at its start is the one it resolved
    (the argument, else the default for the folder), never another."""

    WITHHELD = "IMG_0001.jpg"   # excluded after the audit: its cached section note is what a withheld document leaves

    def setUp(self):
        super().setUp()
        twin = os.path.join(self.root, ".familyai", "rulebook.json")
        write(twin, json.dumps(dict(json.loads(read(twin)), exclude=[self.WITHHELD]), ensure_ascii=False))
        for kind in ("extract", "cards"):   # the fixture has a record and a card of it: they would add to the counts
            os.remove(self.path("_Audit/%s/%s.json" % (kind, self.ids[self.WITHHELD])))
        self.default_work = os.path.join(self.home, ".ai-os-pre-onboarding", "Alex-Personal")
        self.given_work = os.path.join(self.tmp, "state kept elsewhere")

    def leave_a_note(self, work):
        """What a withheld document's cached section note looks like, in the work folder `work`."""
        note = os.path.join(work, "sections", "%s_codex_1_2_abc.txt" % self.ids[self.WITHHELD][:16])
        write(note, "[section 1 of 2]\nA note.\n")
        return note

    def commands(self):
        """Every subcommand that takes --root, with the arguments it needs (`--work` is added by the test)."""
        paths = os.path.join(self.tmp, "paths.txt")
        write(paths, "06 Work/Contract.docx\n")
        write_rows(self.plan, [])
        out = os.path.join(self.tmp, "proposed")
        return {"light": ["light", "--root", self.root, "--out", out],
                "migrate": ["migrate", "--root", self.root, "--project", "Household", "--paths-file", paths,
                            "--out", out],
                "return": ["return", "--root", self.root, "--project", "Household", "--paths-file", paths,
                           "--out", out],
                "rmdirs": ["rmdirs", "--root", self.root, "--plan", self.plan],
                "check": ["check", "--root", self.root, "--plan", self.plan],
                "execute": ["execute", "--root", self.root, "--plan", self.plan, "--bin", self.bin]}

    PURGED = "purged what withheld documents left behind: 1 cached section note\n"

    def test_every_subcommand_with_a_root_purges_the_work_folder_it_was_given_and_no_other(self):
        for cmd, args in self.commands().items():
            with self.subTest(cmd=cmd):
                given, default = self.leave_a_note(self.given_work), self.leave_a_note(self.default_work)
                before = tree_digest(self.default_work)
                code, out, err = self.run_plan(*args, "--work", self.given_work)
                self.assertEqual(code, 0, out + err)
                self.assertNotIn("Traceback", err)
                self.assertIn(self.PURGED, err)
                self.assertFalse(os.path.lexists(given), "the work folder it was given kept the withheld note")
                self.assertTrue(os.path.isfile(default), "a work folder it was not given was cleared")
                self.assertEqual(tree_digest(self.default_work), before)
                shutil.rmtree(self.default_work)

    def test_without_a_work_argument_it_purges_the_default_work_folder_of_the_folder(self):
        for cmd, args in self.commands().items():
            with self.subTest(cmd=cmd):
                default, other = self.leave_a_note(self.default_work), self.leave_a_note(self.given_work)
                code, out, err = self.run_plan(*args)
                self.assertEqual(code, 0, out + err)
                self.assertIn(self.PURGED, err)
                self.assertFalse(os.path.lexists(default))
                self.assertTrue(os.path.isfile(other), "a work folder nobody named was cleared")
                shutil.rmtree(self.given_work)

    def test_a_work_folder_that_does_not_exist_yet_is_no_error(self):
        missing = os.path.join(self.tmp, "not made yet", "work")
        for cmd, args in self.commands().items():
            with self.subTest(cmd=cmd):
                code, out, err = self.run_plan(*args, "--work", missing)
                self.assertEqual(code, 0, out + err)
                self.assertNotIn("Traceback", err)

    def test_a_relative_work_is_made_absolute_from_the_current_directory(self):
        here = os.path.join(self.tmp, "here")
        os.makedirs(here)
        note = self.leave_a_note(os.path.join(here, "rel", "work"))
        code, out, err = self.run_plan("light", "--root", self.root, "--out", os.path.dirname(self.plan),
                                       "--work", os.path.join("rel", "work"), cwd=here)
        self.assertEqual(code, 0, out + err)
        self.assertIn(self.PURGED, err)
        self.assertFalse(os.path.lexists(note))

    def test_a_work_folder_inside_the_folder_is_refused_before_anything_is_purged_or_written(self):
        link = os.path.join(self.tmp, "a link to the folder")
        os.symlink(self.root, link)
        for name, work in {"inside": self.path("scratch"), "the folder itself": self.root,
                           "through a link": os.path.join(link, "scratch")}.items():
            for cmd, args in self.commands().items():
                with self.subTest(name, cmd=cmd):
                    real = os.path.realpath(work)
                    note = self.leave_a_note(real)   # inside the folder: a purge before the refusal would remove it
                    default = self.leave_a_note(self.default_work)
                    before, before_default = tree_digest(self.root), tree_digest(self.default_work)
                    code, out, err = self.run_plan(*args, "--work", work)
                    self.assertEqual(code, 2, out + err)
                    self.assertIn("error: --work must be outside the folder: ", err)
                    self.assertNotIn("Traceback", err)
                    self.assertNotIn("purged", err)
                    self.assertTrue(os.path.isfile(note), "the note in the refused work folder was purged")
                    self.assertEqual(tree_digest(self.root), before, "the refused run wrote or removed a file")
                    self.assertTrue(os.path.isfile(default))
                    self.assertEqual(tree_digest(self.default_work), before_default)
                    shutil.rmtree(os.path.join(real, "sections"))
                    shutil.rmtree(self.default_work)
                    shutil.rmtree(self.path("scratch"), True)

    def test_the_refusal_is_the_other_tools_refusal(self):
        inside = self.path("scratch")
        _c, _o, plan_err = self.run_plan("light", "--root", self.root, "--out", os.path.dirname(self.plan),
                                         "--work", inside)
        _c, _o, audit_err = self.run_tool("audit.py", "--root", self.root, "--work", inside)
        self.assertEqual(plan_err, audit_err)
        self.assertEqual(plan_err, "error: --work must be outside the folder: %s\n" % os.path.realpath(inside))

    def test_the_subcommands_without_a_root_take_no_work_folder(self):
        for args in (["approve", "--plan", self.plan, "--rows", "all"],
                     ["prove", "--plan", self.plan, "--before", self.manifest_path, "--after", self.manifest_path]):
            with self.subTest(cmd=args[0]):
                code, _o, err = self.run_plan(*args, "--work", self.given_work)
                self.assertEqual(code, 2)
                self.assertIn("unrecognized arguments: --work", err)


# ---------------------------------------------------------------------------------------------- migrations

class MigrationRoundTest(PlanCase):
    def round(self, cmd, paths, out, rmdirs=False):
        """Propose, approve, (with `rmdirs`, then propose and approve removing the folders the moves empty), execute,
        re-audit and prove."""
        paths_file = os.path.join(self.tmp, cmd + ".txt")
        write(paths_file, "# one path per line\n" + "".join(p + "\n" for p in paths))
        code, _o, err = self.run_plan(cmd, "--root", self.root, "--project", "Household", "--paths-file",
                                      paths_file, "--out", out)
        self.assertEqual(code, 0, err)
        self.plan = os.path.join(out, "move-plan.csv")
        self.assertEqual({r["action"] for r in self.rows().values()}, {"move"}, "a round proposes moves only")
        self.run_plan("approve", "--plan", self.plan, "--rows", "all")
        if rmdirs:
            code, _o, err = self.run_plan("rmdirs", "--root", self.root, "--plan", self.plan, "--approve-note",
                                          "Alex agreed")
            self.assertEqual(code, 0, err)
        before = os.path.join(out, "before.json")
        shutil.copy(self.manifest_path, before)
        code, out_, err = self.execute()
        self.assertEqual(code, 0, out_ + err)
        self.audit()
        code, proof, err = self.run_plan("prove", "--plan", self.plan, "--before", before, "--after",
                                         self.manifest_path)
        self.assertEqual(code, 0, proof + err)
        return read(os.path.join(os.path.dirname(self.plan), "review.tsv"))

    def test_stage_for_another_project_and_bring_back(self):
        original = tree_digest(self.root, skip=("_Audit",))
        review = self.round("migrate", ["06 Work/", "Missing.pdf"], os.path.join(self.tmp, "round1"))
        self.assertIn("MISSING\tMissing.pdf", review)
        self.assertIn("Household\t06 Work/Essay.docx\tcanonical\t04 Study/Essay.docx; 05 Archive/Essay.docx", review)
        staged = {e["current_path"]: e.get("migration_target") for e in self.manifest["entries"].values()
                  if "migrating" in e["flags"]}
        self.assertEqual(staged["_Migrations/Household/06 Work/Contract.docx"], "Household")
        self.assertEqual(staged["04 Study/Essay.docx"], "Household")      # the staged copy marks its entry
        self.assertFalse(os.path.exists(self.path("06 Work/Contract.docx")))

        partial = os.path.join(self.tmp, "partial")
        write(os.path.join(self.tmp, "partial.txt"), "06 Work/Essay.docx\nNowhere.pdf\n")
        self.run_plan("return", "--root", self.root, "--project", "Household", "--paths-file",
                      os.path.join(self.tmp, "partial.txt"), "--out", partial)
        self.assertEqual([(r["action"], r["from"]) for r in read_rows(os.path.join(partial, "move-plan.csv"))],
                         [("move", "_Migrations/Household/06 Work/Essay.docx")])
        self.assertIn("MISSING\t_Migrations/Household/Nowhere.pdf", read(os.path.join(partial, "review.tsv")))

        self.round("return", ["06 Work/Essay.docx", "06 Work/Contract.docx"], os.path.join(self.tmp, "round2"),
                   rmdirs=True)
        rows = list(self.rows().values())
        self.assertEqual([(r["action"], r["from"], r["status"]) for r in rows if r["action"] == "rmdir"],
                         [("rmdir", "_Migrations/Household/", "done")])
        self.assertEqual(self.bin_names(), ["Household"])
        self.assertEqual(tree_digest(self.root, skip=("_Audit",)), original)


# ---------------------------------------------------------------------------------------------- reorg

CLOUD_ONLY = """
import sys
sys.path.insert(0, sys.argv[1])
import common
import plan
common.is_dataless = lambda path: path.endswith("b.txt")
sys.argv = ["plan.py"] + sys.argv[2:]
common.run_main(plan.main)
"""


class ReorgCase(PlanCase):
    """The fixture copy with a few invented folders of plain files, so that a mapping has something to move: `07 Misc`
    (a, b, dup, and Sub/c), `08 Other` (a, original) and `09 More` (a), all of different bytes but `dup` and `original`,
    `10 Wrap/Inner/z`, a folder that holds only a folder, and `12 Decks/Slides.key`, an iWork package."""

    FILES = {"07 Misc/a.txt": "alpha", "07 Misc/b.txt": "bravo", "07 Misc/Sub/c.txt": "charlie",
             "07 Misc/dup.txt": "original", "08 Other/a.txt": "alpha two", "08 Other/original.txt": "original",
             "09 More/a.txt": "alpha three", "10 Wrap/Inner/z.txt": "zulu", "12 Decks/Slides.key/Index/Doc.iwa": "iwa"}

    def prepare(self):
        for rel, text in self.FILES.items():
            write(self.path(rel), text)

    def mapping(self, scope, moves, name="mapping.json"):
        path = os.path.join(self.tmp, name)
        write(path, json.dumps({"scope": scope, "moves": [{"from": f, "to": t} for f, t in moves]}))
        return path

    def reorg(self, scope, moves, out=None, code=0, extra=(), **kw):
        out = out or os.path.dirname(self.plan)
        got, o, err = self.run_plan("reorg", "--root", self.root, "--mapping", self.mapping(scope, moves), "--out", out,
                                    *extra, **kw)
        self.assertEqual(got, code, o + err)
        self.assertNotIn("Traceback", err)
        return (o, err)

    def refuses(self, scope, moves, *whys, extra=()):
        """The mapping is refused with every one of `whys`, naming each, nothing written and the folder untouched."""
        before = tree_digest(self.root)
        _o, err = self.reorg(scope, moves, code=2, extra=extra)
        self.assertIn("refused, nothing written", err)
        for why in whys:
            self.assertIn(why, err)
        self.assertFalse(os.path.exists(self.plan), "a refusal writes no plan")
        self.assertEqual(tree_digest(self.root), before)
        return err

    def proposal(self, scope, moves):
        self.reorg(scope, moves)
        return [(r["action"], r["from"], r["to"]) for r in read_rows(self.plan)]


class ReorgProposalTest(ReorgCase):
    def test_files_and_folders_expand_to_create_move_and_rmdir_rows(self):
        out, err = self.reorg(["06 Work", "07 Misc"], [("06 Work/Contract.docx", "06 Work/Employment"),
                                                       ("07 Misc", "11 Filed/Misc")])
        self.assertIn("create 4, move 5 (from 2 mapping row(s)), rmdir 1", out)
        rows = read_rows(self.plan)
        self.assertEqual([(r["seq"], r["action"], r["from"], r["to"]) for r in rows], [
            ("1", "create", "", "11 Filed/"), ("2", "create", "", "06 Work/Employment/"),
            ("3", "create", "", "11 Filed/Misc/"), ("4", "create", "", "11 Filed/Misc/Sub/"),
            ("5", "move", "06 Work/Contract.docx", "06 Work/Employment/Contract.docx"),
            ("6", "move", "07 Misc/Sub/c.txt", "11 Filed/Misc/Sub/c.txt"),
            ("7", "move", "07 Misc/a.txt", "11 Filed/Misc/a.txt"),
            ("8", "move", "07 Misc/b.txt", "11 Filed/Misc/b.txt"),
            ("9", "move", "07 Misc/dup.txt", "11 Filed/Misc/dup.txt"),
            ("10", "rmdir", "07 Misc/", "")])
        moves = [r for r in rows if r["action"] == "move"]
        self.assertTrue(all(r["depth"] == "medium" and r["status"] == "proposed" and r["approved"] == "" for r in rows))
        self.assertEqual([r["evidence"] for r in moves], [self.ids[r["from"]] for r in moves],
                         "each move carries the manifest's id of its document")
        self.assertEqual([r["domain"] for r in rows], ["11 Filed", "06 Work", "11 Filed", "11 Filed", "06 Work",
                                                       "07 Misc", "07 Misc", "07 Misc", "07 Misc", "07 Misc"])
        self.assertEqual(moves[0]["reason"], "re-organisation: the approved mapping files it under 06 Work/Employment")
        self.assertEqual(moves[1]["reason"], "re-organisation: the approved mapping moves everything under 07 Misc/ "
                         "to 11 Filed/Misc")
        self.assertEqual(rows[-1]["needs_a_look"], "empty only if every move out of it is approved; the owner may "
                         "decline it (keep_empty_folders)")

    def test_a_folder_merges_into_a_folder_that_exists_keeping_its_structure(self):
        self.assertEqual(self.proposal(["07 Misc"], [("07 Misc/Sub", "08 Other")]), [
            ("move", "07 Misc/Sub/c.txt", "08 Other/c.txt"), ("rmdir", "07 Misc/Sub/", "")])
        write(self.path("07 Misc/Sub/deeper/d.txt"), "delta")
        self.audit()
        os.remove(self.plan)
        self.assertEqual(self.proposal(["07 Misc"], [("07 Misc/Sub", "08 Other")]), [
            ("create", "", "08 Other/deeper/"), ("move", "07 Misc/Sub/c.txt", "08 Other/c.txt"),
            ("move", "07 Misc/Sub/deeper/d.txt", "08 Other/deeper/d.txt"), ("rmdir", "07 Misc/Sub/", "")])

    def test_a_move_row_carries_the_copy_kind_and_a_trailing_slash_is_ignored(self):
        self.proposal(["04 Study"], [("04 Study/Slides.pptx/", "04 Study/Reading/")])
        move = next(r for r in read_rows(self.plan) if r["action"] == "move")
        self.assertEqual((move["from"], move["to"], move["kind"]), ("04 Study/Slides.pptx",
                                                                      "04 Study/Reading/Slides.pptx", "canonical"))

    def test_a_package_moves_as_one_document(self):
        self.assertEqual(self.proposal(["03 Home"], [(LEASE_PAGES, "03 Home/Old leases")]),
                         [("create", "", "03 Home/Old leases/"),
                          ("move", LEASE_PAGES, "03 Home/Old leases/Lease renewal.pages")])

    def test_a_name_in_another_unicode_form_than_the_folders_is_the_same_name(self):
        """A name stored decomposed on disk is written composed by a model: the plan takes the folder's own spelling,
        which is what the audit records and what the proof then compares."""
        import unicodedata
        composed, decomposed = "Caf\u00e9", unicodedata.normalize("NFD", "Caf\u00e9")
        write(self.path("07 Misc/%s.txt" % decomposed), "coffee")
        write(self.path("09 More/%s bar/z.txt" % decomposed), "bar")
        self.audit()
        stored = [p for p in self.ids if "Caf" in p]
        if not any(decomposed in p for p in stored):
            self.skipTest("this file system stores a name composed whatever form it is written in")
        self.reorg(["07 Misc"], [("07 Misc/%s.txt" % composed, "09 More/%s bar" % composed)])
        move = next(r for r in read_rows(self.plan) if r["action"] == "move")
        self.assertEqual((move["from"], move["to"]), ("07 Misc/%s.txt" % decomposed,
                                                      "09 More/%s bar/%s.txt" % (decomposed, decomposed)))
        self.assertEqual([r["action"] for r in read_rows(self.plan)], ["move"], "no folder is created beside the one there")

    def test_a_folder_the_moves_empty_but_a_pack_the_rulebook_or_the_schema_names_gets_no_rmdir(self):
        moves = [("04 Study/%s" % n, "07 Misc/Study") for n in ("Cours de français.pdf", "Essay.docx", "Notes.rtf",
                                                                  "Slides.pptx", "中文课程.pdf")]
        out, _err = self.reorg(["04 Study"], moves)
        self.assertNotIn("rmdir", [r["action"] for r in read_rows(self.plan)])
        self.assertIn("no rmdir row for 1 emptied folder(s) that a pack, the rulebook or the Schema names: 04 Study", out)

    def test_a_folder_the_moves_empty_above_the_scope_gets_no_rmdir_and_the_scope_folder_does(self):
        out, _err = self.reorg(["10 Wrap/Inner"], [("10 Wrap/Inner/z.txt", "09 More")])
        self.assertEqual([(r["action"], r["from"]) for r in read_rows(self.plan)],
                         [("move", "10 Wrap/Inner/z.txt"), ("rmdir", "10 Wrap/Inner/")])
        self.assertIn("no rmdir row for 1 emptied folder(s) that lie outside the scope: 10 Wrap", out)

    def test_files_the_owner_excluded_stay_where_they_are_and_are_counted(self):
        p = self.path(".familyai/rulebook.json")
        data = json.loads(read(p))
        data["exclude"] = ["07 Misc/Sub"]
        write(p, json.dumps(data, indent=1))
        self.audit()
        out, _err = self.reorg(["07 Misc"], [("07 Misc", "08 Other/Misc")])
        self.assertIn("left where they are: 1 path(s) under a folder that moves, which no tool may read", out)
        rows = read_rows(self.plan)
        self.assertEqual(sorted(r["from"] for r in rows if r["action"] == "move"),
                         ["07 Misc/a.txt", "07 Misc/b.txt", "07 Misc/dup.txt"])
        self.assertNotIn("rmdir", [r["action"] for r in rows], "the folder still holds the excluded file")
        self.assertNotIn("Sub", read(self.plan), "the excluded path is named nowhere in the plan")

    def test_a_proposal_does_not_replace_a_plan_the_owner_has_begun_to_decide(self):
        self.reorg(["07 Misc"], [("07 Misc/a.txt", "11 Filed")])
        self.run_plan("approve", "--plan", self.plan, "--rows", "1", "--note", "Alex agreed")
        before = tree_digest(os.path.dirname(self.plan))
        _o, err = self.reorg(["07 Misc"], [("07 Misc/b.txt", "09 More")], code=2)
        self.assertIn("already holds 1 approved, declined or deferred row(s)", err)
        self.assertEqual(tree_digest(os.path.dirname(self.plan)), before)

    def test_read_only_root(self):
        inside = self.path("_Audit/plans/2026-01-01")
        _o, err = self.reorg(["07 Misc"], [("07 Misc/b.txt", "09 More")], out=inside, code=2, extra=["--read-only-root"])
        self.assertIn("--read-only-root", err)
        self.assertFalse(os.path.exists(os.path.join(inside, "move-plan.csv")))
        elsewhere = os.path.join(self.tmp, "elsewhere")
        self.reorg(["07 Misc"], [("07 Misc/b.txt", "09 More")], out=elsewhere, extra=["--read-only-root"])
        self.assertTrue(os.path.exists(os.path.join(elsewhere, "move-plan.csv")))


class ReorgRefusalTest(ReorgCase):
    def test_a_mapping_of_the_wrong_shape_is_refused_by_name(self):
        cases = [("not json", "not valid JSON"), ("[]", "expected a JSON object"),
                 ('{"scope": ["07 Misc"]}', "the mapping is {\"scope\": [...], \"moves\": [...]}"),
                 ('{"scope": ["07 Misc"], "moves": [], "note": 1}', "the keys ['moves', 'note', 'scope']"),
                 ('{"scope": [], "moves": [{"from": "a", "to": "b"}]}', "scope must be a non-empty list of folders"),
                 ('{"scope": [1], "moves": [{"from": "a", "to": "b"}]}', "scope must be a non-empty list of folders"),
                 ('{"scope": ["07 Misc"], "moves": []}', "moves must be a non-empty list"),
                 ('{"scope": ["07 Misc"], "moves": [{"from": "a"}]}', "moves[0] must be"),
                 ('{"scope": ["07 Misc"], "moves": [{"from": "a", "to": "b", "why": "c"}]}', "moves[0] must be"),
                 ('{"scope": ["07 Misc"], "moves": [{"from": "a", "to": 1}]}', "moves[0] must be")]
        for text, why in cases:
            with self.subTest(text=text):
                path = os.path.join(self.tmp, "m.json")
                write(path, text)
                code, o, err = self.run_plan("reorg", "--root", self.root, "--mapping", path, "--out",
                                             os.path.dirname(self.plan))
                self.assertEqual(code, 2, o + err)
                self.assertIn(why, err)
                self.assertFalse(os.path.exists(self.plan))
        code, _o, err = self.run_plan("reorg", "--root", self.root, "--mapping", os.path.join(self.tmp, "none.json"),
                                      "--out", os.path.dirname(self.plan))
        self.assertEqual(code, 2, err)
        self.assertIn("cannot read the mapping", err)

    def test_a_path_that_is_not_relative_to_the_folder(self):
        for bad in ("", "/07 Misc/a.txt", "07 Misc/../08 Other/a.txt", "07 Misc//a.txt", "./07 Misc/a.txt",
                    "07 Misc/a\u0001.txt"):
            with self.subTest(bad=bad):
                self.refuses(["07 Misc"], [(bad, "09 More")], "is not a path relative to the folder")
        self.refuses(["07 Misc"], [("07 Misc/b.txt", "09 More/../x")], "moves[0] to")
        self.refuses(["../07 Misc"], [("07 Misc/b.txt", "09 More")], "scope[0] path")

    def test_a_from_that_is_nothing_or_outside_the_scope(self):
        err = self.refuses(["07 Misc"], [("07 Misc/missing.txt", "09 More"), ("08 Other/a.txt", "09 More"),
                                         ("07 Misc/b.txt", "09 More")],
                           "moves[0]: '07 Misc/missing.txt' is neither a live document nor a folder holding one",
                           "moves[1]: '08 Other/a.txt' is outside the folders the owner approved (scope)")
        self.assertNotIn("moves[2]", err, "the row in scope is not refused")
        self.refuses(["07 Misc"], [("07", "09 More")], "'07' is neither a live document nor a folder")
        self.refuses(["07 Misc/Sub"], [("07 Misc", "09 More")], "'07 Misc' is outside the folders the owner approved")
        self.refuses(["Nowhere"], [("07 Misc/b.txt", "09 More")], "scope[0]: 'Nowhere' is not a folder holding live "
                                                                  "documents")

    def test_a_document_the_owner_excluded_or_staged_is_refused_without_naming_its_path(self):
        p = self.path(".familyai/rulebook.json")
        data = json.loads(read(p))
        data["exclude"] = ["08 Other"]
        write(p, json.dumps(data, indent=1))
        self.audit()
        err = self.refuses(["07 Misc", "08 Other"], [("08 Other/a.txt", "09 More"), ("08 Other", "09 More"),
                                                    ("07 Misc/a.txt", "08 Other")],
                           "moves[0]: its from path is excluded: no tool opens, hashes or moves it",
                           "moves[1]: its from path is excluded", "moves[2]: its to path is excluded",
                           "scope[1]: the folder is excluded")
        self.assertNotIn("original", err)
        err = self.refuses(["_Migrations/Other Project"], [("_Migrations/Other Project/02 Finance/Old invoice.pdf",
                                                            "09 More")],
                           "scope[0]: the folder is held for another project",
                           "moves[0]: its from path is held for another project")
        self.assertNotIn("Old invoice", err)

    def test_nothing_inside_a_pack_moves_or_is_filed_into_one(self):
        pack = "01 Identity/Passport renewal 2021"
        self.refuses(["01 Identity"], [(pack + "/Application form.docx", "01 Identity/Docs")],
                     "moves[0]: 1 of its documents are inside a pack (01 Identity/Passport renewal 2021/Application form"
                     ".docx): copies in a pack are never moved")
        self.refuses(["01 Identity"], [(pack, "01 Identity/Docs")], "2 of its documents are inside a pack")
        self.refuses(["07 Misc"], [("07 Misc/b.txt", pack)], "moves[0]: '%s' is inside a pack" % pack)

    def test_a_folder_the_rulebook_names_is_not_moved_whole(self):
        for folder, key in (("02 Finance", "active"), ("04 Study", "finished")):
            with self.subTest(folder=folder):
                self.refuses([folder], [(folder, "09 More")],
                             "moves[0]: moving %r whole leaves `%s` in .familyai/rulebook.json naming a folder that "
                             "is gone; update it first (edit CLAUDE.md, its AGENTS.md copy and .familyai/rulebook.json, "
                             "then re-pin rulebook_sha256), then propose again" % (folder, key))
        p = self.path(".familyai/rulebook.json")
        data = json.loads(read(p))
        data["active"].append("07 Misc/Sub")
        write(p, json.dumps(data, indent=1))
        self.refuses(["07 Misc"], [("07 Misc", "09 More")], "moving '07 Misc' whole leaves `active` in .familyai")
        self.assertEqual(self.proposal(["07 Misc"], [("07 Misc/Sub/c.txt", "09 More")])[0][0], "move",
                         "a document in a named folder moves; only a whole folder is refused")

    def test_a_folder_the_schema_routes_is_not_moved_whole_once_it_is_compiled(self):
        self.assertEqual(self.proposal(["02 Finance"], [("02 Finance/Tax", "07 Misc")])[0][0], "move")
        os.remove(self.plan)
        code, _o, err = self.run_tool("settings.py", "compile", "--root", self.root, "--work",
                                      os.path.join(self.tmp, "work"))
        self.assertEqual(code, 0, err)
        self.refuses(["02 Finance"], [("02 Finance/Tax", "07 Misc")],
                     "moving '02 Finance/Tax' whole leaves the Routing table of Alex Personal Wiki/90 Schema/90 "
                     "Schema.md naming a folder that is gone; update it first (edit that page, then run settings.py "
                     "compile), then propose again")
        self.assertEqual(self.proposal(["02 Finance"], [("02 Finance/Tax/Tax return 2023.pdf", "07 Misc")])[0][0],
                         "move")

    def test_a_destination_the_system_keeps(self):
        for to in ("_Audit/x", "_Inbox", "_Migrations/Household", "Alex Personal Wiki/20 Finance", ".familyai", "Outbox",
                   "Wiki/x", "CLAUDE.md/x", "_whatever", ".hidden/x", "ALEX PERSONAL WIKI/x"):
            with self.subTest(to=to):
                self.refuses(["07 Misc"], [("07 Misc/b.txt", to)], "is a name the system reserves")

    def test_a_destination_that_is_not_a_place_for_a_document(self):
        self.refuses(["07 Misc"], [("07 Misc/b.txt", "03 Home/Lease notes .txt")],
                     "'03 Home/Lease notes .txt' exists and is not a folder")
        self.refuses(["07 Misc"], [("07 Misc/b.txt", "12 Decks/Slides.key/Index")],
                     "'12 Decks/Slides.key/Index' is inside the package '12 Decks/Slides.key', which is one document")
        self.refuses(["07 Misc"], [("07 Misc/b.txt", "09 more")], "the folder '09 More' is spelled '09 more' in "
                                                                  "'09 more'; spell it as the folder is")
        self.refuses(["07 Misc"], [("07 Misc/b.txt", "09 More/New ")],
                     "'09 More/New ' would create a folder named with a space at either end")
        self.refuses(["07 Misc"], [("07 Misc", "07 Misc"), ("07 Misc/Sub", "07 Misc/Sub/deeper")],
                     "moves[0]: '07 Misc' is the folder it moves, or inside it",
                     "moves[1]: '07 Misc/Sub/deeper' is the folder it moves, or inside it")

    def test_a_destination_file_that_exists_or_is_claimed_twice_or_is_where_the_document_already_is(self):
        self.refuses(["07 Misc"], [("07 Misc/a.txt", "08 Other")],
                     "moves[0]: the destination '08 Other/a.txt' exists (nothing is overwritten)")
        self.refuses(["07 Misc", "09 More"], [("07 Misc/a.txt", "11 New"), ("09 More/a.txt", "11 New")],
                     "moves[1]: '09 More/a.txt' and '07 Misc/a.txt' both move to '11 New/a.txt'")
        self.refuses(["07 Misc"], [("07 Misc/a.txt", "07 Misc")], "moves[0]: '07 Misc/a.txt' is in '07 Misc' already")
        write(self.path("08 Other/B.TXT"), "case")                  # a file on disk the manifest has not seen
        self.refuses(["07 Misc"], [("07 Misc/b.txt", "08 Other")], "the destination '08 Other/b.txt' exists")
        self.refuses(["07 Misc"], [("07 Misc/a.txt", "11 New"), ("07 Misc", "11 New")],
                     "'07 Misc/a.txt' is also moved by moves[0]")

    def test_a_duplicate_of_what_the_destination_holds_is_left_to_the_light_round(self):
        err = self.refuses(["07 Misc"], [("07 Misc/dup.txt", "08 Other")],
                           "moves[0]: the content of '07 Misc/dup.txt' already lives at '08 Other/original.txt' once "
                           "the moves are done (a duplicate): drop the copy with the light round (plan.py light) and "
                           "leave it out of the mapping")
        self.assertNotIn("destination", err)
        # in a sub-folder of the destination counts; a copy that moves out of it does not; a copy moving in does
        self.refuses(["07 Misc", "08 Other"], [("07 Misc/dup.txt", "08 Other"), ("08 Other/original.txt", "08 Other/Sub")],
                     "already lives at '08 Other/Sub/original.txt'")
        self.assertEqual(self.proposal(["07 Misc", "08 Other"], [("07 Misc/dup.txt", "08 Other"),
                                                                 ("08 Other/original.txt", "11 Else")])[:2],
                         [("create", "", "11 Else/"), ("move", "07 Misc/dup.txt", "08 Other/dup.txt")])
        os.remove(self.plan)
        self.refuses(["07 Misc", "08 Other"], [("07 Misc/dup.txt", "11 New"), ("08 Other/original.txt", "11 New/Sub")],
                     "already lives at '11 New/")

    def test_a_copy_may_move_to_a_new_place_but_not_over_its_original(self):
        self.assertEqual(self.proposal(["05 Archive"], [("05 Archive/Essay.docx", "04 Study/Old")]),
                         [("create", "", "04 Study/Old/"), ("move", "05 Archive/Essay.docx", "04 Study/Old/Essay.docx")])
        os.remove(self.plan)
        self.refuses(["05 Archive"], [("05 Archive/Essay.docx", "04 Study")],
                     "the destination '04 Study/Essay.docx' exists (nothing is overwritten)")

    def test_a_source_that_changed_is_gone_or_cloud_only(self):
        write(self.path("07 Misc/b.txt"), "changed since the audit")
        self.refuses(["07 Misc"], [("07 Misc/b.txt", "09 More"), ("07 Misc/a.txt", "11 New")],
                     "moves[0]: '07 Misc/b.txt' no longer hashes to its manifest id: it changed since the audit; "
                     "re-audit first")
        write(self.path("07 Misc/b.txt"), "bravo")
        os.remove(self.path("07 Misc/a.txt"))
        self.refuses(["07 Misc"], [("07 Misc/a.txt", "11 New")], "moves[0]: '07 Misc/a.txt' is not on disk: the "
                                                                  "manifest is older than the folder; re-audit first")

    def test_the_hash_is_the_last_check_and_opens_only_a_clean_mapping(self):
        write(self.path("07 Misc/b.txt"), "changed")
        err = self.refuses(["07 Misc"], [("07 Misc/b.txt", "08 Other"), ("07 Misc/a.txt", "08 Other")],
                           "the destination '08 Other/a.txt' exists")
        self.assertNotIn("no longer hashes", err, "a mapping with another fault is refused before any file is opened")

    def test_the_hash_check_runs_for_every_source_of_a_folder(self):
        write(self.path("07 Misc/Sub/c.txt"), "changed")
        self.refuses(["07 Misc"], [("07 Misc", "11 New")], "'07 Misc/Sub/c.txt' no longer hashes to its manifest id")

    def test_every_refusal_is_named_at_once(self):
        err = self.refuses(["07 Misc"], [("07 Misc/missing.txt", "09 More"), ("07 Misc/a.txt", "_x"),
                                         ("08 Other/a.txt", "09 More")], "3 problem(s)", "moves[0]", "moves[1]",
                           "moves[2]")
        self.assertEqual(err.count("\n  "), 3)


class ReorgRoundTest(ReorgCase):
    """A proposal runs through the existing approval, check, execute, re-audit and prove, and undoes."""

    def test_the_round_executes_proves_and_undoes(self):
        original = tree_digest(self.root, skip=("_Audit",))
        self.reorg(["06 Work", "07 Misc"], [("06 Work/Contract.docx", "06 Work/Employment"), ("07 Misc", "11 Filed/Misc")])
        self.run_plan("approve", "--plan", self.plan, "--rows", "all", "--note", "Alex agreed")
        code, out, err = self.run_plan("check", "--root", self.root, "--plan", self.plan)
        self.assertEqual((code, out.strip().splitlines()[-1]), (0, "rows ok 10 failed 0"), out + err)
        before = os.path.join(self.tmp, "manifest.before.json")
        shutil.copy(self.manifest_path, before)
        code, out, err = self.execute()
        self.assertEqual(code, 0, out + err)
        self.assertEqual({r["status"] for r in read_rows(self.plan)}, {"done"})
        for rel in ("11 Filed/Misc/Sub/c.txt", "11 Filed/Misc/a.txt", "06 Work/Employment/Contract.docx"):
            self.assertTrue(os.path.isfile(self.path(rel)), rel)
        self.assertFalse(os.path.exists(self.path("07 Misc")))
        self.assertEqual(self.bin_names(), ["07 Misc"])
        self.audit()
        code, proof, err = self.run_plan("prove", "--plan", self.plan, "--before", before, "--after", self.manifest_path)
        self.assertEqual(code, 0, proof + err)
        self.assertEqual(json.loads(proof)["rows_checked"], 5)
        for x in reversed([x for x in self.undo_lines() if x["phase"] == "done"]):
            src = os.path.join(self.root, x["undo"]["from"].rstrip("/"))
            dst = os.path.join(self.root, x["undo"]["to"].rstrip("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.rename(src, dst)
        self.assertEqual(tree_digest(self.root, skip=("_Audit",)), original)
        self.assertEqual(self.bin_names(), [])

    def test_an_rmdir_the_owner_approves_over_a_move_they_decline_fails_loud_and_loses_nothing(self):
        self.reorg(["07 Misc"], [("07 Misc/Sub", "08 Other")])
        rows = read_rows(self.plan)
        self.assertEqual([r["action"] for r in rows], ["move", "rmdir"])
        self.run_plan("approve", "--plan", self.plan, "--rows", "1", "--decline", "--note", "keep it")
        self.run_plan("approve", "--plan", self.plan, "--rows", "2", "--note", "tidy")
        code, out, err = self.execute()
        self.assertEqual(code, 1, out + err)
        self.assertIn("FAILED row 2 folder not empty", out)
        self.assertTrue(os.path.isfile(self.path("07 Misc/Sub/c.txt")))
        self.assertEqual(self.bin_names(), [])

    def test_a_cloud_only_source_is_refused_in_the_run_that_would_hash_it(self):
        before = tree_digest(self.root)
        code, out, err = self.run_tool("plan.py", "reorg", "--root", self.root, "--mapping", self.mapping(
            ["07 Misc"], [("07 Misc/b.txt", "09 More")]), "--out", os.path.dirname(self.plan), script=CLOUD_ONLY)
        self.assertEqual(code, 2, out + err)
        self.assertIn("moves[0]: '07 Misc/b.txt' is a cloud-only file, so it cannot be checked without downloading it; "
                      "download it first", err)
        self.assertEqual(tree_digest(self.root), before)
        self.assertFalse(os.path.exists(self.plan))


if __name__ == "__main__":
    unittest.main()
