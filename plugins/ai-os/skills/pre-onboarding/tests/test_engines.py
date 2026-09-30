"""The engine adapters against fake `agy` and `codex`: the argv, the environment, stdin, the working folder, the process
group, tool and denial rejection, quota, degenerate replies and the credential guard.

The flags pinned here are the ones in use today; the isolation spike (issue #91) may change them, and then these
tests change with them, deliberately.

    python3 -m unittest discover plugins/ai-os/skills/pre-onboarding/tests
"""
import json
import os
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
        self.assertEqual(call["argv"][1:], ["--json-schema", CARD_SCHEMA, "--input-format", "stream-json",
                                            "--output-format", "stream-json", "--model", "fake-model", "--sandbox",
                                            "--mode", "plan", "-p="])
        self.assertEqual(call["stdin"], json.dumps({"event": "user", "message": {"role": "user", "content": PROMPT}},
                                                   ensure_ascii=False) + "\n")
        self.assertEqual(call["prompt"], PROMPT)
        self.assertEqual(os.path.realpath(call["cwd"]), cwd)
        self.assertEqual(call["cwd_listing"], [])
        self.assert_own_group(call)
        self.assert_no_secrets(call)
        self.assertEqual(call["env"]["HOME"], self.state)
        self.assertEqual(call["env"]["UNRELATED_SETTING"], "kept")
        self.assertTrue(call["env"]["PATH"].startswith(self.env["PATH"] + ":"))

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
        self.fakes.script("agy", default={"kind": "hold", "hold": 20, "seconds": 15})
        self.addCleanup(self.kill_holder)
        t0 = time.time()
        with mock.patch.object(engines, "KILL_GRACE", 1):
            with self.assertRaisesRegex(engines.EngineError, "timeout"):
                self.agy(timeout=1)("hello", self.cwd())
        # timeout + grace + slack; without the bound the call lasts as long as the grandchild (20 s)
        self.assertLess(time.time() - t0, 1 + 1 + 5, "the wait after the kill was not bounded")
        self.assertIsNotNone(self.fakes.read_state("agy", "holder.pid"), "the pipe-holding grandchild never started")

    def kill_holder(self):
        pid = self.fakes.read_state("agy", "holder.pid")
        if pid:
            try:
                os.kill(int(pid), signal.SIGKILL)
            except OSError:
                pass

    def test_tool_events_fail_unless_reads_are_allowed(self):
        cases = {
            "a tool call event": [{"event": "tool_call", "name": "view_file", "args": {"path": "p1.png"}}],
            "a key naming a function, nested": [{"event": "message", "message": {"functionCall": {"name": "x"}}}],
            "an action type": [{"event": "step", "type": "action", "detail": "open"}],
        }
        for name, events in cases.items():
            with self.subTest(name):
                self.fakes.script("agy", default={"kind": "text", "text": '{"pages": []}', "events": events})
                with self.assertRaises(engines.ToolUseError):
                    self.agy()("hello", self.cwd())
                reply, _usage = self.agy(allow_reads=True)("hello", self.cwd())
                self.assertEqual(reply, '{"pages": []}')
        self.fakes.script("agy", default={"kind": "text", "text": "fine",
                                          "events": [{"event": "thought", "text": "call me later"}]})
        self.assertEqual(self.agy()("hello", self.cwd())[0], "fine", "an ordinary event was taken for a tool")

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
                  "password.txt", "keychain.db", "login.keychain-db", "refresh-token", "msal_token_cache.json"]
        ordinary = ["tokens.json", "token_usage.json", "tokenizer.json", "oauthflow.md", "credential_types.md",
                    "history.jsonl", "rollout-2024.jsonl", "settings.json", "config.toml", "installation_id",
                    "author.txt", "id_rsa.pub", "keyboard.json", "environment.json", "passport.pdf"]
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
        for name in ("PATH", "HOME", "LANG", "TMPDIR", "HTTPS_PROXY", "NO_PROXY", "SSL_CERT_FILE",
                     "TOKENIZERS_PARALLELISM", "SECRET_SANTA_LIST", "API_KEY_HELP"):
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
