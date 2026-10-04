"""The engine adapters against fake `agy` and `codex`: the argv, the environment, stdin, the working folder, the process
group, tool and denial rejection, quota, degenerate replies and the credential guard.

The flags pinned here are the ones in use today; the isolation spike (issue #91) may change them, and then these
tests change with them, deliberately.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests
"""
import json
import os
import re
import shutil
import signal
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import cards  # noqa: E402
import common  # noqa: E402
import engines  # noqa: E402
from fake_engines import SECRETS, Fakes, tool_env  # noqa: E402

CARD_SCHEMA = os.path.realpath(os.path.join(TOOLS, "schemas", "card.json"))
CODEX_SCHEMA = os.path.realpath(os.path.join(TOOLS, "schemas", "card_codex.json"))
CODEX_OFF = ["shell_tool", "unified_exec", "shell_snapshot", "memories", "apps", "browser_use",
             "browser_use_external", "computer_use", "in_app_browser", "image_generation", "multi_agent", "plugins",
             "remote_plugin", "code_mode_host", "hooks", "goals", "tool_suggest", "skill_mcp_dependency_install",
             "workspace_dependencies"]
PROMPT = "Summarise this. Café, 中文, naïve.\nSecond line."
CUT_STREAM = os.path.join(HERE, "fixtures", "agy", "agy-1.2.16-cut-stream.redacted.jsonl")
CUT_STDERR = os.path.join(HERE, "fixtures", "agy", "agy-1.2.16-cut-stderr.redacted.txt")
PLAN_STREAM = os.path.join(HERE, "fixtures", "agy", "agy-1.2.16-json-schema-plan.redacted.jsonl")
SCHEMA_STREAM = os.path.join(HERE, "fixtures", "agy", "agy-1.2.16-schema-in-prompt.redacted.jsonl")
SCHEMA_INTRO = "\n\nReply with JSON only, matching this JSON Schema exactly:\n"


def strict_problems(schema, where="$"):
    """An independent reading of the strict form codex needs: every object closed, every property required."""
    out = []
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            if schema.get("additionalProperties") is not False:
                out.append(where + " open")
            if sorted(schema.get("required", [])) != sorted(schema.get("properties", {})):
                out.append(where + " not all required")
            for k, v in schema.get("properties", {}).items():
                out += strict_problems(v, where + "." + k)
        if "items" in schema:
            out += strict_problems(schema["items"], where + "[]")
    return out


def card_schema_text():
    with open(CARD_SCHEMA, encoding="utf-8") as f:
        return f.read().strip()


class FakeEngineCase(unittest.TestCase):
    """Each test gets its own fakes, a patched environment (temp HOME, fake API keys) and a per-project state folder;
    nothing reads or writes a real home or a real engine."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="engines_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fakes = Fakes(self.tmp)
        self.env = tool_env(self.tmp, self.fakes, UNRELATED_SETTING="kept")
        patcher = mock.patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(self.state)

    def cwd(self):
        return tempfile.mkdtemp(prefix="call_", dir=self.tmp)

    def agy(self, **kw):
        return engines.Agy(kw.pop("model", "fake-model"), binary=self.fakes.path("agy"), **kw)

    def codex(self, **kw):
        return engines.Codex(kw.pop("model", "fake-model"), binary=self.fakes.path("codex"), **kw)

    def only_call(self, engine):
        calls = self.fakes.calls(engine)
        self.assertEqual(len(calls), 1, calls)
        return calls[0]

    def assert_own_group(self, call):
        self.assertEqual(call["pgid"], call["pid"], "the engine does not lead its own process group")
        self.assertEqual(call["sid"], call["pid"], "the engine does not run in its own session")
        self.assertNotEqual(call["pgid"], os.getpgid(0))

    def assert_no_secrets(self, call):
        self.assertTrue(set(SECRETS) <= set(self.env), "the test environment lost its fake secrets")
        leaked = sorted(set(SECRETS) & set(call["env"]))
        self.assertEqual(leaked, [], "secrets reached the engine")


class AgyTest(FakeEngineCase):
    def test_argv_stdin_environment_and_folder(self):
        self.fakes.script("agy", default={"kind": "text", "text": '{"ok": true}'})
        cwd = self.cwd()
        reply, usage = self.agy(state_home=self.state)(PROMPT, cwd, schema=CARD_SCHEMA)
        self.assertEqual(reply, '{"ok": true}')
        self.assertEqual(usage, {"input_tokens": 100, "output_tokens": 20})
        call = self.only_call("agy")
        self.assertEqual(call["argv"][1:], ["--input-format", "stream-json", "--output-format", "stream-json",
                                            "--model", "fake-model", "--sandbox", "--mode", "plan", "-p="])
        sent = PROMPT + SCHEMA_INTRO + card_schema_text()
        self.assertEqual(call["stdin"], json.dumps({"event": "user", "message": {"role": "user", "content": sent}},
                                                   ensure_ascii=False) + "\n")
        self.assertEqual(call["prompt"], sent)
        self.assertEqual(os.path.realpath(call["cwd"]), cwd)
        self.assertEqual(call["cwd_listing"], [])
        self.assert_own_group(call)
        self.assert_no_secrets(call)
        self.assertEqual(call["env"]["HOME"], self.state)
        self.assertEqual(call["env"]["UNRELATED_SETTING"], "kept")
        self.assertTrue(call["env"]["PATH"].startswith(self.env["PATH"] + ":"))

    def test_agy_is_never_given_json_schema_the_schema_goes_in_the_prompt(self):
        """With `--json-schema`, in plan mode, agy's model enters plan mode's workflow (see the two captures under
        tests/fixtures/agy), so a schema is asked for in the prompt and nothing is passed on the command line, whichever
        engine's schema it is."""
        self.fakes.script("agy", default={"kind": "text", "text": "fine"})
        for schema in (CARD_SCHEMA, CODEX_SCHEMA):
            self.agy()("hello", self.cwd(), schema=schema)
        self.agy()("hello", self.cwd())
        with_card, with_codex, without = self.fakes.calls("agy")
        for call in (with_card, with_codex, without):
            self.assertNotIn("--json-schema", call["argv"])
            self.assertNotIn("--output-schema", call["argv"])
            self.assertFalse([a for a in call["argv"] if a.endswith(".json")], call["argv"])
        self.assertEqual(without["prompt"], "hello")
        self.assertTrue(with_card["prompt"].startswith("hello" + SCHEMA_INTRO))
        self.assertTrue(with_card["prompt"].endswith(card_schema_text()))
        with open(CODEX_SCHEMA, encoding="utf-8") as f:
            self.assertTrue(with_codex["prompt"].endswith(f.read().strip()))

    def test_the_prompt_limit_counts_the_schema_text(self):
        extra = len((SCHEMA_INTRO + card_schema_text()).encode("utf-8"))
        room = engines.AGY_MAX_PROMPT_BYTES - extra
        self.fakes.script("agy", default={"kind": "text", "text": "fine"})
        self.assertEqual(self.agy()("a" * room, self.cwd(), schema=CARD_SCHEMA)[0], "fine")
        with self.assertRaises(engines.PromptTooLong) as cm:
            self.agy()("a" * (room + 1), self.cwd(), schema=CARD_SCHEMA)
        self.assertIn("%d-byte prompt" % (engines.AGY_MAX_PROMPT_BYTES + 1), str(cm.exception))
        self.assertEqual(self.agy()("a" * (room + 1), self.cwd())[0], "fine", "without the schema it fits")
        self.assertEqual(len(self.fakes.calls("agy")), 2)

    def test_a_schema_that_cannot_be_read_stops_the_run_before_the_call(self):
        with self.assertRaises(engines.SetupError):
            self.agy()("hello", self.cwd(), schema=os.path.join(self.tmp, "no-such-schema.json"))
        self.assertEqual(self.fakes.calls("agy"), [])

    def empty_stderr(self):
        path = os.path.join(self.tmp, "stderr.txt")
        with open(path, "w", encoding="utf-8"):
            pass
        return path

    def test_the_real_plan_mode_reply_of_a_json_schema_run_is_discarded(self):
        """agy 1.2.16 given `--json-schema` in plan mode wrote plan.md into its own state folder (a write_to_file tool
        step), ended with finish steps and replied by asking to be approved before the JSON. The reply is full of
        tool steps and is never a card, in either lane."""
        self.fakes.script("agy", default={"kind": "replay", "stdout": PLAN_STREAM, "stderr": self.empty_stderr()})
        for reads in (False, True):
            with self.subTest(allow_reads=reads):
                with self.assertRaises(engines.ToolUseError) as cm:
                    self.agy(allow_reads=reads)("hello", self.cwd(), schema=CARD_SCHEMA)
                self.assertIn("write_to_file", str(cm.exception))

    def test_the_real_reply_with_the_schema_in_the_prompt_parses_into_a_card(self):
        """The same kind of document with the schema's text in the prompt and no flag: the stream is a user_input and
        agent_response steps only, and the reply is the JSON alone, which the card checks accept."""
        self.fakes.script("agy", default={"kind": "replay", "stdout": SCHEMA_STREAM, "stderr": self.empty_stderr()})
        reply, usage = self.agy()(PROMPT, self.cwd(), schema=CARD_SCHEMA)
        self.assertIn("input_tokens", usage)
        items = common.parse_json(reply)["items"]
        self.assertEqual(len(items), 1)
        card = cards.validate(items[0], common.DEFAULTS["card_categories"])
        self.assertIsNotNone(card, cards.schema_problems(items[0], cards.CARD_SCHEMA))
        self.assertEqual((card["id"], card["category"], card["category_raw"]), ("doc-1", "Other", "administrative"))
        self.assertNotIn("--json-schema", self.only_call("agy")["argv"])

    def test_the_two_captures_show_what_the_flag_did(self):
        def events(path):
            with open(path, encoding="utf-8") as f:
                return [json.loads(line) for line in f]
        plan, clean = events(PLAN_STREAM), events(SCHEMA_STREAM)
        self.assertIn("json_schema", plan[0]["init"], "the plan-mode capture was run with --json-schema")
        self.assertNotIn("json_schema", clean[0]["init"], "the clean capture was run without it")

        def steps(evs):
            return [ev["step_update"] for ev in evs if ev["event"] == "step_update"]
        self.assertEqual({st["step_type"] for st in steps(clean)}, {"user_input", "agent_response"})
        self.assertTrue({"tool", "finish", "system_message"} <= {st["step_type"] for st in steps(plan)})
        self.assertIn("write_to_file", {st.get("tool_name") for st in steps(plan)})

    def test_without_schema_state_home_or_with_another_model(self):
        self.fakes.script("agy", default={"kind": "text", "text": "fine"})
        self.agy()("hello", self.cwd(), model="other-model")
        call = self.only_call("agy")
        self.assertEqual(call["argv"][1:], ["--input-format", "stream-json", "--output-format", "stream-json",
                                            "--model", "other-model", "--sandbox", "--mode", "plan", "-p="])
        self.assertEqual(call["env"]["HOME"], self.env["HOME"])
        self.assert_no_secrets(call)

    def test_a_model_is_required(self):
        with self.assertRaises(engines.EngineError):
            engines.Agy(None, binary=self.fakes.path("agy"))
        self.assertEqual(self.fakes.calls("agy"), [])

    def test_a_prompt_agy_would_cut_short_is_refused_before_the_call(self):
        """agy cuts a user message at about 192,000 UTF-8 bytes of prompt text, ASCII and CJK alike (measured on
        agy 1.2.16), so 185,000 bytes of either is refused whole, however it is written."""
        prompts = {"ASCII": "a" * 185_000, "CJK": "\u4e2d" * 61_666 + "ab"}
        self.fakes.script("agy", default={"kind": "text", "text": "fine"})
        for name, prompt in prompts.items():
            with self.subTest(name):
                self.assertEqual(len(prompt.encode("utf-8")), 185_000)
                with self.assertRaises(engines.PromptTooLong) as cm:
                    self.agy()(prompt, self.cwd())
                self.assertIn("185000-byte prompt", str(cm.exception))
                self.assertIn("180000", str(cm.exception))
                self.assertNotIn("300 KB", str(cm.exception))
                self.assertEqual(self.fakes.calls("agy"), [])

    def test_the_limit_is_on_the_prompts_bytes_not_on_the_serialised_message(self):
        """CJK text is 3 bytes a character and the message adds its own escapes, so the line's size and the text's
        size differ either way; agy's cut follows the text. 150,000 bytes of CJK is carried (it is half the limit
        in characters but the same in bytes), and so is a prompt whose message is over 200,000 bytes only because
        of the quotes the message escapes."""
        self.fakes.script("agy", default={"kind": "text", "text": "fine"})
        quoted = '""\u4e2d' * 30_000
        prompts = {"CJK": "\u4e2d" * 50_000, "escaped quotes": quoted}
        for name, prompt in prompts.items():
            with self.subTest(name):
                self.assertEqual(len(prompt.encode("utf-8")), 150_000)
                self.assertEqual(self.agy()(prompt, self.cwd())[0], "fine")
        line = json.dumps({"event": "user", "message": {"role": "user", "content": quoted}}, ensure_ascii=False)
        self.assertGreater(len(line.encode("utf-8")), 200_000, "the case no longer tests the serialised size")

    def test_the_limit_is_180000_bytes_of_the_prompt_to_the_byte(self):
        self.assertEqual(engines.AGY_MAX_PROMPT_BYTES, 180_000)
        self.fakes.script("agy", default={"kind": "text", "text": "fine"})
        self.assertEqual(self.agy()("a" * 180_000, self.cwd())[0], "fine")
        with self.assertRaises(engines.PromptTooLong):
            self.agy()("a" * 180_001, self.cwd())
        self.assertEqual(len(self.fakes.calls("agy")), 1)

    def tool_step(self, command, state="DONE"):
        """A tool step in the shape agy 1.2.16 streams (the capture under tests/fixtures/agy)."""
        return {"event": "step_update", "step_update": {"conversation_id": "c-1", "step_index": 2, "state": state,
                                                        "step_type": "tool", "tool_name": "run_command",
                                                        "tool_info": {"name": "run_command",
                                                                      "parameters": {"CommandLine": command}}}}

    def cut_stream(self, **reply):
        """What agy streams when it cut the message and the model went for the stored full copy: a step that names
        transcript_full.jsonl, then a successful result that carries a refused `command`. The two are on different
        lines."""
        read = ("tail -c 1000 /Users/example/.gemini/antigravity-cli/brain/c-1/.system_generated/logs/"
                "transcript_full.jsonl")
        base = {"kind": "empty", "events": [self.tool_step(read, "ACTIVE"), self.tool_step(read)],
                "denied": [{"action": "command", "display_name": "RunCommand"}]}
        base.update(reply)
        return base

    def test_the_real_stream_of_a_cut_prompt_is_a_cut(self):
        """Replayed byte for byte from agy 1.2.16, which cut a 250,260-byte synthetic prompt whose question needs the
        end of it: the model's tool steps name transcript_full.jsonl (twice, ACTIVE then DONE) and only the final
        result carries the refused `command`, so the evidence has to be put together across the stream."""
        self.fakes.script("agy", default={"kind": "replay", "stdout": CUT_STREAM, "stderr": CUT_STDERR})
        for reads in (False, True):
            with self.subTest(allow_reads=reads):
                with self.assertRaises(engines.PromptCut) as cm:
                    self.agy(allow_reads=reads)("hello", self.cwd())
                self.assertIn("transcript_full.jsonl", str(cm.exception))
        self.assertEqual(len(self.fakes.calls("agy")), 2, "the capture was not run through the adapter")

    def test_in_the_real_stream_the_two_halves_of_the_evidence_are_on_different_lines(self):
        """What the test above depends on, stated: a check that wanted the file name and the denial on one line would
        never fire on a real stream."""
        with open(CUT_STREAM, encoding="utf-8") as f:
            events = [json.loads(line) for line in f]
        names = [i for i, ev in enumerate(events) if "transcript_full.jsonl" in json.dumps(ev)]
        refused = [i for i, ev in enumerate(events) if any("command" in engines.words(d.get("action"))
                                                           for d in (ev.get("result") or {}).get("denied_actions", []))]
        self.assertEqual(len(names), 2)
        self.assertEqual(len(refused), 1)
        self.assertEqual(set(names) & set(refused), set())
        self.assertEqual({events[i]["step_update"]["step_type"] for i in names}, {"tool"})
        self.assertEqual(events[refused[0]]["event"], "result")
        seen = engines.tool_events([json.dumps(ev) for ev in events])
        self.assertEqual([(e.label, e.names) for e in seen], [("run_command", frozenset({"run_command"}))] * 2,
                         "both states of the one tool step")
        self.assertEqual([e.params[0]["CommandLine"].endswith("transcript_full.jsonl | tail -c 1000") for e in seen],
                         [True, True])

    def test_the_captured_streams_hold_only_redacted_paths_and_ids(self):
        """The captures are in a public repository: nothing in them may name a person, a machine or a conversation."""
        folder = os.path.dirname(CUT_STREAM)
        names = sorted(os.listdir(folder))
        self.assertGreaterEqual(len(names), 4, names)
        for name in names:
            with self.subTest(name):
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    text = f.read()
                self.assertLessEqual(set(re.findall(r"/(?:Users|home)/[^/\\\"]+", text)), {"/Users/example"})
                ids = set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text))
                self.assertLessEqual(ids, {"00000000-0000-0000-0000-000000000000"})
                self.assertEqual(set(re.findall(r"\S+@\S+", text)), set())

    def test_a_stream_that_shows_the_stored_copy_being_read_means_the_prompt_was_cut(self):
        cases = {
            "an empty answer, the usual cut": {},
            "an answer beside the refused command": {"kind": "text", "text": '{"items": []}'},
        }
        for name, reply in cases.items():
            for reads in (False, True):
                with self.subTest(name, allow_reads=reads):
                    self.fakes.reset("agy")
                    self.fakes.script("agy", default=self.cut_stream(**reply))
                    with self.assertRaises(engines.PromptTooLong) as cm:
                        self.agy(allow_reads=reads)("hello", self.cwd())
                    self.assertIn("transcript_full.jsonl", str(cm.exception))
                    self.assertIn("cut", str(cm.exception))
                    self.assertNotIsInstance(cm.exception, (engines.DegenerateError, engines.ToolUseError))

    def test_the_stored_copy_alone_or_a_refused_command_alone_is_not_a_cut(self):
        """Each half is only evidence together: a refused command is a stray tool attempt, and a step that names the
        file with nothing refused is read as the tool step it is: a failure in both lanes, since the tool it names runs
        a command, but not a cut."""
        named_only = {"kind": "text", "text": "fine", "events": self.cut_stream()["events"]}
        command_only = {"kind": "empty", "denied": [{"action": "command", "display_name": "RunCommand"}],
                        "events": [self.tool_step("ls")]}
        other_denial = self.cut_stream(denied=[{"action": "write_file"}])
        not_a_list = self.cut_stream(denied=True)
        self.fakes.script("agy", default=named_only)
        for reads in (False, True):
            with self.subTest("the stored copy, nothing refused", allow_reads=reads):
                with self.assertRaises(engines.ToolUseError) as cm:
                    self.agy(allow_reads=reads)("hello", self.cwd())
                self.assertNotIsInstance(cm.exception, engines.PromptTooLong)
        for name, reply, want in (("a refused command, no stored copy", command_only, engines.DegenerateError),
                                  ("the stored copy and another denial", other_denial, engines.DegenerateError),
                                  ("the stored copy and a denial that is not a list", not_a_list,
                                   engines.DegenerateError)):
            with self.subTest(name):
                self.fakes.reset("agy")
                self.fakes.script("agy", default=reply)
                with self.assertRaises(want) as cm:
                    self.agy()("hello", self.cwd())
                self.assertNotIsInstance(cm.exception, engines.PromptTooLong)

    def test_a_denied_action_fails_even_with_an_answer(self):
        self.fakes.script("agy", default={"kind": "text", "text": '{"items": []}', "denied": ["write_file plan.md"]})
        with self.assertRaises(engines.ToolUseError) as cm:
            self.agy()("hello", self.cwd())
        self.assertIn("write_file", str(cm.exception))

    def test_an_empty_answer_is_degenerate(self):
        cases = {
            "empty": {"kind": "empty"},
            "blank": {"kind": "text", "text": "  \n "},
            "usage digits that look like a status code": {"kind": "empty",
                                                          "usage": {"input_tokens": 14290, "output_tokens": 429}},
            "after a denied tool attempt": {"kind": "empty", "denied": ["run_command ls"]},
        }
        for name, reply in cases.items():
            with self.subTest(name):
                self.fakes.reset("agy")
                self.fakes.script("agy", default=reply)
                with self.assertRaises(engines.DegenerateError) as cm:
                    self.agy()("hello", self.cwd())
                self.assertNotIsInstance(cm.exception, engines.QuotaError)
        self.assertIn("run_command", str(cm.exception))

    def test_quota_whatever_the_exit_code(self):
        cases = {
            "exit 0, no result": ({"kind": "quota", "rc": 0,
                                   "message": "RESOURCE_EXHAUSTED: Quota exceeded. Resets in 1h2m3s"}, 3723),
            "exit 1, no result": ({"kind": "quota", "rc": 1,
                                   "message": "RESOURCE_EXHAUSTED: Quota exceeded. Resets in 1h2m3s"}, 3723),
            "an error result, exit 0": ({"kind": "quota", "rc": 0, "message": "",
                                         "result_error": "Quota exhausted for this model"}, None),
            "an empty answer with quota text, exit 0": ({"kind": "empty", "rc": 0,
                                                         "stderr": "429 Too Many Requests. Resets in 45s"}, 45),
        }
        for name, (reply, reset) in cases.items():
            with self.subTest(name):
                self.fakes.script("agy", default=reply)
                with self.assertRaises(engines.QuotaError) as cm:
                    self.agy()("hello", self.cwd())
                self.assertEqual(cm.exception.reset_seconds, reset)

    def test_another_failure_is_a_plain_engine_error(self):
        self.fakes.script("agy", default={"kind": "fail", "rc": 3, "message": "model not available"})
        with self.assertRaises(engines.EngineError) as cm:
            self.agy()("hello", self.cwd())
        self.assertNotIsInstance(cm.exception, (engines.QuotaError, engines.DegenerateError, engines.ToolUseError))
        self.assertIn("rc=3", str(cm.exception))

    def test_timeout_kills_the_whole_process_group(self):
        self.fakes.script("agy", default={"kind": "sleep", "seconds": 8})
        t0 = time.time()
        with self.assertRaisesRegex(engines.EngineError, "timeout"):
            self.agy(timeout=2)("hello", self.cwd())
        self.assertLess(time.time() - t0, 7)
        time.sleep(0.3)
        first = self.fakes.heartbeat("agy")
        self.assertIsNotNone(first, "the fake's child never started")
        time.sleep(0.6)
        self.assertEqual(self.fakes.heartbeat("agy"), first, "a child of the engine outlived the timeout")

    def test_a_descendant_that_leaves_the_group_cannot_hang_the_timeout(self):
        """A grandchild that calls setsid() survives the group kill and holds the pipes; the wait after the kill is
        bounded by KILL_GRACE (patched from 5 to 1 second to keep the test short)."""
        self.assertEqual(engines.KILL_GRACE, 5)
        self.fakes.script("agy", default={"kind": "hold", "hold": 30, "seconds": 25})
        self.addCleanup(self.kill_holder)
        t0 = time.time()
        with mock.patch.object(engines, "KILL_GRACE", 1):
            with self.assertRaisesRegex(engines.EngineError, "timeout"):
                self.agy(timeout=2)("hello", self.cwd())  # 2 s: time enough for the holder to start first
        # timeout + grace + slack; without the bound the call lasts as long as the grandchild (30 s)
        self.assertLess(time.time() - t0, 2 + 1 + 6, "the wait after the kill was not bounded")
        self.assertIsNotNone(self.fakes.read_state("agy", "holder.pid"), "the pipe-holding grandchild never started")

    def kill_holder(self):
        pid = self.fakes.read_state("agy", "holder.pid")
        if pid:
            try:
                os.kill(int(pid), signal.SIGKILL)
            except OSError:
                pass

    def test_tool_events_fail_unless_reads_are_allowed(self):
        """The shapes before the real one was known (top-level keys and types): every one fails the cards lane, and
        the vision lane accepts only one that names a read tool."""
        cases = {
            "a tool call event": ([{"event": "tool_call", "name": "view_file", "args": {"path": "p1.png"}}], True),
            "a tool call event that runs a command": ([{"event": "tool_call", "name": "run_command"}], False),
            "a top-level key naming a function, camelCase": ([{"event": "message", "functionCall": {"name": "x"}}],
                                                             False),
            "a non-empty tool_calls list": ([{"event": "message", "tool_calls": [{"name": "run"}]}], False),
            "an action type": ([{"event": "step", "type": "action", "detail": "open"}], False),
            "a top-level call id": ([{"event": "message", "call_id": "c1"}], False),
        }
        for name, (events, read) in cases.items():
            with self.subTest(name):
                self.fakes.script("agy", default={"kind": "text", "text": '{"pages": []}', "events": events})
                with self.assertRaises(engines.ToolUseError):
                    self.agy()("hello", self.cwd())
                if read:
                    self.assertEqual(self.agy(allow_reads=True)("hello", self.cwd())[0], '{"pages": []}')
                else:
                    with self.assertRaises(engines.ToolUseError):
                        self.agy(allow_reads=True)("hello", self.cwd())

    def real_stream(self, tool=None, response='{"pages": []}', denied=None, **params):
        """The real capture's events (the init banner, the user and agent steps), with its tool step swapped for
        another tool (allowed, ACTIVE then DONE, none when `tool` is None) and its result made the given answer.
        Returns a reply for the fake engine to replay."""
        with open(CUT_STREAM, encoding="utf-8") as f:
            events = [json.loads(line) for line in f]
        head, steps, result = events[:3], events[3:5], events[5]
        for step in steps:
            step["step_update"]["tool_name"] = tool
            step["step_update"]["tool_info"] = {"name": tool, "parameters": params}
        result["result"]["response"] = response
        result["result"].pop("denied_actions")
        if denied:
            result["result"]["denied_actions"] = denied
        return self.replay_of(head + (steps if tool else []) + [result])

    def replay_of(self, events):
        """A reply for the fake engine that replays `events` (dicts) as agy's stream, with an empty stderr."""
        stdout, stderr = os.path.join(self.tmp, "stream.jsonl"), os.path.join(self.tmp, "stderr.txt")
        with open(stdout, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(ev) + "\n" for ev in events))
        with open(stderr, "w", encoding="utf-8") as f:
            f.write("")
        return {"kind": "replay", "stdout": stdout, "stderr": stderr}

    def capture_events(self):
        with open(CUT_STREAM, encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def test_a_tool_step_in_the_real_shape_discards_the_reply_unless_the_vision_lane_reads(self):
        """agy 1.2.16 streams a tool as `step_update` with `step_type: "tool"`, a `tool_name` and a `tool_info`, not as
        a top-level tool event. An allowed one (DONE, nothing refused, an answer) still discards the reply in the
        cards lane; the vision lane accepts only the steps that read the call's own folder."""
        cwd = self.cwd()
        reading = {"view_file": {"AbsolutePath": os.path.join(cwd, "p1.png")}, "list_dir": {"DirectoryPath": cwd},
                   "find_by_name": {"SearchDirectory": cwd, "Pattern": "*.png"}}
        other = {"run_command": {"CommandLine": "ls " + cwd}, "write_to_file": {"TargetFile": os.path.join(cwd, "x")},
                 "read_url_content": {"Url": "https://example.invalid/"}, "search_web": {"query": "x"}}
        for tool, params in {**reading, **other}.items():
            with self.subTest(tool):
                self.fakes.script("agy", default=self.real_stream(tool, **params))
                with self.assertRaises(engines.ToolUseError) as cm:
                    self.agy()("hello", cwd)
                self.assertIn(tool, str(cm.exception))
                if tool in reading:
                    self.assertEqual(self.agy(allow_reads=True)("hello", cwd)[0], '{"pages": []}')
                else:
                    with self.assertRaises(engines.ToolUseError) as cm:
                        self.agy(allow_reads=True)("hello", cwd)
                    self.assertIn(tool, str(cm.exception))

    def test_a_step_that_is_not_a_plain_one_is_a_tool_step_whatever_its_keys(self):
        """Only `step_type: "tool"` has been captured, so the rule is the other way round: a step is plain when it is
        a user_input, an agent_response or agy's own system_message, and any other step type, or none, is a tool at
        work, even with no tool_name and no tool_info. In the vision lane it can only be an unnamed tool, which is
        never a read."""
        base = {"conversation_id": "c-1", "step_index": 2, "state": "DONE"}
        shapes = {"run_command": {"step_type": "run_command"}, "command": {"step_type": "command"},
                  "view_file": {"step_type": "view_file"}, "browser_subagent": {"step_type": "browser_subagent"},
                  "toolcall": {"step_type": "toolcall"}, "an unseen word": {"step_type": "planner_response"},
                  "an empty type": {"step_type": ""}, "no type": {}, "an ERROR state": {"step_type": "tool",
                                                                                        "state": "ERROR"}}
        for name, extra in shapes.items():
            for reads in (False, True):
                with self.subTest(name, allow_reads=reads):
                    step = {"event": "step_update", "step_update": dict(base, **extra)}
                    self.fakes.script("agy", default=self.replay_of(
                        self.capture_events()[:3] + [step, self.real_result()]))
                    with self.assertRaises(engines.ToolUseError):
                        self.agy(allow_reads=reads)("hello", self.cwd())
        with self.subTest("a step update that is not an object"):
            events = self.capture_events()[:3] + [{"event": "step_update", "step_update": "run_command"}]
            self.fakes.script("agy", default=self.replay_of(events + [self.real_result()]))
            with self.assertRaises(engines.ToolUseError):
                self.agy()("hello", self.cwd())

    def test_the_plain_steps_of_a_real_stream_are_not_tools(self):
        """user_input and agent_response are in the capture; system_message is agy's own note, seen in a long run
        between tool steps, with nothing but a duration."""
        events = self.capture_events()
        note = {"event": "step_update", "step_update": {"conversation_id": "00000000-0000-0000-0000-000000000000",
                                                        "step_index": 3, "state": "DONE", "step_type": "system_message",
                                                        "duration_seconds": 0.000138}}
        self.fakes.script("agy", default=self.replay_of(events[:3] + [note] + [self.real_result()]))
        for reads in (False, True):
            with self.subTest(allow_reads=reads):
                self.assertEqual(self.agy(allow_reads=reads)("hello", self.cwd())[0], '{"pages": []}')

    def real_result(self, response='{"pages": []}'):
        result = self.capture_events()[5]
        result["result"]["response"] = response
        result["result"].pop("denied_actions")
        return result

    def test_the_vision_lane_reads_only_inside_the_calls_own_folder(self):
        """A read tool is accepted only when every path it names resolves inside the working folder: an absolute path
        elsewhere (the real probes read /private/etc/hosts), `..`, `~`, a file URL, and a link inside the folder that
        points out all fail, and so does a path in a parameter that names a directory or a pattern."""
        cwd = self.cwd()
        outside = os.path.join(self.tmp, "outside.png")
        with open(outside, "w") as f:
            f.write("x")
        os.symlink(outside, os.path.join(cwd, "link.png"))
        os.symlink(cwd, os.path.join(self.tmp, "alias"))
        inside = {
            "relative": ("view_file", {"AbsolutePath": "p1.png"}),
            "absolute": ("view_file", {"AbsolutePath": os.path.join(cwd, "p1.png")}),
            "through an alias of the folder": ("view_file", {"AbsolutePath": os.path.join(self.tmp, "alias",
                                                                                           "p1.png")}),
            "dot-dot that comes back": ("view_file", {"AbsolutePath": os.path.join(cwd, "..", os.path.basename(cwd),
                                                                                     "p1.png")}),
            "the folder itself": ("list_dir", {"DirectoryPath": cwd}),
            "a search under it": ("find_by_name", {"SearchDirectory": ".", "Pattern": "*.png"}),
        }
        elsewhere = {
            "an absolute path elsewhere": ("view_file", {"AbsolutePath": "/private/etc/hosts"}),
            "a sibling folder": ("view_file", {"AbsolutePath": outside}),
            "dot-dot out": ("view_file", {"AbsolutePath": os.path.join(cwd, "..", "outside.png")}),
            "relative dot-dot out": ("view_file", {"AbsolutePath": "../outside.png"}),
            "home": ("view_file", {"AbsolutePath": "~/p1.png"}),
            "a file URL": ("view_file", {"AbsolutePath": "file:///private/etc/hosts"}),
            "a link inside that points out": ("view_file", {"AbsolutePath": os.path.join(cwd, "link.png")}),
            "the parent folder": ("list_dir", {"DirectoryPath": os.path.dirname(cwd)}),
            "the root": ("list_dir", {"DirectoryPath": "/"}),
            "a search elsewhere": ("find_by_name", {"SearchDirectory": "/Users", "Pattern": "*.png"}),
            "a pattern that is a path": ("find_by_name", {"SearchDirectory": cwd, "Pattern": "/private/etc/*"}),
            "a path under an unfamiliar name": ("view_file", {"Source": "/private/etc/hosts"}),
            "a list of paths with one elsewhere": ("view_file", {"Paths": [os.path.join(cwd, "p1.png"),
                                                                           "/private/etc/hosts"]}),
        }
        for name, (tool, params) in inside.items():
            with self.subTest(name):
                self.fakes.script("agy", default=self.real_stream(tool, **params))
                self.assertEqual(self.agy(allow_reads=True)("hello", cwd)[0], '{"pages": []}')
        for name, (tool, params) in elsewhere.items():
            with self.subTest(name):
                self.fakes.script("agy", default=self.real_stream(tool, **params))
                with self.assertRaises(engines.ToolUseError) as cm:
                    self.agy(allow_reads=True)("hello", cwd)
                self.assertIn("outside the call's folder", str(cm.exception))
                with self.assertRaises(engines.ToolUseError):
                    self.agy()("hello", cwd)

    def test_a_read_cannot_name_something_outside_the_folder_by_any_key_or_spelling(self):
        """The path guard does not rest on a parameter's name or on a value looking like a path: a file URL is parsed
        (`file:/x`, a `localhost` host, escapes decoded, `..` resolved), and any string, under any key and at any depth,
        that names something that exists in the folder is judged by where it really leads, links resolved. A string
        that names nothing is not a path, and one that cannot be judged is refused."""
        cwd = self.cwd()
        enc = lambda p: p.replace("/", "%2F")  # noqa: E731
        outside_file = os.path.join(self.tmp, "outside.png")
        outside_dir = os.path.join(self.tmp, "outside_dir")
        os.makedirs(outside_dir)
        for target in (outside_file, os.path.join(outside_dir, "hosts")):
            with open(target, "w") as f:
                f.write("x")
        os.symlink(outside_dir, os.path.join(cwd, "portal"))
        os.symlink(outside_file, os.path.join(cwd, "shortcut"))
        os.makedirs(os.path.join(cwd, "pages"))
        with open(os.path.join(cwd, "p1.png"), "w") as f:
            f.write("x")
        refused = {
            "file: with one slash": {"AbsolutePath": "file:/private/etc/hosts"},
            "file: with localhost": {"Mystery": "file://localhost/private/etc/hosts"},
            "file: with LOCALHOST and a capital scheme": {"Mystery": "FILE://LocalHost/private/etc/hosts"},
            "file: with another host": {"Mystery": "file://example.invalid/private/etc/hosts"},
            "file: with an escaped host": {"Mystery": "file://%6Cocalhost/private/etc/hosts"},
            "file: with an unquoted ..": {"Mystery": "file://" + cwd + "/../outside.png"},
            "file: with a relative ..": {"Mystery": "file:../outside.png"},
            "file: with an encoded slash": {"Mystery": "file:" + enc(cwd) + "%2F..%2Foutside.png"},
            "file: with an encoded slash and dots": {"Mystery": "file://" + enc(cwd + "/../outside.png")},
            "file: with an encoded slash even where it leads inside": {"Mystery": "file:" + enc(cwd) + "%2Fp1.png"},
            "file: with a doubly encoded ..": {"Mystery": "file://" + cwd + "/%252e%252e/outside.png"},
            "file: with a NUL": {"Mystery": "file://" + cwd + "/p1.png%00"},
            "a bare word that is a link to a folder": {"Mystery": "portal"},
            "a bare word that is a link to a file": {"Mystery": "shortcut"},
            "a link's folder with a name under it": {"Mystery": "portal/hosts"},
            "a link's folder, deep in a list": {"Options": [{"Name": "x"}, {"More": ["portal"]}]},
            "a link under a key that names no path": {"Query": "shortcut"},
            "a URL of another scheme": {"Mystery": "https://example.invalid/hosts"},
            "an ftp URL": {"Mystery": "ftp://example.invalid/hosts"},
            "a data URL": {"Mystery": "data:text/plain,hello"},
            "a one-letter drive": {"Mystery": "C:\\Windows\\win.ini"},
        }
        accepted = {
            "a file that exists in the folder, by a bare word": {"Mystery": "p1.png"},
            "a folder in it, by a bare word": {"Mystery": "pages"},
            "a file URL inside it": {"Mystery": "file://" + cwd + "/p1.png"},
            "a file URL inside it, with one slash": {"AbsolutePath": "file:" + cwd + "/p1.png"},
            "a file URL inside it, with an escaped space": {"Mystery": "file://" + cwd + "/a%20b.png"},
            "a file URL inside it, with localhost": {"Mystery": "file://localhost" + cwd + "/p1.png"},
            "a word that names nothing": {"Mystery": "transcribe"},
            "a sentence with a colon": {"Note": "images only: no text"},
            "a number and a boolean": {"MaxDepth": 2, "Recursive": False},
        }
        for name, params in refused.items():
            with self.subTest(name):
                self.fakes.script("agy", default=self.real_stream("view_file", **params))
                with self.assertRaises(engines.ToolUseError) as cm:
                    self.agy(allow_reads=True)("hello", cwd)
                self.assertIn("outside the call's folder", str(cm.exception))
        for name, params in accepted.items():
            with self.subTest(name):
                self.fakes.script("agy", default=self.real_stream("view_file", **params))
                self.assertEqual(self.agy(allow_reads=True)("hello", cwd)[0], '{"pages": []}')

    def test_a_read_that_names_no_parameters_cannot_be_checked_and_is_refused(self):
        events = self.capture_events()[:3]
        step = {"event": "step_update", "step_update": {"conversation_id": "c", "step_index": 2, "state": "DONE",
                                                        "step_type": "tool", "tool_name": "view_file"}}
        self.fakes.script("agy", default=self.replay_of(events + [step, self.real_result()]))
        with self.assertRaises(engines.ToolUseError):
            self.agy(allow_reads=True)("hello", self.cwd())

    def test_a_real_tool_step_with_no_name_is_not_a_read(self):
        reply = self.real_stream("view_file")
        with open(reply["stdout"], encoding="utf-8") as f:
            events = [json.loads(line) for line in f]
        for ev in events:
            step = ev.get("step_update", {})
            if step.get("step_type") == "tool":
                del step["tool_name"], step["tool_info"]["name"]
        with open(reply["stdout"], "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(ev) + "\n" for ev in events))
        self.fakes.script("agy", default=reply)
        with self.assertRaises(engines.ToolUseError):
            self.agy(allow_reads=True)("hello", self.cwd())

    def test_a_read_tool_beside_another_tool_is_not_a_read(self):
        cwd = self.cwd()
        reply = self.real_stream("view_file", AbsolutePath=os.path.join(cwd, "p1.png"))
        with open(reply["stdout"], encoding="utf-8") as f:
            events = [json.loads(line) for line in f]
        stray = json.loads(json.dumps(events[3]))
        stray["step_update"].update(step_index=3, tool_name="run_command")
        stray["step_update"]["tool_info"]["name"] = "run_command"
        events.insert(5, stray)
        with open(reply["stdout"], "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(ev) + "\n" for ev in events))
        self.fakes.script("agy", default=reply)
        with self.assertRaises(engines.ToolUseError) as cm:
            self.agy(allow_reads=True)("hello", cwd)
        self.assertIn("run_command", str(cm.exception))

    def test_the_init_banner_and_the_ordinary_steps_of_a_real_stream_are_not_tools(self):
        """The banner lists every tool agy has, and the user and agent steps carry usage: none of it is a tool at
        work."""
        self.fakes.script("agy", default=self.real_stream(None))
        for reads in (False, True):
            with self.subTest(allow_reads=reads):
                self.assertEqual(self.agy(allow_reads=reads)("hello", self.cwd())[0], '{"pages": []}')

    def test_a_cut_is_named_before_the_tool_steps_that_show_it(self):
        """The real cut stream is full of tool steps, which would fail the call as tool use; the cut is the cause, so it
        is named first and the caller halves the input, with or without an answer beside the refused command."""
        for response in ("", '{"pages": []}'):
            for reads in (False, True):
                with self.subTest(response=response, allow_reads=reads):
                    read = "tail /h/brain/c-1/.system_generated/logs/transcript_full.jsonl"
                    reply = self.real_stream("run_command", response=response, CommandLine=read,
                                             denied=[{"action": "command", "display_name": "RunCommand"}])
                    self.fakes.script("agy", default=reply)
                    with self.assertRaises(engines.PromptCut):
                        self.agy(allow_reads=reads)("hello", self.cwd())

    def test_ordinary_events_are_not_tools(self):
        cases = {
            "free text naming a call": {"event": "thought", "text": "call me later"},
            "an empty tool_calls list": {"event": "message", "tool_calls": []},
            "a nested call id": {"event": "message", "message": {"call_id": "c1", "content": "x"}},
            "interaction_start": {"event": "interaction_start", "interaction_start": "now"},
            "locally": {"event": "message", "locally": True},
            "redaction": {"event": "message", "redaction": "none"},
        }
        for name, event in cases.items():
            with self.subTest(name):
                self.fakes.script("agy", default={"kind": "text", "text": "fine", "events": [event]})
                self.assertEqual(self.agy()("hello", self.cwd())[0], "fine")

    def test_quota_is_checked_before_tool_events(self):
        for rc in (0, 1):
            with self.subTest(rc=rc):
                self.fakes.script("agy", default={"kind": "quota", "rc": rc, "message": "429 Too Many Requests",
                                                  "events": [{"event": "tool_call", "tool_calls": [{"id": 1}]}]})
                with self.assertRaises(engines.QuotaError):
                    self.agy()("hello", self.cwd())

    def test_failures_that_only_look_like_quota(self):
        for message in ("request 14290 failed", "quotation marks unbalanced", "quota_project_id is not set",
                        "exhaustive search failed", "accurate limit reached"):
            with self.subTest(message):
                self.fakes.script("agy", default={"kind": "fail", "rc": 1, "message": message})
                with self.assertRaises(engines.EngineError) as cm:
                    self.agy()("hello", self.cwd())
                self.assertNotIsInstance(cm.exception, engines.QuotaError)

    def test_output_that_is_not_utf8(self):
        self.fakes.script("agy", default={"kind": "text", "text": "fine", "bad_bytes": True})
        self.assertEqual(self.agy()("hello", self.cwd())[0], "fine")


class CodexTest(FakeEngineCase):
    def test_argv_stdin_environment_and_folder(self):
        self.fakes.script("codex", default={"kind": "text", "text": '{"items": []}'})
        cwd = self.cwd()
        reply, usage = self.codex(effort="high", state_home=self.state)(PROMPT, cwd, schema=CODEX_SCHEMA)
        self.assertEqual(reply, '{"items": []}')
        self.assertEqual(usage, {"input_tokens": 100, "output_tokens": 20})
        call = self.only_call("codex")
        expected = ["exec", "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral", "--ignore-user-config",
                    "--ignore-rules", "--json", "-C", cwd, "-o", os.path.join(cwd, "last_%d.txt" % os.getpid()),
                    "-c", 'web_search="disabled"', "-c", 'model_reasoning_effort="high"',
                    "-c", 'approval_policy="never"']
        for feature in CODEX_OFF:
            expected += ["--disable", feature]
        expected += ["-m", "fake-model", "--output-schema", CODEX_SCHEMA, "-"]
        self.assertEqual(call["argv"][1:], expected)
        self.assertEqual(call["stdin"], PROMPT)
        self.assertEqual(os.path.realpath(call["cwd"]), cwd)
        self.assertEqual(call["cwd_listing"], [])
        self.assertEqual(os.listdir(cwd), [], "the reply file was left in the working folder")
        self.assert_own_group(call)
        self.assert_no_secrets(call)
        own = sorted(k for k in call["env"] if not k.startswith(("__", "LC_")))  # what the OS or Python may add
        self.assertEqual(own, ["CODEX_HOME", "HOME", "LANG", "PATH", "TMPDIR"])
        self.assertEqual(call["env"]["CODEX_HOME"], self.state)
        self.assertEqual(call["env"]["HOME"], self.env["HOME"])

    def test_defaults_and_per_call_overrides(self):
        self.fakes.script("codex", default={"kind": "text", "text": "fine"})
        engines.Codex(binary=self.fakes.path("codex"))("hello", self.cwd())
        engines.Codex(binary=self.fakes.path("codex"))("hello", self.cwd(), model="m2", effort="low")
        first, second = self.fakes.calls("codex")
        self.assertIn('model_reasoning_effort="medium"', first["argv"])
        self.assertNotIn("-m", first["argv"])
        self.assertNotIn("--output-schema", first["argv"])
        self.assertNotIn("CODEX_HOME", first["env"])
        self.assertIn('model_reasoning_effort="low"', second["argv"])
        self.assertEqual(second["argv"][second["argv"].index("-m") + 1], "m2")

    def test_the_card_schema_is_strict(self):
        with open(CODEX_SCHEMA, encoding="utf-8") as f:
            self.assertEqual(strict_problems(json.load(f)), [])

    def test_a_schema_that_is_not_strict_is_refused_before_the_call(self):
        with open(CARD_SCHEMA, encoding="utf-8") as f:
            self.assertNotEqual(strict_problems(json.load(f)), [])
        with self.assertRaisesRegex(common.ToolError, "not strict"):
            self.codex()("hello", self.cwd(), schema=CARD_SCHEMA)
        self.assertEqual(self.fakes.calls("codex"), [])

    def test_any_tool_item_fails_the_call(self):
        for item in ("command_execution", "file_change", "mcp_tool_call", "web_search", "todo_list"):
            with self.subTest(item):
                self.fakes.script("codex", default={"kind": "tool", "item": item, "text": '{"items": []}'})
                with self.assertRaises(engines.ToolUseError) as cm:
                    self.codex()("hello", self.cwd())
                self.assertIn(item, str(cm.exception))

    def test_an_empty_answer_is_degenerate_only_on_a_clean_exit(self):
        self.fakes.script("codex", default={"kind": "empty"})
        with self.assertRaises(engines.DegenerateError):
            self.codex()("hello", self.cwd())
        self.fakes.script("codex", default={"kind": "fail", "rc": 1, "message": "stream disconnected"})
        with self.assertRaises(engines.EngineError) as cm:
            self.codex()("hello", self.cwd())
        self.assertNotIsInstance(cm.exception, (engines.DegenerateError, engines.QuotaError))

    def test_quota_whatever_the_exit_code(self):
        self.fakes.script("codex", default={"kind": "quota", "rc": 0,
                                            "message": "You've hit your usage limit. Try again at 5:12 PM."})
        with self.assertRaises(engines.QuotaError) as cm:
            self.codex()("hello", self.cwd())
        self.assertIsInstance(cm.exception.reset_seconds, int)
        self.assertTrue(0 <= cm.exception.reset_seconds <= 86400, cm.exception.reset_seconds)
        self.fakes.script("codex", default={"kind": "quota", "rc": 1,
                                            "message": "429 Too Many Requests: rate limit. Resets in 2h13m5s"})
        with self.assertRaises(engines.QuotaError) as cm:
            self.codex()("hello", self.cwd())
        self.assertEqual(cm.exception.reset_seconds, 2 * 3600 + 13 * 60 + 5)

    def test_failures_that_only_look_like_quota(self):
        for message in ("request 14290 failed", "quotation marks unbalanced", "quota_project_id is not set",
                        "exhaustive search failed"):
            with self.subTest(message):
                self.fakes.script("codex", default={"kind": "fail", "rc": 1, "message": message})
                with self.assertRaises(engines.EngineError) as cm:
                    self.codex()("hello", self.cwd())
                self.assertNotIsInstance(cm.exception, engines.QuotaError)

    def test_output_that_is_not_utf8(self):
        self.fakes.script("codex", default={"kind": "text", "text": "fine", "bad_bytes": True})
        reply, _usage = self.codex()("hello", self.cwd())
        self.assertEqual(reply, "fine �")


class CredentialGuardTest(FakeEngineCase):
    """The per-project state folder may reach the one login (a symlink), never hold a copy of it."""

    def plant(self, rel, text="{}"):
        p = os.path.join(self.state, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def test_a_credential_file_before_the_call_stops_the_run(self):
        for rel in ("auth.json", os.path.join(".gemini", "oauth_creds.json"), "access_token.txt", "credentials.db"):
            with self.subTest(rel):
                shutil.rmtree(self.state)
                self.plant(rel)
                for make in (self.agy, self.codex):
                    with self.assertRaises(engines.EngineError) as cm:
                        make(state_home=self.state)("hello", self.cwd())
                    self.assertIsInstance(cm.exception, common.ToolError, "a credential file must stop the run")
                    self.assertIn(os.path.basename(rel), str(cm.exception))
        self.assertEqual(self.fakes.calls("agy") + self.fakes.calls("codex"), [])

    def test_a_credential_file_written_during_the_call_fails_it(self):
        for engine, make, rel in (("agy", self.agy, os.path.join(".gemini", "oauth_creds.json")),
                                  ("codex", self.codex, "auth.json")):
            with self.subTest(engine):
                shutil.rmtree(self.state)
                os.makedirs(self.state)
                self.fakes.script(engine, default={"kind": "write", "name": rel, "text": '{"items": []}'})
                with self.assertRaises(engines.EngineError) as cm:
                    make(state_home=self.state)("hello", self.cwd())
                self.assertIsInstance(cm.exception, common.ToolError)
                self.assertEqual(len(self.fakes.calls(engine)), 1)

    def test_a_symlink_to_the_login_and_ordinary_state_are_allowed(self):
        login = os.path.join(self.tmp, "elsewhere", "auth.json")
        os.makedirs(os.path.dirname(login))
        with open(login, "w", encoding="utf-8") as f:
            f.write("{}")
        os.symlink(login, os.path.join(self.state, "auth.json"))
        self.plant("history.jsonl", "")
        self.plant(os.path.join("sessions", "2024", "rollout.jsonl"), "")
        self.fakes.script("agy", default={"kind": "text", "text": "fine"})
        self.fakes.script("codex", default={"kind": "text", "text": "fine"})
        self.assertEqual(self.agy(state_home=self.state)("hello", self.cwd())[0], "fine")
        self.assertEqual(self.codex(state_home=self.state)("hello", self.cwd())[0], "fine")


class HelpersTest(unittest.TestCase):
    def test_reset_times(self):
        now = time.mktime((2024, 6, 30, 14, 0, 0, 0, 0, -1))
        cases = {
            "Quota exceeded. Resets in 1h2m3s.": 3723,
            "Resets in 2h13m5s": 7985,
            "Resets in 45m": 2700,
            "Resets in 30s": 30,
            "Usage limit reached; try again at 5:12 PM": 3 * 3600 + 12 * 60,
            "try again at 5:12pm": 3 * 3600 + 12 * 60,
            "Try again at 17:12.": 3 * 3600 + 12 * 60,
            "try again at 9:05 AM": 19 * 3600 + 5 * 60,
            "try again at 12:30 AM": 10 * 3600 + 30 * 60,
            "Try again at 14:00": 0,
            "try again at 2:00 PM": 0,
            "Try again at 13:59": 86400 - 60,
            "Quota exceeded.": None,
            "Resets in a while": None,
        }
        for text, want in cases.items():
            with self.subTest(text):
                self.assertEqual(engines.reset_seconds(text, now=now), want)

    def test_quota_words_are_whole_words(self):
        for text in ("Quota exceeded for this model", "quota exhausted", "RESOURCE_EXHAUSTED", "429 Too Many Requests",
                     "Rate limit reached", "x-ratelimit-remaining: 0", "You've hit your usage limit", "exhausted"):
            with self.subTest(text):
                self.assertIsNotNone(engines.QUOTA_RE.search(text))
        for text in ("quotation", "quota_project_id", "exhaustive", "request 14290 failed", "accurate limit"):
            with self.subTest(text):
                self.assertIsNone(engines.QUOTA_RE.search(text))

    def test_credential_names(self):
        caught = ["auth.json", "oauth_creds.json", "access_token.txt", "credentials.db", ".netrc", "client_secret.json",
                  "secrets.json", "api_key.txt", "apikey", ".env", ".env.local", "prod.env", "id_rsa", "id_ed25519",
                  "password.txt", "keychain.db", "login.keychain-db", "refresh-token", "msal_token_cache.json",
                  "cookies.sqlite", "cookies.json", "tokens.json", "access_tokens.db", "api_keys.txt", "API keys.txt",
                  ".npmrc", ".pgpass", "master.key", "server.key", "cert.pem", "adc.json", "vault.kdbx"]
        ordinary = ["token_usage.json", "tokenizer.json", "oauthflow.md", "credential_types.md", "access_log.txt",
                    "history.jsonl", "rollout-2024.jsonl", "settings.json", "config.toml", "installation_id",
                    "author.txt", "id_rsa.pub", "keyboard.json", "environment.json", "passport.pdf", "hotkeys.json"]
        for name in caught:
            with self.subTest(caught=name):
                self.assertTrue(engines.is_credential_name(name))
        for name in ordinary:
            with self.subTest(ordinary=name):
                self.assertFalse(engines.is_credential_name(name))
        state = tempfile.mkdtemp(prefix="cred_names_")
        self.addCleanup(shutil.rmtree, state, True)
        for i, name in enumerate(caught + ordinary):
            os.makedirs(os.path.join(state, str(i)))
            with open(os.path.join(state, str(i), name), "w", encoding="utf-8") as f:
                f.write("x")
        self.assertEqual(sorted(os.path.basename(p) for p in engines.credential_files(state)), sorted(caught))

    def test_secret_variables(self):
        for name in SECRETS:
            with self.subTest(secret=name):
                self.assertTrue(engines.is_secret_var(name))
        for name in ("PATH", "HOME", "LANG", "TMPDIR", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "SSL_CERT_FILE",
                     "TOKENIZERS_PARALLELISM", "SECRET_SANTA_LIST", "API_KEY_HELP", "ENDPOINT_NOTES"):
            with self.subTest(ordinary=name):
                self.assertFalse(engines.is_secret_var(name))

    def test_fresh_dirs_are_new_and_empty(self):
        a, b = engines.fresh_dir("t_"), engines.fresh_dir("t_")
        self.addCleanup(shutil.rmtree, a, True)
        self.addCleanup(shutil.rmtree, b, True)
        self.assertNotEqual(a, b)
        self.assertEqual((os.listdir(a), os.listdir(b)), ([], []))

    def test_find(self):
        self.assertEqual(engines.find("agy", "/opt/fake/agy"), "/opt/fake/agy")
        empty = tempfile.mkdtemp(prefix="nobin_")
        self.addCleanup(shutil.rmtree, empty, True)
        with mock.patch.dict(os.environ, {"PATH": empty}), mock.patch.object(engines, "SEARCH", []):
            self.assertIsNone(engines.find("agy"))
            with self.assertRaisesRegex(engines.EngineError, "not found"):
                engines.Codex()


if __name__ == "__main__":
    unittest.main()
