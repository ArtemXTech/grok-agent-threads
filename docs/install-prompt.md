# Install by prompt

Open Claude Code on your Mac (the Claude desktop app's Code tab is best; the terminal works too), paste everything
below the line, and send it. Claude installs grok-agent-threads, checks it, sets up the relay chat, and gives you the
prompt for your agent. It asks you only for what it cannot decide: your name, which agent you use, and any install.

---

Install grok-agent-threads on this Mac for me: an MCP server that lets my outside agent (Grok Bot by default) list, read,
search, message and start my Claude Code chats and Codex threads, reachable only on my Tailscale network.
Repository: https://github.com/ArtemXTech/grok-agent-threads

Do these steps in order and tell me each result in one line:

1. Ask me two things in one message: my name (the chats will see "<name> typed this in <agent>") and which agent
   will call the server (default "Grok Bot").
2. Check what is installed: macOS, `uv`, `rg` (ripgrep), `git`, the Tailscale app with its CLI signed in
   (`tailscale status`), and optionally Codex (the ChatGPT app or the `codex` CLI). For anything missing, show me
   the one install command (Homebrew where possible) and run it only after I say yes. If Tailscale is not signed
   in, stop and tell me to sign in to the Tailscale app.
3. Clone the repository to ~/grok-agent-threads (or pull if it is already there), then run
   `scripts/install.sh "<my name>" "<my agent>"` from it. It installs a login item that keeps the server running on
   127.0.0.1:8857 and shares it on my tailnet only with `tailscale serve` (never Funnel). Show me the address it prints (it ends in ?key=, my access key).
4. Check it: `uv run scripts/check.py` in the repository. It must list the tools, the connector status and my 5
   newest chats. If anything fails, read ~/.grok-agent-threads/logs/server.log, fix what you can, and tell me the rest.
5. The relay chat (it lets my agent's work run live in the Claude app for chats that are not open there):
   if you are running inside the Claude desktop app and have a tool to start a new session, start one titled
   `⇄ grok-agent-threads relay` in ~/grok-agent-threads with the prompt in docs/relay-prompt.md (the part below its
   line), on a small fast model, and confirm it replied RELAY READY. Otherwise tell me to start that chat myself
   with that prompt and title.
6. Give me my agent's setup prompt: the text of docs/grok-setup-prompt.md below its line, with <ADDRESS> replaced by
   the address from step 3, in one code block I can copy. For another agent, tell me to add the address, with
   its ?key=, as a streamable HTTP MCP server.
7. Tell me in two lines what this gives my agent access to (all my chats, including running commands through them)
   and point me to docs/security.md for limiting the agent's Tailscale device to this one port.

Do not change any other settings, do not open anything to the internet, and do not delete anything.
