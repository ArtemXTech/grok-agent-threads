#!/bin/zsh
# Start grok-agent-threads with a clean environment (never a Claude app session's), accepting this Mac's tailnet name.
# Settings: GROK_AGENT_THREADS_OWNER, GROK_AGENT_THREADS_CALLER, GROK_AGENT_THREADS_PORT (see README).
set -e
cd "${0:A:h}/.."
PORT="${GROK_AGENT_THREADS_PORT:-8857}"
TS_NAME="$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)"
exec env -i HOME="$HOME" USER="$USER" PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin" \
  GROK_AGENT_THREADS_PORT="$PORT" GROK_AGENT_THREADS_HOSTS="${TS_NAME:+$TS_NAME:$PORT,$TS_NAME}" \
  GROK_AGENT_THREADS_KEY="${GROK_AGENT_THREADS_KEY:-}" GROK_AGENT_THREADS_OWNER="${GROK_AGENT_THREADS_OWNER:-the owner}" GROK_AGENT_THREADS_CALLER="${GROK_AGENT_THREADS_CALLER:-Grok Bot}" \
  "$(command -v uv)" run --quiet grok-agent-threads --port "$PORT"
