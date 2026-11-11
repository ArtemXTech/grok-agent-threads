#!/bin/zsh
# Install grok-agent-threads as a login item (launchd) and share it on your tailnet only.
#   scripts/install.sh "Your Name" ["Grok Bot"]   # your name, and the agent that will call it (default Grok Bot)
#   It creates an access key (~/.grok-agent-threads/key) and prints the address with it; set GROK_AGENT_THREADS_KEY=""
#   before running to go without one.
#   scripts/install.sh --uninstall
set -e
ROOT="${0:A:h:h}"
LABEL="com.grok-agent-threads.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PORT="${GROK_AGENT_THREADS_PORT:-8857}"
if [[ "$1" == "--uninstall" ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  tailscale serve --https="$PORT" off 2>/dev/null || true
  echo "Removed: login item and tailnet share on port $PORT."
  exit 0
fi
OWNER="${1:-the owner}"
CALLER="${2:-Grok Bot}"
command -v uv >/dev/null || { echo "Needs uv: https://docs.astral.sh/uv/"; exit 1; }
command -v tailscale >/dev/null || { echo "Needs the Tailscale CLI, signed in to your tailnet"; exit 1; }
mkdir -p "$HOME/.grok-agent-threads/logs" "$HOME/Library/LaunchAgents"
KEYFILE="$HOME/.grok-agent-threads/key"
if [[ -z "${GROK_AGENT_THREADS_KEY+set}" ]]; then
  [[ -s "$KEYFILE" ]] || (umask 077; python3 -c 'import secrets; print(secrets.token_urlsafe(24))' > "$KEYFILE")
  KEY="$(cat "$KEYFILE")"
else
  KEY="$GROK_AGENT_THREADS_KEY"
fi
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$ROOT/scripts/run.sh</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>GROK_AGENT_THREADS_OWNER</key><string>$OWNER</string>
    <key>GROK_AGENT_THREADS_CALLER</key><string>$CALLER</string>
    <key>GROK_AGENT_THREADS_KEY</key><string>$KEY</string>
    <key>GROK_AGENT_THREADS_PORT</key><string>$PORT</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/.grok-agent-threads/logs/server.log</string>
  <key>StandardErrorPath</key><string>$HOME/.grok-agent-threads/logs/server.log</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
tailscale serve --bg --https="$PORT" "http://127.0.0.1:$PORT" >/dev/null
NAME="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
for i in {1..20}; do curl -s -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 1; done
echo "grok-agent-threads is running and shared on your tailnet only:"
echo "  https://$NAME:$PORT/mcp${KEY:+?key=$KEY}"
[[ -n "$KEY" ]] && echo "The ?key= part is your access key (also in $KEYFILE). Keep it private; anyone with it on your tailnet can use every tool."
