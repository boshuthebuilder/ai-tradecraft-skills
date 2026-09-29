"""Engine adapters for bulk reading: Gemini through the `agy` CLI and ChatGPT through the `codex` CLI.

One login per machine per engine, shared by every project; context is isolated per call, credentials never are.
Each call runs in a fresh, empty working directory, with the prompt on stdin, tools refused, API keys removed
from the environment, in its own process group (killed on timeout). Outcomes are typed:

- `QuotaError` (with `reset_seconds` when the message says when): quota text is detected whatever the exit code.
- `DegenerateError`: an empty final answer (agy returns one after a denied tool attempt, about 3% of calls).
- `ToolUseError`: the model used a tool; the reply is discarded.
- `EngineError`: anything else the CLI reports.

An optional `state_home` points the engine's state (history, sessions) at a per-project folder. It must never hold
login files: it is scanned before and after every call, and a credential-like file fails the call. How each
engine reaches the shared login is decided by the isolation spike and recorded in the skill.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time

KEY_VARS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
QUOTA_RE = re.compile(r"quota|429|exhaust|rate.?limit|resource_exhausted|usage limit|too many requests", re.I)
CRED_RE = re.compile(r"(auth\.json|oauth|token|creds|credential)", re.I)
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
        return int(target - now_s if target > now_s else target + 86400 - now_s)
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
            if CRED_RE.search(f) and os.path.isfile(p) and not os.path.islink(p):
                found.append(os.path.relpath(p, home))
    return found


def _guard(home):
    if home:
        bad = credential_files(home)
        if bad:
            raise EngineError("credential-like files inside the per-project state folder %s: %s" % (home, bad[:5]))


def _run(cmd, stdin, env, cwd, timeout):
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd,
                         env=env, text=True, start_new_session=True)
    try:
        out, err = p.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.communicate()
        raise EngineError("timeout after %ss" % timeout)
    return p.returncode, out, err


def _env(extra):
    env = {k: v for k, v in os.environ.items() if k not in KEY_VARS}
    env["PATH"] = os.environ.get("PATH", "") + ":" + ":".join(SEARCH)
    env.update(extra)
    return env


class Agy:
    def __init__(self, model, binary=None, state_home=None, timeout=900):
        self.model, self.bin, self.home, self.timeout = model, find("agy", binary), state_home, timeout
        if not self.bin:
            raise EngineError("agy not found")

    def __call__(self, prompt, cwd, schema=None, model=None):
        msg = json.dumps({"event": "user", "message": {"role": "user", "content": prompt}}, ensure_ascii=False)
        cmd = [self.bin, "--input-format", "stream-json", "--output-format", "stream-json", "--model",
               model or self.model, "--sandbox", "--mode", "plan", "-p="]
        if schema:
            cmd[1:1] = ["--json-schema", schema]
        _guard(self.home)
        rc, out, err = _run(cmd, msg + "\n", _env({"HOME": self.home} if self.home else {}), cwd, self.timeout)
        _guard(self.home)
        result = None
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("event") == "result":
                result = ev.get("result")
        blob = out[-400:] + " " + err[-400:]
        if not result or result.get("status") != "SUCCESS":
            text = ((result or {}).get("error") or "") + " " + blob
            if QUOTA_RE.search(text):
                raise QuotaError(text.strip()[-300:], reset_seconds(text))
            raise EngineError("agy rc=%s: %s" % (rc, text.strip()[-300:]))
        response = result.get("response") or ""
        if not response.strip():
            raise DegenerateError("agy returned an empty answer (denied: %s)" % result.get("denied_actions"))
        return response, result.get("usage")


class Codex:
    def __init__(self, model=None, effort="medium", binary=None, state_home=None, timeout=1500):
        self.model, self.effort, self.home, self.timeout = model, effort, state_home, timeout
        self.bin = find("codex", binary)
        if not self.bin:
            raise EngineError("codex not found")

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
        text = open(outf, encoding="utf-8").read() if os.path.exists(outf) else ""
        if os.path.exists(outf):
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
