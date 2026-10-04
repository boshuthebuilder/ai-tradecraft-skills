"""Engine adapters for bulk reading: Gemini through the `agy` CLI and ChatGPT through the `codex` CLI.

One login per machine per engine, shared by every project; context is isolated per call, credentials never are.
Each call runs in a fresh, empty working directory, with the prompt on stdin, tools refused, keys, tokens and other
secrets removed from the environment, in its own process group (killed on timeout, and never waited on for longer
than KILL_GRACE after that). Output is read as UTF-8, with undecodable bytes replaced. Outcomes are typed:

- `QuotaError` (with `reset_seconds` when the message says when): quota text is detected whatever the exit code,
  and wins over an empty answer.
- `DegenerateError`: an empty final answer (agy returns one after a denied tool attempt, about 3% of calls).
- `ToolUseError`: the model used a tool (a codex tool item, or an agy stream event naming a tool, action, function
  or call, such as its `step_update` tool step, unless `allow_reads` is set for the vision lane and the tool only
  reads) or was refused one (an agy denied action); the reply is discarded.
- `PromptTooLong`: an agy prompt over AGY_MAX_PROMPT_BYTES, refused before the call because agy would cut it short
  without a word; `PromptCut` (a `PromptTooLong`) when the stream shows a cut that the check did not foresee.
- `CredentialError`: a credential-like file in the per-project state folder. It stops the run, not just the call.
- `SetupError`: the engine cannot run as configured (no binary, no model, a codex schema that is not strict). It
  stops the run.
- `EngineError`: anything else the CLI reports.

An optional `state_home` points the engine's state (history, sessions) at a per-project folder. It must never hold
login files: it is scanned before and after every call, and a credential-like regular file (not a symlink) fails the
run. How each engine reaches the shared login is decided by the isolation spike and recorded in the skill.

The flags below are the ones in use today, pinned by tests/test_engines.py. The isolation mode is the skill's
Engine isolation section; what is still provisional is marked below: the lists of environment variables (issue #91
records what each engine really reads). agy's prompt limit (AGY_MAX_PROMPT_BYTES) and its tool steps (AGY_TOOL_WORDS)
are settled from measurements and a real capture.
"""
import collections
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time

import common

KEY_VARS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
# Variables an engine must not inherit (provisional until the isolation spike, issue #91, records what each engine
# reads): keys, tokens, credentials and secrets, which would sign in or bill some other way than the machine's one
# login, and base URLs and endpoints, which would send the prompt to another service than the one that login belongs
# to. The name's ending decides. Proxy settings (HTTPS_PROXY, NO_PROXY, SSL_CERT_FILE) stay: they only route the
# call to the login's own service through the network this machine needs, and change neither who signs in nor where
# the prompt goes.
SECRET_VAR_RE = re.compile(r"(_API_KEY|_TOKEN|_CREDENTIALS|_SECRET|_SECRET_ACCESS_KEY|_BASE_URL|_API_BASE|_ENDPOINT)$",
                           re.I)
SECRET_VARS = {"GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_GENAI_USE_VERTEXAI"}
QUOTA_RE = re.compile(r"\bquota\b|\b429\b|\bexhausted\b|\brate.?limit|resource_exhausted|usage limit|"
                      r"too many requests", re.I)
# Credential stores are judged by file name. A name is one when a word of it (split at . _ - and spaces) is a
# credential word, or two words form a credential pair, or its extension is a credential store's; notes (.md and
# the like), public keys and anything about usage are not. So auth.json, oauth_creds.json, access_token.txt,
# tokens.json, cookies.sqlite, client_secret.json, api_key.txt, "API keys.txt", .netrc, .npmrc, .pgpass, .env,
# id_rsa, server.key, cert.pem, adc.json, password.txt and keychain.db are caught, and token_usage.json,
# tokenizer.json, access_log.txt, oauthflow.md and credential_types.md are not.
CRED_WORDS = {"auth", "oauth", "creds", "credential", "credentials", "secret", "secrets", "token", "tokens",
              "cookies", "password", "passwords", "passwd", "apikey", "netrc", "npmrc", "pgpass", "keychain", "adc"}
CRED_PAIRS = {("api", "key"), ("api", "keys"), ("private", "key"), ("id", "rsa"), ("id", "ed25519"),
              ("id", "ecdsa"), ("id", "dsa")}
CRED_EXTS = {".env", ".netrc", ".keychain", ".keychain-db", ".p12", ".pfx", ".key", ".pem", ".kdbx"}
NOT_CRED_EXTS = {".md", ".markdown", ".rst", ".html", ".pub"}
# agy stream events that show a tool at work. agy 1.2.16 streams a step as a `step_update` event whose nested step has
# a `step_type`: `user_input`, `agent_response` and `system_message` (agy's own note, which carries nothing but a
# duration) are plain, and anything else is a tool at work, whatever keys it has. The tool steps seen are
# `step_type: "tool"` with a `tool_name` and a `tool_info` (ACTIVE, then DONE or ERROR); that is settled from real
# captures (the fixture under tests/fixtures/agy), but the rule does not rest on it, so a step type nobody has seen
# fails the call rather than passing it. Other events are judged by words, and fail closed: an event whose type, or one
# of whose top-level keys, or a plain step's keys, has tool, action, function or call as a whole word (tool_call,
# functionCall, action), unless that key's value is empty (`tool_calls: []`). The init banner lists every tool agy has
# and is not a tool at work, so only a step is looked into.
AGY_PLAIN_STEPS = frozenset({"user_input", "agent_response", "system_message"})
AGY_TOOL_WORDS = {"tool", "tools", "action", "actions", "function", "functions", "call", "calls"}
# The tools the vision lane's model may use, each one a read, and only when every path it names (a parameter whose name
# says path, directory or file, or a value that looks like one) resolves inside the call's own working folder, which
# holds only its images (no --add-dir is passed, so there is no other folder). The tool names come from the init banner
# of the same capture. Any other tool, or a read of any other path, discards the reply; so does any tool in the cards
# lane, allowed or not.
AGY_READ_TOOLS = frozenset({"view_file", "list_dir", "find_by_name"})
AGY_PATH_WORDS = {"path", "paths", "dir", "directory", "file", "files", "folder", "root", "target"}
PATH_LIKE = re.compile(r"^(?:/|~|file:|[A-Za-z]:[\\/])|(?:^|[\\/])\.\.(?:[\\/]|$)")
ToolEvent = collections.namedtuple("ToolEvent", "label names params")
KILL_GRACE = 5  # seconds to wait for the pipes after killing a timed-out engine's process group
# agy cuts a user message at about 192,000 UTF-8 bytes of PROMPT TEXT (plus or minus 150), with no event, no field and
# exit 0, and leaves the model a stored copy to read with a tool these calls deny, so a run that needs the end of its
# prompt fails and one that does not reads as ok on part of its input. Measured on agy 1.2.16 with
# gemini-3.1-pro-high, 2026-10-03, 20 calls of synthetic text. The same bracket, 191,900 bytes whole to 192,188
# cut, held for ASCII and for CJK, so the limit is on the text's UTF-8 bytes: not characters, not the serialised
# message, not tokens. 180,000 is 6% under the cut: the measure is good to about 150 bytes, and the margin is for what
# was not measured (one agy build, one model, one prompt shape; a vendor re-tune would not announce itself).
# Re-probe on an agy upgrade, about 6 calls: one whole and one cut either side of the bracket, per corpus.
AGY_MAX_PROMPT_BYTES = 180_000
# The file agy keeps the full message in, which the model is pointed at once it has cut one. A step that names it,
# beside a refused `command`, is the stream's own evidence of a cut (see Agy.__call__); its absence proves nothing.
AGY_STORED_COPY = "transcript_full.jsonl"
# agy is never given `--json-schema`. In plan mode that flag sends the model through plan mode's own workflow: it writes
# a plan.md into agy's state folder (write_to_file, outside the call's folder), ends with `finish` steps and replies
# asking to be approved before the JSON, or, when the schema is passed as a string, with the finish tool's task
# summary in place of a card (real captures of agy 1.2.16, tests/fixtures/agy: the plan-mode stream, which the
# isolation rule discards). With the schema in the prompt instead, the model answers with the JSON alone and only
# user_input and agent_response steps. The engine checks nothing against the schema; the caller does (cards.py
# `schema_problems`). The text is part of the prompt, so the size limit counts it.
AGY_SCHEMA_INTRO = "\n\nReply with JSON only, matching this JSON Schema exactly:\n"
AGY_MODEL_REQUIRED = "--model is required for agy (it has no default here; its effort is encoded in the model id)"
CODEX_OFF = ["shell_tool", "unified_exec", "shell_snapshot", "memories", "apps", "browser_use",
             "browser_use_external", "computer_use", "in_app_browser", "image_generation", "multi_agent", "plugins",
             "remote_plugin", "code_mode_host", "hooks", "goals", "tool_suggest", "skill_mcp_dependency_install",
             "workspace_dependencies"]
NO_TOOLS = ("You have no tools in this session. Do not call any tool, run any command, read any file or make a "
            "plan. Everything you need is in this message. Answer directly with the JSON asked for.\n\n")
SEARCH = ["/opt/homebrew/bin", "/usr/local/bin", os.path.expanduser("~/.local/bin"), "/usr/bin", "/bin"]


class EngineError(Exception):
    pass


class QuotaError(EngineError):
    def __init__(self, msg, reset_seconds=None):
        super().__init__(msg)
        self.reset_seconds = reset_seconds


class PromptTooLong(EngineError):
    """A prompt agy would cut short: it keeps the start and asks the model to read the rest from a stored copy with a
    tool, which these calls deny, so the model would answer from part of its input."""


class PromptCut(PromptTooLong):
    """agy cut a prompt that passed the size check: the stream shows the model reading the stored copy and being
    refused a command. The same prompt would be cut again, so a caller does not retry it at that size."""


class DegenerateError(EngineError):
    pass


class ToolUseError(EngineError):
    pass


class CredentialError(EngineError, common.ToolError):
    """A credential-like file in the per-project state folder: the run stops (a ToolError is never retried)."""


class SetupError(EngineError, common.ToolError):
    """The engine cannot run as configured: the run stops rather than retrying every item."""


def is_secret_var(name):
    """An environment variable the engine must not see: SECRET_VAR_RE, the named keys and SECRET_VARS (see the
    comment above SECRET_VAR_RE)."""
    return name in KEY_VARS or name.upper() in SECRET_VARS or SECRET_VAR_RE.search(name) is not None


def is_credential_name(name):
    """True for a file name shaped like a credential store (see CRED_WORDS above)."""
    low = name.lower()
    stem, ext = os.path.splitext(low)
    if ext in CRED_EXTS or stem == ".env":
        return True
    if ext in NOT_CRED_EXTS or "usage" in stem:
        return False
    words = [w for w in re.split(r"[^a-z0-9]+", stem) if w]
    return bool(set(words) & CRED_WORDS) or any(p in CRED_PAIRS for p in zip(words, words[1:]))


def words(name):
    """The lower-case words of a name: split at non-alphanumerics and camelCase boundaries (functionCall: function,
    call)."""
    return {w.lower() for w in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", str(name))}


def tool_events(lines):
    """The agy stream events (other than the result) that show a tool at work, as ToolEvent(label, names, params): see
    AGY_PLAIN_STEPS and AGY_TOOL_WORDS. `names` are the tools the event names (`tool_name`, `tool_info.name`, a
    top-level `name`, the `name` inside a tool-keyed value), empty when it names none, which is never a read tool.
    `params` are the parameter dicts it carries (`tool_info.parameters`, `parameters`, `args`), empty when none."""
    found = []
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        is_step = ev.get("event") == "step_update"
        step = ev.get("step_update") if is_step else None
        step = step if isinstance(step, dict) else {}
        kind = "%s %s" % (ev.get("event", ""), ev.get("type", ""))
        keyed = _tool_keys(ev) + _tool_keys(step)
        stepped = is_step and str(step.get("step_type", "")) not in AGY_PLAIN_STEPS
        if words(kind) & AGY_TOOL_WORDS or stepped or keyed:
            names = frozenset(_tool_names(ev) | _tool_names(step))
            fallback = "step_update %s" % step.get("step_type", "") if is_step else kind.strip() or ",".join(keyed)
            found.append(ToolEvent(",".join(sorted(names)) or fallback.strip(), names, _tool_params(ev, step)))
    return found


def _tool_keys(mapping):
    return [k for k, v in mapping.items() if words(k) & AGY_TOOL_WORDS and v not in (None, "", [], {})]


def _tool_names(mapping):
    names = set()
    for key, value in mapping.items():
        if key in ("name", "tool_name") and isinstance(value, str) and value:
            names.add(value)
        elif words(key) & AGY_TOOL_WORDS:
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]:
                    names.add(item["name"])
    return names


def _tool_params(*mappings):
    found = []
    for m in mappings:
        info = m.get("tool_info")
        if isinstance(info, dict) and isinstance(info.get("parameters"), dict):
            found.append(info["parameters"])
        found += [m[k] for k in ("parameters", "params", "args", "arguments", "input") if isinstance(m.get(k), dict)]
    return found


def inside(folder, value):
    """Whether the path `value` (relative ones are taken from `folder`; symbolic links and `..` are resolved) is
    `folder` or something in it."""
    value = value[len("file://"):] if value.startswith("file://") else value
    if re.match(r"[A-Za-z]:[\\/]", value):
        return False
    base = os.path.realpath(folder)
    target = os.path.realpath(os.path.join(base, os.path.expanduser(value)))
    return target == base or target.startswith(base + os.sep)


def outside_paths(value, folder, key=""):
    """The strings in a tool's parameters that name a path outside `folder`: the value of a parameter whose name says
    path, directory or file, and any value that looks like a path (absolute, `~`, `file:`, a drive, or with `..`)."""
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in outside_paths(v, folder, k)]
    if isinstance(value, list):
        return [p for v in value for p in outside_paths(v, folder, key)]
    if isinstance(value, str) and (words(key) & AGY_PATH_WORDS or PATH_LIKE.search(value)):
        return [] if inside(folder, value) else [value]
    return []


def refused_tools(events, folder, allow_reads):
    """The labels of the tool events that discard the reply: all of them, unless `allow_reads`, which accepts a read
    tool (AGY_READ_TOOLS) whose every path parameter is inside `folder`."""
    refused = []
    for ev in events:
        if allow_reads and ev.names and ev.names <= AGY_READ_TOOLS and ev.params:
            outside = sorted({p for params in ev.params for p in outside_paths(params, folder)})
            if outside:
                refused.append("%s outside the call's folder: %s" % (ev.label, ", ".join(outside[:2])[:120]))
            continue
        refused.append(ev.label)
    return refused


def refuse_a_cut(lines, denied):
    """Raise PromptCut on positive evidence of a cut that the size check did not foresee: an agy stream event (the
    lines other than the result) naming the stored copy of the message, with a `command` refused in the result. That
    is the model's own attempt to read the rest. Absence proves nothing, since a task answerable from the head leaves
    no trace, so this only turns a failure into a clearer one; it never certifies a pass. The two halves are on
    different lines (a real agy 1.2.16 capture, tests/fixtures/agy: `step_update` tool steps whose `tool_info`
    names the file, ACTIVE then DONE, and only the final result carrying `denied_actions`), so they are put
    together across the stream. The file name is looked for anywhere in a line, so a rename of the step's fields
    does not blind it."""
    if not isinstance(denied, list):
        return
    refused = any("command" in words(d.get("action") if isinstance(d, dict) else d) for d in denied)
    if refused and any(AGY_STORED_COPY in line for line in lines):
        raise PromptCut("agy cut the prompt although it was under %d bytes: the model went to read the rest from %s "
                        "and was refused a command; split the input" % (AGY_MAX_PROMPT_BYTES, AGY_STORED_COPY))


def with_schema(prompt, schema):
    """`prompt` with the text of the JSON Schema file `schema` appended after AGY_SCHEMA_INTRO: how agy is asked for a
    shape (see AGY_SCHEMA_INTRO). A file that cannot be read stops the run, as a codex schema that is not strict
    does."""
    try:
        with open(schema, encoding="utf-8") as f:
            text = f.read().strip()
    except (OSError, ValueError) as ex:
        raise SetupError("agy output schema %s cannot be read: %s" % (schema, ex))
    return prompt + AGY_SCHEMA_INTRO + text


def not_strict(schema, where="$"):
    """Where a JSON schema falls short of the strict form codex's --output-schema needs: every object closed
    (`additionalProperties: false`) with every property required. An empty list means strict."""
    out = []
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            props = schema.get("properties", {})
            if schema.get("additionalProperties") is not False:
                out.append(where + ": additionalProperties is not false")
            if set(schema.get("required", [])) != set(props):
                out.append(where + ": not every property is required")
            for k, v in props.items():
                out += not_strict(v, "%s.%s" % (where, k))
        if "items" in schema:
            out += not_strict(schema["items"], where + "[]")
    return out


def reset_seconds(text, now=None):
    """Seconds until a quota resets, from "Resets in 2h13m5s" or "try again at 5:12 PM"; None if not stated."""
    m = re.search(r"Resets in (?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", text)
    if m and any(m.groups()):
        h, mi, s = (int(x or 0) for x in m.groups())
        return h * 3600 + mi * 60 + s
    m = re.search(r"try again at (\d{1,2}):(\d{2})\s*([AP]M)?", text, re.I)
    if m:
        t = time.localtime(now or time.time())
        hour, minute = int(m.group(1)), int(m.group(2))
        if m.group(3):
            hour = hour % 12 + (12 if m.group(3).upper() == "PM" else 0)
        target = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, hour, minute, 0, 0, 0, -1))
        now_s = time.mktime(t)
        return int(target - now_s if target >= now_s else target + 86400 - now_s)
    return None


def find(name, explicit=None):
    if explicit:
        return explicit
    return shutil.which(name, path=os.environ.get("PATH", "") + ":" + ":".join(SEARCH))


def credential_files(home):
    found = []
    for d, _ds, fs in os.walk(home):
        for f in fs:
            p = os.path.join(d, f)
            if is_credential_name(f) and os.path.isfile(p) and not os.path.islink(p):
                found.append(os.path.relpath(p, home))
    return found


def _guard(home):
    if home:
        bad = credential_files(home)
        if bad:
            raise CredentialError("credential-like files inside the per-project state folder %s: %s; no reply is "
                                  "used and the run stops" % (home, bad[:5]))


def _run(cmd, stdin, env, cwd, timeout):
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd,
                         env=env, encoding="utf-8", errors="replace", start_new_session=True)
    try:
        out, err = p.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            p.communicate(timeout=KILL_GRACE)
        except subprocess.TimeoutExpired:
            pass  # a descendant that left the group (setsid) still holds the pipes; stop waiting for it
        for pipe in (p.stdin, p.stdout, p.stderr):
            if pipe:
                pipe.close()
        p.wait()
        raise EngineError("timeout after %ss" % timeout)
    return p.returncode, out, err


def _env(extra):
    env = {k: v for k, v in os.environ.items() if not is_secret_var(k)}
    env["PATH"] = os.environ.get("PATH", "") + ":" + ":".join(SEARCH)
    env.update(extra)
    return env


class Agy:
    """`allow_reads` is for the vision lane only, where the model must open the images in its working folder: a tool
    event is then accepted when every tool it names is in AGY_READ_TOOLS and every path it names is inside that folder
    (plan mode refuses writes and commands, and a denied action still fails the call). Everywhere else any tool step
    in the stream fails the call, allowed or not."""

    def __init__(self, model, binary=None, state_home=None, timeout=900, allow_reads=False):
        self.model, self.bin, self.home, self.timeout = model, find("agy", binary), state_home, timeout
        self.allow_reads = allow_reads
        if not self.bin:
            raise SetupError("agy not found")
        if not model:
            raise SetupError(AGY_MODEL_REQUIRED)

    def __call__(self, prompt, cwd, schema=None, model=None):
        if schema:
            prompt = with_schema(prompt, schema)
        size = len(prompt.encode("utf-8"))
        if size > AGY_MAX_PROMPT_BYTES:
            raise PromptTooLong("a %d-byte prompt is over the %d-byte limit for agy here (it cuts a message at about "
                                "192,000 bytes of text and silently drops the rest); split the input"
                                % (size, AGY_MAX_PROMPT_BYTES))
        msg = json.dumps({"event": "user", "message": {"role": "user", "content": prompt}}, ensure_ascii=False)
        cmd = [self.bin, "--input-format", "stream-json", "--output-format", "stream-json", "--model",
               model or self.model, "--sandbox", "--mode", "plan", "-p="]
        _guard(self.home)
        rc, out, err = _run(cmd, msg + "\n", _env({"HOME": self.home} if self.home else {}), cwd, self.timeout)
        _guard(self.home)
        result, other = None, []
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                ev = None
            if isinstance(ev, dict) and ev.get("event") == "result":
                result = ev.get("result") or {}
            else:
                other.append(line)
        # the result line is left out of the quota search: its usage counts can read like a status code
        blob = "\n".join(other)[-400:] + " " + err[-400:]
        ok = bool(result) and result.get("status") == "SUCCESS"
        response = (result.get("response") or "") if ok else ""
        denied = (result or {}).get("denied_actions") or []
        if not response.strip():  # quota, failure or an empty answer first: a quota wait must not become a retry
            text = ((result or {}).get("error") or "") + " " + blob
            if QUOTA_RE.search(text):
                raise QuotaError(text.strip()[-300:], reset_seconds(text))
            if not ok:
                raise EngineError("agy rc=%s: %s" % (rc, text.strip()[-300:]))
            refuse_a_cut(other, denied)
            raise DegenerateError("agy returned an empty answer (denied: %s)" % denied)
        refuse_a_cut(other, denied)
        if denied:
            raise ToolUseError("agy was refused %s; reply discarded" % denied)
        used = refused_tools(tool_events(other), cwd, self.allow_reads)
        if used:
            raise ToolUseError("agy stream shows tool use %s; reply discarded" % sorted(set(used))[:5])
        return response, result.get("usage")


class Codex:
    def __init__(self, model=None, effort="medium", binary=None, state_home=None, timeout=1500):
        self.model, self.effort, self.home, self.timeout = model, effort, state_home, timeout
        self.bin = find("codex", binary)
        if not self.bin:
            raise SetupError("codex not found")

    def __call__(self, prompt, cwd, schema=None, model=None, effort=None):
        outf = os.path.join(cwd, "last_%d.txt" % os.getpid())
        cmd = [self.bin, "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral",
               "--ignore-user-config", "--ignore-rules", "--json", "-C", cwd, "-o", outf,
               "-c", 'web_search="disabled"', "-c", 'model_reasoning_effort="%s"' % (effort or self.effort),
               "-c", 'approval_policy="never"']
        for f in CODEX_OFF:
            cmd += ["--disable", f]
        if model or self.model:
            cmd += ["-m", model or self.model]
        if schema:
            with open(schema, encoding="utf-8") as f:
                problems = not_strict(json.load(f))
            if problems:
                raise SetupError("codex output schema %s is not strict: %s" % (schema, "; ".join(problems[:3])))
            cmd += ["--output-schema", schema]
        cmd.append("-")
        env = {k: os.environ[k] for k in ("LANG", "TMPDIR", "USER", "LOGNAME", "HOME") if k in os.environ}
        env["PATH"] = os.environ.get("PATH", "") + ":" + ":".join(SEARCH)
        if self.home:
            env["CODEX_HOME"] = self.home
        _guard(self.home)
        rc, out, err = _run(cmd, prompt, env, cwd, self.timeout)
        _guard(self.home)
        usage, tools, errs = None, [], []
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            t = ev.get("type", "")
            if t == "turn.completed":
                usage = ev.get("usage")
            elif t in ("turn.failed", "error"):
                errs.append(json.dumps(ev)[:400])
            elif t.startswith("item.") and (ev.get("item") or {}).get("type") not in (None, "agent_message",
                                                                                      "reasoning"):
                tools.append((ev.get("item") or {}).get("type"))
        text = ""
        if os.path.exists(outf):
            with open(outf, encoding="utf-8", errors="replace") as f:
                text = f.read()
            os.remove(outf)
        blob = " ".join(errs) + " " + err[-600:]
        if tools:
            raise ToolUseError("codex used tools %s; reply discarded" % sorted(set(tools)))
        if not text.strip():
            if QUOTA_RE.search(blob):
                raise QuotaError(blob.strip()[-400:], reset_seconds(blob))
            if rc == 0:
                raise DegenerateError("codex returned an empty answer")
            raise EngineError("codex rc=%s: %s" % (rc, blob.strip()[-300:]))
        return text, usage


def fresh_dir(prefix="engine_"):
    """An empty working directory for one call; the caller removes it."""
    return tempfile.mkdtemp(prefix=prefix)
