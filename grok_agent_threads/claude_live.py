"""Deliver a message into a Claude chat that is open in the Claude desktop app, and read its answer.

How it works, in three steps:
1. Find the chat. Every open chat writes ~/.claude/sessions/<pid>.json with its name, status (idle/busy) and the
   local socket it accepts messages on (the same one Claude chats use to message each other).
2. Send. Connect to that socket with the chat's own key file, and hand it one message from the calling agent.
   It shows in the chat as a message from another session, never as the owner typing.
3. Read the answer. Wait until the chat has taken the message and gone back to idle, then return what it wrote
   after the message, from its transcript. The chat just answers normally; it never has to message anyone back.
"""
import hashlib, json, os, socket, struct, time, uuid
from pathlib import Path
from . import config

FROM = "uds:/tmp/cc-socks/grok-agent-threads.sock"   # a name for the sender; the chat never needs to reply to it
PEER_PROTOCOL = 1                                # the version of the chats' local messaging this was built and tested on


def _sessions():
    return Path.home() / ".claude" / "sessions"


def _projects():
    return Path.home() / ".claude" / "projects"


def open_chats():
    """{sessionId: record} for every chat open in the Claude app with a live process and socket."""
    out = {}
    for p in _sessions().glob("[0-9]*.json"):
        try:
            d = json.loads(p.read_text())
            os.kill(d["pid"], 0)
            if d.get("hostSessionId") and Path(d.get("messagingSocketPath", "")).is_socket():
                out[d["sessionId"]] = d
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out


def _record(sid):
    return open_chats().get(sid)


def _transcript(sid):
    paths = list(_projects().glob(f"*/{sid}.jsonl"))
    if len(paths) != 1:
        raise RuntimeError("no single transcript for this chat")
    return paths[0]


def _text(row):
    c = (row.get("message") or {}).get("content")
    if isinstance(c, str):
        return c
    return "\n".join(b.get("text", "") for b in c or [] if isinstance(b, dict) and b.get("type") == "text")


def send_and_wait(sid, text, wait=45.0):
    """Returns (status, answer). status: answered, working (no answer within wait), or an error string."""
    d = _record(sid)
    if not d:
        return "not open in the Claude app", ""
    if d.get("peerProtocol") != PEER_PROTOCOL:
        return "this chat runs a Claude Code version the connector has not been tested with", ""
    tp = _transcript(sid)
    offset = tp.stat().st_size
    sock = d["messagingSocketPath"]
    key = _sessions() / f"{d['pid']}.{hashlib.sha256(sock.encode()).hexdigest()}.key"
    token = json.loads(key.read_text())["peerToken"]
    body = config.header() + text
    msg = {"type": "user", "session_id": sid, "uuid": str(uuid.uuid4()), "msg_id": uuid.uuid4().hex, "from": FROM,
           "priority": "next", "message": {"role": "user", "content":
           f'<cross-session-message from="{FROM}" from-name="{config.CALLER}" from-mode="prompting">\n{body}\n</cross-session-message>'}}
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(5)
        conn.connect(sock)
        if struct.unpack("i", conn.getsockopt(0, 2, 4))[0] != d["pid"]:   # the socket belongs to that chat's process
            return "socket does not belong to that chat", ""
        conn.sendall((json.dumps({"type": "auth", "token": token}) + "\n" + json.dumps(msg) + "\n").encode())
        try:   # the chat may close its end as soon as it has the message
            conn.shutdown(socket.SHUT_WR)
            conn.recv(1024)
        except (TimeoutError, OSError):
            pass

    # Wait for the chat to take the message, then to finish its turn, and collect what it wrote after it.
    end, received, answer = time.monotonic() + wait, False, []
    while time.monotonic() < end:
        time.sleep(1)
        with tp.open("rb") as f:
            f.seek(offset)
            rows = [json.loads(l) for l in f.read().splitlines() if l.strip().startswith(b"{")]
        answer = []
        for r in rows:
            if r.get("type") == "user" and body in _text(r):
                received, answer = True, []
            elif received and r.get("type") == "assistant" and _text(r).strip():
                answer.append(_text(r).strip())
        rec = _record(sid)
        if received and answer and rec and rec.get("status") == "idle":
            return "answered", "\n\n".join(answer)
    if not received:
        return "sent, but the chat has not taken it yet (it may be busy)", ""
    return "working", "\n\n".join(answer)
