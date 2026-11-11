"""The Claude desktop app's own view of your chats: the same titles, groups, pins, archived state and last status
the sidebar shows. Read only; nothing here writes to the app's files.

The app keeps one small record per chat in
  ~/Library/Application Support/Claude/claude-code-sessions/<account>/<org>/local_<id>.json
and the sidebar groups and pins in claude_desktop_config.json (preferences.epitaxyPrefs).
When those are missing (another machine, a CLI-only setup), callers fall back to the Agent SDK's session list."""
import glob, json, os, subprocess, time
from dataclasses import dataclass, field
from pathlib import Path



def _app():
    return Path(os.environ.get("GROK_AGENT_THREADS_APP_DIR") or Path.home() / "Library/Application Support/Claude")
_cache = {"at": 0.0, "rows": []}


@dataclass
class Chat:
    local_id: str            # local_<uuid>, the id in claude://claude.ai/epitaxy/<local_id> links
    session_id: str          # the Claude Code session id (transcript file name)
    title: str
    cwd: str
    archived: bool
    last_activity: float     # ms since epoch
    created: float
    group: str = ""
    pinned: bool = False
    status: str = ""         # the app's one-line summary after the chat's last turn
    needs_you: str = ""
    model: str = ""
    turns: int = 0
    permission_mode: str = ""  # the mode the chat runs in inside the app (bypassPermissions, acceptEdits, ...)
    effort: str = ""
    extra: dict = field(default_factory=dict)


def available():
    return any(_app().glob("claude-code-sessions/*/*/local_*.json"))


def _prefs():
    try:
        return json.loads((_app() / "claude_desktop_config.json").read_text())["preferences"]["epitaxyPrefs"]
    except (OSError, ValueError, KeyError):
        return {}


def chats(include_archived=False):
    """Every chat the app knows, newest activity first. Cached for 15 s."""
    if time.time() - _cache["at"] > 15:
        prefs = _prefs()
        groups, assigned = {}, {}
        for scope in (prefs.get("dframe-group-scopes") or {}).values():
            groups.update({g["id"]: g["name"] for g in scope.get("groups", [])})
            assigned.update({k.split(":", 1)[-1]: v for k, v in (scope.get("assignments") or {}).items()})
        pinned = set(prefs.get("starred-local-code-sessions") or [])
        rows = []
        for p in glob.glob(str(_app() / "claude-code-sessions/*/*/local_*.json")):
            try:
                d = json.loads(Path(p).read_text())
            except (OSError, ValueError):
                continue
            if not d.get("cliSessionId"):
                continue
            s = d.get("postTurnSummary") or {}
            rows.append(Chat(local_id=d["sessionId"], session_id=d["cliSessionId"], title=d.get("title") or "(untitled)",
                             cwd=d.get("cwd", ""), archived=bool(d.get("isArchived")),
                             last_activity=d.get("lastActivityAt") or d.get("createdAt") or 0, created=d.get("createdAt") or 0,
                             group=groups.get(assigned.get(d["sessionId"], ""), ""), pinned=d["sessionId"] in pinned,
                             status=s.get("status_detail", ""), needs_you=s.get("needs_action", ""),
                             model=d.get("model", ""), turns=d.get("completedTurns") or 0,
                             permission_mode=d.get("permissionMode", ""), effort=d.get("effort", "")))
        rows.sort(key=lambda c: -c.last_activity)
        _cache.update(at=time.time(), rows=rows)
    return [c for c in _cache["rows"] if include_archived or not c.archived]


def groups():
    names = {}
    for c in chats():
        names[c.group or "(no group)"] = names.get(c.group or "(no group)", 0) + 1
    return names


def focused():
    """local_ id of the chat the owner last had in front in the app (highest lastFocusedAt), or None."""
    best, at = None, 0
    for p in glob.glob(str(_app() / "claude-code-sessions/*/*/local_*.json")):
        try:
            d = json.loads(Path(p).read_text())
        except (OSError, ValueError):
            continue
        if (d.get("lastFocusedAt") or 0) > at:
            best, at = d["sessionId"], d["lastFocusedAt"]
    return best


def import_to_sidebar(session_id, keep_focus=True):
    """Add a session started outside the app to its sidebar with the app's own import link (claude://resume).
    The app always switches to the imported chat; with keep_focus it then switches back to the chat that was in
    front. Returns the new local_ id, or None when the import did not finish in 30 s."""
    was = focused() if keep_focus else None
    subprocess.run(["open", "-g", f"claude://resume?session={session_id}"], check=False)
    for _ in range(30):
        if any(_app().glob(f"claude-code-sessions/*/*/local_{session_id}.json")):
            _cache["at"] = 0
            if was:
                time.sleep(1)
                subprocess.run(["open", "-g", f"claude://claude.ai/epitaxy/{was}"], check=False)
            return f"local_{session_id}"
        time.sleep(1)
    return None


def open_in_app(local_id):
    """Show a chat in the app (claude://claude.ai/epitaxy/<local id>). The app loads it, which gives it a live inbox,
    so the work that follows streams in front of the owner."""
    subprocess.run(["open", "-g", f"claude://claude.ai/epitaxy/{local_id}"], check=False)
