"""A live view of one chat's work, as a web page: /watch/<session id>?k=<key>.

It follows the chat's transcript file, so it shows the work wherever the turn runs: in the Claude app, through the
relay, or in the background. The key is an HMAC of the session id with a secret kept in ~/.grok-agent-threads/secret, so
a link opens one chat and cannot be guessed."""
import asyncio, hashlib, hmac, html, json, os, secrets
from pathlib import Path

from . import config


def _secret():
    p = Path(config.LOG_DIR).parent / "secret"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    return p.read_text().strip().encode()


def key(sid):
    return hmac.new(_secret(), sid.encode(), hashlib.sha256).hexdigest()[:24]


def url(sid):
    base = f"https://{config.EXTRA_HOSTS[0]}" if config.EXTRA_HOSTS else f"http://127.0.0.1:{config.PORT}"
    return f"{base}/watch/{sid}?k={key(sid)}"


def allowed(sid, k):
    return bool(k) and hmac.compare_digest(k, key(sid))


def items(row, label):
    """Turn one transcript row into display items: {who, text}. `label(kind, text)` names the speaker."""
    kind, content = row.get("type"), (row.get("message") or {}).get("content")
    if kind not in ("user", "assistant"):
        return []
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])
    out = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text" and (b.get("text") or "").strip():
            who, text = label(kind, b["text"])
            if text and not text.startswith("<"):
                out.append({"who": who, "text": text[:6000]})
        elif b.get("type") == "tool_use":
            i = b.get("input") or {}
            what = i.get("description") or i.get("command") or i.get("file_path") or i.get("skill") or i.get("query") or ""
            out.append({"who": "step", "text": f"{b.get('name', 'tool')}: {str(what)[:160]}".rstrip(": ")})
    return out


async def events(path, label, disconnected, backlog=40):
    """Server-sent events: the last `backlog` items, then every new one as the transcript grows."""
    rows, pos = [], 0
    with open(path, "rb") as f:
        data = f.read()
        pos = len(data)
    for line in data.splitlines():
        if line.strip().startswith(b"{"):
            try:
                rows.extend(items(json.loads(line), label))
            except ValueError:
                pass
    for it in rows[-backlog:]:
        yield f"data: {json.dumps(it, ensure_ascii=False)}\n\n"
    idle = 0
    while not await disconnected():
        await asyncio.sleep(1)
        size = os.path.getsize(path)
        if size <= pos:
            idle += 1
            if idle % 15 == 0:
                yield ": keep-alive\n\n"
            continue
        with open(path, "rb") as f:
            f.seek(pos)
            chunk = f.read()
        cut = chunk.rfind(b"\n") + 1          # only whole lines; the rest comes with the next read
        pos += cut
        for line in chunk[:cut].splitlines():
            if line.strip().startswith(b"{"):
                try:
                    for it in items(json.loads(line), label):
                        yield f"data: {json.dumps(it, ensure_ascii=False)}\n\n"
                except ValueError:
                    pass


PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>
body{margin:0;background:#111;color:#e8e8e8;font:16px/1.5 -apple-system,system-ui,sans-serif}
header{position:sticky;top:0;background:#111;border-bottom:1px solid #2a2a2a;padding:12px 16px;font-weight:600}
header small{display:block;font-weight:400;color:#8a8a8a}
main{padding:8px 16px 80px;max-width:820px;margin:auto}
.i{margin:12px 0;white-space:pre-wrap;word-wrap:break-word}
.who{font-size:12px;color:#8a8a8a;text-transform:uppercase;letter-spacing:.04em}
.step{color:#9a9a9a;font:13px ui-monospace,Menlo,monospace;margin:4px 0}
.me .t{background:#1f2a3a;border-radius:12px;padding:10px 12px;display:inline-block}
#s{color:#6c6}
</style></head><body><header>__TITLE__<small><span id="s">live</span> · grok-agent-threads</small></header><main id="m"></main><script>
const m=document.getElementById('m'),s=document.getElementById('s');
const es=new EventSource(location.pathname+'/events'+location.search);
es.onmessage=e=>{const d=JSON.parse(e.data),el=document.createElement('div');
 const near=innerHeight+scrollY>=document.body.offsetHeight-120;
 if(d.who==='step'){el.className='step';el.textContent='▸ '+d.text}
 else{el.className='i'+(d.who==='chat'?'':' me');const w=document.createElement('div');w.className='who';w.textContent=d.who;
  const t=document.createElement('div');t.className='t';t.textContent=d.text;el.append(w,t)}
 m.append(el);if(near)scrollTo(0,document.body.scrollHeight)};
es.onerror=()=>{s.textContent='reconnecting';s.style.color='#c96'};es.onopen=()=>{s.textContent='live';s.style.color='#6c6'};
</script></body></html>"""


def page(title):
    return PAGE.replace("__TITLE__", html.escape(title))
