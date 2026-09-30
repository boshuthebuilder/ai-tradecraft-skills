"""Engine adapters for bulk reading: Gemini through the `agy` CLI and ChatGPT through the `codex` CLI.

One login per machine per engine, shared by every project; context is isolated per call, credentials never are.
Each call runs in a fresh, empty working directory, with the prompt on stdin, tools refused, keys, tokens and other
secrets removed from the environment, in its own process group (killed on timeout, and never waited on for longer
than KILL_GRACE after that). Output is read as UTF-8, with undecodable bytes replaced. Outcomes are typed:

- `QuotaError` (with `reset_seconds` when the message says when): quota text is detected whatever the exit code,
  and wins over an empty answer.
- `DegenerateError`: an empty final answer (agy returns one after a denied tool attempt, about 3% of calls).
- `ToolUseError`: the model used a tool (a codex tool item, or an agy stream event naming a tool, action, function
  or call, unless `allow_reads` is set for the vision lane) or was refused one (an agy denied action); the reply is
  discarded.
- `CredentialError`: a credential-like file in the per-project state folder. It stops the run, not just the call.
- `SetupError`: the engine cannot run as configured (no binary, no model, a codex schema that is not strict). It
  stops the run.
- `EngineError`: anything else the CLI reports.

An optional `state_home` points the engine's state (history, sessions) at a per-project folder. It must never hold
login files: it is scanned before and after every call, and a credential-like regular file (not a symlink) fails the
run. How each engine reaches the shared login is decided by the isolation spike and recorded in the skill.

The flags below are the ones in use today, pinned by tests/test_engines.py. They are provisional: the isolation
spike (issue #91) decides the final isolation mode and flags per engine, and may change them.
"""
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
# Variables an engine must not inherit: keys, tokens, credentials and secrets (the name's ending decides), and base
# URLs, which would send the prompt to another endpoint than the one the machine's login belongs to.
SECRET_VAR_RE = re.compile(r"(_API_KEY|_AUTH_TOKEN|_ACCESS_TOKEN|_CREDENTIALS|_SECRET|_SECRET_ACCESS_KEY|_BASE_URL)$",
                           re.I)
QUOTA_RE = re.compile(r"\bquota\b|\b429\b|\bexhausted\b|\brate.?limit|resource_exhausted|usage limit|"
                      r"too many requests", re.I)
# Credential stores are judged by file name. A name is one when a word of it (split at . _ - and spaces) is a
# credential word, or two words form a credential pair, or its extension is a credential store's; notes (.md and
# the like), public keys and anything about usage are not. So auth.json, oauth_creds.json, access_token.txt,
# client_secret.json, api_key.txt, .netrc, .env, id_rsa, password.txt and keychain.db are caught, and tokens.json,
# token_usage.json, tokenizer.json, oauthflow.md and credential_types.md are not.
CRED_WORDS = {"auth", "oauth", "creds", "credential", "credentials", "secret", "secrets", "token", "password",
              "passwords", "passwd", "apikey", "netrc", "keychain"}
CRED_PAIRS = {("api", "key"), ("private", "key"), ("id", "rsa"), ("id", "ed25519"), ("id", "ecdsa"), ("id", "dsa")}
CRED_EXTS = {".env", ".netrc", ".keychain", ".keychain-db", ".p12", ".pfx"}
NOT_CRED_EXTS = {".md", ".markdown", ".rst", ".html", ".pub"}
# agy stream events that show a tool at work: an event type or key naming a tool, action, function or call. The
# names are a fail-closed guess until the isolation spike (issue #91) records agy's real event names.
AGY_TOOL_RE = re.compile(r"tool|action|function|call", re.I)
KILL_GRACE = 5  # seconds to wait for the pipes after killing a timed-out engine's process group
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


class DegenerateError(EngineError):
    pass


class ToolUseError(EngineError):
    pass


class CredentialError(EngineError, common.ToolError):
    """A credential-like file in the per-project state folder: the run stops (a ToolError is never retried)."""


class SetupError(EngineError, common.ToolError):
    """The engine cannot run as configured: the run stops rather than retrying every item."""


def is_secret_var(name):
    """An environment variable the engine must not see (SECRET_VAR_RE, the named keys, and
    GOOGLE_APPLICATION_CREDENTIALS). An engine given one could bill, sign in or send the prompt some other way than
    through the machine's one login."""
    return (name in KEY_VARS or name.upper() == "GOOGLE_APPLICATION_CREDENTIALS"
            or SECRET_VAR_RE.search(name) is not None)


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


def tool_events(lines):
    """The agy stream events (other than the result) whose type or any key names a tool, action, function or
    call."""
    def keys(v):
        if isinstance(v, dict):
            for k, x in v.items():
                yield k
                yield from keys(x)
        elif isinstance(v, list):
            for x in v:
                yield from keys(x)
    found = []
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        kind = "%s %s" % (ev.get("event", ""), ev.get("type", ""))
        if AGY_TOOL_RE.search(kind) or any(AGY_TOOL_RE.search(str(k)) for k in keys(ev)):
            found.append(kind.strip() or "event")
    return found


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
    """`allow_reads` is for the vision lane only, where the model must open the images in its working folder: tool
    events are then accepted (plan mode refuses writes and commands, and a denied action still fails the call).
    Everywhere else any tool-like event in the stream fails the call."""

    def __init__(self, model, binary=None, state_home=None, timeout=900, allow_reads=False):
        self.model, self.bin, self.home, self.timeout = model, find("agy", binary), state_home, timeout
        self.allow_reads = allow_reads
        if not self.bin:
            raise SetupError("agy not found")
        if not model:
            raise SetupError("agy needs a model id (its effort is encoded in the id)")

    def __call__(self, prompt, cwd, schema=None, model=None):
        msg = json.dumps({"event": "user", "message": {"role": "user", "content": prompt}}, ensure_ascii=False)
        cmd = [self.bin, "--input-format", "stream-json", "--output-format", "stream-json", "--model",
               model or self.model, "--sandbox", "--mode", "plan", "-p="]
        if schema:
            cmd[1:1] = ["--json-schema", schema]
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
        used = [] if self.allow_reads else tool_events(other)
        if used:
            raise ToolUseError("agy stream shows tool use %s; reply discarded" % sorted(set(used))[:5])
        if not response.strip():
            text = ((result or {}).get("error") or "") + " " + blob
            if QUOTA_RE.search(text):
                raise QuotaError(text.strip()[-300:], reset_seconds(text))
            if not ok:
                raise EngineError("agy rc=%s: %s" % (rc, text.strip()[-300:]))
            raise DegenerateError("agy returned an empty answer (denied: %s)" % denied)
        if denied:
            raise ToolUseError("agy was refused %s; reply discarded" % denied)
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
