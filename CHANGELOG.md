# Changelog

## 0.3.0 (2026-11-10)
- Live work in the Claude app for closed and new chats through the relay chat; background runs as the fallback.
- Live watch page for any chat (private link, streams messages and steps).
- `connector_status`, relay budget tracking, plain reasons when live mode is off.
- One writer per chat: a second message while a background turn runs is refused instead of starting a copy.
- `start_chat` returns in seconds and hands the request over after the chat exists.
- Install by prompt (docs/install-prompt.md), `scripts/check.py`, diagram.

## 0.2.0
- Codex threads: list, read, message, start through `codex app-server`.
- Claude app sidebar view: titles, groups, pins, archived, status lines.
- Package layout, install script (launchd + tailscale serve), docs, tests.
