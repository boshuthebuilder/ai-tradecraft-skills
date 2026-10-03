"""Fake `agy` and `codex` executables for the engine, card, isolation and vision tests.

No network, no real engine, no real home: each fake is a small Python script written into a temporary bin folder
and found first on PATH (or passed to an adapter as its binary). Its state folder is written into the script itself,
because the codex adapter passes the engine only a short allowlist of environment variables. In that folder:

- `scenario.json` scripts the replies: `{"replies": [reply, ...], "default": reply}`; call k takes `replies[k]`, then
  `default`. A reply is a dict with a `kind` (text, empty, quota, fail, tool, sleep, hold, write, replay) and options.
  `replay` writes a captured stdout and stderr (`stdout`, `stderr`: paths) back as they were; it exits 0 (or `rc`).
- `calls.jsonl` gets one line per call: argv, environment, stdin, working directory and its listing, process group,
  session, and the prompt as the engine saw it.

Card replies are built from the items in the prompt: each card names its own document's path and carries the first
run of four or more digits in that document's text, so a reply that swaps ids or crosses contents is visible in what
gets written. `cards_by_path` replaces fields of a document's card (an honest card written as the instructions
ask). Options change that: `swap` (two ids exchanged, cards in place), `cross` (contents rotated, ids and order
intact), `cross_paths` (two named documents' cards trade contents when both are in the call), `reorder` (a correct
reply in reverse order), `drop`, `extra`, `invalid`, `suffix`.
"""
import json
import os
import stat
import sys

FAKE = r'''#!%(python)s
import json, os, re, subprocess, sys, time
STATE = %(state)r
ENGINE = %(engine)r
HEARTBEAT = ("import sys, time\nfor _ in range(100):\n"
             "    with open(sys.argv[1], 'w') as f:\n        f.write(repr(time.time()))\n    time.sleep(0.1)\n")
HOLDER = ("import os, sys, time\nos.setsid()\n"
          "with open(sys.argv[2] + '.tmp', 'w') as f:\n    f.write(str(os.getpid()))\n"
          "os.replace(sys.argv[2] + '.tmp', sys.argv[2])\ntime.sleep(float(sys.argv[1]))\n")


def load(name, default):
    p = os.path.join(STATE, name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def items_in(prompt):
    i = prompt.find("Input items (JSON")
    if i < 0:
        return None
    return json.loads(prompt[prompt.index("\n", i) + 1:])


def card(it, r):
    nums = re.findall(r"\d{4,}", it.get("text", ""))[:1]
    c = {"id": it["id"], "doc_type": "Letter", "party": "Alex", "parties": [], "doc_date": "",
         "title": "Card of " + it["path"],
         "summary": "About " + it["path"] + "." + "".join(" Ref " + n + "." for n in nums) + r.get("suffix", ""),
         "key_facts": {"dates": [], "amounts": [], "reference_numbers": ["ref " + n for n in nums]},
         "category": "Other", "language": "en", "sensitive": False, "confidence": "high", "look": "",
         "proposed_name": ""}
    c.update((r.get("cards_by_path") or {}).get(it["path"], {}))  # an honest card, as the instructions ask
    return c


def answer(prompt, r):
    """The reply text for a text-like kind: cards for a card prompt, notes for a section prompt, pages for a vision
    prompt, else r["text"] (`{marker}` in it taken from the prompt by r["marker_re"])."""
    items = items_in(prompt)
    if items is not None:
        cards = [card(it, r) for it in items]
        if r.get("swap") and len(cards) >= 2:
            cards[0]["id"], cards[1]["id"] = cards[1]["id"], cards[0]["id"]
        if r.get("cross") and len(cards) >= 2:
            ids = [c["id"] for c in cards]
            cards = cards[1:] + cards[:1]
            for c, i in zip(cards, ids):
                c["id"] = i
        pos = [i for i, it in enumerate(items) if it["path"] in (r.get("cross_paths") or [])]
        if len(pos) == 2:  # these two documents' cards trade contents, ids and order intact
            a, b = pos
            cards[a], cards[b] = dict(cards[b], id=cards[a]["id"]), dict(cards[a], id=cards[b]["id"])
        if r.get("reorder"):
            cards = cards[::-1]
        if r.get("drop") and len(cards) >= 2:
            cards.pop()
        if r.get("extra"):
            cards.append(dict(card(items[0], r), id="d99"))
        if r.get("invalid") and len(cards) >= 2:
            del cards[-1]["summary"]
        return json.dumps({"items": cards})
    if "SECTION TEXT:" in prompt:
        if r.get("no_notes"):
            return json.dumps({})
        head = prompt[prompt.index("This is section"):].split(".")[0]
        return json.dumps({"notes": "notes on " + head[len("This is "):]})
    if "these image files: " in prompt:
        if r.get("no_pages"):
            return json.dumps({})
        names = prompt.split("these image files: ", 1)[1].split(".\n")[0].split(", ")
        pages = [{"file": f, "text": "transcribed " + f} for f in names]
        if r.get("drop") and len(pages) >= 2:
            pages.pop()
        if r.get("swap") and len(pages) >= 2:
            pages[0]["file"], pages[1]["file"] = pages[1]["file"], pages[0]["file"]
        if r.get("null_text"):
            pages[-1]["text"] = None
        return json.dumps({"pages": pages})
    text = r.get("text", "")
    text = text.replace("{prompt}", prompt)  # an engine that echoes what it was asked
    if "{marker}" in text:  # the invented name a canary prompt carries: `marker_re` is that prompt, one group
        text = text.replace("{marker}", re.search(r["marker_re"], prompt, re.S).group(1))
    return text


def main():
    raw = sys.stdin.read()
    if ENGINE == "agy":
        prompt = json.loads(raw.splitlines()[0])["message"]["content"] if raw.strip() else ""
    else:
        prompt = raw
    calls = os.path.join(STATE, "calls.jsonl")
    n = 0
    if os.path.exists(calls):
        with open(calls, encoding="utf-8") as f:
            n = sum(1 for _ in f)
    sc = load("scenario.json", {})
    r = (sc.get("replies") or [])[n] if n < len(sc.get("replies") or []) else sc.get("default", {"kind": "text"})
    cwd = os.getcwd()
    rec = {"engine": ENGINE, "argv": sys.argv, "env": dict(os.environ), "stdin": raw, "prompt": prompt, "cwd": cwd,
           "cwd_listing": sorted(os.listdir(cwd)), "pid": os.getpid(), "pgid": os.getpgid(0), "sid": os.getsid(0)}
    if sc.get("watch"):
        rec["watch"] = sorted(os.listdir(sc["watch"])) if os.path.isdir(sc["watch"]) else []
    with open(calls, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    kind = r.get("kind", "text")
    if kind == "sleep":
        hb = os.path.join(STATE, "heartbeat")
        subprocess.Popen([sys.executable, "-c", HEARTBEAT, hb], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while not os.path.exists(hb):
            time.sleep(0.02)
        time.sleep(r.get("seconds", 8))
        return 0
    if kind == "hold":
        # a grandchild that leaves the process group (setsid) but keeps the inherited stdout and stderr open
        pid_file = os.path.join(STATE, "holder.pid")
        subprocess.Popen([sys.executable, "-c", HOLDER, str(r.get("hold", 10)), pid_file], stdin=subprocess.DEVNULL)
        while not os.path.exists(pid_file):
            time.sleep(0.02)
        time.sleep(r.get("seconds", 8))
        return 0
    if kind == "replay":
        with open(r["stdout"], encoding="utf-8", newline="") as f:
            sys.stdout.write(f.read())
        with open(r["stderr"], encoding="utf-8", newline="") as f:
            sys.stderr.write(f.read())
        return r.get("rc", 0)
    if kind == "write":
        home = os.environ.get("HOME" if ENGINE == "agy" else "CODEX_HOME", "")
        target = os.path.join(home, r["name"])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as f:
            f.write("{}")
    if r.get("bad_bytes"):
        sys.stdout.flush()
        sys.stdout.buffer.write(b"\xff\xfe not utf-8 \x80\n")
        sys.stdout.buffer.flush()
        sys.stderr.buffer.write(b"warning \xff\xfe\n")
        sys.stderr.buffer.flush()
    text = "" if kind in ("empty", "quota", "fail") else answer(prompt, r)
    return agy(r, kind, text) if ENGINE == "agy" else codex(r, kind, text)


def agy(r, kind, text):
    usage = r.get("usage", {"input_tokens": 100, "output_tokens": 20})
    if kind in ("quota", "fail"):
        for ev in r.get("events", []):
            print(json.dumps(ev))
        sys.stderr.write(r.get("message", "") + "\n")
        if r.get("result_error") is not None:
            print(json.dumps({"event": "result", "result": {"status": "ERROR", "error": r["result_error"]}}))
        return r.get("rc", 1)
    for ev in r.get("events", []):
        print(json.dumps(ev))
    print(json.dumps({"event": "message", "message": {"role": "assistant", "content": text}}))
    result = {"status": "SUCCESS", "response": text, "usage": usage}
    if r.get("denied"):
        result["denied_actions"] = r["denied"]
    print(json.dumps({"event": "result", "result": result}))
    if r.get("stderr"):
        sys.stderr.write(r["stderr"] + "\n")
    return r.get("rc", 0)


def codex(r, kind, text):
    out = sys.argv[sys.argv.index("-o") + 1]
    print(json.dumps({"type": "thread.started", "thread_id": "fake"}))
    print(json.dumps({"type": "turn.started"}))
    if kind in ("quota", "fail"):
        print(json.dumps({"type": "error", "message": r.get("message", "")}))
        print(json.dumps({"type": "turn.failed", "error": {"message": r.get("message", "")}}))
        return r.get("rc", 1)
    print(json.dumps({"type": "item.completed", "item": {"id": "item_0", "type": "reasoning", "text": "thinking"}}))
    if kind == "tool":
        tool = {"id": "item_1", "type": r.get("item", "command_execution"), "command": "ls", "status": "completed"}
        print(json.dumps({"type": "item.started", "item": tool}))
        print(json.dumps({"type": "item.completed", "item": tool}))
    print(json.dumps({"type": "item.completed", "item": {"id": "item_2", "type": "agent_message", "text": text}}))
    print(json.dumps({"type": "turn.completed", "usage": r.get("usage", {"input_tokens": 100, "output_tokens": 20})}))
    with open(out, "wb") as f:
        f.write(text.encode("utf-8") + (b" \xff" if r.get("bad_bytes") else b""))
    return r.get("rc", 0)


sys.exit(main())
'''


class Fakes:
    """A bin folder holding fake `agy` and `codex`, each with its own state folder, under `base`."""

    def __init__(self, base):
        self.bin = os.path.join(base, "bin")
        os.makedirs(self.bin, exist_ok=True)
        self.state = {}
        for engine in ("agy", "codex"):
            state = os.path.join(base, "fake-%s" % engine)
            os.makedirs(state, exist_ok=True)
            self.state[engine] = state
            path = os.path.join(self.bin, engine)
            with open(path, "w", encoding="utf-8") as f:
                f.write(FAKE % {"python": sys.executable, "state": state, "engine": engine})
            os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def path(self, engine):
        return os.path.join(self.bin, engine)

    def script(self, engine, replies=(), default=None, watch=None):
        sc = {"replies": list(replies), "default": default or {"kind": "text", "text": "ok"}}
        if watch:
            sc["watch"] = watch
        with open(os.path.join(self.state[engine], "scenario.json"), "w", encoding="utf-8") as f:
            json.dump(sc, f)

    def calls(self, engine):
        p = os.path.join(self.state[engine], "calls.jsonl")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def reset(self, engine):
        p = os.path.join(self.state[engine], "calls.jsonl")
        if os.path.exists(p):
            os.remove(p)

    def read_state(self, engine, name):
        p = os.path.join(self.state[engine], name)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return f.read()

    def heartbeat(self, engine):
        return self.read_state(engine, "heartbeat")


def tool_env(base, fakes, **extra):
    """The environment a tool under test runs with: the fakes first on PATH, HOME and TMPDIR in temp folders, secrets
    set (fake values) so their removal can be checked, and ResourceWarning an error in every Python child."""
    home, tmp = os.path.join(base, "home"), os.path.join(base, "tmp")
    os.makedirs(home, exist_ok=True)
    os.makedirs(tmp, exist_ok=True)
    env = {"PATH": fakes.bin + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home, "TMPDIR": tmp,
           "LANG": "C.UTF-8", "PYTHONWARNINGS": "error::ResourceWarning"}
    env.update(SECRETS)
    env.update(extra)
    return env


# every one of these must be kept from both engines (fake values, never real ones)
SECRETS = {"OPENAI_API_KEY": "sk-fake-not-a-key", "GEMINI_API_KEY": "fake", "ANTHROPIC_API_KEY": "fake",
           "GOOGLE_API_KEY": "fake", "OTHERVENDOR_API_KEY": "fake", "GOOGLE_APPLICATION_CREDENTIALS": "/nowhere.json",
           "CLOUDSDK_AUTH_ACCESS_TOKEN": "fake", "ANTHROPIC_AUTH_TOKEN": "fake", "AWS_SECRET_ACCESS_KEY": "fake",
           "SERVICE_CLIENT_SECRET": "fake", "OPENAI_BASE_URL": "http://127.0.0.1:9/", "Mixed_Case_Api_Key": "fake",
           "SOMEHUB_TOKEN": "fake", "OPENAI_API_BASE": "http://127.0.0.1:9/", "SERVICE_ENDPOINT": "http://127.0.0.1:9/",
           "GOOGLE_GENAI_USE_VERTEXAI": "true"}
