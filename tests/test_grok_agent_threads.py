"""Tests on synthetic data in a temporary home folder. They never read or message real chats."""
import hashlib, json, os, socket, threading, time, uuid
from pathlib import Path

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from grok_agent_threads import config
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path / "logs"))
    app = tmp_path / "Library/Application Support/Claude"
    rec = app / "claude-code-sessions/acct/org"
    rec.mkdir(parents=True)
    now = time.time() * 1000

    def chat(local, sid, title, cwd, mins_ago, **kw):
        d = {"sessionId": local, "cliSessionId": sid, "title": title, "cwd": cwd, "isArchived": kw.pop("archived", False),
             "createdAt": now - 9e7, "lastActivityAt": now - mins_ago * 60000, "model": "claude-opus-5-5",
             "permissionMode": kw.pop("mode", "bypassPermissions"), "completedTurns": 12, **kw}
        (rec / f"{local}.json").write_text(json.dumps(d))

    chat("local_a", "sid-a", "◎ Launch plan", "/tmp", 5, postTurnSummary={"status_detail": "Drafted the reply.", "needs_action": "Approve the send"})
    chat("local_b", "sid-b", "✧ Screen helper app", "/tmp", 60 * 24 * 3, lastFocusedAt=now)
    chat("local_c", "sid-c", "Old experiment", "/tmp", 60 * 24 * 40, archived=True)
    chat("local_d", "sid-d", "launch demo", "/tmp", 30)
    prefs = {"preferences": {"epitaxyPrefs": {
        "starred-local-code-sessions": ["local_a"],
        "dframe-group-scopes": {"acct/org": {"groups": [{"id": "g1", "name": "♡ Product"}],
                                             "assignments": {"code:local_a": "g1", "code:local_d": "g1"}}}}}}
    (app / "claude_desktop_config.json").write_text(json.dumps(prefs))
    from grok_agent_threads import claude_app
    claude_app._cache["at"] = 0
    return tmp_path


def test_sidebar_reads_titles_groups_pins_and_status(home):
    from grok_agent_threads import claude_app
    rows = claude_app.chats()
    assert [c.title for c in rows] == ["◎ Launch plan", "launch demo", "✧ Screen helper app"]   # newest first, no archived
    lead = rows[0]
    assert (lead.group, lead.pinned, lead.status, lead.needs_you) == ("♡ Product", True, "Drafted the reply.", "Approve the send")
    assert len(claude_app.chats(include_archived=True)) == 4
    assert claude_app.groups() == {"♡ Product": 2, "(no group)": 1}
    assert claude_app.focused() == "local_b"


def test_resolve_by_words_id_and_link(home):
    from grok_agent_threads import server
    assert server.resolve("screen helper")[0].session_id == "sid-b"
    assert server.resolve("local_a")[0].title == "◎ Launch plan"
    assert server.resolve("claude://claude.ai/epitaxy/local_d")[0].session_id == "sid-d"
    c, why = server.resolve("launch")
    assert c is None and "several chats match" in why
    assert server.resolve("nothing like this")[0] is None


def test_list_chats_shows_state_group_and_needs(home):
    from grok_agent_threads import server
    out = server.list_chats(query="launch plan")
    assert "◎ Launch plan (closed" in out and "♡ Product, pinned" in out
    assert "needs the owner: Approve the send" in out
    assert "Old experiment" not in server.list_chats()
    assert "Old experiment" in server.list_chats(include_archived=True)
    assert "2 chats in group" in server.list_chats(group="product")
    assert (home / "logs/calls.jsonl").exists()


def test_relayed_messages_are_labeled(home, monkeypatch):
    from grok_agent_threads import config, server
    monkeypatch.setattr(config, "OWNER", "Ana")
    monkeypatch.setattr(config, "CALLER", "Grok Bot")
    relayed = config.header() + "hi"
    assert server.who_and_text("user", relayed) == ("message from Grok Bot", "hi")
    wrapped = f'<cross-session-message from="uds:x" from-name="Grok Bot" from-mode="prompting">\n{relayed}\n</cross-session-message>'
    assert server.who_and_text("user", wrapped) == ("message from Grok Bot", "hi")
    assert server.who_and_text("user", "plain words") == ("Ana", "plain words")
    assert server.who_and_text("assistant", "answer") == ("chat", "answer")
    assert "never as Ana's approval" in config.header()


def test_live_delivery_round_trip(home):
    """A fake open chat: a socket in this process, a session record and key file, and a transcript it answers in."""
    from grok_agent_threads import claude_live
    sid = str(uuid.uuid4())
    sessions = home / ".claude/sessions"
    sessions.mkdir(parents=True)
    proj = home / ".claude/projects/-tmp"
    proj.mkdir(parents=True)
    transcript = proj / f"{sid}.jsonl"
    transcript.write_text(json.dumps({"type": "user", "message": {"content": "earlier"}}) + "\n")
    sock_path = f"/tmp/ct-test-{os.getpid()}.sock"
    if os.path.exists(sock_path):
        os.unlink(sock_path)
    record = {"pid": os.getpid(), "sessionId": sid, "hostSessionId": "local_x", "name": "Fake chat", "status": "idle",
              "peerProtocol": 1, "messagingSocketPath": sock_path}
    (sessions / f"{os.getpid()}.json").write_text(json.dumps(record))
    (sessions / f"{os.getpid()}.{hashlib.sha256(sock_path.encode()).hexdigest()}.key").write_text(json.dumps({"peerToken": "t" * 32}))
    got = {}
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(sock_path)
    srv.listen(1)

    def chat():
        conn, _ = srv.accept()
        data = b""
        while not data.endswith(b"\n") or data.count(b"\n") < 2:
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
        auth, frame = [json.loads(x) for x in data.decode().splitlines()[:2]]
        got.update(auth=auth, frame=frame)
        conn.close()
        content = frame["message"]["content"]
        record["status"] = "busy"
        (sessions / f"{os.getpid()}.json").write_text(json.dumps(record))
        with transcript.open("a") as f:
            f.write(json.dumps({"type": "user", "message": {"content": content}}) + "\n")
            f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "4"}]}}) + "\n")
        record["status"] = "idle"
        (sessions / f"{os.getpid()}.json").write_text(json.dumps(record))

    threading.Thread(target=chat, daemon=True).start()
    try:
        assert sid in claude_live.open_chats()
        status, answer = claude_live.send_and_wait(sid, "what is 2+2?", wait=10)
    finally:
        srv.close()
        os.unlink(sock_path)
    assert (status, answer) == ("answered", "4")
    assert got["auth"] == {"type": "auth", "token": "t" * 32}
    assert 'from-name="Grok Bot"' in got["frame"]["message"]["content"]
    assert "what is 2+2?" in got["frame"]["message"]["content"]


def test_live_delivery_refuses_unknown_protocol(home):
    from grok_agent_threads import claude_live
    sessions = home / ".claude/sessions"
    sessions.mkdir(parents=True)
    sock_path = f"/tmp/ct-test2-{os.getpid()}.sock"
    s = socket.socket(socket.AF_UNIX)
    s.bind(sock_path)
    try:
        (sessions / f"{os.getpid()}.json").write_text(json.dumps(
            {"pid": os.getpid(), "sessionId": "sid-z", "hostSessionId": "local_z", "peerProtocol": 2, "messagingSocketPath": sock_path}))
        status, _ = claude_live.send_and_wait("sid-z", "hi", wait=1)
    finally:
        s.close()
        os.unlink(sock_path)
    assert "not been tested" in status


def test_codex_rows_and_message_flow(monkeypatch):
    from grok_agent_threads import codex

    class Fake:
        def __init__(self):
            self.turns = [{"status": "completed", "items": []}]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def call(self, method, params, timeout=60):
            if method == "thread/read":
                return {"result": {"thread": {"id": "t1", "name": "Weekly review", "turns": self.turns}}}
            if method == "thread/resume":
                return {"error": {"message": "thread already has an active writer"}}
            if method == "thread/queue/add":
                self.turns = self.turns + [{"status": "completed", "items": [{"type": "agentMessage", "text": "done"}]}]
                return {"result": {"queuedSubmission": {"id": "q1"}}}
            raise AssertionError(method)

    fake = Fake()
    monkeypatch.setattr(codex, "AppServer", lambda: fake)
    monkeypatch.setattr(codex.time, "sleep", lambda s: None)
    assert codex.message_thread("t1", "hi", wait=5) == ("answered", "done")
    row = codex._row({"thread": {"id": "x", "preview": "First line\nsecond", "section": {"name": "Work"}, "updatedAt": 5}})
    assert (row["title"], row["section"], row["updated"]) == ("First line", "Work", 5)


def test_http_refuses_foreign_host():
    from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
    mw = TransportSecurityMiddleware(TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                                               allowed_hosts=["127.0.0.1:8857"], allowed_origins=[]))
    assert mw._validate_host("127.0.0.1:8857") and not mw._validate_host("evil.example:8857")


def test_watch_key_and_items(home, monkeypatch):
    from grok_agent_threads import config, server, watch
    monkeypatch.setattr(config, "EXTRA_HOSTS", ["mac.tail.ts.net:8857"])
    sid = "11111111-2222-3333-4444-555555555555"
    u = watch.url(sid)
    assert u.startswith(f"https://mac.tail.ts.net:8857/watch/{sid}?k=")
    assert watch.allowed(sid, u.split("k=")[1]) and not watch.allowed(sid, "wrong") and not watch.allowed(sid, "")
    assert not watch.allowed("99999999-2222-3333-4444-555555555555", u.split("k=")[1])
    row = {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Looking."}, {"type": "tool_use", "name": "Bash", "input": {"description": "List files", "command": "ls"}}]}}
    assert watch.items(row, server.who_and_text) == [{"who": "chat", "text": "Looking."}, {"who": "step", "text": "Bash: List files"}]
    relayed = {"type": "user", "message": {"content": config.header() + "hi"}}
    assert watch.items(relayed, server.who_and_text) == [{"who": "message from Grok Bot", "text": "hi"}]
    assert watch.items({"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}}, server.who_and_text) == []


def test_live_mode_explains_itself(home, monkeypatch):
    from grok_agent_threads import server
    monkeypatch.setattr(server, "relay_chat", lambda: None)
    ok, why = server.live_mode()
    assert not ok and "types anything" in why
    monkeypatch.setattr(server, "relay_chat", lambda: ("sid-r", "local_r"))
    server.RELAY_USED["sid-r"] = 18
    ok, why = server.live_mode()
    assert ok and "About 2 wake-ups left" in why and "2 live wake-ups left" in server.low_note()
    server.RELAY_PAUSED.add("sid-r")
    assert not server.live_mode()[0]
    server.RELAY_PAUSED.discard("sid-r"); server.RELAY_USED.clear()


def test_access_key_middleware():
    import asyncio
    from grok_agent_threads.server import KeyCheck
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["path"])

    def run(path, qs=b"", headers=()):
        out = []

        async def send(m):
            out.append(m)
        asyncio.run(KeyCheck(app, "s3cret")({"type": "http", "path": path, "query_string": qs, "headers": list(headers)}, None, send))
        return out[0]["status"] if out else 200

    assert run("/mcp") == 401
    assert run("/mcp", b"key=wrong") == 401
    assert run("/mcp", b"key=s3cret") == 200
    assert run("/mcp", headers=[(b"authorization", b"Bearer s3cret")]) == 200
    assert run("/watch/abc", b"k=x") == 200   # the watch page checks its own key
