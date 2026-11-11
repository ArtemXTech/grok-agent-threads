"""Codex threads through Codex's own app server (`codex app-server`, JSON-RPC over stdio, the interface the ChatGPT
and Codex apps use themselves). Same jobs as the Claude side: list, read, search, message, start.

A thread the ChatGPT app has open belongs to the app (only one writer per thread). A message to it goes into the
thread's queue, which the app picks up within about 10 s and runs as a normal turn; the answer is read back from the
thread. Every other thread gets a new turn directly from here."""
import json, os, queue, shutil, subprocess, threading, time, uuid
from pathlib import Path

CANDIDATES = [os.environ.get("CODEX_BIN", ""),
              "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
              "/Applications/Codex.app/Contents/Resources/codex", shutil.which("codex") or ""]
LOCKED = "already has an active writer"


def binary():
    return next((c for c in CANDIDATES if c and os.access(c, os.X_OK)), None)


def available():
    return binary() is not None


class AppServer:
    """One connection to `codex app-server`. Use as a context manager."""

    def __init__(self):
        self.p = subprocess.Popen([binary(), "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.n, self.waiting, self.lock, self.notes = 0, {}, threading.Lock(), queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self.call("initialize", {"clientInfo": {"name": "grok-agent-threads", "version": "1"},
                                 "capabilities": {"experimentalApi": True}})
        self._send({"jsonrpc": "2.0", "method": "initialized"})

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.p.terminate()

    def _send(self, o):
        with self.lock:
            self.p.stdin.write(json.dumps(o) + "\n")
            self.p.stdin.flush()

    def _pump(self):
        for line in self.p.stdout:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if "id" in o and "method" not in o:
                q = self.waiting.pop(o["id"], None)
                q and q.put(o)
            elif "id" in o:   # the server asks us something (an approval): decline, nobody is here to answer
                self._send({"jsonrpc": "2.0", "id": o["id"], "result": {"decision": "decline"}})
            else:
                self.notes.put(o)
        for q in list(self.waiting.values()):
            q.put({"error": {"message": "codex app-server exited"}})

    def call(self, method, params, timeout=60):
        with self.lock:
            self.n += 1
            i = self.n
        q = queue.Queue()
        self.waiting[i] = q
        self._send({"jsonrpc": "2.0", "id": i, "method": method, "params": params})
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            self.waiting.pop(i, None)
            return {"error": {"message": f"{method}: no answer in {timeout} s"}}


def _ok(r):
    if "error" in r:
        raise RuntimeError(r["error"].get("message", str(r["error"])))
    return r.get("result") or {}


def _row(t):
    t = t.get("thread", t)
    preview = (t.get("preview") or "").strip().splitlines()
    return {"id": t["id"], "title": t.get("name") or (preview[0][:80] if preview else "(untitled)"),
            "cwd": t.get("cwd", ""), "section": (t.get("section") or {}).get("name", ""),
            "updated": t.get("recencyAt") or t.get("updatedAt") or 0, "archived": bool(t.get("archived"))}


def list_threads(query="", limit=30, archived=False):
    with AppServer() as c:
        if query:
            r = _ok(c.call("thread/search", {"searchTerm": query, "limit": limit, "archived": archived}))
        else:
            r = _ok(c.call("thread/list", {"limit": limit, "archived": archived}))
    return [_row(t) for t in r.get("data", [])]


def read_thread(tid, turns=4):
    with AppServer() as c:
        t = _ok(c.call("thread/read", {"threadId": tid, "includeTurns": True}))["thread"]
    out = []
    for turn in t.get("turns", [])[-turns:]:
        for i in turn.get("items", []):
            if i.get("type") == "userMessage":
                out.append(("user", " ".join(x.get("text", "") for x in i.get("content", []) if isinstance(x, dict))))
            elif i.get("type") == "agentMessage" and i.get("text"):
                out.append(("codex", i["text"]))
    return _row(t), out, (t.get("turns") or [{}])[-1].get("status", "")


def _last_answer(c, tid, after_turns):
    t = _ok(c.call("thread/read", {"threadId": tid, "includeTurns": True}))["thread"]
    turns = t.get("turns", [])
    if len(turns) <= after_turns:
        return None, ""
    last = turns[-1]
    text = "\n\n".join(i["text"] for i in last.get("items", []) if i.get("type") == "agentMessage" and i.get("text"))
    return last.get("status"), text


def message_thread(tid, text, wait=100):
    """Returns (status, answer): answered, working, queued (the app holds it and has not started), or an error."""
    with AppServer() as c:
        before = len(_ok(c.call("thread/read", {"threadId": tid, "includeTurns": True}))["thread"].get("turns", []))
        r = c.call("thread/resume", {"threadId": tid})
        held = "error" in r and LOCKED in r["error"].get("message", "")
        if "error" in r and not held:
            return f"error: {r['error'].get('message')}", ""
        if held:
            _ok(c.call("thread/queue/add", {"threadId": tid, "clientUserMessageId": str(uuid.uuid4()),
                                            "input": [{"type": "text", "text": text}]}))
        else:
            _ok(c.call("turn/start", {"threadId": tid, "input": [{"type": "text", "text": text}]}))
        end = time.monotonic() + wait
        status, answer = None, ""
        while time.monotonic() < end:
            time.sleep(2)
            status, answer = _last_answer(c, tid, before)
            if status in ("completed", "failed", "interrupted"):
                return ("answered" if status == "completed" else status), answer
        if status is None:
            return ("queued" if held else "working"), ""
        return "working", answer


def start_thread(title, text, cwd, wait=100):
    with AppServer() as c:
        tid = _ok(c.call("thread/start", {"cwd": cwd}))["thread"]["id"]
        c.call("thread/name/set", {"threadId": tid, "name": title})
        _ok(c.call("turn/start", {"threadId": tid, "input": [{"type": "text", "text": text}]}))
        end = time.monotonic() + wait
        while time.monotonic() < end:
            time.sleep(2)
            status, answer = _last_answer(c, tid, 0)
            if status in ("completed", "failed", "interrupted"):
                return tid, answer
    return tid, ""
